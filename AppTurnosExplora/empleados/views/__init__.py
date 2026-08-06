"""Vistas de la app empleados, divididas por dominio.

Este paquete reemplaza el antiguo módulo empleados/views.py (961 líneas). El
__init__ re-exporta todas las vistas para que `from .views import X` (en
empleados/urls.py) siga funcionando sin cambios.
"""
from .empleado import (
    EmpleadoListView,
    EmpleadoDetailView,
    EmpleadoEditForm,
    EmpleadoEditView,
    EmpleadoDeleteView,
    EmpleadoUsuarioCreateView,
    AsignarRolesSalasForm,
    AsignarRolesSalasView,
    ChangePasswordView,
)
from .roles import (
    RoleListView,
    RoleCreateView,
    RoleUpdateView,
    RoleDeleteView,
)
from .salas import (
    SalaListView,
    SalaCreateView,
    SalaUpdateView,
    SalaDeleteView,
)
from .jornadas import (
    JornadaListView,
    JornadaCreateView,
    JornadaUpdateView,
    JornadaDeleteView,
)
from .restricciones import (
    RestriccionListView,
    RestriccionCreateView,
    RestriccionUpdateView,
    RestriccionDeleteView,
    RestriccionVisualizarListView,
    _invalidar_turnos_cache_restriccion,
)
from .sanciones import (
    SancionListView,
    SancionCreateView,
    SancionUpdateView,
    SancionLevantarView,
    SancionVisualizarListView,
    _invalidar_turnos_cache_sancion,
)
from .indicadores import (
    IndicadoresView,
    MisIndicadoresView,
)
from .pdh import (
    PDHListView,
    DeudasPendientesExploradorView,
    PDHCreateView,
    PDHUpdateView,
    PDHDeleteView,
    PDHVisualizarListView,
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
    'SancionVisualizarListView', '_invalidar_turnos_cache_sancion',
    # indicadores
    'IndicadoresView', 'MisIndicadoresView',
    # pdh
    'PDHListView', 'DeudasPendientesExploradorView', 'PDHCreateView', 'PDHUpdateView',
    'PDHDeleteView', 'PDHVisualizarListView',
]
