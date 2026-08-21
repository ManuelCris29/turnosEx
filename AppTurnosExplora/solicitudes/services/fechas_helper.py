"""
Helper para analizar fechas de solicitudes de cambio de turno.
Proporciona información sobre fechas aplicables, excluidas y validaciones
para diferentes tipos de solicitudes.
"""
from datetime import date
from typing import Dict, Optional
from empleados.models import Empleado
from turnos.models import DiaEspecial
from core.utils.jornada_utils import JornadaUtils
from turnos.services.jornada_service import JornadaService
import logging

logger = logging.getLogger(__name__)


def _estrategia_de(tipo_solicitud):
    """
    Strategy del tipo, buscada por NOMBRE, o None si no hay ninguna registrada.

    SIN la caida por defecto de `SolicitudFactory.get_strategy`: esa devuelve
    CambioTurnoStrategy para lo desconocido, y aqui eso convertiria un tipo no
    contemplado en el MAS ESTRICTO de todos, cuando la cadena original lo trataba
    con la regla permisiva. Es al reves que en `views/detalle.py` y en
    `solicitud_request_parser.py`, donde el `else` si mandaba a CAMBIO TURNO.

    Tampoco se filtra por `activo`: aqui solo llega el nombre del tipo, y de todas
    formas que un tipo ya no admita solicitudes nuevas no cambia sus reglas.
    """
    from solicitudes.services.solicitud_factory import SolicitudFactory

    clave = SolicitudFactory.normalize_name(tipo_solicitud or '')
    clase = (SolicitudFactory._strategies.get(clave)
             or SolicitudFactory._strategies.get((tipo_solicitud or '').upper().strip()))
    return clase() if clase else None


def _validez_por_tipo(tipo_solicitud, analisis) -> bool:
    """Regla de validez del tipo, o la generica si no hay strategy."""
    from solicitudes.services.strategies.base_strategy import SolicitudStrategy

    estrategia = _estrategia_de(tipo_solicitud)
    if estrategia is None:
        return SolicitudStrategy.fecha_valida_generica(analisis)
    return estrategia.fecha_valida(analisis)


