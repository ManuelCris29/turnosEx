"""
Servicio para aplicar cambios de doblada.

Responsabilidad única: Aplicar los cambios de turnos y generar deudas cuando
una solicitud de doblada es aprobada.
"""
from typing import Tuple, Dict
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.cache import cache
from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from turnos.models import Jornada, Turno
from turnos.services.jornada_service import JornadaService
from turnos.services.doblada_turno_service import DobladaTurnoService
from .deuda_service import DeudaService
from .deuda_corporativa_service import DeudaCorporativaService
from datetime import date
import logging

logger = logging.getLogger(__name__)


def _obtener_jornadas_cache() -> Dict[str, Jornada]:
    """
    Obtiene las jornadas AM y PM con cache para evitar múltiples consultas.
    
    Returns:
        Diccionario con {'AM': Jornada, 'PM': Jornada}
    """
    cache_key = 'jornadas_am_pm'
    jornadas = cache.get(cache_key)
    
    if jornadas is None:
        jornadas = {
            'AM': Jornada.objects.get(nombre='AM'),
            'PM': Jornada.objects.get(nombre='PM')
        }
        # Cache por 1 hora (las jornadas no cambian frecuentemente)
        cache.set(cache_key, jornadas, 3600)
    
    return jornadas


class DobladaAplicacionService:
    """
    Servicio para aplicar cambios de doblada.
    
    Responsabilidad única: Aplicar cambios de turnos y generar deudas.
    Incluye validación post-aplicación para garantizar integridad de datos.
    """
    
    @staticmethod
    def validar_turnos_doblada_cesion(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> dict:
        """
        Valida que los turnos se hayan creado correctamente después de aplicar la doblada de cesión.
        
        Returns:
            dict con 'valido' (bool), 'errores' (list), 'advertencias' (list)
        """
        resultado = {
            'valido': True,
            'errores': [],
            'advertencias': []
        }
        
        fecha_cesion = solicitud.fecha_cambio_turno
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        
        # Verificar turnos del receptor
        turnos_receptor = Turno.objects.filter(
            explorador=receptor,
            fecha=fecha_cesion
        ).select_related('jornada')
        
        if not turnos_receptor.exists():
            resultado['valido'] = False
            resultado['errores'].append(
                f"CRÍTICO: Receptor {receptor.nombre} no tiene turnos para {fecha_cesion}. "
                f"Debería tener al menos 1 turno."
            )
        else:
            jornadas_receptor = [t.jornada.nombre.upper() for t in turnos_receptor]
            
            # Para cesión completa, el receptor debe tener al menos 1 jornada
            # Para cesión parcial, debe tener la jornada cedida
            if detalle.tipo_cesion in ['cesion_parcial_am', 'cesion_parcial_pm']:
                jornada_esperada = detalle.jornada_cedida.upper() if detalle.jornada_cedida else None
                if jornada_esperada and jornada_esperada not in jornadas_receptor:
                    resultado['valido'] = False
                    resultado['errores'].append(
                        f"ERROR: Receptor {receptor.nombre} no tiene la jornada {jornada_esperada} "
                        f"en {fecha_cesion}. Jornadas encontradas: {', '.join(jornadas_receptor)}"
                    )
            
            logger.info(f"✅ Validación receptor: {receptor.nombre} tiene {len(jornadas_receptor)} jornada(s): {', '.join(jornadas_receptor)}")
        
        # Verificar turnos del solicitante (debe estar descansando o con cesión parcial)
        turnos_solicitante = Turno.objects.filter(
            explorador=solicitante,
            fecha=fecha_cesion
        ).count()
        
        if detalle.tipo_cesion == 'cesion_completa':
            if turnos_solicitante > 0:
                resultado['advertencias'].append(
                    f"ADVERTENCIA: Solicitante {solicitante.nombre} tiene {turnos_solicitante} turno(s) "
                    f"en {fecha_cesion}, pero debería estar descansando (cesión completa)."
                )
        
        return resultado
    
    @staticmethod
    @transaction.atomic
    def aplicar_doblada_cesion(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Aplica la doblada en la fecha de cesión.
        
        Reglas:
        - Receptor dobla (trabaja su jornada + jornada del solicitante)
        - Solicitante descansa (no tiene turno)
        
        Args:
            solicitud: Solicitud de doblada aprobada
            detalle: Detalle de la doblada
        
        Raises:
            ValidationError: Si hay errores al aplicar los cambios
        """
        fecha_cesion = solicitud.fecha_cambio_turno
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        
        fecha_cesion_str = fecha_cesion.strftime('%Y-%m-%d')
        
        # Obtener jornadas
        jornada_solicitante = JornadaService.get_jornada_explorador_fecha(
            solicitante.id, fecha_cesion_str
        )
        
        # Determinar jornada a ceder
        if detalle.jornada_cedida:
            jornada_cedida_nombre = detalle.jornada_cedida.upper()
        else:
            jornada_cedida_nombre = jornada_solicitante.nombre.upper()
        
        # Obtener jornadas con cache
        jornadas_cache = _obtener_jornadas_cache()
        jornada_cedida_obj = jornadas_cache[jornada_cedida_nombre]
        
        # Obtener jornada del receptor
        jornada_receptor = JornadaService.get_jornada_explorador_fecha(
            receptor.id, fecha_cesion_str
        )
        
        # Receptor: según tipo de cesión
        if detalle.tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm'):
            # Cesión parcial: el receptor solo trabaja la jornada cedida (media jornada), no doblada
            Turno.objects.filter(explorador=receptor, fecha=fecha_cesion).delete()
            sala_receptor = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_cesion)
            Turno.objects.create(
                explorador=receptor,
                fecha=fecha_cesion,
                jornada=jornada_cedida_obj,
                sala=sala_receptor,
                tipo_cambio="DOBLADA"
            )
        else:
            # Cesión completa: receptor dobla (su jornada + jornada cedida)
            turno_receptor_existente = DobladaTurnoService.tiene_jornada_en_fecha(
                receptor, fecha_cesion, jornada_receptor
            )
            if turno_receptor_existente:
                jornadas_receptor = DobladaTurnoService.obtener_jornadas_en_fecha(receptor, fecha_cesion)
                if jornada_cedida_nombre not in jornadas_receptor:
                    DobladaTurnoService.agregar_jornada_a_doblada(
                        receptor, fecha_cesion, jornada_cedida_obj, 'DOBLADA'
                    )
            else:
                DobladaTurnoService.crear_doblada_completa(
                    receptor, fecha_cesion, jornada_receptor, jornada_cedida_obj, 'DOBLADA'
                )
        
        # Solicitante: Eliminar turnos según tipo de cesión
        # Si es cesión parcial, eliminar solo la jornada cedida y asegurar que tenga la otra
        if detalle.tipo_cesion == 'cesion_parcial_am':
            # Cesión parcial AM: Eliminar solo turno AM, dejar/crear PM
            Turno.objects.filter(
                explorador=solicitante,
                fecha=fecha_cesion,
                jornada=jornada_cedida_obj
            ).delete()
            jornada_otra_nombre = 'PM'
            jornada_otra_obj = jornadas_cache[jornada_otra_nombre]
            if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_cesion, jornada_otra_obj):
                sala_sol = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_cesion)
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_cesion,
                    jornada=jornada_otra_obj,
                    sala=sala_sol,
                    tipo_cambio="DOBLADA"
                )
            logger.info(
                f"Doblada cesión parcial AM aplicada: Receptor {receptor.nombre} dobla en {fecha_cesion}, "
                f"Solicitante {solicitante.nombre} mantiene PM"
            )
        elif detalle.tipo_cesion == 'cesion_parcial_pm':
            # Cesión parcial PM: Eliminar solo turno PM, dejar/crear AM
            Turno.objects.filter(
                explorador=solicitante,
                fecha=fecha_cesion,
                jornada=jornada_cedida_obj
            ).delete()
            jornada_otra_nombre = 'AM'
            jornada_otra_obj = jornadas_cache[jornada_otra_nombre]
            if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_cesion, jornada_otra_obj):
                sala_sol = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_cesion)
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_cesion,
                    jornada=jornada_otra_obj,
                    sala=sala_sol,
                    tipo_cambio="DOBLADA"
                )
            logger.info(
                f"Doblada cesión parcial PM aplicada: Receptor {receptor.nombre} dobla en {fecha_cesion}, "
                f"Solicitante {solicitante.nombre} mantiene AM"
            )
        else:
            # Cesión completa: Eliminar todos los turnos
            DobladaTurnoService.eliminar_turnos_explorador(solicitante, fecha_cesion)
            logger.info(
                f"Doblada cesión aplicada: Receptor {receptor.nombre} dobla en {fecha_cesion}, "
                f"Solicitante {solicitante.nombre} descansa"
            )
        
        # #region agent log
        import json
        import time
        from turnos.models import Turno as TurnoModel
        turnos_receptor_despues = list(TurnoModel.objects.filter(explorador=receptor, fecha=fecha_cesion).values('id', 'jornada__nombre'))
        turnos_solicitante_despues = list(TurnoModel.objects.filter(explorador=solicitante, fecha=fecha_cesion).values('id', 'jornada__nombre'))
        log_data = {
            'location': 'doblada_aplicacion_service.py:aplicar_doblada_cesion',
            'message': 'Cesión aplicada - turnos después',
            'data': {
                'solicitud_id': solicitud.id,
                'fecha_cesion': str(fecha_cesion),
                'tipo_cesion': detalle.tipo_cesion,
                'receptor_id': receptor.id,
                'receptor_nombre': receptor.nombre,
                'turnos_receptor': turnos_receptor_despues,
                'solicitante_id': solicitante.id,
                'solicitante_nombre': solicitante.nombre,
                'turnos_solicitante': turnos_solicitante_despues,
            },
            'timestamp': int(time.time() * 1000)
        }
        with open('c:\\appTurnos\\.cursor\\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_data) + '\n')
        # #endregion
        
        # VALIDACIÓN POST-APLICACIÓN (Integridad de datos)
        try:
            from django.core.exceptions import ValidationError as DjangoValidationError
            
            # Validar que los turnos se hayan creado correctamente
            # (La transacción atómica garantiza que los cambios sean visibles dentro del bloque)
            validacion = DobladaAplicacionService.validar_turnos_doblada_cesion(solicitud, detalle)
            
            if not validacion['valido']:
                errores_str = '; '.join(validacion['errores'])
                logger.error(f"❌ VALIDACIÓN FALLIDA para solicitud {solicitud.id}: {errores_str}")
                raise DjangoValidationError(
                    f"Error de integridad de datos al aplicar doblada: {errores_str}. "
                    f"La transacción será revertida."
                )
            
            if validacion['advertencias']:
                for adv in validacion['advertencias']:
                    logger.warning(f"⚠️ {adv}")
            
            logger.info(f"✅ Validación exitosa para solicitud {solicitud.id}")
            
        except Exception as e:
            logger.error(f"❌ Error en validación post-aplicación: {e}", exc_info=True)
            # Re-lanzar para que la transacción se revierta
            raise
    
    @staticmethod
    @transaction.atomic
    def aplicar_doblada_pago(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Aplica la doblada en la fecha de pago.
        
        Reglas:
        - Deudor (solicitante) dobla (trabaja su jornada + jornada del acreedor)
        - Acreedor (receptor) descansa (no tiene turno)
        
        Args:
            solicitud: Solicitud de doblada aprobada
            detalle: Detalle de la doblada
        
        Raises:
            ValidationError: Si hay errores al aplicar los cambios
        """
        fecha_pago = detalle.fecha_pago
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        
        fecha_pago_str = fecha_pago.strftime('%Y-%m-%d')
        
        # ===========================
        # Caso especial: Pago en Sábado
        # ===========================
        # Regla de negocio:
        # - En un sábado (fin de semana), el explorador que "tiene el fin de semana"
        #   normalmente tiene AM+PM (doblada completa) en BD o por asignación.
        # - Al pagar en sábado, el solicitante elige qué jornada trabajará (AM o PM)
        # - El receptor trabaja la jornada contraria (la que queda disponible).
        #
        # Implementación:
        # - Asegurar que el solicitante tenga SOLO la jornada seleccionada.
        # - Asegurar que el receptor tenga SOLO la jornada contraria.
        #
        if fecha_pago.weekday() == 5 and detalle.jornada_pago_sabado:
            jornada_sel = detalle.jornada_pago_sabado.upper()
            if jornada_sel not in ("AM", "PM"):
                raise ValidationError("jornada_pago_sabado inválida. Debe ser 'AM' o 'PM'")

            jornada_contraria = "PM" if jornada_sel == "AM" else "AM"

            jornadas_cache = _obtener_jornadas_cache()
            jornada_sel_obj = jornadas_cache[jornada_sel]
            jornada_contraria_obj = jornadas_cache[jornada_contraria]

            # 1) Solicitante: dejar SOLO la jornada seleccionada
            Turno.objects.filter(explorador=solicitante, fecha=fecha_pago).delete()
            sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
            Turno.objects.create(
                explorador=solicitante,
                fecha=fecha_pago,
                jornada=jornada_sel_obj,
                sala=sala_solicitante,
                tipo_cambio="DOBLADA"
            )

            # 2) Receptor: dejar SOLO la jornada contraria
            # - Si tenía doblada completa (AM+PM) ese sábado, se elimina la jornada que ahora cubre el solicitante.
            Turno.objects.filter(explorador=receptor, fecha=fecha_pago, jornada=jornada_sel_obj).delete()

            # Si el receptor no tiene aún la jornada contraria en BD, crearla (caso raro)
            if not Turno.objects.filter(explorador=receptor, fecha=fecha_pago, jornada=jornada_contraria_obj).exists():
                sala_receptor = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_pago)
                Turno.objects.create(
                    explorador=receptor,
                    fecha=fecha_pago,
                    jornada=jornada_contraria_obj,
                    sala=sala_receptor,
                    tipo_cambio="DOBLADA"
                )

            logger.info(
                f"Pago en sábado aplicado: {solicitante.nombre} trabaja {jornada_sel} en {fecha_pago}, "
                f"{receptor.nombre} trabaja {jornada_contraria} (jornada restante)"
            )
            return

        # ===========================
        # Cesión parcial: pago = la misma jornada que se cedió (jornada_cedida)
        # ===========================
        # Regla: El deudor paga trabajando la jornada que cedió (si cedió AM, trabaja AM el día de pago).
        # El acreedor ese día hace la otra jornada (o descansa si solo tenía esa).
        if detalle.tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm'):
            # Cesión parcial: deudor paga con la jornada cedida; acreedor trabaja la otra (media jornada)
            if detalle.jornada_cedida:
                jornada_pago_nombre = detalle.jornada_cedida.upper()
            else:
                jornada_pago_nombre = 'AM' if detalle.tipo_cesion == 'cesion_parcial_am' else 'PM'
            if jornada_pago_nombre not in ('AM', 'PM'):
                raise ValidationError("jornada_cedida inválida en cesión parcial. Debe ser AM o PM.")
            jornada_otra_nombre = 'PM' if jornada_pago_nombre == 'AM' else 'AM'
            jornadas_cache = _obtener_jornadas_cache()
            jornada_pago_obj = jornadas_cache[jornada_pago_nombre]
            jornada_otra_obj = jornadas_cache[jornada_otra_nombre]
            # Solicitante: solo la jornada que paga (la cedida)
            Turno.objects.filter(explorador=solicitante, fecha=fecha_pago).delete()
            sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
            Turno.objects.create(
                explorador=solicitante,
                fecha=fecha_pago,
                jornada=jornada_pago_obj,
                sala=sala_solicitante,
                tipo_cambio="DOBLADA"
            )
            # Receptor: solo la otra jornada (media jornada), no descansa
            Turno.objects.filter(explorador=receptor, fecha=fecha_pago).delete()
            sala_receptor = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_pago)
            Turno.objects.create(
                explorador=receptor,
                fecha=fecha_pago,
                jornada=jornada_otra_obj,
                sala=sala_receptor,
                tipo_cambio="DOBLADA"
            )
            logger.info(
                f"Doblada pago (cesión parcial) aplicada: {solicitante.nombre} trabaja {jornada_pago_nombre}, "
                f"{receptor.nombre} trabaja {jornada_otra_nombre} en {fecha_pago}"
            )
            # #region agent log
            import json
            import time
            from turnos.models import Turno as TurnoModel
            turnos_solicitante_pago = list(TurnoModel.objects.filter(explorador=solicitante, fecha=fecha_pago).values('id', 'jornada__nombre'))
            turnos_receptor_pago = list(TurnoModel.objects.filter(explorador=receptor, fecha=fecha_pago).values('id', 'jornada__nombre'))
            log_data = {
                'location': 'doblada_aplicacion_service.py:aplicar_doblada_pago',
                'message': 'Pago parcial aplicado - turnos después',
                'data': {
                    'solicitud_id': solicitud.id,
                    'fecha_pago': str(fecha_pago),
                    'tipo_cesion': detalle.tipo_cesion,
                    'solicitante_id': solicitante.id,
                    'solicitante_nombre': solicitante.nombre,
                    'turnos_solicitante': turnos_solicitante_pago,
                    'receptor_id': receptor.id,
                    'receptor_nombre': receptor.nombre,
                    'turnos_receptor': turnos_receptor_pago,
                },
                'timestamp': int(time.time() * 1000)
            }
            with open('c:\\appTurnos\\.cursor\\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_data) + '\n')
            # #endregion
            return

        # ===========================
        # Caso normal: Pago (no sábado, cesión completa)
        # ===========================
        # Obtener jornadas
        jornada_deudor = JornadaService.get_jornada_explorador_fecha(
            solicitante.id, fecha_pago_str
        )
        jornada_acreedor = JornadaService.get_jornada_explorador_fecha(
            receptor.id, fecha_pago_str
        )
        
        # Obtener jornada con cache
        jornadas_cache = _obtener_jornadas_cache()
        jornada_acreedor_obj = jornadas_cache[jornada_acreedor.nombre.upper()]
        
        # Verificar si deudor ya tiene turno en fecha de pago
        turno_deudor_existente = DobladaTurnoService.tiene_jornada_en_fecha(
            solicitante, fecha_pago, jornada_deudor
        )
        
        if turno_deudor_existente:
            # Ya tiene turno, agregar jornada del acreedor si no la tiene
            jornadas_deudor = DobladaTurnoService.obtener_jornadas_en_fecha(solicitante, fecha_pago)
            jornada_acreedor_nombre = jornada_acreedor.nombre.upper()
            
            if jornada_acreedor_nombre not in jornadas_deudor:
                DobladaTurnoService.agregar_jornada_a_doblada(
                    solicitante, fecha_pago, jornada_acreedor_obj, 'DOBLADA'
                )
        else:
            # No tiene turno, crear doblada completa
            DobladaTurnoService.crear_doblada_completa(
                solicitante, fecha_pago, jornada_deudor, jornada_acreedor_obj, 'DOBLADA'
            )
        
        # Acreedor descansa (eliminar turnos)
        DobladaTurnoService.eliminar_turnos_explorador(receptor, fecha_pago)
        
        logger.info(
            f"Doblada pago aplicada: Deudor {solicitante.nombre} dobla en {fecha_pago}, "
            f"Acreedor {receptor.nombre} descansa"
        )
        
        # #region agent log
        import json
        import time
        from turnos.models import Turno as TurnoModel
        turnos_solicitante_pago = list(TurnoModel.objects.filter(explorador=solicitante, fecha=fecha_pago).values('id', 'jornada__nombre'))
        turnos_receptor_pago = list(TurnoModel.objects.filter(explorador=receptor, fecha=fecha_pago).values('id', 'jornada__nombre'))
        log_data = {
            'location': 'doblada_aplicacion_service.py:aplicar_doblada_pago',
            'message': 'Pago aplicado - turnos después',
            'data': {
                'solicitud_id': solicitud.id,
                'fecha_pago': str(fecha_pago),
                'tipo_cesion': detalle.tipo_cesion,
                'solicitante_id': solicitante.id,
                'solicitante_nombre': solicitante.nombre,
                'turnos_solicitante': turnos_solicitante_pago,
                'receptor_id': receptor.id,
                'receptor_nombre': receptor.nombre,
                'turnos_receptor': turnos_receptor_pago,
            },
            'timestamp': int(time.time() * 1000)
        }
        with open('c:\\appTurnos\\.cursor\\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_data) + '\n')
        # #endregion
    
    @staticmethod
    @transaction.atomic
    def generar_deudas_doblada(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Genera las deudas entre exploradores y corporativas asociadas a una doblada.
        
        Reglas:
        - Se crea una deuda entre exploradores (estado 'pagada' porque ambas dobladas ya están aplicadas)
        - La deuda corporativa (30 minutos) **solo se genera si la doblada es efectiva en esa fecha**,
          es decir, si la jornada real del día es DOBLADA (AM+PM) según los turnos aplicados.
        
        Args:
            solicitud: Solicitud de doblada aprobada
            detalle: Detalle de la doblada
        """
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        
        # Determinar jornada cedida
        if detalle.jornada_cedida:
            jornada_cedida_nombre = detalle.jornada_cedida.upper()
        else:
            fecha_cesion_str = fecha_cesion.strftime('%Y-%m-%d')
            jornada_solicitante = JornadaService.get_jornada_explorador_fecha(
                solicitante.id, fecha_cesion_str
            )
            jornada_cedida_nombre = jornada_solicitante.nombre.upper()
        
        # Generar deuda entre exploradores (estado 'pagada' porque, conceptualmente,
        # ambas partes se comprometen a realizar la doblada en cesión y pago).
        DeudaService.crear_deuda(
            deudor=solicitante,
            acreedor=receptor,
            solicitud=solicitud,
            fecha_generacion=fecha_cesion,
            fecha_pago_pactada=fecha_pago,
            fecha_pago_real=fecha_pago,  # Ya se aplicó
            jornada_cedida=jornada_cedida_nombre,
            media_jornada=True
        )
        
        # ===========================
        # Deuda corporativa SOLO por doblada efectiva
        # ===========================
        # Regla de negocio:
        # - La deuda corporativa (30 minutos) se genera únicamente cuando el explorador
        #   realmente trabaja una jornada DOBLADA (AM+PM) en una fecha concreta.
        # - No basta con que la solicitud esté aprobada; debemos verificar los turnos reales.
        #
        # Implementación:
        # - Usamos TurnoService.obtener_jornada_display() como fuente de verdad.
        # - Si jornada_display == 'DOBLADA' → se crea la deuda corporativa.
        # - Si jornada_display es 'AM', 'PM' o None (descanso / media jornada) → NO se genera deuda.
        from turnos.services.turno_service import TurnoService

        def _registrar_deuda_corporativa_si_doblada(explorador: Empleado, fecha_doblada: date, comentario: str) -> None:
            jornada_display = TurnoService.obtener_jornada_display(explorador, fecha_doblada)
            if jornada_display == 'DOBLADA':
                DeudaCorporativaService.crear_deuda_corporativa(
                    explorador=explorador,
                    minutos=30,
                    fecha_generacion=date.today(),
                    fecha_doblada=fecha_doblada,
                    solicitud=solicitud,
                    comentario=comentario
                )
                logger.info(
                    f"Deuda corporativa generada (30 min) para {explorador.nombre} "
                    f"en {fecha_doblada} por jornada DOBLADA."
                )
            else:
                logger.info(
                    f"No se genera deuda corporativa para {explorador.nombre} en {fecha_doblada}: "
                    f"jornada_display={jornada_display!r}"
                )

        # Receptor: posible doblada en fecha de cesión
        _registrar_deuda_corporativa_si_doblada(
            explorador=receptor,
            fecha_doblada=fecha_cesion,
            comentario=f'Doblada efectiva en fecha de cesión ({fecha_cesion})'
        )

        # Solicitante (deudor): posible doblada en fecha de pago
        _registrar_deuda_corporativa_si_doblada(
            explorador=solicitante,
            fecha_doblada=fecha_pago,
            comentario=f'Doblada efectiva en fecha de pago ({fecha_pago})'
        )
        
        logger.info(
            f"Deudas generadas: Solicitud {solicitud.id} - "
            f"Deuda entre {solicitante.nombre} y {receptor.nombre}, "
            f"Deudas corporativas para ambos"
        )

    @staticmethod
    @transaction.atomic
    def revertir_doblada_aplicada(solicitud: SolicitudCambio) -> None:
        """
        Revierte los cambios de una doblada ya aprobada.

        Utilizado dentro de la ventana de cancelación de 30 minutos.
        Elimina los turnos tipo DOBLADA creados para ambos empleados en ambas fechas
        y restaura sus turnos base según la jornada asignada.
        Cancela las deudas asociadas a esta solicitud.

        Args:
            solicitud: Solicitud de doblada aprobada a revertir

        Raises:
            Exception: Si ocurre un error durante la reversión
        """
        from solicitudes.models import DeudaExplorador, DeudaCorporativa
        from core.utils.jornada_utils import JornadaUtils

        detalle = solicitud.doblada
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago

        jornadas_cache = _obtener_jornadas_cache()

        def _restaurar_turno_base(empleado, fecha):
            """
            Elimina turnos DOBLADA del empleado en la fecha y recrea su turno normal
            basándose en la jornada asignada si corresponde trabajar ese día.
            """
            Turno.objects.filter(explorador=empleado, fecha=fecha, tipo_cambio='DOBLADA').delete()

            # Obtener jornada asignada y calcular si trabaja ese día
            jornada_base = JornadaService.get_jornada_explorador_fecha(empleado.id, fecha.strftime('%Y-%m-%d'))
            if not jornada_base:
                return

            jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
            if jornada_dia == 'Descanso':
                return

            jornada_nombre = jornada_dia if jornada_dia in ('AM', 'PM') else jornada_base.nombre.upper()
            if jornada_nombre not in jornadas_cache:
                return

            if not Turno.objects.filter(explorador=empleado, fecha=fecha).exists():
                sala = DobladaTurnoService.obtener_sala_explorador_fecha(empleado, fecha)
                Turno.objects.create(
                    explorador=empleado,
                    fecha=fecha,
                    jornada=jornadas_cache[jornada_nombre],
                    sala=sala,
                    tipo_cambio=None
                )
                logger.info(f"Turno base restaurado: {empleado.nombre} - {fecha} - {jornada_nombre}")

        # --- Revertir fecha de cesión ---
        _restaurar_turno_base(receptor, fecha_cesion)
        _restaurar_turno_base(solicitante, fecha_cesion)

        # --- Revertir fecha de pago ---
        _restaurar_turno_base(solicitante, fecha_pago)
        _restaurar_turno_base(receptor, fecha_pago)

        # --- Cancelar deudas entre exploradores ---
        DeudaExplorador.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')

        # --- Cancelar deudas corporativas ---
        DeudaCorporativa.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')

        logger.info(
            f"Doblada revertida: Solicitud {solicitud.id} - "
            f"{solicitante.nombre} <-> {receptor.nombre}"
        )
