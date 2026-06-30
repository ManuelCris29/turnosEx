"""
Máquina de estados finitos para SolicitudCambio.

Centraliza las transiciones válidas entre estados para evitar que el código
asigne solicitud.estado = '...' directamente sin validar si la transición es legal.

Estados terminales (sin salida): rechazada, cancelada, reemplazada, pagada.
"""

# Mapa de transiciones válidas: estado_actual -> {estados_destino_permitidos}
_TRANSICIONES: dict[str, set[str]] = {
    'pendiente':    {'aprobada', 'rechazada', 'cancelada'},
    'aprobada':     {'cancelada', 'reemplazada', 'pagada'},
    'rechazada':    set(),   # terminal
    'cancelada':    set(),   # terminal
    'reemplazada':  set(),   # terminal
    'pagada':       set(),   # terminal
}

_ESTADOS_VALIDOS = set(_TRANSICIONES.keys())


class EstadoTransicionError(ValueError):
    """Se lanza cuando se intenta una transición de estado inválida."""
    pass


def transicionar(solicitud, nuevo_estado: str, *, save: bool = True, update_fields: list | None = None) -> None:
    """
    Transiciona una SolicitudCambio a un nuevo estado, validando que la transición sea legal.

    Args:
        solicitud:     instancia de SolicitudCambio a transicionar.
        nuevo_estado:  estado destino ('aprobada', 'cancelada', etc.).
        save:          si True (por defecto), guarda el modelo tras el cambio.
        update_fields: lista de campos adicionales a guardar junto con 'estado'
                       (solo se usa cuando save=True).

    Raises:
        EstadoTransicionError: si la transición no está permitida.
        ValueError:            si nuevo_estado no es un estado reconocido.
    """
    if nuevo_estado not in _ESTADOS_VALIDOS:
        raise ValueError(f"Estado desconocido: '{nuevo_estado}'. Válidos: {sorted(_ESTADOS_VALIDOS)}")

    estado_actual = solicitud.estado
    if nuevo_estado not in _TRANSICIONES.get(estado_actual, set()):
        raise EstadoTransicionError(
            f"Transición inválida en solicitud {getattr(solicitud, 'id', '?')}: "
            f"'{estado_actual}' → '{nuevo_estado}'. "
            f"Transiciones permitidas desde '{estado_actual}': "
            f"{sorted(_TRANSICIONES.get(estado_actual, set())) or '(ninguna — estado terminal)'}"
        )

    solicitud.estado = nuevo_estado

    if save:
        campos = ['estado'] + (update_fields or [])
        solicitud.save(update_fields=campos)


def puede_transicionar(estado_actual: str, nuevo_estado: str) -> bool:
    """Retorna True si la transición es válida, sin lanzar excepción."""
    return nuevo_estado in _TRANSICIONES.get(estado_actual, set())


def transiciones_posibles(estado_actual: str) -> set[str]:
    """Retorna el conjunto de estados a los que se puede ir desde estado_actual."""
    return set(_TRANSICIONES.get(estado_actual, set()))


def es_terminal(estado: str) -> bool:
    """Retorna True si el estado no tiene salidas (rechazada, cancelada, reemplazada, pagada)."""
    return not _TRANSICIONES.get(estado)
