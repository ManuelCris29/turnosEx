from django.shortcuts import render, get_object_or_404
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from empleados.views import AdminRequiredMixin
from empleados.models import Empleado
from .models import TipoSolicitudCambio, Notificacion, SolicitudCambio
from .services.solicitud_service import SolicitudService
from .services.solicitud_factory import SolicitudFactory
from .services.permiso_service import PermisoService
from .services.notificacion_service import NotificacionService
from django.utils import timezone
import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)

def json_ok(payload=None, status=200):
    data = {'success': True}
    if isinstance(payload, dict):
        data.update(payload)
    return JsonResponse(data, status=status)

def json_error(message, *, status=400, code=None, extra=None):
    data = {'success': False, 'error': str(message)}
    if code:
        data['code'] = code
    if isinstance(extra, dict):
        data['extra'] = extra
    return JsonResponse(data, status=status)

# Create your views here.

class SolicitudesView(LoginRequiredMixin, TemplateView):
    template_name = 'solicitudes/list.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated and hasattr(self.request.user, 'empleado'):
            # Contar solicitudes del usuario logueado (donde es el solicitante)
            mis_solicitudes_count = SolicitudCambio.objects.filter(
                explorador_solicitante=self.request.user.empleado
            ).count()
            
            # Contar solicitudes pendientes que el usuario puede aprobar
            # Solo receptor y supervisor (NO solicitante)
            from django.db.models import Q
            solicitudes_pendientes_count = SolicitudCambio.objects.filter(
                Q(estado='pendiente', explorador_receptor=self.request.user.empleado, aprobado_receptor=False) |
                Q(estado='pendiente', explorador_solicitante__supervisor=self.request.user.empleado, aprobado_supervisor=False)
            ).distinct().count()
            
            # Debug: Imprimir información para entender el conteo
            print(f"DEBUG CONTADOR - Usuario: {self.request.user.empleado.nombre}")
            print(f"DEBUG CONTADOR - Total pendientes (con distinct): {solicitudes_pendientes_count}")
            
            # Debug detallado: Mostrar las solicitudes específicas
            solicitudes_combined = SolicitudCambio.objects.filter(
                Q(estado='pendiente', explorador_receptor=self.request.user.empleado, aprobado_receptor=False) |
                Q(estado='pendiente', explorador_solicitante__supervisor=self.request.user.empleado, aprobado_supervisor=False)
            ).distinct()
            
            print(f"DEBUG DETALLADO - Solicitudes combinadas:")
            for s in solicitudes_combined:
                es_receptor = s.explorador_receptor == self.request.user.empleado and not s.aprobado_receptor
                es_supervisor = s.explorador_solicitante.supervisor == self.request.user.empleado and not s.aprobado_supervisor
                
                if es_receptor and es_supervisor:
                    rol = "AMBOS"
                elif es_receptor:
                    rol = "RECEPTOR"
                elif es_supervisor:
                    rol = "SUPERVISOR"
                else:
                    rol = "DESCONOCIDO"
                    
                print(f"  - ID: {s.id}, Solicitante: {s.explorador_solicitante.nombre}, Receptor: {s.explorador_receptor.nombre}, Rol: {rol}, Fecha: {s.fecha_solicitud}")
            
            context['mis_solicitudes_count'] = mis_solicitudes_count
            context['solicitudes_pendientes_count'] = solicitudes_pendientes_count
            
        return context

# CRUD de TipoSolicitudCambio
class TipoSolicitudCambioListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_list.html'
    context_object_name = 'tipos_solicitud'

class TipoSolicitudCambioCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_create.html'
    fields = ['nombre', 'activo', 'genera_deuda']
    success_url = '/solicitudes/tipos-solicitud/'

class TipoSolicitudCambioUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_edit.html'
    fields = ['nombre', 'activo', 'genera_deuda']
    success_url = '/solicitudes/tipos-solicitud/'

class TipoSolicitudCambioDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_confirm_delete.html'
    success_url = '/solicitudes/tipos-solicitud/'

# CRUD de PermisoDetalle - COMENTADO TEMPORALMENTE (modelo no existe)
# class PermisoDetalleListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
#     model = PermisoDetalle
#     template_name = 'solicitudes/permisodetalle_list.html'
#     context_object_name = 'permisos_detalle'

#     def get_queryset(self):
#         # Usar el servicio para obtener permisos
#         return PermisoService.get_permisos_pendientes()

# class PermisoDetalleCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
#     model = PermisoDetalle
#     template_name = 'solicitudes/permisodetalle_create.html'
#     fields = ['solicitud', 'horas_solicitadas']
#     success_url = '/solicitudes/permisos-detalle/'

# class PermisoDetalleUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
#     model = PermisoDetalle
#     template_name = 'solicitudes/permisodetalle_edit.html'
#     fields = ['solicitud', 'horas_solicitadas']
#     success_url = '/solicitudes/permisos-detalle/'

# class PermisoDetalleDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
#     model = PermisoDetalle
#     template_name = 'solicitudes/permisodetalle_confirm_delete.html'
#     success_url = '/solicitudes/permisos-detalle/'

class CambioTurnoInicioView(LoginRequiredMixin, TemplateView):
    template_name = 'solicitudes/cambio_turno_inicio.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tipos_solicitud'] = SolicitudService.get_tipos_solicitud_activos()
        return context
    
class SolicitarCambioTurnoView(LoginRequiredMixin, View):
    def get(self, request, tipo_id):
        tipo_solicitud = get_object_or_404(TipoSolicitudCambio, id=tipo_id)
        
        # Determinar qué template usar según el tipo de solicitud
        if tipo_solicitud.nombre == "CT PERMANENTE":
            return self._render_ct_permanente(request, tipo_solicitud)
        else:
            return self._render_cambio_turno_normal(request, tipo_solicitud)
    
    def _render_ct_permanente(self, request, tipo_solicitud):
        """Renderizar formulario específico para CT PERMANENTE"""
        # Usar una fecha que tenga jornadas asignadas por defecto
        fecha_por_defecto = timezone.now().date() + timezone.timedelta(days=1)
        
        # Si no hay jornadas para mañana, usar una fecha futura
        from turnos.models import AsignarJornadaExplorador
        if not AsignarJornadaExplorador.objects.filter(fecha_inicio__lte=fecha_por_defecto, fecha_fin__gte=fecha_por_defecto).exists():
            fecha_por_defecto = timezone.datetime(2025, 8, 25).date()
        
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.now().date() + timezone.timedelta(days=1),
            'fecha_inicio': fecha_por_defecto,
            'fecha_fin': None,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
            'comentarios': '',
        }
        return render(request, 'solicitudes/solicitar_ct_permanente.html', context)
    
    def _render_cambio_turno_normal(self, request, tipo_solicitud):
        """Renderizar formulario para cambio de turno normal"""
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.now().date(),
            'fecha_seleccionada': timezone.now().date(),
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
        }
        return render(request, 'solicitudes/solicitar_cambio_turno.html', context)


