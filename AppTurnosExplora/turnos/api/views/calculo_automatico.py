from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View
from django.http import JsonResponse
from datetime import date


class CalcularMantenimientoAutomaticoView(LoginRequiredMixin, View):
    """
    Endpoint API para calcular automáticamente los días de mantenimiento para un año.

    Parámetros:
    - anio: Año (requerido)

    Retorna JSON con días de mantenimiento calculados automáticamente, agrupados por mes.
    """

    def get(self, request):
        try:
            anio = request.GET.get('anio')

            if not anio:
                return JsonResponse({'error': 'El parámetro "anio" es requerido'}, status=400)

            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)

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
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al calcular días de mantenimiento automático: {e}")
            return JsonResponse({'error': f'Error al calcular días de mantenimiento: {str(e)}'}, status=500)


class CalcularFestivosAutomaticoView(LoginRequiredMixin, View):
    """
    Endpoint API para generar y obtener automáticamente los días festivos para un año.

    Parámetros:
    - anio: Año (requerido)

    Retorna JSON con días festivos calculados y/o generados en BD, agrupados por mes.
    """

    def get(self, request):
        try:
            anio = request.GET.get('anio')

            if not anio:
                return JsonResponse({'error': 'El parámetro \"anio\" es requerido'}, status=400)

            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)

            # Validar año mínimo (solo para evitar años históricos muy antiguos)
            if anio < 2000:
                return JsonResponse({
                    'error': f'El año debe ser mayor o igual a 2000. Año proporcionado: {anio}'
                }, status=400)

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
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al calcular festivos automáticos: {e}")
            return JsonResponse({'error': f'Error al calcular festivos automáticos: {str(e)}'}, status=500)
