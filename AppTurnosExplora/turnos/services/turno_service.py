from empleados.models import Empleado, Jornada
from turnos.models import AsignarJornadaExplorador, Turno
from datetime import datetime, timedelta
import re
from django.db import models

class TurnoService:
    @staticmethod
    def get_exploradores_por_jornada(fecha):
        fecha_str = re.match(r"\d{4}-\d{2}-\d{2}", fecha).group(0)
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        exploradores = Empleado.objects.filter(activo=True)
        am, pm = [], []
        for explorador in exploradores:
            turno = Turno.objects.filter(explorador=explorador, fecha=fecha_obj).first()
            if turno:
                jornada = turno.jornada
                tipo = 'cambio'
            else:
                asignacion = AsignarJornadaExplorador.objects.filter(
                    explorador=explorador,
                    fecha_inicio__lte=fecha_obj
                ).filter(
                    models.Q(fecha_fin__isnull=True) | models.Q(fecha_fin__gte=fecha_obj)
                ).order_by('-fecha_inicio').first()
                jornada = asignacion.jornada if asignacion else None
                tipo = 'oficial' if jornada else None
            if jornada:
                item = {'id': explorador.id, 'nombre': explorador.nombre, 'apellido': explorador.apellido, 'tipo': tipo}
                if jornada.nombre.strip().lower() == 'am':
                    am.append(item)
                elif jornada.nombre.strip().lower() == 'pm':
                    pm.append(item)
        return {'am': am, 'pm': pm}

    @staticmethod
    def get_exploradores_por_jornada_rango(fecha_inicio, fecha_fin):
        inicio_str = re.match(r"\d{4}-\d{2}-\d{2}", fecha_inicio).group(0)
        fin_str = re.match(r"\d{4}-\d{2}-\d{2}", fecha_fin).group(0)
        inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
        fin = datetime.strptime(fin_str, '%Y-%m-%d').date()
        dias = (fin - inicio).days + 1
        resultado = {}
        for i in range(dias):
            dia = inicio + timedelta(days=i)
            resultado[str(dia)] = TurnoService.get_exploradores_por_jornada(str(dia))
        return resultado 