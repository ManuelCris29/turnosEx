"""
Helper para calcular fechas aplicables de cambios permanentes.
Reutiliza la lógica de CTPermanenteStrategy para ser usada en otros contextos.
"""
from datetime import date, timedelta
from typing import List, Dict, Tuple
from empleados.models import Empleado
from turnos.models import DiaEspecial
from solicitudes.models import CambioPermanenteDetalle
from core.utils.date_utils import DateUtils
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

_PRIORIDAD_RAZONES_CT_PERMANENTE = [
    # Más importante primero (opción 2: una sola razón por fecha)
    'Fecha pasada',
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
    # Ambos trabajan, pero en la MISMA jornada: no hay nada que intercambiar. Va después de
    # los descansos porque, cuando alguien descansa, ese motivo explica mejor el día.
    'Sin jornada contraria',
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


def dias_seleccionados_desde_detalle(detalle: CambioPermanenteDetalle) -> Dict[str, list]:
    """Reconstruye el dict `dias_seleccionados` a partir de los `CambioPermanenteDia`."""
    dias_semana, fechas_especificas = [], []
    for dia in detalle.dias.all():
        if dia.tipo == 'dia_semana' and dia.dia_semana is not None:
            dias_semana.append(dia.dia_semana)
        elif dia.tipo == 'fecha_especifica' and dia.fecha_especifica:
            fechas_especificas.append(dia.fecha_especifica)
    return {'dias_semana': dias_semana, 'fechas_especificas': fechas_especificas}


def generar_fechas_candidatas_ct_permanente(
    fecha_inicio: date,
    fecha_fin: date,
    dias_seleccionados: Dict[str, list] = None,
) -> List[date]:
    """
    IMPLEMENTACIÓN ÚNICA de la expansión de un CT permanente a fechas concretas.

    Antes esto estaba copiado en cinco sitios (strategy, este helper ×2, validador y vista de
    previsualización) y las copias ya habían divergido. Ahora todos llaman aquí.

    Reglas:
      - `fechas_especificas` tiene PRIORIDAD sobre `dias_semana` (compatibilidad parcial).
      - Solo lunes-viernes (weekday 0-4); las fechas fuera del rango se descartan.
      - Sin días seleccionados, se expande el rango completo (retrocompatibilidad).
    """
    dias_seleccionados = dias_seleccionados or {}
    fechas_especificas = dias_seleccionados.get('fechas_especificas') or []
    dias_semana = dias_seleccionados.get('dias_semana') or []

    fechas: set = set()

    if fechas_especificas:
        for valor in fechas_especificas:
            try:
                fecha_obj = DateUtils.parse_date(valor) if isinstance(valor, str) else valor
            except (ValueError, TypeError):
                continue
            if fecha_obj and fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                fechas.add(fecha_obj)
        return sorted(fechas)

    if dias_semana:
        try:
            objetivo = {int(d) for d in dias_semana}
        except (ValueError, TypeError):
            objetivo = set()
        fecha_actual = fecha_inicio
        while fecha_actual <= fecha_fin:
            if fecha_actual.weekday() < 5 and fecha_actual.weekday() in objetivo:
                fechas.add(fecha_actual)
            fecha_actual += timedelta(days=1)
        return sorted(fechas)

    fecha_actual = fecha_inicio
    while fecha_actual <= fecha_fin:
        if fecha_actual.weekday() < 5:
            fechas.add(fecha_actual)
        fecha_actual += timedelta(days=1)
    return sorted(fechas)


def jornadas_intercambiables_ct(solicitante: Empleado, receptor: Empleado, fecha: date):
    """
    ¿Ese día solicitante y receptor pueden INTERCAMBIAR jornada? Devuelve `(js, jr)` con las
    jornadas REALES ('AM'/'PM') si ambos trabajan una jornada única y son CONTRARIAS; si no, None.

    Es el corazón del caso de uso: un CT permanente es un intercambio. Si ese día ambos están
    en la misma jornada no hay nada que intercambiar y aplicarlo dejaría a los dos en la jornada
    contraria (la franja original se queda sin cobertura).

    Usa `TurnoService.estado_dia` (fuente única de "Mis Turnos"), igual que el resto del módulo.
    """
    js = _jornada_efectiva_ct(solicitante, fecha)
    jr = _jornada_efectiva_ct(receptor, fecha)
    if js and jr and js != jr:
        return js, jr
    return None


def _jornada_efectiva_ct(explorador: Empleado, fecha: date):
    """Jornada REAL única ('AM'/'PM') del explorador ese día, o None (descansa o ya dobla)."""
    try:
        from turnos.services.turno_service import TurnoService
        jornada = TurnoService.estado_dia(explorador, fecha).get('jornada')
        return jornada if jornada in ('AM', 'PM') else None
    except Exception:
        return None


def _razones_exclusion_ct_permanente(
    fecha: date,
    solicitante: Empleado,
    receptor: Empleado = None,
    excluir_pasadas: bool = False,
) -> List[str]:
    """
    Todas las razones por las que `fecha` NO puede incluirse en el CT permanente.
    Lista vacía = fecha aplicable. `receptor` es opcional (previsualización sin compañero).

    `excluir_pasadas` descarta los días ya transcurridos: lo usan la validación y la aplicación
    (no tiene sentido cambiarle el turno a alguien en un día que ya pasó), pero NO la consulta
    del detalle de una solicitud histórica, que debe seguir mostrando lo que se aplicó.
    """
    from datetime import date as _date

    razones = []

    if excluir_pasadas and fecha < timezone.localdate():
        razones.append('Fecha pasada')

    if fecha.weekday() in (5, 6):
        razones.append('Fines de semana')
    if _es_festivo(fecha):
        razones.append('Festivo')
    if _es_mantenimiento(fecha):
        razones.append('Mantenimiento')
    if _es_temporada(fecha):
        razones.append('Temporada')

    if _es_dia_descanso(solicitante, fecha):
        razones.append('Descanso Solicitante')
    if receptor and _es_dia_descanso(receptor, fecha):
        razones.append('Descanso Receptor')

    # Día LIBRE por otra solicitud aprobada (sin Turno: doblada cedida, cambio de descanso…)
    if _dia_libre_por_solicitud(solicitante, fecha):
        razones.append('Día libre Solicitante')
    if receptor and _dia_libre_por_solicitud(receptor, fecha):
        razones.append('Día libre Receptor')

    # Día ya cambiado (doblada / CT sencillo / D FDS): no está en jornada predeterminada
    tipo_previo_sol = _tipo_cambio_previo(solicitante, fecha)
    if tipo_previo_sol:
        razones.append(_razon_cambio_previo(tipo_previo_sol, True))
    if receptor:
        tipo_previo_rec = _tipo_cambio_previo(receptor, fecha)
        if tipo_previo_rec:
            razones.append(_razon_cambio_previo(tipo_previo_rec, False))

    # Sin intercambio posible: ambos trabajan la MISMA jornada ese día.
    if receptor and not razones and not jornadas_intercambiables_ct(solicitante, receptor, fecha):
        razones.append('Sin jornada contraria')

    return razones


def evaluar_fechas_ct_permanente(
    fecha_inicio: date,
    fecha_fin: date,
    solicitante: Empleado,
    receptor: Empleado = None,
    dias_seleccionados: Dict[str, list] = None,
    incluir_fines_semana: bool = False,
    excluir_pasadas: bool = False,
) -> Tuple[List[date], List[Dict[str, any]]]:
    """
    EVALUACIÓN ÚNICA de un CT permanente: devuelve `(aplicables, excluidas)`.

    `excluidas` es una lista de `{'fecha': date, 'razon': str}` con UNA sola razón por fecha
    (la de mayor prioridad). `incluir_fines_semana` añade sábados y domingos al conjunto
    evaluado para poder reportarlos como excluidos (transparencia en la vista previa); nunca
    cambia el conjunto de aplicables, que es siempre lunes-viernes.

    La usan la validación, la previsualización y la aplicación, de modo que las tres responden
    exactamente lo mismo.
    """
    candidatas = set(generar_fechas_candidatas_ct_permanente(fecha_inicio, fecha_fin, dias_seleccionados))

    if incluir_fines_semana:
        fecha_actual = fecha_inicio
        while fecha_actual <= fecha_fin:
            if fecha_actual.weekday() in (5, 6):
                candidatas.add(fecha_actual)
            fecha_actual += timedelta(days=1)

    aplicables, excluidas = [], []
    for fecha_dia in sorted(candidatas):
        razones = _razones_exclusion_ct_permanente(fecha_dia, solicitante, receptor, excluir_pasadas)
        if razones:
            excluidas.append({'fecha': fecha_dia, 'razon': _razon_principal_ct_permanente(razones)})
        else:
            aplicables.append(fecha_dia)
    return aplicables, excluidas


def _rango_detalle(detalle: CambioPermanenteDetalle) -> Tuple[date, date]:
    """Rango (inicio, fin) del detalle; si no hay fecha_fin, hasta fin de año."""
    fecha_fin = detalle.fecha_fin or date(detalle.fecha_inicio.year, 12, 31)
    return detalle.fecha_inicio, fecha_fin


def calcular_fechas_aplicables_ct_permanente(
    detalle: CambioPermanenteDetalle,
    solicitante: Empleado,
    receptor: Empleado
) -> List[date]:
    """
    Fechas donde se aplicará el cambio permanente (excluye fines de semana, festivos,
    mantenimiento, temporada, descansos, días ya cambiados y días sin jornada contraria).

    Envoltorio sobre `evaluar_fechas_ct_permanente`.
    """
    fecha_inicio, fecha_fin = _rango_detalle(detalle)
    aplicables, _ = evaluar_fechas_ct_permanente(
        fecha_inicio, fecha_fin, solicitante, receptor,
        dias_seleccionados_desde_detalle(detalle),
    )
    return aplicables


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
    Fechas aplicables y excluidas de un cambio permanente (para el detalle y la vista previa).

    Envoltorio sobre `evaluar_fechas_ct_permanente`; incluye los fines de semana del rango
    entre las excluidas para que el usuario vea por qué no entran.

    Returns:
        (fechas_aplicables, [{'fecha': date, 'razon': str}, ...])
    """
    fecha_inicio, fecha_fin = _rango_detalle(detalle)
    return evaluar_fechas_ct_permanente(
        fecha_inicio, fecha_fin, solicitante, receptor,
        dias_seleccionados_desde_detalle(detalle),
        incluir_fines_semana=True,
    )
