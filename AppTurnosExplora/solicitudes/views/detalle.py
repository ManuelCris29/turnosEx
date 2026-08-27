import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.views import View

from ..models import SolicitudCambio

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.utils.date_utils import DateUtils
from core.utils.json_responses import json_error, json_ok

# Create your views here.

class ObtenerDetalleSolicitudView(LoginRequiredMixin, View):
    """
    Endpoint API para obtener detalles completos de una solicitud.
    Incluye información específica según el tipo de solicitud.
    """
    def get(self, request, solicitud_id):
        try:
            # Obtener la solicitud con todas sus relaciones
            solicitud = get_object_or_404(
                SolicitudCambio.objects.select_related(
                    'explorador_solicitante',
                    'explorador_receptor',
                    'tipo_cambio',
                    'explorador_solicitante__supervisor',
                    'explorador_receptor__supervisor'
                ),
                id=solicitud_id
            )
            
            # Verificar permisos: solo el solicitante, receptor, supervisor o admin pueden ver
            usuario_empleado = None
            if hasattr(request.user, 'empleado'):
                usuario_empleado = request.user.empleado
            
            puede_ver = False
            if usuario_empleado:
                puede_ver = (
                    solicitud.explorador_solicitante == usuario_empleado or
                    solicitud.explorador_receptor == usuario_empleado or
                    solicitud.explorador_solicitante.supervisor == usuario_empleado or
                    solicitud.explorador_receptor.supervisor == usuario_empleado or
                    request.user.is_staff
                )
            
            if not puede_ver:
                return json_error('No tiene permisos para ver esta solicitud', status=403, code='forbidden')

            datos = ObtenerDetalleSolicitudView.construir_datos(solicitud)
            return json_ok(datos)

        except Exception as e:
            logger.error(f"Error en ObtenerDetalleSolicitudView: {e}", exc_info=True)
            return json_error('Error al obtener detalles de la solicitud', status=500, code='internal_error')

    @staticmethod
    def construir_datos(solicitud):
        """
        Construye el diccionario de detalle completo de una solicitud (común +
        específico por tipo). Reutilizable por la API de detalle y por las
        páginas de resultado de aprobación/rechazo por email.
        """
        # Información básica común
        datos = {
                'id': solicitud.id,
                'fecha_solicitud': DateUtils.format_datetime_display(solicitud.fecha_solicitud),
                'tipo': solicitud.tipo_cambio.nombre,
                'tipo_codigo': solicitud.tipo_cambio.codigo_estrategia or solicitud.tipo_cambio.nombre.upper(),
                'estado': solicitud.estado,
                'comentario': solicitud.comentario or 'Sin comentario',
                'fecha_resolucion': DateUtils.format_datetime_display(solicitud.fecha_resolucion),
                # Hora REAL de la cancelación. No es la de resolución: esa es la de la aprobación y
                # se conserva (de ella dependen la ventana de 30 min y la guardia LIFO).
                'fecha_cancelacion': DateUtils.format_datetime_display(solicitud.fecha_cancelacion),
                'solicitante': {
                    'id': solicitud.explorador_solicitante.id,
                    'nombre': f"{solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}",
                    'email': solicitud.explorador_solicitante.email,
                    'supervisor': f"{solicitud.explorador_solicitante.supervisor.nombre} {solicitud.explorador_solicitante.supervisor.apellido}" if solicitud.explorador_solicitante.supervisor else None,
                },
                'receptor': {
                    'id': solicitud.explorador_receptor.id,
                    'nombre': f"{solicitud.explorador_receptor.nombre} {solicitud.explorador_receptor.apellido}",
                    'email': solicitud.explorador_receptor.email,
                    'supervisor': f"{solicitud.explorador_receptor.supervisor.nombre} {solicitud.explorador_receptor.supervisor.apellido}" if solicitud.explorador_receptor.supervisor else None,
                },
                'aprobaciones': {
                    'receptor': {
                        'aprobado': solicitud.aprobado_receptor,
                        'fecha': DateUtils.format_datetime_display(solicitud.fecha_aprobacion_receptor),
                    },
                    'supervisor': {
                        'aprobado': solicitud.aprobado_supervisor,
                        'fecha': DateUtils.format_datetime_display(solicitud.fecha_aprobacion_supervisor),
                    },
                },
            'fechas': {},
            'informacion_adicional': {}
        }

        # Información específica del tipo: la aporta la STRATEGY, no esta vista.
        #
        # Aquí había una cadena `if tipo_nombre == 'CT PERMANENTE': ... elif ...` con
        # seis ramas. Añadir un tipo de solicitud obligaba a editar esta vista, que es
        # exactamente lo que el principio abierto/cerrado dice que no debe pasar: la
        # pantalla de detalle no tiene por qué conocer los tipos que existen.
        #
        # El `else` de aquella cadena mandaba los tipos no contemplados al detalle de
        # CAMBIO TURNO. Ese comportamiento SE CONSERVA a propósito —lo fija un test de
        # `test_detalle_caracterizacion.py`— para que un tipo sin strategy registrada
        # siga devolviendo detalle en lugar de una pantalla vacía.
        # `get_strategy_registrada` y no `get_strategy`: la segunda descarta los tipos
        # INACTIVOS, y con ella una DOBLADA de un tipo dado de baja pasaba a mostrar
        # el detalle de un CAMBIO TURNO. Que el tipo ya no admita solicitudes nuevas
        # no cambia como se materializo una que ya existe.
        #
        # El `or CambioTurnoStrategy()` conserva el `else` de la cadena anterior: un
        # tipo sin strategy propia sigue mostrando el detalle generico en vez de una
        # pantalla vacia. Aqui esa caida es correcta porque solo se LEE; en los flujos
        # que escriben (revertir, reconciliar) seria inaceptable y por eso alli no hay
        # caida por defecto.
        from ..services.solicitud_factory import SolicitudFactory
        from ..services.strategies.cambio_turno_strategy import CambioTurnoStrategy

        estrategia = (SolicitudFactory.get_strategy_registrada(solicitud.tipo_cambio)
                      or CambioTurnoStrategy())
        estrategia.detalle(solicitud, datos)
        return datos

    

    

    





    
