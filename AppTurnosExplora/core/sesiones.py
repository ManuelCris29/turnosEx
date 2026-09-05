"""
Catálogo de SESIONES de la aplicación y sus permisos por empleado.

Una "sesión" es cada entrada del menú lateral: un módulo funcional completo
(PDH, Sanciones, Roles...) con todas sus pantallas asociadas. Este módulo es la
ÚNICA fuente de verdad de esa lista: el menú (`templates/base.html`), la
pantalla de permisos (`empleados/views/permisos_sesion.py`) y el guardia que
bloquea la URL (`core.middleware.PermisoSesionMiddleware`) leen todos de aquí.

⚠ Por qué el catálogo se indexa por NOMBRE DE URL y no por prefijo de ruta:
las rutas se solapan. `/empleados/` contiene PDH, sanciones, roles, salas y
jornadas, así que un guardia por prefijo no podría distinguirlas. El nombre de
URL (`pdh_list`, `sanciones_edit`) sí es único y además sobrevive a que alguien
cambie la ruta sin tocar el `name`.

⚠ Una URL que NO aparezca aquí NO queda desprotegida: sigue bajo el permiso de
siempre (`AdminRequiredMixin` / `SupervisorApiRequiredMixin`). Este catálogo
solo AÑADE una segunda reja, más fina, sobre las pantallas que se listan. Se
deja así a propósito: los cientos de endpoints AJAX que alimentan los
formularios del explorador no son "sesiones" y mapearlos uno a uno sería una
fuente inagotable de pantallas rotas.
"""

#: Grupos del menú, en el orden en que se pintan.
GRUPO_GENERAL = 'General'
GRUPO_CONSULTAS = 'Consultas rápidas'
GRUPO_ADMIN = 'Administración'


class Sesion:
    """Una entrada del menú y el conjunto de URLs que la componen.

    `defecto_supervisor` / `defecto_explorador` son lo que ve alguien de ese rol
    mientras nadie haya tocado sus permisos. Existen para que el sistema
    arranque comportándose EXACTAMENTE como antes de esta función, con una única
    excepción deliberada: `consulta_dias_especiales`, que nace apagada para el
    explorador porque la planificación anual no es información suya.
    """

    __slots__ = ('codigo', 'etiqueta', 'grupo', 'url_names',
                 'defecto_supervisor', 'defecto_explorador')

    def __init__(self, codigo, etiqueta, grupo, url_names,
                 defecto_supervisor=True, defecto_explorador=True):
        self.codigo = codigo
        self.etiqueta = etiqueta
        self.grupo = grupo
        self.url_names = tuple(url_names)
        self.defecto_supervisor = defecto_supervisor
        self.defecto_explorador = defecto_explorador


