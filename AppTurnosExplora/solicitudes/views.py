from django.shortcuts import render, get_object_or_404
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from core.mixins import AdminRequiredMixin
from core.services import get_turno_service
from empleados.models import Empleado
from .models import TipoSolicitudCambio, Notificacion, SolicitudCambio, CambioPermanenteDetalle
from .services.solicitud_service import SolicitudService
from .services.solicitud_factory import SolicitudFactory
from .services.permiso_service import PermisoService
from .services.notificacion_service import NotificacionService
from django.utils import timezone
import hashlib
import hmac
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.utils.json_responses import json_ok, json_error

# Create your views here.

class SolicitudesView(LoginRequiredMixin, TemplateView):
    template_name = 'solicitudes/list.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated and hasattr(self.request.user, 'empleado'):
            from .services.solicitud_context_service import SolicitudContextService
            context_data = SolicitudContextService.get_context_data_for_solicitudes_view(
                self.request.user.empleado
            )
            context.update(context_data)
        return context

# CRUD de TipoSolicitudCambio
class TipoSolicitudCambioListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_list.html'
    context_object_name = 'tipos_solicitud'

class TipoSolicitudCambioCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_create.html'
    fields = ['nombre', 'codigo_estrategia', 'activo', 'genera_deuda']
    success_url = '/solicitudes/tipos-solicitud/'

class TipoSolicitudCambioUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_edit.html'
    fields = ['nombre', 'codigo_estrategia', 'activo', 'genera_deuda']
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
        from .services.solicitud_consulta_service import SolicitudConsultaService
        context['tipos_solicitud'] = SolicitudConsultaService.get_tipos_solicitud_activos()
        return context
    
class SolicitarCambioTurnoView(LoginRequiredMixin, View):
    def get(self, request, tipo_id):
        tipo_solicitud = get_object_or_404(TipoSolicitudCambio, id=tipo_id)
        
        # Determinar qué template usar según el tipo de solicitud
        if tipo_solicitud.nombre == "CT PERMANENTE":
            return self._render_ct_permanente(request, tipo_solicitud)
        elif tipo_solicitud.nombre == "DOBLADA":
            return self._render_doblada(request, tipo_solicitud)
        else:
            return self._render_cambio_turno_normal(request, tipo_solicitud)
    
    def _render_ct_permanente(self, request, tipo_solicitud):
        """Renderizar formulario especÃ­fico para CT PERMANENTE"""
        # No establecer fecha inicial por defecto - el usuario debe seleccionarla
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.now().date() + timezone.timedelta(days=1),
            'fecha_inicio': None,  # Sin fecha inicial - usuario debe seleccionar
            'fecha_fin': None,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
            'comentarios': '',
        }
        return render(request, 'solicitudes/solicitar_ct_permanente.html', context)
    
    def _render_doblada(self, request, tipo_solicitud):
        """Renderizar formulario específico para DOBLADA"""
        # No establecer fecha inicial - el usuario debe seleccionarla
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.now().date(),
            'fecha_seleccionada': None,  # Sin fecha inicial - usuario debe seleccionar
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
        }
        return render(request, 'solicitudes/solicitar_doblada.html', context)
    
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
        
        # Nuevos parámetros para CT PERMANENTE
        fecha_fin = request.GET.get('fecha_fin')
        dias_seleccionados_json = request.GET.get('dias_seleccionados', '{}')
        
        # Logging mejorado para diagnóstico
        logger.info("ObtenerEmpleadosDisponiblesView - Parámetros recibidos", extra={
            'fecha': fecha,
            'tipo_solicitud_id': tipo_solicitud_id,
            'fecha_fin': fecha_fin,
            'usuario_id': request.user.id if request.user.is_authenticated else None,
            'empleado_id': request.user.empleado.id if hasattr(request.user, 'empleado') else None
        })
        
        if not fecha:
            logger.warning("ObtenerEmpleadosDisponiblesView - Fecha no proporcionada")
            return json_ok({'empleados': []})
        
        # Obtener el tipo de solicitud
        tipo_solicitud = None
        if tipo_solicitud_id:
            try:
                tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)  # type: ignore
                logger.info("ObtenerEmpleadosDisponiblesView - Tipo de solicitud obtenido", extra={
                    'tipo_solicitud': tipo_solicitud.nombre,
                    'tipo_id': tipo_solicitud_id,
                    'codigo_estrategia': tipo_solicitud.codigo_estrategia,
                    'activo': tipo_solicitud.activo
                })
                print(f"DEBUG: Tipo de solicitud encontrado - ID: {tipo_solicitud.id}, Nombre: {tipo_solicitud.nombre}, Activo: {tipo_solicitud.activo}")
            except TipoSolicitudCambio.DoesNotExist:  # type: ignore
                logger.warning("ObtenerEmpleadosDisponiblesView - Tipo de solicitud no encontrado", extra={
                    'tipo_id': tipo_solicitud_id
                })
                print(f"DEBUG: Tipo de solicitud NO encontrado - ID: {tipo_solicitud_id}")
        else:
            logger.warning("ObtenerEmpleadosDisponiblesView - tipo_solicitud_id no proporcionado")
            print("DEBUG: tipo_solicitud_id no proporcionado")
        
        # Verificar si el usuario tiene empleado asociado
        if not hasattr(request.user, 'empleado'):
            return json_ok({'empleados': []})
            
        # Parsear dias_seleccionados
        import json
        try:
            dias_seleccionados = json.loads(dias_seleccionados_json)
        except json.JSONDecodeError:
            dias_seleccionados = {}
        
        # Cache para empleados disponibles usando CacheService
        # INCLUIR usuario actual en cache key para evitar contaminación cruzada
        from core.services.cache_service import CacheService
        
        # Clave de caché extendida para incluir parámetros de rango
        cache_params = f"{fecha}_{tipo_solicitud_id or 'default'}_{request.user.empleado.id}"
        if fecha_fin:
            import hashlib
            dias_hash = hashlib.md5(dias_seleccionados_json.encode()).hexdigest()
            cache_params += f"_{fecha_fin}_{dias_hash}"
            
        cache_key = f"empleados_disp_v4_{cache_params}"  # Incrementado a v4 para invalidar caché anterior
        
        def obtener_empleados():
            # Obtener empleados según el tipo de solicitud usando el Factory
            try:
                empleados = SolicitudFactory.get_empleados_disponibles(
                    tipo_solicitud, 
                    fecha, 
                    request.user.empleado,
                    fecha_fin=fecha_fin,
                    dias_seleccionados=dias_seleccionados
                )
                logger.info("ObtenerEmpleadosDisponiblesView - Empleados obtenidos desde Factory", extra={
                    'count': len(empleados) if empleados else 0,
                    'tipo_solicitud': tipo_solicitud.nombre if tipo_solicitud else 'None',
                    'tipo_id': tipo_solicitud_id
                })
                return empleados
            except Exception as e:
                logger.error("ObtenerEmpleadosDisponiblesView - Error obteniendo empleados", extra={
                    'error': str(e),
                    'tipo_solicitud': tipo_solicitud.nombre if tipo_solicitud else 'None'
                }, exc_info=True)
                return []
        
        from core.services.cache_service import CACHE_TTL_MEDIUM
        
        empleados_disponibles = CacheService.get_or_set(
            cache_key,
            obtener_empleados,
            ttl=CACHE_TTL_MEDIUM
        )
        
        logger.info("ObtenerEmpleadosDisponiblesView - Empleados disponibles finales", extra={
            'count': len(empleados_disponibles) if empleados_disponibles else 0,
            'tipo_solicitud': tipo_solicitud.nombre if tipo_solicitud else 'None',
            'cache_key': cache_key
        })
        
        # Convertir a formato JSON con metadatos extendidos
        empleados_data = []
        
        # Verificar que empleados_disponibles sea iterable
        if not empleados_disponibles:
            logger.warning("ObtenerEmpleadosDisponiblesView - empleados_disponibles es None o vacío")
            empleados_disponibles = []
        elif not hasattr(empleados_disponibles, '__iter__'):
            logger.error("ObtenerEmpleadosDisponiblesView - empleados_disponibles no es iterable", extra={
                'tipo': type(empleados_disponibles).__name__
            })
            empleados_disponibles = []
        
        for empleado in empleados_disponibles:
            try:
                data = {
                    'id': empleado.id,
                    'nombre': empleado.nombre,
                    'apellido': empleado.apellido,
                }
                
                # Agregar metadatos de compatibilidad si existen (CT Permanente Best Match)
                if hasattr(empleado, 'compatibilidad_percent'):
                    data['compatibilidad_percent'] = empleado.compatibilidad_percent
                    data['dias_compatibles'] = getattr(empleado, 'dias_compatibles', [])
                    data['dias_incompatibles'] = getattr(empleado, 'dias_incompatibles', [])
                    data['total_dias_rango'] = getattr(empleado, 'total_dias_rango', 0)
                    
                empleados_data.append(data)
            except Exception as e:
                logger.error("ObtenerEmpleadosDisponiblesView - Error serializando empleado", extra={
                    'empleado_id': getattr(empleado, 'id', 'N/A'),
                    'error': str(e)
                }, exc_info=True)
        
        logger.info("ObtenerEmpleadosDisponiblesView - Respuesta JSON preparada", extra={
            'empleados_count': len(empleados_data),
            'tipo_solicitud': tipo_solicitud.nombre if tipo_solicitud else 'None'
        })
        
        return json_ok({'empleados': empleados_data})


