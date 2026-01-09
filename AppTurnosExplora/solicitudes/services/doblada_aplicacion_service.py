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
from turnos.models import Jornada
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
        from turnos.models import Turno
        
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
        
        # Verificar si receptor ya tiene turno en esa fecha
        turno_receptor_existente = DobladaTurnoService.tiene_jornada_en_fecha(
            receptor, fecha_cesion, jornada_receptor
        )
        
        if turno_receptor_existente:
            # Ya tiene turno, agregar jornada cedida si no la tiene
            # El receptor debe cubrir la jornada que el solicitante cede
            jornadas_receptor = DobladaTurnoService.obtener_jornadas_en_fecha(receptor, fecha_cesion)
            
            if jornada_cedida_nombre not in jornadas_receptor:
                DobladaTurnoService.agregar_jornada_a_doblada(
                    receptor, fecha_cesion, jornada_cedida_obj, 'DOBLADA'
                )
        else:
            # No tiene turno, crear doblada completa
            # Receptor trabaja: su jornada base + jornada que se cede
            DobladaTurnoService.crear_doblada_completa(
                receptor, fecha_cesion, jornada_receptor, jornada_cedida_obj, 'DOBLADA'
            )
        
        # Solicitante: Eliminar turnos según tipo de cesión
        # Si es cesión parcial, eliminar solo la jornada cedida; si es completa, eliminar todas
        if detalle.tipo_cesion == 'cesion_parcial_am':
            # Cesión parcial AM: Eliminar solo turno AM, mantener PM
            from turnos.models import Turno
            Turno.objects.filter(
                explorador=solicitante,
                fecha=fecha_cesion,
                jornada=jornada_cedida_obj
            ).delete()
            logger.info(
                f"Doblada cesión parcial AM aplicada: Receptor {receptor.nombre} dobla en {fecha_cesion}, "
                f"Solicitante {solicitante.nombre} mantiene PM"
            )
        elif detalle.tipo_cesion == 'cesion_parcial_pm':
            # Cesión parcial PM: Eliminar solo turno PM, mantener AM
            from turnos.models import Turno
            Turno.objects.filter(
                explorador=solicitante,
                fecha=fecha_cesion,
                jornada=jornada_cedida_obj
            ).delete()
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
    
    @staticmethod
    @transaction.atomic
    def generar_deudas_doblada(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Genera las deudas entre exploradores y corporativas.
        
        Reglas:
        - Se crea una deuda entre exploradores (estado 'pagada' porque ambas dobladas ya están aplicadas)
        - Receptor acumula +30 minutos de deuda corporativa (por doblada en fecha de cesión)
        - Deudor acumula +30 minutos de deuda corporativa (por doblada en fecha de pago)
        
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
        
        # Generar deuda entre exploradores (estado 'pagada' porque ambas dobladas ya están aplicadas)
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
        
        # Receptor acumula +30 minutos (por doblada en fecha de cesión)
        DeudaCorporativaService.crear_deuda_corporativa(
            explorador=receptor,
            minutos=30,
            fecha_generacion=date.today(),
            fecha_doblada=fecha_cesion,
            solicitud=solicitud,
            comentario=f'Doblada en fecha de cesión ({fecha_cesion})'
        )
        
        # Deudor acumula +30 minutos (por doblada en fecha de pago)
        DeudaCorporativaService.crear_deuda_corporativa(
            explorador=solicitante,
            minutos=30,
            fecha_generacion=date.today(),
            fecha_doblada=fecha_pago,
            solicitud=solicitud,
            comentario=f'Doblada en fecha de pago ({fecha_pago})'
        )
        
        logger.info(
            f"Deudas generadas: Solicitud {solicitud.id} - "
            f"Deuda entre {solicitante.nombre} y {receptor.nombre}, "
            f"Deudas corporativas para ambos"
        )

