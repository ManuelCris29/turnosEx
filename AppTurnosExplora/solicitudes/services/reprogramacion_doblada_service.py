"""
ReprogramacionDobladaService

Gestiona el imprevisto de que UNA persona no pueda cumplir SU día de doblada en una doblada
ya aprobada (enfermedad, incapacidad…). Es simétrico (sirve para el solicitante o el receptor)
y NUNCA afecta al otro explorador. Todo queda en registro para auditoría:
- El día no cumplido se ANULA (soft-delete del Turno, ver Turno.anulado) y se le resta su deuda
  de 30 min (DeudaCorporativa → cancelada). Nada se borra físicamente.
- Al PROGRAMAR el día nuevo, la persona dobla esa fecha (tipo 'PAGO REPROGRAMADO') y se le vuelve
  a agregar la deuda de 30 min en la fecha real. Neto: 1 sola deuda de 30 min, en el día que sí dobla.

Para deshacer TODO el acuerdo se usa la cancelación mutua ya existente, permitida solo mientras
NADIE haya cumplido su día (ver `puede_cancelar`).
"""
from datetime import date
import logging

from django.db import transaction

from solicitudes.models import SolicitudCambio, ReprogramacionDiaDoblada
from .doblada_aplicacion_service import DobladaAplicacionService
from .d_fds_aplicacion_service import DFDSAplicacionService
from .deuda_corporativa_service import DeudaCorporativaService

logger = logging.getLogger(__name__)

TIPO_PAGO_REPROGRAMADO = 'PAGO REPROGRAMADO'


