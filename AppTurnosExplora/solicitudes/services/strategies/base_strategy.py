"""
Base Strategy for Solicitud types - Domain-Driven Design (DDD) + Clean Architecture

This module implements the Strategy Pattern for different types of solicitudes.
Each solicitud type (Cambio Turno, Doblada, CT Permanente, D FDS) will have
its own strategy that inherits from this base class.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
from solicitudes.models import SolicitudCambio
from empleados.models import Empleado
from core.services import get_empleado_disponibilidad_service, get_turno_service


class SolicitudStrategy(ABC):
    """
    Abstract base class for solicitud strategies.
    
    This implements the Strategy Pattern where each type of solicitud
    (Cambio Turno, Doblada, etc.) has its own strategy with specific
    validation, creation, and application logic.
    """
    
    def __init__(self, tipo_solicitud: str):
        """
        Initialize the strategy with the solicitud type.
        
        Args:
            tipo_solicitud: Name of the solicitud type (e.g., "Cambio Turno", "DOBLADA")
        """
        self.tipo_solicitud = tipo_solicitud
    
    @abstractmethod
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate solicitud-specific data.
        
        Args:
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        pass
    
    @abstractmethod
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        """
        Create a new solicitud with type-specific logic.
        
        Args:
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (solicitud_instance, message)
        """
        pass
    
    @abstractmethod
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Apply changes when solicitud is approved.
        
        Args:
            solicitud: The approved solicitud instance
            
        Returns:
            Tuple of (success, message)
        """
        pass
    
    def _datos_desde_solicitud(self, solicitud: SolicitudCambio) -> Optional[Dict[str, Any]]:
        """
        Reconstruye el dict `datos` (igual al de la creación) a partir de una solicitud YA
        persistida, para poder RE-VALIDARLA al aprobar con el estado actual del sistema.

        Devuelve None si el tipo aún no soporta re-validación (en ese caso se omite, sin
        bloquear). Cada estrategia concreta debe implementarlo para quedar cubierta.
        """
        return None

    def revalidar_para_aprobar(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Re-valida la solicitud con el estado ACTUAL, justo antes de aplicarla al aprobar.
        Atrapa solicitudes que quedaron inválidas entre el envío y la aprobación (festivo
        nuevo, día ya comprometido por otra gestión, fecha en el pasado, etc.).

        Marca `es_revalidacion=True` para que se OMITAN los chequeos de "duplicado pendiente"
        (son una regla de creación; al aprobar no aplican y verían la propia solicitud).
        """
        datos = self._datos_desde_solicitud(solicitud)
        if datos is None:
            return True, 'Sin re-validación para este tipo'
        datos['es_revalidacion'] = True
        datos['solicitud_actual_id'] = solicitud.id
        return self.validar_solicitud(datos)

    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """
        Get available employees for this solicitud type.
        Can be overridden by specific strategies.
        
        Args:
            fecha: Date string in YYYY-MM-DD format
            usuario_actual: Current user's empleado instance
            **kwargs: Additional arguments
            
        Returns:
            List of available empleados
        """
        service = get_empleado_disponibilidad_service()
        return service.get_empleados_disponibles(fecha, usuario_actual)

    def disponibilidad_companero(self, candidato: Empleado, fecha_cesion) -> Tuple[bool, Optional[str]]:
        """
        ¿Puede este compañero participar en un cambio de FIN DE SEMANA sobre `fecha_cesion`?

        Devuelve (disponible, motivo) — el motivo se muestra en el formulario cuando no lo está.
        Cada tipo de cambio tiene su regla, por eso es un punto de extensión: el intercambio
        (CAMBIO DESCANSO) necesita que el compañero trabaje el OTRO día del finde para poder
        canjearlo, mientras que una cesión (D FDS) solo necesita que tenga libre el día que recibe.
        Antes esta regla vivía dentro de la vista compartida por ambos formularios, así que no
        se podía cambiar para uno sin alterar el otro.

        Por defecto se aplica la regla del INTERCAMBIO, que es la histórica.
        """
        from datetime import timedelta
        from turnos.services.turno_service import TurnoService

        otro = (fecha_cesion + timedelta(days=1) if fecha_cesion.weekday() == 5
                else fecha_cesion - timedelta(days=1))
        dia_otro = 'sábado' if otro.weekday() == 5 else 'domingo'

        trabaja_otro = TurnoService.estado_dia(candidato, otro)['trabaja']
        libre_cesion = not TurnoService.estado_dia(candidato, fecha_cesion)['trabaja']
        if trabaja_otro and libre_cesion:
            return True, None
        if not libre_cesion:
            return False, 'ya trabaja los dos días ese finde (doblada)'
        if not trabaja_otro:
            return False, f'no trabaja el {dia_otro} de ese finde'
        return False, 'no disponible ese finde'

    def etiqueta_companero(self, candidato: Empleado, fecha_cesion) -> str:
        """
        Texto que describe a un compañero DISPONIBLE en el selector del formulario.

        Va junto a `disponibilidad_companero`: debe decir POR QUÉ ese compañero sirve, y por eso
        también depende del tipo de cambio. Antes el texto se armaba en la vista a partir del
        calendario ("trabaja <el otro día del finde>"), igual para todos; con el intercambio era
        cierto por construcción, pero al abrir la cesión a cualquiera que descanse ese día pasó a
        afirmar cosas falsas —p. ej. "trabaja sábado 08/08" de alguien que ese sábado descansa—.

        Por defecto, la regla del INTERCAMBIO: lo que lo habilita es trabajar el otro día.
        """
        from datetime import timedelta

        otro = (fecha_cesion + timedelta(days=1) if fecha_cesion.weekday() == 5
                else fecha_cesion - timedelta(days=1))
        dia_otro = 'sábado' if otro.weekday() == 5 else 'domingo'
        return f'trabaja {dia_otro} {otro.strftime("%d/%m")}'


    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Dict[str, Any]:
        """
        Get turn information for an explorer.
        Can be overridden by specific strategies.
        
        Args:
            explorador_id: ID of the empleado
            fecha: Date string in YYYY-MM-DD format
            
        Returns:
            Dictionary with turn information
        """
        turno_service = get_turno_service()
        return turno_service.get_turno_explorador(explorador_id, fecha)
    
    def detalle(self, solicitud: SolicitudCambio, datos: Dict[str, Any]) -> None:
        """
        Enriquece `datos` con la información propia de este tipo de solicitud.

        Es la pieza que cierra el OCP para la pantalla de detalle (Fase 2 de la
        auditoría). Antes, `views/detalle.py` decidía con una cadena
        `if tipo_nombre == 'CT PERMANENTE': ... elif ...`, así que **añadir un tipo
        nuevo obligaba a editar la vista**: justo lo que el principio abierto/cerrado
        dice que no hay que hacer. Ahora cada strategy trae su propio detalle.

        Contrato:
        - Recibe `datos` YA construido con el tronco común (id, estado, solicitante,
          receptor, aprobaciones…) y con las secciones `fechas` e
          `informacion_adicional` inicializadas a diccionario vacío.
        - MUTA `datos` en el sitio; no devuelve nada.
        - No debe lanzar: la vista de detalle es de solo lectura y un fallo al leer
          un modelo de detalle no puede tumbar la pantalla. Cada implementación
          registra el problema en `datos['fechas']['error']`.

        La implementación por defecto no añade nada. Es deliberada: un tipo que no
        tenga detalle propio debe devolver el tronco común, no fallar.
        """
        return None

    def validar_campos_requeridos(self, post) -> Tuple[bool, str]:
        """
        Comprueba que el POST traiga los campos obligatorios de ESTE tipo.

        Falla rápido, antes de tocar la base de datos, y devuelve `(ok, mensaje)`
        con un texto pensado para el usuario ("La fecha de cesión es requerida"),
        no para el log.

        Movido desde `SolicitudRequestParser.validate_required` en la Fase 2: allí
        era una cadena `if tipo_nombre == ...` que había que editar por cada tipo
        nuevo.

        Por defecto exige lo mínimo común —compañero y fecha—, que es lo que pedía
        la rama `else` de aquella cadena para CAMBIO TURNO y los tipos genéricos.
        """
        if not post.get('empleado_receptor'):
            return False, 'Debe seleccionar un compañero para el intercambio'
        if not post.get('fecha_solicitud'):
            return False, 'La fecha es requerida'
        return True, ''

    def parsear_datos(self, post, solicitante, receptor) -> Dict[str, Any]:
        """
        Traduce el POST al diccionario que consume `crear_solicitud`.

        Solo transforma y normaliza: no valida reglas de negocio ni escribe nada.
        Quien llama añade después la clave 'tipo_cambio'.

        Movido desde `SolicitudRequestParser.parse_datos` en la Fase 2. La
        implementación por defecto reproduce la rama `else` de aquella cadena.
        """
        return {
            'explorador_solicitante': solicitante,
            'explorador_receptor': receptor,
            'comentario': post.get('comentarios', ''),
            'fecha_cambio_turno': post.get('fecha_solicitud'),
        }

    # ¿Este tipo se materializa a través de un `DobladaDetalle`?
    #
    # No es una curiosidad del modelo: es la CLAVE DE DESPACHO de la reconciliación
    # (`DobladaSnapshotService`). Allí la decisión se tomaba mirando primero si la
    # solicitud tiene detalle de doblada y solo después el tipo, con un `else` que
    # significaba "cualquier otro tipo CON detalle, trátalo como DOBLADA".
    #
    # Se declara como capacidad y no como lista de tipos en el servicio a propósito:
    # una lista allí obligaría a editar el servicio por cada tipo nuevo, que es
    # justo lo que la Fase 2 viene a quitar.
    usa_detalle_doblada = False

    def reaplicar(self, solicitud: SolicitudCambio, fechas: set) -> None:
        """
        Re-materializa una solicitud YA APROBADA sobre `fechas`, con la lógica de
        este tipo. La usa la reconciliación posterior a revertir otra solicitud.

        Contrato crítico: lo que se re-aplique aquí tiene que estar declarado en
        `pares_que_reescribe`, o el cierre de días afectados se queda corto y se
        pierde en silencio lo que viva en los días colaterales (patrón #33 de
        `PROTECTION_PATTERNS.md`). Los dos métodos son espejo; hay tests que lo
        comprueban en `test_snapshot_dispatch_caracterizacion.py`.

        Por defecto no hace nada: un tipo que no sepa re-materializarse debe
        quedarse quieto, nunca improvisar. Reproduce el `return` de la rama final
        de la cadena que había en el servicio.
        """
        return None

    def pares_que_reescribe(self, solicitud: SolicitudCambio, fechas: set) -> set:
        """
        Pares `(explorador_id, fecha)` que `reaplicar` va a escribir.

        Espejo declarativo de `reaplicar`. Se usa para CERRAR el conjunto de días
        afectados antes de tocar nada, así que debe ser exacto en los dos sentidos:
        declarar de menos deja días colaterales fuera del cierre; declarar de más
        bloquea reconciliaciones ajenas legítimas.

        Por defecto, los días propios de la solicitud que caigan en `fechas`, para
        ambas partes.
        """
        return self._pares(solicitud, [solicitud.fecha_cambio_turno], fechas)

    @staticmethod
    def _pares(solicitud, candidatas, fechas=None, todas=False) -> set:
        """
        Producto (personas × fechas) de la solicitud, filtrando vacíos.

        `candidatas` se materializa con `tuple()` antes de recorrerla, y eso NO es
        decorativo: la comprensión la recorre una vez POR PERSONA, así que pasar un
        generador daba un resultado silenciosamente incompleto —solo los pares de
        la primera persona—. Fue un bug real, corregido el 2026-08-20.

        Con `todas=False` solo entran las fechas que ya están en juego; con
        `todas=True` entran todas las del tipo, porque su aplicador las muta de una
        vez sin importar cuál coincidió.
        """
        personas = [p for p in (solicitud.explorador_solicitante_id,
                                solicitud.explorador_receptor_id) if p]
        materializadas = tuple(candidatas)
        if not todas and fechas is not None:
            materializadas = tuple(f for f in materializadas if f in fechas)
        return {(p, f) for p in personas for f in materializadas if f}

    def __str__(self):
        return f"{self.__class__.__name__}({self.tipo_solicitud})"
    
    def __repr__(self):
        return f"{self.__class__.__name__}(tipo_solicitud='{self.tipo_solicitud}')"

