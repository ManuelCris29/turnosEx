"""
Helper para calcular fechas aplicables de cambios permanentes.
Reutiliza la lógica de CTPermanenteStrategy para ser usada en otros contextos.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, timedelta
from typing import List, Dict, Tuple
from empleados.models import Empleado
from turnos.models import DiaEspecial, DescansoSemanaManual
from turnos.services.descanso_semana_service import DescansoSemanaService
from solicitudes.models import CambioPermanenteDetalle
from core.utils.date_utils import DateUtils
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------- #
# PRECARGA EN LOTE (rendimiento)
#
# Evaluar un CT permanente es rellenar una MATRIZ empleado×día: para cada candidato y cada
# fecha del rango hay que saber su estado real, si el día ya está comprometido y si ya tiene
# un cambio. Resolver cada celda por separado costaba ~13 consultas y ~17 ms (el grueso, en
# `DescansoPorSolicitudService.en_fecha`, que por dentro arranca la maquinaria BATCH para una
# sola celda). Un rango de 90 días con una decena de candidatos se iba a ~13.000 consultas y
# ~40 s, y escalaba LINEALMENTE con la plantilla.
#
# Con `precargar_ct_permanente(...)` las cuatro fuentes se traen de una vez para todo el
# rango y todos los empleados; dentro del `with`, las funciones de abajo leen de esa tabla en
# memoria en vez de ir a la BD. Fuera del `with` todo sigue funcionando igual (consulta
# directa), así que ningún otro llamador se ve afectado.
#
# La caché SOLO sirve celdas que estén dentro del rango y del conjunto de empleados
# precargados; cualquier otra cosa cae al camino individual. Es una caché de LECTURA de vida
# muy corta (una petición), así que no puede quedarse obsoleta.
# --------------------------------------------------------------------------------------- #

_CTX_CT_PERMANENTE: ContextVar = ContextVar('ctx_ct_permanente', default=None)


class _ContextoCTPermanente:
    """Tabla precargada de estado empleado×día para una evaluación de CT permanente."""

    __slots__ = ('emp_ids', 'ini', 'fin', 'estados', 'descansos', 'cambios_previos',
                 'festivos', 'mantenimiento', 'temporada')

    def __init__(self, empleados, ini: date, fin: date):
        from turnos.services.turno_service import TurnoService
        from solicitudes.services.descanso_solicitud_service import DescansoPorSolicitudService
        from turnos.models import Turno

        empleados = [e for e in (empleados or []) if e is not None]
        self.emp_ids = {getattr(e, 'id', e) for e in empleados}
        self.ini, self.fin = ini, fin

        # Estado real del día ("Mis Turnos") para todos los empleados y todo el rango.
        self.estados = TurnoService.estado_rango_multiple(empleados, ini, fin)

        # Días comprometidos por una solicitud aprobada (sin `excluir_id`: ese caso, poco
        # frecuente y siempre puntual, sigue yendo a la BD).
        self.descansos = DescansoPorSolicitudService.en_rango_multiple(empleados, ini, fin)

        # Turnos que YA llevan un cambio (doblada / CT sencillo / D FDS...).
        self.cambios_previos = {}
        for t in (Turno.objects
                  .filter(explorador_id__in=self.emp_ids, fecha__range=(ini, fin))
                  .exclude(tipo_cambio__isnull=True).exclude(tipo_cambio='')):
            self.cambios_previos.setdefault((t.explorador_id, t.fecha), []).append(t.tipo_cambio)

        # Días especiales del rango: festivo / mantenimiento / temporada, de una sola consulta.
        self.festivos, mantenimiento_raw, self.temporada = set(), set(), set()
        for f, tipo, es_temp in DiaEspecial.objects.filter(
                fecha__range=(ini, fin), activo=True).values_list('fecha', 'tipo', 'es_temporada'):
            if tipo == 'festivo':
                self.festivos.add(f)
            elif tipo == 'mantenimiento':
                mantenimiento_raw.add(f)
            if es_temp:
                self.temporada.add(f)
        # Días de descanso FIJADOS de temporada: cuentan como temporada aunque su fecha no lleve
        # el marcador de semana (son conjuntos distintos, ver `_es_temporada`). Se traen aquí, en
        # una sola consulta para todo el rango, para no pagar una por día.
        self.temporada |= set(DescansoSemanaManual.objects.filter(
            fecha__range=(ini, fin), activo=True, motivo='temporada',
        ).values_list('fecha', flat=True))
        # Misma regla que `DiaEspecial.es_mantenimiento_efectivo`: la temporada manda.
        self.mantenimiento = mantenimiento_raw - self.temporada

    def cubre_fecha(self, fecha: date) -> bool:
        return self.ini <= fecha <= self.fin

    def cubre(self, empleado, fecha: date) -> bool:
        return self.cubre_fecha(fecha) and getattr(empleado, 'id', empleado) in self.emp_ids


@contextmanager
def precargar_ct_permanente(empleados, fecha_inicio: date, fecha_fin: date):
    """
    Precarga en LOTE el estado de `empleados` entre `fecha_inicio` y `fecha_fin`, para que las
    funciones de este módulo resuelvan la matriz empleado×día sin volver a la base de datos.

    Uso::

        with precargar_ct_permanente([solicitante, *candidatos], ini, fin):
            ...  # evaluar_fechas_ct_permanente, _razones_exclusion_ct_permanente, etc.

    Es puramente una optimización: los resultados son idénticos a los del camino individual.
    Si la precarga falla, se sigue sin caché (correcto, solo más lento).

    Si YA hay una precarga activa que cubre lo que se pide (empleados y rango), se reutiliza en
    vez de anidar otra: así `evaluar_fechas_ct_permanente`, que precarga por su cuenta, no repite
    el trabajo cuando lo llama alguien que ya precargó a toda la plantilla.
    """
    actual = _CTX_CT_PERMANENTE.get()
    if actual is not None and actual.cubre_fecha(fecha_inicio) and actual.cubre_fecha(fecha_fin) \
            and all(getattr(e, 'id', e) in actual.emp_ids for e in empleados if e is not None):
        yield actual
        return
    try:
        ctx = _ContextoCTPermanente(empleados, fecha_inicio, fecha_fin)
    except Exception:
        logger.exception('CT permanente: falló la precarga en lote; se sigue sin caché')
        yield None
        return
    token = _CTX_CT_PERMANENTE.set(ctx)
    try:
        yield ctx
    finally:
        _CTX_CT_PERMANENTE.reset(token)

_PRIORIDAD_RAZONES_CT_PERMANENTE = [
    # Más importante primero (opción 2: una sola razón por fecha)
    'Fecha pasada',
    'Mantenimiento',
    'Festivo',
    'Temporada',
    # Día en el que alguno de los dos no tiene MEDIA JORNADA que intercambiar (ya dobla,
    # descansa, o el día ya no está en su jornada predeterminada).
    #
    # Primero TODAS las razones del SOLICITANTE y luego las del RECEPTOR, no agrupadas por tipo.
    # Es su formulario: lo que le impide el cambio a ÉL es lo accionable, y así el motivo de una
    # fecha no cambia al elegir compañero. Con el orden por tipo, un día en que el solicitante
    # descansaba pasaba de 'Descanso Solicitante' (vista previa sin compañero) a 'Doblada
    # Receptor' en cuanto escogía a alguien —ambas ciertas, pero el salto desconcierta—.
    'Doblada Solicitante',
    'Cambio Previo Solicitante',
    'Día libre Solicitante',
    'Descanso Solicitante',
    'Doblada Receptor',
    'Cambio Previo Receptor',
    'Día libre Receptor',
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


def _estado_ct(explorador: Empleado, fecha: date) -> dict:
    """
    Estado REAL del día según "Mis Turnos" (`TurnoService.estado_dia`), o `{}` si no se pudo
    resolver. Punto único de acceso para no repetir el try/except ni recalcular el estado varias
    veces por fecha dentro de la misma evaluación.

    Dentro de `precargar_ct_permanente` lee de la tabla en lote (misma respuesta, sin consulta).
    """
    ctx = _CTX_CT_PERMANENTE.get()
    if ctx is not None and ctx.cubre(explorador, fecha):
        return ctx.estados.get(getattr(explorador, 'id', explorador), {}).get(fecha) or {}
    try:
        from turnos.services.turno_service import TurnoService
        return TurnoService.estado_dia(explorador, fecha) or {}
    except Exception:
        return {}


def _razon_estado_no_apto(estado: dict, quien: str):
    """
    Razón por la que el estado REAL del día impide participar en el intercambio, o None si el
    explorador tiene MEDIA JORNADA (AM o PM) con la que intercambiar.

    Un CT permanente intercambia media jornada por media jornada: si ese día el explorador ya
    está DOBLADA (AM+PM) no hay nada que ceder, y si descansa tampoco. Ojo: la doblada puede ser
    VIRTUAL —la genera la capa de temporada de `estado_dia` y no deja ninguna fila `Turno`—, así
    que `_tipo_cambio_previo` (que mira `Turno.tipo_cambio`) no la ve. Por eso la aptitud del día
    se decide aquí, con el estado completo, y no a partir de los turnos en BD.

    `estado` vacío (no se pudo resolver) NO excluye, para mantener el comportamiento permisivo
    que tenía `_es_dia_descanso` ante un fallo del servicio.
    """
    if not estado:
        return None
    jornada = estado.get('jornada')
    if jornada in ('AM', 'PM'):
        return None
    if jornada == 'DOBLADA':
        return f'Doblada {quien}'
    return f'Descanso {quien}'


def _jornada_efectiva_ct(explorador: Empleado, fecha: date):
    """Jornada REAL única ('AM'/'PM') del explorador ese día, o None (descansa o ya dobla)."""
    jornada = _estado_ct(explorador, fecha).get('jornada')
    return jornada if jornada in ('AM', 'PM') else None


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

    razones = []

    if excluir_pasadas and fecha < timezone.localdate():
        razones.append('Fecha pasada')

    if fecha.weekday() in (5, 6):
        razones.append('Fines de semana')
    if _es_festivo(fecha):
        razones.append('Festivo')
    if _es_mantenimiento(fecha):
        razones.append('Mantenimiento')
    # `_es_temporada` incluye tanto la semana de temporada como los días de descanso fijados
    # dentro de ella (exclusivos del formulario de CAMBIO DESCANSO). Mismo motivo para los dos:
    # al usuario le da igual el matiz, el día no está disponible aquí.
    if _es_temporada(fecha):
        razones.append('Temporada')

    # APTITUD DEL DÍA según el estado REAL ("Mis Turnos"): hace falta MEDIA JORNADA (AM/PM).
    # Se evalúa SIEMPRE, también cuando no hay receptor (vista previa antes de elegir compañero).
    # Antes esto solo miraba `_es_dia_descanso` (que con una doblada da `trabaja=True` y por tanto
    # NO excluía) y la única comprobación de media jornada —`jornadas_intercambiables_ct`, más
    # abajo— estaba condicionada a que hubiera receptor: un día ya DOBLADO se colaba como
    # aplicable en la previsualización sin compañero, y con compañero se excluía pero con el
    # motivo equivocado ('Sin jornada contraria' en vez de 'Doblada').
    razon_sol = _razon_estado_no_apto(_estado_ct(solicitante, fecha), 'Solicitante')
    if razon_sol:
        razones.append(razon_sol)
    if receptor:
        razon_rec = _razon_estado_no_apto(_estado_ct(receptor, fecha), 'Receptor')
        if razon_rec:
            razones.append(razon_rec)

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

    # Sin intercambio posible: ambos tienen media jornada, pero es la MISMA. Llegados aquí ya
    # sabemos que ninguno descansa ni dobla (lo filtra `_razon_estado_no_apto`), así que este
    # motivo significa de verdad "ambos están en la misma franja".
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

    if not candidatas:
        return [], []

    # Precarga en lote de los dos implicados para todo el rango: el barrido de abajo pasa de
    # ~13 consultas por fecha a ninguna. Si ya hay una precarga activa (p. ej. la del cálculo de
    # compatibilidad, que abarca a todos los candidatos), esta se anida sin coste apreciable y la
    # de fuera sigue sirviendo las celdas que cubre.
    with precargar_ct_permanente(
        [solicitante, receptor], min(candidatas), max(candidatas)
    ):
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
    ctx = _CTX_CT_PERMANENTE.get()
    if ctx is not None and ctx.cubre_fecha(fecha):
        return fecha in ctx.festivos
    return DiaEspecial.es_festivo(fecha)


def _es_mantenimiento(fecha: date) -> bool:
    """Verificar si es día de mantenimiento EFECTIVO (temporada manda sobre mantenimiento)."""
    ctx = _CTX_CT_PERMANENTE.get()
    if ctx is not None and ctx.cubre_fecha(fecha):
        return fecha in ctx.mantenimiento
    try:
        return DiaEspecial.es_mantenimiento_efectivo(fecha)
    except Exception:
        return False

def _es_temporada(fecha: date) -> bool:
    """
    ¿`fecha` queda descartada por temporada? Cubre DOS cosas, no una:

      - el marcador de la SEMANA de temporada (`DiaEspecial.es_temporada`), y
      - los DÍAS DE DESCANSO que el supervisor fija dentro de ella
        (`DescansoSemanaManual` con `motivo='temporada'`).

    Son conjuntos distintos: hay días de descanso fijados en fechas SIN el marcador de semana
    (07/08/2026: `_dia_calendario_no_apto(2026-09-15)` devolvía None sobre uno de ellos). Esos
    días son territorio exclusivo del formulario de CAMBIO DESCANSO, así que ni CT PERMANENTE ni
    DOBLADA PERMANENTE pueden usarlos.

    Los dos conjuntos se unen ya en la precarga (`_ContextoCTPermanente.temporada`), para no
    añadir una consulta por día y romper el coste constante que garantiza
    `test_rango_largo_no_cuesta_mas_que_uno_corto`.
    """
    ctx = _CTX_CT_PERMANENTE.get()
    if ctx is not None and ctx.cubre_fecha(fecha):
        return fecha in ctx.temporada
    return (DiaEspecial.es_temporada_en(fecha)
            or DescansoSemanaService.es_dia_descanso_temporada(fecha))


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

    OJO: "no descansa" NO implica "puede intercambiar" — con una DOBLADA `trabaja` es True. La
    aptitud del día para el CT permanente la decide `_razon_estado_no_apto`, no esta función.
    """
    # Por defecto `trabaja=True`: si el estado no se pudo resolver, no inventamos un descanso
    # (mismo comportamiento permisivo que tenía el try/except original).
    return not _estado_ct(explorador, fecha).get('trabaja', True)