class PrevisualizarCTPermanenteView(LoginRequiredMixin, View):
    """
    Endpoint de previsualización para CT PERMANENTE.
    Usa la misma lógica de negocio del backend para que la vista previa
    coincida exactamente con las fechas que se aplicarán.
    """

    def get(self, request):
        from datetime import datetime, timedelta
        import json
        from django.core.exceptions import ValidationError
        from empleados.models import Empleado
        from .services.ct_permanente_helper import (
            _es_festivo,
            _es_mantenimiento,
            _es_temporada,
            _es_dia_descanso,
            _razon_principal_ct_permanente,
        )
        from .services.solicitud_validator import SolicitudValidator  # type: ignore

        fecha_inicio_str = request.GET.get('fecha_inicio')
        fecha_fin_str = request.GET.get('fecha_fin')
        dias_seleccionados_json = request.GET.get('dias_seleccionados', '{}')
        empleado_receptor_id = request.GET.get('empleado_receptor_id')

        if not fecha_inicio_str or not fecha_fin_str:
            return json_error(
                'Faltan parámetros de fecha_inicio o fecha_fin',
                status=400,
                code='missing_params',
            )

        try:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
        except ValueError:
            return json_error(
                'Formato de fecha inválido. Use YYYY-MM-DD.',
                status=400,
                code='invalid_date',
            )

        # Validar que el usuario tenga empleado asociado
        if not hasattr(request.user, 'empleado'):
            return json_error(
                'Usuario sin empleado asociado',
                status=400,
                code='no_empleado',
            )

        solicitante: Empleado = request.user.empleado  # type: ignore

        # Receptor es opcional en la previsualización (antes de escoger compañero)
        receptor: Empleado | None = None  # type: ignore
        if empleado_receptor_id:
            try:
                receptor = Empleado.objects.get(id=empleado_receptor_id)
            except Empleado.DoesNotExist:
                receptor = None

        # Parsear días seleccionados
        try:
            dias_seleccionados = json.loads(dias_seleccionados_json) if dias_seleccionados_json else {}
        except json.JSONDecodeError:
            dias_seleccionados = {}

        try:
            # Validaciones básicas (mismas que al guardar)
            SolicitudValidator.validar_fechas_cambio_permanente(fecha_inicio, fecha_fin)

            if dias_seleccionados:
                SolicitudValidator.validar_dias_seleccionados_permanente(
                    fecha_inicio, fecha_fin, dias_seleccionados
                )

            # Jornada contraria en rango solo si hay receptor
            if receptor:
                fechas_especificas = dias_seleccionados.get('fechas_especificas', [])
                if not fechas_especificas:
                    SolicitudValidator.validar_jornada_contraria_rango_permanente(
                        solicitante,
                        receptor,
                        fecha_inicio,
                        fecha_fin,
                        dias_seleccionados if dias_seleccionados else None,
                    )

            # Generar fechas candidatas
            fechas_candidatas = []

            if dias_seleccionados:
                fechas_especificas = dias_seleccionados.get('fechas_especificas', [])
                dias_semana = dias_seleccionados.get('dias_semana', [])

                if fechas_especificas:
                    for fecha_str in fechas_especificas:
                        try:
                            if isinstance(fecha_str, str):
                                fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                            else:
                                fecha_obj = fecha_str
                            if fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                                fechas_candidatas.append(fecha_obj)
                        except (ValueError, TypeError):
                            continue
                elif dias_semana:
                    dias_semana_int = [int(d) for d in dias_semana]
                    fecha_actual = fecha_inicio
                    while fecha_actual <= fecha_fin:
                        weekday = fecha_actual.weekday()
                        if weekday in dias_semana_int and weekday < 5:
                            fechas_candidatas.append(fecha_actual)
                        fecha_actual += timedelta(days=1)
            else:
                # Rango completo lunes-viernes
                fecha_actual = fecha_inicio
                while fecha_actual <= fecha_fin:
                    if fecha_actual.weekday() < 5:
                        fechas_candidatas.append(fecha_actual)
                    fecha_actual += timedelta(days=1)

            # Filtrar fechas aplicables / excluidas usando la misma lógica del helper
            fechas_aplicables = []
            fechas_excluidas = []

            # Incluir fines de semana en el set evaluado para reportarlos en excluidas (transparencia),
            # sin alterar que los aplicables sean solo lunes-viernes.
            fecha_actual = fecha_inicio
            while fecha_actual <= fecha_fin:
                if fecha_actual.weekday() in (5, 6):
                    fechas_candidatas.append(fecha_actual)
                fecha_actual += timedelta(days=1)

            for fecha_dia in sorted(set(fechas_candidatas)):
                razones_exclusion = []

                if fecha_dia.weekday() in (5, 6):
                    razones_exclusion.append('Fines de semana')
                if _es_festivo(fecha_dia):
                    razones_exclusion.append('Festivo')
                if _es_mantenimiento(fecha_dia):
                    razones_exclusion.append('Mantenimiento')
                if _es_temporada(fecha_dia):
                    razones_exclusion.append('Temporada')
                if _es_dia_descanso(solicitante, fecha_dia):
                    razones_exclusion.append('Descanso Solicitante')
                if receptor and _es_dia_descanso(receptor, fecha_dia):
                    razones_exclusion.append('Descanso Receptor')

                if razones_exclusion:
                    fechas_excluidas.append(
                        {
                            'fecha': fecha_dia.strftime('%Y-%m-%d'),
                            'razon': _razon_principal_ct_permanente(razones_exclusion),
                        }
                    )
                else:
                    fechas_aplicables.append(fecha_dia.strftime('%Y-%m-%d'))

            if not fechas_aplicables:
                raise ValidationError(
                    'No se encontraron días válidos en el rango seleccionado. '
                    'Todos los días son festivos, de mantenimiento, temporada, o días de descanso.'
                )

            # Resumen informativo del rango (UX): siempre mostrar fines de semana en el rango
            total_dias_rango = (fecha_fin - fecha_inicio).days + 1
            total_fines_semana_rango = 0
            fecha_actual = fecha_inicio
            while fecha_actual <= fecha_fin:
                if fecha_actual.weekday() in (5, 6):
                    total_fines_semana_rango += 1
                fecha_actual += timedelta(days=1)

            return json_ok(
                {
                    'success': True,
                    'fechas': {
                        'aplicables': fechas_aplicables,
                        'excluidas': fechas_excluidas,
                        'total_aplicables': len(fechas_aplicables),
                        'total_excluidas': len(fechas_excluidas),
                        'resumen': {
                            'total_dias_rango': total_dias_rango,
                            'fines_de_semana_en_rango': total_fines_semana_rango,
                            'prioridad': 'Mantenimiento > Festivo > Temporada > Descanso Solicitante > Descanso Receptor > Fines de semana',
                        },
                    },
                }
            )

        except ValidationError as e:
            return json_ok(
                {
                    'success': False,
                    'message': str(e),
                    'fechas': {
                        'aplicables': [],
                        'excluidas': [],
                        'total_aplicables': 0,
                        'total_excluidas': 0,
                    },
                }
            )
        except Exception as e:  # pragma: no cover
            logger.exception('Error en PrevisualizarCTPermanenteView', extra={'error': str(e)})
            return json_error(
                'Error interno al previsualizar el cambio permanente.',
                status=500,
                code='internal_error',
            )


