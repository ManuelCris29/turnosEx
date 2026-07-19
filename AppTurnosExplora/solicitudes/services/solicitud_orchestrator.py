"""
SolicitudOrchestrator

Orquesta el flujo completo de creación de una solicitud:
  sanción → restricción médica → parseo → validación → creación.

No contiene lógica HTTP: recibe datos ya parseados del POST y devuelve
JsonResponse. Toda la lógica de negocio la delega en Factory/strategies.
"""
import json
import logging
from django.http import JsonResponse
from django.utils import timezone

from empleados.models import Empleado
from ..models import TipoSolicitudCambio
from .solicitud_factory import SolicitudFactory
from .solicitud_request_parser import SolicitudRequestParser
from core.utils.json_responses import json_ok, json_error

logger = logging.getLogger(__name__)


class SolicitudOrchestrator:

    # ------------------------------------------------------------------
    # Checks transversales
    # ------------------------------------------------------------------

    @staticmethod
    def _refrescar_y_sancion(empleado):
        """Refresca la auto-sanción por deuda del empleado y devuelve su sanción activa (o None)."""
        if empleado is None:
            return None
        try:
            from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
            DeudaCorporativaService.gestionar_sancion_por_deuda(empleado)
        except Exception:
            logger.exception('Error gestionando sanción automática por deuda de %s', getattr(empleado, 'id', '?'))

        from empleados.sancion_utils import sancion_activa
        return sancion_activa(empleado)

    @staticmethod
    def _fechas_objetivo(post, tipo_nombre: str) -> list:
        """Fechas concretas que la solicitud agenda (para el cierre semanal). CT PERMANENTE expande
        el rango × días de la semana; el resto usa las fechas puntuales del POST."""
        from datetime import datetime as _dt, timedelta as _td
        if tipo_nombre == 'CT PERMANENTE':
            try:
                d0 = _dt.strptime(post.get('fecha_inicio'), '%Y-%m-%d').date()
                d1 = _dt.strptime(post.get('fecha_fin'), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return SolicitudRequestParser.get_fechas_del_post(post)
            try:
                dias = set(json.loads(post.get('dias_seleccionados', '{}') or '{}').get('dias_semana', []))
            except (json.JSONDecodeError, TypeError, AttributeError):
                dias = set()
            out, d = [], d0
            while d <= d1:
                if not dias or d.weekday() in dias:
                    out.append(d)
                d += _td(days=1)
            return out
        return SolicitudRequestParser.get_fechas_del_post(post)

    @classmethod
    def verificar_cierre(cls, fechas) -> JsonResponse | None:
        """Cierre semanal: bloquea si alguna fecha objetivo cae en una ventana cerrada habilitada."""
        try:
            from solicitudes.services.cierre_solicitudes_service import CierreSolicitudesService
            _f, msg = CierreSolicitudesService.validar_fechas([f for f in fechas if f])
            if msg:
                return json_error(msg, status=400, code='cierre_semanal')
        except Exception:
            logger.exception('Error verificando cierre semanal de solicitudes')
        return None

    @classmethod
    def verificar_sancion(cls, solicitante) -> JsonResponse | None:
        """Gestiona la sanción automática y bloquea si el SOLICITANTE está sancionado."""
        sancion = cls._refrescar_y_sancion(solicitante)
        if sancion:
            from empleados.sancion_utils import mensaje_sancion
            return json_error(mensaje_sancion(sancion), status=403, code='sancionado')
        return None

    @classmethod
    def verificar_sancion_receptor(cls, receptor) -> JsonResponse | None:
        """
        Bloquea si el COMPAÑERO/receptor está sancionado. Un sancionado no puede
        participar en NINGUNA solicitud ni siquiera como compañero: de lo contrario
        bastaría con que otro enviara la solicitud en su nombre para saltarse la sanción.
        """
        sancion = cls._refrescar_y_sancion(receptor)
        if sancion:
            nombre = getattr(receptor, 'nombre', None) or str(receptor)
            return json_error(
                f'El compañero {nombre} está sancionado y no puede participar en la solicitud. '
                'Elige otro compañero o espera a que termine su sanción.',
                status=403, code='sancionado_receptor')
        return None

    @staticmethod
    def verificar_restriccion(solicitante, receptor_ids: set, fechas: list, confirmar: bool) -> dict | None:
        """
        Verifica restricciones médicas activas sobre los exploradores involucrados.
        Retorna el payload de advertencia o None si no hay restricciones.
        """
        if confirmar or not fechas:
            return None

        from empleados.models import RestriccionEmpleado
        from django.db.models import Q

        fmin, fmax = min(fechas), max(fechas)
        vistos = {solicitante.id}
        emps = [solicitante]
        for rid in receptor_ids:
            try:
                emp = Empleado.objects.get(id=rid)
                if emp.id not in vistos:
                    emps.append(emp)
                    vistos.add(emp.id)
            except Empleado.DoesNotExist:
                pass

        advertencias = []
        for emp in emps:
            qs = RestriccionEmpleado.objects.filter(
                empleado=emp, fecha_inicio__lte=fmax,
            ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fmin))
            for r in qs:
                advertencias.append({
                    'explorador': f"{emp.nombre} {emp.apellido}",
                    'tipo': r.tipo_restriccion or 'Restricción',
                    'nota': r.recomendacion or '—',
                })

        if advertencias:
            return {
                'success': False,
                'code': 'advertencia_restriccion',
                'message': 'Hay una restricción médica vigente en las fechas. Revisa la nota antes de continuar.',
                'restricciones': advertencias,
            }
        return None

    # ------------------------------------------------------------------
    # Manejo de errores de validación
    # ------------------------------------------------------------------

    @staticmethod
    def _respuesta_error_validacion(mensaje: str) -> JsonResponse:
        """
        Convierte el mensaje de error del Factory en la respuesta JSON adecuada.
        Maneja el caso especial de 'requiere_cambio_turno_previo'.
        """
        try:
            error_data = json.loads(mensaje)
            if isinstance(error_data, dict) and error_data.get('code') == 'requiere_cambio_turno_previo':
                return JsonResponse({
                    'success': False,
                    'code': 'requiere_cambio_turno_previo',
                    'message': error_data.get('message', 'Se requiere cambio de turno previo'),
                    'fecha_pago': error_data.get('fecha_pago'),
                    'jornada_comun': error_data.get('jornada_comun'),
                }, status=400)
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        return json_error(mensaje, status=400, code='validation_error')

    # ------------------------------------------------------------------
    # DOBLADA PERMANENTE (flujo multi-compañero independiente)
    # ------------------------------------------------------------------

    @classmethod
    def _procesar_doblada_permanente_multi(cls, post, tipo_solicitud, solicitante, comentario) -> JsonResponse:
        """
        DOBLADA PERMANENTE con varios compañeros: agrupa días por compañero
        y crea una solicitud independiente por cada uno. Valida todo antes de crear ninguna.
        """
        if not comentario or not comentario.strip():
            return json_error('Ingresa un comentario.', status=400, code='missing_fields')

        from datetime import datetime as _dt

        fecha_inicio = post.get('fecha_inicio')
        fecha_fin = post.get('fecha_fin')

        # NUEVO flujo: fechas ESPECÍFICAS por compañero (listas paralelas). Tienen prioridad sobre
        # los weekdays; permiten balancear cuando los días de la semana tienen distinto número de
        # ocurrencias. Si no vienen, se usa el flujo antiguo por weekday (retrocompatible).
        ces_fechas = post.getlist('cesion_fecha')
        ces_fcomps = post.getlist('cesion_fecha_companero')
        dev_fechas = post.getlist('devolucion_fecha')
        dev_fcomps = post.getlist('devolucion_fecha_companero')
        usa_fechas = bool(ces_fechas)

        cesion_fechas_por_comp, devol_fechas_por_comp = {}, {}
        for f, comp in zip(ces_fechas, ces_fcomps):
            if comp and f:
                cesion_fechas_por_comp.setdefault(comp, set()).add(f)
        for f, comp in zip(dev_fechas, dev_fcomps):
            if comp and f:
                devol_fechas_por_comp.setdefault(comp, set()).add(f)

        # UNA fecha = UN solo compañero: una fecha no puede estar asignada a dos compañeros (ni en
        # cesión ni en devolución). Dos personas no pueden cubrir la misma jornada el mismo día, ni
        # se puede pagar la misma jornada dos veces ese día. (Cada solicitud se valida por separado,
        # así que este cruce entre compañeros hay que detectarlo aquí.)
        def _fecha_repetida(por_comp):
            vistas = set()
            for _c, _fset in por_comp.items():
                for _f in _fset:
                    if _f in vistas:
                        return _f
                    vistas.add(_f)
            return None
        _dup_c = _fecha_repetida(cesion_fechas_por_comp)
        _dup_d = _fecha_repetida(devol_fechas_por_comp)
        if _dup_c or _dup_d:
            _f = _dup_c or _dup_d
            try:
                _fmt = _dt.strptime(_f, '%Y-%m-%d').strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                _fmt = _f
            _accion = 'cubrirla' if _dup_c else 'pagarla'
            return json_error(
                f'La fecha {_fmt} está asignada a dos compañeros; una fecha solo puede {_accion} un '
                f'compañero (no puedes cubrir ni pagar la misma jornada el mismo día con dos personas).',
                status=400, code='validation_error')

        # Cierre semanal: ninguna fecha de cesión/devolución puede caer en una ventana cerrada.
        _cierre_fechas = []
        for _s in list(ces_fechas) + list(dev_fechas):
            try:
                _cierre_fechas.append(_dt.strptime(_s, '%Y-%m-%d').date())
            except (ValueError, TypeError):
                pass
        cierre_resp = cls.verificar_cierre(_cierre_fechas)
        if cierre_resp:
            return cierre_resp

        def _wd(iso):
            try:
                return str(_dt.strptime(iso, '%Y-%m-%d').date().weekday())
            except (ValueError, TypeError):
                return ''

        # Weekdays por compañero (derivados de las fechas si usa_fechas; del POST si back-compat).
        cesion_por_comp, devol_por_comp = {}, {}
        if usa_fechas:
            for comp, fset in cesion_fechas_por_comp.items():
                cesion_por_comp[comp] = {_wd(f) for f in fset if _wd(f)}
            for comp, fset in devol_fechas_por_comp.items():
                devol_por_comp[comp] = {_wd(f) for f in fset if _wd(f)}
        else:
            for dia, comp in zip(post.getlist('cesion_dia'), post.getlist('cesion_companero')):
                if comp and str(dia) != '':
                    cesion_por_comp.setdefault(comp, set()).add(str(dia))
            for dia, comp in zip(post.getlist('devolucion_dia'), post.getlist('devolucion_companero')):
                if comp and str(dia) != '':
                    devol_por_comp.setdefault(comp, set()).add(str(dia))

        base_ces = cesion_fechas_por_comp if usa_fechas else cesion_por_comp
        base_dev = devol_fechas_por_comp if usa_fechas else devol_por_comp
        if not base_ces:
            return json_error('Agrega al menos un día de cesión con su compañero',
                              status=400, code='missing_fields')
        for comp in base_dev:
            if comp not in base_ces:
                return json_error('Solo puedes devolverle a un compañero que te cubra.',
                                  status=400, code='validation_error')
        # BALANCE (bloqueo): por compañero, nº de FECHAS de cesión == nº de FECHAS de devolución.
        unidad = 'fechas' if usa_fechas else 'días'
        for comp, cset in base_ces.items():
            if len(base_dev.get(comp, set())) != len(cset):
                return json_error(
                    f'A cada compañero debes devolverle la misma cantidad de {unidad} que te cubre.',
                    status=400, code='validation_error')

        # Verificar restricción médica sobre el rango completo
        confirmar = str(post.get('confirmar_restriccion', '')).lower() in ('1', 'true', 'si', 'sí')
        try:
            from datetime import datetime as _dt
            fechas_rango = [
                _dt.strptime(fecha_inicio, '%Y-%m-%d').date(),
                _dt.strptime(fecha_fin, '%Y-%m-%d').date(),
            ]
        except (ValueError, TypeError):
            fechas_rango = []

        restriccion = cls.verificar_restriccion(
            solicitante, set(cesion_por_comp.keys()), fechas_rango, confirmar,
        )
        if restriccion:
            restriccion['message'] = 'Hay una restricción médica vigente en el rango. Revisa la nota antes de continuar.'
            return JsonResponse(restriccion, status=400)

        # Validar TODAS antes de crear ninguna (todo o nada)
        pendientes = []
        for comp_id, dias_c in cesion_por_comp.items():
            try:
                receptor = Empleado.objects.get(id=comp_id)
            except Empleado.DoesNotExist:
                return json_error('Compañero no válido.', status=400, code='validation_error')

            # Sanción del compañero: un sancionado no puede participar en la doblada.
            sancion_receptor_resp = cls.verificar_sancion_receptor(receptor)
            if sancion_receptor_resp:
                return sancion_receptor_resp

            datos = {
                'explorador_solicitante': solicitante,
                'explorador_receptor': receptor,
                'tipo_cambio': tipo_solicitud,
                'comentario': comentario,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'dias_cesion': sorted(dias_c),
                'dias_devolucion': sorted(devol_por_comp.get(comp_id, set())),
                'fechas_cesion': sorted(cesion_fechas_por_comp.get(comp_id, set())) if usa_fechas else [],
                'fechas_devolucion': sorted(devol_fechas_por_comp.get(comp_id, set())) if usa_fechas else [],
                'fecha_creacion_solicitud': timezone.now().date(),
            }
            es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_solicitud, datos)
            if not es_valida:
                return cls._respuesta_error_validacion(
                    f"{receptor.nombre} {receptor.apellido}: {mensaje}"
                    if '{' not in mensaje else mensaje
                )
            pendientes.append((receptor, datos))

        # Crear todas
        creadas = 0
        for receptor, datos in pendientes:
            solicitud, mensaje = SolicitudFactory.crear_solicitud(tipo_solicitud, datos)
            if solicitud is None:
                return json_error(
                    f"Error creando la solicitud para {receptor.nombre}: {mensaje}",
                    status=400, code='creation_failed')
            creadas += 1

        msg = (
            'Doblada permanente solicitada. Se notificó al compañero y al supervisor.'
            if creadas == 1 else
            f'Se crearon {creadas} solicitudes de doblada permanente (una por compañero). '
            f'Se notificó a cada uno y al supervisor.'
        )
        return json_ok({'message': msg, 'solicitudes_creadas': creadas}, status=201)

    # ------------------------------------------------------------------
    # Punto de entrada principal
    # ------------------------------------------------------------------

    @classmethod
    def procesar(cls, post, tipo_solicitud: TipoSolicitudCambio, solicitante) -> JsonResponse:
        """
        Flujo principal de creación de solicitud:
          1. Verificar sanción
          2. Despachar DOBLADA PERMANENTE (flujo propio multi-compañero)
          3. Verificar restricción médica
          4. Resolver receptor
          5. Parsear datos según tipo
          6. Validar con Factory
          7. Crear con Factory
        """
        tipo_nombre = tipo_solicitud.nombre
        comentario = post.get('comentarios', '')

        # 1. Sanción
        sancion_resp = cls.verificar_sancion(solicitante)
        if sancion_resp:
            return sancion_resp

        # 2. DOBLADA PERMANENTE multi-compañero (flujo independiente)
        if tipo_nombre == "DOBLADA PERMANENTE":
            return cls._procesar_doblada_permanente_multi(post, tipo_solicitud, solicitante, comentario)

        # 2b. Cierre semanal (programación del fin de semana ya cerrada)
        cierre_resp = cls.verificar_cierre(cls._fechas_objetivo(post, tipo_nombre))
        if cierre_resp:
            return cierre_resp

        # 3. Restricción médica
        confirmar = str(post.get('confirmar_restriccion', '')).lower() in ('1', 'true', 'si', 'sí')
        fechas = SolicitudRequestParser.get_fechas_del_post(post)
        receptor_ids = {v for c in ['empleado_receptor'] if (v := post.get(c))}
        restriccion = cls.verificar_restriccion(solicitante, receptor_ids, fechas, confirmar)
        if restriccion:
            return JsonResponse(restriccion, status=400)

        # 4. Resolver receptor
        receptor_id = post.get('empleado_receptor')
        if not receptor_id:
            return json_error('Debe seleccionar un compañero para el intercambio',
                              status=400, code='missing_fields')
        try:
            receptor = Empleado.objects.get(id=receptor_id)
        except Empleado.DoesNotExist:
            return json_error('El compañero seleccionado no existe.', status=400, code='validation_error')

        # 4b. Sanción del receptor: un sancionado no puede participar ni como compañero.
        sancion_receptor_resp = cls.verificar_sancion_receptor(receptor)
        if sancion_receptor_resp:
            return sancion_receptor_resp

        # 5. Parsear datos
        datos = SolicitudRequestParser.parse_datos(tipo_nombre, post, solicitante, receptor)
        datos['tipo_cambio'] = tipo_solicitud

        # 6. Validar
        es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_solicitud, datos)
        if not es_valida:
            return cls._respuesta_error_validacion(mensaje)

        # 7. Crear
        try:
            solicitud, mensaje = SolicitudFactory.crear_solicitud(tipo_solicitud, datos)
            if solicitud is None:
                return json_error(mensaje, status=400, code='creation_failed')
            logger.info("Solicitud %d creada — tipo=%s solicitante=%s receptor=%s",
                        solicitud.id, tipo_nombre, solicitante.id, receptor.id)
            return json_ok({
                'message': 'Solicitud enviada correctamente. Se han enviado notificaciones al supervisor y al compañero.',
                'solicitud_id': solicitud.id,
            }, status=201)
        except Exception:
            logger.exception("Error creando solicitud — tipo=%s solicitante=%s", tipo_nombre, solicitante.id)
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')
