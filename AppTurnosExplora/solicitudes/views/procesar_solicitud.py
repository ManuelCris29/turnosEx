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

    def _advertencia_restriccion_generica(self, request, empleado_solicitante):
        """
        Devuelve un JsonResponse de ADVERTENCIA (no bloqueo) si el solicitante o algún
        receptor tiene una restricción médica que solapa las fechas de la solicitud, y
        aún no se confirmó. Devuelve None si no hay nada que advertir o ya se confirmó.
        La sanción se sigue bloqueando aparte (no aquí).
        """
        if str(request.POST.get('confirmar_restriccion', '')).lower() in ('1', 'true', 'si', 'sí'):
            return None
        from empleados.models import RestriccionEmpleado
        from django.db.models import Q as _Q
        from datetime import datetime as _dt

        # Fechas candidatas (cualquiera presente en el POST según el tipo)
        campos = ['fecha_solicitud', 'fecha_cambio_turno', 'fecha_pago', 'fecha_inicio',
                  'fecha_fin', 'fecha_pago_am', 'fecha_pago_pm', 'fecha_pago_semana']
        fechas = []
        for c in campos:
            v = request.POST.get(c)
            if v:
                try:
                    fechas.append(_dt.strptime(v, '%Y-%m-%d').date())
                except (ValueError, TypeError):
                    pass
        if not fechas:
            return None
        fmin, fmax = min(fechas), max(fechas)

        # Exploradores involucrados: solicitante + receptores presentes en el POST
        receptor_ids = set()
        for c in ['empleado_receptor']:
            v = request.POST.get(c)
            if v:
                receptor_ids.add(v)
        emps, vistos = [empleado_solicitante], set()
        for rid in receptor_ids:
            try:
                emps.append(Empleado.objects.get(id=rid))
            except Empleado.DoesNotExist:
                pass

        advertencias = []
        for emp in emps:
            if emp.id in vistos:
                continue
            vistos.add(emp.id)
            rs = RestriccionEmpleado.objects.filter(empleado=emp, fecha_inicio__lte=fmax).filter(
                _Q(fecha_fin__isnull=True) | _Q(fecha_fin__gte=fmin)
            )
            for r in rs:
                advertencias.append({
                    'explorador': f"{emp.nombre} {emp.apellido}",
                    'tipo': r.tipo_restriccion or 'Restricción',
                    'nota': r.recomendacion or '—',
                })
        if advertencias:
            return JsonResponse({
                'success': False,
                'code': 'advertencia_restriccion',
                'message': 'Hay una restricción médica vigente en las fechas. Revisa la nota antes de continuar.',
                'restricciones': advertencias,
            }, status=400)
        return None

    def _procesar_doblada_permanente_multi(self, request, tipo_solicitud, empleado_solicitante, comentario):
        """
        Doblada permanente con VARIOS compañeros: agrupa los días por compañero y
        crea una solicitud independiente por cada uno (como la "Cesión Total" de la
        doblada normal). Valida TODAS antes de crear ninguna (todo o nada).
        """
        fecha_inicio = request.POST.get('fecha_inicio')
        fecha_fin = request.POST.get('fecha_fin')
        ces_dias = request.POST.getlist('cesion_dia')
        ces_comps = request.POST.getlist('cesion_companero')
        dev_dias = request.POST.getlist('devolucion_dia')
        dev_comps = request.POST.getlist('devolucion_companero')

        if not comentario or not comentario.strip():
            return json_error('Ingresa un comentario.', status=400, code='missing_fields')

        # Agrupar (día, compañero) por compañero
        cesion_por_comp = {}
        for dia, comp in zip(ces_dias, ces_comps):
            if comp and str(dia) != '':
                cesion_por_comp.setdefault(comp, set()).add(str(dia))
        devol_por_comp = {}
        for dia, comp in zip(dev_dias, dev_comps):
            if comp and str(dia) != '':
                devol_por_comp.setdefault(comp, set()).add(str(dia))

        if not cesion_por_comp:
            return json_error('Agrega al menos un día de cesión con su compañero', status=400, code='missing_fields')

        # Devolución solo a quien te cubre, y balance por compañero
        for comp in devol_por_comp:
            if comp not in cesion_por_comp:
                return json_error('Solo puedes devolverle a un compañero que te cubra.', status=400, code='validation_error')
        for comp, dias_c in cesion_por_comp.items():
            if len(devol_por_comp.get(comp, set())) != len(dias_c):
                return json_error('A cada compañero debes devolverle la misma cantidad de días que te cubre.',
                                  status=400, code='validation_error')

        # ADVERTENCIA (no bloquea) por restricción médica del solicitante o de algún compañero.
        # Si hay restricción y el usuario aún no confirmó, devolvemos el aviso con la nota.
        confirmar_restriccion = str(request.POST.get('confirmar_restriccion', '')).lower() in ('1', 'true', 'si', 'sí')
        if not confirmar_restriccion:
            from empleados.models import RestriccionEmpleado
            from django.db.models import Q as _Q
            from datetime import datetime as _dt
            try:
                _fi = _dt.strptime(fecha_inicio, '%Y-%m-%d').date()
                _ff = _dt.strptime(fecha_fin, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                _fi = _ff = None
            advertencias = []
            if _fi and _ff:
                emps = [empleado_solicitante]
                for comp_id in cesion_por_comp:
                    try:
                        emps.append(Empleado.objects.get(id=comp_id))
                    except Empleado.DoesNotExist:
                        pass
                vistos = set()
                for emp in emps:
                    if emp.id in vistos:
                        continue
                    vistos.add(emp.id)
                    rs = RestriccionEmpleado.objects.filter(empleado=emp, fecha_inicio__lte=_ff).filter(
                        _Q(fecha_fin__isnull=True) | _Q(fecha_fin__gte=_fi)
                    )
                    for r in rs:
                        advertencias.append({
                            'explorador': f"{emp.nombre} {emp.apellido}",
                            'tipo': r.tipo_restriccion or 'Restricción',
                            'nota': r.recomendacion or '—',
                        })
            if advertencias:
                return JsonResponse({
                    'success': False,
                    'code': 'advertencia_restriccion',
                    'message': 'Hay una restricción médica vigente en el rango. Revisa la nota antes de continuar.',
                    'restricciones': advertencias,
                }, status=400)

        # Validar TODAS antes de crear ninguna
        pendientes = []
        for comp_id, dias_c in cesion_por_comp.items():
            try:
                receptor = Empleado.objects.get(id=comp_id)
            except Empleado.DoesNotExist:
                return json_error('Compañero no válido.', status=400, code='validation_error')
            datos = {
                'explorador_solicitante': empleado_solicitante,
                'explorador_receptor': receptor,
                'tipo_cambio': tipo_solicitud,
                'comentario': comentario,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'dias_cesion': sorted(dias_c),
                'dias_devolucion': sorted(devol_por_comp.get(comp_id, set())),
                'fecha_creacion_solicitud': timezone.now().date(),
            }
            es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_solicitud, datos)
            if not es_valida:
                # Regla del sábado u otras que devuelven el código de cambio de turno previo
                try:
                    import json as _json
                    err = _json.loads(mensaje)
                    if isinstance(err, dict) and err.get('code') == 'requiere_cambio_turno_previo':
                        return JsonResponse({'success': False, **err}, status=400)
                except (ValueError, TypeError):
                    pass
                return json_error(f"{receptor.nombre} {receptor.apellido}: {mensaje}", status=400, code='validation_error')
            pendientes.append((receptor, datos))

        # Crear todas
        creadas = 0
        for receptor, datos in pendientes:
            solicitud, mensaje = SolicitudFactory.crear_solicitud(tipo_solicitud, datos)
            if solicitud is None:
                return json_error(f"Error creando la solicitud para {receptor.nombre}: {mensaje}",
                                  status=400, code='creation_failed')
            creadas += 1

        msg = ('Doblada permanente solicitada. Se notificó al compañero y al supervisor.'
               if creadas == 1 else
               f'Se crearon {creadas} solicitudes de doblada permanente (una por compañero). '
               f'Se notificó a cada uno y al supervisor.')
        return json_ok({'message': msg, 'solicitudes_creadas': creadas}, status=201)

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
            elif tipo_nombre == "CAMBIO DESCANSO":
                # Cambio de descanso de fin de semana: cesión = finde que cambias,
                # pago = finde de devolución (mismo mes), receptor = compañero contrario.
                if not fecha_solicitud:
                    return json_error('El fin de semana que cambias es requerido', status=400, code='missing_fields')
                if not empleado_receptor_id:
                    return json_error('Debe seleccionar el compañero con quien intercambia el descanso', status=400, code='missing_fields')
                if not request.POST.get('fecha_pago'):
                    return json_error('El fin de semana de devolución es obligatorio (otro finde del mismo mes).', status=400, code='missing_fields')
            elif tipo_nombre == "DOBLADA PERMANENTE":
                # Doblada permanente (varios compañeros): rango + filas día+compañero
                if not request.POST.get('fecha_inicio') or not request.POST.get('fecha_fin'):
                    return json_error('El rango de fechas (inicio y fin) es obligatorio', status=400, code='missing_fields')
                if not request.POST.getlist('cesion_companero'):
                    return json_error('Agrega al menos un día de cesión con su compañero', status=400, code='missing_fields')
                if not request.POST.getlist('devolucion_companero'):
                    return json_error('Agrega al menos un día de devolución con su compañero', status=400, code='missing_fields')
            else:
                # CT y otros tipos requieren: empleado_receptor, fecha_solicitud
                if not empleado_receptor_id:
                    return json_error('Debe seleccionar un compañero para el intercambio', status=400, code='missing_fields')
                if not fecha_solicitud:
                    return json_error('La fecha es requerida', status=400, code='missing_fields')
            
            # Obtener objetos
            tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)  # type: ignore
            empleado_solicitante = request.user.empleado

            # SANCIÓN AUTOMÁTICA POR DEUDA DE DOBLADA VENCIDA (>30 días sin pagar):
            # genera la sanción automáticamente (o la levanta si ya pagó) antes de validar el bloqueo.
            try:
                from ..services.deuda_corporativa_service import DeudaCorporativaService
                DeudaCorporativaService.gestionar_sancion_por_deuda(empleado_solicitante)
            except Exception:
                logger.exception('Error gestionando sanción automática por deuda')

            # BLOQUEO POR SANCIÓN: un explorador sancionado no puede solicitar cambios de turno
            from empleados.sancion_utils import sancion_activa, mensaje_sancion
            _sancion = sancion_activa(empleado_solicitante)
            if _sancion:
                return json_error(mensaje_sancion(_sancion), status=403, code='sancionado')

            # DOBLADA PERMANENTE (varios compañeros): se agrupa por compañero y se crea
            # una solicitud independiente por cada uno (como la "Cesión Total" de la doblada).
            if tipo_nombre == "DOBLADA PERMANENTE":
                return self._procesar_doblada_permanente_multi(
                    request, tipo_solicitud, empleado_solicitante, comentario
                )

            # ADVERTENCIA (no bloqueo) por restricción médica — aplica a los demás tipos.
            _adv = self._advertencia_restriccion_generica(request, empleado_solicitante)
            if _adv is not None:
                return _adv

            # Para D FDS, el receptor es el compañero seleccionado (no auto-solicitud)
            if tipo_nombre == "D FDS":
                empleado_receptor = Empleado.objects.get(id=empleado_receptor_id)  # type: ignore
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
                jornada_pago_sabado = request.POST.get('jornada_pago_sabado')  # 'AM' | 'PM' | 'AMBAS' (si fecha_pago es sábado)
                jornada_cubre_en_pago = request.POST.get('jornada_cubre_en_pago')  # AM | PM | AMBAS (receptor doblada en pago)
                fecha_pago_semana = request.POST.get('fecha_pago_semana')  # solo si jornada_pago_sabado=AMBAS: día de devolución en semana
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
                
                # Obtener receptor
                if not empleado_receptor and empleado_receptor_id:
                    empleado_receptor = Empleado.objects.get(id=empleado_receptor_id)

                datos_solicitud = datos_solicitud_base.copy()
                datos_solicitud.update({
                    'explorador_receptor': empleado_receptor,
                    'fecha_cambio_turno': fecha_solicitud,
                    'fecha_pago': fecha_pago,
                    'jornada_cedida': jornada_cedida,
                    'jornada_pago_sabado': jornada_pago_sabado,
                    'jornada_cubre_en_pago': jornada_cubre_en_pago,
                    'fecha_pago_semana': fecha_pago_semana,
                    'tipo_cesion': tipo_cesion,
                    'fecha_creacion_solicitud': timezone.now().date()
                })

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
            elif tipo_solicitud.nombre == "CAMBIO DESCANSO":
                # Cambio de descanso: cesión = finde que cambias, pago = finde de devolución
                datos_solicitud = datos_solicitud_base.copy()
                datos_solicitud.update({
                    'explorador_receptor': empleado_receptor,
                    'fecha_cambio_turno': fecha_solicitud,
                    'fecha_pago': request.POST.get('fecha_pago'),
                    'fecha_creacion_solicitud': timezone.now().date(),
                })
            elif tipo_solicitud.nombre == "DOBLADA PERMANENTE":
                # Doblada permanente: rango + días de cesión y devolución (CSV de 0..6)
                dias_cesion = request.POST.getlist('dias_cesion') or request.POST.get('dias_cesion', '').split(',')
                dias_devolucion = request.POST.getlist('dias_devolucion') or request.POST.get('dias_devolucion', '').split(',')
                datos_solicitud = datos_solicitud_base.copy()
                datos_solicitud.update({
                    'explorador_receptor': empleado_receptor,
                    'fecha_inicio': request.POST.get('fecha_inicio'),
                    'fecha_fin': request.POST.get('fecha_fin'),
                    'dias_cesion': [d for d in dias_cesion if str(d).strip() != ''],
                    'dias_devolucion': [d for d in dias_devolucion if str(d).strip() != ''],
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

