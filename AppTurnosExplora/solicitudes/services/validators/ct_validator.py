from django.core.exceptions import ValidationError  # type: ignore
from empleados.models import Empleado


class CTValidator:
    """Validaciones específicas del Cambio de Turno sencillo (CT)."""

    @staticmethod
    def validar_jornada_contraria(solicitante: Empleado, receptor: Empleado, fecha, jornada_solicitante=None, jornada_receptor=None):
        """
        Validar que los empleados tengan jornadas contrarias.

        OPTIMIZACIÓN: Si se proporcionan las jornadas como parámetro, no se vuelven a consultar.
        Esto evita consultas duplicadas cuando ya se obtuvieron en validar_jornada_en_fecha.

        Args:
            solicitante: Empleado que solicita el cambio
            receptor: Empleado que recibe el cambio
            fecha: Fecha para verificar las jornadas
            jornada_solicitante: (Opcional) Jornada del solicitante ya obtenida
            jornada_receptor: (Opcional) Jornada del receptor ya obtenida
        """
        from turnos.services.jornada_service import JornadaService

        # Obtener jornadas solo si no se proporcionaron como parámetro
        if jornada_solicitante is None:
            jornada_solicitante = JornadaService.get_jornada_explorador_fecha(solicitante.id, fecha)
        if jornada_receptor is None:
            jornada_receptor = JornadaService.get_jornada_explorador_fecha(receptor.id, fecha)

        # NOTA: No validamos existencia aquí porque se garantiza que se llama después de validar_jornada_en_fecha
        # Si las jornadas son None, es un error de programación, no de validación de negocio

        # Verificar que tengan jornadas contrarias
        if jornada_solicitante and jornada_receptor and jornada_solicitante.nombre == jornada_receptor.nombre:
            raise ValidationError('No se puede cambiar por la misma jornada. Los empleados deben tener jornadas contrarias')

    @staticmethod
    def validar_no_domingo_por_semana(fecha, es_cambio_permanente=False):
        """
        Validar que no se esté cambiando domingo por día de semana.
        Para CT PERMANENTE: NO permitir domingos (regla de negocio estricta)

        Args:
            fecha: Fecha a validar
            es_cambio_permanente: Si es True, validar estrictamente (NO permitir domingos)
        """
        from datetime import datetime

        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, '%Y-%m-%d').date()

        # Para CT PERMANENTE: Validar estrictamente (NO permitir domingos)
        if es_cambio_permanente:
            if fecha.weekday() == 6:
                raise ValidationError('No se pueden realizar cambios permanentes en domingos')
            return True

        # Para CT normal: Mantener validación estricta
        if fecha.weekday() == 6:
            raise ValidationError('No se puede cambiar domingo por día de semana')

    @staticmethod
    def validar_no_sabado_ct_sencillo(fecha):
        """
        Validar que no se esté cambiando sábado en Cambio de Turno Sencillo.

        Args:
            fecha: Fecha a validar
        """
        from datetime import datetime

        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, '%Y-%m-%d').date()

        if fecha.weekday() == 5:  # Sábado
            raise ValidationError('No se puede cambiar sábado por día de semana')
