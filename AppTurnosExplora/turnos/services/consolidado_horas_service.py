"""
Servicio para el Consolidado de Horas.

Fuente de verdad: DeudaCorporativa (cada doblada efectiva AM+PM acumula 30 min = 0.5 h).
Se separa por rol del explorador en la solicitud que originó cada deuda:
- Solicitante: el explorador era quien pidió la doblada (acumula al doblarse en la fecha de pago).
- Reemplazante: el explorador cubrió a otro (acumula al doblarse en la fecha de cesión).
- Otras: dobladas predeterminadas de fin de semana (sin solicitud) u orígenes sin rol claro.

Pendiente (futuro): Permisos Especiales y Pago de Horas (descuentos) también afectan el total.
"""
from empleados.models import Empleado
from solicitudes.models import DeudaCorporativa

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
        # Se leen de las deudas MENSUALES y no de `horas_totales()`. La diferencia importa:
        # el total del permiso ignora lo ya abonado a cuenta, así que un permanente medio
        # pagado seguiría figurando por su importe completo. Aquí se suma lo PENDIENTE, mes
        # a mes, que es lo que de verdad se le puede reclamar.
        from permisos.models import DeudaPermisoMes
        deudas_mes = (
            DeudaPermisoMes.objects
            .filter(explorador=empleado, estado='activa')
            .select_related('permiso')
            .order_by('anio', 'mes', 'id')
        )
        permisos = []
        total_permisos = 0.0
        for d in deudas_mes:
            if d.minutos_pendientes <= 0:
                continue
            pe = d.permiso
            h = d.horas_pendientes
            total_permisos += h
            if pe.es_permanente:
                detalle = pe.dias_semana_legible()
            else:
                detalle = pe.especificacion or ''
            permisos.append({
                'fecha_str': f'{_MESES_ES[d.mes].capitalize()} {d.anio}',
                'horas': h,
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
            .prefetch_related('deudas_pagadas__solicitud_origen__tipo_cambio', 'permisos_pagados')
            .order_by('fecha')
        )
        pagos = []
        for p in pagos_qs:
            # Trazabilidad: qué deudas concretas saldó este pago (evita conflictos
            # supervisor/explorador: se ve exactamente qué se pagó).
            detalle_deudas = []
            for d in p.deudas_pagadas.all():
                origen = (d.solicitud_origen.tipo_cambio.nombre
                          if d.solicitud_origen and d.solicitud_origen.tipo_cambio else 'Doblada')
                detalle_deudas.append({
                    'tipo': 'doblada',
                    'fecha_str': _fecha_es(d.fecha_doblada),
                    'horas': round(d.minutos / 60, 2),
                    'descripcion': f'{origen} {_fecha_es(d.fecha_doblada)}',
                })
            for pe in p.permisos_pagados.all():
                detalle_deudas.append({
                    'tipo': 'permiso',
                    'fecha_str': _fecha_es(pe.fecha_inicio),
                    'horas': round(pe.horas_totales(), 2),
                    'descripcion': f'Permiso {pe.get_tipo_display()} {_fecha_es(pe.fecha_inicio)}',
                })
            pagos.append({
                'fecha': p.fecha,
                'fecha_str': _fecha_es(p.fecha),
                'horas': float(p.horas),
                'lider': f"{p.supervisor.nombre} {p.supervisor.apellido}" if p.supervisor else '—',
                'comentario': p.comentario or '',
                'detalle_deudas': detalle_deudas,
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
