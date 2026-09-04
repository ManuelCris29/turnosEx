"""
Lo que pide el formulario de DOBLADA PERMANENTE multi-compañero, ya normalizado.

QUÉ HACE ESTE MÓDULO
--------------------
Lee el POST —que llega como listas paralelas— y lo convierte en un `PlanMultiCompanero`:
qué días cede a cada compañero y cuáles le devuelve. Y comprueba lo que se puede
comprobar SIN tocar la base de datos: que una fecha no esté asignada a dos personas, que
no sea a la vez día que cedes y día que devuelves, y que las cuentas cuadren por
compañero.

POR QUÉ SE SACÓ DE `_procesar_doblada_permanente_multi`
--------------------------------------------------------
Esa función eran 236 líneas con 60 ramas, uno de los cuatro puntos calientes que
señalaba la auditoría: el sitio donde «cada corrección futura tendrá que entrar a
ciegas». Y es el único de los tres que CREA datos —transacción, todo o nada y correos—,
así que entrar a ciegas ahí sale caro.

Dentro había dos oficios mezclados. Uno es entender el formulario y decidir si lo que
pide tiene sentido: aritmética sobre listas, sin base de datos, sin usuario, sin
transacción. El otro es la orquestación de verdad —cierre semanal, restricciones
médicas, sanciones, validar con la Factory y crear en bloque—, que necesita todo eso.

Aquí vive el primero. Se puede leer y probar sin montar empleados ni turnos.

EL ORDEN IMPORTA Y SE CONSERVA
------------------------------
`construir_plan` NO comprueba el balance, y no es un olvido: el balance se comprueba
después del cierre semanal, igual que antes de la extracción. Si se adelantara, un
formulario con las dos cosas mal cambiaría el mensaje que recibe el usuario. Por eso
`error_de_balance` es una función aparte, que el orquestador llama en su sitio.

LOS DOS FLUJOS
--------------
`usa_fechas=True` es el flujo actual: fechas concretas por compañero, que permite
balancear cuando los días de la semana tienen distinto número de ocurrencias en el
rango. `usa_fechas=False` es el flujo ANTIGUO, por día de la semana; sigue vivo y sigue
creando solicitudes, así que se conserva tal cual.
"""
from dataclasses import dataclass, field
from datetime import datetime

from core.utils.date_utils import DateUtils

from .resultado import ResultadoSolicitud


def _formatear(iso: str) -> str:
    """`2026-09-14` → `14/09/2026`. Si no se puede, se devuelve tal cual: el mensaje es
    para que el usuario reconozca SU fecha, y un ISO se reconoce mejor que un error."""
    try:
        return datetime.strptime(iso, '%Y-%m-%d').strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return iso


@dataclass(frozen=True)
class PlanMultiCompanero:
    """Qué días se ceden y se devuelven, agrupados por compañero.

    Las claves son ids de compañero **en texto**, tal y como llegan del formulario; se
    convierten a `Empleado` más tarde, al validar. Los valores son conjuntos: el mismo
    día repetido en el POST cuenta una vez.
    """

    usa_fechas: bool
    #: comp_id -> {fecha ISO}
    cesion_fechas_por_comp: dict = field(default_factory=dict)
    devol_fechas_por_comp: dict = field(default_factory=dict)
    #: comp_id -> {día de la semana como texto, '0'=lunes}
    cesion_por_comp: dict = field(default_factory=dict)
    devol_por_comp: dict = field(default_factory=dict)
    #: Todas las fechas ISO del POST, para comprobar la ventana de cierre.
    fechas_iso: list = field(default_factory=list)

    @property
    def base_cesion(self) -> dict:
        """Lo que se cuenta al comprobar el balance: fechas en el flujo nuevo, días en el
        antiguo."""
        return self.cesion_fechas_por_comp if self.usa_fechas else self.cesion_por_comp

    @property
    def base_devolucion(self) -> dict:
        return self.devol_fechas_por_comp if self.usa_fechas else self.devol_por_comp


def _agrupar(fechas, companeros) -> dict:
    """Listas paralelas del formulario → {compañero: {valor}}. Descarta los pares
    incompletos, que es lo que llega cuando el navegador manda un campo vacío."""
    por_comp: dict = {}
    for valor, comp in zip(fechas, companeros):
        if comp and valor:
            por_comp.setdefault(comp, set()).add(valor)
    return por_comp


def _fecha_repetida(por_comp: dict):
    """La primera fecha asignada a más de un compañero, o None."""
    vistas = set()
    for _comp, fechas in por_comp.items():
        for f in fechas:
            if f in vistas:
                return f
            vistas.add(f)
    return None