def _tipo_cambio_previo(explorador: Empleado, fecha: date):
    """
    Devuelve el tipo de cambio que el explorador ya tiene ese día si su turno NO es su
    jornada predeterminada (doblada, CT sencillo, D FDS...), o None si está en estado
    predeterminado (sin turno, o turno del horario importado con tipo_cambio NULL).

    El CT permanente intercambia las jornadas PREDETERMINADAS; si ese día el explorador ya
    no está en su jornada predeterminada, ese día no puede incluirse en el cambio.
    """
    def _clasificar(tipos_lista):
        if not tipos_lista:
            return None
        tipos = set(tipos_lista)
        # Una doblada deja 2 turnos (día completo): reportarla como doblada.
        if len(tipos_lista) >= 2 or tipos & {'DOBLADA', 'DOBLADA PERM'}:
            return 'DOBLADA PERM' if 'DOBLADA PERM' in tipos else 'DOBLADA'
        return next(iter(tipos))

    ctx = _CTX_CT_PERMANENTE.get()
    if ctx is not None and ctx.cubre(explorador, fecha):
        return _clasificar(
            ctx.cambios_previos.get((getattr(explorador, 'id', explorador), fecha), [])
        )
    try:
        from turnos.models import Turno
        turnos = list(
            Turno.objects.filter(explorador=explorador, fecha=fecha)
            .exclude(tipo_cambio__isnull=True)
            .exclude(tipo_cambio='')
        )
        return _clasificar([t.tipo_cambio for t in turnos])
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
    # Con `excluir_id` NO se usa la caché: la tabla precargada se construye sin exclusiones.
    ctx = _CTX_CT_PERMANENTE.get()
    if excluir_id is None and ctx is not None and ctx.cubre(empleado, fecha):
        return fecha in ctx.descansos.get(getattr(empleado, 'id', empleado), {})
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


