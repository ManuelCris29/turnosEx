"""
Servicio para gestionar días especiales (festivos y mantenimiento) por año.
Responsabilidad única: Gestión de festivos y mantenimiento por año y mes.
"""
from django.db import transaction
from django.db.models import Count, Max
from turnos.models import DiaEspecial
from datetime import date, timedelta
from typing import List, Dict, Set
import logging
from turnos.services.temporada_service import TemporadaService
from core.utils.festivos_colombia import CalculadoraFestivos

logger = logging.getLogger(__name__)


class DiaEspecialService:
    """
    Servicio para gestionar días especiales (festivos y mantenimiento).
    Permite crear, consultar y eliminar días especiales por año y tipo.
    """

    @staticmethod
    def token_estado(tipo: str, anio: int) -> str:
        """
        Huella del estado guardado de un tipo/año, para detectar ediciones concurrentes.

        Guardar un año es "borrar todo y recrear" a partir de lo que el navegador envía,
        así que dos personas con la página abierta se pisan: la última en guardar borra
        lo que hizo la primera, sin aviso. La página lleva esta huella en un campo oculto
        y el guardado la rechaza si ya no coincide.

        Cuenta TODAS las filas del tipo/año (incluidas las inactivas), porque el borrado
        previo al guardado también se las lleva.
        """
        datos = DiaEspecial.objects.filter(
            tipo=tipo, fecha__year=anio, es_temporada=False
        ).aggregate(n=Count('id'), ultimo=Max('actualizado_en'))

        ultimo = datos['ultimo'].isoformat() if datos['ultimo'] else '-'
        return f"{datos['n']}:{ultimo}"

    @staticmethod
    def obtener_dias_por_tipo_anio(tipo: str, anio: int) -> List[DiaEspecial]:
        """
        Obtiene todos los días especiales de un tipo y año específico.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año a consultar
            
        Returns:
            Lista de objetos DiaEspecial del tipo y año especificados
        """
        return DiaEspecial.objects.filter(
            tipo=tipo,
            año_planificacion=anio,
            activo=True
        ).exclude(es_temporada=True).order_by('fecha')

    @staticmethod
    def obtener_dias_por_tipo_mes(tipo: str, anio: int, mes: int) -> List[DiaEspecial]:
        """
        Obtiene los días especiales de un tipo, mes y año específicos.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año a consultar
            mes: Mes a consultar (1-12)
            
        Returns:
            Lista de objetos DiaEspecial del tipo, mes y año especificados
        """
        return DiaEspecial.objects.filter(
            tipo=tipo,
            año_planificacion=anio,
            mes=mes,
            activo=True
        ).exclude(es_temporada=True).order_by('fecha')

    @staticmethod
    def obtener_dias_por_tipo_por_mes(tipo: str, anio: int) -> Dict[int, List[int]]:
        """
        Obtiene los días especiales agrupados por mes.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año a consultar
            
        Returns:
            Diccionario con mes como clave y lista de días como valor
            Ejemplo: {1: [15, 16, 20], 2: [10, 14]}
        """
        dias_especiales = DiaEspecialService.obtener_dias_por_tipo_anio(tipo, anio)
        resultado = {}
        
        for dia in dias_especiales:
            mes = dia.mes or dia.fecha.month
            dia_numero = dia.fecha.day
            
            if mes not in resultado:
                resultado[mes] = []
            resultado[mes].append(dia_numero)
        
        # Ordenar los días de cada mes
        for mes in resultado:
            resultado[mes].sort()
        
        return resultado

    @staticmethod
    def guardar_dias_especiales_anual(
        tipo: str,
        anio: int,
        dias_seleccionados: Dict[int, List[int]],
        descripcion: str = "",
        usuario=None,
        permitir_vacio: bool = False,
        token_esperado: str = None
    ) -> tuple[bool, str]:
        """
        Guarda los días especiales para un tipo y año específicos.
        IMPORTANTE: Reemplaza todos los días existentes del mismo tipo y año.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año para el cual se guardan los días
            dias_seleccionados: Diccionario con mes como clave y lista de días como valor
                               Ejemplo: {1: [15, 16, 20], 2: [10, 14]}
            descripcion: Descripción general para todos los días
            usuario: Usuario que realiza la operación (opcional, para historial)
            permitir_vacio: Si es True, una selección vacía significa "dejar el año sin
                            días de este tipo" (borrado explícito). Si es False (por
                            defecto), una selección vacía se rechaza SIN tocar la BD.
            token_esperado: Huella del estado que tenía el año cuando se cargó la página
                            (ver `token_estado`). Si se pasa y ya no coincide, el guardado
                            se rechaza para no pisar el trabajo de otra persona.

        Returns:
            Tupla (éxito, mensaje)
        """
        from core.services.cache_service import CacheService

        # Todas las validaciones ocurren ANTES de tomar el lock y de escribir nada:
        # el patrón de guardado es "borrar el año y recrear", así que un rechazo
        # posterior al borrado dejaría el año vacío mientras se reporta un error.
        if tipo not in ['festivo', 'mantenimiento']:
            return False, f"Tipo inválido: {tipo}. Debe ser 'festivo' o 'mantenimiento'."

        if anio < DiaEspecial.ANIO_MIN or anio > DiaEspecial.ANIO_MAX:
            return False, f"Año inválido: {anio}. Debe estar entre {DiaEspecial.ANIO_MIN} y {DiaEspecial.ANIO_MAX}."

        if not dias_seleccionados and not permitir_vacio:
            logger.warning("No hay días seleccionados para guardar")
            return False, f"No se seleccionaron días de {tipo}."

        if token_esperado is not None and token_esperado != DiaEspecialService.token_estado(tipo, anio):
            logger.warning(f"Guardado rechazado por edición concurrente en {tipo} {anio}")
            return False, (
                f"Otra persona modificó los {tipo}s de {anio} mientras tenías esta página abierta. "
                "Se recargaron los datos actuales: revisa el calendario y vuelve a aplicar tu cambio."
            )

        # Guarda contra dos guardados simultáneos del mismo año/tipo (dos pestañas, doble-clic):
        # sin este lock la segunda escritura pisaría en silencio lo que la primera acababa de crear.
        clave_lock = f"dias_especiales_lock_{tipo}_{anio}"
        if not CacheService.acquire_lock(clave_lock, ttl=15):
            return False, f"Ya hay un guardado en curso para {tipo} del año {anio}. Espera unos segundos y reintenta."

        try:
            return DiaEspecialService._escribir_dias_especiales_anual(
                tipo, anio, dias_seleccionados, descripcion or f"Día de {tipo}"
            )
        except Exception as e:
            # El rollback ya lo hizo `_escribir_dias_especiales_anual` al propagar la
            # excepción fuera de su bloque atómico: aquí solo se traduce a mensaje.
            logger.error(f"Error al guardar días especiales anual: {e}", exc_info=True)
            return False, f"Error al guardar días especiales: {str(e)}"
        finally:
            # Se libera fuera del bloque atómico, ya con los datos confirmados en BD.
            CacheService.delete(clave_lock)

    @staticmethod
    @transaction.atomic
    def _escribir_dias_especiales_anual(
        tipo: str,
        anio: int,
        dias_seleccionados: Dict[int, List[int]],
        descripcion: str
    ) -> tuple[bool, str]:
        """
        Borra y recrea los días del tipo/año dentro de una única transacción.

        Cualquier excepción se propaga a propósito para que el `atomic` revierta:
        capturarla aquí dentro confirmaría un año a medio escribir.
        """
        eliminados = DiaEspecialService.eliminar_dias_por_tipo_anio(tipo, anio)

        logger.info(f"Guardando días {tipo} para año {anio}. Días seleccionados: {dias_seleccionados}")

        if not dias_seleccionados:
            return True, f"Se eliminaron los {eliminados} días de {tipo} del año {anio}. El año queda sin {tipo}s."

        dias_creados = 0

        for mes, dias in dias_seleccionados.items():
            if not dias:  # Si no hay días seleccionados para este mes, continuar
                continue

            # Convertir mes a int si viene como string (del JSON)
            try:
                mes = int(mes)
            except (ValueError, TypeError):
                logger.warning(f"Mes inválido (no es número): {mes}")
                continue

            # Validar mes
            if mes < 1 or mes > 12:
                logger.warning(f"Mes inválido ignorado: {mes}")
                continue

            for dia in dias:
                # Convertir día a int si viene como string
                try:
                    dia = int(dia)
                except (ValueError, TypeError):
                    logger.warning(f"Día inválido (no es número): {dia}")
                    continue

                # Validar día según el mes
                if not DiaEspecialService._validar_dia_mes(anio, mes, dia):
                    logger.warning(f"Día inválido ignorado: {anio}-{mes:02d}-{dia:02d}")
                    continue

                fecha = date(anio, mes, dia)

                # Se busca por (fecha, tipo): la misma fecha puede tener además una
                # temporada o un día del otro tipo, y esos no se tocan aquí.
                DiaEspecial.objects.update_or_create(
                    fecha=fecha,
                    tipo=tipo,
                    defaults={
                        'descripcion': descripcion,
                        'es_temporada': False,
                        'activo': True,
                        'recurrente': False,
                    }
                )
                dias_creados += 1

        return True, f"Se guardaron {dias_creados} días de {tipo} para el año {anio}."

    @staticmethod
    @transaction.atomic
    def eliminar_dias_por_tipo_anio(tipo: str, anio: int) -> int:
        """
        Elimina todos los días especiales de un tipo y año específicos.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año del cual eliminar los días
            
        Returns:
            Número de registros eliminados
        """
        # Se filtra por `fecha__year` y no por `año_planificacion`: la fecha es el dato
        # autoritativo, así que un registro antiguo con el año desincronizado igual se limpia.
        eliminados = DiaEspecial.objects.filter(
            tipo=tipo,
            fecha__year=anio,
            es_temporada=False
        ).delete()[0]
        
        logger.info(f"Se eliminaron {eliminados} días de {tipo} del año {anio}")
        return eliminados

    @staticmethod
    def validar_fechas_dia_especial(tipo: str, anio: int, dias_seleccionados: Dict[int, List[int]]) -> tuple[bool, str]:
        """
        Valida que las fechas de días especiales sean válidas.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año a validar
            dias_seleccionados: Diccionario con mes como clave y lista de días como valor
            
        Returns:
            Tupla (válido, mensaje_error)
        """
        if tipo not in ['festivo', 'mantenimiento']:
            return False, f"Tipo inválido: {tipo}. Debe ser 'festivo' o 'mantenimiento'."
        
        if anio < DiaEspecial.ANIO_MIN or anio > DiaEspecial.ANIO_MAX:
            return False, f"Año inválido: {anio}. Debe estar entre {DiaEspecial.ANIO_MIN} y {DiaEspecial.ANIO_MAX}."

        for mes, dias in dias_seleccionados.items():
            if mes < 1 or mes > 12:
                return False, f"Mes inválido: {mes}. Debe estar entre 1 y 12."
            
            for dia in dias:
                if not DiaEspecialService._validar_dia_mes(anio, mes, dia):
                    return False, f"Día inválido: {dia} para el mes {mes} del año {anio}."
        
        return True, ""

    @staticmethod
    def _validar_dia_mes(anio: int, mes: int, dia: int) -> bool:
        """
        Valida que un día sea válido para un mes y año específicos.
        Considera años bisiestos.
        
        Args:
            anio: Año
            mes: Mes (1-12)
            dia: Día
            
        Returns:
            True si el día es válido, False en caso contrario
        """
        try:
            fecha = date(anio, mes, dia)
            # Si la fecha se crea correctamente, el día es válido
            return fecha.month == mes and fecha.day == dia
        except ValueError:
            return False

    @staticmethod
    def obtener_anios_con_tipo(tipo: str) -> List[int]:
        """
        Obtiene la lista de años que tienen días especiales del tipo especificado configurados.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            
        Returns:
            Lista de años ordenados de forma descendente
        """
        anios = DiaEspecial.objects.filter(
            tipo=tipo,
            activo=True,
            es_temporada=False
        ).values_list('año_planificacion', flat=True).distinct()
        
        return sorted(set(anios), reverse=True) if anios else []

    @staticmethod
    def tiene_dias_tipo_anio(tipo: str, anio: int) -> bool:
        """
        Verifica si un año tiene días especiales del tipo especificado configurados.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año a verificar
            
        Returns:
            True si el año tiene días del tipo, False en caso contrario
        """
        return DiaEspecial.objects.filter(
            tipo=tipo,
            año_planificacion=anio,
            activo=True,
            es_temporada=False
        ).exists()

    @staticmethod
    def calcular_festivos_automaticos(anio: int) -> Dict[int, List[int]]:
        """
        Calcula los festivos colombianos de un año (Ley Emiliani) y los devuelve
        agrupados por mes, SIN persistir en BD.

        Espejo de `calcular_dias_mantenimiento_automatico`: solo previsualiza. La
        persistencia ocurre únicamente cuando el admin guarda desde la vista anual
        (`guardar_dias_especiales_anual`), igual que temporada y mantenimiento.
        Así no se pre-cargan años que no se van a usar.

        Returns:
            Diccionario {mes: [dias]} para pintar en el calendario.
        """
        if anio < DiaEspecial.ANIO_MIN or anio > DiaEspecial.ANIO_MAX:
            error_msg = f"Año inválido: {anio}. Debe estar entre {DiaEspecial.ANIO_MIN} y {DiaEspecial.ANIO_MAX}."
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Calculando festivos automáticos para el año {anio}")

        # Festivos calculados (lista de {'fecha': date, 'descripcion': str})
        festivos_calculados = CalculadoraFestivos.calcular_festivos(anio)

        resultado: Dict[int, List[int]] = {}
        for festivo in festivos_calculados:
            fecha_festivo: date = festivo['fecha']
            # Solo el año solicitado (por seguridad)
            if fecha_festivo.year != anio:
                continue
            resultado.setdefault(fecha_festivo.month, [])
            if fecha_festivo.day not in resultado[fecha_festivo.month]:
                resultado[fecha_festivo.month].append(fecha_festivo.day)

        for mes in resultado:
            resultado[mes].sort()

        return resultado

    @staticmethod
    def calcular_dias_mantenimiento_automatico(anio: int) -> Dict[int, List[int]]:
        """
        Calcula automáticamente los días de mantenimiento para un año según las reglas:
        - Primer día hábil de cada semana (Lunes-Viernes)
        - Si el lunes es festivo, pasa al siguiente día hábil (martes, miércoles, etc.)
        - Si el lunes es temporada, NO se asigna día de mantenimiento esa semana
        - Si el lunes NO es temporada, se asigna como día de mantenimiento (si no es festivo)
        - Si el lunes es festivo pero no temporada, se busca el siguiente día hábil que no sea festivo ni temporada
        
        Args:
            anio: Año para el cual calcular los días de mantenimiento
            
        Returns:
            Diccionario con mes como clave y lista de días como valor
            Ejemplo: {1: [6, 13, 20, 27], 2: [2, 9, 16, 23]}
        """
        if anio < DiaEspecial.ANIO_MIN or anio > DiaEspecial.ANIO_MAX:
            error_msg = f"Año inválido: {anio}. Debe estar entre {DiaEspecial.ANIO_MIN} y {DiaEspecial.ANIO_MAX}."
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Obtener todos los festivos del año
        festivos = DiaEspecialService.obtener_dias_por_tipo_anio('festivo', anio)
        fechas_festivos: Set[date] = {f.fecha for f in festivos}

        # La página de mantenimiento suele visitarse para el año siguiente, cuando los
        # festivos todavía no se han guardado. Sin este respaldo el cálculo trataría el
        # año como si no tuviera festivos y propondría mantenimientos encima de ellos.
        if not fechas_festivos:
            logger.info(f"El año {anio} no tiene festivos guardados; se usan los festivos calculados para el cálculo de mantenimiento.")
            festivos_calculados = DiaEspecialService.calcular_festivos_automaticos(anio)
            fechas_festivos = {
                date(anio, mes, dia)
                for mes, dias in festivos_calculados.items()
                for dia in dias
            }

        # Obtener todos los días de temporada del año
        temporadas = TemporadaService.obtener_dias_temporada_anio(anio)
        fechas_temporadas: Set[date] = {t.fecha for t in temporadas}
        
        # Inicializar resultado
        resultado: Dict[int, List[int]] = {}
        
        # Obtener el primer día del año
        fecha_actual = date(anio, 1, 1)
        
        # Avanzar hasta el primer lunes del año
        # weekday(): 0=Lunes, 1=Martes, ..., 6=Domingo
        # Si no es lunes, calcular días hasta el siguiente lunes
        if fecha_actual.weekday() != 0:  # Si no es lunes
            # Calcular días hasta el siguiente lunes
            # Si es domingo (6), avanzamos 1 día; si es martes (1), avanzamos 6 días, etc.
            dias_hasta_lunes = (7 - fecha_actual.weekday()) % 7
            fecha_actual += timedelta(days=dias_hasta_lunes)
        
        # Recorrer todas las semanas del año
        while fecha_actual.year == anio:
            # Verificar si el LUNES (primer día hábil) es temporada
            lunes_es_temporada = fecha_actual in fechas_temporadas
            
            # Si el lunes NO es temporada, calcular el día de mantenimiento
            if not lunes_es_temporada:
                dia_mantenimiento = None
                
                # Buscar el primer día hábil de la semana (Lunes-Viernes) que:
                # 1. NO sea festivo
                # 2. NO sea temporada
                for dia_semana in range(5):  # Lunes (0) a Viernes (4)
                    fecha_candidata = fecha_actual + timedelta(days=dia_semana)
                    
                    # Verificar que no se salga del año
                    if fecha_candidata.year != anio:
                        break
                    
                    # Si no es festivo Y no es temporada, este es el día de mantenimiento
                    if fecha_candidata not in fechas_festivos and fecha_candidata not in fechas_temporadas:
                        dia_mantenimiento = fecha_candidata
                        break
                
                # Si se encontró un día de mantenimiento, agregarlo al resultado
                if dia_mantenimiento:
                    mes = dia_mantenimiento.month
                    dia = dia_mantenimiento.day
                    
                    if mes not in resultado:
                        resultado[mes] = []
                    resultado[mes].append(dia)
            
            # Avanzar a la siguiente semana (7 días)
            fecha_actual += timedelta(days=7)
        
        # Ordenar los días de cada mes
        for mes in resultado:
            resultado[mes].sort()
        
        logger.info(f"Calculados {sum(len(dias) for dias in resultado.values())} días de mantenimiento automático para el año {anio}")
        
        return resultado

