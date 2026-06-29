"""
Doblada Permanente Strategy.

Doblada recurrente en días fijos de la semana dentro de un rango, con mutuo
acuerdo: el receptor cubre los días de cesión del solicitante y el solicitante
devuelve el favor doblándose en los días de devolución. Misma regla de negocio
que la doblada (jornadas contrarias, sin domingos ni festivos), pero recurrente.
"""
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from solicitudes.models import SolicitudCambio, DobladaPermanenteDetalle
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy
from turnos.services.jornada_service import JornadaService


def _csv(dias):
    """Normaliza una lista o csv de días a 'a,b,c' (enteros 0..6)."""
    if isinstance(dias, (list, tuple)):
        vals = dias
    else:
        vals = str(dias or '').split(',')
    out = [str(int(v)) for v in vals if str(v).strip().isdigit()]
    return ','.join(out)


def _set(dias_str):
    return {int(x) for x in (dias_str or '').split(',') if str(x).strip().isdigit()}


class DobladaPermanenteStrategy(SolicitudStrategy):

    def __init__(self):
        super().__init__("DOBLADA PERMANENTE")

    @staticmethod
    def _parse(fecha):
        if not fecha:
            return None
        if isinstance(fecha, str):
            try:
                return datetime.strptime(fecha, '%Y-%m-%d').date()
            except ValueError:
                return None
        return fecha

    @staticmethod
    def _grupo_base(explorador, fecha):
        # Grupo base (AM/PM) por ASIGNACIÓN de jornada, NO por el turno del día.
        # (En sábados/dobladas el turno del día no representa el grupo del explorador.)
        from turnos.models import AsignarJornadaExplorador
        asg = (
            AsignarJornadaExplorador.objects
            .filter(explorador=explorador, fecha_inicio__lte=fecha)
            .select_related('jornada')
            .order_by('-fecha_inicio')
            .first()
        )
        return asg.jornada.nombre.upper() if asg else None

    def _datos_desde_solicitud(self, solicitud):
        """Reconstruye los datos para re-validar al aprobar (ver base)."""
        det = getattr(solicitud, 'doblada_permanente', None)
        if not det:
            return None
        return {
            'explorador_solicitante': solicitud.explorador_solicitante,
            'explorador_receptor': solicitud.explorador_receptor,
            'tipo_cambio': solicitud.tipo_cambio,
            'comentario': solicitud.comentario or '',
            'fecha_inicio': det.fecha_inicio.strftime('%Y-%m-%d'),
            'fecha_fin': det.fecha_fin.strftime('%Y-%m-%d') if det.fecha_fin else None,
            'dias_cesion': det.dias_cesion,
            'dias_devolucion': det.dias_devolucion,
        }

    # --------------------------------------------------------------- validación
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            from ..solicitud_validator import SolicitudValidator

            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            fi = self._parse(datos.get('fecha_inicio'))
            ff = self._parse(datos.get('fecha_fin'))
            dias_cesion = _set(_csv(datos.get('dias_cesion')))
            dias_devolucion = _set(_csv(datos.get('dias_devolucion')))
            comentario = datos.get('comentario') or ''

            if not solicitante:
                return False, "Explorador solicitante es requerido"
            if not receptor:
                return False, "Debe seleccionar el compañero que cubrirá la doblada"
            if not fi or not ff:
                return False, "El rango de fechas (inicio y fin) es obligatorio"
            if not dias_cesion:
                return False, "Selecciona al menos un día de la semana que cedes"
            if not dias_devolucion:
                return False, "Selecciona al menos un día de la semana en que devolverás la doblada"

            SolicitudValidator.validar_empleado_activo(solicitante)
            SolicitudValidator.validar_empleado_activo(receptor)
            SolicitudValidator.validar_no_mismo_empleado(solicitante, receptor)
            SolicitudValidator.validar_comentario_obligatorio(comentario, 'la solicitud de doblada permanente')

            # No DUPLICADOS pendientes (regla de CREACIÓN; se OMITE al re-validar para aprobar).
            if not datos.get('es_revalidacion'):
                SolicitudValidator.validar_solicitante_sin_solicitud_pendiente_en_fecha(solicitante, fi)

            # Rango válido y no pasado
            from django.utils import timezone
            hoy = timezone.now().date()
            if ff < fi:
                return False, "La fecha de fin debe ser posterior a la fecha de inicio"
            if fi < hoy:
                return False, "El rango no puede iniciar en el pasado"

            # Rango dentro del MISMO mes
            if (fi.year, fi.month) != (ff.year, ff.month):
                return False, ("El rango debe estar dentro del mismo mes: la fecha de inicio y la de fin "
                               "deben caer en el mismo mes.")

            # Sanción (BLOQUEA): ni el solicitante ni el compañero pueden tener una sanción que solape el rango.
            # NOTA: la restricción médica NO bloquea; se avisa como advertencia en el procesamiento (ver vista).
            from empleados.models import SancionEmpleado
            from django.db.models import Q as _Q

            def _solapa_rango(model, campo_emp, emp):
                return model.objects.filter(**{campo_emp: emp}, fecha_inicio__lte=ff).filter(
                    _Q(fecha_fin__isnull=True) | _Q(fecha_fin__gte=fi)
                ).exists()

            if _solapa_rango(SancionEmpleado, 'explorador', solicitante):
                return False, "Estás sancionado en ese rango de fechas; no puedes crear la solicitud."
            if _solapa_rango(SancionEmpleado, 'explorador', receptor):
                return False, (f"{receptor.nombre} {receptor.apellido} está sancionado en ese rango. "
                               f"Elige otro compañero o ajusta las fechas.")

            # Solo lunes a viernes: la doblada permanente es RECURRENTE y los fines de semana se
            # rigen por alternancia (un sábado de media jornada es una excepción puntual, no
            # permanente). Para intercambiar un sábado puntual se usa Doblada de Fin de Semana.
            if (dias_cesion | dias_devolucion) & {5, 6}:
                return False, ("La doblada permanente es solo de lunes a viernes (no aplica fines de "
                               "semana). Para intercambiar un sábado usa una Doblada de Fin de Semana.")

            # Cesión y devolución no pueden compartir día de la semana (mismo día: descansar y doblar a la vez)
            interseccion = dias_cesion & dias_devolucion
            if interseccion:
                return False, ("Un mismo día de la semana no puede ser de cesión y de devolución a la vez. "
                               "Revisa los días seleccionados.")

            # Balance: a cada compañero le devuelves la misma cantidad de jornadas que te cubrió.
            # (Cada día = una jornada cubierta.)
            if len(dias_cesion) != len(dias_devolucion):
                return False, (
                    f"Debes devolver la misma cantidad de días que te cubren: te cubren {len(dias_cesion)} "
                    f"día(s) y estás devolviendo {len(dias_devolucion)}. Ajusta los días para que queden iguales."
                )

            # El compañero no puede tener YA otra doblada permanente (pendiente o aprobada) que
            # solape el rango y comparta días: quedaría doblemente comprometido.
            from solicitudes.models import DobladaPermanenteDetalle
            dias_acuerdo = dias_cesion | dias_devolucion
            otros = (
                DobladaPermanenteDetalle.objects
                .filter(solicitud__estado__in=['pendiente', 'aprobada'],
                        fecha_inicio__lte=ff, fecha_fin__gte=fi)
                .filter(_Q(solicitud__explorador_receptor=receptor) | _Q(solicitud__explorador_solicitante=receptor))
                .select_related('solicitud')
            )
            # Al re-validar para aprobar, excluir la PROPIA solicitud (no solapa consigo misma).
            _excluir = datos.get('solicitud_actual_id')
            if _excluir:
                otros = otros.exclude(solicitud_id=_excluir)
            for det in otros:
                dias_otro = _set(det.dias_cesion) | _set(det.dias_devolucion)
                if dias_acuerdo & dias_otro:
                    return False, (
                        f"{receptor.nombre} {receptor.apellido} ya tiene una doblada permanente en esos días "
                        f"dentro del rango. Elige otros días u otro compañero."
                    )

            # Jornadas contrarias (base) — al inicio del rango
            grupo_sol = self._grupo_base(solicitante, fi)
            grupo_rec = self._grupo_base(receptor, fi)
            if not grupo_sol or not grupo_rec:
                return False, "No se pudo determinar la jornada base de los exploradores"
            if grupo_sol == grupo_rec:
                return False, ("El compañero debe tener la jornada contraria (AM↔PM). "
                               "No puedes doblarte con alguien de tu misma jornada.")

            # Revalidar al FINAL del rango: si dentro del rango sus jornadas dejan de ser
            # contrarias (alguno cambia de jornada), no se permite.
            grupo_sol_fin = self._grupo_base(solicitante, ff)
            grupo_rec_fin = self._grupo_base(receptor, ff)
            if grupo_sol_fin and grupo_rec_fin and grupo_sol_fin == grupo_rec_fin:
                return False, ("Dentro del rango sus jornadas dejan de ser contrarias (alguno cambia de jornada). "
                               "Ajusta el rango o elige otro compañero.")

            # ===========================
            # OMITIR los días inválidos (como CT Permanente): NO se rechaza toda la solicitud.
            # ===========================
            # Se aplica solo en los días VÁLIDOS del rango; los inválidos (festivo, fin de semana,
            # mantenimiento, temporada, descanso o día ya comprometido de cualquiera de los dos)
            # se SALTAN en la aplicación. Aquí solo exigimos que quede AL MENOS un día válido para
            # que la solicitud tenga efecto.
            from solicitudes.services.doblada_permanente_aplicacion_service import (
                DobladaPermanenteAplicacionService as _DPAS,
            )
            # BALANCE: deben quedar días válidos en AMBOS lados (cubrir Y devolver). Si un lado
            # queda en 0, la doblada sería injusta (pagar sin cobertura o al revés) → se rechaza.
            _ex = datos.get('solicitud_actual_id')
            ocur_ces = list(_DPAS._ocurrencias(fi, ff, dias_cesion, solicitante, receptor, _ex))
            ocur_dev = list(_DPAS._ocurrencias(fi, ff, dias_devolucion, solicitante, receptor, _ex))
            if min(len(ocur_ces), len(ocur_dev)) == 0:
                return False, (
                    "En este rango no quedan días válidos para CUBRIR y DEVOLVER a la vez "
                    "(un lado queda en 0 por festivos, fines de semana, mantenimiento, temporada, "
                    "descansos o días ya comprometidos). Ajusta el rango o los días seleccionados."
                )

            return True, "Solicitud de doblada permanente válida"

        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Error validando doblada permanente: {str(e)}"

    # ------------------------------------------------------------------- crear
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        try:
            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fi = self._parse(datos.get('fecha_inicio'))
            ff = self._parse(datos.get('fecha_fin'))

            solicitud = SolicitudCambio.objects.create(
                explorador_solicitante=solicitante,
                explorador_receptor=receptor,
                tipo_cambio=tipo_cambio,
                comentario=comentario,
                fecha_cambio_turno=fi,  # fecha principal = inicio del rango
                estado='pendiente',
            )
            try:
                DobladaPermanenteDetalle.objects.create(
                    solicitud=solicitud,
                    fecha_inicio=fi,
                    fecha_fin=ff,
                    dias_cesion=_csv(datos.get('dias_cesion')),
                    dias_devolucion=_csv(datos.get('dias_devolucion')),
                    empleado_receptor=receptor,
                )
            except Exception:
                solicitud.delete()
                raise

            # Notificaciones + email (reutiliza el flujo de cambio de turno)
            try:
                from ..notificacion_service import NotificacionService
                NotificacionService.crear_notificacion_solicitud(solicitud)
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Error notificando doblada permanente %s", solicitud.id)

            return solicitud, "Solicitud de doblada permanente creada correctamente"

        except Exception as e:
            return None, f"Error creando solicitud de doblada permanente: {str(e)}"

    # ----------------------------------------------------------------- aplicar
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        try:
            from ..doblada_permanente_aplicacion_service import DobladaPermanenteAplicacionService
            from core.services.cache_service import CacheService

            with transaction.atomic():
                detalle = solicitud.doblada_permanente
                n_ces, n_dev = DobladaPermanenteAplicacionService.aplicar(solicitud, detalle)

            # Invalidar caché de ambos en los meses del rango
            solicitante = solicitud.explorador_solicitante
            receptor = solicitud.explorador_receptor
            detalle = solicitud.doblada_permanente
            meses = set()
            from datetime import timedelta
            d = detalle.fecha_inicio
            while d <= detalle.fecha_fin:
                meses.add((d.month, d.year))
                d += timedelta(days=28)
            meses.add((detalle.fecha_fin.month, detalle.fecha_fin.year))
            for (m, y) in meses:
                CacheService.invalidar_cache_turnos_empleado(solicitante.id, m, y)
                CacheService.invalidar_cache_turnos_empleado(receptor.id, m, y)

            return True, f"Doblada permanente aplicada ({n_ces} días de cesión, {n_dev} de devolución)."

        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Error aplicando doblada permanente")
            return False, f"Error aplicando doblada permanente: {str(e)}"

    # --------------------------------------------------- empleados disponibles
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """Compañeros con jornada contraria al solicitante (para cubrir la doblada)."""
        try:
            fecha_obj = self._parse(fecha)
            if not fecha_obj:
                return []
            grupo_sol = self._grupo_base(usuario_actual, fecha_obj)
            if not grupo_sol:
                return []
            contrario = 'PM' if grupo_sol == 'AM' else 'AM'

            from turnos.models import AsignarJornadaExplorador
            empleados = (
                Empleado.objects.filter(activo=True)
                .exclude(id=usuario_actual.id)
                .select_related('supervisor')
            )
            bases = {}
            for asg in (
                AsignarJornadaExplorador.objects
                .filter(explorador__in=empleados, fecha_inicio__lte=fecha_obj)
                .select_related('jornada', 'explorador')
                .order_by('explorador_id', '-fecha_inicio')
            ):
                bases.setdefault(asg.explorador_id, asg.jornada.nombre.upper())
            return [e for e in empleados if bases.get(e.id) == contrario]
        except Exception:
            return []

    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Dict[str, Any]:
        try:
            from core.services import get_turno_service
            return get_turno_service().get_turno_explorador(explorador_id, fecha)
        except Exception:
            return {}
