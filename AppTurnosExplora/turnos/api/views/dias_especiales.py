from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View
from django.http import JsonResponse
from core.utils.json_responses import json_error_inesperado
from turnos.models import DiaEspecial
from turnos.services.temporada_service import TemporadaService
from datetime import datetime
from core.utils.date_utils import DateUtils


class DiasFestivosView(LoginRequiredMixin, View):
    """
    Vista para obtener días festivos.
    Útil para mostrar en calendarios y validaciones.

    ESTRATEGIA HÍBRIDA:
    1. Intenta usar biblioteca calendario-colombiano (más precisa)
    2. Si no está disponible, usa festivos de BD
    3. Combina ambos para máxima precisión

    OPTIMIZACIÓN: Usa caché para evitar consultas repetidas a la BD.
    Los festivos no cambian frecuentemente, así que se cachean por 1 hora.
    """

    def _obtener_festivos_calculados(self, año_inicio, año_fin):
        """
        Obtiene festivos calculados usando biblioteca externa si está disponible.
        Retorna dict con fecha (YYYY-MM-DD) como clave y descripción como valor.
        """
        festivos_calculados = {}

        try:
            # Intentar usar biblioteca calendario-colombiano
            from calendario_colombiano import CalendarioColombiano
            from datetime import date, timedelta

            calendario = CalendarioColombiano()

            # Obtener festivos para el rango de años
            fecha_inicio = date(año_inicio, 1, 1)
            fecha_fin = date(año_fin, 12, 31)
            fecha_actual = fecha_inicio

            while fecha_actual <= fecha_fin:
                if calendario.es_festivo(fecha_actual):
                    fecha_str = fecha_actual.strftime('%Y-%m-%d')
                    # Obtener nombre del festivo si es posible
                    nombre = getattr(calendario, 'nombre_festivo', lambda d: 'Día festivo')(fecha_actual)
                    festivos_calculados[fecha_str] = nombre
                fecha_actual += timedelta(days=1)

        except ImportError:
            # Si no está instalada la biblioteca, retornar vacío
            # El frontend usará su cálculo JavaScript como respaldo
            pass
        except Exception as e:
            # En caso de error, continuar sin festivos calculados
            import logging
            logger = logging.getLogger(__name__)
            # exc_info: sin la traza este aviso no sirve para diagnosticar nada,
            # y el fallo es silencioso para el usuario (se sigue sin festivos).
            logger.warning('Error al calcular festivos con biblioteca externa', exc_info=True)

        return festivos_calculados

    def get(self, request):
        """
        Obtener días festivos.

        Parámetros opcionales:
        - fecha_inicio: Fecha de inicio (formato: YYYY-MM-DD)
        - fecha_fin: Fecha de fin (formato: YYYY-MM-DD)
        - anio: Año específico (formato: YYYY)
        - mes: Mes específico (formato: MM)
        - sin_cache: Si es 'true', omite el caché (útil para testing)

        Si no se proporcionan parámetros, devuelve todos los festivos activos.
        """
        try:
            fecha_inicio = request.GET.get('fecha_inicio')
            fecha_fin = request.GET.get('fecha_fin')
            anio = request.GET.get('anio')
            mes = request.GET.get('mes')
            sin_cache = request.GET.get('sin_cache', 'false').lower() == 'true'

            # Generar clave de caché basada en los filtros
            cache_key = 'dias_festivos'
            if fecha_inicio:
                cache_key += f'_desde_{fecha_inicio}'
            if fecha_fin:
                cache_key += f'_hasta_{fecha_fin}'
            if anio:
                cache_key += f'_anio_{anio}'
            if mes:
                cache_key += f'_mes_{mes}'

            # Intentar obtener del caché usando CacheService (solo si no se solicita sin caché)
            if not sin_cache:
                from core.services.cache_service import CacheService
                cached_data = CacheService.get(cache_key)
                if cached_data is not None:
                    return JsonResponse(cached_data)

            # Construir query base
            festivos = DiaEspecial.objects.filter(
                tipo='festivo',
                activo=True
            )

            # Filtrar por rango de fechas si se proporciona
            if fecha_inicio and fecha_fin:
                fecha_inicio_obj = DateUtils.parse_date(fecha_inicio)
                fecha_fin_obj = DateUtils.parse_date(fecha_fin)
                festivos = festivos.filter(fecha__gte=fecha_inicio_obj, fecha__lte=fecha_fin_obj)
            elif fecha_inicio:
                fecha_inicio_obj = DateUtils.parse_date(fecha_inicio)
                festivos = festivos.filter(fecha__gte=fecha_inicio_obj)
            elif fecha_fin:
                fecha_fin_obj = DateUtils.parse_date(fecha_fin)
                festivos = festivos.filter(fecha__lte=fecha_fin_obj)

            # Filtrar por año si se proporciona
            if anio:
                festivos = festivos.filter(fecha__year=int(anio))

            # Filtrar por mes si se proporciona
            if mes:
                festivos = festivos.filter(fecha__month=int(mes))

            # Serializar resultados de BD
            festivos_list = []
            festivos_bd = {}  # Dict para fácil combinación

            for festivo in festivos.order_by('fecha'):
                fecha_str = festivo.fecha.strftime('%Y-%m-%d')
                festivos_bd[fecha_str] = festivo.descripcion or 'Día festivo'
                festivos_list.append({
                    'fecha': fecha_str,
                    'descripcion': festivo.descripcion or '',
                    'recurrente': festivo.recurrente
                })

            # Obtener festivos calculados
            # Si no se especifica año, calcular para un rango amplio (año actual - 1 a + 10)
            año_actual = datetime.now().year

            if anio:
                # Si se especifica un año, calcular solo para ese año
                año_inicio = int(anio)
                año_fin = int(anio)
            else:
                # Si no se especifica, calcular para un rango amplio
                año_inicio = año_actual - 1
                año_fin = año_actual + 10

            # Combinar festivos calculados con los de BD
            festivos_calculados = self._obtener_festivos_calculados(año_inicio, año_fin)

            # Los festivos de BD tienen prioridad, pero agregamos los calculados que no estén en BD
            for fecha_calc, descripcion_calc in festivos_calculados.items():
                if fecha_calc not in festivos_bd:
                    festivos_list.append({
                        'fecha': fecha_calc,
                        'descripcion': descripcion_calc,
                        'recurrente': False
                    })

            # Ordenar por fecha
            festivos_list.sort(key=lambda x: x['fecha'])

            response_data = {
                'festivos': festivos_list,
                'total': len(festivos_list),
                'fuente': 'bd_y_calculado' if festivos_calculados else 'bd'
            }

            # Guardar en caché usando CacheService
            # Los festivos no cambian frecuentemente
            if not sin_cache:
                from core.services.cache_service import CacheService
                from core.services.cache_service import CACHE_TTL_LONG
                CacheService.set(cache_key, response_data, ttl=CACHE_TTL_LONG)

            return JsonResponse(response_data)

        except ValueError as e:
            return JsonResponse({'error': f'Formato de fecha inválido: {str(e)}'}, status=400)
        except Exception as e:
            return json_error_inesperado(
                request, e, 'No pudimos cargar los festivos. Inténtalo de nuevo.')


