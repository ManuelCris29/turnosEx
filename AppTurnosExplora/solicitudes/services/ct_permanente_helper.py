"""
Helper para calcular fechas aplicables de cambios permanentes.
Reutiliza la lógica de CTPermanenteStrategy para ser usada en otros contextos.
"""
from datetime import date, timedelta
from typing import List, Dict, Tuple
from empleados.models import Empleado
from turnos.models import DiaEspecial
from core.utils.jornada_utils import JornadaUtils
from turnos.services.jornada_service import JornadaService
from solicitudes.models import CambioPermanenteDetalle
import logging

logger = logging.getLogger(__name__)

_PRIORIDAD_RAZONES_CT_PERMANENTE = [
    # Más importante primero (opción 2: una sola razón por fecha)
    'Mantenimiento',
    'Festivo',
    'Temporada',
    'Descanso Solicitante',
    'Descanso Receptor',
    'Fines de semana',
]


def _razon_principal_ct_permanente(razones: List[str]) -> str:
    """
    Selecciona una sola razón principal (sin duplicar fechas en UI).
    Si no encuentra una razón conocida, retorna la primera.
    """
    if not razones:
        return ''
    for r in _PRIORIDAD_RAZONES_CT_PERMANENTE:
        if r in razones:
            return r
    return razones[0]


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
    
    # Separar días de semana y fechas específicas
    dias_semana_list = []
    fechas_especificas_list = []
    
    for dia_seleccionado in dias_seleccionados:
        if dia_seleccionado.tipo == 'dia_semana' and dia_seleccionado.dia_semana is not None:
            dias_semana_list.append(dia_seleccionado.dia_semana)
        elif dia_seleccionado.tipo == 'fecha_especifica' and dia_seleccionado.fecha_especifica:
            fechas_especificas_list.append(dia_seleccionado.fecha_especifica)
    
    # Procesar fechas específicas primero (tienen prioridad)
    if fechas_especificas_list:
        for fecha_obj in fechas_especificas_list:
            # Solo agregar si está dentro del rango y es lunes-viernes
            if fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                fechas_candidatas.add(fecha_obj)
    
    # Procesar días de semana (solo si no hay fechas específicas)
    if dias_semana_list and not fechas_especificas_list:
        for dia_semana_buscado in dias_semana_list:
            # Día de semana: generar todas las ocurrencias dentro del rango
            fecha_actual = fecha_inicio
            
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
    
    # Si no hay días seleccionados, usar rango completo (retrocompatibilidad)
    if not dias_semana_list and not fechas_especificas_list:
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


def calcular_fechas_aplicables_y_excluidas_ct_permanente(
    detalle: CambioPermanenteDetalle,
    solicitante: Empleado,
    receptor: Empleado
) -> Tuple[List[date], List[Dict[str, any]]]:
    """
    Calcula las fechas aplicables y excluidas para un cambio permanente.
    
    Args:
        detalle: Instancia de CambioPermanenteDetalle
        solicitante: Empleado solicitante
        receptor: Empleado receptor
        
    Returns:
        Tupla con:
        - Lista de fechas aplicables (válidas)
        - Lista de dicts con fechas excluidas: [{'fecha': date, 'razon': str}]
    """
    fecha_inicio = detalle.fecha_inicio
    fecha_fin = detalle.fecha_fin
    
    if not fecha_fin:
        # Si no hay fecha fin, usar fin de año
        fecha_fin = date(fecha_inicio.year, 12, 31)
    
    fechas_candidatas = set()
    
    # Obtener días seleccionados
    dias_seleccionados = detalle.dias.all()
    
    # Separar días de semana y fechas específicas
    dias_semana_list = []
    fechas_especificas_list = []
    
    for dia_seleccionado in dias_seleccionados:
        if dia_seleccionado.tipo == 'dia_semana' and dia_seleccionado.dia_semana is not None:
            dias_semana_list.append(dia_seleccionado.dia_semana)
        elif dia_seleccionado.tipo == 'fecha_especifica' and dia_seleccionado.fecha_especifica:
            fechas_especificas_list.append(dia_seleccionado.fecha_especifica)
    
    # Procesar fechas específicas primero (tienen prioridad)
    if fechas_especificas_list:
        for fecha_obj in fechas_especificas_list:
            # Solo agregar si está dentro del rango y es lunes-viernes
            if fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                fechas_candidatas.add(fecha_obj)
    
    # Procesar días de semana (solo si no hay fechas específicas)
    if dias_semana_list and not fechas_especificas_list:
        for dia_semana_buscado in dias_semana_list:
            # Día de semana: generar todas las ocurrencias dentro del rango
            fecha_actual = fecha_inicio
            
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
    
    # Si no hay días seleccionados, usar rango completo (retrocompatibilidad)
    if not dias_semana_list and not fechas_especificas_list:
        # IMPORTANTE: Solo lunes-viernes (excluir sábados y domingos)
        fecha_actual = fecha_inicio
        while fecha_actual <= fecha_fin:
            if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                fechas_candidatas.add(fecha_actual)
            fecha_actual += timedelta(days=1)

    # Incluir fines de semana como "excluidos" (para transparencia en vista previa / detalle),
    # sin alterar los aplicables (CT Permanente aplica solo lunes-viernes).
    fecha_actual = fecha_inicio
    while fecha_actual <= fecha_fin:
        if fecha_actual.weekday() in (5, 6):  # 5=sábado, 6=domingo
            fechas_candidatas.add(fecha_actual)
        fecha_actual += timedelta(days=1)
    
    # Filtrar fechas y registrar exclusiones
    fechas_aplicables = []
    fechas_excluidas = []
    
    for fecha_dia in sorted(list(fechas_candidatas)):
        razones_exclusion = []

        # Verificar fin de semana (regla estructural de CT Permanente)
        if fecha_dia.weekday() in (5, 6):
            razones_exclusion.append('Fines de semana')
        
        # Verificar festivo
        if _es_festivo(fecha_dia):
            razones_exclusion.append('Festivo')
        
        # Verificar mantenimiento
        if _es_mantenimiento(fecha_dia):
            razones_exclusion.append('Mantenimiento')
        
        # Verificar temporada
        if _es_temporada(fecha_dia):
            razones_exclusion.append('Temporada')
        
        # Verificar día de descanso del solicitante
        if _es_dia_descanso(solicitante, fecha_dia):
            razones_exclusion.append('Descanso Solicitante')
        
        # Verificar día de descanso del receptor
        if _es_dia_descanso(receptor, fecha_dia):
            razones_exclusion.append('Descanso Receptor')
        
        # Si hay razones de exclusión, agregar a excluidas
        if razones_exclusion:
            # Opción 2: una sola razón principal por fecha (sin razones compuestas)
            razon = _razon_principal_ct_permanente(razones_exclusion)
            fechas_excluidas.append({
                'fecha': fecha_dia,
                'razon': razon
            })
        else:
            # Si no hay razones, es una fecha aplicable
            fechas_aplicables.append(fecha_dia)
    
    return fechas_aplicables, fechas_excluidas


