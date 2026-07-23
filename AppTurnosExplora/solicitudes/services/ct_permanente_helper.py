"""
Helper para calcular fechas aplicables de cambios permanentes.
Reutiliza la lógica de CTPermanenteStrategy para ser usada en otros contextos.
"""
from datetime import date, timedelta
from typing import List, Dict, Tuple
from empleados.models import Empleado
from turnos.models import DiaEspecial
from solicitudes.models import CambioPermanenteDetalle
import logging

logger = logging.getLogger(__name__)

_PRIORIDAD_RAZONES_CT_PERMANENTE = [
    # Más importante primero (opción 2: una sola razón por fecha)
    'Mantenimiento',
    'Festivo',
    'Temporada',
    # Día que ya no está en jornada predeterminada (no se puede aplicar el permanente):
    'Doblada Solicitante',
    'Doblada Receptor',
    'Cambio Previo Solicitante',
    'Cambio Previo Receptor',
    'Día libre Solicitante',
    'Día libre Receptor',
    'Descanso Solicitante',
    'Descanso Receptor',
    'Fines de semana',
]


def _razon_principal_ct_permanente(razones: List[str]) -> str:
    """
    Selecciona una sola razón principal (sin duplicar fechas en UI).
    Si no encuentra una razón conocida, retorna la primera.
    """
    if not razones:
        return ''
    for r in _PRIORIDAD_RAZONES_CT_PERMANENTE:
        if r in razones:
            return r
    return razones[0]


def calcular_fechas_aplicables_ct_permanente(
    detalle: CambioPermanenteDetalle,
    solicitante: Empleado,
    receptor: Empleado
) -> List[date]:
    """
    Calcula las fechas aplicables para un cambio permanente, excluyendo
    domingos, festivos, mantenimiento, temporadas y días de descanso.
    
    Args:
        detalle: Instancia de CambioPermanenteDetalle
        solicitante: Empleado solicitante
        receptor: Empleado receptor
        
    Returns:
        Lista de fechas ordenadas donde se aplicará el cambio
    """
    fecha_inicio = detalle.fecha_inicio
    fecha_fin = detalle.fecha_fin
    
    if not fecha_fin:
        # Si no hay fecha fin, usar fin de año
        fecha_fin = date(fecha_inicio.year, 12, 31)
    
    fechas_candidatas = set()
    
    # Obtener días seleccionados
    dias_seleccionados = detalle.dias.all()
    
    # Separar días de semana y fechas específicas
    dias_semana_list = []
    fechas_especificas_list = []
    
    for dia_seleccionado in dias_seleccionados:
        if dia_seleccionado.tipo == 'dia_semana' and dia_seleccionado.dia_semana is not None:
            dias_semana_list.append(dia_seleccionado.dia_semana)
        elif dia_seleccionado.tipo == 'fecha_especifica' and dia_seleccionado.fecha_especifica:
            fechas_especificas_list.append(dia_seleccionado.fecha_especifica)
    
    # Procesar fechas específicas primero (tienen prioridad)
    if fechas_especificas_list:
        for fecha_obj in fechas_especificas_list:
            # Solo agregar si está dentro del rango y es lunes-viernes
            if fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                fechas_candidatas.add(fecha_obj)
    
    # Procesar días de semana (solo si no hay fechas específicas)
    if dias_semana_list and not fechas_especificas_list:
        for dia_semana_buscado in dias_semana_list:
            # Día de semana: generar todas las ocurrencias dentro del rango
            fecha_actual = fecha_inicio
            
            # Avanzar hasta el primer día de la semana buscado
            dias_hasta_proximo = (dia_semana_buscado - fecha_actual.weekday()) % 7
            if dias_hasta_proximo > 0:
                fecha_actual += timedelta(days=dias_hasta_proximo)
            
            # Agregar todas las ocurrencias del día de semana dentro del rango
            # IMPORTANTE: Solo agregar si es lunes-viernes (weekday 0-4)
            while fecha_actual <= fecha_fin:
                if fecha_actual.weekday() < 5:  # 0-4 = lunes-viernes
                    fechas_candidatas.add(fecha_actual)
                fecha_actual += timedelta(days=7)  # Siguiente semana
    
    # Si no hay días seleccionados, usar rango completo (retrocompatibilidad)
    if not dias_semana_list and not fechas_especificas_list:
        # IMPORTANTE: Solo lunes-viernes (excluir sábados y domingos)
        fecha_actual = fecha_inicio
        while fecha_actual <= fecha_fin:
            if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                fechas_candidatas.add(fecha_actual)
            fecha_actual += timedelta(days=1)
    
    # Filtrar fechas inválidas (festivos, mantenimiento, descansos)
    fechas_finales = []
    for fecha_dia in sorted(list(fechas_candidatas)):
        es_domingo = fecha_dia.weekday() == 6
        es_festivo = _es_festivo(fecha_dia)
        es_mantenimiento = _es_mantenimiento(fecha_dia)
        es_temporada = _es_temporada(fecha_dia)
        es_descanso_solicitante = _es_dia_descanso(solicitante, fecha_dia)
        es_descanso_receptor = _es_dia_descanso(receptor, fecha_dia)
        tipo_previo_solicitante = _tipo_cambio_previo(solicitante, fecha_dia)
        tipo_previo_receptor = _tipo_cambio_previo(receptor, fecha_dia)

        if (not es_domingo and
            not es_festivo and
            not es_mantenimiento and
            not es_temporada and
            not es_descanso_solicitante and
            not es_descanso_receptor and
            not tipo_previo_solicitante and
            not tipo_previo_receptor and
            not _dia_libre_por_solicitud(solicitante, fecha_dia) and
            not _dia_libre_por_solicitud(receptor, fecha_dia)):
            fechas_finales.append(fecha_dia)

    return fechas_finales


