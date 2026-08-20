"""
SolicitudRequestParser

Responsabilidad única: extraer y normalizar datos de request.POST
según el tipo de solicitud. No contiene lógica de negocio.
"""
import logging
from core.utils.date_utils import DateUtils

logger = logging.getLogger(__name__)

_CAMPOS_FECHA = [
    'fecha_solicitud', 'fecha_cambio_turno', 'fecha_pago',
    'fecha_inicio', 'fecha_fin', 'fecha_pago_semana',
]


class SolicitudRequestParser:

    @staticmethod
    def _estrategia(tipo_nombre: str):
        """
        Strategy que atiende a `tipo_nombre`, buscada por NOMBRE.

        Aquí solo llega el nombre del tipo, no el objeto `TipoSolicitudCambio` que
        pide `SolicitudFactory.get_strategy`, así que se consulta el registro
        directamente. Si el tipo no está registrado se devuelve `CambioTurnoStrategy`,
        que es exactamente donde mandaba el `else` de las cadenas que había aquí.
        """
        from .solicitud_factory import SolicitudFactory
        from .strategies.cambio_turno_strategy import CambioTurnoStrategy

        clave = SolicitudFactory.normalize_name(tipo_nombre or '')
        clase = (SolicitudFactory._strategies.get(clave)
                 or SolicitudFactory._strategies.get((tipo_nombre or '').upper().strip())
                 or CambioTurnoStrategy)
        return clase()

    @staticmethod
    def validate_required(tipo_nombre: str, post) -> tuple:
        """
        Valida presencia de campos obligatorios por tipo.
        Retorna (ok: bool, error_msg: str). Falla rápido antes de tocar la BD.

        Aquí había una cadena `if tipo_nombre == ...` con seis ramas: cada tipo
        nuevo obligaba a editar este archivo. Ahora lo contesta la strategy, que es
        quien sabe qué campos necesita (Fase 2 de la auditoría).
        """
        return SolicitudRequestParser._estrategia(tipo_nombre).validar_campos_requeridos(post)

    @staticmethod
    def parse_datos(tipo_nombre: str, post, solicitante, receptor) -> dict:
        """
        Construye el dict datos_solicitud listo para SolicitudFactory.
        Asume que validate_required ya pasó. El caller agrega 'tipo_cambio'.

        Segunda cadena movida a las strategies en la Fase 2.
        """
        return SolicitudRequestParser._estrategia(tipo_nombre).parsear_datos(
            post, solicitante, receptor)

    @staticmethod
    def get_fechas_del_post(post) -> list:
        """Extrae todas las fechas del POST (restricciones médicas y cierre semanal).

        Usa `getlist` cuando está disponible: si un formulario envía varios valores con el mismo
        nombre, hay que validarlos TODOS, no solo el primero.
        """
        fechas = []
        getlist = getattr(post, 'getlist', None)
        for campo in _CAMPOS_FECHA:
            valores = getlist(campo) if getlist else [post.get(campo)]
            for v in valores:
                if not v:
                    continue
                try:
                    f = DateUtils.parse_date(v)
                except (ValueError, TypeError):
                    continue
                if f not in fechas:
                    fechas.append(f)
        return fechas