class ObtenerEmpleadosDisponiblesView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        tipo_solicitud_id = request.GET.get('tipo_solicitud_id')
        
        print(f"DEBUG: fecha={fecha}, tipo_solicitud_id={tipo_solicitud_id}")
        
        if not fecha:
            return json_ok({'empleados': []})
        
        # Obtener el tipo de solicitud
        tipo_solicitud = None
        if tipo_solicitud_id:
            try:
                tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)  # type: ignore
                logger.debug("Tipo de solicitud obtenido", extra={
                    'tipo_solicitud': tipo_solicitud.nombre,
                    'tipo_id': tipo_solicitud_id
                })
            except TipoSolicitudCambio.DoesNotExist:  # type: ignore
                logger.warning("Tipo de solicitud no encontrado", extra={'tipo_id': tipo_solicitud_id})
        
        # Verificar si el usuario tiene empleado asociado
        if not hasattr(request.user, 'empleado'):
            return json_ok({'empleados': []})
        
        # Obtener empleados según el tipo de solicitud usando el Factory
        empleados_disponibles = SolicitudFactory.get_empleados_disponibles(
            tipo_solicitud, 
            fecha, 
            request.user.empleado
        )
        
        logger.debug("Empleados disponibles obtenidos", extra={
            'count': len(empleados_disponibles),
            'tipo_solicitud': tipo_solicitud.nombre if tipo_solicitud else 'None'
        })
        
        # Convertir a formato JSON
        empleados_data = []
        for empleado in empleados_disponibles:
            empleados_data.append({
                'id': empleado.id,
                'nombre': empleado.nombre,
                'apellido': empleado.apellido,
            })
        
        return json_ok({'empleados': empleados_data})


class ObtenerTurnoExploradorView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        explorador_id = request.GET.get('explorador_id')
        
        if not fecha or not explorador_id:
            return json_error('Faltan parámetros requeridos', status=400, code='missing_params')
        
        try:
            # Obtener el tipo de solicitud desde la URL o parámetros
            tipo_solicitud_id = request.GET.get('tipo_solicitud_id')
            tipo_solicitud = None
            
            if tipo_solicitud_id:
                try:
                    tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)
                except TipoSolicitudCambio.DoesNotExist:
                    pass
            
            # Obtener el turno del explorador usando el Factory
            if tipo_solicitud:
                turno_dict = SolicitudFactory.get_turno_explorador(tipo_solicitud, explorador_id, fecha)
            else:
                # Fallback al servicio original si no hay tipo
                turno_dict = SolicitudService.get_turno_explorador(explorador_id, fecha)
            
            return json_ok({'turno': turno_dict, 'tiene_turno': turno_dict is not None})
        except Exception as e:
            logger.exception('Error en ObtenerTurnoExploradorView')
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')