SESIONES = (
    # ── General: lo que usa el explorador para su día a día ──────────────────
    # El Dashboard no está en el catálogo a propósito: es la pantalla a la que
    # se redirige tras entrar, así que apagarla dejaría al usuario sin sitio
    # donde aterrizar.
    Sesion('mis_turnos', 'Mis Turnos / Mi Calendario', GRUPO_GENERAL,
           ['mis_turnos']),
    Sesion('notificaciones', 'Notificaciones / Solicitudes', GRUPO_GENERAL,
           ['solicitudes:solicitudes', 'solicitudes:notificaciones_list',
            'solicitudes:mis_solicitudes_list', 'solicitudes:mis_favores',
            'solicitudes:solicitudes_pendientes_list',
            'solicitudes:notificaciones_solicitudes']),
    Sesion('cambios_turno', 'Cambios de Turno', GRUPO_GENERAL,
           ['solicitudes:cambio_turno_inicio', 'solicitudes:solicitar_cambio_turno']),
    Sesion('consolidado_horas', 'Consolidado de Horas', GRUPO_GENERAL,
           ['consolidado_horas']),
    Sesion('permisos_especiales', 'Permisos Especiales', GRUPO_GENERAL,
           ['permisos_especiales', 'permisos_especiales_list',
            'permisos_especiales_create', 'permisos_especiales_permanente_create',
            'permisos_especiales_delete', 'permisos_media_jornada_create',
            'permisos_media_jornada_cancelar']),
    Sesion('beneficios', 'Beneficios Utilizados', GRUPO_GENERAL, ['beneficios']),

    # ── Consultas rápidas ────────────────────────────────────────────────────
    Sesion('consulta_sanciones', 'Consulta de Sanciones', GRUPO_CONSULTAS,
           ['sanciones_visualizar']),
    Sesion('consulta_restricciones', 'Consulta de Restricciones', GRUPO_CONSULTAS,
           ['restricciones_visualizar']),
    # La única que nace apagada para el explorador (decisión de negocio), pero
    # queda en el catálogo para poder encendérsela a quien haga falta.
    Sesion('consulta_dias_especiales', 'Consulta de Días Especiales', GRUPO_CONSULTAS,
           ['dias_especiales_visualizar'], defecto_explorador=False),

    # ── Administración: el explorador no las ve nunca por defecto ────────────
    Sesion('indicadores', 'Indicadores', GRUPO_ADMIN,
           ['indicadores'], defecto_explorador=False),
    Sesion('empleados', 'Empleados/Exploradores', GRUPO_ADMIN,
           ['empleados', 'empleado_detail', 'empleado_edit', 'empleado_baja', 'empleado_reingreso',
            'empleado_usuario_create', 'asignar_roles_salas', 'change_password'],
           defecto_explorador=False),
    Sesion('gestion_solicitudes', 'Gestión de Solicitudes', GRUPO_ADMIN,
           ['solicitudes:gestion_solicitudes', 'solicitudes:gestion_reenviar_solicitud',
            'solicitudes:gestion_cancelar_solicitud', 'solicitudes:gestion_eliminar_solicitud'],
           defecto_explorador=False),
    Sesion('reprogramaciones', 'Reprogramaciones', GRUPO_ADMIN,
           ['solicitudes:reprog_list', 'solicitudes:reprog_registrar',
            'solicitudes:reprog_programar', 'solicitudes:reprog_cancelar'],
           defecto_explorador=False),
    Sesion('cierre_solicitudes', 'Cierre de solicitudes', GRUPO_ADMIN,
           ['solicitudes:cierre_config'], defecto_explorador=False),
    Sesion('apertura_anio', 'Apertura de Año', GRUPO_ADMIN,
           ['apertura_anio_actual', 'apertura_anio'], defecto_explorador=False),
    Sesion('descansos_semana', 'Descansos de Semana', GRUPO_ADMIN,
           ['descanso_semana_anual', 'descanso_semana_list', 'descanso_semana_create',
            'descanso_semana_edit', 'descanso_semana_delete'],
           defecto_explorador=False),
    Sesion('fines_semana_festivos', 'Fines de Semana / Festivos', GRUPO_ADMIN,
           ['asignacion_especial_anual', 'asignacion_especial_siembra'],
           defecto_explorador=False),
    Sesion('tipos_solicitud', 'Tipos de Solicitud', GRUPO_ADMIN,
           ['solicitudes:tiposolicitudcambio_list', 'solicitudes:tiposolicitudcambio_create',
            'solicitudes:tiposolicitudcambio_edit', 'solicitudes:tiposolicitudcambio_delete'],
           defecto_explorador=False),
    Sesion('salas', 'Salas', GRUPO_ADMIN,
           ['salas_list', 'salas_create', 'salas_edit', 'salas_delete'],
           defecto_explorador=False),
    Sesion('turnos', 'Reporte Diario', GRUPO_ADMIN, ['turnos_list'], defecto_explorador=False),
    Sesion('jornadas', 'Jornadas', GRUPO_ADMIN,
           ['jornadas_list', 'jornadas_create', 'jornadas_edit', 'jornadas_delete'],
           defecto_explorador=False),
    Sesion('pdh', 'PDH (Pago de Horas)', GRUPO_ADMIN,
           ['pdh_list', 'pdh_create', 'pdh_edit', 'pdh_delete'],
           defecto_explorador=False),
    # Sesión aparte de 'pdh' y no fusionada con ella: reconocer horas a favor es
    # comprometer a la corporación, mientras que un PDH solo constata lo que el explorador
    # ya debía. Separarlas permite dar el pago sin dar la potestad de generar crédito.
    Sesion('credito_horas', 'Horas a favor del explorador', GRUPO_ADMIN,
           ['credito_list', 'credito_create', 'credito_anular'],
           defecto_explorador=False),
    # ⚠ 'sanciones_list' NO se lista aquí a propósito: es una pantalla
    # compartida que al explorador le enseña solo SUS sanciones. Bloquearla
    # dejaría al supervisor sin poder ver las propias. Apagar esta sesión lo
    # degrada a esa vista personal — ver `_gestiona` en empleados/views/sanciones.py.
    Sesion('sanciones', 'Sanciones (gestión)', GRUPO_ADMIN,
           ['sanciones_create', 'sanciones_edit',
            'sanciones_levantar', 'sanciones_morosos'],
           defecto_explorador=False),
    # Mismo caso compartido que 'sanciones': 'restricciones_list' queda fuera.
    Sesion('restricciones', 'Restricciones (gestión)', GRUPO_ADMIN,
           ['restricciones_create', 'restricciones_edit',
            'restricciones_delete'],
           defecto_explorador=False),
    # Quien administra roles puede darse a sí mismo cualquier permiso, así que
    # esta sesión es la llave maestra: apagarla es lo que de verdad separa a un
    # supervisor de un administrador.
    Sesion('roles', 'Roles', GRUPO_ADMIN,
           ['roles_list', 'roles_create', 'roles_edit', 'roles_delete',
            'permisos_sesion_edit'],
           defecto_explorador=False),
    Sesion('dias_especiales', 'Días Especiales (gestión)', GRUPO_ADMIN,
           ['dias_especiales_list', 'dias_especiales_edit', 'dias_especiales',
            'dias_especiales_temporadas_anual',
            'dias_especiales_festivos_mantenimiento_anual'],
           defecto_explorador=False),
)

#: codigo -> Sesion
POR_CODIGO = {s.codigo: s for s in SESIONES}

#: nombre de URL completo ('app:name' o 'name') -> codigo de sesión.
POR_URL_NAME = {
    url_name: s.codigo
    for s in SESIONES
    for url_name in s.url_names
}

#: Códigos válidos, para validar lo que llega del formulario.
CODIGOS = frozenset(POR_CODIGO)


def grupos():
    """El catálogo agrupado y en orden, tal como lo pinta la pantalla de permisos."""
    orden = (GRUPO_GENERAL, GRUPO_CONSULTAS, GRUPO_ADMIN)
    return [(g, [s for s in SESIONES if s.grupo == g]) for g in orden]