def _es_festivo(fecha: date) -> bool:
    """Verificar si es festivo"""
    return DiaEspecial.es_festivo(fecha)


def _es_mantenimiento(fecha: date) -> bool:
    """Verificar si es día de mantenimiento EFECTIVO (temporada manda sobre mantenimiento)."""
    try:
        return DiaEspecial.es_mantenimiento_efectivo(fecha)
    except Exception:
        return False

def _es_temporada(fecha: date) -> bool:
    """Verificar si es temporada"""
    return DiaEspecial.es_temporada_en(fecha)


def _es_dia_descanso(explorador: Empleado, fecha: date) -> bool:
    """¿El explorador DESCANSA ese día? (estado REAL, no la configuración).

    FUENTE DE VERDAD ÚNICA: `TurnoService.estado_dia` — las mismas capas que pinta "Mis Turnos"
    (turno real, descanso por solicitud aprobada, alternancia de fin de semana, mantenimiento,
    temporada, festivo, base). Antes esto reimplementaba el cálculo con la CONFIGURACIÓN
    (jornada predeterminada + descanso de semana manual), lo que producía la incongruencia
    base-vs-real: días con turno real de trabajo se veían como descanso (y viceversa).

    Las razones de exclusión de grano fino (Festivo / Mantenimiento / Temporada / Día libre /
    Cambio previo) se siguen calculando aparte y tienen PRIORIDAD sobre 'Descanso', así que el
    solape con las capas de `estado_dia` no cambia el texto que ve el usuario.
    """
    try:
        from turnos.services.turno_service import TurnoService
        return not TurnoService.estado_dia(explorador, fecha).get('trabaja')
    except Exception:
        return False


def _tipo_cambio_previo(explorador: Empleado, fecha: date):
    """
    Devuelve el tipo de cambio que el explorador ya tiene ese día si su turno NO es su
    jornada predeterminada (doblada, CT sencillo, D FDS...), o None si está en estado
    predeterminado (sin turno, o turno del horario importado con tipo_cambio NULL).

    El CT permanente intercambia las jornadas PREDETERMINADAS; si ese día el explorador ya
    no está en su jornada predeterminada, ese día no puede incluirse en el cambio.
    """
    try:
        from turnos.models import Turno
        turnos = list(
            Turno.objects.filter(explorador=explorador, fecha=fecha)
            .exclude(tipo_cambio__isnull=True)
            .exclude(tipo_cambio='')
        )
        if not turnos:
            return None
        tipos = {t.tipo_cambio for t in turnos}
        # Una doblada deja 2 turnos (día completo): reportarla como doblada.
        if len(turnos) >= 2 or tipos & {'DOBLADA', 'DOBLADA PERM'}:
            return 'DOBLADA PERM' if 'DOBLADA PERM' in tipos else 'DOBLADA'
        return next(iter(tipos))
    except Exception:
        return None


