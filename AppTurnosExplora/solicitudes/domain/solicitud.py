"""
Objetos de dominio y reglas de negocio puras para SolicitudCambio.

Todo lo que está aquí es lógica de negocio sin dependencias de Django ORM,
frameworks externos ni servicios. Puede ser testeado sin base de datos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .estado_machine import TRANSICIONES, ESTADOS_TERMINALES
from .jornada import es_jornada_valida, normalizar_jornada


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParTurno:
    """Representa el par (empleado, fecha) afectado por un cambio."""
    empleado_id: int
    fecha: date

    def __str__(self) -> str:
        return f"{self.empleado_id}:{self.fecha.isoformat()}"

    @classmethod
    def from_key(cls, key: str) -> "ParTurno":
        """Parsea una clave 'empleado_id:YYYY-MM-DD'."""
        parts = key.split(':', 1)
        return cls(empleado_id=int(parts[0]), fecha=date.fromisoformat(parts[1]))


@dataclass(frozen=True)
class VentanaCancelacion:
    """Regla de dominio: ventana de tiempo para cancelar una solicitud aprobada."""
    minutos: int = 30

    def esta_dentro_de_ventana(self, minutos_transcurridos: float) -> bool:
        return minutos_transcurridos <= self.minutos

    def mensaje_vencida(self, minutos_transcurridos: int) -> str:
        return (
            f'Ya no es posible cancelar esta solicitud. Solo se puede cancelar dentro de los '
            f'{self.minutos} minutos posteriores a su aprobación '
            f'(han pasado {minutos_transcurridos} minutos).'
        )


# ---------------------------------------------------------------------------
# Reglas de negocio puras (sin ORM)
# ---------------------------------------------------------------------------

def puede_cancelar(estado: str, es_solicitante: bool) -> tuple[bool, str]:
    """
    Regla de dominio: ¿puede un empleado cancelar una solicitud en este estado?
    Devuelve (puede, motivo_si_no).
    """
    if not es_solicitante:
        return False, 'Solo puedes cancelar tus propias solicitudes'
    if estado == 'pendiente':
        return True, ''
    if estado == 'aprobada':
        return True, ''
    return False, f'No se puede cancelar una solicitud en estado "{estado}".'


def puede_aprobar_como_receptor(estado: str, explorador_receptor_id: int, empleado_id: int) -> tuple[bool, str]:
    if estado != 'pendiente':
        return False, f'La solicitud no está en estado pendiente (estado actual: {estado})'
    if explorador_receptor_id != empleado_id:
        return False, 'No eres el receptor de esta solicitud'
    return True, ''


def puede_aprobar_como_supervisor(estado: str, supervisor_id: Optional[int], empleado_id: int) -> tuple[bool, str]:
    if estado != 'pendiente':
        return False, f'La solicitud no está en estado pendiente (estado actual: {estado})'
    if supervisor_id != empleado_id:
        return False, 'No eres el supervisor del solicitante'
    return True, ''


def pares_afectados_desde_snapshot(snapshot: dict) -> set[ParTurno]:
    """Convierte el snapshot JSON en un conjunto de ParTurno."""
    return {ParTurno.from_key(k) for k in snapshot.keys()}


def hay_conflicto_lifo(mios: set[ParTurno], otros_snapshots: list[dict]) -> Optional[str]:
    """
    Verifica la guardia LIFO: si hay un cambio posterior sobre los mismos pares,
    devuelve un mensaje de error; si no hay conflicto, devuelve None.
    """
    for snapshot in otros_snapshots:
        otros = pares_afectados_desde_snapshot(snapshot)
        comunes = mios & otros
        if comunes:
            fechas = sorted({p.fecha.strftime('%d/%m') for p in comunes})
            fmt = ', '.join(fechas)
            return (
                f'No puedes cancelar este cambio: hay otro más reciente sobre el mismo '
                f'día ({fmt}). Cancela primero el cambio más reciente.'
            )
    return None
