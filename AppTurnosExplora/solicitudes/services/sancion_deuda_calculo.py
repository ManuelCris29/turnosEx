"""
CAPA 1 — Cálculo determinista de la sanción por deuda de horas.

Funciones puras: no tocan la base de datos, no leen el reloj y no escriben nada. Se les
dan los periodos mensuales que un explorador dejó incumplidos y responden qué sanción
corresponde a cada uno.

Por qué el periodo mensual, y no la doblada
-------------------------------------------
Antes la unidad sancionable era UNA doblada, y la escalada 15 → 30 → 45 se derivaba de una
cadena de ventanas consecutivas sobre esa misma deuda: si la primera expiraba sin pago,
empezaba la segunda, más larga.

Ese modelo dejó de ser posible cuando cumplir la sanción pasó a CONSUMIR la deuda que la
originó (la sanción es el pago). Una deuda consumida no puede generar una segunda ventana,
así que la cadena tenía que colgar de otra cosa.

Cuelga del PERIODO MENSUAL. La deuda de un mes vence al terminar ese mes; cada mes que se
cierra con saldo pendiente es un incumplimiento independiente, y la reincidencia cuenta
cuántos van::

    agosto impagado      -> nivel 1, 15 días
    + septiembre         -> nivel 2, 30 días
    + octubre            -> nivel 3, 45 días

Esto unifica además las dos fuentes de deuda —dobladas y permisos especiales—, que antes
se trataban por separado y solo la primera llegaba a sancionar.

La ventana de reincidencia
--------------------------
El nivel NO es acumulativo para siempre. Cuando una sanción termina empieza una ventana
configurable (por defecto 30 días): si dentro de ella cae otra sanción, es reincidencia y
sube un nivel; si la ventana se agota sin sanciones nuevas, el contador vuelve a cero y la
siguiente vuelve a ser de 15 días.

Sin esa caducidad, un descuido aislado de hace dos años seguía encareciendo la sanción de
hoy, y el castigo por un tropiezo puntual acababa siendo de meses. El antecedente
disciplinario tiene que poder prescribir.

La ventana se mide desde la finalización EFECTIVA de la sanción anterior (`fecha_fin`, o
`levantada_en - 1` si el supervisor la levantó antes), no desde su inicio: lo que abre el
periodo de prueba es haber terminado de cumplirla.

Quien evita la aplicación sigue sin salir ganando, pero por otra vía: el servicio
materializa de golpe TODAS las sanciones pendientes de la cadena, así que aparecer tres
meses después no borra los tramos anteriores — se graban encadenados, con sus niveles.

Encadenado, no solapado
-----------------------
Una sanción de 45 días dura más que un mes, así que dos periodos consecutivos incumplidos
producirían castigos superpuestos —y un mismo día perteneciendo a dos sanciones hace
ambiguo cuándo termina el bloqueo—. Cada sanción empieza, como muy pronto, el día
siguiente al fin de la anterior::

    inicio_k = max(primer día vencido de P_k, fin planeado de la anterior + 1 día)

Se encadena sobre el fin PLANEADO y no sobre el efectivo: si se usara el efectivo, levantar
una sanción a mano adelantaría todas las siguientes, que ya estaban comunicadas.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

# Primera sanción: 15 días. Cada reincidencia suma otros 15 (30, 45, 60…). No hay tope:
# cuatro meses seguidos sin pagar encadenan 15+30+45+60 días, que es el comportamiento
# querido —la escalada pierde su sentido si se aplana justo cuando más se incumple—.
DURACION_BASE_DIAS = 15

_MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
          'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


@dataclass(frozen=True, order=True)
class Periodo:
    """
    Un mes concreto: la unidad en que vence la deuda y en que se cuenta la reincidencia.

    `order=True` sobre (anio, mes) da el orden cronológico gratis, que es lo que usa
    `cadena_sanciones` para saber cuál es la primera reincidencia y cuál la tercera.
    """

    anio: int
    mes: int

    @classmethod
    def de_fecha(cls, fecha: date) -> 'Periodo':
        return cls(fecha.year, fecha.month)

    def fin_de_plazo(self) -> date:
        """Último día del mes: hasta cuándo hay para pagar sin consecuencias."""
        if self.mes == 12:
            return date(self.anio, 12, 31)
        return date(self.anio, self.mes + 1, 1) - timedelta(days=1)

    def primer_dia_vencida(self) -> date:
        """Primer día en que la deuda de este mes ya está vencida."""
        return self.fin_de_plazo() + timedelta(days=1)

    def nombre(self) -> str:
        """'agosto 2026', para redactar avisos y motivos."""
        return f'{_MESES[self.mes - 1]} {self.anio}'

    def __str__(self) -> str:
        return f'{self.anio}-{self.mes:02d}'


@dataclass(frozen=True)
class SancionPeriodo:
    """La sanción que corresponde a un periodo incumplido, ya resuelta."""

    periodo: Periodo
    inicio: date
    fin: date
    nivel: int              # 1 = primera sanción, 2 = reincidencia #1, 3 = reincidencia #2…
    duracion_dias: int

    @property
    def reincidencia(self) -> int:
        """0 en la primera sanción; 1, 2, 3… en las siguientes. Es lo que se muestra."""
        return self.nivel - 1

    @property
    def duracion_siguiente(self) -> int:
        """Cuántos días duraría la próxima si se incumple otro mes. Va en el aviso."""
        return self.duracion_dias + DURACION_BASE_DIAS


@dataclass(frozen=True)
class Antecedente:
    """
    La última sanción que ya existe, para saber si lo que viene es reincidencia.

    Solo hacen falta dos datos: cuándo dejó de tener efecto y en qué nivel estaba. Se pasa
    como valor y no como objeto de base de datos para que el cálculo siga siendo puro.
    """

    fin: date       # último día con efecto (fecha_fin, o levantada_en - 1 si se levantó)
    nivel: int


def nivel_siguiente(antecedente: Antecedente | None, inicio: date,
                    ventana_dias: int) -> int:
    """
    Qué nivel corresponde a una sanción que empieza en `inicio`.

    Es 1 —primera sanción, 15 días— si no hay antecedente o si la ventana ya se agotó. Si
    la nueva cae dentro de la ventana, sube un escalón sobre el antecedente.

    El día en que vence la ventana todavía cuenta como reincidencia: una ventana de 30 días
    abarca los 30 días siguientes al fin de la anterior, no 29.
    """
    if antecedente is None:
        return 1
    if inicio <= antecedente.fin:
        # Solapada con la anterior (no debería ocurrir: las sanciones se encadenan), pero
        # si ocurre es claramente consecutiva, no un caso de prescripción.
        return antecedente.nivel + 1
    if (inicio - antecedente.fin).days <= ventana_dias:
        return antecedente.nivel + 1
    return 1


def cadena_sanciones(periodos_incumplidos: Iterable[Periodo],
                     ventana_dias: int = 45,
                     antecedente: Antecedente | None = None) -> list[SancionPeriodo]:
    """
    Qué sanción corresponde a cada periodo incumplido, en orden cronológico.

    `periodos_incumplidos` son los meses ya cerrados que quedaron sin saldar; se ordenan y
    deduplican aquí para que quien llama no tenga que garantizarlo (dos fuentes de deuda
    pueden aportar el mismo mes).

    `antecedente` es la última sanción que YA existe para esa persona, si la hay: de ella
    depende si el primer tramo de esta cadena arranca en nivel 1 o continúa la escalada.

    OJO con el tamaño de la ventana, porque entre el fin de un tramo y el vencimiento del
    mes siguiente hay días muertos: la sanción por enero acaba el 16/02, pero la deuda de
    febrero no vence hasta el 01/03. Meses consecutivos necesitan al menos 13 días de
    ventana; saltarse un mes, hasta 44. Por debajo de eso la escalada deja de encadenarse y
    todo sale de 15 días. El valor por defecto (45) cubre ambos casos.
    """
    periodos = sorted(set(periodos_incumplidos))
    sanciones: list[SancionPeriodo] = []
    previa = antecedente

    for periodo in periodos:
        inicio = periodo.primer_dia_vencida()
        if previa is not None and inicio <= previa.fin:
            inicio = previa.fin + timedelta(days=1)
        nivel = nivel_siguiente(previa, inicio, ventana_dias)
        duracion = DURACION_BASE_DIAS * nivel
        fin = inicio + timedelta(days=duracion)
        sanciones.append(SancionPeriodo(
            periodo=periodo, inicio=inicio, fin=fin,
            nivel=nivel, duracion_dias=duracion,
        ))
        previa = Antecedente(fin=fin, nivel=nivel)

    return sanciones


def sancion_de(periodos_incumplidos: Iterable[Periodo], periodo: Periodo,
               ventana_dias: int = 45,
               antecedente: Antecedente | None = None) -> SancionPeriodo | None:
    """La sanción de UN periodo dentro de la cadena, o None si ese mes no está incumplido."""
    for sancion in cadena_sanciones(periodos_incumplidos, ventana_dias, antecedente):
        if sancion.periodo == periodo:
            return sancion
    return None


# ---------------------------------------------------------------- compatibilidad
# Envoltorios sobre `Periodo` para el código que razona con fechas sueltas (la tabla de
# morosos y sus plantillas piden "hasta cuándo se puede pagar" de una fecha, no de un mes).
# La fórmula vive en un solo sitio: si se duplicara, la pantalla podría anunciar un plazo
# distinto del que de verdad dispara la sanción.

def fin_de_plazo(fecha: date) -> date:
    """Último día del mes de `fecha`: hasta cuándo hay para pagar sin sanción."""
    return Periodo.de_fecha(fecha).fin_de_plazo()


def primer_dia_vencida(fecha: date) -> date:
    """Primer día en que la deuda de `fecha` ya está vencida."""
    return Periodo.de_fecha(fecha).primer_dia_vencida()


def nombre_mes(fecha: date) -> str:
    """Nombre del mes en minúsculas, sin año, para redactar los avisos."""
    return _MESES[fecha.month - 1]