@method_decorator(csrf_exempt, name='dispatch')
class ProcesarSolicitudView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            # Obtener datos del formulario
            tipo_solicitud_id = request.POST.get('tipo_solicitud_id')
            empleado_receptor_id = request.POST.get('empleado_receptor')
            fecha_solicitud = request.POST.get('fecha_solicitud')
            comentario = request.POST.get('comentarios', '')
            
            print(f"DEBUG POST: tipo_solicitud_id={tipo_solicitud_id}")
            print(f"DEBUG POST: empleado_receptor_id={empleado_receptor_id}")
            print(f"DEBUG POST: fecha_solicitud={fecha_solicitud}")
            print(f"DEBUG POST: comentario={comentario}")
            print(f"DEBUG POST: request.POST completo={dict(request.POST)}")
            
            # Validar datos requeridos según el tipo de solicitud
            if tipo_solicitud_id and empleado_receptor_id:
                # Obtener el tipo de solicitud para validar campos específicos
                try:
                    tipo_solicitud_obj = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)
                    if tipo_solicitud_obj.nombre == "CT PERMANENTE":
                        # Para CT PERMANENTE, validar fecha_inicio en lugar de fecha_solicitud
                        fecha_inicio = request.POST.get('fecha_inicio')
                        if not fecha_inicio:
                            return json_error('Todos los campos son requeridos', status=400, code='missing_fields')
                    else:
                        # Para otros tipos, validar fecha_solicitud
                        if not fecha_solicitud:
                            return json_error('Todos los campos son requeridos', status=400, code='missing_fields')
                except TipoSolicitudCambio.DoesNotExist:
                    return json_error('Tipo de solicitud no válido', status=400, code='invalid_type')
            else:
                return json_error('Todos los campos son requeridos', status=400, code='missing_fields')
            
            # Obtener objetos
            tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)  # type: ignore
            empleado_receptor = Empleado.objects.get(id=empleado_receptor_id)  # type: ignore
            empleado_solicitante = request.user.empleado
            
            # Preparar datos para el Factory
            datos_solicitud = {
                'explorador_solicitante': empleado_solicitante,
                'explorador_receptor': empleado_receptor,
                'tipo_cambio': tipo_solicitud,
                'comentario': comentario,
            }
            
            # Configurar fecha según el tipo de solicitud
            if tipo_solicitud.nombre == "CT PERMANENTE":
                fecha_inicio = request.POST.get('fecha_inicio')
                fecha_fin = request.POST.get('fecha_fin')
                
                # Para CT PERMANENTE, usar fecha_inicio como fecha_cambio_turno
                datos_solicitud.update({
                    'fecha_cambio_turno': fecha_inicio,
                    'fecha_inicio': fecha_inicio,
                    'fecha_fin': fecha_fin
                })
            else:
                # Para otros tipos, usar fecha_solicitud
                datos_solicitud['fecha_cambio_turno'] = fecha_solicitud
                
            logger.info("Datos preparados", extra={
                'tipo_solicitud': tipo_solicitud.nombre,
                'fecha_cambio_turno': datos_solicitud.get('fecha_cambio_turno'),
                'fecha_inicio': datos_solicitud.get('fecha_inicio'),
                'fecha_fin': datos_solicitud.get('fecha_fin')
            })
            
            # Register strategies if not already registered
            from .services.strategies import CambioTurnoStrategy, DobladaStrategy, CTPermanenteStrategy, DFDSStrategy
            SolicitudFactory.register_strategy("Cambio Turno", CambioTurnoStrategy)
            SolicitudFactory.register_strategy("DOBLADA", DobladaStrategy)
            SolicitudFactory.register_strategy("CT PERMANENTE", CTPermanenteStrategy)
            SolicitudFactory.register_strategy("D FDS", DFDSStrategy)
            
            # Validar la solicitud usando el Factory
            es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_solicitud, datos_solicitud)
            
            if not es_valida:
                return json_error(mensaje, status=400, code='validation_error')
            
            # Crear la solicitud usando el Factory
            logger.info("Creando solicitud usando SolicitudFactory", extra={
                'tipo_solicitud': tipo_solicitud.nombre,
                'solicitante_id': empleado_solicitante.id,
                'receptor_id': empleado_receptor.id
            })
            
            try:
                solicitud, mensaje = SolicitudFactory.crear_solicitud(tipo_solicitud, datos_solicitud)
                
                if solicitud is None:
                    return json_error(mensaje, status=400, code='creation_failed')
                
                logger.info("Solicitud creada exitosamente", extra={
                    'solicitud_id': solicitud.id,
                    'tipo_solicitud': tipo_solicitud.nombre
                })
                
            except Exception as e:
                logger.exception("Error al crear solicitud usando Factory")
                return json_error('Error al procesar la solicitud', status=500, code='internal_error')
            
            return json_ok({
                'message': 'Solicitud enviada correctamente. Se han enviado notificaciones al supervisor y al compañero.',
                'solicitud_id': solicitud.id
            }, status=201)
            
        except Exception as e:
            print(f"ERROR VISTA GENERAL: {e}")
            import traceback
            print(f"ERROR VISTA GENERAL: Traceback: {traceback.format_exc()}")
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')

class NotificacionesListView(LoginRequiredMixin, ListView):
    model = Notificacion
    template_name = 'solicitudes/notificaciones_list.html'
    context_object_name = 'notificaciones'
    
    def get_queryset(self):
        if hasattr(self.request.user, 'empleado'):
            return NotificacionService.obtener_notificaciones(self.request.user.empleado)
        return Notificacion.objects.none()