class ObtenerTurnoExploradorView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        explorador_id = request.GET.get('explorador_id')
        jornada_base = request.GET.get('jornada_base', 'false').lower() == 'true'
        
        if not fecha or not explorador_id:
            return json_error('Faltan parÃ¡metros requeridos', status=400, code='missing_params')
        
        try:
            # Si se solicita jornada base, obtener directamente de AsignarJornadaExplorador
            if jornada_base:
                from turnos.models import AsignarJornadaExplorador
                from datetime import datetime
                from empleados.models import Empleado
                
                fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
                explorador = Empleado.objects.get(id=explorador_id)
                
                # Obtener jornada base (sin considerar Turnos)
                asignacion_jornada = AsignarJornadaExplorador.objects.select_related('jornada').filter(
                    explorador=explorador,
                    fecha_inicio__lte=fecha_obj
                ).order_by('-fecha_inicio').first()
                
                if asignacion_jornada and asignacion_jornada.jornada:
                    jornada = asignacion_jornada.jornada
                    # Obtener salas de competencia
                    from turnos.models import CompetenciaEmpleado
                    competencias = CompetenciaEmpleado.objects.filter(empleado=explorador).select_related('sala')
                    salas_competencia = [
                        {'id': c.sala.id, 'nombre': c.sala.nombre} for c in competencias
                    ]
                    
                    turno_dict = {
                        'id': None,
                        'jornada': jornada.nombre,
                        'sala': None,
                        'sala_id': None,
                        'hora_inicio': jornada.hora_inicio.strftime('%H:%M') if jornada.hora_inicio else None,
                        'hora_fin': jornada.hora_fin.strftime('%H:%M') if jornada.hora_fin else None,
                        'es_turno_virtual': True,
                        'tipo_sala': 'competencia',
                        'salas_competencia': salas_competencia,
                        'es_jornada_base': True
                    }
                    return json_ok({'turno': turno_dict, 'tiene_turno': True})
                else:
                    return json_ok({'turno': None, 'tiene_turno': False})
            
            # Obtener el tipo de solicitud desde la URL o parÃ¡metros
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
                turno_service = get_turno_service()
                turno_dict = turno_service.get_turno_explorador(explorador_id, fecha)
            
            # CORRECCIÓN: Detectar si el explorador tiene doblada (AM + PM) en esta fecha
            from turnos.models import Turno
            from datetime import datetime
            
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            turnos_en_fecha = Turno.objects.filter(
                explorador_id=explorador_id,
                fecha=fecha_obj
            ).select_related('jornada')
            
            turnos_list = [t.jornada.nombre for t in turnos_en_fecha if t.jornada]
            es_doblada = 'AM' in turnos_list and 'PM' in turnos_list
            
            response_data = {
                'turno': turno_dict,
                'tiene_turno': turno_dict is not None,
                'es_doblada': es_doblada,
                'jornadas': turnos_list if turnos_list else ([turno_dict['jornada']] if turno_dict and 'jornada' in turno_dict else [])
            }
            
            return json_ok(response_data)
        except Exception as e:
            logger.exception('Error en ObtenerTurnoExploradorView')
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')


class VerificarCoincidenciaJornadasView(LoginRequiredMixin, View):
    """
    Endpoint para validar en tiempo real si hay coincidencia de jornadas en fecha de pago.
    Útil para DOBLADA para verificar el caso crítico antes de enviar la solicitud.
    
    Parámetros:
    - deudor_id: ID del explorador deudor (solicitante)
    - acreedor_id: ID del explorador acreedor (receptor)
    - fecha_pago: Fecha de pago en formato YYYY-MM-DD
    """
    def get(self, request):
        deudor_id = request.GET.get('deudor_id')
        acreedor_id = request.GET.get('acreedor_id')
        fecha_pago = request.GET.get('fecha_pago')
        
        if not all([deudor_id, acreedor_id, fecha_pago]):
            return json_error('Faltan parámetros requeridos (deudor_id, acreedor_id, fecha_pago)', 
                            status=400, code='missing_params')
        
        try:
            from empleados.models import Empleado
            from solicitudes.services.solicitud_validator import SolicitudValidator
            
            deudor = Empleado.objects.get(id=deudor_id)
            acreedor = Empleado.objects.get(id=acreedor_id)
            
            # Validar coincidencia de jornadas
            resultado = SolicitudValidator.validar_coincidencia_jornadas_pago(
                deudor,
                acreedor,
                fecha_pago
            )
            
            # Construir respuesta
            respuesta = {
                'coinciden': resultado['coinciden'],
                'jornada_comun': resultado.get('jornada_comun'),
                'requiere_cambio_turno': resultado.get('requiere_cambio_turno', False)
            }
            
            # Agregar mensaje explicativo
            if resultado['requiere_cambio_turno']:
                respuesta['mensaje'] = (
                    f"No se puede pagar trabajando dos veces la misma jornada ({resultado.get('jornada_comun', '')}). "
                    "Debes primero realizar un cambio de turno sencillo para tener jornada contraria en la fecha de pago."
                )
                respuesta['url_redireccion'] = f'/solicitudes/cambio-turno/solicitar/?tipo_id=1&fecha_solicitud={fecha_pago}'
            elif resultado['coinciden']:
                respuesta['mensaje'] = f"Ambos exploradores tienen la misma jornada ({resultado.get('jornada_comun', '')}) en la fecha de pago."
            else:
                respuesta['mensaje'] = 'Las jornadas son contrarias. Puedes proceder con la doblada.'
            
            return json_ok(respuesta)
            
        except Empleado.DoesNotExist:
            return json_error('Empleado no encontrado', status=404, code='empleado_not_found')
        except Exception as e:
            logger.exception('Error en VerificarCoincidenciaJornadasView')
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')


class ObtenerJornadasRangoView(LoginRequiredMixin, View):
    """
    Endpoint para obtener jornadas día a día de un explorador en un rango de fechas.
    Útil para CT PERMANENTE para mostrar desglose de jornadas en el rango.
    """
    def get(self, request):
        explorador_id = request.GET.get('explorador_id')
        fecha_inicio = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')
        dias_seleccionados_json = request.GET.get('dias_seleccionados', '{}')
        
        if not all([explorador_id, fecha_inicio, fecha_fin]):
            return json_error('Faltan parámetros requeridos (explorador_id, fecha_inicio, fecha_fin)', 
                            status=400, code='missing_params')
        
        try:
            from datetime import datetime, date, timedelta
            from turnos.services.jornada_service import JornadaService
            import json
            
            fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            
            # Parsear días seleccionados
            try:
                dias_seleccionados = json.loads(dias_seleccionados_json) if dias_seleccionados_json else {}
            except json.JSONDecodeError:
                dias_seleccionados = {}
            
            # Generar fechas válidas del rango (similar a CTPermanenteStrategy)
            fechas_validas = []
            dias_semana_list = dias_seleccionados.get('dias_semana', [])
            
            if dias_semana_list:
                # Solo días de semana seleccionados
                fecha_actual = fecha_inicio_obj
                while fecha_actual <= fecha_fin_obj:
                    # weekday(): 0=lunes, 6=domingo
                    dia_semana = fecha_actual.weekday()
                    # Convertir a formato del backend (0=lunes, 4=viernes)
                    if dia_semana < 5 and dia_semana in dias_semana_list:  # Solo lunes-viernes
                        fechas_validas.append(fecha_actual)
                    fecha_actual += timedelta(days=1)
            else:
                # Todos los días hábiles del rango
                fecha_actual = fecha_inicio_obj
                while fecha_actual <= fecha_fin_obj:
                    if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                        fechas_validas.append(fecha_actual)
                    fecha_actual += timedelta(days=1)
            
            # Obtener jornada para cada fecha
            from django.utils import formats
            dias_semana_es = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            
            jornadas_por_dia = []
            for fecha_obj in fechas_validas:
                jornada = JornadaService.get_jornada_explorador_fecha(explorador_id, fecha_obj)
                dia_semana_num = fecha_obj.weekday()
                jornadas_por_dia.append({
                    'fecha': fecha_obj.strftime('%Y-%m-%d'),
                    'fecha_formateada': fecha_obj.strftime('%d/%m/%Y'),
                    'dia_semana': dias_semana_es[dia_semana_num] if dia_semana_num < len(dias_semana_es) else fecha_obj.strftime('%A'),
                    'jornada': jornada.nombre if jornada else None,
                    'jornada_id': jornada.id if jornada else None
                })
            
            # Calcular resumen
            resumen = {
                'total_dias': len(jornadas_por_dia),
                'dias_am': len([j for j in jornadas_por_dia if j['jornada'] == 'AM']),
                'dias_pm': len([j for j in jornadas_por_dia if j['jornada'] == 'PM']),
                'dias_sin_jornada': len([j for j in jornadas_por_dia if j['jornada'] is None])
            }
            
            return json_ok({
                'jornadas': jornadas_por_dia,
                'resumen': resumen
            })
            
        except Exception as e:
            logger.exception('Error en ObtenerJornadasRangoView')
            return json_error(f'Error al procesar la solicitud: {str(e)}', status=500, code='internal_error')