def _dia_calendario_no_apto(fecha: date):
    """
    ¿El CALENDARIO por sí solo descarta `fecha` para una doblada permanente? Devuelve
    'mantenimiento' / 'festivo' / 'temporada', o None.

    Una doblada permanente parte de la jornada PREDETERMINADA del día y la duplica; en
    mantenimiento, festivo o temporada el día no está en jornada predeterminada, así que no hay
    nada que doblar. Se comprueba por REGLA, igual que hace `_razones_exclusion_ct_permanente`
    para el CT permanente, y NO se delega en que `estado_dia` lo refleje: la capa de temporada
    solo altera el estado de quien descansa o dobla por temporada, de modo que a un explorador
    que en temporada conserva su jornada el día le llegaba como 'base' AM/PM y se ofrecía como
    doblable. Hasta ahora eso lo tapaba el calendario del formulario (que deshabilita esos días),
    una defensa de una sola capa que no cubre el POST directo ni un rango precargado.

    Prioridad igual que en el resto del módulo: mantenimiento > festivo > temporada. Ojo:
    `_es_mantenimiento` ya es el mantenimiento EFECTIVO (en temporada no cuenta).

    `_es_temporada` cubre tanto el marcador de la SEMANA de temporada como los DOS DÍAS de
    descanso que el supervisor fija dentro de ella — que son territorio exclusivo del formulario
    de CAMBIO DESCANSO y que, en la práctica, aparecen también en fechas sin ese marcador
    (comprobado el 07/08/2026: 2026-09-15 salía apto).
    """
    if _es_mantenimiento(fecha):
        return 'mantenimiento'
    if _es_festivo(fecha):
        return 'festivo'
    if _es_temporada(fecha):
        return 'temporada'
    return None


