"""
Resultado de dominio de crear una solicitud.

POR QUÉ EXISTE
--------------
`SolicitudOrchestrator.procesar()` devolvía `JsonResponse`. Eso ataba todo el flujo
de alta —sanción, cierre semanal, restricción médica, validación y creación— a la
capa HTTP: crear una solicitud desde un test de integración, un comando de gestión
o una tarea programada obligaba a fabricar un POST y a leer el cuerpo con
`json.loads(resp.content)` para saber si había salido bien.

Ahora el orquestador devuelve esto —éxito/error, mensaje, código y datos— y la
VISTA lo convierte en `JsonResponse` (`solicitudes/views/resultado_http.py`).

EL CUERPO JSON NO CAMBIA
------------------------
`como_payload()` reproduce exactamente lo que producían `json_ok`/`json_error`
(`success`, `error`, `code`, `extra`, y el resto del payload en el caso correcto),
porque los seis formularios leen esas claves. Este cambio es de estructura, no de
contrato: los tests de caracterización de las vistas siguen valiendo tal cual.

`desde_payload` cubre los dos cuerpos cuya FORMA la define el dominio y no estos
helpers: la advertencia de restricción médica (`verificar_restriccion`) y
`RequiereCambioTurnoPrevio.como_payload()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResultadoSolicitud:
    """Qué pasó al intentar crear la solicitud. Sin nada de HTTP dentro."""

    exitoso: bool
    status: int = 200
    mensaje: str = ''
    code: str | None = None
    datos: dict = field(default_factory=dict)
    #: Cuerpo ya formado cuando la forma la define el dominio (restricción médica,
    #: `RequiereCambioTurnoPrevio`). Si está presente, manda sobre todo lo demás.
    payload_crudo: dict | None = None

    # ------------------------------------------------------------------
    # Constructores (misma firma que los antiguos `json_ok` / `json_error`,
    # para que el orquestador se lea igual y la sustitución sea verificable)
    # ------------------------------------------------------------------

    @classmethod
    def exito(cls, payload: dict | None = None, status: int = 200) -> "ResultadoSolicitud":
        datos = dict(payload) if isinstance(payload, dict) else {}
        mensaje = str(datos.get('message', ''))
        return cls(exitoso=True, status=status, mensaje=mensaje, datos=datos)

    @classmethod
    def error(cls, message, *, status: int = 400, code: str | None = None,
              extra: dict | None = None) -> "ResultadoSolicitud":
        datos = {'extra': extra} if isinstance(extra, dict) else {}
        # `message` puede ser un `ErrorDelCompanero`/`RequiereCambioTurnoPrevio` (subclases
        # de `str` con datos colgados): se conserva tal cual, no se normaliza a `str`, para
        # que quien lo reciba pueda seguir reconociéndolo con `isinstance`.
        return cls(exitoso=False, status=status, mensaje=message, code=code, datos=datos)

    @classmethod
    def desde_payload(cls, payload: dict, status: int = 400) -> "ResultadoSolicitud":
        """Resultado cuyo cuerpo JSON ya viene formado por el dominio."""
        return cls(
            exitoso=bool(payload.get('success', False)),
            status=status,
            mensaje=str(payload.get('message') or payload.get('error') or ''),
            code=payload.get('code'),
            payload_crudo=dict(payload),
        )

    # ------------------------------------------------------------------

    @property
    def fallo(self) -> bool:
        return not self.exitoso

    def como_payload(self) -> dict:
        """El cuerpo JSON, idéntico al que producían `json_ok` / `json_error`."""
        if self.payload_crudo is not None:
            return dict(self.payload_crudo)
        if self.exitoso:
            return {'success': True, **self.datos}
        cuerpo: dict = {'success': False, 'error': str(self.mensaje)}
        if self.code:
            cuerpo['code'] = self.code
        extra = self.datos.get('extra')
        if isinstance(extra, dict):
            cuerpo['extra'] = extra
        return cuerpo
