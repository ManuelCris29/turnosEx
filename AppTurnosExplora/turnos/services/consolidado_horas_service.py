"""
Servicio para el Consolidado de Horas.

Fuente de verdad: DeudaCorporativa (cada doblada efectiva AM+PM acumula 30 min = 0.5 h).
Se separa por rol del explorador en la solicitud que originó cada deuda:
- Solicitante: el explorador era quien pidió la doblada (acumula al doblarse en la fecha de pago).
- Reemplazante: el explorador cubrió a otro (acumula al doblarse en la fecha de cesión).
- Otras: dobladas predeterminadas de fin de semana (sin solicitud) u orígenes sin rol claro.

Pendiente (futuro): Permisos Especiales y Pago de Horas (descuentos) también afectan el total.
"""

from django.db import models
from django.utils import timezone

from empleados.models import Empleado
from solicitudes.models import DeudaCorporativa
from solicitudes.services.sancion_deuda_calculo import Periodo

_MESES_ES = [
    '', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]


def _fecha_es(d):
    """Formatea una fecha como 'j de mes de aaaa' en español (LANGUAGE_CODE es en-us)."""
    if not d:
        return ''
    return f"{d.day} de {_MESES_ES[d.month]} de {d.year}"


def _dias_del_permiso(permiso):
    """
    Los días que abarca un permiso puntual, en español: '26 de junio de 2026'.

    La columna «Fecha» del consolidado decía «Junio 2026» aquí y «6 de noviembre de 2026»
    en las demás secciones, porque la deuda de permiso se guarda por mes y las dobladas por
    día. Dos vocabularios en la misma columna hacen dudar de si falta el día o es que no lo
    hay, así que el puntual —que tiene un día concreto— lo enseña.

    NO se recorta contra el mes de la deuda. Un permiso puntual genera UNA sola obligación,
    en el mes de su fecha de inicio, aunque el rango cruce de mes (`ocurrencias_por_mes`).
    Recortarlo escondería días que sí se deben: un permiso del 28/06 al 02/07 diría «28 al
    30 de junio» y se perderían dos días de vista.
    """
    desde = permiso.fecha_inicio
    hasta = permiso.fecha_fin or desde
    if hasta <= desde:
        return _fecha_es(desde)
    if (desde.year, desde.month) == (hasta.year, hasta.month):
        return f'{desde.day} al {hasta.day} de {_MESES_ES[desde.month]} de {desde.year}'
    return f'{_fecha_es(desde)} al {_fecha_es(hasta)}'


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
    def _extinguidas_por_sancion(empleado) -> list:
        """
        Deudas que extinguió una sanción, agrupadas por la sanción responsable.

        Son dos casos con el mismo efecto sobre el saldo y motivos distintos: la sanción se
        CUMPLIÓ (el castigo fue el pago) o el supervisor la LEVANTÓ (perdonó el hecho y con
        él la deuda). Van juntos porque el explorador pregunta lo mismo en ambos —"¿por qué
        dejé de deber estas horas?"— y separados por la marca `condonada`, porque la
        respuesta no es la misma y confundirlas haría creer que basta con que te levanten
        una sanción para no cumplir ninguna.

        Estas horas no están pendientes (ya no se pueden cobrar) ni pagadas (no hubo PDH),
        así que sin esta sección desaparecían del consolidado sin dejar rastro y el
        explorador no tenía dónde ver por qué dejó de deberlas. Se muestran aparte, con el
        mismo detalle que un pago, porque cumplen la misma función: explicar una extinción.
        """
        from empleados.models import SancionEmpleado

        consumidas = (
            SancionEmpleado.objects
            .filter(explorador=empleado)
            .filter(models.Q(deudas_corporativas_consumidas__isnull=False)
                    | models.Q(deudas_permiso_consumidas__isnull=False))
            .prefetch_related(
                'deudas_corporativas_consumidas__solicitud_origen__tipo_cambio',
                'deudas_permiso_consumidas__permiso',
            )
            .distinct()
            .order_by('fecha_inicio', 'id')
        )

        filas = []
        for sancion in consumidas:
            detalle, minutos = [], 0
            for d in sancion.deudas_corporativas_consumidas.all():
                origen = (d.solicitud_origen.tipo_cambio.nombre
                          if d.solicitud_origen and d.solicitud_origen.tipo_cambio else 'Doblada')
                minutos += d.minutos
                detalle.append({
                    'tipo': 'doblada',
                    'horas': round(d.minutos / 60, 2),
                    'descripcion': f'{origen} {_fecha_es(d.fecha_doblada)}',
                })
            for d in sancion.deudas_permiso_consumidas.all():
                # Lo extinguido es lo que quedaba SIN pagar: si abonó una parte a tiempo,
                # esa parte ya figura en la sección de pagos y contarla aquí la duplicaría.
                minutos += d.minutos_pendientes
                detalle.append({
                    'tipo': 'permiso',
                    'horas': d.horas_pendientes,
                    'descripcion': f'Permiso {d.permiso.get_tipo_display()} — {d.periodo.nombre()}',
                })
            if not detalle:
                continue
            filas.append({
                'periodo_str': (Periodo(sancion.periodo_anio, sancion.periodo_mes).nombre().capitalize()
                                if sancion.periodo_anio and sancion.periodo_mes else '—'),
                'horas': round(minutos / 60, 2),
                'inicio_str': _fecha_es(sancion.fecha_inicio),
                # El fin EFECTIVO, no el planeado: en una levantada el planeado nunca
                # llegó a ocurrir y enseñarlo sugeriría un castigo que no se cumplió.
                'fin_str': _fecha_es(sancion.fecha_fin_efectiva),
                'condonada': sancion.esta_levantada,
                'motivo': sancion.motivo,
                'detalle_deudas': detalle,
            })
        return filas

    @staticmethod
    def get_consolidado(empleado, hoy=None) -> dict:
        """
        Devuelve el consolidado de horas del explorador, separado por rol.

        Estructura:
            {
              'solicitante': [{fecha, horas, tipo, comentario}, ...],
              'reemplazante': [...],
              'otras': [...],
              'total_solicitante', 'total_reemplazante', 'total_otras', 'total_horas'
            }

        Cada línea de deuda lleva `vencida`: su mes ya cerró, así que sigue debiéndose pero
        YA NO SE PUEDE COBRAR —se extingue cumpliendo la sanción—. Sin esa marca, entre el
        vencimiento y el fin de la sanción el consolidado enseña una deuda con pinta de
        normal que en realidad nadie puede reclamar. `hoy` se inyecta para las pruebas.
        """
        hoy = hoy or timezone.localdate()
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
                'vencida': Periodo.de_fecha(d.fecha_doblada).esta_vencido(hoy),
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

        from permisos.models import DeudaPermisoMes

        # --- Permisos especiales aprobados: acumulan horas que el explorador debe ---
        # Se leen de las deudas MENSUALES y no de `horas_totales()`. La diferencia importa:
        # el total del permiso ignora lo ya abonado a cuenta, así que un permanente medio
        # pagado seguiría figurando por su importe completo. Aquí se suma lo PENDIENTE, mes
        # a mes, que es lo que de verdad se le puede reclamar.
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
                fecha_str = f'{_MESES_ES[d.mes].capitalize()} {d.anio}'
            else:
                detalle = pe.especificacion or ''
                fecha_str = _dias_del_permiso(pe)
            permisos.append({
                'fecha_str': fecha_str,
                'ocurrencias': d.ocurrencias,
                'mes_str': f'{_MESES_ES[d.mes].capitalize()} {d.anio}',
                'horas': h,
                'tiempo': float(pe.tiempo or 0),
                'es_permanente': pe.es_permanente,
                'tipo': pe.get_tipo_display(),
                'detalle': detalle,
                'motivo': pe.motivo,
                'vencida': d.periodo.esta_vencido(hoy),
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

        # --- Saldado por sanción cumplida: ni pendiente ni pagado, pero tampoco invisible ---
        sanciones = ConsolidadoHorasService._extinguidas_por_sancion(empleado)
        total_extinguido_sancion = round(float(sum(x['horas'] for x in sanciones)), 2)

        # Histórico = lo que aún debe + lo que pagó + lo que extinguió cumpliendo sanciones.
        # Sin el tercer sumando, el acumulado de una persona ENCOGÍA al cumplir el castigo,
        # como si esas horas no hubieran existido nunca.
        total_acumulado = round(saldo + total_pagado + total_extinguido_sancion, 2)

        return {
            'solicitante': solicitante,
            'reemplazante': reemplazante,
            'otras': otras,
            'permisos': permisos,
            'pagos': pagos,
            'extinguidas_sancion': sanciones,
            'total_extinguido_sancion': total_extinguido_sancion,
            'total_solicitante': _suma(solicitante),
            'total_reemplazante': _suma(reemplazante),
            'total_otras': _suma(otras),
            'total_permisos': total_permisos,
            'total_acumulado': total_acumulado,
            'total_pagado': total_pagado,
            # total_horas = saldo pendiente (lo que aún debe)
            'total_horas': saldo,
        }
