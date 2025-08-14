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
import hashlib
import hmac

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
            # Usar la misma lógica que en SolicitudesPendientesListView para evitar duplicados
            from django.db.models import Q
            solicitudes_pendientes_count = SolicitudCambio.objects.filter(
                Q(estado='pendiente', explorador_receptor=self.request.user.empleado) |
                Q(estado='pendiente', explorador_solicitante__supervisor=self.request.user.empleado)
            ).distinct().count()
            
            # Debug: Imprimir información para entender el conteo
            print(f"DEBUG CONTADOR - Usuario: {self.request.user.empleado.nombre}")
            print(f"DEBUG CONTADOR - Total pendientes (con distinct): {solicitudes_pendientes_count}")
            
            # Debug detallado: Mostrar las solicitudes específicas
            solicitudes_combined = SolicitudCambio.objects.filter(
                Q(estado='pendiente', explorador_receptor=self.request.user.empleado) |
                Q(estado='pendiente', explorador_solicitante__supervisor=self.request.user.empleado)
            ).distinct()
            
            print(f"DEBUG DETALLADO - Solicitudes combinadas:")
            for s in solicitudes_combined:
                rol = "AMBOS" if (s.explorador_receptor == self.request.user.empleado and 
                                s.explorador_solicitante.supervisor == self.request.user.empleado) else \
                     "RECEPTOR" if s.explorador_receptor == self.request.user.empleado else "SUPERVISOR"
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
            
            print(f"DEBUG POST: tipo_solicitud_id={tipo_solicitud_id}")
            print(f"DEBUG POST: empleado_receptor_id={empleado_receptor_id}")
            print(f"DEBUG POST: fecha_solicitud={fecha_solicitud}")
            print(f"DEBUG POST: comentario={comentario}")
            print(f"DEBUG POST: request.POST completo={dict(request.POST)}")
            
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
            print(f"DEBUG VISTA: Llamando a SolicitudService.crear_solicitud_cambio")
            print(f"DEBUG VISTA: explorador_solicitante={empleado_solicitante.nombre}")
            print(f"DEBUG VISTA: explorador_receptor={empleado_receptor.nombre}")
            print(f"DEBUG VISTA: tipo_cambio={tipo_solicitud.nombre}")
            print(f"DEBUG VISTA: fecha_cambio_turno={fecha_solicitud}")
            
            try:
                resultado = SolicitudService.crear_solicitud_cambio(
                    explorador_solicitante=empleado_solicitante,
                    explorador_receptor=empleado_receptor,
                    tipo_cambio=tipo_solicitud,
                    comentario=comentario,
                    fecha_cambio_turno=fecha_solicitud
                )
                
                # El método ahora retorna (solicitud, mensaje)
                if isinstance(resultado, tuple):
                    solicitud, mensaje = resultado
                else:
                    solicitud = resultado
                    mensaje = "Solicitud creada correctamente"
                
                if solicitud is None:
                    return JsonResponse({
                        'success': False,
                        'error': mensaje
                    })
                
                print(f"DEBUG VISTA: Solicitud creada exitosamente con ID: {solicitud.id}")
                print(f"DEBUG VISTA: Mensaje: {mensaje}")
                
            except Exception as e:
                print(f"ERROR VISTA: Error al crear solicitud: {e}")
                import traceback
                print(f"ERROR VISTA: Traceback: {traceback.format_exc()}")
                raise
            
            return JsonResponse({
                'success': True,
                'message': 'Solicitud enviada correctamente. Se han enviado notificaciones al supervisor y al compañero.',
                'solicitud_id': solicitud.id
            })
            
        except Exception as e:
            print(f"ERROR VISTA GENERAL: {e}")
            import traceback
            print(f"ERROR VISTA GENERAL: Traceback: {traceback.format_exc()}")
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
            print(f"DEBUG SOLICITUDES PENDIENTES - Usuario: {self.request.user.empleado.nombre}")
            
            # Obtener solicitudes como receptor
            solicitudes_receptor = SolicitudService.get_solicitudes_por_receptor(self.request.user.empleado)
            print(f"DEBUG SOLICITUDES PENDIENTES - Solicitudes como receptor: {solicitudes_receptor.count()}")
            
            # Obtener solicitudes como supervisor
            solicitudes_supervisor = SolicitudService.get_solicitudes_por_supervisor(self.request.user.empleado)
            print(f"DEBUG SOLICITUDES PENDIENTES - Solicitudes como supervisor: {solicitudes_supervisor.count()}")
            
            # Combinar ambas querysets (evitar duplicados)
            from django.db.models import Q
            solicitudes_combined = SolicitudCambio.objects.filter(
                Q(estado='pendiente', explorador_receptor=self.request.user.empleado) |
                Q(estado='pendiente', explorador_solicitante__supervisor=self.request.user.empleado)
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
                if solicitud.explorador_receptor == self.request.user.empleado:
                    solicitud.mi_rol = 'receptor'
                elif solicitud.explorador_solicitante.supervisor == self.request.user.empleado:
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
            return JsonResponse({
                'success': False,
                'error': 'Usuario no tiene empleado asociado'
            })
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        success, message = SolicitudService.aprobar_solicitud_supervisor(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return JsonResponse({
            'success': success,
            'message': message
        })

@method_decorator(csrf_exempt, name='dispatch')
class AprobarSolicitudReceptorView(LoginRequiredMixin, View):
    """
    Vista para aprobar una solicitud por parte del compañero receptor
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return JsonResponse({
                'success': False,
                'error': 'Usuario no tiene empleado asociado'
            })
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        success, message = SolicitudService.aprobar_solicitud_receptor(
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
    Vista para rechazar una solicitud por parte del supervisor
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return JsonResponse({
                'success': False,
                'error': 'Usuario no tiene empleado asociado'
            })
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        success, message = SolicitudService.rechazar_solicitud_supervisor(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return JsonResponse({
            'success': success,
            'message': message
        })

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
            return JsonResponse({'success': success, 'message': message})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})

@method_decorator(csrf_exempt, name='dispatch')
class CancelarSolicitudView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        try:
            # Verificar que el usuario sea el solicitante o tenga permisos
            solicitud = SolicitudCambio.objects.get(id=solicitud_id)
            
            # Solo el solicitante puede cancelar su propia solicitud
            if solicitud.explorador_solicitante != request.user.empleado:
                return JsonResponse({
                    'success': False, 
                    'message': 'Solo puedes cancelar tus propias solicitudes'
                })
            
            # Verificar que la solicitud esté pendiente
            if solicitud.estado != 'pendiente':
                return JsonResponse({
                    'success': False, 
                    'message': 'Solo se pueden cancelar solicitudes pendientes'
                })
            
            # Cancelar la solicitud
            solicitud.estado = 'cancelada'
            solicitud.fecha_resolucion = timezone.now()
            solicitud.comentario = f"{solicitud.comentario or ''}\n\nCancelada por el solicitante"
            solicitud.save()
            
            # Crear notificación de cancelación
            from .services.notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_cancelacion(solicitud)
            
            return JsonResponse({
                'success': True, 
                'message': 'Solicitud cancelada correctamente'
            })
            
        except SolicitudCambio.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'message': 'Solicitud no encontrada'
            })
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': f'Error al cancelar la solicitud: {str(e)}'
            })

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
