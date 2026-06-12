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
        from ..services.ct_permanente_helper import (
            _es_festivo,
            _es_mantenimiento,
            _es_temporada,
            _es_dia_descanso,
            _razon_principal_ct_permanente,
        )
        from ..services.solicitud_validator import SolicitudValidator  # type: ignore

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


