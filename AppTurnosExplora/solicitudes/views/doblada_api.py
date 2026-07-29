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
from core.utils.date_utils import DateUtils

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.utils.json_responses import json_ok, json_error

# Create your views here.

class ObtenerExploradoresDobladaView(LoginRequiredMixin, View):
    """
    Endpoint para obtener exploradores disponibles para doblada.
    Filtra según jornada contraria y excluye exploradores con doblada activa.
    """
    def get(self, request):
        try:
            fecha = request.GET.get('fecha')
            jornada_cedida = request.GET.get('jornada_cedida')  # Opcional: 'AM' o 'PM'
            solicitante_descansa = request.GET.get('solicitante_descansa') in ['1', 'true', 'True']
            incluir_descanso = request.GET.get('incluir_descanso') in ['1', 'true', 'True']
            
            if not fecha:
                return json_error('La fecha es requerida', status=400, code='missing_fields')
            
            usuario_actual = request.user.empleado
            
            tipo_doblada = TipoSolicitudCambio.objects.filter(nombre='DOBLADA', activo=True).first()
            if not tipo_doblada:
                return json_error('Tipo de solicitud DOBLADA no encontrado', status=404, code='not_found')
            
            strategy = SolicitudFactory.get_strategy(tipo_doblada)
            empleados_disponibles = strategy.get_empleados_disponibles(
                fecha,
                usuario_actual,
                jornada_cedida=jornada_cedida,
                solicitante_descansa=solicitante_descansa
            )
            
            if incluir_descanso:
                from solicitudes.services.doblada_filtro_service import DobladaFiltroService
                from turnos.services.turno_service import TurnoService
                from turnos.models import Turno as TurnoCheck
                from core.utils.date_utils import DateUtils

                fecha_obj_desc = DateUtils.parse_date(fecha)

                ids_con_turno = set(
                    TurnoCheck.objects.filter(
                        fecha=fecha_obj_desc
                    ).values_list('explorador_id', flat=True)
                )

                ids_cedieron_en_cesion = set(
                    SolicitudCambio.objects.filter(
                        tipo_cambio__nombre='DOBLADA',
                        fecha_cambio_turno=fecha_obj_desc,
                        estado='aprobada'
                    ).values_list('explorador_solicitante_id', flat=True)
                )

                from solicitudes.models import DobladaDetalle
                ids_recibieron_pago = set(
                    SolicitudCambio.objects.filter(
                        tipo_cambio__nombre='DOBLADA',
                        estado='aprobada',
                        doblada__fecha_pago=fecha_obj_desc
                    ).values_list('explorador_receptor_id', flat=True)
                )

                ids_descanso_doblada = ids_cedieron_en_cesion | ids_recibieron_pago

                for emp_dict in empleados_disponibles:
                    eid = emp_dict['id']
                    if eid not in ids_con_turno and eid in ids_descanso_doblada:
                        emp_dict['jornada'] = 'Descanso'
                    elif eid in ids_con_turno:
                        try:
                            emp_obj = Empleado.objects.get(id=eid)
                            jd = TurnoService.obtener_jornada_display(emp_obj, fecha_obj_desc)
                            if jd is None:
                                emp_dict['jornada'] = 'Descanso'
                        except Exception:
                            logger.warning("Error resolviendo jornada display (empleado=%s)", eid, exc_info=True)

                en_descanso = DobladaFiltroService.obtener_empleados_en_descanso(fecha, usuario_actual.id)
                en_descanso = DobladaFiltroService.filtrar_empleados_sin_doblada_activa(en_descanso, fecha)
                ids_ya_incluidos = {e['id'] for e in empleados_disponibles}
                for emp in en_descanso:
                    if emp.id not in ids_ya_incluidos:
                        empleados_disponibles.append({
                            'id': emp.id,
                            'nombre': emp.nombre,
                            'apellido': emp.apellido,
                            'jornada': 'Descanso',
                        })
            
            return json_ok({
                'empleados': empleados_disponibles,
                'total': len(empleados_disponibles)
            })
            
        except Exception:
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
            fecha_obj = DateUtils.parse_date(fecha)
            
            # ✅ PRIORIDAD ABSOLUTA: Usar Turno como fuente de verdad única
            # Si hay turnos AM+PM en Turno, significa que ya está aplicado (aprobado y ejecutado)
            # Esto simplifica la lógica y mejora el rendimiento (una sola consulta)
            # IMPORTANTE: La presencia de turnos físicos tiene PRIORIDAD ABSOLUTA sobre cualquier solicitud aprobada
            from turnos.models import Turno
            turnos = Turno.objects.filter(
                explorador=usuario_actual,
                fecha=fecha_obj
            ).select_related('jornada')
            
            # Convertir a lista para evaluar múltiples veces si es necesario
            turnos_list = list(turnos)
            jornadas = [t.jornada.nombre.upper() for t in turnos_list if t.jornada]
            es_doblada_turnos = 'AM' in jornadas and 'PM' in jornadas
            
            # CASO 1: Usuario tiene turnos AM+PM (doblada asignada) - PRIORIDAD ABSOLUTA
            # Si hay turnos AM+PM en BD, SIEMPRE retornar tiene_doblada: true
            # Esto tiene prioridad sobre cualquier DOBLADA aprobada o regla de negocio
            if es_doblada_turnos:
                # Opcional: Buscar solicitud relacionada solo para mostrar ID (si existe)
                # Esto es opcional y no afecta la lógica principal
                solicitud_id = None
                try:
                    doblada_solicitud = (
                        SolicitudCambio.objects
                        .filter(
                            Q(explorador_solicitante=usuario_actual, fecha_cambio_turno=fecha_obj) |
                            Q(explorador_receptor=usuario_actual, doblada__fecha_pago=fecha_obj),
                            tipo_cambio__nombre='DOBLADA',
                            estado='aprobada'
                        )
                        .first()
                    )
                    if doblada_solicitud:
                        solicitud_id = doblada_solicitud.id
                except Exception:
                    # Si falla la búsqueda de solicitud, no es crítico
                    logger.warning("Error buscando solicitud de doblada asociada", exc_info=True)
                
                return json_ok({
                    'tiene_doblada': True,
                    'esta_descansando': False,
                    'puede_ceder': True,
                    'jornadas': jornadas,
                    'mensaje': f'Tienes jornada doblada ({", ".join(jornadas)}) ese día. Puedes ceder una jornada (AM o PM), o intercambiar tu doblada por la de un compañero.',
                    'solicitud_id': solicitud_id,
                    'datos_inconsistentes': False,
                    'requiere_atencion_admin': False
                })
            
            # Variable para mensaje cuando es festivo pero el usuario descansa (no tiene doblada)
            mensaje_festivo_descansa = None
            # CASO 2.9 (PRIORIDAD): Usuario NO tiene turnos - verificar PRIMERO si descansa por DOBLADA aprobada
            # Si no hay turnos en BD, puede ser porque cedió (solicitante) o porque es fecha de pago (receptor).
            # Esto debe ejecutarse ANTES de la regla de festivo: en festivo, JornadaService puede devolver
            # la jornada del grupo que trabaja ese día y marcar "tiene_doblada", cuando en realidad está descansando.
            if not jornadas and len(turnos_list) == 0:
                doblada_como_solicitante = (
                    SolicitudCambio.objects
                    .filter(
                        explorador_solicitante=usuario_actual,
                        tipo_cambio__nombre='DOBLADA',
                        fecha_cambio_turno=fecha_obj,
                        estado='aprobada'
                    )
                    .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor', 'doblada')
                    .first()
                )
                doblada_como_receptor = (
                    SolicitudCambio.objects
                    .filter(
                        explorador_receptor=usuario_actual,
                        tipo_cambio__nombre='DOBLADA',
                        estado='aprobada',
                        doblada__fecha_pago=fecha_obj
                    )
                    .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor', 'doblada')
                    .first()
                )
                if doblada_como_solicitante or doblada_como_receptor:
                    sol = doblada_como_solicitante or doblada_como_receptor
                    return json_ok({
                        'tiene_doblada': False,
                        'esta_descansando': True,
                        'puede_ceder': False,
                        'jornadas': [],
                        'mensaje': 'Ya cediste tu jornada para esta fecha. Estás descansando este día.',
                        'solicitud_id': sol.id
                    })

            # CASO 1.5: No hay turnos AM+PM en BD, pero es FESTIVO de semana y al usuario le corresponde doblar por rotación
            # Aplica tanto si tiene 0 turnos como si tiene 1 turno (su grupo es el que dobla ese festivo).
            from solicitudes.services.solicitud_validator import SolicitudValidator
            es_festivo = SolicitudValidator.es_festivo_semana(fecha_obj)
            logger.info(
                "VerificarDobladaExistente CASO 1.5: es_doblada_turnos=%s es_festivo_semana=%s fecha=%s usuario_id=%s",
                es_doblada_turnos, es_festivo, str(fecha_obj), usuario_actual.id
            )
            if not es_doblada_turnos and es_festivo:
                try:
                    from turnos.services.asignacion_especial_service import AsignacionEspecialService
                    from turnos.services.jornada_service import JornadaService
                    grupo_que_dobla = AsignacionEspecialService.grupo_trabaja(fecha_obj)
                    jornada_usuario = None
                    if jornadas:
                        jornada_usuario = jornadas[0].upper()  # Un solo turno en BD
                    else:
                        pred = JornadaService.get_jornada_explorador_fecha(
                            usuario_actual.id, fecha_obj.strftime('%Y-%m-%d')
                        )
                        jornada_usuario = pred.nombre.upper() if pred else None
                    # `grupo_que_dobla` es None si el año no tiene la alternancia publicada:
                    # entonces no se afirma nada sobre ese festivo.
                    coincide = bool(grupo_que_dobla and jornada_usuario
                                    and jornada_usuario == grupo_que_dobla)
                    logger.info(
                        "VerificarDobladaExistente festivo: grupo_que_dobla=%s jornada_usuario=%s coincide=%s",
                        grupo_que_dobla, jornada_usuario, coincide
                    )
                    if not coincide and jornada_usuario:
                        grupo_descansa = jornada_usuario
                        mensaje_festivo_descansa = (
                            f'Este día es festivo y le toca doblar al grupo {grupo_que_dobla}; '
                            f'tú eres del grupo {grupo_descansa}, así que descansas y no tienes jornada que ceder.'
                        )
                    tiene_doblada_real_bd = set(jornadas) == {'AM', 'PM'}
                    # Mensaje único para festivo: el día se trabaja COMPLETO (AM + PM) y, por la regla
                    # de negocio de festivos, solo se puede ceder el día entero (no media jornada) y la
                    # fecha de pago debe ser otro festivo del mismo mes. El frontend usa `es_festivo`
                    # para ocultar el selector de "Tipo de Cesión" (parcial/total) y forzar cesión completa.
                    mensaje_festivo_doblada = (
                        f'Este día es festivo: trabajas la jornada completa (AM + PM) porque le corresponde '
                        f'doblar al grupo {grupo_que_dobla}. Por regla de festivos solo puedes ceder el día '
                        f'completo a un compañero, y la fecha de pago debe ser otro día festivo del mismo mes.'
                    )
                    # Festivo sin modificaciones (0 turnos): mostrar DOBLADA por regla si el grupo trabaja
                    if not jornadas and grupo_que_dobla and jornada_usuario == grupo_que_dobla:
                        return json_ok({
                            'tiene_doblada': True,
                            'esta_descansando': False,
                            'puede_ceder': True,
                            'jornadas': ['AM', 'PM'],
                            'es_festivo': True,
                            'mensaje': mensaje_festivo_doblada,
                            'solicitud_id': None,
                            'datos_inconsistentes': False,
                            'requiere_atencion_admin': False
                        })
                    # Doblada real en BD (2 turnos AM+PM)
                    if tiene_doblada_real_bd and grupo_que_dobla and jornada_usuario == grupo_que_dobla:
                        return json_ok({
                            'tiene_doblada': True,
                            'esta_descansando': False,
                            'puede_ceder': True,
                            'jornadas': ['AM', 'PM'],
                            'es_festivo': True,
                            'mensaje': mensaje_festivo_doblada,
                            'solicitud_id': None,
                            'datos_inconsistentes': False,
                            'requiere_atencion_admin': False
                        })
                except Exception as e:
                    logger.warning(
                        "VerificarDobladaExistente: error al evaluar doblada en festivo: %s",
                        e,
                        extra={'fecha': str(fecha_obj), 'usuario_id': usuario_actual.id},
                        exc_info=True
                    )
            
            # CASO TEMPORADA: día entre semana donde el usuario trabaja el día COMPLETO por
            # temporada (el grupo contrario descansa). No hay turnos reales, pero trabaja AM+PM.
            # NO es una doblada cedible por este formulario: las cesiones de un día de temporada
            # van por Cambio de Descanso → «Que me cubran mi día» (cobertura), con pago en la
            # MISMA semana. Aquí solo informamos y guiamos al flujo correcto.
            if not es_doblada_turnos and fecha_obj.weekday() < 5:
                from turnos.services.turno_service import TurnoService as _TSt
                est_t = _TSt.estado_dia(usuario_actual, fecha_obj)
                if est_t['trabaja'] and est_t['jornada'] == 'DOBLADA' and est_t['fuente'] == 'temporada':
                    return json_ok({
                        'tiene_doblada': False,
                        'esta_descansando': False,
                        'puede_ceder': False,
                        'jornadas': ['AM', 'PM'],
                        'es_temporada_dia_completo': True,
                        'mensaje': (
                            'Este día trabajas la jornada completa (AM + PM) por temporada. '
                            'La doblada normal no aplica en días de temporada: para ceder una '
                            'jornada usa Cambio de Descanso → «Que me cubran mi día» (cobertura), '
                            'donde el pago es en la misma semana.'
                        ),
                        'solicitud_id': None,
                    })

            # CASO 2: Usuario tiene turnos pero NO es doblada (solo una jornada)
            # IMPORTANTE: Verificar si estos turnos son resultado de un CT donde el usuario es solicitante
            if jornadas:
                # Verificar si alguno de los turnos que tiene el usuario está relacionado con un CT donde él es solicitante
                # turno_origen es el turno del solicitante (con jornada del receptor)
                # (Q ya está importado a nivel de módulo; un import local aquí volvía
                #  'Q' local a todo el método y rompía su uso en el CASO 1 de arriba.)
                turnos_ids = [t.id for t in turnos]
                ct_como_solicitante = (
                    SolicitudCambio.objects
                    .filter(
                        explorador_solicitante=usuario_actual,
                        tipo_cambio__nombre='CT',  # Cambio Turno sencillo
                        fecha_cambio_turno=fecha_obj,
                        estado='aprobada'
                    )
                    .filter(
                        Q(turno_origen_id__in=turnos_ids) | Q(turno_destino_id__in=turnos_ids)
                    )
                    .select_related('turno_origen', 'turno_destino', 'explorador_receptor', 'tipo_cambio')
                    .first()
                )
                
                if ct_como_solicitante:
                    p = {'tiene_doblada': False, 'esta_descansando': False, 'puede_ceder': False,
                         'jornadas': jornadas, 'mensaje': 'Ya tienes un cambio de turno aprobado para esta fecha. No puedes solicitar doblada en la misma fecha.',
                         'solicitud_id': ct_como_solicitante.id}
                    if mensaje_festivo_descansa:
                        p['mensaje_festivo_descansa'] = mensaje_festivo_descansa
                    return json_ok(p)
                p = {'tiene_doblada': False, 'esta_descansando': False, 'puede_ceder': True, 'jornadas': jornadas, 'solicitud_id': None}
                if mensaje_festivo_descansa:
                    p['mensaje_festivo_descansa'] = mensaje_festivo_descansa
                return json_ok(p)
            
            # CASO 3: Usuario NO tiene turnos - verificar si cedió su jornada (está descansando)
            # IMPORTANTE: Este caso SOLO se ejecuta si NO hay turnos físicos en BD
            # Si hay turnos AM+PM, el CASO 1 ya retornó y este código NO se ejecuta
            # PRIORIDAD: Verificar descanso por DOBLADA aprobada ANTES de cualquier regla de negocio
            # Esto tiene prioridad sobre la regla de doblada en sábados y sobre CT
            # VALIDACIÓN CRÍTICA: Asegurar que no hay turnos antes de verificar descanso
            if not jornadas and len(turnos_list) == 0:
                # Verificar si está descansando por DOBLADA aprobada (como solicitante o receptor)
                doblada_como_solicitante = (
                    SolicitudCambio.objects
                    .filter(
                        explorador_solicitante=usuario_actual,
                        tipo_cambio__nombre='DOBLADA',
                        fecha_cambio_turno=fecha_obj,
                        estado='aprobada'
                    )
                    .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor', 'doblada')
                    .first()
                )
                
                doblada_como_receptor = (
                    SolicitudCambio.objects
                    .filter(
                        explorador_receptor=usuario_actual,
                        tipo_cambio__nombre='DOBLADA',
                        estado='aprobada',
                        doblada__fecha_pago=fecha_obj
                    )
                    .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor', 'doblada')
                    .first()
                )
                
                if doblada_como_solicitante or doblada_como_receptor:
                    # Usuario está descansando por DOBLADA aprobada - PRIORIDAD ABSOLUTA
                    sol = doblada_como_solicitante or doblada_como_receptor
                    return json_ok({
                        'tiene_doblada': False,
                        'esta_descansando': True,
                        'puede_ceder': False,
                        'jornadas': [],
                        'mensaje': 'Ya cediste tu jornada para esta fecha. Estás descansando este día.',
                        'solicitud_id': sol.id
                    })
            
            # CASO 2.6: Verificar si tiene cambio de turno (CT) aprobado ANTES de verificar doblada por regla de negocio
            # Esto tiene prioridad sobre la regla de doblada en sábados
            # Solo se ejecuta si NO hay turnos físicos en BD y NO está descansando por DOBLADA
            # VALIDACIÓN CRÍTICA: Asegurar que no hay turnos antes de verificar CT
            if not jornadas and len(turnos_list) == 0:
                ct_como_solicitante = (
                    SolicitudCambio.objects
                    .filter(
                        explorador_solicitante=usuario_actual,
                        tipo_cambio__nombre='CT',  # Cambio Turno sencillo
                        fecha_cambio_turno=fecha_obj,
                        estado='aprobada'
                    )
                    .select_related('turno_origen', 'turno_destino', 'explorador_receptor', 'tipo_cambio')
                    .first()
                )
                
                if ct_como_solicitante:
                    # Usuario tiene un CT aprobado para esta fecha
                    # No puede solicitar doblada porque ya hizo un cambio de turno
                    return json_ok({
                        'tiene_doblada': False,
                        'esta_descansando': False,  # Técnicamente no está descansando, está trabajando con jornada diferente
                        'puede_ceder': False,
                        'jornadas': [],
                        'mensaje': 'Ya tienes un cambio de turno aprobado para esta fecha. No puedes solicitar doblada en la misma fecha.',
                        'solicitud_id': ct_como_solicitante.id
                    })
            
            # CASO 2.5: No hay turnos físicos, pero es sábado y debería tener DOBLADA por regla de negocio
            # Esto es necesario porque en sábados, según la alternancia, algunos exploradores trabajan
            # y tienen DOBLADA (AM+PM) aunque no haya turnos físicos creados en BD todavía
            # SOLO se aplica si NO está descansando por DOBLADA aprobada y NO tiene CT aprobado
            # VALIDACIÓN CRÍTICA: Asegurar que no hay turnos antes de aplicar regla de sábado
            if not jornadas and len(turnos_list) == 0 and fecha_obj.weekday() == 5:  # Sábado (weekday 5)
                # Verificar estado real antes de aplicar la alternancia: un CAMBIO DESCANSO aprobado
                # puede hacer que el sábado sea descanso aunque la alternancia diga que trabaja.
                # TurnoService.estado_dia aplica las 6 capas (L2 incluye solicitudes de todo tipo).
                from turnos.services.turno_service import TurnoService
                estado_real = TurnoService.estado_dia(usuario_actual, fecha_obj)
                if not estado_real.get('trabaja') and estado_real.get('fuente') == 'solicitud':
                    return json_ok({
                        'tiene_doblada': False,
                        'esta_descansando': True,
                        'puede_ceder': False,
                        'jornadas': [],
                        'mensaje': 'Estás descansando este día por un intercambio aprobado (cambio de descanso u otro).',
                        'solicitud_id': None,
                    })

                from turnos.services.asignacion_especial_service import AsignacionEspecialService
                from turnos.services.jornada_service import JornadaService

                jornada_trabaja_sabado = AsignacionEspecialService.grupo_trabaja(fecha_obj)
                if jornada_trabaja_sabado:
                    jornada_predeterminada = JornadaService.get_jornada_explorador_fecha(
                        usuario_actual.id, fecha_obj.strftime('%Y-%m-%d')
                    )
                    if jornada_predeterminada and jornada_predeterminada.nombre.upper() == jornada_trabaja_sabado.upper():
                        # Le corresponde trabajar ese sábado → jornada predeterminada es DOBLADA (AM+PM)
                        return json_ok({
                            'tiene_doblada': True,
                            'esta_descansando': False,
                            'puede_ceder': True,
                            'jornadas': ['AM', 'PM'],  # DOBLADA por regla de negocio
                            'mensaje': 'Tienes jornada doblada (AM, PM) por regla de negocio (sábado). Puedes ceder una jornada (AM o PM), o intercambiar tu doblada por la de un compañero.',
                            'solicitud_id': None,
                            'datos_inconsistentes': False,
                            'requiere_atencion_admin': False
                        })
            
            # CASO 4: No hay turnos ni solicitud.
            if mensaje_festivo_descansa:
                # Festivo en el que al grupo del usuario NO le corresponde trabajar: descansa ese día
                # y NO tiene jornada que ceder. No puede solicitar doblada en esta fecha.
                # puede_ceder=False hace que el frontend muestre el aviso y bloquee compañero/fecha de pago/envío.
                return json_ok({
                    'tiene_doblada': False,
                    'esta_descansando': False,
                    'puede_ceder': False,
                    'jornadas': [],
                    'mensaje': mensaje_festivo_descansa,
                    'mensaje_festivo_descansa': mensaje_festivo_descansa,
                    'solicitud_id': None,
                })

            # Día normal sin turnos: puede solicitar doblada normalmente.
            return json_ok({
                'tiene_doblada': False,
                'esta_descansando': False,
                'puede_ceder': True,
                'jornadas': [],
                'solicitud_id': None,
            })
            
        except Exception as e:
            logger.exception("Error verificando doblada existente")
            return json_error('Error al verificar doblada existente', status=500, code='internal_error')


