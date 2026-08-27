"""Vistas de la app empleados, divididas por dominio.

Este paquete reemplaza el antiguo módulo empleados/views.py (961 líneas). El
__init__ re-exporta todas las vistas para que `from .views import X` (en
empleados/urls.py) siga funcionando sin cambios.
"""
from .empleado import (
    AsignarRolesSalasForm,
    AsignarRolesSalasView,
    ChangePasswordView,
    EmpleadoDeleteView,
    EmpleadoDetailView,
    EmpleadoEditForm,
    EmpleadoEditView,
    EmpleadoListView,
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
from .restricciones import (
    RestriccionCreateView,
    RestriccionDeleteView,
    RestriccionListView,
    RestriccionUpdateView,
    RestriccionVisualizarListView,
    _invalidar_turnos_cache_restriccion,
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
    _invalidar_turnos_cache_sancion,
)

__all__ = [
    # empleado
    'EmpleadoListView', 'EmpleadoDetailView', 'EmpleadoEditForm', 'EmpleadoEditView',
    'EmpleadoDeleteView',
    'EmpleadoUsuarioCreateView', 'AsignarRolesSalasForm', 'AsignarRolesSalasView',
    'ChangePasswordView',
    # roles
    'RoleListView', 'RoleCreateView', 'RoleUpdateView', 'RoleDeleteView',
    # salas
    'SalaListView', 'SalaCreateView', 'SalaUpdateView', 'SalaDeleteView',
    # jornadas
    'JornadaListView', 'JornadaCreateView', 'JornadaUpdateView', 'JornadaDeleteView',
    # restricciones
    'RestriccionListView', 'RestriccionCreateView', 'RestriccionUpdateView',
    'RestriccionDeleteView', 'RestriccionVisualizarListView',
    '_invalidar_turnos_cache_restriccion',
    # sanciones
    'SancionListView', 'SancionCreateView', 'SancionUpdateView', 'SancionLevantarView',
    'SancionVisualizarListView', 'MorososDeudaView', '_invalidar_turnos_cache_sancion',
    # indicadores
    'IndicadoresView', 'MisIndicadoresView',
    # pdh
    'PDHListView', 'DeudasPendientesExploradorView', 'PDHCreateView', 'PDHUpdateView',
    'PDHDeleteView',
]
