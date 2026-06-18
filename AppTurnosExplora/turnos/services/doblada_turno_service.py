"""
Servicio para gestión de turnos específicos de dobladas.

Responsabilidad única: Crear y eliminar turnos relacionados con dobladas,
manejando la lógica de salas y jornadas de forma centralizada.
"""
from typing import Optional, Tuple
from django.core.exceptions import ValidationError
from django.db import transaction
from turnos.models import Turno, Jornada, Sala
from empleados.models import Empleado
from turnos.services.turno_service import TurnoService
from datetime import date
import logging

logger = logging.getLogger(__name__)


class DobladaTurnoService:
    """
    Servicio para gestión de turnos de dobladas.
    
    Responsabilidad única: Operaciones sobre turnos relacionados con dobladas.
    """
    
    @staticmethod
    def obtener_sala_explorador_fecha(explorador: Empleado, fecha: date) -> Sala:
        """
        Obtiene la sala del explorador para una fecha específica.
        
        Prioridad:
        1. Sala del turno existente en esa fecha
        2. Sala de asignación especial activa
        3. Primera sala de competencia del explorador
        
        Args:
            explorador: Explorador para el cual obtener la sala
            fecha: Fecha para la cual obtener la sala
        
        Returns:
            Instancia de Sala
        
        Raises:
            ValidationError: Si no se encuentra ninguna sala asignada
        """
        # 1. Buscar sala del turno existente en esa fecha
        turno_existente = Turno.objects.filter(
            explorador=explorador,
            fecha=fecha
        ).select_related('sala').first()
        
        if turno_existente:
            return turno_existente.sala
        
        # 2. Usar primera sala de competencia (la sala es informativa: especialidad del explorador)
        from empleados.models import CompetenciaEmpleado
        competencia = CompetenciaEmpleado.objects.filter(
            empleado=explorador
        ).select_related('sala').first()
        
        if competencia:
            return competencia.sala
        
        # Si no hay sala, lanzar error
        raise ValidationError(
            f'Explorador {explorador.nombre} no tiene sala asignada para la fecha {fecha}'
        )
    
    @staticmethod
    def crear_doblada_completa(
        explorador: Empleado,
        fecha: date,
        jornada_base: Jornada,
        jornada_adicional: Jornada,
        tipo_cambio: str = 'DOBLADA'
    ) -> Tuple[Turno, Turno]:
        """
        Crea una doblada completa (ambos turnos) cuando el explorador no tiene turnos en esa fecha.
        
        Args:
            explorador: Explorador que realizará la doblada
            fecha: Fecha de la doblada
            jornada_base: Jornada base del explorador (su jornada predeterminada)
            jornada_adicional: Jornada adicional (la que se agrega para la doblada)
            tipo_cambio: Tipo de cambio (default: 'DOBLADA')
        
        Returns:
            Tupla con (turno_base, turno_adicional)
        
        Raises:
            ValidationError: Si no se puede obtener la sala del explorador
        """
        # Obtener sala del explorador
        sala = DobladaTurnoService.obtener_sala_explorador_fecha(explorador, fecha)
        
        # Crear turno con jornada base
        turno_base = Turno.objects.create(
            explorador=explorador,
            fecha=fecha,
            jornada=jornada_base,
            sala=sala,
            tipo_cambio=tipo_cambio
        )
        
        # Crear turno con jornada adicional (doblada)
        turno_adicional = Turno.objects.create(
            explorador=explorador,
            fecha=fecha,
            jornada=jornada_adicional,
            sala=sala,
            tipo_cambio=tipo_cambio
        )
        
        logger.info(
            f"Doblada completa creada: {explorador.nombre} - {fecha} - "
            f"{jornada_base.nombre} + {jornada_adicional.nombre}"
        )
        
        return turno_base, turno_adicional
    
    @staticmethod
    def agregar_jornada_a_doblada(
        explorador: Empleado,
        fecha: date,
        jornada_adicional: Jornada,
        tipo_cambio: str = 'DOBLADA'
    ) -> Turno:
        """
        Agrega una jornada adicional a un turno existente (para crear doblada parcial).
        
        Verifica que la jornada adicional no exista ya en los turnos del explorador.
        
        Args:
            explorador: Explorador que realizará la doblada
            fecha: Fecha de la doblada
            jornada_adicional: Jornada adicional a agregar
            tipo_cambio: Tipo de cambio (default: 'DOBLADA')
        
        Returns:
            Instancia de Turno creada
        
        Raises:
            ValidationError: Si la jornada adicional ya existe o no se puede obtener la sala
        """
        # Verificar que no exista ya la jornada adicional
        turno_existente = Turno.objects.filter(
            explorador=explorador,
            fecha=fecha,
            jornada=jornada_adicional
        ).first()
        
        if turno_existente:
            raise ValidationError(
                f'El explorador {explorador.nombre} ya tiene turno con jornada '
                f'{jornada_adicional.nombre} en la fecha {fecha}'
            )
        
        # Obtener sala del turno existente o del explorador
        turno_anterior = Turno.objects.filter(
            explorador=explorador,
            fecha=fecha
        ).select_related('sala').first()
        
        if turno_anterior:
            sala = turno_anterior.sala
        else:
            sala = DobladaTurnoService.obtener_sala_explorador_fecha(explorador, fecha)
        
        # Crear turno con jornada adicional
        turno_adicional = Turno.objects.create(
            explorador=explorador,
            fecha=fecha,
            jornada=jornada_adicional,
            sala=sala,
            tipo_cambio=tipo_cambio
        )
        
        logger.info(
            f"Jornada adicional agregada: {explorador.nombre} - {fecha} - {jornada_adicional.nombre}"
        )
        
        return turno_adicional
    
    @staticmethod
    @transaction.atomic
    def eliminar_turnos_explorador(explorador: Empleado, fecha: date) -> int:
        """
        Elimina todos los turnos de un explorador en una fecha específica.
        
        Útil cuando un explorador descansa (en fecha de cesión o pago de doblada).
        
        Args:
            explorador: Explorador cuyos turnos se eliminarán
            fecha: Fecha para la cual eliminar los turnos
        
        Returns:
            Número de turnos eliminados
        """
        turnos_eliminados = Turno.objects.filter(
            explorador=explorador,
            fecha=fecha
        ).delete()[0]
        
        if turnos_eliminados > 0:
            logger.info(
                f"Turnos eliminados: {explorador.nombre} - {fecha} - {turnos_eliminados} turno(s)"
            )
        
        return turnos_eliminados
    
    @staticmethod
    def tiene_jornada_en_fecha(explorador: Empleado, fecha: date, jornada: Jornada) -> bool:
        """
        Verifica si un explorador tiene un turno con una jornada específica en una fecha.
        
        Args:
            explorador: Explorador a verificar
            fecha: Fecha a verificar
            jornada: Jornada a verificar
        
        Returns:
            True si tiene el turno, False en caso contrario
        """
        return Turno.objects.filter(
            explorador=explorador,
            fecha=fecha,
            jornada=jornada
        ).exists()
    
    @staticmethod
    def obtener_jornadas_en_fecha(explorador: Empleado, fecha: date) -> list[str]:
        """
        Obtiene las jornadas (nombres) que tiene un explorador en una fecha.
        
        Args:
            explorador: Explorador a verificar
            fecha: Fecha a verificar
        
        Returns:
            Lista de nombres de jornadas (ej: ['AM', 'PM'])
        """
        turnos = Turno.objects.filter(
            explorador=explorador,
            fecha=fecha
        ).select_related('jornada')
        
        return [t.jornada.nombre.upper() for t in turnos]

