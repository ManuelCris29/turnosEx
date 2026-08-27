from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.generic import View

from core.mixins import SupervisorApiRequiredMixin
from core.utils.json_responses import json_error_inesperado
from turnos.models import DiaEspecial


def _parsear_anio(request):
    """
    Lee y valida `anio` de la query string.

    Devuelve (anio, None) si es válido o (None, JsonResponse) con el error. El rango
    se acota porque el cálculo recorre el año semana a semana: sin tope, un año
    absurdo convierte una petición en un bucle de decenas de miles de iteraciones.
    """
    anio = request.GET.get('anio')

    if not anio:
        return None, JsonResponse({'error': 'El parámetro "anio" es requerido'}, status=400)

    try:
        anio = int(anio)
    except ValueError:
        return None, JsonResponse({'error': 'El año debe ser un número válido'}, status=400)

    if anio < DiaEspecial.ANIO_MIN or anio > DiaEspecial.ANIO_MAX:
        return None, JsonResponse({
            'error': f'El año debe estar entre {DiaEspecial.ANIO_MIN} y {DiaEspecial.ANIO_MAX}. Año proporcionado: {anio}'
        }, status=400)

    return anio, None


class CalcularMantenimientoAutomaticoView(LoginRequiredMixin, SupervisorApiRequiredMixin, View):
    """
    Endpoint API para calcular automáticamente los días de mantenimiento para un año.

    Parámetros:
    - anio: Año (requerido)

    Retorna JSON con días de mantenimiento calculados automáticamente, agrupados por mes.
    """

    def get(self, request):
        try:
            anio, error = _parsear_anio(request)
            if error:
                return error

            from turnos.services.dia_especial_service import DiaEspecialService

            # Calcular días de mantenimiento automático
            dias_por_mes = DiaEspecialService.calcular_dias_mantenimiento_automatico(anio)

            # Convertir a formato de lista para compatibilidad
            dias_list = []
            for mes, dias in dias_por_mes.items():
                for dia in dias:
                    fecha = date(anio, mes, dia)
                    dias_list.append({
                        'fecha': fecha.strftime('%Y-%m-%d'),
                        'mes': mes,
                        'dia': dia,
                        'descripcion': 'Día de mantenimiento'
                    })

            return JsonResponse({
                'dias': dias_list,
                'por_mes': dias_por_mes,
                'total': len(dias_list),
                'tipo': 'mantenimiento',
                'anio': anio
            })

        except Exception as e:
            return json_error_inesperado(
                request, e, 'No pudimos calcular los días de mantenimiento. Inténtalo de nuevo.')


class CalcularFestivosAutomaticoView(LoginRequiredMixin, SupervisorApiRequiredMixin, View):
    """
    Endpoint API para generar y obtener automáticamente los días festivos para un año.

    Parámetros:
    - anio: Año (requerido)

    Retorna JSON con días festivos calculados y/o generados en BD, agrupados por mes.
    """

    def get(self, request):
        try:
            anio, error = _parsear_anio(request)
            if error:
                return error

            from turnos.services.dia_especial_service import DiaEspecialService

            # Calcular festivos automáticos (solo previsualización, no persiste)
            dias_por_mes = DiaEspecialService.calcular_festivos_automaticos(anio)

            # Convertir a formato de lista para compatibilidad
            dias_list = []
            for mes, dias in dias_por_mes.items():
                for dia in dias:
                    fecha = date(anio, mes, dia)
                    dias_list.append({
                        'fecha': fecha.strftime('%Y-%m-%d'),
                        'mes': mes,
                        'dia': dia,
                        'descripcion': 'Día festivo'
                    })

            return JsonResponse({
                'dias': dias_list,
                'por_mes': dias_por_mes,
                'total': len(dias_list),
                'tipo': 'festivo',
                'anio': anio
            })

        except ValueError as e:
            # Capturar errores de validación de rango de años
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Intento de generar festivos con año inválido: {e}")
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return json_error_inesperado(
                request, e, 'No pudimos calcular los festivos del año. Inténtalo de nuevo.')
