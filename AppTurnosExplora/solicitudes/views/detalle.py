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
                        from ..services.ct_permanente_helper import calcular_fechas_aplicables_y_excluidas_ct_permanente
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

                        # Tipo de cesión y jornada cedida
                        _tc = {
                            'cesion_completa': 'Completa (AM y PM)',
                            'cesion_parcial_am': 'Parcial AM',
                            'cesion_parcial_pm': 'Parcial PM',
                        }.get(detalle.tipo_cesion, detalle.tipo_cesion)
                        datos['informacion_adicional']['tipo_cesion'] = _tc
                        if detalle.jornada_cedida:
                            datos['informacion_adicional']['jornada_cedida'] = detalle.jornada_cedida.upper()

                        # Pago en sábado (AM / PM / AMBAS) y, si es AMBAS, el día de pago en semana
                        if getattr(detalle, 'jornada_pago_sabado', None):
                            jps = detalle.jornada_pago_sabado.upper()
                            datos['informacion_adicional']['pago_sabado'] = {
                                'AM': 'Cubres la jornada AM ese sábado (el compañero conserva PM)',
                                'PM': 'Cubres la jornada PM ese sábado (el compañero conserva AM)',
                                'AMBAS': 'Cubres el día completo (AM+PM); el compañero descansa y te devuelve media jornada en semana',
                            }.get(jps, jps)
                        if getattr(detalle, 'fecha_pago_semana', None):
                            datos['informacion_adicional']['fecha_pago_semana'] = detalle.fecha_pago_semana.strftime('%d/%m/%Y')

                        # Analizar fecha para mostrar información detallada
                        if solicitud.fecha_cambio_turno:
                            from ..services.fechas_helper import obtener_informacion_fecha_para_detalle
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
                            from ..services.fechas_helper import obtener_informacion_fecha_para_detalle
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
            
            # DOBLADA PERMANENTE (acuerdo recurrente por días de la semana)
            elif tipo_nombre == 'DOBLADA PERMANENTE':
                try:
                    detalle = solicitud.doblada_permanente
                    if detalle:
                        datos['fechas']['inicio'] = detalle.fecha_inicio.strftime('%d/%m/%Y')
                        datos['fechas']['fin'] = detalle.fecha_fin.strftime('%d/%m/%Y') if detalle.fecha_fin else 'Sin fecha de fin'
                        datos['informacion_adicional']['dias_cesion'] = detalle.dias_cesion_legible() or '—'
                        datos['informacion_adicional']['dias_devolucion'] = detalle.dias_devolucion_legible() or '—'
                        datos['informacion_adicional']['nota'] = (
                            'El compañero (receptor) te cubre doblándose en tus días de cesión, y tú le devuelves '
                            'doblándote en los días de devolución, durante el rango indicado. '
                            'No aplica domingos, festivos ni días de mantenimiento.'
                        )
                except Exception as e:
                    logger.error(f"Error obteniendo detalles de DOBLADA PERMANENTE: {e}")
                    datos['fechas']['error'] = 'No se pudieron obtener los detalles de la doblada permanente'

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
                    from ..services.fechas_helper import obtener_informacion_fecha_para_detalle
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