def _dia_libre_por_solicitud(empleado: Empleado, fecha: date, excluir_id=None) -> bool:
    """
    ¿El empleado tiene el día LIBRE por una solicitud APROBADA (doblada cedida, pago de doblada,
    cambio de descanso, doblada permanente)? Capta los descansos por solicitud que NO dejan un
    registro Turno y que _es_dia_descanso (solo calendario/rotación) no ve — para que los
    formularios permanentes respeten "Mis Turnos".

    `excluir_id` ignora una solicitud (la PROPIA, al aplicarla ya aprobada) y evita auto-detección.
    """
    try:
        from turnos.services.turno_service import TurnoService
        return TurnoService.dia_comprometido_por_solicitud(empleado, fecha, excluir_id=excluir_id) is not None
    except Exception:
        return False


def _jornada_unica_real(explorador: Empleado, fecha: date):
    """
    Jornada ÚNICA real (AM/PM) del explorador ese día, para la DOBLADA PERMANENTE. Considera los
    turnos reales —incluidos los que cambian la jornada del día (CT sencillo/permanente)— y, si no
    hay turno, la jornada base. Devuelve None si el día tiene DOBLADA (AM+PM real) o no tiene una
    jornada única (así una doblada permanente no puede armarse sobre un día que ya está doblado).

    Deliberadamente NO usa `estado_dia` (su capa L2 de descanso por solicitud): así la jornada del
    día no se confunde con el descanso que genera la PROPIA doblada permanente al re-validar o
    re-aplicar. Los descansos por solicitud se filtran aparte con `_dia_libre_por_solicitud`
    (que sí admite `excluir_id`).
    """
    try:
        from turnos.models import Turno, AsignarJornadaExplorador
        turnos = list(
            Turno.objects.filter(explorador=explorador, fecha=fecha).select_related('jornada')
        )
        if turnos:
            js = {t.jornada.nombre.upper() for t in turnos if t.jornada}
            if 'AM' in js and 'PM' in js:
                return None  # doblada real → sin jornada única
            if 'AM' in js:
                return 'AM'
            if 'PM' in js:
                return 'PM'
            return None
        asg = (
            AsignarJornadaExplorador.objects
            .filter(explorador=explorador, fecha_inicio__lte=fecha)
            .select_related('jornada')
            .order_by('-fecha_inicio')
            .first()
        )
        j = asg.jornada.nombre.upper() if asg and asg.jornada else None
        return j if j in ('AM', 'PM') else None
    except Exception:
        return None


def _elegibles_contrarios_doblada(solicitante: Empleado, receptor: Empleado, fecha: date):
    """
    ¿En `fecha` el solicitante y el receptor son elegibles para doblarse? Ambos deben tener
    jornada ÚNICA real (AM/PM) y CONTRARIA entre sí. Devuelve (js, jr) si son contrarios, o None.
    """
    js = _jornada_doblada_perm(solicitante, fecha)
    jr = _jornada_doblada_perm(receptor, fecha)
    if js and jr and js != jr:
        return js, jr
    return None


def _jornada_doblada_perm(explorador: Empleado, fecha: date, excluir_id=None):
    """
    Jornada REAL efectiva (AM/PM) del explorador ese día para la DOBLADA PERMANENTE, según la
    FUENTE DE VERDAD de "Mis Turnos" (`TurnoService.estado_dia`): refleja turnos reales, temporada,
    alternancia de fin de semana, festivo y cambios (CT sencillo/permanente, cambio de descanso,
    doblada). Devuelve None si ese día NO tiene una jornada única con la que doblar: ya está en
    DOBLADA (AM+PM, incluidas las virtuales por temporada), descansa, o no tiene turno.

    A diferencia de `_jornada_unica_real` (que solo miraba turnos reales + base y no veía las
    dobladas/descansos VIRTUALES), este usa el estado completo del día. `excluir_id`: al
    re-validar/re-aplicar una doblada permanente ya aprobada, ignora el descanso que genera la
    PROPIA solicitud —que `estado_dia` no puede excluir— para no auto-excluirse.
    """
    try:
        from turnos.services.turno_service import TurnoService
        st = TurnoService.estado_dia(explorador, fecha)
        j = st.get('jornada')
        if j in ('AM', 'PM'):
            return j
        if j == 'DOBLADA':
            return None
        # Descanso / sin jornada. Si viene de una solicitud aprobada y —EXCLUYENDO la propia
        # (excluir_id)— el día ya NO estaría libre, ese descanso es de la PROPIA doblada permanente:
        # recuperar la jornada previa (turno real o base) para no auto-excluirse al re-validar.
        if excluir_id is not None and st.get('fuente') == 'solicitud':
            if not _dia_libre_por_solicitud(explorador, fecha, excluir_id):
                return _jornada_unica_real(explorador, fecha)
        return None
    except Exception:
        return None