class ObtenerCambioAprobadoView(LoginRequiredMixin, View):
    """
    FASE 2.5: Endpoint para verificar si el usuario ya tiene un cambio aprobado para una fecha.
    Devuelve informaciÃ³n sobre la solicitud que creÃ³ el turno si existe.
    """
    def get(self, request):
        fecha = request.GET.get('fecha')
        
        if not fecha:
            return json_error('Falta el parÃ¡metro fecha', status=400, code='missing_fecha')
        
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=400, code='no_empleado')
        
        try:
            from datetime import datetime
            from django.db.models import Q
            from turnos.models import Turno
            
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            empleado = request.user.empleado
            
            # Buscar si existe un Turno para este empleado y fecha
            turno = Turno.objects.filter(
                explorador=empleado,
                fecha=fecha_obj
            ).first()
            
            if not turno:
                return json_ok({
                    'tiene_cambio_aprobado': False,
                    'mensaje': None,
                    'informacion_cambio': None
                })
            
            # Si existe turno, buscar la solicitud que lo creÃ³
            solicitud = SolicitudCambio.objects.filter(
                Q(turno_origen=turno) | Q(turno_destino=turno),
                estado='aprobada'
            ).order_by('-fecha_resolucion').select_related(
                'explorador_solicitante',
                'explorador_receptor'
            ).first()
            
            if solicitud:
                # Determinar si el empleado es el solicitante o receptor
                es_solicitante = solicitud.explorador_solicitante.id == empleado.id
                companero = solicitud.explorador_receptor if es_solicitante else solicitud.explorador_solicitante
                
                informacion_cambio = {
                    'solicitud_id': solicitud.id,
                    'jornada_actual': turno.jornada.nombre if turno.jornada else 'N/A',
                    'companero_nombre': f"{companero.nombre} {companero.apellido}",
                    'fecha_aprobacion': solicitud.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_resolucion else 'N/A',
                    'es_solicitante': es_solicitante
                }
                
                mensaje = (
                    f"Ya tienes un cambio aprobado para esta fecha. "
                    f"Tu jornada actual es {turno.jornada.nombre} (intercambio con {companero.nombre} {companero.apellido}). "
                    f"Este nuevo cambio lo reemplazarÃ¡."
                )
                
                return json_ok({
                    'tiene_cambio_aprobado': True,
                    'mensaje': mensaje,
                    'informacion_cambio': informacion_cambio
                })
            else:
                # Hay turno pero no se encontrÃ³ la solicitud (caso raro)
                return json_ok({
                    'tiene_cambio_aprobado': True,
                    'mensaje': f"Ya tienes un turno asignado para esta fecha (jornada: {turno.jornada.nombre if turno.jornada else 'N/A'}). Este nuevo cambio lo reemplazarÃ¡.",
                    'informacion_cambio': {
                        'jornada_actual': turno.jornada.nombre if turno.jornada else 'N/A',
                        'solicitud_id': None
                    }
                })
                
        except Exception as e:
            logger.exception('Error en ObtenerCambioAprobadoView')
            return json_error('Error al verificar cambio aprobado', status=500, code='internal_error')

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
            
            # Validar datos requeridos segÃºn el tipo de solicitud
            if not tipo_solicitud_id:
                return json_error('El tipo de solicitud es requerido', status=400, code='missing_fields')
            
            # Obtener el tipo de solicitud para validar campos especÃ­ficos
            try:
                tipo_solicitud_obj = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)
                tipo_nombre = tipo_solicitud_obj.nombre
            except TipoSolicitudCambio.DoesNotExist:
                return json_error('Tipo de solicitud no vÃ¡lido', status=400, code='invalid_type')
            
            # Validaciones específicas por tipo de solicitud
            if tipo_nombre == "CT PERMANENTE":
                # CT PERMANENTE requiere: empleado_receptor, fecha_inicio, fecha_fin
                if not empleado_receptor_id:
                    return json_error('Debe seleccionar un compañero para el intercambio', status=400, code='missing_fields')
                fecha_inicio = request.POST.get('fecha_inicio')
                fecha_fin = request.POST.get('fecha_fin')
                if not fecha_inicio:
                    return json_error('La fecha de inicio es requerida', status=400, code='missing_fields')
                if not fecha_fin:
                    return json_error('La fecha de fin es requerida', status=400, code='missing_fields')
            elif tipo_nombre == "DOBLADA":
                # DOBLADA requiere validaciones según tipo de cesión
                if not fecha_solicitud:
                    return json_error('La fecha de cesión es requerida', status=400, code='missing_fields')
                
                # Verificar si es cesión total
                tipo_cesion = request.POST.get('tipo_cesion', 'cesion_completa')
                empleado_receptor_am = request.POST.get('empleado_receptor_am')
                empleado_receptor_pm = request.POST.get('empleado_receptor_pm')
                fecha_pago_am = request.POST.get('fecha_pago_am')
                fecha_pago_pm = request.POST.get('fecha_pago_pm')
                
                es_cesion_total = (tipo_cesion == 'cesion_completa' and 
                                  empleado_receptor_am and empleado_receptor_pm and
                                  fecha_pago_am and fecha_pago_pm)
                
                if es_cesion_total:
                    # Cesión total: validar ambos receptores y fechas
                    if not empleado_receptor_am:
                        return json_error('Debe seleccionar un compañero para la jornada AM', status=400, code='missing_fields')
                    if not empleado_receptor_pm:
                        return json_error('Debe seleccionar un compañero para la jornada PM', status=400, code='missing_fields')
                    if not fecha_pago_am:
                        return json_error('La fecha de pago para AM es obligatoria', status=400, code='missing_fields')
                    if not fecha_pago_pm:
                        return json_error('La fecha de pago para PM es obligatoria', status=400, code='missing_fields')
                else:
                    # Cesión parcial o completa normal
                    if not empleado_receptor_id:
                        return json_error('Debe seleccionar un compañero para cubrir la doblada', status=400, code='missing_fields')
                    fecha_pago = request.POST.get('fecha_pago')
                    if not fecha_pago:
                        return json_error('La fecha de pago es obligatoria. No existen dobladas abiertas.', status=400, code='missing_fields')
            elif tipo_nombre == "D FDS":
                # D FDS NO requiere empleado_receptor (es auto-solicitud)
                if not fecha_solicitud:
                    return json_error('La fecha es requerida', status=400, code='missing_fields')
                # Para D FDS, usar el mismo empleado como receptor
                empleado_receptor_id = None  # Se establecerá después como el mismo solicitante
            else:
                # CT y otros tipos requieren: empleado_receptor, fecha_solicitud
                if not empleado_receptor_id:
                    return json_error('Debe seleccionar un compañero para el intercambio', status=400, code='missing_fields')
                if not fecha_solicitud:
                    return json_error('La fecha es requerida', status=400, code='missing_fields')
            
            # Obtener objetos
            tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)  # type: ignore
            empleado_solicitante = request.user.empleado
            
            # Para D FDS, el receptor es el mismo que el solicitante
            if tipo_nombre == "D FDS":
                empleado_receptor = empleado_solicitante
            elif tipo_nombre == "DOBLADA":
                # Para DOBLADA, verificar si es cesión total (se manejará después)
                # Por ahora, establecer None (se obtendrá después si es cesión parcial)
                empleado_receptor = None
            else:
                if not empleado_receptor_id:
                    return json_error('Debe seleccionar un compañero para el intercambio', status=400, code='missing_fields')
                empleado_receptor = Empleado.objects.get(id=empleado_receptor_id)  # type: ignore
            
            # Preparar datos base para el Factory
            datos_solicitud_base = {
                'explorador_solicitante': empleado_solicitante,
                'tipo_cambio': tipo_solicitud,
                'comentario': comentario,
            }
            
            # Configurar fecha según el tipo de solicitud
            if tipo_solicitud.nombre == "CT PERMANENTE":
                fecha_inicio = request.POST.get('fecha_inicio')
                fecha_fin = request.POST.get('fecha_fin')
                
                # Capturar días seleccionados (JSON string)
                import json
                dias_seleccionados_json = request.POST.get('dias_seleccionados', '{}')
                try:
                    dias_seleccionados = json.loads(dias_seleccionados_json) if dias_seleccionados_json else {}
                except json.JSONDecodeError:
                    dias_seleccionados = {}
                
                # Para CT PERMANENTE, usar fecha_inicio como fecha_cambio_turno
                datos_solicitud = datos_solicitud_base.copy()
                datos_solicitud.update({
                    'explorador_receptor': empleado_receptor,
                    'fecha_cambio_turno': fecha_inicio,
                    'fecha_inicio': fecha_inicio,
                    'fecha_fin': fecha_fin,
                    'dias_seleccionados': dias_seleccionados
                })
            elif tipo_solicitud.nombre == "DOBLADA":
                # Para DOBLADA, capturar fecha_pago y otros campos
                fecha_pago = request.POST.get('fecha_pago')
                jornada_cedida = request.POST.get('jornada_cedida')  # 'AM' o 'PM' (opcional)
                tipo_cesion = request.POST.get('tipo_cesion', 'cesion_completa')
                
                # CORRECCIÓN: Inferir jornada_cedida si no se proporcionó
                # Esto ocurre cuando es cesión completa desde jornada simple (no doblada existente)
                if not jornada_cedida and fecha_solicitud:
                    from turnos.services.jornada_service import JornadaService
                    try:
                        jornada_solicitante = JornadaService.get_jornada_explorador_fecha(
                            empleado_solicitante.id, 
                            fecha_solicitud
                        )
                        jornada_cedida = jornada_solicitante.nombre.upper()
                        logger.info(
                            f"jornada_cedida inferida automáticamente: {jornada_cedida} "
                            f"para {empleado_solicitante.nombre} en fecha {fecha_solicitud}"
                        )
                    except Exception as e:
                        logger.warning(f"No se pudo inferir jornada_cedida: {str(e)}")
                        # Si falla, dejarlo None (el backend validará después)
                
                # Verificar si es cesión total (cesión completa desde doblada existente)
                empleado_receptor_am = request.POST.get('empleado_receptor_am')
                empleado_receptor_pm = request.POST.get('empleado_receptor_pm')
                fecha_pago_am = request.POST.get('fecha_pago_am')
                fecha_pago_pm = request.POST.get('fecha_pago_pm')
                
                es_cesion_total = (tipo_cesion == 'cesion_completa' and 
                                  empleado_receptor_am and empleado_receptor_pm and
                                  fecha_pago_am and fecha_pago_pm)
                
                if es_cesion_total:
                    # Cesión Total: Crear 2 solicitudes independientes
                    # Solicitud 1: Cesión AM
                    datos_solicitud_am = datos_solicitud_base.copy()
                    datos_solicitud_am.update({
                        'explorador_receptor': Empleado.objects.get(id=empleado_receptor_am),
                        'fecha_cambio_turno': fecha_solicitud,
                        'fecha_pago': fecha_pago_am,
                        'jornada_cedida': 'AM',
                        'tipo_cesion': 'cesion_parcial_am',
                        'fecha_creacion_solicitud': timezone.now().date()
                    })
                    
                    # Solicitud 2: Cesión PM
                    datos_solicitud_pm = datos_solicitud_base.copy()
                    datos_solicitud_pm.update({
                        'explorador_receptor': Empleado.objects.get(id=empleado_receptor_pm),
                        'fecha_cambio_turno': fecha_solicitud,
                        'fecha_pago': fecha_pago_pm,
                        'jornada_cedida': 'PM',
                        'tipo_cesion': 'cesion_parcial_pm',
                        'fecha_creacion_solicitud': timezone.now().date()
                    })
                    
                    # Validar ambas solicitudes
                    es_valida_am, mensaje_am = SolicitudFactory.validar_solicitud(tipo_solicitud, datos_solicitud_am)
                    es_valida_pm, mensaje_pm = SolicitudFactory.validar_solicitud(tipo_solicitud, datos_solicitud_pm)
                    
                    # Verificar si alguna validación falló con el caso crítico o doblada existente
                    if not es_valida_am:
                        try:
                            import json
                            error_data_am = json.loads(mensaje_am)
                            if isinstance(error_data_am, dict) and error_data_am.get('code') == 'requiere_cambio_turno_previo':
                                # Retornar error especial del caso crítico para AM
                                return JsonResponse({
                                    'success': False,
                                    'code': 'requiere_cambio_turno_previo',
                                    'message': error_data_am.get('message', 'Se requiere cambio de turno previo'),
                                    'fecha_pago': error_data_am.get('fecha_pago'),
                                    'jornada_comun': error_data_am.get('jornada_comun'),
                                    'jornada_afectada': 'AM'  # Indicar que es la jornada AM
                                }, status=400)
                        except (json.JSONDecodeError, TypeError, AttributeError):
                            pass
                        
                        # Detectar error de doblada existente
                        if 'ya tiene una doblada' in str(mensaje_am).lower():
                            import re
                            fecha_match = re.search(r'\d{2}/\d{2}/\d{4}', str(mensaje_am))
                            fecha_conflicto = fecha_match.group(0) if fecha_match else 'desconocida'
                            return JsonResponse({
                                'success': False,
                                'code': 'doblada_existente',
                                'message': 'No se puede crear la solicitud porque ya tienes una doblada en la fecha de pago seleccionada.',
                                'fecha_conflicto': fecha_conflicto,
                                'jornada_afectada': 'AM',
                                'mensaje_detallado': str(mensaje_am)
                            }, status=400)
                        
                        return json_error(f'Error en solicitud AM: {mensaje_am}', status=400, code='validation_error')
                    
                    if not es_valida_pm:
                        try:
                            import json
                            error_data_pm = json.loads(mensaje_pm)
                            if isinstance(error_data_pm, dict) and error_data_pm.get('code') == 'requiere_cambio_turno_previo':
                                # Retornar error especial del caso crítico para PM
                                return JsonResponse({
                                    'success': False,
                                    'code': 'requiere_cambio_turno_previo',
                                    'message': error_data_pm.get('message', 'Se requiere cambio de turno previo'),
                                    'fecha_pago': error_data_pm.get('fecha_pago'),
                                    'jornada_comun': error_data_pm.get('jornada_comun'),
                                    'jornada_afectada': 'PM'  # Indicar que es la jornada PM
                                }, status=400)
                        except (json.JSONDecodeError, TypeError, AttributeError):
                            pass
                        
                        # Detectar error de doblada existente
                        if 'ya tiene una doblada' in str(mensaje_pm).lower():
                            import re
                            fecha_match = re.search(r'\d{2}/\d{2}/\d{4}', str(mensaje_pm))
                            fecha_conflicto = fecha_match.group(0) if fecha_match else 'desconocida'
                            return JsonResponse({
                                'success': False,
                                'code': 'doblada_existente',
                                'message': 'No se puede crear la solicitud porque ya tienes una doblada en la fecha de pago seleccionada.',
                                'fecha_conflicto': fecha_conflicto,
                                'jornada_afectada': 'PM',
                                'mensaje_detallado': str(mensaje_pm)
                            }, status=400)
                        
                        return json_error(f'Error en solicitud PM: {mensaje_pm}', status=400, code='validation_error')
                    
                    # Crear ambas solicitudes
                    try:
                        solicitud_am, mensaje_am = SolicitudFactory.crear_solicitud(tipo_solicitud, datos_solicitud_am)
                        solicitud_pm, mensaje_pm = SolicitudFactory.crear_solicitud(tipo_solicitud, datos_solicitud_pm)
                        
                        if solicitud_am is None or solicitud_pm is None:
                            return json_error(
                                f'Error creando solicitudes: {mensaje_am if solicitud_am is None else mensaje_pm}',
                                status=400,
                                code='creation_failed'
                            )
                        
                        logger.info("Cesión total creada: 2 solicitudes independientes", extra={
                            'solicitud_am_id': solicitud_am.id,
                            'solicitud_pm_id': solicitud_pm.id,
                            'solicitante_id': empleado_solicitante.id
                        })
                        
                        return json_ok({
                            'message': 'Solicitudes de cesión total enviadas correctamente. Se han enviado notificaciones a los supervisores y compañeros.',
                            'solicitud_am_id': solicitud_am.id,
                            'solicitud_pm_id': solicitud_pm.id,
                            'es_cesion_total': True
                        }, status=201)
                        
                    except Exception as e:
                        logger.exception("Error creando solicitudes de cesión total")
                        return json_error('Error al procesar las solicitudes de cesión total', status=500, code='internal_error')
                else:
                    # Cesión parcial o completa normal
                    # Obtener receptor si no se obtuvo antes
                    if not empleado_receptor and empleado_receptor_id:
                        empleado_receptor = Empleado.objects.get(id=empleado_receptor_id)
                    
                    datos_solicitud = datos_solicitud_base.copy()
                    datos_solicitud.update({
                        'explorador_receptor': empleado_receptor,
                        'fecha_cambio_turno': fecha_solicitud,  # Fecha de cesión
                        'fecha_pago': fecha_pago,
                        'jornada_cedida': jornada_cedida,
                        'tipo_cesion': tipo_cesion,
                        'fecha_creacion_solicitud': timezone.now().date()  # Para validación de fecha_pago
                    })
            else:
                # Para otros tipos, usar fecha_solicitud
                datos_solicitud = datos_solicitud_base.copy()
                datos_solicitud.update({
                    'explorador_receptor': empleado_receptor,
                    'fecha_cambio_turno': fecha_solicitud
                })
            
            # Solo validar y crear si no es cesión total (cesión total ya se procesó arriba)
            if tipo_solicitud.nombre == "DOBLADA":
                tipo_cesion_check = request.POST.get('tipo_cesion', 'cesion_completa')
                empleado_receptor_am_check = request.POST.get('empleado_receptor_am')
                empleado_receptor_pm_check = request.POST.get('empleado_receptor_pm')
                fecha_pago_am_check = request.POST.get('fecha_pago_am')
                fecha_pago_pm_check = request.POST.get('fecha_pago_pm')
                
                es_cesion_total_check = (tipo_cesion_check == 'cesion_completa' and 
                                       empleado_receptor_am_check and empleado_receptor_pm_check and
                                       fecha_pago_am_check and fecha_pago_pm_check)
                
                if es_cesion_total_check:
                    # Ya se procesó arriba, no hacer nada más
                    return  # Salir temprano, ya se retornó respuesta arriba
                else:
                    # Continuar con validación y creación normal
                    logger.info("Datos preparados", extra={
                        'tipo_solicitud': tipo_solicitud.nombre,
                        'fecha_cambio_turno': datos_solicitud.get('fecha_cambio_turno'),
                        'fecha_inicio': datos_solicitud.get('fecha_inicio'),
                        'fecha_fin': datos_solicitud.get('fecha_fin')
                    })
                    
                    # Validar la solicitud usando el Factory
                    es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_solicitud, datos_solicitud)
                    
                    if not es_valida:
                        # Verificar si es el caso crítico de coincidencia de jornadas (DOBLADA)
                        try:
                            import json
                            error_data = json.loads(mensaje)
                            if isinstance(error_data, dict) and error_data.get('code') == 'requiere_cambio_turno_previo':
                                # Retornar error especial para que frontend maneje la redirección
                                return JsonResponse({
                                    'success': False,
                                    'code': 'requiere_cambio_turno_previo',
                                    'message': error_data.get('message', 'Se requiere cambio de turno previo'),
                                    'fecha_pago': error_data.get('fecha_pago'),
                                    'jornada_comun': error_data.get('jornada_comun')
                                }, status=400)
                        except (json.JSONDecodeError, TypeError, AttributeError):
                            # No es JSON, es un error normal
                            pass
                        
                        return json_error(mensaje, status=400, code='validation_error')
                    
                    # Crear la solicitud usando el Factory
                    logger.info("Creando solicitud usando SolicitudFactory", extra={
                        'tipo_solicitud': tipo_solicitud.nombre,
                        'solicitante_id': empleado_solicitante.id,
                        'receptor_id': empleado_receptor.id if empleado_receptor else None
                    })
                    
                    try:
                        solicitud, mensaje = SolicitudFactory.crear_solicitud(tipo_solicitud, datos_solicitud)
                        
                        if solicitud is None:
                            return json_error(mensaje, status=400, code='creation_failed')
                        
                        logger.info("Solicitud creada exitosamente", extra={
                            'solicitud_id': solicitud.id,
                            'tipo_solicitud': tipo_solicitud.nombre
                        })
                        
                        return json_ok({
                            'message': 'Solicitud enviada correctamente. Se han enviado notificaciones al supervisor y al compañero.',
                            'solicitud_id': solicitud.id
                        }, status=201)
                        
                    except Exception as e:
                        logger.exception("Error al crear solicitud usando Factory")
                        return json_error('Error al procesar la solicitud', status=500, code='internal_error')
            else:
                # Para otros tipos, validar normalmente
                logger.info("Datos preparados", extra={
                    'tipo_solicitud': tipo_solicitud.nombre,
                    'fecha_cambio_turno': datos_solicitud.get('fecha_cambio_turno'),
                    'fecha_inicio': datos_solicitud.get('fecha_inicio'),
                    'fecha_fin': datos_solicitud.get('fecha_fin')
                })
                
                # Validar la solicitud usando el Factory
                es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_solicitud, datos_solicitud)
                
                if not es_valida:
                    # Verificar si es el caso crítico de coincidencia de jornadas (DOBLADA)
                    try:
                        import json
                        error_data = json.loads(mensaje)
                        if isinstance(error_data, dict) and error_data.get('code') == 'requiere_cambio_turno_previo':
                            # Retornar error especial para que frontend maneje la redirección
                            return JsonResponse({
                                'success': False,
                                'code': 'requiere_cambio_turno_previo',
                                'message': error_data.get('message', 'Se requiere cambio de turno previo'),
                                'fecha_pago': error_data.get('fecha_pago'),
                                'jornada_comun': error_data.get('jornada_comun')
                            }, status=400)
                    except (json.JSONDecodeError, TypeError, AttributeError):
                        # No es JSON, es un error normal
                        pass
                    
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
                'message': 'Solicitud enviada correctamente. Se han enviado notificaciones al supervisor y al compaÃ±ero.',
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
            from .services.solicitud_consulta_service import SolicitudConsultaService
            return SolicitudConsultaService.get_solicitudes_usuario(self.request.user)
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
            
            from .services.solicitud_consulta_service import SolicitudConsultaService
            # Obtener solicitudes como receptor
            solicitudes_receptor = SolicitudConsultaService.get_solicitudes_por_receptor(self.request.user.empleado)
            print(f"DEBUG SOLICITUDES PENDIENTES - Solicitudes como receptor: {solicitudes_receptor.count()}")
            
            # Obtener solicitudes como supervisor
            solicitudes_supervisor = SolicitudConsultaService.get_solicitudes_por_supervisor(self.request.user.empleado)
            print(f"DEBUG SOLICITUDES PENDIENTES - Solicitudes como supervisor: {solicitudes_supervisor.count()}")
            
            # Combinar ambas querysets (evitar duplicados) respetando flags de aprobaciÃ³n
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
            
            # Debug detallado: Mostrar las solicitudes especÃ­ficas
            print(f"DEBUG SOLICITUDES PENDIENTES - Solicitudes como receptor:")
            for s in solicitudes_receptor:
                print(f"  - ID: {s.id}, Solicitante: {s.explorador_solicitante.nombre}, Receptor: {s.explorador_receptor.nombre}, Fecha: {s.fecha_solicitud}")
            
            print(f"DEBUG SOLICITUDES PENDIENTES - Solicitudes como supervisor:")
            for s in solicitudes_supervisor:
                print(f"  - ID: {s.id}, Solicitante: {s.explorador_solicitante.nombre}, Receptor: {s.explorador_receptor.nombre}, Fecha: {s.fecha_solicitud}")
            
            # Agregar informaciÃ³n del rol a cada solicitud
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
        
        from .services.solicitud_aprobacion_service import SolicitudAprobacionService
        success, message = SolicitudAprobacionService.aprobar_solicitud_supervisor(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return json_ok({'success': success, 'message': message})

@method_decorator(csrf_exempt, name='dispatch')
class AprobarSolicitudReceptorView(LoginRequiredMixin, View):
    """
    Vista para aprobar una solicitud por parte del compaÃ±ero receptor
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        from .services.solicitud_aprobacion_service import SolicitudAprobacionService
        success, message = SolicitudAprobacionService.aprobar_solicitud_receptor(
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
        
        from .services.solicitud_aprobacion_service import SolicitudAprobacionService
        success, message = SolicitudAprobacionService.rechazar_solicitud_supervisor(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return json_ok({'success': success, 'message': message})

@method_decorator(csrf_exempt, name='dispatch')
class RechazarSolicitudReceptorView(LoginRequiredMixin, View):
    """
    Vista para rechazar una solicitud por parte del compaÃ±ero receptor
    """
    def post(self, request, solicitud_id):
        try:
            comentario_respuesta = request.POST.get('comentario_respuesta', '')
            from .services.solicitud_aprobacion_service import SolicitudAprobacionService
            success, message = SolicitudAprobacionService.rechazar_solicitud_receptor(
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
            
            # Verificar que la solicitud estÃ© pendiente
            if solicitud.estado != 'pendiente':
                return json_error('Solo se pueden cancelar solicitudes pendientes', status=400, code='invalid_state')
            
            # Cancelar la solicitud
            solicitud.estado = 'cancelada'
            solicitud.fecha_resolucion = timezone.now()
            solicitud.comentario = f"{solicitud.comentario or ''}\n\nCancelada por el solicitante"
            solicitud.save()
            
            # Invalidar cache de contadores para todos los afectados
            from core.services.cache_service import CacheService
            cache_keys = [
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_receptor.id}",
            ]
            # Si el solicitante tiene supervisor, también invalidar su caché
            if solicitud.explorador_solicitante.supervisor:
                cache_keys.append(f"solicitudes_count_pend_{solicitud.explorador_solicitante.supervisor.id}")
            CacheService.delete_many(cache_keys)
            
            # Crear notificaciÃ³n de cancelaciÃ³n
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
    Aprueba como Receptor y como Supervisor en una sola acciÃ³n
    Solo disponible si el usuario es simultÃ¡neamente receptor y supervisor de la solicitud
    y la solicitud estÃ¡ en estado pendiente.
    """
    def post(self, request, solicitud_id):
        try:
            if not hasattr(request.user, 'empleado'):
                return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')

            solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
            empleado = request.user.empleado

            # Validar roles simultÃ¡neos
            es_receptor = solicitud.explorador_receptor == empleado
            es_supervisor = (getattr(solicitud.explorador_solicitante, 'supervisor', None) == empleado)

            if not (es_receptor and es_supervisor):
                return json_error('No tienes permisos para aprobar en ambos roles', status=403, code='forbidden')

            if solicitud.estado != 'pendiente':
                return json_error('La solicitud no estÃ¡ pendiente', status=400, code='invalid_state')

            # Recargar la solicitud para obtener el estado actualizado
            solicitud.refresh_from_db()
            
            # Aprobar primero como receptor si falta
            if not solicitud.aprobado_receptor:
                from .services.solicitud_aprobacion_service import SolicitudAprobacionService
                success, message = SolicitudAprobacionService.aprobar_solicitud_receptor(solicitud_id, empleado, 'Aprobado como receptor (acciÃ³n combinada)')
                if not success:
                    return json_error(message, status=400, code='approval_error')
                # Recargar despuÃ©s de aprobar como receptor
                solicitud.refresh_from_db()

            # Aprobar como supervisor si falta
            if not solicitud.aprobado_supervisor:
                from .services.solicitud_aprobacion_service import SolicitudAprobacionService
                success, message = SolicitudAprobacionService.aprobar_solicitud_supervisor(solicitud_id, empleado, 'Aprobado como supervisor (acciÃ³n combinada)')
                if not success:
                    return json_error(message, status=400, code='approval_error')
                # Recargar despuÃ©s de aprobar como supervisor
                solicitud.refresh_from_db()

            # NOTA: No necesitamos llamar a aplicar_cambios aquÃ­ porque
            # aprobar_solicitud_receptor y aprobar_solicitud_supervisor ya lo hacen
            # cuando detectan que ambos roles estÃ¡n aprobados

            return json_ok({'message': 'Solicitud aprobada en ambos roles correctamente'})
        except Exception:
            logger.exception('Error en AprobarSolicitudAmbosView')
            return json_error('Error al aprobar en ambos roles', status=500, code='internal_error')


# Vistas para aprobaciÃ³n por email (sin login requerido)
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
                    'mensaje': 'Token invÃ¡lido o expirado'
                })
            
            # Verificar que el usuario actual es el supervisor
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'No se encontrÃ³ supervisor para esta solicitud'
                })
            
            # Aprobar la solicitud
            from .services.solicitud_aprobacion_service import SolicitudAprobacionService
            success, message = SolicitudAprobacionService.aprobar_solicitud_supervisor(
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
        """Verifica que el token sea vÃ¡lido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producciÃ³n
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
                    'mensaje': 'Token invÃ¡lido o expirado'
                })
            
            # Verificar que el usuario actual es el supervisor
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'No se encontrÃ³ supervisor para esta solicitud'
                })
            
            # Rechazar la solicitud
            from .services.solicitud_aprobacion_service import SolicitudAprobacionService
            success, message = SolicitudAprobacionService.rechazar_solicitud_supervisor(
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
        """Verifica que el token sea vÃ¡lido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producciÃ³n
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
                    'mensaje': 'Token invÃ¡lido o expirado'
                })
            
            # Aprobar la solicitud
            from .services.solicitud_aprobacion_service import SolicitudAprobacionService
            success, message = SolicitudAprobacionService.aprobar_solicitud_receptor(
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
        """Verifica que el token sea vÃ¡lido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producciÃ³n
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
                    'mensaje': 'Token invÃ¡lido o expirado'
                })
            
            # Rechazar la solicitud
            from .services.solicitud_aprobacion_service import SolicitudAprobacionService
            success, message = SolicitudAprobacionService.rechazar_solicitud_receptor(
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
        """Verifica que el token sea vÃ¡lido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producciÃ³n
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(token, expected_token)


class ObtenerExploradoresDobladaView(LoginRequiredMixin, View):
    """
    Endpoint para obtener exploradores disponibles para doblada.
    Filtra según jornada contraria y excluye exploradores con doblada activa.
    """
    def get(self, request):
        try:
            fecha = request.GET.get('fecha')
            jornada_cedida = request.GET.get('jornada_cedida')  # Opcional: 'AM' o 'PM'
            
            if not fecha:
                return json_error('La fecha es requerida', status=400, code='missing_fields')
            
            usuario_actual = request.user.empleado
            
            # Obtener estrategia de doblada
            tipo_doblada = TipoSolicitudCambio.objects.filter(nombre='DOBLADA').first()
            if not tipo_doblada:
                return json_error('Tipo de solicitud DOBLADA no encontrado', status=404, code='not_found')
            
            strategy = SolicitudFactory.get_strategy(tipo_doblada)
            empleados_disponibles = strategy.get_empleados_disponibles(
                fecha,
                usuario_actual,
                jornada_cedida=jornada_cedida
            )
            
            return json_ok({
                'empleados': empleados_disponibles,
                'total': len(empleados_disponibles)
            })
            
        except Exception as e:
            logger.exception("Error obteniendo exploradores para doblada")
            return json_error('Error al obtener exploradores disponibles', status=500, code='internal_error')


class VerificarDobladaExistenteView(LoginRequiredMixin, View):
    """
    Endpoint para verificar si el usuario tiene alguna relación con una doblada en una fecha.
    Distingue entre 3 estados:
    1. Usuario está descansando (cedió su jornada como solicitante)
    2. Usuario tiene doblada (cubre como receptor)
    3. Usuario no tiene ninguna doblada
    """
    def get(self, request):
        try:
            fecha = request.GET.get('fecha')
            
            if not fecha:
                return json_error('La fecha es requerida', status=400, code='missing_fields')
            
            usuario_actual = request.user.empleado
            
            # Verificar si tiene doblada aprobada en esa fecha
            from datetime import datetime
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            
            # Buscar solicitudes donde el usuario está involucrado
            doblada_como_solicitante = SolicitudCambio.objects.filter(
                explorador_solicitante=usuario_actual,
                tipo_cambio__nombre='DOBLADA',
                fecha_cambio_turno=fecha_obj,
                estado='aprobada'
            ).first()
            
            doblada_como_receptor = SolicitudCambio.objects.filter(
                explorador_receptor=usuario_actual,
                tipo_cambio__nombre='DOBLADA',
                fecha_cambio_turno=fecha_obj,
                estado='aprobada'
            ).first()
            
            # CASO 1: Usuario cedió su jornada → está descansando
            if doblada_como_solicitante:
                return json_ok({
                    'tiene_doblada': False,
                    'esta_descansando': True,
                    'puede_ceder': False,
                    'jornadas': [],
                    'mensaje': 'Ya cediste tu jornada para esta fecha. Estás descansando este día.',
                    'solicitud_id': doblada_como_solicitante.id
                })
            
            # CASO 2: Usuario cubre a otro → tiene doblada
            if doblada_como_receptor:
                # Obtener jornadas del turno (AM, PM, o ambas)
                from turnos.models import Turno
                turnos = Turno.objects.filter(
                    explorador=usuario_actual,
                    fecha=fecha_obj
                ).select_related('jornada')
                
                jornadas = [t.jornada.nombre.upper() for t in turnos]
                
                # VALIDACIÓN DE INTEGRIDAD: Detectar inconsistencias
                datos_inconsistentes = False
                mensaje_inconsistencia = None
                
                if not jornadas:
                    # PROBLEMA: Solicitud aprobada pero sin turnos generados
                    datos_inconsistentes = True
                    mensaje_inconsistencia = (
                        f'⚠️ Datos inconsistentes detectados: Tienes una doblada aprobada '
                        f'(Solicitud #{doblada_como_receptor.id}) pero no se generaron los turnos correctamente. '
                        f'Por favor, contacta al administrador o intenta cancelar y volver a solicitar.'
                    )
                    logger.error(
                        f"INCONSISTENCIA DETECTADA: Usuario {usuario_actual.nombre} (ID: {usuario_actual.id}) "
                        f"tiene doblada aprobada (ID: {doblada_como_receptor.id}) para {fecha_obj} "
                        f"pero no tiene turnos generados en la tabla turnos_turno"
                    )
                    
                    # Intentar obtener la jornada predeterminada para mostrar algo
                    from turnos.services.jornada_service import JornadaService
                    jornada_pred = JornadaService.get_jornada_explorador_fecha(
                        usuario_actual.id, fecha
                    )
                    if jornada_pred:
                        jornadas = [jornada_pred.nombre.upper()]
                        mensaje_inconsistencia += f' Se muestra tu jornada predeterminada ({jornada_pred.nombre}).'
                
                mensaje = mensaje_inconsistencia if datos_inconsistentes else (
                    f'Tienes una doblada aprobada ({", ".join(jornadas)}). Puedes ceder una o ambas jornadas.'
                )
                
                return json_ok({
                    'tiene_doblada': True,
                    'esta_descansando': False,
                    'puede_ceder': not datos_inconsistentes,  # No permitir ceder si hay inconsistencia
                    'jornadas': jornadas,
                    'mensaje': mensaje,
                    'solicitud_id': doblada_como_receptor.id,
                    'datos_inconsistentes': datos_inconsistentes,  # Nuevo flag
                    'requiere_atencion_admin': datos_inconsistentes  # Nuevo flag
                })
            
            # CASO 3: No hay doblada
            return json_ok({
                'tiene_doblada': False,
                'esta_descansando': False,
                'puede_ceder': True,
                'jornadas': [],
                'solicitud_id': None
            })
            
        except Exception as e:
            logger.exception("Error verificando doblada existente")
            return json_error('Error al verificar doblada existente', status=500, code='internal_error')


class ObtenerFechasDescansoView(LoginRequiredMixin, View):
    """
    Endpoint para obtener fechas donde el usuario está descansando (cedió su jornada).
    Útil para deshabilitar estas fechas en el calendario de solicitud de doblada.
    """
    def get(self, request):
        try:
            usuario_actual = request.user.empleado
            
            # Buscar solicitudes donde usuario es solicitante y estado=aprobada
            from datetime import datetime
            
            solicitudes_cedidas = SolicitudCambio.objects.filter(
                explorador_solicitante=usuario_actual,
                tipo_cambio__nombre='DOBLADA',
                estado='aprobada'
            ).values_list('fecha_cambio_turno', flat=True)
            
            fechas_descanso = [f.strftime('%Y-%m-%d') for f in solicitudes_cedidas]
            
            return json_ok({
                'fechas': fechas_descanso,
                'total': len(fechas_descanso)
            })
            
        except Exception as e:
            logger.exception("Error obteniendo fechas de descanso")
            return json_error('Error al obtener fechas de descanso', status=500, code='internal_error')


class ObtenerDetalleSolicitudView(LoginRequiredMixin, View):
    """
    Endpoint API para obtener detalles completos de una solicitud.
    Incluye informaciÃ³n especÃ­fica segÃºn el tipo de solicitud.
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
            
            # InformaciÃ³n bÃ¡sica comÃºn
            datos = {
                'id': solicitud.id,
                'fecha_solicitud': solicitud.fecha_solicitud.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_solicitud else None,
                'tipo': solicitud.tipo_cambio.nombre,
                'tipo_codigo': solicitud.tipo_cambio.codigo_estrategia or solicitud.tipo_cambio.nombre.upper(),
                'estado': solicitud.estado,
                'comentario': solicitud.comentario or 'Sin comentario',
                'fecha_resolucion': solicitud.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_resolucion else None,
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
                        'fecha': solicitud.fecha_aprobacion_receptor.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_aprobacion_receptor else None,
                    },
                    'supervisor': {
                        'aprobado': solicitud.aprobado_supervisor,
                        'fecha': solicitud.fecha_aprobacion_supervisor.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_aprobacion_supervisor else None,
                    },
                },
                'fechas': {},
                'informacion_adicional': {}
            }
            
            # InformaciÃ³n especÃ­fica segÃºn el tipo
            tipo_nombre = solicitud.tipo_cambio.nombre.upper()
            
            # CT PERMANENTE
            if tipo_nombre == 'CT PERMANENTE':
                try:
                    detalle = solicitud.cambio_permanente
                    if detalle:
                        datos['fechas']['inicio'] = detalle.fecha_inicio.strftime('%d/%m/%Y')
                        datos['fechas']['fin'] = detalle.fecha_fin.strftime('%d/%m/%Y') if detalle.fecha_fin else 'Sin fecha de fin'
                        
                        # Obtener dÃ­as de semana seleccionados
                        dias_seleccionados = detalle.dias.filter(tipo='dia_semana')
                        dias_semana_nombres = []
                        for dia in dias_seleccionados:
                            if dia.dia_semana is not None:
                                dias_semana_nombres.append(dia.get_dia_semana_display())
                        
                        if dias_semana_nombres:
                            datos['informacion_adicional']['dias_semana_seleccionados'] = ', '.join(dias_semana_nombres)
                        else:
                            datos['informacion_adicional']['dias_semana_seleccionados'] = 'Todos los dÃ­as hÃ¡biles'
                        
                        # Calcular fechas aplicables y excluidas
                        from datetime import datetime as _dt
                        from .services.ct_permanente_helper import calcular_fechas_aplicables_y_excluidas_ct_permanente
                        fechas_aplicables, fechas_excluidas = calcular_fechas_aplicables_y_excluidas_ct_permanente(
                            detalle,
                            solicitud.explorador_solicitante,
                            solicitud.explorador_receptor
                        )
                        
                        datos['fechas']['aplicables'] = [fecha.strftime('%d/%m/%Y') for fecha in fechas_aplicables]
                        datos['fechas']['total_dias'] = len(fechas_aplicables)
                        
                        # Agregar fechas excluidas con sus razones
                        datos['fechas']['excluidas'] = [
                            {
                                'fecha': fecha_info['fecha'].strftime('%d/%m/%Y'),
                                'razon': fecha_info['razon']
                            }
                            for fecha_info in fechas_excluidas
                        ]

                        # Resumen informativo del rango (UX)
                        try:
                            fi = detalle.fecha_inicio
                            ff = detalle.fecha_fin or _dt.strptime(f"{fi.year}-12-31", "%Y-%m-%d").date()
                            total_dias_rango = (ff - fi).days + 1
                            fines_semana = 0
                            cur = fi
                            while cur <= ff:
                                if cur.weekday() in (5, 6):
                                    fines_semana += 1
                                cur = cur + timezone.timedelta(days=1)
                            datos['fechas']['resumen'] = {
                                'total_dias_rango': total_dias_rango,
                                'fines_de_semana_en_rango': fines_semana,
                                'prioridad': 'Mantenimiento > Festivo > Temporada > Descanso Solicitante > Descanso Receptor > Fines de semana',
                            }
                        except Exception:
                            datos['fechas']['resumen'] = None
                        
                        datos['informacion_adicional']['nota'] = 'Se excluyen domingos, festivos, dÃ­as de mantenimiento y dÃ­as de descanso de los exploradores.'
                except Exception as e:
                    logger.error(f"Error obteniendo detalles de CT PERMANENTE: {e}")
                    datos['fechas']['error'] = 'No se pudieron obtener los detalles del cambio permanente'
            
            # DOBLADA
            elif tipo_nombre == 'DOBLADA':
                try:
                    detalle = solicitud.doblada
                    if detalle:
                        datos['fechas']['fecha_doblada'] = solicitud.fecha_cambio_turno.strftime('%d/%m/%Y') if solicitud.fecha_cambio_turno else 'No especificada'
                        datos['informacion_adicional']['minutos_deuda'] = detalle.minutos_deuda
                        datos['informacion_adicional']['fecha_pago'] = detalle.fecha_pago.strftime('%d/%m/%Y') if detalle.fecha_pago else 'Pendiente de pago'
                        
                        # Analizar fecha para mostrar información detallada
                        if solicitud.fecha_cambio_turno:
                            from .services.fechas_helper import obtener_informacion_fecha_para_detalle
                            info_fecha = obtener_informacion_fecha_para_detalle(
                                solicitud.fecha_cambio_turno,
                                solicitante=solicitud.explorador_solicitante,
                                receptor=None,
                                tipo_solicitud='DOBLADA'
                            )
                            datos['fechas']['analisis'] = info_fecha
                            if info_fecha['razones_exclusion']:
                                datos['fechas']['excluidas'] = [{
                                    'fecha': info_fecha['fecha'],
                                    'razon': ', '.join(info_fecha['razones_exclusion'])
                                }]
                            datos['informacion_adicional']['nota'] = 'Se excluyen días de mantenimiento y temporada.'
                except Exception as e:
                    logger.error(f"Error obteniendo detalles de DOBLADA: {e}")
            
            # D FDS (Doblada Fin de Semana)
            elif tipo_nombre == 'D FDS':
                try:
                    detalle = solicitud.doblada  # D FDS usa el mismo modelo que DOBLADA
                    if detalle:
                        datos['fechas']['fecha_doblada'] = solicitud.fecha_cambio_turno.strftime('%d/%m/%Y') if solicitud.fecha_cambio_turno else 'No especificada'
                        datos['informacion_adicional']['minutos_deuda'] = detalle.minutos_deuda
                        datos['informacion_adicional']['fecha_pago'] = detalle.fecha_pago.strftime('%d/%m/%Y') if detalle.fecha_pago else 'Pendiente de pago'
                        
                        # Analizar fecha para mostrar información detallada
                        if solicitud.fecha_cambio_turno:
                            from .services.fechas_helper import obtener_informacion_fecha_para_detalle
                            info_fecha = obtener_informacion_fecha_para_detalle(
                                solicitud.fecha_cambio_turno,
                                solicitante=solicitud.explorador_solicitante,
                                receptor=None,
                                tipo_solicitud='D FDS'
                            )
                            datos['fechas']['analisis'] = info_fecha
                            if info_fecha['razones_exclusion']:
                                datos['fechas']['excluidas'] = [{
                                    'fecha': info_fecha['fecha'],
                                    'razon': ', '.join(info_fecha['razones_exclusion'])
                                }]
                            datos['informacion_adicional']['nota'] = 'Se excluyen días de mantenimiento y temporada.'
                except Exception as e:
                    logger.error(f"Error obteniendo detalles de D FDS: {e}")
            
            # CT (Cambio Turno normal) y otros tipos
            else:
                if solicitud.fecha_cambio_turno:
                    datos['fechas']['fecha_cambio'] = solicitud.fecha_cambio_turno.strftime('%d/%m/%Y')
                    
                    # Obtener informaciÃ³n de jornadas si hay turnos asociados
                    if solicitud.turno_origen:
                        datos['informacion_adicional']['jornada_solicitante'] = solicitud.turno_origen.jornada.nombre if solicitud.turno_origen.jornada else None
                    if solicitud.turno_destino:
                        datos['informacion_adicional']['jornada_receptor'] = solicitud.turno_destino.jornada.nombre if solicitud.turno_destino.jornada else None
                    
                    # Analizar fecha para mostrar información detallada
                    from .services.fechas_helper import obtener_informacion_fecha_para_detalle
                    info_fecha = obtener_informacion_fecha_para_detalle(
                        solicitud.fecha_cambio_turno,
                        solicitante=solicitud.explorador_solicitante,
                        receptor=solicitud.explorador_receptor,
                        tipo_solicitud='CT'
                    )
                    datos['fechas']['analisis'] = info_fecha
                    
                    # Si hay razones de exclusión, agregarlas
                    if info_fecha['razones_exclusion']:
                        datos['fechas']['excluidas'] = [{
                            'fecha': info_fecha['fecha'],
                            'razon': ', '.join(info_fecha['razones_exclusion'])
                        }]
                    else:
                        # Si es válida, agregarla a aplicables
                        datos['fechas']['aplicables'] = [info_fecha['fecha']]
                    
                    datos['informacion_adicional']['nota'] = 'Se excluyen días de mantenimiento, domingos y dobladas activas. Los festivos se permiten si ambos empleados tienen jornada.'
            
            return json_ok(datos)
            
        except Exception as e:
            logger.error(f"Error en ObtenerDetalleSolicitudView: {e}", exc_info=True)
            return json_error('Error al obtener detalles de la solicitud', status=500, code='internal_error')

