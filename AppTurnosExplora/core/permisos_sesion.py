"""
Resolución del permiso de sesión: qué pantallas ve realmente un usuario.

Única definición de la regla. La consumen el context processor (para pintar el
menú), el middleware (para bloquear la URL) y la pantalla de administración
(para marcar las casillas). Si la regla cambia, cambia aquí y en ningún otro
sitio.

La regla, en orden:

1. `is_staff` / `is_superuser` → lo ve TODO. Es el administrador de la
   aplicación y no se le puede recortar desde esta pantalla; si hay que
   limitarlo, se le quita el flag desde /admin/. Se resuelve primero para que
   nadie pueda dejar el sistema sin administrador marcando casillas.
2. Fila en `PermisoSesion` para esa sesión → manda lo que diga `habilitado`.
3. Sin fila → el valor por defecto del rol (Supervisor o Explorador) que define
   `core.sesiones`.

⚠ Esto NUNCA concede acceso: `AdminRequiredMixin` sigue exigiendo rol Supervisor
para las pantallas de Administración. Marcarle `pdh` a un explorador no le abre
PDH; solo evita que la sesión le aparezca tachada el día que sí sea supervisor.
"""
import logging

from core.sesiones import POR_CODIGO, SESIONES

logger = logging.getLogger(__name__)


def _es_admin_total(user) -> bool:
    """El administrador de la aplicación, inmune a la matriz de permisos."""
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


def defectos_para(es_supervisor_rol: bool) -> dict:
    """Los valores por defecto del catálogo para un rol, como {codigo: bool}."""
    campo = 'defecto_supervisor' if es_supervisor_rol else 'defecto_explorador'
    return {s.codigo: getattr(s, campo) for s in SESIONES}


def excepciones_de(empleado) -> dict:
    """Las filas guardadas para un empleado, como {codigo: habilitado}."""
    if empleado is None:
        return {}
    return {
        p.sesion: p.habilitado
        for p in empleado.permisos_sesion.all()
        if p.sesion in POR_CODIGO  # una sesión retirada del catálogo se ignora
    }


def sesiones_habilitadas(user) -> dict:
    """Mapa {codigo: bool} con lo que este usuario ve. Falla CERRADO salvo staff.

    Devuelve un dict completo (todas las sesiones del catálogo) y no un set,
    porque la plantilla necesita poder preguntar por una sesión que está
    apagada sin que Django lo confunda con "la variable no existe".
    """
    from core.mixins import es_supervisor

    if not getattr(user, 'is_authenticated', False):
        return {s.codigo: False for s in SESIONES}

    if _es_admin_total(user):
        return {s.codigo: True for s in SESIONES}

    empleado = getattr(user, 'empleado', None)
    permisos = defectos_para(es_supervisor(user))
    try:
        permisos.update(excepciones_de(empleado))
    except Exception:
        # Un fallo leyendo las excepciones no puede tumbar todas las pantallas:
        # se cae a los valores por defecto del rol, que son los de siempre.
        logger.warning(
            "No se pudieron leer los permisos de sesión de user=%s",
            getattr(user, 'username', '?'), exc_info=True,
        )
    return permisos


def puede_ver(user, codigo: str) -> bool:
    """True si el usuario tiene habilitada esa sesión. Un código desconocido pasa.

    Un código que no está en el catálogo devuelve True a propósito: significa que
    la pantalla no es una sesión gobernada por esta matriz, y su permiso sigue
    siendo el de siempre.
    """
    if codigo not in POR_CODIGO:
        return True
    return sesiones_habilitadas(user).get(codigo, False)