def _motivo_no_doblada_perm(explorador: Empleado, fecha: date):
    """
    Razón corta (para el preview) por la que el explorador NO puede doblar ese día, o None si SÍ
    puede (tiene jornada única AM/PM). Usa `estado_dia` para dar el motivo REAL (coincide con
    "Mis Turnos"): ya doblada, festivo, temporada, mantenimiento, fin de semana o descanso.
    """
    try:
        from turnos.services.turno_service import TurnoService
        st = TurnoService.estado_dia(explorador, fecha)
        j = st.get('jornada')
        if j in ('AM', 'PM'):
            return None
        if j == 'DOBLADA':
            return 'Ese día ya tienes doblada (AM+PM)'
        fuente = st.get('fuente')
        motivo = st.get('motivo')
        etiquetas = {
            'festivo': 'Festivo',
            'temporada': 'Descanso de temporada',
            'mantenimiento': 'Mantenimiento',
            'alternancia': 'Descanso de fin de semana',
            'manual': 'Descanso de fin de semana',
        }
        if fuente in etiquetas:
            return etiquetas[fuente]
        if fuente == 'solicitud':
            return f'Ese día descansas ({motivo})' if motivo else 'Ese día descansas por otra solicitud'
        return motivo or 'Ese día descansas o no tienes turno'
    except Exception:
        return 'No se pudo determinar tu turno ese día'


def _razon_cambio_previo(tipo: str, es_solicitante: bool) -> str:
    """Etiqueta corta (para la vista previa) según el cambio que ya existe ese día."""
    quien = 'Solicitante' if es_solicitante else 'Receptor'
    if tipo in ('DOBLADA', 'DOBLADA PERM'):
        return f'Doblada {quien}'
    return f'Cambio Previo {quien}'