class MarcarNotificacionLeidaView(LoginRequiredMixin, View):
    def post(self, request, notificacion_id):
        if hasattr(request.user, 'empleado'):
            success = NotificacionService.marcar_como_leida(notificacion_id, request.user.empleado)
            return json_ok({'success': success})
        return json_error('No autorizado', status=403, code='forbidden')

class MisSolicitudesListView(LoginRequiredMixin, ListView):
    """
    Vista para que los empleados vean sus propias solicitudes
    """
    model = SolicitudCambio
    template_name = 'solicitudes/mis_solicitudes_list.html'
    context_object_name = 'solicitudes'
    
    def get_queryset(self):
        if hasattr(self.request.user, 'empleado'):
            return SolicitudService.get_solicitudes_usuario(self.request.user)
        return SolicitudCambio.objects.none()

class SolicitudesPendientesListView(LoginRequiredMixin, ListView):
    """
    Vista para que los supervisores vean las solicitudes pendientes de sus empleados
    """
    model = SolicitudCambio
    template_name = 'solicitudes/solicitudes_pendientes_list.html'
    context_object_name = 'solicitudes'
    
    def get_queryset(self):
        if hasattr(self.request.user, 'empleado'):
            print(f"DEBUG SOLICITUDES PENDIENTES - Usuario: {self.request.user.empleado.nombre}")
            
            # Obtener solicitudes como receptor
            solicitudes_receptor = SolicitudService.get_solicitudes_por_receptor(self.request.user.empleado)
            print(f"DEBUG SOLICITUDES PENDIENTES - Solicitudes como receptor: {solicitudes_receptor.count()}")
            
            # Obtener solicitudes como supervisor
            solicitudes_supervisor = SolicitudService.get_solicitudes_por_supervisor(self.request.user.empleado)
            print(f"DEBUG SOLICITUDES PENDIENTES - Solicitudes como supervisor: {solicitudes_supervisor.count()}")
            
            # Combinar ambas querysets (evitar duplicados) respetando flags de aprobación
            # Solo receptor y supervisor (NO solicitante)
            from django.db.models import Q
            solicitudes_combined = SolicitudCambio.objects.filter(
                (
                    Q(estado='pendiente', explorador_receptor=self.request.user.empleado, aprobado_receptor=False)
                ) |
                (
                    Q(estado='pendiente', explorador_solicitante__supervisor=self.request.user.empleado, aprobado_supervisor=False)
                )
            ).distinct().order_by('-fecha_solicitud')
            
            print(f"DEBUG SOLICITUDES PENDIENTES - Total combinado: {solicitudes_combined.count()}")
            
            # Debug detallado: Mostrar las solicitudes específicas
            print(f"DEBUG SOLICITUDES PENDIENTES - Solicitudes como receptor:")
            for s in solicitudes_receptor:
                print(f"  - ID: {s.id}, Solicitante: {s.explorador_solicitante.nombre}, Receptor: {s.explorador_receptor.nombre}, Fecha: {s.fecha_solicitud}")
            
            print(f"DEBUG SOLICITUDES PENDIENTES - Solicitudes como supervisor:")
            for s in solicitudes_supervisor:
                print(f"  - ID: {s.id}, Solicitante: {s.explorador_solicitante.nombre}, Receptor: {s.explorador_receptor.nombre}, Fecha: {s.fecha_solicitud}")
            
            # Agregar información del rol a cada solicitud
            for solicitud in solicitudes_combined:
                es_receptor = solicitud.explorador_receptor == self.request.user.empleado and not solicitud.aprobado_receptor
                es_supervisor = solicitud.explorador_solicitante.supervisor == self.request.user.empleado and not solicitud.aprobado_supervisor
                
                if es_receptor and es_supervisor:
                    solicitud.mi_rol = 'ambos'
                elif es_receptor:
                    solicitud.mi_rol = 'receptor'
                elif es_supervisor:
                    solicitud.mi_rol = 'supervisor'
            
            return solicitudes_combined
        return SolicitudCambio.objects.none()

