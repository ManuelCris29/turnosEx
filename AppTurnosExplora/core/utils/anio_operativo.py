"""
El AÑO OPERATIVO: la app trabaja sobre el año en curso y solo sobre él.

Cada 1 de enero el sistema arranca en limpio. La planificación del año siguiente se prepara
aparte, en la APERTURA DE AÑO (`/turnos/apertura-anio/`): festivos, mantenimientos,
temporadas, descansos de semana y alternancia de findes se publican para ese año antes de
que empiece. Hasta que eso ocurre, el año siguiente no existe como terreno donde operar.

De ahí la regla: **ninguna solicitud ni permiso puede tocar un año distinto del año en curso.**
No hay cambios de turno con el pago en el año siguiente, ni permisos que crucen el 31 de
diciembre, ni rangos permanentes que se estiren hasta el año que viene. Si se permitiera, la
solicitud caería sobre un calendario que todavía no está publicado —o que se va a reconstruir
en la apertura— y el turno resultante sería basura.

Este módulo es la ÚNICA definición de esa frontera. Devuelve datos, no excepciones: cada capa
la traduce a su convención (`ValidationError` en los validadores de solicitudes, `json_error`
en los endpoints). Así la regla se comprueba igual en todas partes y solo hay un sitio que
cambiar si algún día el negocio decide abrir una ventana entre años.
"""
from datetime import date

from django.utils import timezone

__all__ = ['anio_operativo', 'fechas_fuera_del_anio_operativo', 'mensaje_fuera_del_anio_operativo']


def anio_operativo(hoy: date | None = None) -> int:
    """El año sobre el que se puede operar hoy. Siempre el año en curso."""
    return (hoy or timezone.localdate()).year


def fechas_fuera_del_anio_operativo(fechas, hoy: date | None = None) -> list[date]:
    """
    Las fechas de `fechas` que caen fuera del año operativo, ordenadas y sin repetir.

    Ignora los valores vacíos: quien llama suele pasar campos opcionales (`fecha_pago`,
    `fecha_compensacion`, `fecha_fin`) que pueden venir a None.
    """
    anio = anio_operativo(hoy)
    fuera = {f for f in fechas if f and f.year != anio}
    return sorted(fuera)


def mensaje_fuera_del_anio_operativo(fechas, hoy: date | None = None) -> str | None:
    """
    Mensaje de error si alguna fecha se sale del año operativo; None si todas son válidas.

    El mensaje nombra las fechas infractoras: con rangos permanentes o permisos de varios
    días, decir solo "hay fechas de otro año" obliga al usuario a adivinar cuál.
    """
    fuera = fechas_fuera_del_anio_operativo(fechas, hoy)
    if not fuera:
        return None

    anio = anio_operativo(hoy)
    listado = ', '.join(f.strftime('%d/%m/%Y') for f in fuera)
    return (
        f'Solo se puede operar sobre el año {anio}. '
        f'Estas fechas son de otro año: {listado}. '
        f'El año siguiente se habilita con la apertura de año.'
    )