def calcular_fechas_aplicables_y_excluidas_ct_permanente(
    detalle: CambioPermanenteDetalle,
    solicitante: Empleado,
    receptor: Empleado
) -> Tuple[List[date], List[Dict[str, any]]]:
    """
    Calcula las fechas aplicables y excluidas para un cambio permanente.
    
    Args:
        detalle: Instancia de CambioPermanenteDetalle
        solicitante: Empleado solicitante
        receptor: Empleado receptor
        
    Returns:
        Tupla con:
        - Lista de fechas aplicables (válidas)
        - Lista de dicts con fechas excluidas: [{'fecha': date, 'razon': str}]
    """
    fecha_inicio = detalle.fecha_inicio
    fecha_fin = detalle.fecha_fin
    
    if not fecha_fin:
        # Si no hay fecha fin, usar fin de año
        fecha_fin = date(fecha_inicio.year, 12, 31)
    
    fechas_candidatas = set()
    
    # Obtener días seleccionados
    dias_seleccionados = detalle.dias.all()
    
    # Separar días de semana y fechas específicas
    dias_semana_list = []
    fechas_especificas_list = []
    
    for dia_seleccionado in dias_seleccionados:
        if dia_seleccionado.tipo == 'dia_semana' and dia_seleccionado.dia_semana is not None:
            dias_semana_list.append(dia_seleccionado.dia_semana)
        elif dia_seleccionado.tipo == 'fecha_especifica' and dia_seleccionado.fecha_especifica:
            fechas_especificas_list.append(dia_seleccionado.fecha_especifica)
    
    # Procesar fechas específicas primero (tienen prioridad)
    if fechas_especificas_list:
        for fecha_obj in fechas_especificas_list:
            # Solo agregar si está dentro del rango y es lunes-viernes
            if fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                fechas_candidatas.add(fecha_obj)
    
    # Procesar días de semana (solo si no hay fechas específicas)
    if dias_semana_list and not fechas_especificas_list:
        for dia_semana_buscado in dias_semana_list:
            # Día de semana: generar todas las ocurrencias dentro del rango
            fecha_actual = fecha_inicio
            
            # Avanzar hasta el primer día de la semana buscado
            dias_hasta_proximo = (dia_semana_buscado - fecha_actual.weekday()) % 7
            if dias_hasta_proximo > 0:
                fecha_actual += timedelta(days=dias_hasta_proximo)
            
            # Agregar todas las ocurrencias del día de semana dentro del rango
            # IMPORTANTE: Solo agregar si es lunes-viernes (weekday 0-4)
            while fecha_actual <= fecha_fin:
                if fecha_actual.weekday() < 5:  # 0-4 = lunes-viernes
                    fechas_candidatas.add(fecha_actual)
                fecha_actual += timedelta(days=7)  # Siguiente semana
    
    # Si no hay días seleccionados, usar rango completo (retrocompatibilidad)
    if not dias_semana_list and not fechas_especificas_list:
        # IMPORTANTE: Solo lunes-viernes (excluir sábados y domingos)
        fecha_actual = fecha_inicio
        while fecha_actual <= fecha_fin:
            if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                fechas_candidatas.add(fecha_actual)
            fecha_actual += timedelta(days=1)

    # Incluir fines de semana como "excluidos" (para transparencia en vista previa / detalle),
    # sin alterar los aplicables (CT Permanente aplica solo lunes-viernes).
    fecha_actual = fecha_inicio
    while fecha_actual <= fecha_fin:
        if fecha_actual.weekday() in (5, 6):  # 5=sábado, 6=domingo
            fechas_candidatas.add(fecha_actual)
        fecha_actual += timedelta(days=1)
    
    # Filtrar fechas y registrar exclusiones
    fechas_aplicables = []
    fechas_excluidas = []
    
    for fecha_dia in sorted(list(fechas_candidatas)):
        razones_exclusion = []

        # Verificar fin de semana (regla estructural de CT Permanente)
        if fecha_dia.weekday() in (5, 6):
            razones_exclusion.append('Fines de semana')
        
        # Verificar festivo
        if _es_festivo(fecha_dia):
            razones_exclusion.append('Festivo')
        
        # Verificar mantenimiento
        if _es_mantenimiento(fecha_dia):
            razones_exclusion.append('Mantenimiento')
        
        # Verificar temporada
        if _es_temporada(fecha_dia):
            razones_exclusion.append('Temporada')
        
        # Verificar día de descanso del solicitante
        if _es_dia_descanso(solicitante, fecha_dia):
            razones_exclusion.append('Descanso Solicitante')
        
        # Verificar día de descanso del receptor
        if _es_dia_descanso(receptor, fecha_dia):
            razones_exclusion.append('Descanso Receptor')

        # Día LIBRE por otra solicitud aprobada (sin Turno) — refleja "Mis Turnos".
        if _dia_libre_por_solicitud(solicitante, fecha_dia):
            razones_exclusion.append('Día libre Solicitante')
        if _dia_libre_por_solicitud(receptor, fecha_dia):
            razones_exclusion.append('Día libre Receptor')

        # Verificar día ya cambiado (doblada / CT sencillo / D FDS): no está en jornada predeterminada
        tipo_previo_sol = _tipo_cambio_previo(solicitante, fecha_dia)
        if tipo_previo_sol:
            razones_exclusion.append(_razon_cambio_previo(tipo_previo_sol, True))
        tipo_previo_rec = _tipo_cambio_previo(receptor, fecha_dia)
        if tipo_previo_rec:
            razones_exclusion.append(_razon_cambio_previo(tipo_previo_rec, False))

        # Si hay razones de exclusión, agregar a excluidas
        if razones_exclusion:
            # Opción 2: una sola razón principal por fecha (sin razones compuestas)
            razon = _razon_principal_ct_permanente(razones_exclusion)
            fechas_excluidas.append({
                'fecha': fecha_dia,
                'razon': razon
            })
        else:
            # Si no hay razones, es una fecha aplicable
            fechas_aplicables.append(fecha_dia)
    
    return fechas_aplicables, fechas_excluidas