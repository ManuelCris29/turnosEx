"""
SolicitudRequestParser

Responsabilidad única: extraer y normalizar datos de request.POST
según el tipo de solicitud. No contiene lógica de negocio.
"""
import json
import logging
from datetime import datetime
from django.utils import timezone

logger = logging.getLogger(__name__)

_CAMPOS_FECHA = [
    'fecha_solicitud', 'fecha_cambio_turno', 'fecha_pago',
    'fecha_inicio', 'fecha_fin', 'fecha_pago_semana',
]


class SolicitudRequestParser:

    @staticmethod
    def validate_required(tipo_nombre: str, post) -> tuple:
        """
        Valida presencia de campos obligatorios por tipo.
        Retorna (ok: bool, error_msg: str). Falla rápida antes de tocar la BD.
        """
        def missing(msg):
            return False, msg

        if tipo_nombre == "CT PERMANENTE":
            if not post.get('empleado_receptor'):
                return missing('Debe seleccionar un compañero para el intercambio')
            if not post.get('fecha_inicio'):
                return missing('La fecha de inicio es requerida')
            if not post.get('fecha_fin'):
                return missing('La fecha de fin es requerida')

        elif tipo_nombre == "DOBLADA":
            if not post.get('fecha_solicitud'):
                return missing('La fecha de cesión es requerida')
            if not post.get('empleado_receptor'):
                return missing('Debe seleccionar un compañero para cubrir la doblada')

        elif tipo_nombre == "D FDS":
            if not post.get('fecha_solicitud'):
                return missing('La fecha del fin de semana es requerida')
            if not post.get('empleado_receptor'):
                return missing('Debe seleccionar el compañero que se doblará el fin de semana')
            if not post.get('fecha_pago'):
                return missing('La fecha de pago es obligatoria (otro fin de semana del mismo mes).')

        elif tipo_nombre == "CAMBIO DESCANSO":
            if not post.get('fecha_solicitud'):
                return missing('El fin de semana que cambias es requerido')
            if not post.get('empleado_receptor'):
                return missing('Debe seleccionar el compañero con quien intercambia el descanso')
            if not post.get('fecha_pago'):
                return missing('El fin de semana de devolución es obligatorio (otro finde del mismo mes).')

        elif tipo_nombre == "DOBLADA PERMANENTE":
            if not post.get('fecha_inicio') or not post.get('fecha_fin'):
                return missing('El rango de fechas (inicio y fin) es obligatorio')
            if not post.getlist('cesion_companero'):
                return missing('Agrega al menos un día de cesión con su compañero')
            if not post.getlist('devolucion_companero'):
                return missing('Agrega al menos un día de devolución con su compañero')

        else:  # CT y tipos genéricos
            if not post.get('empleado_receptor'):
                return missing('Debe seleccionar un compañero para el intercambio')
            if not post.get('fecha_solicitud'):
                return missing('La fecha es requerida')

        return True, ''

    @staticmethod
    def parse_datos(tipo_nombre: str, post, solicitante, receptor) -> dict:
        """
        Construye el dict datos_solicitud listo para SolicitudFactory.
        Asume que validate_required ya pasó. El caller agrega 'tipo_cambio'.
        """
        fecha_solicitud = post.get('fecha_solicitud')
        comentario = post.get('comentarios', '')

        base = {
            'explorador_solicitante': solicitante,
            'comentario': comentario,
        }

        if tipo_nombre == "CT PERMANENTE":
            fecha_inicio = post.get('fecha_inicio')
            fecha_fin = post.get('fecha_fin')
            try:
                dias_seleccionados = json.loads(post.get('dias_seleccionados', '{}') or '{}')
            except (json.JSONDecodeError, TypeError):
                dias_seleccionados = {}
            return {**base,
                    'explorador_receptor': receptor,
                    'fecha_cambio_turno': fecha_inicio,
                    'fecha_inicio': fecha_inicio,
                    'fecha_fin': fecha_fin,
                    'dias_seleccionados': dias_seleccionados}

        elif tipo_nombre == "DOBLADA":
            jornada_cedida = post.get('jornada_cedida')
            # Inferir jornada_cedida si no viene del formulario (cesión desde jornada simple)
            if not jornada_cedida and fecha_solicitud:
                try:
                    from turnos.services.jornada_service import JornadaService
                    j = JornadaService.get_jornada_explorador_fecha(solicitante.id, fecha_solicitud)
                    jornada_cedida = j.nombre.upper()
                    logger.info("jornada_cedida inferida: %s para %s en %s",
                                jornada_cedida, solicitante.nombre, fecha_solicitud)
                except Exception:
                    logger.warning("No se pudo inferir jornada_cedida para %s en %s",
                                   solicitante.nombre, fecha_solicitud)

            return {**base,
                    'explorador_receptor': receptor,
                    'fecha_cambio_turno': fecha_solicitud,
                    'fecha_pago': post.get('fecha_pago'),
                    'jornada_cedida': jornada_cedida,
                    'jornada_pago_sabado': post.get('jornada_pago_sabado'),
                    'jornada_cubre_en_pago': post.get('jornada_cubre_en_pago'),
                    'fecha_pago_semana': post.get('fecha_pago_semana'),
                    'tipo_cesion': post.get('tipo_cesion', 'cesion_completa'),
                    'fecha_creacion_solicitud': timezone.now().date()}

        elif tipo_nombre in ("D FDS", "CAMBIO DESCANSO"):
            return {**base,
                    'explorador_receptor': receptor,
                    'fecha_cambio_turno': fecha_solicitud,
                    'fecha_pago': post.get('fecha_pago'),
                    # Sub-modalidades de CAMBIO DESCANSO entre semana (temporada)
                    'submodalidad_semana': post.get('submodalidad_semana'),
                    'tipo_cesion': post.get('tipo_cesion'),
                    'jornada_cedida': post.get('jornada_cedida'),
                    'fecha_creacion_solicitud': timezone.now().date()}

        elif tipo_nombre == "DOBLADA PERMANENTE":
            dias_cesion = (post.getlist('dias_cesion')
                           or [d for d in post.get('dias_cesion', '').split(',') if d.strip()])
            dias_devolucion = (post.getlist('dias_devolucion')
                               or [d for d in post.get('dias_devolucion', '').split(',') if d.strip()])
            return {**base,
                    'explorador_receptor': receptor,
                    'fecha_inicio': post.get('fecha_inicio'),
                    'fecha_fin': post.get('fecha_fin'),
                    'dias_cesion': [d for d in dias_cesion if str(d).strip()],
                    'dias_devolucion': [d for d in dias_devolucion if str(d).strip()],
                    'fecha_creacion_solicitud': timezone.now().date()}

        else:  # CT y otros
            return {**base,
                    'explorador_receptor': receptor,
                    'fecha_cambio_turno': fecha_solicitud}

    @staticmethod
    def get_fechas_del_post(post) -> list:
        """Extrae todas las fechas del POST para verificación de restricciones médicas."""
        fechas = []
        for campo in _CAMPOS_FECHA:
            v = post.get(campo)
            if v:
                try:
                    fechas.append(datetime.strptime(v, '%Y-%m-%d').date())
                except (ValueError, TypeError):
                    pass
        return fechas
