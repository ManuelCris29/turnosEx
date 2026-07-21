from django.core.exceptions import ValidationError  # type: ignore
from empleados.models import Empleado


class BaseValidator:
    """Validaciones transversales, compartidas por varios tipos de solicitud
    (CT, CT Permanente, Doblada, Doblada Permanente, D FDS, Cambio Descanso)."""

    @staticmethod
    def validar_empleado_activo(empleado: Empleado):
        if not empleado or not getattr(empleado, 'activo', False):
            raise ValidationError('El empleado no está activo')

    @staticmethod
    def validar_no_mismo_empleado(solicitante: Empleado, receptor: Empleado):
        if solicitante.id == receptor.id:
            raise ValidationError('No puedes solicitar cambio contigo mismo')

    @staticmethod
    def validar_duplicada_misma_fecha(solicitante: Empleado, receptor: Empleado, fecha):
        """
        Valida que no exista una solicitud pendiente del mismo par (solicitante-receptor-fecha).

        FASE 1.13: Esta validación permite que múltiples solicitantes envíen solicitudes
        al mismo receptor para la misma fecha (First-Come, First-Served).
        Solo previene que el mismo solicitante envíe múltiples solicitudes al mismo receptor.

        Ejemplos permitidos:
        - A→X, fecha 15/12 → ✅ Permite
        - B→X, fecha 15/12 → ✅ Permite (diferente solicitante)
        - C→X, fecha 15/12 → ✅ Permite (diferente solicitante)

        Ejemplos rechazados:
        - A→X, fecha 15/12 (segunda vez) → ❌ Rechaza (mismo par)
        """
        from solicitudes.models import SolicitudCambio
        existe = SolicitudCambio.objects.filter(
            explorador_solicitante=solicitante,
            explorador_receptor=receptor,
            estado='pendiente',
            fecha_cambio_turno=fecha
        ).exists()
        if existe:
            raise ValidationError('Ya existe una solicitud pendiente tuya con este explorador para la misma fecha')

    @staticmethod
    def validar_no_dia_mantenimiento(fecha):
        """
        Validar que no sea día de mantenimiento.

        Args:
            fecha: Fecha a validar (puede ser string YYYY-MM-DD o date object)

        Raises:
            ValidationError: Si la fecha es un día de mantenimiento activo
        """
        from datetime import datetime
        try:
            from turnos.models import DiaEspecial

            if isinstance(fecha, str):
                fecha = datetime.strptime(fecha, '%Y-%m-%d').date()

            # Verificar si es día de mantenimiento EFECTIVO.
            # La temporada manda: si la fecha cae en temporada, NO se considera mantenimiento.
            es_mantenimiento = DiaEspecial.es_mantenimiento_efectivo(fecha)

            if es_mantenimiento:
                # Obtener descripción del día de mantenimiento para mensaje más informativo
                dia_mantenimiento = DiaEspecial.objects.filter(
                    fecha=fecha,
                    tipo='mantenimiento',
                    activo=True
                ).first()

                descripcion = dia_mantenimiento.descripcion if dia_mantenimiento and dia_mantenimiento.descripcion else 'Día de mantenimiento'
                raise ValidationError(f'No se pueden realizar cambios de turno en días de mantenimiento. {descripcion}')

        except ImportError:
            # Si no existe el modelo, no validar
            pass
        except ValueError:
            # Si la fecha no es válida, no validar (otra validación la manejará)
            pass

    # ===== VALIDACIONES ESPECÍFICAS PARA CAMBIO TURNO (CT) =====

    @staticmethod
    def validar_no_doblada_activa(empleado: Empleado, fecha, mensaje=None):
        """
        Validar que el empleado no tenga una doblada activa (AM + PM) para la fecha especificada.

        Si un explorador tiene doblada para una fecha (ya sea como solicitante o receptor),
        no puede realizar cambios de turno adicionales para esa misma fecha.

        Esta validación busca directamente en turnos_turno para detectar si el empleado
        tiene AM + PM en la fecha, sin importar cómo llegó a tener esa doblada.

        Args:
            empleado: Empleado a validar
            fecha: Fecha a validar (puede ser string o date)
            mensaje: Texto de error a usar si hay doblada (opcional). Permite a cada formulario
                dar un mensaje contextual; por defecto usa el genérico (que remite a la Solicitud
                de Dobladas, apropiado solo cuando se llama desde OTROS tipos de cambio).

        Raises:
            ValidationError: Si el empleado tiene una doblada (AM + PM) para esa fecha
        """
        from datetime import datetime
        from turnos.models import Turno

        # Convertir fecha a date si es string
        if isinstance(fecha, str):
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        elif hasattr(fecha, 'strftime'):
            fecha_obj = fecha
        else:
            # Si no se puede convertir, no validar (evitar errores)
            return

        # CORRECCIÓN: Buscar directamente en turnos_turno si tiene AM + PM (doblada real)
        # Esto detecta dobladas sin importar si el empleado fue solicitante o receptor
        turnos = Turno.objects.filter(
            explorador=empleado,
            fecha=fecha_obj
        ).select_related('jornada')

        jornadas = [t.jornada.nombre.upper() for t in turnos]

        # Si tiene AM + PM, es una doblada real (jornada completa)
        if 'AM' in jornadas and 'PM' in jornadas:
            raise ValidationError(
                mensaje or (
                    'No se puede realizar esta solicitud porque el explorador ya tiene '
                    'una jornada doblada (AM + PM) para el '
                    f'{fecha_obj.strftime("%d/%m/%Y")}. '
                    'Este tipo de caso debe gestionarse mediante la Solicitud de Dobladas, no mediante otros tipos de cambio.'
                )
            )

    # ===== VALIDACIONES ESPECÍFICAS PARA FESTIVOS Y ROTACIÓN =====

    @staticmethod
    def es_festivo_semana(fecha):
        """
        Verifica si una fecha es un festivo activo de lunes a viernes.

        Args:
            fecha: Fecha a verificar (date o string YYYY-MM-DD)

        Returns:
            bool: True si es festivo de lunes a viernes, False en caso contrario
        """
        from datetime import datetime
        from turnos.models import DiaEspecial

        if isinstance(fecha, str):
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        else:
            fecha_obj = fecha

        # Verificar que sea lunes a viernes (weekday 0-4)
        if fecha_obj.weekday() > 4:
            return False

        return DiaEspecial.objects.filter(
            fecha=fecha_obj,
            tipo__iexact='festivo',
            activo=True
        ).exists()

    # ===== VALIDACIONES DE CAMPOS DE TEXTO =====

    @staticmethod
    def validar_comentario_obligatorio(comentario: str, contexto: str = 'la solicitud'):
        """
        Valida que el comentario no esté vacío.

        Args:
            comentario: Texto recibido desde el formulario.
            contexto: Texto descriptivo para el mensaje de error.

        Raises:
            ValidationError: Si el comentario está vacío o solo tiene espacios.
        """
        from django.core.exceptions import ValidationError

        if not comentario or not str(comentario).strip():
            raise ValidationError(f'Debes ingresar un comentario para {contexto}.')

    @staticmethod
    def validar_fecha_pago_mismo_mes_cesion(fecha_pago, fecha_cesion):
        """
        Caso A: La fecha de pago debe estar dentro del mismo mes calendario
        que la fecha de cesión.

        Regla de negocio: El pago puede ser antes o después de la cesión,
        pero siempre dentro del mismo mes. No se puede pagar en un mes diferente
        al mes en que se cede la jornada.

        Ejemplos:
        - Cesión 20/03/2026 → Pago 05/03/2026 ✓ (ambos en marzo, pago anticipado)
        - Cesión 20/03/2026 → Pago 28/02/2026 ✗ (febrero ≠ marzo)
        - Cesión 20/03/2026 → Pago 25/03/2026 ✓ (ambos en marzo)

        Args:
            fecha_pago: Fecha de pago (string o date)
            fecha_cesion: Fecha de cesión de la jornada (string o date)

        Raises:
            ValidationError: Si la fecha de pago está en un mes diferente al de la cesión
        """
        from core.utils.date_utils import DateUtils

        fecha_pago_obj = DateUtils.parse_date(fecha_pago)
        fecha_cesion_obj = DateUtils.parse_date(fecha_cesion)

        if fecha_pago_obj.year != fecha_cesion_obj.year or fecha_pago_obj.month != fecha_cesion_obj.month:
            raise ValidationError(
                f'La fecha de pago ({fecha_pago_obj.strftime("%d/%m/%Y")}) debe estar en el mismo mes '
                f'que la fecha de cesión ({fecha_cesion_obj.strftime("%d/%m/%Y")}). '
                f'Ambas fechas deben pertenecer al mes {fecha_cesion_obj.strftime("%m/%Y")}.'
            )

    @staticmethod
    def validar_receptor_sin_solicitud_pendiente_en_fecha(receptor: Empleado, fecha_cesion):
        """
        Caso C: El receptor no puede tener ninguna solicitud pendiente (sin aprobar ni cancelar)
        para la misma fecha de cesión.

        Regla de negocio: Una solicitud pendiente puede aprobarse o cancelarse después.
        Mientras esté pendiente, no se puede enviar otra solicitud que involucre al receptor
        para esa misma fecha, ya que podría generar conflictos al aprobarse ambas.

        Args:
            receptor: Empleado receptor de la doblada
            fecha_cesion: Fecha de cesión (string o date)

        Raises:
            ValidationError: Si el receptor ya tiene una solicitud pendiente en esa fecha
        """
        from datetime import datetime
        from django.db import models as db_models
        from solicitudes.models import SolicitudCambio

        if isinstance(fecha_cesion, str):
            fecha_cesion_obj = datetime.strptime(fecha_cesion, '%Y-%m-%d').date()
        else:
            fecha_cesion_obj = fecha_cesion

        tiene_pendiente = SolicitudCambio.objects.filter(
            db_models.Q(explorador_solicitante=receptor) | db_models.Q(explorador_receptor=receptor),
            estado='pendiente',
            fecha_cambio_turno=fecha_cesion_obj
        ).exists()

        if tiene_pendiente:
            raise ValidationError(
                f'El compañero receptor ya tiene una solicitud pendiente para el '
                f'{fecha_cesion_obj.strftime("%d/%m/%Y")}. '
                'Debe esperar a que esa solicitud sea aprobada o cancelada antes de '
                'enviar una nueva para esa misma fecha.'
            )

    @staticmethod
    def validar_solicitante_sin_solicitud_pendiente_en_fecha(solicitante: Empleado, fecha_cesion):
        """
        Caso D: El solicitante no puede tener ninguna solicitud pendiente para la misma
        fecha de cesión.

        Regla de negocio: Una solicitud pendiente puede aprobarse después y generar
        conflictos si simultáneamente otra solicitud para la misma fecha se aprueba.

        Args:
            solicitante: Empleado solicitante de la doblada
            fecha_cesion: Fecha de cesión (string o date)

        Raises:
            ValidationError: Si el solicitante ya tiene una solicitud pendiente en esa fecha
        """
        from datetime import datetime
        from django.db import models as db_models
        from solicitudes.models import SolicitudCambio

        if isinstance(fecha_cesion, str):
            fecha_cesion_obj = datetime.strptime(fecha_cesion, '%Y-%m-%d').date()
        else:
            fecha_cesion_obj = fecha_cesion

        tiene_pendiente = SolicitudCambio.objects.filter(
            db_models.Q(explorador_solicitante=solicitante) | db_models.Q(explorador_receptor=solicitante),
            estado='pendiente',
            fecha_cambio_turno=fecha_cesion_obj
        ).exists()

        if tiene_pendiente:
            raise ValidationError(
                f'Ya tienes una solicitud pendiente para el {fecha_cesion_obj.strftime("%d/%m/%Y")}. '
                'Debes esperar a que sea aprobada o cancelada antes de enviar '
                'una nueva solicitud para esa misma fecha.'
            )

    @staticmethod
    def es_dia_temporada(fecha) -> bool:
        """
        Helper: verifica si una fecha es día de temporada activo.

        Args:
            fecha: Fecha a verificar (string o date)

        Returns:
            True si es temporada, False en caso contrario
        """
        from datetime import datetime
        try:
            from turnos.models import DiaEspecial
            if isinstance(fecha, str):
                fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
            return DiaEspecial.objects.filter(
                fecha=fecha,
                es_temporada=True,
                activo=True
            ).exists()
        except Exception:
            return False

    @staticmethod
    def _explorador_trabaja(explorador: Empleado, fecha_obj) -> bool:
        """
        Devuelve True si el explorador TRABAJA ese día, considerando TODOS los tipos de descanso:
          - Turnos explícitos en BD → trabaja.
          - Descanso de FIN DE SEMANA por alternancia (obtener_jornada_display == None).
          - Descanso de SEMANA manual (temporada/festivo configurado por jornada) — entre semana.
          - Mantenimiento efectivo — entre semana (todos descansan).

        Cierra el hueco de que obtener_jornada_display NO reflejaba el descanso de semana entre
        semana, lo que permitía pagar/ceder a alguien que en realidad descansa ese día.
        """
        from turnos.services.turno_service import TurnoService
        from turnos.services.jornada_service import JornadaService
        from turnos.services.descanso_semana_service import DescansoSemanaService
        from turnos.models import DiaEspecial, Turno

        # 1) Turnos explícitos → trabaja (un cambio/CT puede ponerle turno aunque sea descanso de semana).
        if Turno.objects.filter(explorador=explorador, fecha=fecha_obj).exists():
            return True
        # 2) Fin de semana / festivo donde descansa → obtener_jornada_display devuelve None.
        if TurnoService.obtener_jornada_display(explorador, fecha_obj) is None:
            return False
        # 3) Entre semana: descanso de semana manual o mantenimiento efectivo.
        if fecha_obj.weekday() < 5:
            if DiaEspecial.es_mantenimiento_efectivo(fecha_obj):
                return False
            base = JornadaService.get_jornada_explorador_fecha(explorador.id, fecha_obj.strftime('%Y-%m-%d'))
            base_nombre = base.nombre.upper() if base else None
            if base_nombre and DescansoSemanaService.es_descanso_semana_manual(base_nombre, fecha_obj):
                return False
        return True
