from django.shortcuts import render, get_object_or_404
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from empleados.views import AdminRequiredMixin
from empleados.models import Empleado
from .models import TipoSolicitudCambio, PermisoDetalle, Notificacion, SolicitudCambio
from .services.solicitud_service import SolicitudService
from .services.permiso_service import PermisoService
from .services.notificacion_service import NotificacionService
from django.utils import timezone

# Create your views here.

class SolicitudesView(LoginRequiredMixin, TemplateView):
    template_name = 'solicitudes/list.html'

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

# CRUD de PermisoDetalle
class PermisoDetalleListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = PermisoDetalle
    template_name = 'solicitudes/permisodetalle_list.html'
    context_object_name = 'permisos_detalle'

    def get_queryset(self):
        # Usar el servicio para obtener permisos
        return PermisoService.get_permisos_pendientes()

class PermisoDetalleCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = PermisoDetalle
    template_name = 'solicitudes/permisodetalle_create.html'
    fields = ['solicitud', 'horas_solicitadas']
    success_url = '/solicitudes/permisos-detalle/'

class PermisoDetalleUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = PermisoDetalle
    template_name = 'solicitudes/permisodetalle_edit.html'
    fields = ['solicitud', 'horas_solicitadas']
    success_url = '/solicitudes/permisos-detalle/'

class PermisoDetalleDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = PermisoDetalle
    template_name = 'solicitudes/permisodetalle_confirm_delete.html'
    success_url = '/solicitudes/permisos-detalle/'

class CambioTurnoInicioView(LoginRequiredMixin, TemplateView):
    template_name = 'solicitudes/cambio_turno_inicio.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tipos_solicitud'] = SolicitudService.get_tipos_solicitud_activos()
        return context
    
class SolicitarCambioTurnoView(LoginRequiredMixin, View):
    template_name = 'solicitudes/solicitar_cambio_turno.html'

    def get(self, request, tipo_id):
        tipo_solicitud = get_object_or_404(TipoSolicitudCambio, id=tipo_id)
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.now().date(),
            'fecha_seleccionada': timezone.now().date(),
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
        }
        return render(request, self.template_name, context)


class ObtenerEmpleadosDisponiblesView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        tipo_solicitud_id = request.GET.get('tipo_solicitud_id')
        
        print(f"DEBUG: fecha={fecha}, tipo_solicitud_id={tipo_solicitud_id}")
        
        if not fecha:
            return JsonResponse({'empleados': []})
        
        # Determinar si debe filtrar por jornada contraria según el tipo de solicitud
        solo_jornada_contraria = False
        if tipo_solicitud_id:
            try:
                tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)  # type: ignore
                # Para "Cambio Turno" filtrar por jornada contraria
                # Para "Doblada" mostrar todos los empleados
                solo_jornada_contraria = "cambio" in tipo_solicitud.nombre.lower()
                print(f"DEBUG: tipo_solicitud.nombre={tipo_solicitud.nombre}, solo_jornada_contraria={solo_jornada_contraria}")
            except TipoSolicitudCambio.DoesNotExist:  # type: ignore
                pass
        
        # Obtener empleados según el tipo de solicitud
        empleados_disponibles = SolicitudService.get_empleados_disponibles(
            fecha, 
            request.user, 
            solo_jornada_contraria=solo_jornada_contraria
        )
        
        print(f"DEBUG: empleados_disponibles count={len(empleados_disponibles)}")
        
        # Convertir a formato JSON
        empleados_data = []
        for empleado in empleados_disponibles:
            empleados_data.append({
                'id': empleado.id,
                'nombre': empleado.nombre,
                'apellido': empleado.apellido,
            })
        
        return JsonResponse({'empleados': empleados_data})


class ObtenerTurnoExploradorView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        explorador_id = request.GET.get('explorador_id')
        
        if not fecha or not explorador_id:
            return JsonResponse({'error': 'Faltan parámetros requeridos'})
        
        try:
            # Obtener el turno del explorador usando el servicio actualizado
            turno_dict = SolicitudService.get_turno_explorador(explorador_id, fecha)
            # El dict ya contiene toda la info necesaria (jornada, sala, salas_competencia, etc)
            return JsonResponse({
                'turno': turno_dict,
                'tiene_turno': turno_dict is not None
            })
        except Exception as e:
            return JsonResponse({'error': f'Error al procesar la solicitud: {str(e)}'})

@method_decorator(csrf_exempt, name='dispatch')
class ProcesarSolicitudView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            # Obtener datos del formulario
            tipo_solicitud_id = request.POST.get('tipo_solicitud_id')
            empleado_receptor_id = request.POST.get('empleado_receptor')
            fecha_solicitud = request.POST.get('fecha_solicitud')
            comentario = request.POST.get('comentarios', '')
            
            # Validar datos requeridos
            if not all([tipo_solicitud_id, empleado_receptor_id, fecha_solicitud]):
                return JsonResponse({
                    'success': False,
                    'error': 'Todos los campos son requeridos'
                })
            
            # Obtener objetos
            tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)  # type: ignore
            empleado_receptor = Empleado.objects.get(id=empleado_receptor_id)  # type: ignore
            empleado_solicitante = request.user.empleado
            
            # Validar la solicitud
            es_valida, mensaje = SolicitudService.validar_solicitud_cambio(
                empleado_solicitante, empleado_receptor, fecha_solicitud
            )
            
            if not es_valida:
                return JsonResponse({
                    'success': False,
                    'error': mensaje
                })
            
            # Crear la solicitud
            solicitud = SolicitudService.crear_solicitud_cambio(
                explorador_solicitante=empleado_solicitante,
                explorador_receptor=empleado_receptor,
                tipo_cambio=tipo_solicitud,
                fecha_cambio=fecha_solicitud,
                comentario=comentario
            )
            
            return JsonResponse({
                'success': True,
                'message': 'Solicitud enviada correctamente. Se han enviado notificaciones al supervisor y al compañero.',
                'solicitud_id': solicitud.id
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'Error al procesar la solicitud: {str(e)}'
            })

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
            return JsonResponse({'success': success})
        return JsonResponse({'success': False})

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
            return SolicitudService.get_solicitudes_por_supervisor(self.request.user.empleado)
        return SolicitudCambio.objects.none()

@method_decorator(csrf_exempt, name='dispatch')
class AprobarSolicitudView(LoginRequiredMixin, View):
    """
    Vista para aprobar una solicitud
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return JsonResponse({
                'success': False,
                'error': 'Usuario no tiene empleado asociado'
            })
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        success, message = SolicitudService.aprobar_solicitud(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return JsonResponse({
            'success': success,
            'message': message
        })

@method_decorator(csrf_exempt, name='dispatch')
class RechazarSolicitudView(LoginRequiredMixin, View):
    """
    Vista para rechazar una solicitud
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return JsonResponse({
                'success': False,
                'error': 'Usuario no tiene empleado asociado'
            })
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        success, message = SolicitudService.rechazar_solicitud(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return JsonResponse({
            'success': success,
            'message': message
        })