@method_decorator(csrf_exempt, name='dispatch')
class AprobarSolicitudView(LoginRequiredMixin, View):
    """
    Vista para aprobar una solicitud por parte del supervisor
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        success, message = SolicitudService.aprobar_solicitud_supervisor(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return json_ok({'success': success, 'message': message})

@method_decorator(csrf_exempt, name='dispatch')
class AprobarSolicitudReceptorView(LoginRequiredMixin, View):
    """
    Vista para aprobar una solicitud por parte del compañero receptor
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        success, message = SolicitudService.aprobar_solicitud_receptor(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return json_ok({'success': success, 'message': message})

@method_decorator(csrf_exempt, name='dispatch')
class RechazarSolicitudView(LoginRequiredMixin, View):
    """
    Vista para rechazar una solicitud por parte del supervisor
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        success, message = SolicitudService.rechazar_solicitud_supervisor(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return json_ok({'success': success, 'message': message})

@method_decorator(csrf_exempt, name='dispatch')
class RechazarSolicitudReceptorView(LoginRequiredMixin, View):
    """
    Vista para rechazar una solicitud por parte del compañero receptor
    """
    def post(self, request, solicitud_id):
        try:
            comentario_respuesta = request.POST.get('comentario_respuesta', '')
            success, message = SolicitudService.rechazar_solicitud_receptor(
                solicitud_id, request.user.empleado, comentario_respuesta
            )
            return json_ok({'success': success, 'message': message})
        except Exception as e:
            logger.exception('Error en RechazarSolicitudReceptorView')
            return json_error('Error al rechazar la solicitud', status=500, code='internal_error')

@method_decorator(csrf_exempt, name='dispatch')
class CancelarSolicitudView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        try:
            # Verificar que el usuario sea el solicitante o tenga permisos
            solicitud = SolicitudCambio.objects.get(id=solicitud_id)
            
            # Solo el solicitante puede cancelar su propia solicitud
            if solicitud.explorador_solicitante != request.user.empleado:
                return json_error('Solo puedes cancelar tus propias solicitudes', status=403, code='forbidden')
            
            # Verificar que la solicitud esté pendiente
            if solicitud.estado != 'pendiente':
                return json_error('Solo se pueden cancelar solicitudes pendientes', status=400, code='invalid_state')
            
            # Cancelar la solicitud
            solicitud.estado = 'cancelada'
            solicitud.fecha_resolucion = timezone.now()
            solicitud.comentario = f"{solicitud.comentario or ''}\n\nCancelada por el solicitante"
            solicitud.save()
            
            # Crear notificación de cancelación
            from .services.notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_cancelacion(solicitud)
            
            return json_ok({'message': 'Solicitud cancelada correctamente'})
            
        except SolicitudCambio.DoesNotExist:
            return json_error('Solicitud no encontrada', status=404, code='not_found')
        except Exception as e:
            logger.exception('Error en CancelarSolicitudView')
            return json_error('Error al cancelar la solicitud', status=500, code='internal_error')

@method_decorator(csrf_exempt, name='dispatch')
class AprobarSolicitudAmbosView(LoginRequiredMixin, View):
    """
    Aprueba como Receptor y como Supervisor en una sola acción
    Solo disponible si el usuario es simultáneamente receptor y supervisor de la solicitud
    y la solicitud está en estado pendiente.
    """
    def post(self, request, solicitud_id):
        try:
            if not hasattr(request.user, 'empleado'):
                return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')

            solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
            empleado = request.user.empleado

            # Validar roles simultáneos
            es_receptor = solicitud.explorador_receptor == empleado
            es_supervisor = (getattr(solicitud.explorador_solicitante, 'supervisor', None) == empleado)

            if not (es_receptor and es_supervisor):
                return json_error('No tienes permisos para aprobar en ambos roles', status=403, code='forbidden')

            if solicitud.estado != 'pendiente':
                return json_error('La solicitud no está pendiente', status=400, code='invalid_state')

            # Aprobar primero como receptor si falta
            if not solicitud.aprobado_receptor:
                SolicitudService.aprobar_solicitud_receptor(solicitud_id, empleado, 'Aprobado como receptor (acción combinada)')

            # Aprobar como supervisor si falta
            if not solicitud.aprobado_supervisor:
                SolicitudService.aprobar_solicitud_supervisor(solicitud_id, empleado, 'Aprobado como supervisor (acción combinada)')

            # Aplicar los cambios usando el Factory (ya que ambos roles están aprobados)
            from .services.solicitud_factory import SolicitudFactory
            success, message = SolicitudFactory.aplicar_cambios(solicitud)
            if not success:
                logger.error(f"Error aplicando cambios en ambos roles: {message}")

            return json_ok({'message': 'Solicitud aprobada en ambos roles correctamente'})
        except Exception:
            logger.exception('Error en AprobarSolicitudAmbosView')
            return json_error('Error al aprobar en ambos roles', status=500, code='internal_error')

class NotificacionesSolicitudesView(LoginRequiredMixin, TemplateView):
    """
    Vista inteligente para mostrar notificaciones y solicitudes
    - Para todos los usuarios: muestra sus notificaciones y solicitudes
    - Para supervisores: también muestra solicitudes pendientes de aprobación
    - Para receptores: también muestra solicitudes que deben aprobar
    """
    template_name = 'solicitudes/notificaciones_solicitudes.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if hasattr(self.request.user, 'empleado'):
            empleado = self.request.user.empleado
            
            # Verificar si es supervisor
            es_supervisor = empleado.empleados_supervisados.exists()
            context['es_supervisor'] = es_supervisor
            
            # Obtener notificaciones no leídas
            notificaciones_no_leidas = NotificacionService.obtener_notificaciones_no_leidas(empleado)
            context['notificaciones_no_leidas'] = notificaciones_no_leidas
            
            # Obtener mis solicitudes
            mis_solicitudes = SolicitudService.get_solicitudes_usuario(self.request.user)
            context['mis_solicitudes'] = mis_solicitudes
            
            # Si es supervisor, obtener solicitudes pendientes
            if es_supervisor:
                solicitudes_pendientes = SolicitudService.get_solicitudes_por_supervisor(empleado)
                context['solicitudes_pendientes'] = solicitudes_pendientes
            
            # Obtener solicitudes que debe aprobar como receptor
            solicitudes_por_receptor = SolicitudService.get_solicitudes_por_receptor(empleado)
            context['solicitudes_por_receptor'] = solicitudes_por_receptor
            
            # Agregar información de estado de aprobación para cada solicitud
            for solicitud in mis_solicitudes:
                solicitud.estado_aprobacion = SolicitudService.get_estado_aprobacion_solicitud(solicitud)
            
            if es_supervisor:
                for solicitud in solicitudes_pendientes:
                    solicitud.estado_aprobacion = SolicitudService.get_estado_aprobacion_solicitud(solicitud)
            
            for solicitud in solicitudes_por_receptor:
                solicitud.estado_aprobacion = SolicitudService.get_estado_aprobacion_solicitud(solicitud)
        
        return context

# Vistas para aprobación por email (sin login requerido)
class AprobarSolicitudEmailView(View):
    """
    Vista para aprobar una solicitud por email (supervisor)
    """
    def get(self, request, solicitud_id, token):
        try:
            solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
            
            # Verificar token
            if not self._verificar_token(solicitud, token, 'supervisor'):
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'Token inválido o expirado'
                })
            
            # Verificar que el usuario actual es el supervisor
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'No se encontró supervisor para esta solicitud'
                })
            
            # Aprobar la solicitud
            success, message = SolicitudService.aprobar_solicitud_supervisor(
                solicitud_id, 
                supervisor, 
                'Aprobado por email'
            )
            
            if success:
                return render(request, 'solicitudes/aprobacion_exitosa.html', {
                    'solicitud': solicitud,
                    'tipo': 'supervisor',
                    'accion': 'aprobada'
                })
            else:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': message
                })
                
        except Exception as e:
            return render(request, 'solicitudes/error_token.html', {
                'mensaje': f'Error al procesar la solicitud: {str(e)}'
            })
    
    def _verificar_token(self, solicitud, token, tipo):
        """Verifica que el token sea válido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producción
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(token, expected_token)

class RechazarSolicitudEmailView(View):
    """
    Vista para rechazar una solicitud por email (supervisor)
    """
    def get(self, request, solicitud_id, token):
        try:
            solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
            
            # Verificar token
            if not self._verificar_token(solicitud, token, 'supervisor'):
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'Token inválido o expirado'
                })
            
            # Verificar que el usuario actual es el supervisor
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'No se encontró supervisor para esta solicitud'
                })
            
            # Rechazar la solicitud
            success, message = SolicitudService.rechazar_solicitud_supervisor(
                solicitud_id, 
                supervisor, 
                'Rechazado por email'
            )
            
            if success:
                return render(request, 'solicitudes/aprobacion_exitosa.html', {
                    'solicitud': solicitud,
                    'tipo': 'supervisor',
                    'accion': 'rechazada'
                })
            else:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': message
                })
                
        except Exception as e:
            return render(request, 'solicitudes/error_token.html', {
                'mensaje': f'Error al procesar la solicitud: {str(e)}'
            })
    
    def _verificar_token(self, solicitud, token, tipo):
        """Verifica que el token sea válido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producción
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(token, expected_token)

class AprobarSolicitudReceptorEmailView(View):
    """
    Vista para aprobar una solicitud por email (receptor)
    """
    def get(self, request, solicitud_id, token):
        try:
            solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
            
            # Verificar token
            if not self._verificar_token(solicitud, token, 'receptor'):
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'Token inválido o expirado'
                })
            
            # Aprobar la solicitud
            success, message = SolicitudService.aprobar_solicitud_receptor(
                solicitud_id, 
                solicitud.explorador_receptor, 
                'Aprobado por email'
            )
            
            if success:
                return render(request, 'solicitudes/aprobacion_exitosa.html', {
                    'solicitud': solicitud,
                    'tipo': 'receptor',
                    'accion': 'aprobada'
                })
            else:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': message
                })
                
        except Exception as e:
            return render(request, 'solicitudes/error_token.html', {
                'mensaje': f'Error al procesar la solicitud: {str(e)}'
            })
    
    def _verificar_token(self, solicitud, token, tipo):
        """Verifica que el token sea válido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producción
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(token, expected_token)

class RechazarSolicitudReceptorEmailView(View):
    """
    Vista para rechazar una solicitud por email (receptor)
    """
    def get(self, request, solicitud_id, token):
        try:
            solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
            
            # Verificar token
            if not self._verificar_token(solicitud, token, 'receptor'):
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'Token inválido o expirado'
                })
            
            # Rechazar la solicitud
            success, message = SolicitudService.rechazar_solicitud_receptor(
                solicitud_id, 
                solicitud.explorador_receptor, 
                'Rechazado por email'
            )
            
            if success:
                return render(request, 'solicitudes/aprobacion_exitosa.html', {
                    'solicitud': solicitud,
                    'tipo': 'receptor',
                    'accion': 'rechazada'
                })
            else:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': message
                })
                
        except Exception as e:
            return render(request, 'solicitudes/error_token.html', {
                'mensaje': f'Error al procesar la solicitud: {str(e)}'
            })
    
    def _verificar_token(self, solicitud, token, tipo):
        """Verifica que el token sea válido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producción
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(token, expected_token)
