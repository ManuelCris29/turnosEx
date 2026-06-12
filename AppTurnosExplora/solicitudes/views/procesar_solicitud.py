from django.shortcuts import render, get_object_or_404
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.db.models import Q
from core.mixins import AdminRequiredMixin
from core.services import get_turno_service
from empleados.models import Empleado
from ..models import TipoSolicitudCambio, Notificacion, SolicitudCambio, CambioPermanenteDetalle
from ..services.solicitud_service import SolicitudService
from ..services.solicitud_factory import SolicitudFactory
from ..services.permiso_service import PermisoService
from ..services.notificacion_service import NotificacionService
from django.utils import timezone
import hashlib
import hmac
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.utils.json_responses import json_ok, json_error

# Create your views here.

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
                    
                    # Validación adicional: el compañero receptor no puede tener ya una DOBLADA (AM+PM)
                    # en la fecha de cesión (fecha_solicitud). Usamos Turno como fuente de verdad.
                    try:
                        from datetime import datetime as _dt_datetime
                        from turnos.models import Turno as _Turno

                        fecha_cesion_obj = _dt_datetime.strptime(fecha_solicitud, '%Y-%m-%d').date()
                        turnos_receptor = (
                            _Turno.objects
                            .filter(explorador_id=empleado_receptor_id, fecha=fecha_cesion_obj)
                            .select_related('jornada')
                        )
                        jornadas_receptor = {
                            t.jornada.nombre.upper()
                            for t in turnos_receptor
                            if t.jornada
                        }
                        if 'AM' in jornadas_receptor and 'PM' in jornadas_receptor:
                            return json_error(
                                'El compañero seleccionado ya tiene una doblada (AM+PM) en la fecha de cesión y no puede cubrirte.',
                                status=400,
                                code='doblada_receptor_existente',
                            )
                    except Exception:
                        # Si algo falla en esta validación, no bloquear la solicitud por seguridad,
                        # la lógica de negocio principal seguirá validando más adelante.
                        logger.exception(
                            "Error verificando doblada existente para el receptor en fecha de cesión"
                        )
                    fecha_pago = request.POST.get('fecha_pago')
                    if not fecha_pago:
                        return json_error('La fecha de pago es obligatoria. No existen dobladas abiertas.', status=400, code='missing_fields')
            elif tipo_nombre == "D FDS":
                # D FDS: el solicitante cede su día de finde a un compañero (receptor real)
                # y devuelve el favor en otro finde del mismo mes (fecha de pago).
                if not fecha_solicitud:
                    return json_error('La fecha del fin de semana es requerida', status=400, code='missing_fields')
                if not empleado_receptor_id:
                    return json_error('Debe seleccionar el compañero que se doblará el fin de semana', status=400, code='missing_fields')
                if not request.POST.get('fecha_pago'):
                    return json_error('La fecha de pago es obligatoria (otro fin de semana del mismo mes).', status=400, code='missing_fields')
            else:
                # CT y otros tipos requieren: empleado_receptor, fecha_solicitud
                if not empleado_receptor_id:
                    return json_error('Debe seleccionar un compañero para el intercambio', status=400, code='missing_fields')
                if not fecha_solicitud:
                    return json_error('La fecha es requerida', status=400, code='missing_fields')
            
            # Obtener objetos
            tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)  # type: ignore
            empleado_solicitante = request.user.empleado
            
            # Para D FDS, el receptor es el compañero seleccionado (no auto-solicitud)
            if tipo_nombre == "D FDS":
                empleado_receptor = Empleado.objects.get(id=empleado_receptor_id)  # type: ignore
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
                jornada_pago_sabado = request.POST.get('jornada_pago_sabado')  # 'AM' o 'PM' (si fecha_pago es sábado)
                jornada_cubre_en_pago = request.POST.get('jornada_cubre_en_pago')  # AM | PM | AMBAS (receptor doblada en pago)
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
                    # Si el mismo receptor cubre AM y PM y la misma fecha de pago: una sola solicitud cesión completa
                    mismo_receptor_y_misma_fecha = (
                        str(empleado_receptor_am) == str(empleado_receptor_pm) and
                        str(fecha_pago_am) == str(fecha_pago_pm)
                    )
                    if mismo_receptor_y_misma_fecha:
                        receptor = Empleado.objects.get(id=empleado_receptor_am)
                        datos_solicitud = datos_solicitud_base.copy()
                        datos_solicitud.update({
                            'explorador_receptor': receptor,
                            'fecha_cambio_turno': fecha_solicitud,
                            'fecha_pago': fecha_pago_am,
                            'tipo_cesion': 'cesion_completa',
                            'fecha_creacion_solicitud': timezone.now().date()
                        })
                        es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_solicitud, datos_solicitud)
                        if not es_valida:
                            return json_error(f'Error validando solicitud: {mensaje}', status=400, code='validation_error')
                        solicitud, mensaje = SolicitudFactory.crear_solicitud(tipo_solicitud, datos_solicitud)
                        if solicitud is None:
                            return json_error(f'Error creando solicitud: {mensaje}', status=400, code='creation_failed')
                        logger.info("Cesión total (un receptor, una fecha pago) creada: 1 solicitud cesion_completa", extra={
                            'solicitud_id': solicitud.id,
                            'solicitante_id': empleado_solicitante.id,
                            'receptor_id': receptor.id
                        })
                        return json_ok({
                            'message': 'Solicitud de cesión total enviada correctamente.',
                            'solicitud_id': solicitud.id,
                            'es_cesion_total': True,
                            'una_solicitud': True
                        }, status=201)
                    # Cesión total con receptores o fechas distintas: 2 solicitudes independientes
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
                        'jornada_pago_sabado': jornada_pago_sabado,
                        'jornada_cubre_en_pago': jornada_cubre_en_pago,
                        'tipo_cesion': tipo_cesion,
                        'fecha_creacion_solicitud': timezone.now().date()  # Para validación de fecha_pago
                    })
                    
                    # Log para debugging
                    logger.info("Datos de solicitud DOBLADA preparados", extra={
                        'fecha_cesion': fecha_solicitud,
                        'fecha_pago': fecha_pago,
                        'jornada_cedida': jornada_cedida,
                        'jornada_pago_sabado': jornada_pago_sabado,
                        'jornada_cubre_en_pago': jornada_cubre_en_pago,
                        'tipo_cesion': tipo_cesion,
                        'receptor_id': empleado_receptor.id if empleado_receptor else None
                    })
            elif tipo_solicitud.nombre == "D FDS":
                # D FDS: cesión = finde que cede, pago = finde de devolución (mismo mes)
                datos_solicitud = datos_solicitud_base.copy()
                datos_solicitud.update({
                    'explorador_receptor': empleado_receptor,
                    'fecha_cambio_turno': fecha_solicitud,
                    'fecha_pago': request.POST.get('fecha_pago'),
                    'fecha_creacion_solicitud': timezone.now().date(),
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
                    
                    logger.info("Resultado de validación DOBLADA", extra={
                        'es_valida': es_valida,
                        'mensaje': mensaje[:200] if mensaje else None,  # Limitar longitud del mensaje
                        'fecha_cesion': datos_solicitud.get('fecha_cambio_turno'),
                        'fecha_pago': datos_solicitud.get('fecha_pago'),
                        'jornada_pago_sabado': datos_solicitud.get('jornada_pago_sabado')
                    })
                    
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

