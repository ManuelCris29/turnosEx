import logging

from django.core.exceptions import ValidationError  # type: ignore
from django.db import models
from empleados.models import Empleado
from core.utils.date_utils import DateUtils

logger = logging.getLogger(__name__)


class CTPermanenteValidator:
    """Validaciones específicas del Cambio de Turno Permanente (CT PERMANENTE)."""

    @staticmethod
    def validar_fechas_cambio_permanente(fecha_inicio, fecha_fin=None):
        """
        Validar fechas para cambio permanente.

        Args:
            fecha_inicio: Fecha de inicio del cambio permanente
            fecha_fin: Fecha de fin del cambio permanente (OBLIGATORIA según reglas de negocio)
        """
        from datetime import date, datetime

        # Convertir a date si es string
        if isinstance(fecha_inicio, str):
            fecha_inicio = DateUtils.parse_date(fecha_inicio)
        if fecha_fin and isinstance(fecha_fin, str):
            fecha_fin = DateUtils.parse_date(fecha_fin)

        # Validar que fecha_inicio no sea en el pasado
        if fecha_inicio < date.today():
            raise ValidationError('La fecha de inicio no puede ser en el pasado')

        # Validar que fecha_fin sea obligatoria
        if not fecha_fin:
            raise ValidationError('La fecha fin es obligatoria para cambios permanentes')

        # Validar que fecha_fin sea posterior a fecha_inicio
        if fecha_fin <= fecha_inicio:
            raise ValidationError('La fecha fin debe ser posterior a la fecha inicio')

    @staticmethod
    def validar_jornada_contraria_rango_permanente(solicitante: Empleado, receptor: Empleado, fecha_inicio, fecha_fin, dias_seleccionados=None):
        """
        Validar que haya al menos un día en el rango donde las jornadas REALES sean contrarias.

        Esta función evalúa día a día en el rango (o días seleccionados) usando las jornadas
        REALES de cada explorador (considera cambios aprobados previos).

        Args:
            solicitante: Empleado que solicita el cambio
            receptor: Empleado que recibe el cambio
            fecha_inicio: Fecha de inicio del rango
            fecha_fin: Fecha de fin del rango
            dias_seleccionados: Dict con 'dias_semana' (lista de ints) o 'fechas_especificas' (lista de strings)

        Raises:
            ValidationError: Si no hay ningún día en el rango donde las jornadas sean contrarias
        """
        from datetime import datetime, timedelta
        from turnos.services.jornada_service import JornadaService

        # Convertir fechas a date si son strings
        if isinstance(fecha_inicio, str):
            fecha_inicio = DateUtils.parse_date(fecha_inicio)
        if isinstance(fecha_fin, str):
            fecha_fin = DateUtils.parse_date(fecha_fin)

        # Generar lista de fechas a evaluar
        fechas_a_evaluar = []

        if dias_seleccionados:
            fechas_especificas = dias_seleccionados.get('fechas_especificas', [])
            dias_semana = dias_seleccionados.get('dias_semana', [])

            # Si hay fechas específicas, usarlas
            if fechas_especificas:
                for fecha_str in fechas_especificas:
                    try:
                        if isinstance(fecha_str, str):
                            fecha_obj = DateUtils.parse_date(fecha_str)
                        else:
                            fecha_obj = fecha_str
                        # Solo lunes-viernes
                        if fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                            fechas_a_evaluar.append(fecha_obj)
                    except (ValueError, TypeError):
                        continue
            # Si hay días de semana, generar fechas
            elif dias_semana:
                fecha_actual = fecha_inicio
                while fecha_actual <= fecha_fin:
                    if fecha_actual.weekday() in dias_semana and fecha_actual.weekday() < 5:
                        fechas_a_evaluar.append(fecha_actual)
                    fecha_actual += timedelta(days=1)

        # Si no hay días seleccionados, usar rango completo (solo lunes-viernes)
        if not fechas_a_evaluar:
            fecha_actual = fecha_inicio
            while fecha_actual <= fecha_fin:
                if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                    fechas_a_evaluar.append(fecha_actual)
                fecha_actual += timedelta(days=1)

        # Evaluar cada fecha para verificar jornadas contrarias
        dias_con_jornadas_contrarias = 0

        for fecha in fechas_a_evaluar:
            jornada_solicitante = JornadaService.get_jornada_explorador_fecha(solicitante.id, fecha)
            jornada_receptor = JornadaService.get_jornada_explorador_fecha(receptor.id, fecha)

            # Si ambos tienen jornada y son contrarias, contar este día
            if jornada_solicitante and jornada_receptor:
                if jornada_solicitante.nombre != jornada_receptor.nombre:
                    dias_con_jornadas_contrarias += 1

        # Si no hay ningún día con jornadas contrarias, rechazar
        if dias_con_jornadas_contrarias == 0:
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
    def validar_rango_completo_cambio_permanente(explorador_solicitante: Empleado, explorador_receptor: Empleado, fecha_inicio, fecha_fin, dias_seleccionados=None):
        """
        Validar que haya al menos un día válido en el rango (o días seleccionados) para cambio permanente.

        Los días inválidos se excluyen automáticamente (festivos, mantenimiento, descansos).
        Solo se rechaza la solicitud si NO hay ningún día válido en el rango.

        Días inválidos (se excluyen automáticamente):
        - Domingo
        - Sábado
        - Festivo
        - Día de mantenimiento
        - Día de temporada
        - Día de descanso del explorador

        Args:
            explorador_solicitante: Empleado solicitante
            explorador_receptor: Empleado receptor
            fecha_inicio: Fecha de inicio
            fecha_fin: Fecha de fin
            dias_seleccionados: Dict con días seleccionados (opcional)

        Raises:
            ValidationError: Si no hay ningún día válido en el rango
        """
        from datetime import datetime, timedelta

        if isinstance(fecha_inicio, str):
            fecha_inicio = DateUtils.parse_date(fecha_inicio)
        if isinstance(fecha_fin, str):
            fecha_fin = DateUtils.parse_date(fecha_fin)

        # Generar lista de fechas candidatas
        fechas_candidatas = []

        if dias_seleccionados:
            fechas_especificas = dias_seleccionados.get('fechas_especificas', [])
            dias_semana = dias_seleccionados.get('dias_semana', [])

            # Si hay fechas específicas, usarlas directamente (compatibilidad parcial)
            if fechas_especificas:
                for fecha_str in fechas_especificas:
                    try:
                        if isinstance(fecha_str, str):
                            fecha_obj = DateUtils.parse_date(fecha_str)
                        else:
                            fecha_obj = fecha_str
                        # Solo agregar si está dentro del rango y es lunes-viernes
                        if fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                            fechas_candidatas.append(fecha_obj)
                    except (ValueError, TypeError):
                        continue
            # Si hay días de semana, generar fechas
            elif dias_semana:
                dias_semana_int = [int(d) for d in dias_semana]
                fecha_actual = fecha_inicio
                while fecha_actual <= fecha_fin:
                    weekday = fecha_actual.weekday()
                    if weekday in dias_semana_int and weekday < 5:
                        fechas_candidatas.append(fecha_actual)
                    fecha_actual += timedelta(days=1)
        else:
            # Validar rango completo (retrocompatibilidad) - solo lunes-viernes
            fecha_actual = fecha_inicio
            while fecha_actual <= fecha_fin:
                if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                    fechas_candidatas.append(fecha_actual)
                fecha_actual += timedelta(days=1)

        # Filtrar fechas válidas (excluir festivos, mantenimiento, descansos, etc.)
        fechas_validas = []

        for fecha in fechas_candidatas:
            # Validar domingo (no debería llegar aquí si ya filtramos, pero por seguridad)
            if fecha.weekday() == 6:
                continue

            # Validar sábado (no debería llegar aquí si ya filtramos, pero por seguridad)
            if fecha.weekday() == 5:
                continue

            # Verificar si es festivo
            es_festivo = False
            try:
                from turnos.models import DiaEspecial
                es_festivo = DiaEspecial.es_festivo(fecha)
            except ImportError:
                pass

            if es_festivo:
                continue  # Excluir festivo, pero no rechazar toda la solicitud

            # Verificar si es mantenimiento
            es_mantenimiento = False
            try:
                from turnos.models import DiaEspecial
                es_mantenimiento = DiaEspecial.objects.filter(
                    fecha=fecha,
                    tipo='mantenimiento',
                    activo=True
                ).exclude(es_temporada=True).exists()
            except ImportError:
                pass

            if es_mantenimiento:
                continue  # Excluir mantenimiento

            # Verificar si es temporada
            es_temporada = False
            try:
                from turnos.models import DiaEspecial
                es_temporada = DiaEspecial.es_temporada_en(fecha)
            except ImportError:
                pass

            if es_temporada:
                continue  # Excluir temporada

            # Verificar si es día de descanso del solicitante
            es_descanso_solicitante = False
            try:
                from core.utils.jornada_utils import JornadaUtils
                from turnos.services.jornada_service import JornadaService

                jornada_base = JornadaService.get_jornada_explorador_fecha(
                    explorador_solicitante.id,
                    fecha.strftime('%Y-%m-%d')
                )
                if jornada_base:
                    jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
                    es_descanso_solicitante = (jornada_dia == "Descanso")
            except Exception:
                logger.warning("Error verificando descanso del solicitante en CT permanente (fecha=%s)", fecha, exc_info=True)

            if es_descanso_solicitante:
                continue  # Excluir día de descanso del solicitante

            # Verificar si es día de descanso del receptor
            es_descanso_receptor = False
            try:
                from core.utils.jornada_utils import JornadaUtils
                from turnos.services.jornada_service import JornadaService

                jornada_base = JornadaService.get_jornada_explorador_fecha(
                    explorador_receptor.id,
                    fecha.strftime('%Y-%m-%d')
                )
                if jornada_base:
                    jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
                    es_descanso_receptor = (jornada_dia == "Descanso")
            except Exception:
                logger.warning("Error verificando descanso del receptor en CT permanente (fecha=%s)", fecha, exc_info=True)

            if es_descanso_receptor:
                continue  # Excluir día de descanso del receptor

            # Si llegamos aquí, la fecha es válida
            fechas_validas.append(fecha)

        # Validar que haya al menos un día válido
        if not fechas_validas:
            raise ValidationError(
                'No se encontraron días válidos en el rango seleccionado. '
                'Todos los días son festivos, de mantenimiento, temporada, o días de descanso.'
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

                fecha_fin_existente = detalle.fecha_fin
                fecha_fin_nueva = fecha_fin

                # Si el cambio existente no tiene fecha fin, se considera indefinido (hasta el futuro)
                # Si el cambio nuevo no tiene fecha fin, también se considera indefinido

                # Verificar superposición:
                # - Si ambos tienen fecha fin: fecha_inicio <= fecha_fin_existente AND fecha_fin_nueva >= detalle.fecha_inicio
                # - Si existente no tiene fecha fin: fecha_inicio >= detalle.fecha_inicio (cualquier fecha nueva se superpone)
                # - Si nuevo no tiene fecha fin: fecha_inicio <= (fecha_fin_existente o futuro) AND fecha_inicio >= detalle.fecha_inicio

                if fecha_fin_existente is None:
                    # Cambio existente es indefinido: cualquier fecha nueva que sea >= fecha_inicio_existente se superpone
                    if fecha_inicio >= detalle.fecha_inicio:
                        raise ValidationError('Ya existe un cambio permanente superpuesto entre estos empleados')
                elif fecha_fin_nueva is None:
                    # Cambio nuevo es indefinido: se superpone si fecha_inicio <= fecha_fin_existente
                    if fecha_inicio <= fecha_fin_existente and fecha_inicio >= detalle.fecha_inicio:
                        raise ValidationError('Ya existe un cambio permanente superpuesto entre estos empleados')
                else:
                    # Ambos tienen fecha fin: verificar superposición estándar
                    if fecha_inicio <= fecha_fin_existente and fecha_fin_nueva >= detalle.fecha_inicio:
                        raise ValidationError('Ya existe un cambio permanente superpuesto entre estos empleados')
