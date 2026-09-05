"""Vistas de la app empleados, divididas por dominio.

Este paquete reemplaza el antiguo módulo empleados/views.py (961 líneas). El
__init__ re-exporta todas las vistas para que `from .views import X` (en
empleados/urls.py) siga funcionando sin cambios.
"""
from .credito import (
    CreditoHorasAnularView,
    CreditoHorasCreateView,
    CreditoHorasListView,
)
from .empleado import (
    AsignarRolesSalasForm,
    AsignarRolesSalasView,
    ChangePasswordView,
    EmpleadoBajaView,
    EmpleadoDetailView,
    EmpleadoEditForm,
    EmpleadoEditView,
    EmpleadoListView,
    EmpleadoReingresoView,
    EmpleadoUsuarioCreateView,
)
from .indicadores import (
    IndicadoresView,
    MisIndicadoresView,
)
from .jornadas import (
    JornadaCreateView,
    JornadaDeleteView,
    JornadaListView,
    JornadaUpdateView,
)
from .pdh import (
    DeudasPendientesExploradorView,
    PDHCreateView,
    PDHDeleteView,
    PDHListView,
    PDHUpdateView,
)
from .permisos_sesion import (
    PermisosSesionUpdateView,
)
from .restricciones import (
    RestriccionCreateView,
    RestriccionDeleteView,
    RestriccionListView,
    RestriccionUpdateView,
    RestriccionVisualizarListView,
)
from .roles import (
    RoleCreateView,
    RoleDeleteView,
    RoleListView,
    RoleUpdateView,
)
from .salas import (
    SalaCreateView,
    SalaDeleteView,
    SalaListView,
    SalaUpdateView,
)
from .sanciones import (
    MorososDeudaView,
    SancionCreateView,
    SancionLevantarView,
    SancionListView,
    SancionUpdateView,
    SancionVisualizarListView,
)

__all__ = [
    'CreditoHorasAnularView',
    'CreditoHorasCreateView',
    'CreditoHorasListView',
    # empleado
    'EmpleadoListView', 'EmpleadoDetailView', 'EmpleadoEditForm', 'EmpleadoEditView',
    'EmpleadoBajaView',
    'EmpleadoReingresoView',
    'EmpleadoUsuarioCreateView', 'AsignarRolesSalasForm', 'AsignarRolesSalasView',
    'ChangePasswordView',
    # permisos de sesión
    'PermisosSesionUpdateView',
    # roles
    'RoleListView', 'RoleCreateView', 'RoleUpdateView', 'RoleDeleteView',
    # salas
    'SalaListView', 'SalaCreateView', 'SalaUpdateView', 'SalaDeleteView',
    # jornadas
    'JornadaListView', 'JornadaCreateView', 'JornadaUpdateView', 'JornadaDeleteView',
    # restricciones
    'RestriccionListView', 'RestriccionCreateView', 'RestriccionUpdateView',
    'RestriccionDeleteView', 'RestriccionVisualizarListView',
    # sanciones
    'SancionListView', 'SancionCreateView', 'SancionUpdateView', 'SancionLevantarView',
    'SancionVisualizarListView', 'MorososDeudaView',
    # indicadores
    'IndicadoresView', 'MisIndicadoresView',
    # pdh
    'PDHListView', 'DeudasPendientesExploradorView', 'PDHCreateView', 'PDHUpdateView',
    'PDHDeleteView',
]
