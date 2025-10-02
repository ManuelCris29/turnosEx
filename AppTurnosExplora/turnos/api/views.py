from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View
from django.http import JsonResponse
from turnos.models import Turno, AsignarJornadaExplorador
from turnos.services.turno_service import TurnoService
from datetime import datetime, timedelta


class TurnosPorDiaView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        if not fecha:
            return JsonResponse({'error': 'Debe seleccionar una fecha'}, status=400)
        data = TurnoService.get_exploradores_por_jornada(fecha)
        # Serializar empleados (solo nombre y apellido)
        am = [{'id': e.id, 'nombre': e.nombre, 'apellido': e.apellido} for e in data['am']]
        pm = [{'id': e.id, 'nombre': e.nombre, 'apellido': e.apellido} for e in data['pm']]
        return JsonResponse({'am': am, 'pm': pm})


class TurnosPorMesView(LoginRequiredMixin, View):
    def get(self, request):
        fecha_inicio = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')
        if not fecha_inicio or not fecha_fin:
            return JsonResponse({'error': 'Debe enviar fecha_inicio y fecha_fin'}, status=400)
        data = TurnoService.get_exploradores_por_jornada_rango(fecha_inicio, fecha_fin)
        # Serializar empleados (ya son dicts)
        serializado = {}
        for dia, grupos in data.items():
            serializado[dia] = {
                'am': grupos['am'],
                'pm': grupos['pm'],
            }
        return JsonResponse(serializado)


class MisTurnosPorMesView(LoginRequiredMixin, View):
    """Vista para obtener jornadas de un mes específico (cálculo dinámico)"""
    
    def get(self, request):
        if not hasattr(request.user, 'empleado'):
            return JsonResponse({'error': 'Usuario no es empleado'}, status=400)
        
        empleado = request.user.empleado
        mes = request.GET.get('mes')  # formato: '08' o '8'
        anio = request.GET.get('anio')  # formato: '2025'
        
        if not mes or not anio:
            return JsonResponse({'error': 'Debe enviar mes y anio'}, status=400)
        # Validación y normalización de mes/año
        try:
            mes_int = int(mes)
            anio_int = int(anio)
            if not (1 <= mes_int <= 12):
                return JsonResponse({'error': 'Mes invalido'}, status=400)
            mes = f"{mes_int:02d}"
        except ValueError:
            return JsonResponse({'error': 'anio/mes deben ser numéricos'}, status=400)
        
        try:
            # Calcular inicio y fin del mes solicitado
            fecha_inicio = datetime.strptime(f"{anio}-{mes}-01", "%Y-%m-%d").date()
            if int(mes) == 12:
                fecha_fin = datetime.strptime(f"{int(anio)+1}-01-01", "%Y-%m-%d").date() - timedelta(days=1)
            else:
                fecha_fin = datetime.strptime(f"{anio}-{int(mes)+1:02d}-01", "%Y-%m-%d").date() - timedelta(days=1)
            
            # Obtener turnos del mes solicitado (optimizado, evitando N+1)
            turnos_mes = (
                Turno.objects
                .filter(explorador=empleado, fecha__gte=fecha_inicio, fecha__lte=fecha_fin)
                .select_related('jornada', 'sala')
                .order_by('fecha')
            )
            turnos_por_fecha = {t.fecha: t for t in turnos_mes}
            
            # Obtener jornada predeterminada (un único registro vigente por explorador)
            try:
                jornada_predeterminada = AsignarJornadaExplorador.objects.select_related('jornada').get(
                    explorador=empleado
                )
            except AsignarJornadaExplorador.DoesNotExist:
                jornada_predeterminada = None
            jornada_base = (jornada_predeterminada.jornada.nombre if jornada_predeterminada else None)

            def calcular_jornada_dia(j_base, fecha):
                if not j_base:
                    return "PM"
                if j_base == "AM" and fecha.weekday() == 5:  # Sábado
                    return "Descanso"
                if j_base == "PM" and fecha.weekday() == 6:  # Domingo
                    return "Descanso"
                return j_base
            
            # Crear estructura de datos para el mes
            turnos_mes_dict = {}
            dias_mes = (fecha_fin - fecha_inicio).days + 1
            for i in range(dias_mes):
                fecha = fecha_inicio + timedelta(days=i)
                turno = turnos_por_fecha.get(fecha)
                
                if turno:
                    turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                        'jornada': turno.jornada.nombre,
                        'sala': (turno.sala.nombre if turno.sala else 'Por asignar'),
                        'tipo': 'asignado',
                        'es_cambio': turno.tipo_cambio is not None
                    }
                else:
                    # Usar jornada predeterminada con regla de descanso
                    jornada_nombre = calcular_jornada_dia(jornada_base, fecha)
                    
                    turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                        'jornada': jornada_nombre,
                        'sala': 'Por asignar',
                        'tipo': 'predeterminado',
                        'es_cambio': False
                    }
            
            return JsonResponse(turnos_mes_dict)
            
        except Exception as e:
            return JsonResponse({'error': f'Error al procesar fechas: {str(e)}'}, status=400)
