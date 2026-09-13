"""
Paleta y estilos del reporte operacional en Excel.

Antes esto vivía dentro de `ReporteDiaExcelView._generar_excel` como cinco closures
(`fill`, `fuente`, `borde_fino`, `centrado`, `izquierda`) más catorce constantes de color,
y cada hoja las recibía por parámetro: `_hoja_trabajan` llegó a tener doce argumentos, de
los cuales cinco eran esas funciones y tres eran colores.

Ninguna de las cinco capturaba nada del contexto, así que no había razón para pasarlas: son
funciones puras y aquí están como tales. Los colores tampoco varían por ejecución — son la
identidad visual del reporte —, salvo el par oscuro/medio que distingue una hoja de otra,
que viaja en `PaletaHoja`.
"""
from dataclasses import dataclass

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# ── Paleta ───────────────────────────────────────────────────────────────────
AZUL_OSCURO = '1E3A5F'
AZUL_MEDIO = '2563EB'
AZUL_CLARO = 'DBEAFE'
NARANJA_OSC = '92400E'
NARANJA_MED = 'D97706'
NARANJA_CL = 'FEF3C7'
GRIS_OSC = '334155'
GRIS_MED = '64748B'
GRIS_CLARO = 'F1F5F9'
VERDE_OSC = '065F46'
VERDE_MED = '0D9488'
VERDE_CL = 'DCFCE7'
MORADO_CL = 'EDE9FE'
ROJO_OSC = '7F1D1D'
ROJO_MED = 'DC2626'
BLANCO = 'FFFFFF'


@dataclass(frozen=True)
class PaletaHoja:
    """Los dos colores que distinguen una hoja de las demás.

    `oscuro` pinta el título (fila 1) y los textos destacados del cuerpo; `medio` pinta la
    fecha (fila 2) y la cabecera de la tabla (fila 4).
    """

    oscuro: str
    medio: str


PALETA_AM = PaletaHoja(oscuro=AZUL_OSCURO, medio=AZUL_MEDIO)
PALETA_PM = PaletaHoja(oscuro=NARANJA_OSC, medio=NARANJA_MED)
PALETA_DESCANSAN = PaletaHoja(oscuro=GRIS_OSC, medio=GRIS_MED)
PALETA_CAMBIOS = PaletaHoja(oscuro=VERDE_OSC, medio=VERDE_MED)
PALETA_DEUDA = PaletaHoja(oscuro=ROJO_OSC, medio=ROJO_MED)


# ── Estilos ──────────────────────────────────────────────────────────────────
def fill(hex_color):
    return PatternFill('solid', fgColor=hex_color)


def fuente(bold=False, color='000000', size=10, italic=False):
    return Font(bold=bold, color=color, size=size, italic=italic)


def borde():
    s = Side(style='thin', color='CBD5E1')
    return Border(left=s, right=s, top=s, bottom=s)


def centrado(wrap=False):
    return Alignment(horizontal='center', vertical='center', wrap_text=wrap)


def izquierda(wrap=False):
    return Alignment(horizontal='left', vertical='center', wrap_text=wrap)
