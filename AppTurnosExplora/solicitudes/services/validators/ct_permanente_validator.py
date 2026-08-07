import logging

from django.core.exceptions import ValidationError  # type: ignore
from django.db import models
from empleados.models import Empleado
from core.utils.date_utils import DateUtils
from django.utils import timezone

logger = logging.getLogger(__name__)


#: Duración máxima (en días, extremos incluidos) del rango de un CT PERMANENTE.
#: 366 = un año, contando el bisiesto, para que "hoy → el mismo día del año que viene" entre justo.
#:
#: Es una regla de NEGOCIO, no un límite técnico: un cambio permanente más largo que un año no
#: tiene sentido operativo. De paso acota el coste de la búsqueda de compañeros, que evalúa
#: días × candidatos día a día y crece con el rango.
MAX_DIAS_RANGO_PERMANENTE = 366


class CTPermanenteValidator:
    """Validaciones específicas del Cambio de Turno Permanente (CT PERMANENTE)."""

    @staticmethod
    def validar_fechas_cambio_permanente(fecha_inicio, fecha_fin=None, es_revalidacion=False):
        """
        Validar fechas para cambio permanente.

        Args:
            fecha_inicio: Fecha de inicio del cambio permanente
            fecha_fin: Fecha de fin del cambio permanente (OBLIGATORIA según reglas de negocio)
            es_revalidacion: True al re-validar una solicitud ya enviada para aprobarla.

        "No empezar en el pasado" y la duración máxima del rango son reglas de CREACIÓN. Al
        re-validar para APROBAR se omiten: si no, una solicitud enviada para un rango que ya
        arrancó —o creada antes de que existiera el tope— quedaba inaprobable para siempre,
        aunque le quedaran semanas válidas por delante. Los días ya transcurridos los descarta
        `validar_rango_completo_cambio_permanente` (con `excluir_pasadas`), que además exige que
        quede al menos uno aplicable.
        """
        from datetime import date, datetime

        # Convertir a date si es string
        if isinstance(fecha_inicio, str):
            fecha_inicio = DateUtils.parse_date(fecha_inicio)
        if fecha_fin and isinstance(fecha_fin, str):
            fecha_fin = DateUtils.parse_date(fecha_fin)

        # Validar que fecha_inicio no sea en el pasado
        if not es_revalidacion and fecha_inicio < timezone.localdate():
            raise ValidationError('La fecha de inicio no puede ser en el pasado')

        # Validar que fecha_fin sea obligatoria
        if not fecha_fin:
            raise ValidationError('La fecha fin es obligatoria para cambios permanentes')

        # Validar que fecha_fin sea posterior a fecha_inicio
        if fecha_fin <= fecha_inicio:
            raise ValidationError('La fecha fin debe ser posterior a la fecha inicio')

        # Tope de duración (solo al CREAR: ver docstring).
        if not es_revalidacion:
            dias = (fecha_fin - fecha_inicio).days + 1
            if dias > MAX_DIAS_RANGO_PERMANENTE:
                raise ValidationError(
                    f'El cambio permanente no puede durar más de un año. '
                    f'El rango seleccionado ({fecha_inicio.strftime("%d/%m/%Y")} – '
                    f'{fecha_fin.strftime("%d/%m/%Y")}) abarca {dias} días. '
                    f'Acorta la fecha de fin.'
                )

    @staticmethod
    def validar_jornada_contraria_rango_permanente(solicitante: Empleado, receptor: Empleado, fecha_inicio, fecha_fin, dias_seleccionados=None):
        """
        Validar que haya al menos un día en el rango donde las jornadas REALES sean contrarias.

        Evalúa día a día con `jornadas_intercambiables_ct`, que usa `TurnoService.estado_dia`
        (la fuente de verdad de "Mis Turnos"), igual que la vista previa y la aplicación.

        OJO: esto es solo una comprobación temprana con mensaje claro. La garantía real de que
        NINGÚN día sin jornada contraria llegue a aplicarse la da la evaluación por día
        (`evaluar_fechas_ct_permanente`), que es la que decide qué fechas se materializan.

        Raises:
            ValidationError: Si no hay ningún día en el rango donde las jornadas sean contrarias
        """
        from solicitudes.services.ct_permanente_helper import (
            generar_fechas_candidatas_ct_permanente, jornadas_intercambiables_ct,
            precargar_ct_permanente,
        )

        if isinstance(fecha_inicio, str):
            fecha_inicio = DateUtils.parse_date(fecha_inicio)
        if isinstance(fecha_fin, str):
            fecha_fin = DateUtils.parse_date(fecha_fin)

        fechas_a_evaluar = generar_fechas_candidatas_ct_permanente(
            fecha_inicio, fecha_fin, dias_seleccionados
        )
        if not fechas_a_evaluar:
            raise ValidationError(
                'No se puede realizar el cambio permanente. '
                'No se encontraron días en el rango donde los empleados tengan jornadas contrarias. '
                'Los empleados deben tener jornadas opuestas (AM ↔ PM) en al menos un día del rango.'
            )

        # Precarga en lote: el barrido de abajo resolvía el estado de los dos empleados fecha a
        # fecha. Si el llamador ya precargó (vista previa, cálculo de compatibilidad), se reutiliza.
        with precargar_ct_permanente(
            [solicitante, receptor], min(fechas_a_evaluar), max(fechas_a_evaluar)
        ):
            if any(jornadas_intercambiables_ct(solicitante, receptor, f) for f in fechas_a_evaluar):
                return

        raise ValidationError(
            'No se puede realizar el cambio permanente. '
            'No se encontraron días en el rango donde los empleados tengan jornadas contrarias. '
            'Los empleados deben tener jornadas opuestas (AM ↔ PM) en al menos un día del rango.'
        )

    @staticmethod
    def validar_dias_seleccionados_permanente(fecha_inicio, fecha_fin, dias_seleccionados):
        """
        Validar que haya al menos un día seleccionado y que todos estén dentro del rango.

        Args:
            fecha_inicio: Fecha de inicio del cambio permanente
            fecha_fin: Fecha de fin del cambio permanente
            dias_seleccionados: Dict con 'dias_semana' (lista de ints) o 'fechas_especificas' (lista de strings YYYY-MM-DD)

        Raises:
            ValidationError: Si no hay días seleccionados o son inválidos
        """
        from datetime import datetime

        dias_seleccionados = dias_seleccionados or {}
        dias_semana = dias_seleccionados.get('dias_semana', [])
        fechas_especificas = dias_seleccionados.get('fechas_especificas', [])

        # Validar que haya al menos un día seleccionado (dias_semana o fechas_especificas)
        if not dias_semana and not fechas_especificas:
            raise ValidationError('Debe seleccionar al menos un día de la semana (lunes a viernes) para el cambio permanente.')

        # Validar días de semana si existen
        if dias_semana:
            # Validar que los días de semana sean lunes-viernes (0-4)
            dias_invalidos = [int(d) for d in dias_semana if int(d) < 0 or int(d) > 4]
            if dias_invalidos:
                raise ValidationError('Los cambios permanentes solo se pueden realizar de lunes a viernes (0=Lunes, 4=Viernes).')

        # Validar fechas específicas si existen
        if fechas_especificas:
            # Convertir fecha_inicio y fecha_fin a date si son strings
            if isinstance(fecha_inicio, str):
                fecha_inicio = DateUtils.parse_date(fecha_inicio)
            if isinstance(fecha_fin, str):
                fecha_fin = DateUtils.parse_date(fecha_fin)

            # Validar que todas las fechas estén dentro del rango
            fechas_fuera_rango = []
            for fecha_str in fechas_especificas:
                try:
                    if isinstance(fecha_str, str):
                        fecha_obj = DateUtils.parse_date(fecha_str)
                    else:
                        fecha_obj = fecha_str

                    if fecha_obj < fecha_inicio or fecha_obj > fecha_fin:
                        fechas_fuera_rango.append(fecha_str)

                    # Validar que no sea sábado ni domingo
                    if fecha_obj.weekday() >= 5:
                        raise ValidationError(f'Los cambios permanentes solo se pueden realizar de lunes a viernes. La fecha {fecha_str} es {"sábado" if fecha_obj.weekday() == 5 else "domingo"}.')
                except (ValueError, TypeError):
                    raise ValidationError(f'Fecha inválida en fechas específicas: {fecha_str}')

            if fechas_fuera_rango:
                raise ValidationError(f'Las siguientes fechas están fuera del rango seleccionado: {", ".join(fechas_fuera_rango)}')

    @staticmethod
    def validar_rango_completo_cambio_permanente(explorador_solicitante: Empleado, explorador_receptor: Empleado, fecha_inicio, fecha_fin, dias_seleccionados=None, es_revalidacion=False):
        """
        Validar que quede al menos un día APLICABLE en el rango (o en los días seleccionados).

        Los días inválidos se excluyen automáticamente; solo se rechaza la solicitud si no
        queda ninguno. Se excluyen: fines de semana, festivos, mantenimiento, temporada, días
        de descanso (estado REAL de "Mis Turnos"), días ya comprometidos por otra solicitud,
        días ya cambiados y días en los que ambos trabajan la MISMA jornada.

        Delega en `evaluar_fechas_ct_permanente`: es la misma función que usan la vista previa
        y la aplicación, así que las tres capas coinciden. Antes esta validación reimplementaba
        el descanso con la CONFIGURACIÓN base (`JornadaUtils.calcular_jornada_dia`) en lugar del
        estado real, y no miraba ni los cambios previos ni las jornadas contrarias: podía dar por
        bueno un rango cuyo conjunto aplicable real era vacío.

        Raises:
            ValidationError: Si no hay ningún día aplicable en el rango
        """
        from solicitudes.services.ct_permanente_helper import evaluar_fechas_ct_permanente

        if isinstance(fecha_inicio, str):
            fecha_inicio = DateUtils.parse_date(fecha_inicio)
        if isinstance(fecha_fin, str):
            fecha_fin = DateUtils.parse_date(fecha_fin)

        aplicables, excluidas = evaluar_fechas_ct_permanente(
            fecha_inicio, fecha_fin, explorador_solicitante, explorador_receptor,
            dias_seleccionados,
            # Al re-validar para aprobar, un rango que ya empezó solo vale por sus días futuros.
            excluir_pasadas=es_revalidacion,
        )

        if not aplicables:
            razones = sorted({e['razon'] for e in excluidas})
            detalle = f" Motivos: {', '.join(razones)}." if razones else ''
            raise ValidationError(
                'No se encontraron días válidos en el rango seleccionado. '
                'Todos los días quedan excluidos (fin de semana, festivo, mantenimiento, '
                'temporada, descanso, día ya comprometido o sin jornada contraria).'
                + detalle
            )

    @staticmethod
    def validar_no_cambio_permanente_superpuesto(solicitante: Empleado, receptor: Empleado, fecha_inicio, fecha_fin=None, excluir_id=None):
        """
        Validar que no haya cambios permanentes superpuestos.

        Args:
            solicitante: Empleado que solicita
            receptor: Empleado que recibe
            fecha_inicio: Fecha de inicio del cambio
            fecha_fin: Fecha de fin del cambio (opcional)
        """
        from datetime import datetime
        from solicitudes.models import SolicitudCambio, CambioPermanenteDetalle

        if isinstance(fecha_inicio, str):
            fecha_inicio = DateUtils.parse_date(fecha_inicio)
        if fecha_fin and isinstance(fecha_fin, str):
            fecha_fin = DateUtils.parse_date(fecha_fin)

        # Buscar cambios permanentes existentes entre estos empleados
        # Verificar en ambas direcciones: solicitante->receptor y receptor->solicitante
        cambios_existentes = SolicitudCambio.objects.filter(
            (
                (models.Q(explorador_solicitante=solicitante) & models.Q(explorador_receptor=receptor)) |
                (models.Q(explorador_solicitante=receptor) & models.Q(explorador_receptor=solicitante))
            ),
            tipo_cambio__nombre='CT PERMANENTE',
            estado__in=['pendiente', 'aprobada']
        ).select_related('cambio_permanente')

        # Al re-validar para aprobar, excluir la PROPIA solicitud (no es un solapamiento consigo misma).
        if excluir_id:
            cambios_existentes = cambios_existentes.exclude(id=excluir_id)

        for cambio in cambios_existentes:
            detalle = cambio.cambio_permanente
            if detalle:
                # Lógica correcta de superposición de rangos:
                # Dos rangos [a1, b1] y [a2, b2] se superponen si: a1 <= b2 AND b1 >= a2
                # Si b1 o b2 es None, significa que el rango es indefinido (hasta el futuro)

                # Solapamiento de intervalos, caso único: [a1, b1] y [a2, b2] se solapan si
                # a1 <= b2 AND b1 >= a2. Un `fecha_fin` nulo (rango indefinido, solo en registros
                # heredados: hoy fecha_fin es obligatoria) se trata como +infinito.
                #
                # Antes había tres ramas y la del rango existente indefinido exigía además
                # `fecha_inicio >= detalle.fecha_inicio`: un rango nuevo que empezara ANTES del
                # existente y se solapara después se colaba sin detectar.
                a1, b1 = fecha_inicio, fecha_fin
                a2, b2 = detalle.fecha_inicio, detalle.fecha_fin

                empieza_antes_de_que_acabe_el_otro = (b2 is None) or (a1 <= b2)
                acaba_despues_de_que_empiece_el_otro = (b1 is None) or (b1 >= a2)

                if empieza_antes_de_que_acabe_el_otro and acaba_despues_de_que_empiece_el_otro:
                    raise ValidationError('Ya existe un cambio permanente superpuesto entre estos empleados')