def bloque_calendario_no_apto(desde: date, limite_dias: int = 400):
    """
    Tramo CONTIGUO de días no aptos que empieza en `desde`, o None si `desde` sí es apto.

    Devuelve ``{'tipo', 'tipos', 'desde', 'hasta', 'siguiente_habil'}``: `tipo` es el motivo del
    primer día, `tipos` todos los que aparecen en el tramo (un bloque puede mezclarlos: la semana
    de receso encadena temporada, festivo y mantenimiento) y `siguiente_habil` el primer día
    lunes-viernes realmente apto tras el tramo — decir que la temporada acaba el 11 no sirve si
    el 12 cae domingo.

    Una SOLA consulta para toda la ventana. La versión anterior recorría el tramo llamando a
    `_dia_calendario_no_apto` día a día FUERA de cualquier precarga (el tramo empieza en
    `fecha_fin + 1`, fuera del rango precargado), y cada día costaba ~3 consultas: el rango que
    termina la víspera de la temporada de fin de año pagaba ~85 consultas extra solo por
    redactar el aviso.
    """
    limite_dias = max(1, limite_dias)
    hasta_ventana = desde + timedelta(days=limite_dias)

    festivos, mant_raw, temporada = set(), set(), set()
    for f, tipo, es_temp in DiaEspecial.objects.filter(
            fecha__range=(desde, hasta_ventana), activo=True).values_list(
                'fecha', 'tipo', 'es_temporada'):
        if tipo == 'festivo':
            festivos.add(f)
        elif tipo == 'mantenimiento':
            mant_raw.add(f)
        if es_temp:
            temporada.add(f)
    # Misma regla que `DiaEspecial.es_mantenimiento_efectivo`: la temporada manda.
    mantenimiento = mant_raw - temporada
    # Días de descanso FIJADOS de temporada: cuentan como 'temporada' igual que en
    # `_dia_calendario_no_apto`, y en una consulta para toda la ventana (esta función existe
    # justamente para no ir día a día).
    temporada |= set(DescansoSemanaManual.objects.filter(
        fecha__range=(desde, hasta_ventana), activo=True, motivo='temporada',
    ).values_list('fecha', flat=True))

    def _tipo(f: date):
        # Mismo orden de prioridad que `_dia_calendario_no_apto`.
        if f in mantenimiento:
            return 'mantenimiento'
        if f in festivos:
            return 'festivo'
        if f in temporada:
            return 'temporada'
        return None

    tipo_inicial = _tipo(desde)
    if not tipo_inicial:
        return None

    fin_bloque, tipos = desde, [tipo_inicial]
    while fin_bloque < hasta_ventana:
        t = _tipo(fin_bloque + timedelta(days=1))
        if not t:
            break
        if t not in tipos:
            tipos.append(t)
        fin_bloque += timedelta(days=1)

    habil = fin_bloque + timedelta(days=1)
    for _ in range(30):
        if habil.weekday() < 5 and not _tipo(habil):
            break
        habil += timedelta(days=1)
    else:
        habil = None

    return {
        'tipo': tipo_inicial,
        'tipos': tipos,
        'desde': desde.strftime('%Y-%m-%d'),
        'hasta': fin_bloque.strftime('%Y-%m-%d'),
        'siguiente_habil': habil.strftime('%Y-%m-%d') if habil else None,
    }


