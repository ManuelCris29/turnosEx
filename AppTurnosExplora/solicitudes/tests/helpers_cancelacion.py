"""
Helper de pruebas para el ciclo de cancelación consensuada.

Cancelar una solicitud APROBADA dejó de ser un acto del solicitante: se pide y la aprueba el
receptor (ver `CancelarSolicitudUseCase`). Los tests que sólo quieren llegar al estado "cancelada"
—para comprobar la reversión de turnos, deudas o reconciliación— no deberían repetir los dos
pasos ni acoplarse a su forma, así que los envuelve esta función.

Para probar el ACUERDO en sí (que pedir no cancela, que rechazar deja el cambio firme, la
caducidad, quién puede responder), ver `test_cancelacion_lifo.py`.
"""
from __future__ import annotations

from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase


def cancelar_con_acuerdo(solicitud, solicitante=None, receptor=None):
    """
    Ejecuta el ciclo completo: el solicitante pide la cancelación y el receptor la aprueba.

    Devuelve `(ok, mensaje)` con el mismo contrato que el use case. Si la petición falla —una
    guardia la bloquea, el plazo venció— se devuelve ese fallo sin llegar a responder: es el
    primer paso el que decide.
    """
    uc = CancelarSolicitudUseCase()
    ok, msg = uc.execute(solicitud.id, solicitante or solicitud.explorador_solicitante)
    if not ok:
        return ok, msg
    return uc.responder_cancelacion(
        solicitud.id, receptor or solicitud.explorador_receptor, aprueba=True
    )