class DiasTemporadaView(LoginRequiredMixin, View):
    """
    Endpoint API para obtener días de temporada por año y mes.

    Parámetros:
    - anio: Año (requerido)
    - mes: Mes opcional (1-12)

    Retorna JSON con días de temporada agrupados por mes.
    """

    def get(self, request):
        try:
            anio = request.GET.get('anio')
            mes = request.GET.get('mes')

            if not anio:
                return JsonResponse({'error': 'El parámetro "anio" es requerido'}, status=400)

            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)

            if mes:
                try:
                    mes = int(mes)
                    if mes < 1 or mes > 12:
                        return JsonResponse({'error': 'El mes debe estar entre 1 y 12'}, status=400)

                    # Obtener días de temporada del mes específico
                    dias_temporada = TemporadaService.obtener_dias_temporada_mes(anio, mes)
                    temporadas = [
                        {
                            'fecha': dia.fecha.strftime('%Y-%m-%d'),
                            'mes': dia.mes or dia.fecha.month,
                            'dia': dia.fecha.day,
                            'descripcion': dia.descripcion or 'Día de temporada'
                        }
                        for dia in dias_temporada
                    ]

                    return JsonResponse({
                        'temporadas': temporadas,
                        'total': len(temporadas),
                        'anio': anio,
                        'mes': mes
                    })
                except ValueError:
                    return JsonResponse({'error': 'El mes debe ser un número válido'}, status=400)
            else:
                # Obtener todos los días de temporada del año, agrupados por mes
                dias_por_mes = TemporadaService.obtener_dias_temporada_por_mes(anio)
                dias_temporada = TemporadaService.obtener_dias_temporada_anio(anio)

                temporadas = [
                    {
                        'fecha': dia.fecha.strftime('%Y-%m-%d'),
                        'mes': dia.mes or dia.fecha.month,
                        'dia': dia.fecha.day,
                        'descripcion': dia.descripcion or 'Día de temporada'
                    }
                    for dia in dias_temporada
                ]

                return JsonResponse({
                    'temporadas': temporadas,
                    'por_mes': dias_por_mes,
                    'total': len(temporadas),
                    'anio': anio
                })

        except Exception as e:
            return json_error_inesperado(
                request, e, 'No pudimos cargar los días de temporada. Inténtalo de nuevo.')