class ReprogramacionDobladaService:

    @staticmethod
    def _dia_doblada_de(solicitud: SolicitudCambio, explorador) -> date:
        """El día en que `explorador` se dobla en una DOBLADA sencilla: el receptor dobla en la
        fecha de cesión; el solicitante dobla en la fecha de pago."""
        detalle = solicitud.doblada
        if explorador.id == solicitud.explorador_receptor_id:
            return solicitud.fecha_cambio_turno
        if explorador.id == solicitud.explorador_solicitante_id:
            return detalle.fecha_pago
        raise ValueError('El explorador no participa en esta doblada.')

    @staticmethod
    def _fechas_activas_perm(explorador, det, lado: str) -> list:
        """Fechas en que `explorador` SE DOBLA en una doblada permanente (receptor en cesión;
        solicitante en devolución) y que siguen ACTIVAS (doblada PERM sin anular). Sirve para que
        el supervisor elija cuál día específico no se cumplió."""
        from turnos.models import Turno
        fechas_txt = det.fechas_cesion if lado == 'cesion' else det.fechas_devolucion
        fechas = []
        for s in (fechas_txt or '').split(','):
            s = s.strip()
            if s:
                try:
                    fechas.append(date.fromisoformat(s))
                except ValueError:
                    pass
        # Legacy (patrón por weekday, sin fechas): usar las dobladas PERM aplicadas en el rango.
        if not fechas:
            fechas = list(Turno.objects.filter(
                explorador=explorador, tipo_cambio='DOBLADA PERM',
                fecha__range=(det.fecha_inicio, det.fecha_fin)).values_list('fecha', flat=True))
        activas = set(Turno.objects.filter(
            explorador=explorador, tipo_cambio='DOBLADA PERM', fecha__in=fechas
        ).values_list('fecha', flat=True))
        return sorted(f for f in fechas if f in activas)

    @staticmethod
    def participantes_y_dias(solicitud: SolicitudCambio) -> list:
        """[(rol, explorador, [fechas de doblada reprogramables])] para DOBLADA o DOBLADA
        PERMANENTE. En sencilla cada uno tiene 1 día; en permanente, varias fechas específicas."""
        tipo = solicitud.tipo_cambio.nombre
        if tipo == 'DOBLADA':
            det = solicitud.doblada
            return [
                ('receptor', solicitud.explorador_receptor, [solicitud.fecha_cambio_turno]),
                ('solicitante', solicitud.explorador_solicitante, [det.fecha_pago]),
            ]
        if tipo == 'DOBLADA PERMANENTE':
            det = solicitud.doblada_permanente
            return [
                ('receptor', solicitud.explorador_receptor,
                 ReprogramacionDobladaService._fechas_activas_perm(solicitud.explorador_receptor, det, 'cesion')),
                ('solicitante', solicitud.explorador_solicitante,
                 ReprogramacionDobladaService._fechas_activas_perm(solicitud.explorador_solicitante, det, 'devolucion')),
            ]
        return []

    @staticmethod
    def _jornada_debida(explorador, fecha) -> str | None:
        """Jornada que la persona quedó debiendo = la CONTRARIA a su jornada base ese día."""
        from turnos.models import AsignarJornadaExplorador
        asg = (AsignarJornadaExplorador.objects.filter(explorador=explorador, fecha_inicio__lte=fecha)
               .select_related('jornada').order_by('-fecha_inicio').first())
        base = asg.jornada.nombre.upper() if asg and asg.jornada else None
        if base == 'AM':
            return 'PM'
        if base == 'PM':
            return 'AM'
        return None

    @staticmethod
    def puede_cancelar(solicitud: SolicitudCambio) -> bool:
        """Solo se puede CANCELAR (deshacer todo) si NINGÚN día de doblada se ha cumplido aún
        (ambas fechas de doblada son hoy o futuras). Si uno ya pasó, cancelar afectaría a quien
        ya cumplió → bloqueado (solo queda reprogramar el día del que falta)."""
        detalle = getattr(solicitud, 'doblada', None)
        if not detalle:
            return False
        hoy = date.today()
        return solicitud.fecha_cambio_turno >= hoy and detalle.fecha_pago >= hoy

    @staticmethod
    @transaction.atomic
    def registrar_inasistencia(solicitud: SolicitudCambio, explorador, supervisor=None,
                               motivo: str | None = None, fecha_original: date | None = None) -> ReprogramacionDiaDoblada:
        """Registra que `explorador` no cumplió UN día de doblada: anula ese día (soft-delete +
        resta sus 30 min) y crea la reprogramación en estado 'pendiente'.

        Para DOBLADA sencilla `fecha_original` se deriva (cada uno tiene 1 día); para DOBLADA
        PERMANENTE se pasa la fecha específica que no se cumplió."""
        if fecha_original is None:
            fecha_original = ReprogramacionDobladaService._dia_doblada_de(solicitud, explorador)

        ya = ReprogramacionDiaDoblada.objects.filter(
            doblada_origen=solicitud, explorador=explorador, fecha_original=fecha_original,
            estado__in=['pendiente', 'pagada'],
        ).first()
        if ya:
            raise ValueError('Ya existe una reprogramación para el día de doblada de esta persona.')

        DobladaAplicacionService.anular_doblada_de_un_dia(
            solicitud, explorador, fecha_original,
            motivo=f'Anulado por reprogramación (inasistencia){": " + motivo if motivo else ""}',
        )

        reprog = ReprogramacionDiaDoblada.objects.create(
            doblada_origen=solicitud,
            explorador=explorador,
            fecha_original=fecha_original,
            jornada_debida=ReprogramacionDobladaService._jornada_debida(explorador, fecha_original),
            estado='pendiente',
            motivo=motivo,
            registrado_por=supervisor,
        )
        logger.info("Reprogramación registrada: %s no cumplió %s (doblada %s).",
                    explorador, fecha_original, solicitud.id)
        return reprog

    @staticmethod
    @transaction.atomic
    def programar(reprog: ReprogramacionDiaDoblada, fecha_nueva: date) -> ReprogramacionDiaDoblada:
        """El supervisor programa el día en que la persona paga doblándose. Aplica la doblada ese
        día (sin pasar por el flujo normal) y le regenera los 30 min en la fecha real."""
        from solicitudes.services.ct_permanente_helper import _jornada_doblada_perm
        from core.services.cache_service import CacheService

        if reprog.estado != 'pendiente':
            raise ValueError('Esta reprogramación no está pendiente de programar.')
        if fecha_nueva == reprog.fecha_original:
            raise ValueError('El día de pago debe ser distinto al día que no se cumplió.')

        # La persona debe tener jornada única real ese día (para poder doblar = agregar la contraria).
        j = _jornada_doblada_perm(reprog.explorador, fecha_nueva)
        if j is None:
            raise ValueError(
                'Ese día la persona no tiene una jornada única para doblar (ya dobla, descansa, '
                'es festivo/fin de semana, o no tiene turno). Elige otro día.'
            )

        DFDSAplicacionService._crear_doblada_dia(
            reprog.explorador, fecha_nueva, tipo_cambio=TIPO_PAGO_REPROGRAMADO)

        # Regenerar los 30 min en la fecha real (misma regla que una doblada: solo lun-vie no festivo).
        if DeudaCorporativaService.aplica_deuda_doblada(fecha_nueva):
            DeudaCorporativaService.crear_deuda_corporativa(
                explorador=reprog.explorador, minutos=30, fecha_generacion=date.today(),
                fecha_doblada=fecha_nueva, solicitud=reprog.doblada_origen,
                comentario=f'Pago reprogramado por inasistencia del {reprog.fecha_original.strftime("%d/%m/%Y")}',
            )

        reprog.fecha_reprogramada = fecha_nueva
        reprog.estado = 'pagada'
        reprog.save(update_fields=['fecha_reprogramada', 'estado', 'actualizado_en'])

        CacheService.invalidar_cache_turnos_empleado(reprog.explorador_id, fecha_nueva.month, fecha_nueva.year)
        logger.info("Reprogramación %s programada: %s paga doblando el %s.",
                    reprog.id, reprog.explorador, fecha_nueva)
        return reprog

    @staticmethod
    @transaction.atomic
    def cancelar(reprog: ReprogramacionDiaDoblada) -> ReprogramacionDiaDoblada:
        """Cancela la reprogramación. Si el día nuevo ya se aplicó, lo anula (soft-delete + resta
        esos 30 min); el día original queda como estaba (anulado)."""
        from core.services.cache_service import CacheService
        if reprog.estado == 'pagada' and reprog.fecha_reprogramada:
            DobladaAplicacionService.anular_doblada_de_un_dia(
                reprog.doblada_origen, reprog.explorador, reprog.fecha_reprogramada,
                motivo='Anulado: reprogramación cancelada',
            )
            CacheService.invalidar_cache_turnos_empleado(
                reprog.explorador_id, reprog.fecha_reprogramada.month, reprog.fecha_reprogramada.year)
        reprog.estado = 'cancelada'
        reprog.save(update_fields=['estado', 'actualizado_en'])
        logger.info("Reprogramación %s cancelada.", reprog.id)
        return reprog
