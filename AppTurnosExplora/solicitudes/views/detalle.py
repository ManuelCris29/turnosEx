from django.shortcuts import get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from ..models import SolicitudCambio
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.utils.json_responses import json_ok, json_error
from core.utils.date_utils import DateUtils

# Create your views here.

class ObtenerDetalleSolicitudView(LoginRequiredMixin, View):
    """
    Endpoint API para obtener detalles completos de una solicitud.
    Incluye información específica según el tipo de solicitud.
    """
    def get(self, request, solicitud_id):
        try:
            # Obtener la solicitud con todas sus relaciones
            solicitud = get_object_or_404(
                SolicitudCambio.objects.select_related(
                    'explorador_solicitante',
                    'explorador_receptor',
                    'tipo_cambio',
                    'explorador_solicitante__supervisor',
                    'explorador_receptor__supervisor'
                ),
                id=solicitud_id
            )
            
            # Verificar permisos: solo el solicitante, receptor, supervisor o admin pueden ver
            usuario_empleado = None
            if hasattr(request.user, 'empleado'):
                usuario_empleado = request.user.empleado
            
            puede_ver = False
            if usuario_empleado:
                puede_ver = (
                    solicitud.explorador_solicitante == usuario_empleado or
                    solicitud.explorador_receptor == usuario_empleado or
                    solicitud.explorador_solicitante.supervisor == usuario_empleado or
                    solicitud.explorador_receptor.supervisor == usuario_empleado or
                    request.user.is_staff
                )
            
            if not puede_ver:
                return json_error('No tiene permisos para ver esta solicitud', status=403, code='forbidden')

            datos = ObtenerDetalleSolicitudView.construir_datos(solicitud)
            return json_ok(datos)

        except Exception as e:
            logger.error(f"Error en ObtenerDetalleSolicitudView: {e}", exc_info=True)
            return json_error('Error al obtener detalles de la solicitud', status=500, code='internal_error')

    @staticmethod
    def construir_datos(solicitud):
        """
        Construye el diccionario de detalle completo de una solicitud (común +
        específico por tipo). Reutilizable por la API de detalle y por las
        páginas de resultado de aprobación/rechazo por email.
        """
        # Información básica común
        datos = {
                'id': solicitud.id,
                'fecha_solicitud': DateUtils.format_datetime_display(solicitud.fecha_solicitud),
                'tipo': solicitud.tipo_cambio.nombre,
                'tipo_codigo': solicitud.tipo_cambio.codigo_estrategia or solicitud.tipo_cambio.nombre.upper(),
                'estado': solicitud.estado,
                'comentario': solicitud.comentario or 'Sin comentario',
                'fecha_resolucion': DateUtils.format_datetime_display(solicitud.fecha_resolucion),
                # Hora REAL de la cancelación. No es la de resolución: esa es la de la aprobación y
                # se conserva (de ella dependen la ventana de 30 min y la guardia LIFO).
                'fecha_cancelacion': DateUtils.format_datetime_display(solicitud.fecha_cancelacion),
                'solicitante': {
                    'id': solicitud.explorador_solicitante.id,
                    'nombre': f"{solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}",
                    'email': solicitud.explorador_solicitante.email,
                    'supervisor': f"{solicitud.explorador_solicitante.supervisor.nombre} {solicitud.explorador_solicitante.supervisor.apellido}" if solicitud.explorador_solicitante.supervisor else None,
                },
                'receptor': {
                    'id': solicitud.explorador_receptor.id,
                    'nombre': f"{solicitud.explorador_receptor.nombre} {solicitud.explorador_receptor.apellido}",
                    'email': solicitud.explorador_receptor.email,
                    'supervisor': f"{solicitud.explorador_receptor.supervisor.nombre} {solicitud.explorador_receptor.supervisor.apellido}" if solicitud.explorador_receptor.supervisor else None,
                },
                'aprobaciones': {
                    'receptor': {
                        'aprobado': solicitud.aprobado_receptor,
                        'fecha': DateUtils.format_datetime_display(solicitud.fecha_aprobacion_receptor),
                    },
                    'supervisor': {
                        'aprobado': solicitud.aprobado_supervisor,
                        'fecha': DateUtils.format_datetime_display(solicitud.fecha_aprobacion_supervisor),
                    },
                },
            'fechas': {},
            'informacion_adicional': {}
        }

        # Información específica según el tipo
        tipo_nombre = solicitud.tipo_cambio.nombre.upper()

        # CT PERMANENTE
        if tipo_nombre == 'CT PERMANENTE':
            ObtenerDetalleSolicitudView._detalle_ct_permanente(solicitud, datos)
        # DOBLADA
        elif tipo_nombre == 'DOBLADA':
            ObtenerDetalleSolicitudView._detalle_doblada(solicitud, datos)
        # D FDS (Doblada Fin de Semana)
        elif tipo_nombre == 'D FDS':
            ObtenerDetalleSolicitudView._detalle_d_fds(solicitud, datos)
        # DOBLADA PERMANENTE (acuerdo recurrente por días de la semana)
        elif tipo_nombre == 'DOBLADA PERMANENTE':
            ObtenerDetalleSolicitudView._detalle_doblada_permanente(solicitud, datos)
        # CAMBIO DESCANSO (fin de semana y sub-modalidades de temporada)
        elif tipo_nombre == 'CAMBIO DESCANSO':
            ObtenerDetalleSolicitudView._detalle_cambio_descanso(solicitud, datos)
        # CT (Cambio Turno normal) y otros tipos
        else:
            ObtenerDetalleSolicitudView._detalle_ct(solicitud, datos)
        return datos

    @staticmethod
    def _detalle_ct_permanente(solicitud, datos):
        try:
            detalle = solicitud.cambio_permanente
            if detalle:
                datos['fechas']['inicio'] = detalle.fecha_inicio.strftime('%d/%m/%Y')
                datos['fechas']['fin'] = detalle.fecha_fin.strftime('%d/%m/%Y') if detalle.fecha_fin else 'Sin fecha de fin'
                
                # Obtener días de semana seleccionados
                dias_seleccionados = detalle.dias.filter(tipo='dia_semana')
                dias_semana_nombres = []
                for dia in dias_seleccionados:
                    if dia.dia_semana is not None:
                        dias_semana_nombres.append(dia.get_dia_semana_display())
                
                if dias_semana_nombres:
                    datos['informacion_adicional']['dias_semana_seleccionados'] = ', '.join(dias_semana_nombres)
                else:
                    datos['informacion_adicional']['dias_semana_seleccionados'] = 'Todos los días hábiles'
                
                # Calcular fechas aplicables y excluidas
                from ..services.ct_permanente_helper import calcular_fechas_aplicables_y_excluidas_ct_permanente
                fechas_aplicables, fechas_excluidas = calcular_fechas_aplicables_y_excluidas_ct_permanente(
                    detalle,
                    solicitud.explorador_solicitante,
                    solicitud.explorador_receptor
                )
                
                datos['fechas']['aplicables'] = [fecha.strftime('%d/%m/%Y') for fecha in fechas_aplicables]
                datos['fechas']['total_dias'] = len(fechas_aplicables)
                
                # Agregar fechas excluidas con sus razones
                datos['fechas']['excluidas'] = [
                    {
                        'fecha': fecha_info['fecha'].strftime('%d/%m/%Y'),
                        'razon': fecha_info['razon']
                    }
                    for fecha_info in fechas_excluidas
                ]

                # Resumen informativo del rango (UX)
                try:
                    fi = detalle.fecha_inicio
                    ff = detalle.fecha_fin or DateUtils.parse_date(f"{fi.year}-12-31")
                    total_dias_rango = (ff - fi).days + 1
                    fines_semana = 0
                    cur = fi
                    while cur <= ff:
                        if cur.weekday() in (5, 6):
                            fines_semana += 1
                        cur = cur + timezone.timedelta(days=1)
                    datos['fechas']['resumen'] = {
                        'total_dias_rango': total_dias_rango,
                        'fines_de_semana_en_rango': fines_semana,
                        'prioridad': 'Mantenimiento > Festivo > Temporada > Descanso Solicitante > Descanso Receptor > Fines de semana',
                    }
                except Exception:
                    datos['fechas']['resumen'] = None
                
                datos['informacion_adicional']['nota'] = 'Se excluyen domingos, festivos, días de mantenimiento y días de descanso de los exploradores.'
        except Exception as e:
            logger.error(f"Error obteniendo detalles de CT PERMANENTE: {e}")
            datos['fechas']['error'] = 'No se pudieron obtener los detalles del cambio permanente'
    

    @staticmethod
    def _detalle_doblada(solicitud, datos):
        try:
            detalle = solicitud.doblada
            if detalle:
                _fc = solicitud.fecha_cambio_turno.strftime('%d/%m/%Y') if solicitud.fecha_cambio_turno else 'No especificada'
                _fp = detalle.fecha_pago.strftime('%d/%m/%Y') if detalle.fecha_pago else 'Pendiente de pago'
                _sol_nom = solicitud.explorador_solicitante.nombre
                _rec_nom = solicitud.explorador_receptor.nombre

                if getattr(detalle, 'es_intercambio', False):
                    # INTERCAMBIO DE DOBLADAS: swap de días doblados. NO es una cesión
                    # (no hay jornada cedida ni tipo de cesión) y NO genera ni altera deudas.
                    datos['informacion_adicional']['modalidad'] = 'Intercambio de dobladas'
                    datos['informacion_adicional']['intercambio_dia_a'] = (
                        f'{_fc} — tu doblada: la trabaja completa {_rec_nom} y tú descansas'
                    )
                    datos['informacion_adicional']['intercambio_dia_b'] = (
                        f'{_fp} — doblada de {_rec_nom}: la trabajas completa tú y él/ella descansa'
                    )
                    datos['informacion_adicional']['deuda_30min'] = (
                        'No genera ni altera deudas (es un intercambio de días doblados; '
                        'cada uno conserva las deudas que ya tenía).'
                    )
                else:
                    datos['fechas']['fecha_doblada'] = _fc
                    datos['fechas']['fecha_pago'] = _fp

                    # Tipo de cesión y jornada cedida
                    _tc = {
                        'cesion_completa': 'Completa (AM y PM)',
                        'cesion_parcial_am': 'Parcial AM',
                        'cesion_parcial_pm': 'Parcial PM',
                    }.get(detalle.tipo_cesion, detalle.tipo_cesion)
                    datos['informacion_adicional']['tipo_cesion'] = _tc
                    if detalle.jornada_cedida:
                        datos['informacion_adicional']['jornada_cedida'] = detalle.jornada_cedida.upper()

                    # Qué cubre el deudor en la fecha de pago (cuando el compañero tiene doblada)
                    _jcp = (getattr(detalle, 'jornada_cubre_en_pago', '') or '').upper()
                    if _jcp:
                        datos['informacion_adicional']['cubre_en_pago'] = {
                            'AM': f'En el pago cubres la jornada AM de {_rec_nom} (él/ella conserva PM)',
                            'PM': f'En el pago cubres la jornada PM de {_rec_nom} (él/ella conserva AM)',
                            'AMBAS': f'En el pago cubres la doblada completa de {_rec_nom} (él/ella descansa)',
                        }.get(_jcp, _jcp)

                    # Pago en sábado (AM / PM / AMBAS) y, si es AMBAS, el día de pago en semana
                    if getattr(detalle, 'jornada_pago_sabado', None):
                        jps = detalle.jornada_pago_sabado.upper()
                        datos['informacion_adicional']['pago_sabado'] = {
                            'AM': 'Cubres la jornada AM ese sábado (el compañero conserva PM)',
                            'PM': 'Cubres la jornada PM ese sábado (el compañero conserva AM)',
                            'AMBAS': 'Cubres el día completo (AM+PM); el compañero descansa y te devuelve media jornada en semana',
                        }.get(jps, jps)
                    if getattr(detalle, 'fecha_pago_semana', None):
                        datos['informacion_adicional']['fecha_pago_semana'] = detalle.fecha_pago_semana.strftime('%d/%m/%Y')

                    # Deuda de 30 min REAL (no el campo genérico del modelo):
                    # - aprobada: lo que efectivamente se generó (por persona y fecha).
                    # - pendiente: explicar la regla (se calcula al aprobar).
                    if solicitud.estado in ('aprobada', 'completada'):
                        from ..models import DeudaCorporativa as _DC
                        _dcs = list(_DC.objects.filter(solicitud_origen=solicitud)
                                    .exclude(estado='cancelada').select_related('explorador'))
                        if _dcs:
                            datos['informacion_adicional']['deuda_30min'] = '; '.join(
                                f'{x.explorador.nombre}: {x.minutos} min '
                                f'(dobla el {x.fecha_doblada.strftime("%d/%m/%Y")})'
                                for x in _dcs
                            )
                        else:
                            datos['informacion_adicional']['deuda_30min'] = (
                                'No se generó deuda de 30 min (nadie queda doblado en día hábil).'
                            )
                    else:
                        datos['informacion_adicional']['deuda_30min'] = (
                            'Se calcula al aprobar: 30 min para quien trabaje doblada '
                            '(AM+PM) en día hábil; sábados y festivos no generan.'
                        )
        except Exception as e:
            logger.error(f"Error obteniendo detalles de DOBLADA: {e}")
    

    @staticmethod
    def _detalle_d_fds(solicitud, datos):
        try:
            detalle = solicitud.doblada  # D FDS usa el mismo modelo que DOBLADA
            if detalle:
                _rec_nom = solicitud.explorador_receptor.nombre
                _fc = solicitud.fecha_cambio_turno.strftime('%d/%m/%Y') if solicitud.fecha_cambio_turno else 'No especificada'
                _fp = detalle.fecha_pago.strftime('%d/%m/%Y') if detalle.fecha_pago else 'Pendiente de pago'
                datos['informacion_adicional']['modalidad'] = 'Doblada de fin de semana (intercambio de días de finde)'
                datos['informacion_adicional']['intercambio_dia_a'] = (
                    f'{_fc} — tu día del finde: lo cubre {_rec_nom} doblándose y tú descansas'
                )
                datos['informacion_adicional']['intercambio_dia_b'] = (
                    f'{_fp} — día del finde de {_rec_nom}: lo cubres tú doblándote y él/ella descansa'
                )
                datos['informacion_adicional']['deuda_30min'] = (
                    'No genera deuda de 30 min (las dobladas de fin de semana no la generan).'
                )
        except Exception as e:
            logger.error(f"Error obteniendo detalles de D FDS: {e}")
    

    @staticmethod
    def _detalle_doblada_permanente(solicitud, datos):
        try:
            detalle = solicitud.doblada_permanente
            if detalle:
                datos['fechas']['inicio'] = detalle.fecha_inicio.strftime('%d/%m/%Y')
                datos['fechas']['fin'] = detalle.fecha_fin.strftime('%d/%m/%Y') if detalle.fecha_fin else 'Sin fecha de fin'
                datos['informacion_adicional']['dias_cesion'] = detalle.dias_cesion_legible() or '—'
                datos['informacion_adicional']['dias_devolucion'] = detalle.dias_devolucion_legible() or '—'
                datos['informacion_adicional']['nota'] = (
                    'El compañero (receptor) te cubre doblándose en tus días de cesión, y tú le devuelves '
                    'doblándote en los días de devolución, durante el rango indicado. '
                    'No aplica domingos, festivos ni días de mantenimiento. Solo se aplican pares completos '
                    '(si un lado tiene más fechas elegibles que el otro, el sobrante queda excluido por balance).'
                )

                from ..services.doblada_permanente_aplicacion_service import DobladaPermanenteAplicacionService
                resultado = DobladaPermanenteAplicacionService.calcular_fechas_aplicables_y_excluidas(
                    detalle, solicitud.explorador_solicitante, solicitud.explorador_receptor
                )
                datos['fechas']['cesion_aplicables'] = [f.strftime('%d/%m/%Y') for f in resultado['cesion']['aplicables']]
                datos['fechas']['cesion_excluidas'] = [
                    {'fecha': fi['fecha'].strftime('%d/%m/%Y'), 'razon': fi['razon']}
                    for fi in resultado['cesion']['excluidas']
                ]
                datos['fechas']['devolucion_aplicables'] = [f.strftime('%d/%m/%Y') for f in resultado['devolucion']['aplicables']]
                datos['fechas']['devolucion_excluidas'] = [
                    {'fecha': fi['fecha'].strftime('%d/%m/%Y'), 'razon': fi['razon']}
                    for fi in resultado['devolucion']['excluidas']
                ]
                datos['fechas']['total_dias'] = len(resultado['cesion']['aplicables']) + len(resultado['devolucion']['aplicables'])
        except Exception as e:
            logger.error(f"Error obteniendo detalles de DOBLADA PERMANENTE: {e}")
            datos['fechas']['error'] = 'No se pudieron obtener los detalles de la doblada permanente'


    @staticmethod
    def _detalle_cambio_descanso(solicitud, datos):
        try:
            detalle = solicitud.doblada
            if detalle:
                fc = solicitud.fecha_cambio_turno
                datos['fechas']['fecha_cesion'] = fc.strftime('%d/%m/%Y') if fc else 'No especificada'
                datos['fechas']['fecha_pago'] = detalle.fecha_pago.strftime('%d/%m/%Y') if detalle.fecha_pago else '—'
                es_finde = bool(fc) and fc.weekday() in (5, 6)
                if es_finde:
                    datos['informacion_adicional']['modalidad'] = 'Fin de semana (intercambio ida y vuelta)'
                else:
                    sub = getattr(detalle, 'submodalidad_semana', None) or 'intercambio_dia'
                    sub_legible = {
                        'intercambio_dia': 'Entre semana: intercambio de día',
                        'jornadas_partidas': 'Entre semana: jornadas partidas',
                        'cobertura_misma_semana': 'Entre semana: cobertura con pago en la misma semana',
                        'cambio_doblada': 'Entre semana: cambio de doblada',
                    }.get(sub, sub)
                    datos['informacion_adicional']['modalidad'] = sub_legible
                    if sub == 'jornadas_partidas' and detalle.jornada_cedida:
                        datos['informacion_adicional']['jornada_cedida_partida'] = detalle.jornada_cedida.upper()
                    if sub == 'cobertura_misma_semana':
                        _tc = {
                            'cesion_completa': 'Día completo (AM y PM)',
                            'cesion_parcial_am': 'Solo jornada AM',
                            'cesion_parcial_pm': 'Solo jornada PM',
                        }.get(detalle.tipo_cesion, detalle.tipo_cesion)
                        datos['informacion_adicional']['te_cubren'] = _tc
                        # Deuda de 30 min: real si ya está aprobada; regla si sigue pendiente.
                        if solicitud.estado in ('aprobada', 'completada'):
                            from ..models import DeudaCorporativa as _DC
                            _dcs = list(_DC.objects.filter(solicitud_origen=solicitud)
                                        .exclude(estado='cancelada').select_related('explorador'))
                            if _dcs:
                                datos['informacion_adicional']['deuda_30min'] = '; '.join(
                                    f'{x.explorador.nombre}: {x.minutos} min '
                                    f'(dobla el {x.fecha_doblada.strftime("%d/%m/%Y")})'
                                    for x in _dcs
                                )
                            else:
                                datos['informacion_adicional']['deuda_30min'] = (
                                    'No se generó deuda de 30 min.'
                                )
                        else:
                            datos['informacion_adicional']['deuda_30min'] = (
                                'Se calcula al aprobar: 30 min solo para quien doble '
                                'sobre su propia jornada.'
                            )
                    elif sub == 'cambio_doblada':
                        datos['informacion_adicional']['nota'] = (
                            'Sin deuda: ambos ya doblaban un día, solo se intercambia cuál.'
                        )
                    else:
                        datos['informacion_adicional']['nota'] = 'Intercambio directo, sin deuda.'
        except Exception as e:
            logger.error(f"Error obteniendo detalles de CAMBIO DESCANSO: {e}")
            datos['fechas']['error'] = 'No se pudieron obtener los detalles del cambio de descanso'


    @staticmethod
    def _detalle_ct(solicitud, datos):
        if solicitud.fecha_cambio_turno:
            datos['fechas']['fecha_cambio'] = solicitud.fecha_cambio_turno.strftime('%d/%m/%Y')
            
            # Jornada de cada uno en la fecha del cambio. Si la solicitud ya fue aplicada,
            # turno_origen/turno_destino reflejan el turno YA intercambiado (jornada final).
            # Si sigue pendiente, esos turnos aún no existen: se calcula la jornada ACTUAL
            # (antes del intercambio) para que el revisor sepa qué se va a intercambiar.
            if solicitud.turno_origen and solicitud.turno_origen.jornada:
                datos['informacion_adicional']['jornada_solicitante'] = solicitud.turno_origen.jornada.nombre
            else:
                from turnos.services.jornada_service import JornadaService
                j_sol = JornadaService.get_jornada_explorador_fecha(
                    solicitud.explorador_solicitante.id, solicitud.fecha_cambio_turno
                )
                datos['informacion_adicional']['jornada_solicitante'] = j_sol.nombre if j_sol else None

            if solicitud.turno_destino and solicitud.turno_destino.jornada:
                datos['informacion_adicional']['jornada_receptor'] = solicitud.turno_destino.jornada.nombre
            else:
                from turnos.services.jornada_service import JornadaService
                j_rec = JornadaService.get_jornada_explorador_fecha(
                    solicitud.explorador_receptor.id, solicitud.fecha_cambio_turno
                )
                datos['informacion_adicional']['jornada_receptor'] = j_rec.nombre if j_rec else None

            if solicitud.estado == 'pendiente':
                datos['informacion_adicional']['nota_jornadas'] = (
                    'Jornadas actuales (antes del intercambio): al aprobarse, el solicitante '
                    'pasa a la jornada del receptor y viceversa.'
                )
            
            # Analizar fecha para mostrar información detallada
            from ..services.fechas_helper import obtener_informacion_fecha_para_detalle
            info_fecha = obtener_informacion_fecha_para_detalle(
                solicitud.fecha_cambio_turno,
                solicitante=solicitud.explorador_solicitante,
                receptor=solicitud.explorador_receptor,
                tipo_solicitud='CT'
            )
            datos['fechas']['analisis'] = info_fecha
            
            # Si hay razones de exclusión, agregarlas
            if info_fecha['razones_exclusion']:
                datos['fechas']['excluidas'] = [{
                    'fecha': info_fecha['fecha'],
                    'razon': ', '.join(info_fecha['razones_exclusion'])
                }]
            else:
                # Si es válida, agregarla a aplicables
                datos['fechas']['aplicables'] = [info_fecha['fecha']]
            
            datos['informacion_adicional']['nota'] = 'Se excluyen días de mantenimiento, domingos y dobladas activas. Los festivos se permiten si ambos empleados tienen jornada.'
    