def analizar_fecha_solicitud(
    fecha: date,
    solicitante: Optional[Empleado] = None,
    receptor: Optional[Empleado] = None,
    tipo_solicitud: str = 'CT'
) -> Dict[str, any]:
    """
    Analiza una fecha específica para una solicitud y determina si es válida
    y qué restricciones aplican.
    
    Args:
        fecha: Fecha a analizar
        solicitante: Empleado solicitante (opcional)
        receptor: Empleado receptor (opcional)
        tipo_solicitud: Tipo de solicitud ('CT', 'DOBLADA', 'D FDS', etc.)
        
    Returns:
        Dict con:
        - 'valida': bool - Si la fecha es válida para el tipo de solicitud
        - 'razones_exclusion': List[str] - Razones por las que está excluida (si aplica)
        - 'es_festivo': bool
        - 'es_mantenimiento': bool
        - 'es_temporada': bool
        - 'es_domingo': bool
        - 'es_sabado': bool
        - 'es_descanso_solicitante': bool
        - 'es_descanso_receptor': bool
        - 'tiene_doblada_solicitante': bool
        - 'tiene_doblada_receptor': bool
        - 'tiene_jornada_solicitante': bool
        - 'tiene_jornada_receptor': bool
    """
    resultado = {
        'valida': True,
        'razones_exclusion': [],
        'es_festivo': False,
        'es_mantenimiento': False,
        'es_temporada': False,
        'es_domingo': fecha.weekday() == 6,
        'es_sabado': fecha.weekday() == 5,
        'es_descanso_solicitante': False,
        'es_descanso_receptor': False,
        'tiene_doblada_solicitante': False,
        'tiene_doblada_receptor': False,
        'tiene_jornada_solicitante': False,
        'tiene_jornada_receptor': False
    }
    
    # Verificar festivo
    try:
        resultado['es_festivo'] = DiaEspecial.objects.filter(
            fecha=fecha, 
            tipo='festivo', 
            activo=True
        ).exists()
        if resultado['es_festivo']:
            resultado['razones_exclusion'].append('Festivo')
    except Exception:
        logger.warning("Error verificando festivo (fecha=%s)", fecha, exc_info=True)
    
    # Verificar mantenimiento EFECTIVO (la temporada manda sobre el mantenimiento)
    try:
        resultado['es_mantenimiento'] = DiaEspecial.es_mantenimiento_efectivo(fecha)
        if resultado['es_mantenimiento']:
            resultado['razones_exclusion'].append('Mantenimiento')
    except Exception:
        logger.warning("Error verificando mantenimiento (fecha=%s)", fecha, exc_info=True)
    
    # Verificar temporada
    try:
        resultado['es_temporada'] = DiaEspecial.es_temporada_en(fecha)
        if resultado['es_temporada']:
            resultado['razones_exclusion'].append('Temporada')
    except Exception:
        logger.warning("Error verificando temporada (fecha=%s)", fecha, exc_info=True)
    
    # Fin de semana: lo declara cada strategy (`excluye_fin_de_semana`), no este
    # archivo. Un cambio de turno intercambia AM por PM, y en sábado o domingo manda
    # la alternancia de findes: no hay dos jornadas que intercambiar. Una DOBLADA sí
    # vale, porque no intercambia sino que CUBRE.
    _estrategia = _estrategia_de(tipo_solicitud)
    if _estrategia is not None and _estrategia.excluye_fin_de_semana:
        if resultado['es_domingo']:
            resultado['razones_exclusion'].append('Domingo')
        if resultado['es_sabado']:
            resultado['razones_exclusion'].append('Sábado')
    
    # Verificar descanso del solicitante
    if solicitante:
        try:
            jornada_base = JornadaService.get_jornada_explorador_fecha(
                solicitante.id, 
                fecha.strftime('%Y-%m-%d')
            )
            if jornada_base:
                resultado['tiene_jornada_solicitante'] = True
                jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
                if jornada_dia == "Descanso":
                    resultado['es_descanso_solicitante'] = True
                    resultado['razones_exclusion'].append('Descanso Solicitante')
        except Exception:
            logger.warning("Error verificando descanso del solicitante (fecha=%s)", fecha, exc_info=True)
    
    # Verificar descanso del receptor
    if receptor:
        try:
            jornada_base = JornadaService.get_jornada_explorador_fecha(
                receptor.id, 
                fecha.strftime('%Y-%m-%d')
            )
            if jornada_base:
                resultado['tiene_jornada_receptor'] = True
                jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
                if jornada_dia == "Descanso":
                    resultado['es_descanso_receptor'] = True
                    resultado['razones_exclusion'].append('Descanso Receptor')
        except Exception:
            logger.warning("Error verificando descanso del receptor (fecha=%s)", fecha, exc_info=True)
    
    # Doblada activa: también lo declara la strategy (`excluye_doblada_activa`).
    # Quien ya tiene una doblada ese día trabaja AM+PM y no le queda jornada libre
    # que intercambiar.
    if _estrategia is not None and _estrategia.excluye_doblada_activa:
        if solicitante:
            try:
                from solicitudes.models import SolicitudCambio
                resultado['tiene_doblada_solicitante'] = SolicitudCambio.objects.filter(
                    explorador_solicitante=solicitante,
                    tipo_cambio__nombre='DOBLADA',
                    fecha_cambio_turno=fecha,
                    estado='aprobada'
                ).exists()
                if resultado['tiene_doblada_solicitante']:
                    resultado['razones_exclusion'].append('Doblada Activa (Solicitante)')
            except Exception:
                logger.warning("Error verificando doblada activa del solicitante (fecha=%s)", fecha, exc_info=True)
        
        if receptor:
            try:
                from solicitudes.models import SolicitudCambio
                resultado['tiene_doblada_receptor'] = SolicitudCambio.objects.filter(
                    explorador_solicitante=receptor,
                    tipo_cambio__nombre='DOBLADA',
                    fecha_cambio_turno=fecha,
                    estado='aprobada'
                ).exists()
                if resultado['tiene_doblada_receptor']:
                    resultado['razones_exclusion'].append('Doblada Activa (Receptor)')
            except Exception:
                logger.warning("Error verificando doblada activa del receptor (fecha=%s)", fecha, exc_info=True)
    
    # Validez segun el tipo: la contesta la STRATEGY.
    #
    # Aqui habia una cadena `if tipo_solicitud == ...` con cinco ramas. La regla de
    # cada tipo vivia por duplicado -una vez en su strategy, que decide si la
    # solicitud se puede crear, y otra aqui, que decide lo que ve el supervisor- y
    # las dos copias llegaron a CONTRADECIRSE: esta pantalla daba por valido un CT
    # en festivo y en sabado que el motor rechazaba (corregido el 2026-08-20).
    #
    # OJO con la caida por defecto: el `else` de esta cadena era el GENERICO
    # PERMISIVO (solo mantenimiento y temporada), no el de CAMBIO TURNO. Es al reves
    # que en `views/detalle.py` y en `solicitud_request_parser.py`. Por eso aqui NO
    # se cae a CambioTurnoStrategy: sin strategy se aplica la regla generica, que es
    # lo que hacia el `else`.
    resultado['valida'] = _validez_por_tipo(tipo_solicitud, resultado)

    return resultado


def obtener_informacion_fecha_para_detalle(
    fecha: date,
    solicitante: Optional[Empleado] = None,
    receptor: Optional[Empleado] = None,
    tipo_solicitud: str = 'CT'
) -> Dict[str, any]:
    """
    Obtiene información detallada de una fecha para mostrar en el detalle de solicitud.
    
    Args:
        fecha: Fecha a analizar
        solicitante: Empleado solicitante (opcional)
        receptor: Empleado receptor (opcional)
        tipo_solicitud: Tipo de solicitud
        
    Returns:
        Dict con información formateada para mostrar en el frontend
    """
    analisis = analizar_fecha_solicitud(fecha, solicitante, receptor, tipo_solicitud)
    
    return {
        'fecha': fecha.strftime('%d/%m/%Y'),
        'valida': analisis['valida'],
        'razones_exclusion': analisis['razones_exclusion'],
        'informacion': {
            'es_festivo': analisis['es_festivo'],
            'es_mantenimiento': analisis['es_mantenimiento'],
            'es_temporada': analisis['es_temporada'],
            'es_domingo': analisis['es_domingo'],
            'es_sabado': analisis['es_sabado'],
            'es_descanso_solicitante': analisis['es_descanso_solicitante'],
            'es_descanso_receptor': analisis['es_descanso_receptor'],
            'tiene_doblada_solicitante': analisis['tiene_doblada_solicitante'],
            'tiene_doblada_receptor': analisis['tiene_doblada_receptor'],
            'tiene_jornada_solicitante': analisis['tiene_jornada_solicitante'],
            'tiene_jornada_receptor': analisis['tiene_jornada_receptor']
        }
    }