class DiasEspecialesPorTipoView(LoginRequiredMixin, View):
    """
    Endpoint API para obtener días especiales (festivos o mantenimiento) por tipo, año y mes.

    Parámetros:
    - tipo: Tipo de día especial ('festivo' o 'mantenimiento') (requerido)
    - anio: Año (requerido)
    - mes: Mes opcional (1-12)

    Retorna JSON con días especiales agrupados por mes.
    """

    def get(self, request):
        try:
            tipo = request.GET.get('tipo')
            anio = request.GET.get('anio')
            mes = request.GET.get('mes')

            if not tipo:
                return JsonResponse({'error': 'El parámetro "tipo" es requerido'}, status=400)

            if tipo not in ['festivo', 'mantenimiento']:
                return JsonResponse({'error': 'El tipo debe ser "festivo" o "mantenimiento"'}, status=400)

            if not anio:
                return JsonResponse({'error': 'El parámetro "anio" es requerido'}, status=400)

            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)

            from turnos.services.dia_especial_service import DiaEspecialService

            if mes:
                try:
                    mes = int(mes)
                    if mes < 1 or mes > 12:
                        return JsonResponse({'error': 'El mes debe estar entre 1 y 12'}, status=400)

                    # Obtener días del tipo del mes específico
                    dias_especiales = DiaEspecialService.obtener_dias_por_tipo_mes(tipo, anio, mes)
                    dias_list = [
                        {
                            'fecha': dia.fecha.strftime('%Y-%m-%d'),
                            'mes': dia.mes or dia.fecha.month,
                            'dia': dia.fecha.day,
                            'descripcion': dia.descripcion or f'Día de {tipo}'
                        }
                        for dia in dias_especiales
                    ]

                    return JsonResponse({
                        'dias': dias_list,
                        'total': len(dias_list),
                        'tipo': tipo,
                        'anio': anio,
                        'mes': mes
                    })
                except ValueError:
                    return JsonResponse({'error': 'El mes debe ser un número válido'}, status=400)
            else:
                # Obtener todos los días del tipo del año, agrupados por mes
                dias_por_mes = DiaEspecialService.obtener_dias_por_tipo_por_mes(tipo, anio)
                dias_especiales = DiaEspecialService.obtener_dias_por_tipo_anio(tipo, anio)

                dias_list = [
                    {
                        'fecha': dia.fecha.strftime('%Y-%m-%d'),
                        'mes': dia.mes or dia.fecha.month,
                        'dia': dia.fecha.day,
                        'descripcion': dia.descripcion or f'Día de {tipo}'
                    }
                    for dia in dias_especiales
                ]

                return JsonResponse({
                    'dias': dias_list,
                    'por_mes': dias_por_mes,
                    'total': len(dias_list),
                    'tipo': tipo,
                    'anio': anio
                })

        except Exception as e:
            return json_error_inesperado(
                request, e, 'No pudimos cargar los días especiales. Inténtalo de nuevo.')
