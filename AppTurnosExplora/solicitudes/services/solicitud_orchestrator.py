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
    def verificar_sancion(solicitante) -> JsonResponse | None:
        """Gestiona la sanción automática y bloquea si el explorador está sancionado."""
        try:
            from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
            DeudaCorporativaService.gestionar_sancion_por_deuda(solicitante)
        except Exception:
            logger.exception('Error gestionando sanción automática por deuda de %s', solicitante.id)

        from empleados.sancion_utils import sancion_activa, mensaje_sancion
        sancion = sancion_activa(solicitante)
        if sancion:
            return json_error(mensaje_sancion(sancion), status=403, code='sancionado')
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

        fecha_inicio = post.get('fecha_inicio')
        fecha_fin = post.get('fecha_fin')
        ces_dias = post.getlist('cesion_dia')
        ces_comps = post.getlist('cesion_companero')
        dev_dias = post.getlist('devolucion_dia')
        dev_comps = post.getlist('devolucion_companero')

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
            return json_error('Agrega al menos un día de cesión con su compañero',
                              status=400, code='missing_fields')
        for comp in devol_por_comp:
            if comp not in cesion_por_comp:
                return json_error('Solo puedes devolverle a un compañero que te cubra.',
                                  status=400, code='validation_error')
        for comp, dias_c in cesion_por_comp.items():
            if len(devol_por_comp.get(comp, set())) != len(dias_c):
                return json_error(
                    'A cada compañero debes devolverle la misma cantidad de días que te cubre.',
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

            datos = {
                'explorador_solicitante': solicitante,
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
