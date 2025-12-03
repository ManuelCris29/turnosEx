"""
Helper para calcular fechas aplicables de cambios permanentes.
Reutiliza la lógica de CTPermanenteStrategy para ser usada en otros contextos.
"""
from datetime import date, timedelta
from typing import List
from empleados.models import Empleado
from turnos.models import DiaEspecial
from core.utils.jornada_utils import JornadaUtils
from turnos.services.jornada_service import JornadaService
from solicitudes.models import CambioPermanenteDetalle
import logging

logger = logging.getLogger(__name__)


def calcular_fechas_aplicables_ct_permanente(
    detalle: CambioPermanenteDetalle,
    solicitante: Empleado,
    receptor: Empleado
) -> List[date]:
    """
    Calcula las fechas aplicables para un cambio permanente, excluyendo
    domingos, festivos, mantenimiento, temporadas y días de descanso.
    
    Args:
        detalle: Instancia de CambioPermanenteDetalle
        solicitante: Empleado solicitante
        receptor: Empleado receptor
        
    Returns:
        Lista de fechas ordenadas donde se aplicará el cambio
    """
    fecha_inicio = detalle.fecha_inicio
    fecha_fin = detalle.fecha_fin
    
    if not fecha_fin:
        # Si no hay fecha fin, usar fin de año
        fecha_fin = date(fecha_inicio.year, 12, 31)
    
    fechas_candidatas = set()
    
    # Obtener días seleccionados
    dias_seleccionados = detalle.dias.all()
    
    if dias_seleccionados.exists():
        # Hay días seleccionados: usar solo esos
        for dia_seleccionado in dias_seleccionados:
            if dia_seleccionado.tipo == 'dia_semana' and dia_seleccionado.dia_semana is not None:
                # Día de semana: generar todas las ocurrencias dentro del rango
                fecha_actual = fecha_inicio
                dia_semana_buscado = dia_seleccionado.dia_semana
                
                # Avanzar hasta el primer día de la semana buscado
                dias_hasta_proximo = (dia_semana_buscado - fecha_actual.weekday()) % 7
                if dias_hasta_proximo > 0:
                    fecha_actual += timedelta(days=dias_hasta_proximo)
                
                # Agregar todas las ocurrencias del día de semana dentro del rango
                # IMPORTANTE: Solo agregar si es lunes-viernes (weekday 0-4)
                while fecha_actual <= fecha_fin:
                    if fecha_actual.weekday() < 5:  # 0-4 = lunes-viernes
                        fechas_candidatas.add(fecha_actual)
                    fecha_actual += timedelta(days=7)  # Siguiente semana
    else:
        # No hay días seleccionados: usar rango completo (retrocompatibilidad)
        # IMPORTANTE: Solo lunes-viernes (excluir sábados y domingos)
        fecha_actual = fecha_inicio
        while fecha_actual <= fecha_fin:
            if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                fechas_candidatas.add(fecha_actual)
            fecha_actual += timedelta(days=1)
    
    # Filtrar fechas inválidas (festivos, mantenimiento, descansos)
    fechas_finales = []
    for fecha_dia in sorted(list(fechas_candidatas)):
        es_domingo = fecha_dia.weekday() == 6
        es_festivo = _es_festivo(fecha_dia)
        es_mantenimiento = _es_mantenimiento(fecha_dia)
        es_temporada = _es_temporada(fecha_dia)
        es_descanso_solicitante = _es_dia_descanso(solicitante, fecha_dia)
        es_descanso_receptor = _es_dia_descanso(receptor, fecha_dia)
        
        if (not es_domingo and 
            not es_festivo and 
            not es_mantenimiento and
            not es_temporada and
            not es_descanso_solicitante and
            not es_descanso_receptor):
            fechas_finales.append(fecha_dia)
    
    return fechas_finales


def _es_festivo(fecha: date) -> bool:
    """Verificar si es festivo"""
    try:
        return DiaEspecial.objects.filter(fecha=fecha, tipo='festivo', activo=True).exists()
    except Exception:
        return False


def _es_mantenimiento(fecha: date) -> bool:
    """Verificar si es día de mantenimiento"""
    try:
        return DiaEspecial.objects.filter(fecha=fecha, tipo='mantenimiento', activo=True).exists()
    except Exception:
        return False

def _es_temporada(fecha: date) -> bool:
    """Verificar si es temporada"""
    try:
        return DiaEspecial.objects.filter(
            fecha=fecha,
            es_temporada=True,
            activo=True
        ).exists()
    except Exception:
        return False


def _es_dia_descanso(explorador: Empleado, fecha: date) -> bool:
    """Verificar si un explorador está descansando en una fecha específica"""
    try:
        jornada_base = JornadaService.get_jornada_explorador_fecha(explorador.id, fecha.strftime('%Y-%m-%d'))
        
        if not jornada_base:
            return False
        
        jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
        return jornada_dia == "Descanso"
    except Exception:
        return False