def jornadas_unicas_reales(empleados, fecha: date) -> dict:
    """
    Versión BATCH de `_jornada_unica_real` para MUCHOS empleados en una fecha:
    ``{emp_id: 'AM' | 'PM' | None}``, con un número CONSTANTE de consultas (2).

    Misma semántica que la individual (turnos reales del día y, si no hay, la asignación vigente
    más reciente ≤ fecha), pero el bucle de candidatos de la doblada permanente barre a TODA la
    plantilla: a ~1,8 consultas por empleado, 400 exploradores eran ~730 consultas y >1 s solo
    para poblar el desplegable de compañeros.
    """
    from turnos.models import Turno, AsignarJornadaExplorador

    ids = [getattr(e, 'id', e) for e in (empleados or [])]
    if not ids:
        return {}

    # Turnos reales del día (1 consulta) → jornadas por empleado.
    turnos_por_emp = {}
    for t in (Turno.objects.filter(explorador_id__in=ids, fecha=fecha)
              .select_related('jornada')):
        if t.jornada:
            turnos_por_emp.setdefault(t.explorador_id, set()).add(t.jornada.nombre.upper())

    # Asignación vigente en `fecha` (1 consulta). Se ordena ascendente y se sobrescribe, de modo
    # que al terminar cada empleado queda con la ÚLTIMA fecha_inicio ≤ fecha: igual que el
    # `order_by('-fecha_inicio').first()` de la versión individual.
    base_por_emp = {}
    for a in (AsignarJornadaExplorador.objects
              .filter(explorador_id__in=ids, fecha_inicio__lte=fecha)
              .select_related('jornada').order_by('fecha_inicio')):
        base_por_emp[a.explorador_id] = a.jornada.nombre.upper() if a.jornada else None

    salida = {}
    for i in ids:
        js = turnos_por_emp.get(i)
        if js:
            # AM+PM = doblada real: no hay jornada única sobre la que armar la doblada permanente.
            j = None if ('AM' in js and 'PM' in js) else ('AM' if 'AM' in js else ('PM' if 'PM' in js else None))
        else:
            j = base_por_emp.get(i)
        salida[i] = j if j in ('AM', 'PM') else None
    return salida


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

    Los días que el CALENDARIO descarta (mantenimiento / festivo / temporada) se filtran antes de
    mirar el estado: ver `_dia_calendario_no_apto`. Es el único punto por el que pasan la vista de
    días disponibles, la previsualización, la validación/aplicación y la reprogramación, así que
    el filtro vale para todas ellas.
    """
    if _dia_calendario_no_apto(fecha):
        return None
    st = _estado_ct(explorador, fecha)
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


def _motivo_no_doblada_perm(explorador: Empleado, fecha: date):
    """
    Razón corta (para el preview) por la que el explorador NO puede doblar ese día, o None si SÍ
    puede (tiene jornada única AM/PM). Usa `estado_dia` para dar el motivo REAL (coincide con
    "Mis Turnos"): ya doblada, festivo, temporada, mantenimiento, fin de semana o descanso.
    """
    calendario = _dia_calendario_no_apto(fecha)
    if calendario:
        # Mismo veredicto que `_jornada_doblada_perm`, con el motivo del calendario. Va primero
        # porque en temporada el estado del día puede seguir siendo una jornada normal.
        return {
            'mantenimiento': 'Mantenimiento',
            'festivo': 'Festivo',
            'temporada': 'Descanso de temporada',
        }[calendario]
    st = _estado_ct(explorador, fecha)
    if not st:
        return 'No se pudo determinar tu turno ese día'
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


def _motivo_no_cubre_companero(companero: Empleado, fecha: date, jornada_solicitante: str):
    """
    Razón corta, en TERCERA persona, por la que `companero` NO puede cubrir/doblar con el
    solicitante en `fecha`; None si sí puede (jornada única y contraria).

    Existe porque "no aparece la casilla" tiene causas muy distintas y el formulario las
    colapsaba en una sola ("necesitas un compañero de la jornada contraria"), que es FALSA
    cuando el compañero sí es contrario pero ya está doblado o descansa por otro acuerdo. Se
    devuelve además `tipo` para que el front agrupe el consejo: solo 'misma_jornada' se
    arregla eligiendo otro compañero de la jornada opuesta.

    Returns:
        None, o {'tipo': 'misma_jornada'|'no_disponible', 'razon': str}
    """
    if companero is None:
        return {'tipo': 'no_disponible', 'razon': 'compañero no encontrado'}
    calendario = _dia_calendario_no_apto(fecha)
    if calendario:
        # El día no es doblable para NADIE: no es cosa del compañero, así que el motivo se
        # redacta sin culparlo (y nunca como 'misma_jornada', que sugeriría cambiar de persona).
        return {'tipo': 'no_disponible', 'razon': {
            'mantenimiento': 'ese día es de mantenimiento',
            'festivo': 'ese día es festivo',
            'temporada': 'ese día es de temporada',
        }[calendario]}
    jr = _jornada_doblada_perm(companero, fecha)
    if jr and jr != jornada_solicitante:
        return None
    nombre = getattr(companero, 'nombre', '') or 'El compañero'
    if jr:
        # Contrario a lo que sugería el mensaje genérico, aquí sí hay jornada: el choque es
        # que ambos están en la MISMA (nadie puede cubrir a nadie).
        return {'tipo': 'misma_jornada', 'razon': f'{nombre} también está {jr}'}
    st = _estado_ct(companero, fecha)
    if not st:
        return {'tipo': 'no_disponible', 'razon': f'no se pudo determinar el turno de {nombre}'}
    if st.get('jornada') == 'DOBLADA':
        return {'tipo': 'no_disponible', 'razon': f'{nombre} ya está doblada ese día (AM+PM)'}
    fuente = st.get('fuente')
    motivo = st.get('motivo')
    etiquetas = {
        'festivo': f'{nombre} no trabaja: festivo',
        'temporada': f'{nombre} está en descanso de temporada',
        'mantenimiento': f'{nombre} está en mantenimiento',
        'alternancia': f'{nombre} descansa ese fin de semana',
        'manual': f'{nombre} descansa ese fin de semana',
    }
    if fuente in etiquetas:
        return {'tipo': 'no_disponible', 'razon': etiquetas[fuente]}
    if fuente == 'solicitud':
        otro = (st.get('companero') or {}).get('nombre')
        detalle = f' ({motivo} con {otro})' if (motivo and otro) else (f' ({motivo})' if motivo else '')
        return {'tipo': 'no_disponible', 'razon': f'{nombre} ya cedió ese día en otro acuerdo{detalle}'}
    return {'tipo': 'no_disponible', 'razon': motivo or f'{nombre} no tiene turno ese día'}


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