class ObtenerFechasDescansoView(LoginRequiredMixin, View):
    """
    Endpoint para obtener las fechas donde el usuario tiene DÍA LIBRE por una solicitud aprobada
    (para marcarlas en el calendario de la doblada). Debe ser CONSISTENTE para todos los usuarios:
    cubre TODAS las formas de quedar libre por solicitud —cedió su jornada, recibe el pago de una
    doblada (acreedor descansa), cambio de descanso, doblada permanente—, no solo la cesión completa
    como solicitante. Por eso usa la FUENTE DE VERDAD (estado_mes = estado_dia por lote), en lugar de
    una consulta parcial que dejaba a unos usuarios con días marcados y a otros no.
    """
    def get(self, request):
        try:
            from datetime import date
            from turnos.services.turno_service import TurnoService
            usuario_actual = request.user.empleado

            hoy = timezone.localdate()
            # Ventana que cubre la navegación típica del datepicker: mes anterior .. +6 meses.
            anio, mes = hoy.year, hoy.month
            mes -= 1
            if mes == 0:
                mes, anio = 12, anio - 1

            fechas_descanso = []
            for _ in range(8):
                estado = TurnoService.estado_mes(usuario_actual, anio, mes)
                for f, d in estado.items():
                    # Día libre por SOLICITUD aprobada: no trabaja y la fuente es la capa de
                    # solicitudes (cedió / paga doblada / cambio de descanso / doblada permanente).
                    # Se respeta el turno real (L1): si ese día trabaja de verdad, NO se marca.
                    if not d.get('trabaja') and d.get('fuente') == 'solicitud':
                        fechas_descanso.append(f.strftime('%Y-%m-%d'))
                mes += 1
                if mes == 13:
                    mes, anio = 1, anio + 1

            return json_ok({'fechas': fechas_descanso, 'total': len(fechas_descanso)})

        except Exception:
            logger.exception("Error obteniendo fechas de descanso")
            return json_error('Error al obtener fechas de descanso', status=500, code='internal_error')


