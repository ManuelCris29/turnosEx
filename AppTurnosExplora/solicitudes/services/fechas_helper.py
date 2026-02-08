"""
Helper para analizar fechas de solicitudes de cambio de turno.
Proporciona información sobre fechas aplicables, excluidas y validaciones
para diferentes tipos de solicitudes.
"""
from datetime import date
from typing import Dict, List, Optional, Tuple
from empleados.models import Empleado
from turnos.models import DiaEspecial
from core.utils.jornada_utils import JornadaUtils
from turnos.services.jornada_service import JornadaService
import logging

logger = logging.getLogger(__name__)


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
        pass
    
    # Verificar mantenimiento
    try:
        resultado['es_mantenimiento'] = DiaEspecial.objects.filter(
            fecha=fecha,
            tipo='mantenimiento',
            activo=True
        ).exclude(es_temporada=True).exists()
        if resultado['es_mantenimiento']:
            resultado['razones_exclusion'].append('Mantenimiento')
    except Exception:
        pass
    
    # Verificar temporada
    try:
        resultado['es_temporada'] = DiaEspecial.objects.filter(
            fecha=fecha,
            es_temporada=True,
            activo=True
        ).exists()
        if resultado['es_temporada']:
            resultado['razones_exclusion'].append('Temporada')
    except Exception:
        pass
    
    # Verificar domingo (para CT y CT PERMANENTE)
    if resultado['es_domingo']:
        if tipo_solicitud in ['CT', 'CT PERMANENTE']:
            resultado['razones_exclusion'].append('Domingo')
    
    # Verificar sábado (solo para CT PERMANENTE)
    if resultado['es_sabado'] and tipo_solicitud == 'CT PERMANENTE':
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
            pass
    
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
            pass
    
    # Verificar dobladas activas (solo para CT)
    if tipo_solicitud == 'CT':
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
                pass
        
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
                pass
    
    # Determinar si es válida según el tipo
    if tipo_solicitud == 'CT PERMANENTE':
        # CT PERMANENTE: No permite festivos, mantenimiento, temporada, descansos, domingos, sábados
        resultado['valida'] = len(resultado['razones_exclusion']) == 0
    elif tipo_solicitud == 'CT':
        # CT: No permite mantenimiento, domingos, dobladas activas
        # Permite festivos si ambos tienen jornada
        exclusiones_ct = [r for r in resultado['razones_exclusion'] 
                         if r not in ['Festivo']]  # Festivos se permiten si hay jornada
        resultado['valida'] = len(exclusiones_ct) == 0
    elif tipo_solicitud in ['DOBLADA', 'D FDS']:
        # DOBLADA/D FDS: No permite mantenimiento, temporada
        # Permite festivos, descansos, domingos, sábados
        exclusiones_doblada = [r for r in resultado['razones_exclusion'] 
                              if r in ['Mantenimiento', 'Temporada']]
        resultado['valida'] = len(exclusiones_doblada) == 0
    else:
        # Otros tipos: Validar según reglas generales
        exclusiones_generales = [r for r in resultado['razones_exclusion'] 
                                if r in ['Mantenimiento', 'Temporada']]
        resultado['valida'] = len(exclusiones_generales) == 0
    
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





