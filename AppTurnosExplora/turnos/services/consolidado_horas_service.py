"""
Servicio para el Consolidado de Horas.

Fuente de verdad: DeudaCorporativa (cada doblada efectiva AM+PM acumula 30 min = 0.5 h).
Se separa por rol del explorador en la solicitud que originó cada deuda:
- Solicitante: el explorador era quien pidió la doblada (acumula al doblarse en la fecha de pago).
- Reemplazante: el explorador cubrió a otro (acumula al doblarse en la fecha de cesión).
- Otras: dobladas predeterminadas de fin de semana (sin solicitud) u orígenes sin rol claro.

Pendiente (futuro): Permisos Especiales y Pago de Horas (descuentos) también afectan el total.
"""
from solicitudes.models import DeudaCorporativa
from empleados.models import Empleado

_MESES_ES = [
    '', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]


def _fecha_es(d):
    """Formatea una fecha como 'j de mes de aaaa' en español (LANGUAGE_CODE es en-us)."""
    if not d:
        return ''
    return f"{d.day} de {_MESES_ES[d.month]} de {d.year}"


class ConsolidadoHorasService:
    """Calcula el consolidado de horas acumuladas de un explorador."""

    @staticmethod
    def es_supervisor(user) -> bool:
        """True si el usuario es supervisor/admin (puede consultar a cualquiera)."""
        if getattr(user, 'is_staff', False):
            return True
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return False
        return empleado.empleadorole_set.filter(role__nombre__icontains='supervisor').exists()

    @staticmethod
    def exploradores_disponibles():
        """Lista de exploradores activos para el selector del supervisor."""
        return Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')

    @staticmethod
    def get_consolidado(empleado) -> dict:
        """
        Devuelve el consolidado de horas del explorador, separado por rol.

        Estructura:
            {
              'solicitante': [{fecha, horas, tipo, comentario}, ...],
              'reemplazante': [...],
              'otras': [...],
              'total_solicitante', 'total_reemplazante', 'total_otras', 'total_horas'
            }
        """
        deudas = (
            DeudaCorporativa.objects
            .filter(explorador=empleado, estado='activa')
            .select_related(
                'solicitud_origen',
                'solicitud_origen__explorador_solicitante',
                'solicitud_origen__explorador_receptor',
                'solicitud_origen__tipo_cambio',
            )
            .order_by('fecha_doblada')
        )

        solicitante, reemplazante, otras = [], [], []
        total_min = 0

        for d in deudas:
            total_min += d.minutos
            s = d.solicitud_origen
            fila = {
                'fecha': d.fecha_doblada,
                'fecha_str': _fecha_es(d.fecha_doblada),
                'horas': round(d.minutos / 60, 2),
                'tipo': (s.tipo_cambio.nombre if s and s.tipo_cambio else 'Fin de semana'),
                'comentario': d.comentario or '',
            }
            if s and s.explorador_solicitante_id == empleado.id:
                fila['contraparte'] = f"{s.explorador_receptor.nombre} {s.explorador_receptor.apellido}" if s.explorador_receptor else '—'
                solicitante.append(fila)
            elif s and s.explorador_receptor_id == empleado.id:
                fila['contraparte'] = f"{s.explorador_solicitante.nombre} {s.explorador_solicitante.apellido}" if s.explorador_solicitante else '—'
                reemplazante.append(fila)
            else:
                fila['contraparte'] = '—'
                otras.append(fila)

        def _suma(filas):
            return round(sum(f['horas'] for f in filas), 2)

        # --- Permisos especiales aprobados: acumulan horas que el explorador debe ---
        from permisos.models import PermisoEspecial
        pe_qs = (
            PermisoEspecial.objects
            .filter(empleado=empleado, estado='APROBADO', pagado=False)
            .order_by('fecha_inicio')
        )
        permisos = []
        total_permisos = 0.0
        for pe in pe_qs:
            h = pe.horas_totales()
            total_permisos += h
            if pe.es_permanente:
                fecha_txt = f"{_fecha_es(pe.fecha_inicio)} – {_fecha_es(pe.fecha_fin)}"
                detalle = pe.dias_semana_legible()
            else:
                fecha_txt = _fecha_es(pe.fecha_inicio)
                detalle = pe.especificacion or ''
            permisos.append({
                'fecha_str': fecha_txt,
                'horas': round(h, 2),
                'tiempo': float(pe.tiempo or 0),
                'es_permanente': pe.es_permanente,
                'tipo': pe.get_tipo_display(),
                'detalle': detalle,
                'motivo': pe.motivo,
            })
        total_permisos = round(total_permisos, 2)

        # Las deudas pagadas ahora se marcan (doblada estado='pagada', permiso pagado=True),
        # por lo que las listas de arriba YA son solo lo pendiente. El saldo es directamente
        # lo pendiente; no se vuelve a restar el pagado (eso causaría doble descuento).
        saldo = round(total_min / 60 + total_permisos, 2)

        # --- Pagos de horas (PDH): descuentos autorizados por un supervisor ---
        from permisos.models import PDH
        pagos_qs = (
            PDH.objects
            .filter(explorador=empleado, tipo_registro='pago_horas')
            .select_related('supervisor')
            .order_by('fecha')
        )
        pagos = []
        for p in pagos_qs:
            pagos.append({
                'fecha': p.fecha,
                'fecha_str': _fecha_es(p.fecha),
                'horas': float(p.horas),
                'lider': f"{p.supervisor.nombre} {p.supervisor.apellido}" if p.supervisor else '—',
                'comentario': p.comentario or '',
            })
        total_pagado = round(sum(p['horas'] for p in pagos), 2)
        # Histórico = lo que aún debe + lo que ya pagó (solo informativo).
        total_acumulado = round(saldo + total_pagado, 2)

        return {
            'solicitante': solicitante,
            'reemplazante': reemplazante,
            'otras': otras,
            'permisos': permisos,
            'pagos': pagos,
            'total_solicitante': _suma(solicitante),
            'total_reemplazante': _suma(reemplazante),
            'total_otras': _suma(otras),
            'total_permisos': total_permisos,
            'total_acumulado': total_acumulado,
            'total_pagado': total_pagado,
            # total_horas = saldo pendiente (lo que aún debe)
            'total_horas': saldo,
        }