def construir_plan(post):
    """
    POST → `(plan, error)`. Exactamente uno de los dos es None.

    Comprueba aquí lo que es un choque ENTRE compañeros, que ninguna solicitud individual
    puede ver: cada una se valida por separado, así que si no se detecta en este punto no
    se detecta en ninguno.
    """
    ces_fechas = post.getlist('cesion_fecha')
    dev_fechas = post.getlist('devolucion_fecha')
    usa_fechas = bool(ces_fechas)

    cesion_fechas_por_comp = _agrupar(ces_fechas, post.getlist('cesion_fecha_companero'))
    devol_fechas_por_comp = _agrupar(dev_fechas, post.getlist('devolucion_fecha_companero'))

    # UNA fecha = UN solo compañero. Dos personas no pueden cubrir la misma jornada el
    # mismo día, ni se puede pagar la misma jornada dos veces ese día.
    dup_cesion = _fecha_repetida(cesion_fechas_por_comp)
    dup_devol = _fecha_repetida(devol_fechas_por_comp)
    if dup_cesion or dup_devol:
        fecha = dup_cesion or dup_devol
        accion = 'cubrirla' if dup_cesion else 'pagarla'
        return None, ResultadoSolicitud.error(
            f'La fecha {_formatear(fecha)} está asignada a dos compañeros; una fecha solo '
            f'puede {accion} un compañero (no puedes cubrir ni pagar la misma jornada el '
            f'mismo día con dos personas).',
            status=400, code='validation_error')

    # UNA fecha no puede ser CESIÓN de uno y DEVOLUCIÓN de otro: ese día no puedes
    # descansar (te cubre uno) y doblarte (le pagas al otro) a la vez. Lo bloqueaba solo
    # el formulario; si se colaba, al aplicar la segunda el día se descartaba en silencio
    # y la devolución pedida desaparecía sin avisar.
    todas_cesion = {f for fs in cesion_fechas_por_comp.values() for f in fs}
    todas_devol = {f for fs in devol_fechas_por_comp.values() for f in fs}
    cruce = sorted(todas_cesion & todas_devol)
    if cruce:
        return None, ResultadoSolicitud.error(
            f'El {_formatear(cruce[0])} lo tienes como día que cedes y como día que '
            f'devuelves a la vez. Ese día no puedes descansar y doblarte al mismo tiempo, '
            f'aunque sean compañeros distintos.',
            status=400, code='validation_error')

    plan = PlanMultiCompanero(
        usa_fechas=usa_fechas,
        cesion_fechas_por_comp=cesion_fechas_por_comp,
        devol_fechas_por_comp=devol_fechas_por_comp,
        cesion_por_comp=_dias_por_companero(post, cesion_fechas_por_comp, usa_fechas,
                                            'cesion_dia', 'cesion_companero'),
        devol_por_comp=_dias_por_companero(post, devol_fechas_por_comp, usa_fechas,
                                           'devolucion_dia', 'devolucion_companero'),
        fechas_iso=list(ces_fechas) + list(dev_fechas),
    )
    return plan, None


def _dias_por_companero(post, fechas_por_comp: dict, usa_fechas: bool,
                        campo_dia: str, campo_comp: str) -> dict:
    """Días de la semana por compañero: derivados de las fechas en el flujo nuevo, leídos
    del POST en el antiguo."""
    if not usa_fechas:
        return _agrupar(post.getlist(campo_dia), post.getlist(campo_comp))

    por_comp = {}
    for comp, fechas in fechas_por_comp.items():
        dias = {_dia_de_la_semana(f) for f in fechas}
        por_comp[comp] = {d for d in dias if d}
    return por_comp


def _dia_de_la_semana(iso: str) -> str:
    try:
        return str(DateUtils.parse_date(iso).weekday())
    except (ValueError, TypeError):
        return ''


def error_de_balance(plan: PlanMultiCompanero):
    """
    Las cuentas del acuerdo, o None si cuadran.

    Se llama DESPUÉS del cierre semanal, no dentro de `construir_plan`: adelantarlo
    cambiaría qué error ve un usuario que tiene las dos cosas mal.
    """
    base_ces, base_dev = plan.base_cesion, plan.base_devolucion

    if not base_ces:
        return ResultadoSolicitud.error('Agrega al menos un día de cesión con su compañero',
                                        status=400, code='missing_fields')

    for comp in base_dev:
        if comp not in base_ces:
            return ResultadoSolicitud.error(
                'Solo puedes devolverle a un compañero que te cubra.',
                status=400, code='validation_error')

    # Por compañero: tantos días devueltos como cubiertos. Es lo que hace que el acuerdo
    # sea un intercambio y no un favor a medias.
    unidad = 'fechas' if plan.usa_fechas else 'días'
    for comp, cedidos in base_ces.items():
        if len(base_dev.get(comp, set())) != len(cedidos):
            return ResultadoSolicitud.error(
                f'A cada compañero debes devolverle la misma cantidad de {unidad} que te cubre.',
                status=400, code='validation_error')
    return None
