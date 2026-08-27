import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from core.services import get_turno_service
from core.utils.date_utils import DateUtils
from empleados.models import Empleado

from ..models import SolicitudCambio, TipoSolicitudCambio
from ..services.solicitud_factory import SolicitudFactory

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.constants import JornadaDisplay
from core.utils.json_responses import json_error, json_error_inesperado, json_ok

# Create your views here.

class ObtenerTurnoExploradorView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        explorador_id = request.GET.get('explorador_id')
        jornada_base = request.GET.get('jornada_base', 'false').lower() == 'true'
        
        if not fecha or not explorador_id:
            return json_error('Faltan parámetros requeridos', status=400, code='missing_params')

        # Un explorador que no existe es un error del CLIENTE, no una avería: 404 con
        # un mensaje claro, y separado del 500 de más abajo.
        #
        # Antes no se comprobaba, y el id viaja en la URL. `Empleado.objects.get()`
        # lanzaba DoesNotExist dentro de la estrategia, que la capturaba y devolvía
        # `{}` — así que la respuesta era 200 con `turno: {}, tiene_turno: true`:
        # "sí tiene turno", con un objeto vacío. Comprobado ejecutándolo.
        if not Empleado.objects.filter(id=explorador_id).exists():
            return json_error('El explorador indicado no existe.',
                              status=404, code='explorador_no_encontrado')

        try:
            # `jornada_base=true` es una rama COMPLETA y aparte: responde con su
            # propio `return` y no ejecuta nada del resto del método. La usa
            # `solicitar_ct_permanente.js`, que necesita la jornada PREDETERMINADA
            # y no el estado real del día.
            if jornada_base:
                return self._responder_jornada_base(explorador_id, fecha)

            # Obtener el tipo de solicitud desde la URL o parámetros
            tipo_solicitud_id = request.GET.get('tipo_solicitud_id')
            tipo_solicitud = None
            
            if tipo_solicitud_id:
                try:
                    tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)
                except TipoSolicitudCambio.DoesNotExist:
                    # Sigue con tipo_solicitud=None, que más abajo toma OTRA rama de cálculo.
                    # Es decir: un id inexistente no da error, da un resultado distinto del
                    # que el formulario pidió. Se registra para que se pueda diagnosticar.
                    logger.warning('tipo_solicitud_id=%s no existe; se responde por la rama '
                                   'genérica, no por la del tipo pedido', tipo_solicitud_id)
            
            # Obtener el turno del explorador usando el Factory
            if tipo_solicitud:
                turno_dict = SolicitudFactory.get_turno_explorador(tipo_solicitud, explorador_id, fecha)
            else:
                # Fallback al servicio original si no hay tipo
                turno_service = get_turno_service()
                turno_dict = turno_service.get_turno_explorador(explorador_id, fecha)
            
            # CORRECCIÓN: Detectar si el explorador tiene doblada (AM + PM) en esta fecha
            # IMPORTANTE: Solo es doblada si hay TURNOS ASIGNADOS (AM+PM), no solo jornada predeterminada
            from turnos.models import Turno
            
            fecha_obj = DateUtils.parse_date(fecha)
            turnos_en_fecha = Turno.objects.filter(
                explorador_id=explorador_id,
                fecha=fecha_obj
            ).select_related('jornada')
            
            # Normalizar a mayúsculas: en BD a veces viene distinto y fallaba 'AM' in turnos_list
            turnos_list = [t.jornada.nombre.upper() for t in turnos_en_fecha if t.jornada]
            # Doblada real: al menos dos turnos en la fecha y una jornada AM y otra PM
            es_doblada = len(turnos_en_fecha) >= 2 and 'AM' in turnos_list and 'PM' in turnos_list

            # Misma señal que TurnoService.get_turno_explorador (tarjeta de horario / jornada DOBLADA)
            if turno_dict:
                svc_doblada = (
                    turno_dict.get('jornada') == JornadaDisplay.DOBLADA
                    or turno_dict.get('es_doblada')
                    or turno_dict.get('es_doblada_sabado')
                )
                if svc_doblada:
                    es_doblada = True
                    if 'AM' not in turnos_list or 'PM' not in turnos_list:
                        turnos_list = ['AM', 'PM']
            
            # Verificar si es fin de semana y corresponde trabajar (día completo). Usa el
            # grupo EFECTIVO: override manual del supervisor si existe; si no, alternancia.
            es_fin_semana_doblada_predeterminada = False
            if fecha_obj.weekday() in (5, 6):
                from turnos.services.asignacion_especial_service import AsignacionEspecialService
                grupo_finde = AsignacionEspecialService.grupo_trabaja(fecha_obj)
                if grupo_finde:
                    from turnos.services.jornada_service import JornadaService
                    jornada_predeterminada = JornadaService.get_jornada_explorador_fecha(explorador_id, fecha)
                    if jornada_predeterminada and jornada_predeterminada.nombre.upper() == grupo_finde.upper():
                        # En fin de semana, quien trabaja lo hace el día completo (DOBLADA)
                        es_fin_semana_doblada_predeterminada = True
            
            # Detectar caso especial: está descansando por una doblada aprobada (no hay turnos en BD)
            # Descanso sin turnos en BD, extraido en la Fase 3. Devuelve el
            # `descanso_info` o None; las tres ramas que tenia dentro fijaban
            # EXACTAMENTE lo mismo al detectar descanso (anular el turno y la
            # lista de jornadas), asi que eso se deriva aqui en vez de
            # devolver cuatro valores.
            descanso_info = self._detectar_descanso(explorador_id, fecha, fecha_obj,
                                                    turnos_en_fecha)
            esta_descansando = descanso_info is not None
            if esta_descansando:
                turno_dict = None
                turnos_list = []

            # Regla adicional para festivos de lunes a viernes:
            # - Solo mostrar DOBLADA (AM+PM) si en BD tiene realmente ambos turnos.
            #   Si ya hizo cesión parcial y solo tiene una jornada, mostrar esa jornada, no doblada.
            # - Si NO es el grupo que dobla y la solicitud es de DOBLADA → tratar como día de descanso.
            if not es_doblada and not es_fin_semana_doblada_predeterminada:
                try:
                    from solicitudes.services.solicitud_validator import SolicitudValidator

                    es_festivo_semana = SolicitudValidator.es_festivo_semana(fecha_obj)
                    if es_festivo_semana:
                        # Alternancia publicada del festivo (None si el año no está sembrado).
                        from turnos.services.asignacion_especial_service import AsignacionEspecialService as _AES
                        grupo_que_dobla = _AES.grupo_trabaja(fecha_obj)
                        jornada_turno = (turno_dict.get('jornada') or '').upper() if turno_dict else None
                        if not jornada_turno and not turnos_list:
                            from turnos.services.jornada_service import JornadaService
                            pred = JornadaService.get_jornada_explorador_fecha(explorador_id, fecha)
                            jornada_turno = pred.nombre.upper() if pred else None
                        tiene_doblada_real_bd = set(turnos_list) == {'AM', 'PM'}
                        # Festivo sin modificaciones (0 turnos): mostrar DOBLADA por regla si el grupo trabaja
                        if not turnos_list and jornada_turno and grupo_que_dobla and jornada_turno == grupo_que_dobla:
                            es_doblada = True
                            turnos_list = ['AM', 'PM']
                        elif tiene_doblada_real_bd and turno_dict and jornada_turno and grupo_que_dobla and jornada_turno == grupo_que_dobla:
                            es_doblada = True
                            turnos_list = ['AM', 'PM']
                        elif not tiene_doblada_real_bd and jornada_turno and grupo_que_dobla and jornada_turno != grupo_que_dobla:
                            # Festivo donde el solicitante NO es del grupo que dobla → DESCANSA por
                            # rotación. Aplica a CUALQUIER tipo de solicitud (igual que "Mis Turnos");
                            # antes solo se contemplaba para DOBLADA y el Cambio de Turno mostraba la
                            # jornada base por error.
                            turno_dict = None
                            turnos_list = []
                            esta_descansando = True
                            if not descanso_info:
                                descanso_info = {'tipo': 'descanso_semana', 'motivo': 'festivo'}
                except Exception:
                    logger.warning("Error resolviendo estado de doblada/festivo del día", exc_info=True)

            # Coherencia de la jornada que se muestra, extraida en la Fase 3.
            # Modifica `turno_dict` in situ, que es lo que ya hacia.
            self._normalizar_jornada_mostrada(
                turno_dict, es_doblada, es_fin_semana_doblada_predeterminada,
                explorador_id, fecha)

            response_data = {
                'turno': turno_dict,
                'tiene_turno': turno_dict is not None,
                'es_doblada': es_doblada,
                'jornadas': turnos_list if turnos_list else ([turno_dict['jornada']] if turno_dict and 'jornada' in turno_dict and turno_dict['jornada'] != JornadaDisplay.DOBLADA else []),
                'esta_descansando': esta_descansando,
                'descanso_info': descanso_info,
            }
            
            # Datos propios del sábado, extraídos en la Fase 3. Solo LEEN, así que
            # devuelven un diccionario que se fusiona en vez de escribir dentro.
            if fecha_obj.weekday() == 5:
                response_data.update(self._extras_sabado(explorador_id, fecha_obj))

            return json_ok(response_data)
        except Exception:
            logger.exception('Error en ObtenerTurnoExploradorView')
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')


    def _detectar_descanso(self, explorador_id, fecha, fecha_obj, turnos_en_fecha):
        """
        Por que descansa el explorador ese dia, cuando NO tiene turnos en la base.

        Devuelve el `descanso_info` que consume el formulario, o None si no
        descansa. Extraido de `get` en la Fase 3; la logica no cambia.

        Las tres capas van en orden y la primera que acierta manda:

          1. DOBLADA aprobada: cedio su jornada, o le pagan ese dia. Es la unica
             que aporta datos que la fuente de verdad no da (nombre del companero,
             fechas de cesion y pago), y por eso sigue aqui.
          2. Cualquier otro compromiso por solicitud aprobada (D FDS, CAMBIO
             DESCANSO, DOBLADA PERMANENTE), via `dia_comprometido_por_solicitud`.
          3. Descanso de ENTRE SEMANA por temporada o mantenimiento.

        Solo se llama cuando no hay turnos reales: con turno en la base, el turno
        manda y ninguna de estas capas aplica.
        """
        descanso_info = None
        # Detectar descanso por DOBLADA para cualquier tipo de solicitud (CT, CT permanente, DOBLADA, etc.)
        # Solo aplicamos esta lógica cuando NO hay turnos reales en BD para esa fecha.
        if not turnos_en_fecha:
            from solicitudes.models import SolicitudCambio
            
            # Caso 1: Es SOLICITANTE y cede su jornada en esta fecha (cesión)
            doblada_como_solicitante = (
                SolicitudCambio.objects
                .filter(
                    explorador_solicitante_id=explorador_id,
                    tipo_cambio__nombre='DOBLADA',
                    fecha_cambio_turno=fecha_obj,
                    estado='aprobada'
                )
                .select_related('doblada', 'explorador_receptor')
                .first()
            )
            
            # Caso 2: Es RECEPTOR y descansa en fecha de pago de una doblada
            doblada_como_receptor = (
                SolicitudCambio.objects
                .filter(
                    explorador_receptor_id=explorador_id,
                    tipo_cambio__nombre='DOBLADA',
                    estado='aprobada',
                    doblada__fecha_pago=fecha_obj
                )
                .select_related('doblada', 'explorador_solicitante')
                .first()
            )
            
            if doblada_como_solicitante or doblada_como_receptor:
                
                if doblada_como_solicitante:
                    sol = doblada_como_solicitante
                    rol_descanso = 'cedio'
                    companero = sol.explorador_receptor
                else:
                    sol = doblada_como_receptor
                    rol_descanso = 'pago'
                    companero = sol.explorador_solicitante
                
                detalle = getattr(sol, 'doblada', None)
                fecha_cesion_str = (
                    sol.fecha_cambio_turno.strftime('%d/%m/%Y')
                    if sol.fecha_cambio_turno else None
                )
                fecha_pago_str = (
                    detalle.fecha_pago.strftime('%d/%m/%Y')
                    if detalle and detalle.fecha_pago else None
                )
                
                descanso_info = {
                    'tipo': rol_descanso,  # 'cedio' o 'pago'
                    'companero_nombre': f"{companero.nombre} {getattr(companero, 'apellido', '')}".strip(),
                    'companero_id': companero.id,
                    'solicitud_id': sol.id,
                    'fecha_cesion': fecha_cesion_str,
                    'fecha_pago': fecha_pago_str,
                }
                
                # Si está descansando por doblada, no queremos mostrar jornada base

            # Otros descansos por solicitud APROBADA: D FDS, CAMBIO DESCANSO y
            # DOBLADA PERMANENTE (el bloque de arriba solo cubre DOBLADA). Usa la fuente
            # de verdad única para que el display coincida con "Mis Turnos".
            if descanso_info is None:
                from empleados.models import Empleado as _Emp
                from turnos.services.turno_service import TurnoService as _TSv
                _emp_obj = _Emp.objects.filter(id=explorador_id).first()
                _comp = _TSv.dia_comprometido_por_solicitud(_emp_obj, fecha_obj) if _emp_obj else None
                if _comp:
                    _c = _comp.get('companero') or {}
                    descanso_info = {
                        'tipo': 'cedio',
                        'companero_nombre': _c.get('nombre'),
                        'companero_id': _c.get('id'),
                        'motivo': _comp.get('motivo'),
                    }

            # Descanso de ENTRE SEMANA (manual de temporada/festivo o lunes de mantenimiento).
            # Debe verse igual que en Mis Turnos: es un descanso, no la jornada predeterminada.
            if descanso_info is None and fecha_obj.weekday() < 5:
                from turnos.models import DiaEspecial as _DE
                from turnos.services.descanso_semana_service import DescansoSemanaService
                from turnos.services.jornada_service import JornadaService as _JS
                _pred = _JS.get_jornada_explorador_fecha(explorador_id, fecha)
                _jb = _pred.nombre.upper() if _pred else None
                _motivo_ds = None
                if DescansoSemanaService.es_descanso_semana_manual(_jb, fecha_obj):
                    _motivo_ds = 'temporada'
                elif _DE.es_mantenimiento_efectivo(fecha_obj):
                    _motivo_ds = 'mantenimiento'
                if _motivo_ds:
                    descanso_info = {'tipo': 'descanso_semana', 'motivo': _motivo_ds}
        return descanso_info

    def _normalizar_jornada_mostrada(self, turno_dict, es_doblada,
                                     es_fin_semana_doblada_predeterminada,
                                     explorador_id, fecha):
        """
        Deja la jornada del turno coherente con lo que el día realmente es.

        Modifica `turno_dict` in situ y no devuelve nada, que es exactamente lo que
        hacía dentro de `get`. Son dos ajustes en sentidos opuestos:

          * Si el día quedó como DOBLADA —por ser festivo del grupo que dobla, o
            por tener los dos turnos reales— la jornada mostrada debe decir
            'DOBLADA' y no la base, igual que hacen `estado_dia` y Mis Turnos.

          * Al revés: si el servicio dijo 'DOBLADA' pero NO es doblada real ni un
            fin de semana con doblada predeterminada, entonces era la jornada
            predeterminada de un día de semana y se sustituye por la real, ajustando
            también el horario.

        La condición de fin de semana no es un detalle: ahí la jornada
        predeterminada ES doblada, así que convertirla a simple mostraría media
        jornada donde se trabaja el día entero.
        """
        if es_doblada and turno_dict and turno_dict.get('jornada') != JornadaDisplay.DOBLADA:
            turno_dict['jornada'] = 'DOBLADA'

        if (turno_dict and turno_dict.get('jornada') == JornadaDisplay.DOBLADA
                and not es_doblada and not es_fin_semana_doblada_predeterminada):
            from turnos.services.jornada_service import JornadaService
            jornada_real = JornadaService.get_jornada_explorador_fecha(explorador_id, fecha)
            if jornada_real:
                turno_dict['jornada'] = jornada_real.nombre
                if jornada_real.hora_inicio and jornada_real.hora_fin:
                    turno_dict['hora_inicio'] = jornada_real.hora_inicio.strftime('%H:%M')
                    turno_dict['hora_fin'] = jornada_real.hora_fin.strftime('%H:%M')

    def _extras_sabado(self, explorador_id, fecha_obj):
        """
        Las dos claves que el formulario de doblada solo recibe en sábado.

        `jornada_trabaja_sabado` es el grupo EFECTIVO que trabaja ese día (el
        override manual del supervisor si lo hay; si no, la alternancia).

        `corresponde_trabajar_sabado` decide si el formulario muestra el selector
        de media jornada: si al explorador le toca por su grupo, la doblada se
        devuelve en su jornada habitual y no hay nada que elegir; si su grupo
        descansa, viene especialmente y sí elige.

        Se calcula sobre la jornada BASE (`AsignarJornadaExplorador`) y NO sobre el
        turno del día, y eso es lo importante de este método: otra doblada pudo
        alterar el turno hasta coincidir con el grupo que trabaja, y entonces daría
        un falso positivo — el selector desaparecería para quien sí debía elegir.
        """
        from turnos.models import AsignarJornadaExplorador
        from turnos.services.asignacion_especial_service import AsignacionEspecialService

        grupo_trabaja = AsignacionEspecialService.grupo_trabaja(fecha_obj)
        asignacion = (AsignarJornadaExplorador.objects
                      .filter(explorador_id=explorador_id, fecha_inicio__lte=fecha_obj)
                      .select_related('jornada').order_by('-fecha_inicio').first())
        jornada_base = asignacion.jornada.nombre.upper() if asignacion else None

        return {
            'jornada_trabaja_sabado': grupo_trabaja,
            'corresponde_trabajar_sabado': bool(
                grupo_trabaja and jornada_base and jornada_base == str(grupo_trabaja).upper()
            ),
        }

    def _responder_jornada_base(self, explorador_id, fecha):
        """
        Jornada PREDETERMINADA del explorador, sin mirar los turnos del día.

        Extraído de `get` en la Fase 3; la lógica no cambia.

        Es deliberado que ignore los turnos reales: `solicitar_ct_permanente.js`
        pide esto justo cuando necesita saber a qué grupo pertenece alguien, no qué
        le pasa ese día concreto. Si algún refactor la unificara con la rama
        general, CT permanente empezaría a ver el estado del día —con sus dobladas
        y descansos— en vez de la base.
        """
        from turnos.models import AsignarJornadaExplorador

        fecha_obj = DateUtils.parse_date(fecha)
        explorador = Empleado.objects.get(id=explorador_id)

        asignacion_jornada = AsignarJornadaExplorador.objects.select_related('jornada').filter(
            explorador=explorador,
            fecha_inicio__lte=fecha_obj
        ).order_by('-fecha_inicio').first()

        if not (asignacion_jornada and asignacion_jornada.jornada):
            return json_ok({'turno': None, 'tiene_turno': False})

        jornada = asignacion_jornada.jornada
        from turnos.models import CompetenciaEmpleado
        competencias = CompetenciaEmpleado.objects.filter(empleado=explorador).select_related('sala')
        salas_competencia = [
            {'id': c.sala.id, 'nombre': c.sala.nombre} for c in competencias
        ]

        turno_dict = {
            'id': None,
            'jornada': jornada.nombre,
            'sala': None,
            'sala_id': None,
            'hora_inicio': jornada.hora_inicio.strftime('%H:%M') if jornada.hora_inicio else None,
            'hora_fin': jornada.hora_fin.strftime('%H:%M') if jornada.hora_fin else None,
            'es_turno_virtual': True,
            'tipo_sala': 'competencia',
            'salas_competencia': salas_competencia,
            'es_jornada_base': True
        }
        return json_ok({'turno': turno_dict, 'tiene_turno': True})


class VerificarCoincidenciaJornadasView(LoginRequiredMixin, View):
    """
    Endpoint para validar en tiempo real si hay coincidencia de jornadas en fecha de pago.
    Útil para DOBLADA para verificar el caso crítico antes de enviar la solicitud.
    
    Parámetros:
    - deudor_id: ID del explorador deudor (solicitante)
    - acreedor_id: ID del explorador acreedor (receptor)
    - fecha_pago: Fecha de pago en formato YYYY-MM-DD
    """
    def get(self, request):
        deudor_id = request.GET.get('deudor_id')
        acreedor_id = request.GET.get('acreedor_id')
        fecha_pago = request.GET.get('fecha_pago')
        
        if not all([deudor_id, acreedor_id, fecha_pago]):
            return json_error('Faltan parámetros requeridos (deudor_id, acreedor_id, fecha_pago)', 
                            status=400, code='missing_params')
        
        try:
            from empleados.models import Empleado
            from solicitudes.services.solicitud_validator import SolicitudValidator
            
            deudor = Empleado.objects.get(id=deudor_id)
            acreedor = Empleado.objects.get(id=acreedor_id)
            
            # Validar coincidencia de jornadas
            resultado = SolicitudValidator.validar_coincidencia_jornadas_pago(
                deudor,
                acreedor,
                fecha_pago
            )
            
            # Construir respuesta
            respuesta = {
                'coinciden': resultado['coinciden'],
                'jornada_comun': resultado.get('jornada_comun'),
                'requiere_cambio_turno': resultado.get('requiere_cambio_turno', False)
            }
            
            # Agregar mensaje explicativo
            if resultado['requiere_cambio_turno']:
                respuesta['mensaje'] = (
                    f"No se puede pagar trabajando dos veces la misma jornada ({resultado.get('jornada_comun', '')}). "
                    "Debes primero realizar un cambio de turno sencillo para tener jornada contraria en la fecha de pago."
                )
                respuesta['url_redireccion'] = f'/solicitudes/cambio-turno/solicitar/?tipo_id=1&fecha_solicitud={fecha_pago}'
            elif resultado['coinciden']:
                respuesta['mensaje'] = f"Ambos exploradores tienen la misma jornada ({resultado.get('jornada_comun', '')}) en la fecha de pago."
            else:
                respuesta['mensaje'] = 'Las jornadas son contrarias. Puedes proceder con la doblada.'
            
            return json_ok(respuesta)
            
        except Empleado.DoesNotExist:
            return json_error('Empleado no encontrado', status=404, code='empleado_not_found')
        except Exception:
            logger.exception('Error en VerificarCoincidenciaJornadasView')
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')


class ObtenerJornadasRangoView(LoginRequiredMixin, View):
    """
    Endpoint para obtener jornadas día a día de un explorador en un rango de fechas.
    Útil para CT PERMANENTE para mostrar desglose de jornadas en el rango.
    """
    def get(self, request):
        explorador_id = request.GET.get('explorador_id')
        fecha_inicio = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')
        dias_seleccionados_json = request.GET.get('dias_seleccionados', '{}')
        
        if not all([explorador_id, fecha_inicio, fecha_fin]):
            return json_error('Faltan parámetros requeridos (explorador_id, fecha_inicio, fecha_fin)', 
                            status=400, code='missing_params')
        
        try:
            import json
            from datetime import timedelta

            from turnos.services.jornada_service import JornadaService
            
            fecha_inicio_obj = DateUtils.parse_date(fecha_inicio)
            fecha_fin_obj = DateUtils.parse_date(fecha_fin)
            
            # Parsear días seleccionados
            try:
                dias_seleccionados = json.loads(dias_seleccionados_json) if dias_seleccionados_json else {}
            except json.JSONDecodeError:
                dias_seleccionados = {}
            
            # Generar fechas válidas del rango (similar a CTPermanenteStrategy)
            fechas_validas = []
            dias_semana_list = dias_seleccionados.get('dias_semana', [])
            
            if dias_semana_list:
                # Solo días de semana seleccionados
                fecha_actual = fecha_inicio_obj
                while fecha_actual <= fecha_fin_obj:
                    # weekday(): 0=lunes, 6=domingo
                    dia_semana = fecha_actual.weekday()
                    # Convertir a formato del backend (0=lunes, 4=viernes)
                    if dia_semana < 5 and dia_semana in dias_semana_list:  # Solo lunes-viernes
                        fechas_validas.append(fecha_actual)
                    fecha_actual += timedelta(days=1)
            else:
                # Todos los días hábiles del rango
                fecha_actual = fecha_inicio_obj
                while fecha_actual <= fecha_fin_obj:
                    if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                        fechas_validas.append(fecha_actual)
                    fecha_actual += timedelta(days=1)
            
            # Obtener jornada para cada fecha
            dias_semana_es = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            
            from empleados.models import Empleado as _EmpRango
            from solicitudes.services.ct_permanente_helper import (
                _dia_libre_por_solicitud,
                _es_festivo,
                _es_mantenimiento,
                _es_temporada,
                _estado_ct,
                precargar_ct_permanente,
            )
            from turnos.models import Jornada, Turno
            _emp_rango = _EmpRango.objects.filter(id=explorador_id).first()

            # Turnos del rango de una sola vez (antes: una consulta por fecha).
            _turnos_por_fecha = {}
            for _t in (Turno.objects
                       .filter(explorador_id=explorador_id,
                               fecha__range=(fecha_inicio_obj, fecha_fin_obj))
                       .select_related('jornada')):
                _turnos_por_fecha.setdefault(_t.fecha, []).append(_t)

            # Catálogo de jornadas por nombre (antes: una consulta por día trabajado).
            _jornadas_cat = {j.nombre.upper(): j for j in Jornada.objects.all()}

            jornadas_por_dia = []
            # Precarga en lote del estado del explorador: este bucle resolvía cada fecha por
            # separado (día comprometido, festivo, mantenimiento, temporada y `estado_dia`),
            # que era ~1.400 consultas para un rango de 90 días.
            with precargar_ct_permanente([_emp_rango] if _emp_rango else [],
                                         fecha_inicio_obj, fecha_fin_obj):
                for fecha_obj in fechas_validas:
                    dia_semana_num = fecha_obj.weekday()
                    # Reflejar el estado REAL del día, coherente con lo que se aplicará en el CT
                    # permanente. Prioridad (igual que la exclusión real):
                    #   Doblada (turno real) > Comprometido por solicitud > Mantenimiento >
                    #   Festivo > Temporada > jornada AM/PM (real del día).
                    turnos_dia = _turnos_por_fecha.get(fecha_obj, [])
                    if len(turnos_dia) >= 2:
                        jornada_nombre, jornada_id = 'DOBLADA', None
                    elif _emp_rango and _dia_libre_por_solicitud(_emp_rango, fecha_obj):
                        # Día ya cedido/comprometido en otra solicitud aprobada (L2): no aplica.
                        jornada_nombre, jornada_id = 'COMPROMETIDO', None
                    elif _es_mantenimiento(fecha_obj):
                        jornada_nombre, jornada_id = 'MANTENIMIENTO', None
                    elif _es_festivo(fecha_obj):
                        jornada_nombre, jornada_id = 'FESTIVO', None
                    elif _es_temporada(fecha_obj):
                        jornada_nombre, jornada_id = 'TEMPORADA', None
                    elif len(turnos_dia) == 1 and turnos_dia[0].jornada:
                        # Turno real único: la jornada REAL de ese día (no la predeterminada)
                        jornada_nombre = turnos_dia[0].jornada.nombre
                        jornada_id = turnos_dia[0].jornada.id
                    elif _emp_rango:
                        # FUENTE DE VERDAD (estado_dia): igual que Mis Turnos. Cubre descanso de
                        # temporada por DescansoSemanaManual, día completo (grupo contrario
                        # descansa), festivos por rotación/override y demás capas.
                        _est = _estado_ct(_emp_rango, fecha_obj)
                        if not _est.get('trabaja'):
                            _map_fuente = {'temporada': 'TEMPORADA', 'mantenimiento': 'MANTENIMIENTO',
                                           'festivo': 'FESTIVO', 'solicitud': 'COMPROMETIDO'}
                            jornada_nombre = _map_fuente.get(_est.get('fuente'), 'DESCANSO')
                            jornada_id = None
                        elif _est.get('jornada') == JornadaDisplay.DOBLADA:
                            jornada_nombre, jornada_id = 'DOBLADA', None
                        else:
                            _nom = _est.get('jornada')
                            _j_obj = _jornadas_cat.get(_nom.upper()) if _nom else None
                            jornada_nombre = _j_obj.nombre if _j_obj else _nom
                            jornada_id = _j_obj.id if _j_obj else None
                    else:
                        jornada = JornadaService.get_jornada_explorador_fecha(explorador_id, fecha_obj)
                        jornada_nombre = jornada.nombre if jornada else None
                        jornada_id = jornada.id if jornada else None
                    jornadas_por_dia.append({
                        'fecha': fecha_obj.strftime('%Y-%m-%d'),
                        'fecha_formateada': fecha_obj.strftime('%d/%m/%Y'),
                        'dia_semana': dias_semana_es[dia_semana_num] if dia_semana_num < len(dias_semana_es) else fecha_obj.strftime('%A'),
                        'jornada': jornada_nombre,
                        'jornada_id': jornada_id
                    })

            # Etiquetas que NO son una jornada aplicable (el día queda excluido del cambio)
            _NO_APLICAN = {'DOBLADA', 'MANTENIMIENTO', 'FESTIVO', 'TEMPORADA', 'COMPROMETIDO', 'DESCANSO'}
            # Calcular resumen
            resumen = {
                'total_dias': len(jornadas_por_dia),
                'dias_am': len([j for j in jornadas_por_dia if j['jornada'] == 'AM']),
                'dias_pm': len([j for j in jornadas_por_dia if j['jornada'] == 'PM']),
                'dias_doblada': len([j for j in jornadas_por_dia if j['jornada'] == JornadaDisplay.DOBLADA]),
                'dias_mantenimiento': len([j for j in jornadas_por_dia if j['jornada'] == 'MANTENIMIENTO']),
                'dias_festivo': len([j for j in jornadas_por_dia if j['jornada'] == 'FESTIVO']),
                'dias_temporada': len([j for j in jornadas_por_dia if j['jornada'] == 'TEMPORADA']),
                'dias_no_aplican': len([j for j in jornadas_por_dia if j['jornada'] in _NO_APLICAN]),
                'dias_sin_jornada': len([j for j in jornadas_por_dia if j['jornada'] is None])
            }
            
            return json_ok({
                'jornadas': jornadas_por_dia,
                'resumen': resumen
            })
            
        except Exception as e:
            return json_error_inesperado(
                request, e, 'No pudimos calcular las jornadas de ese rango. Inténtalo de nuevo.')


class ObtenerCambioAprobadoView(LoginRequiredMixin, View):
    """
    FASE 2.5: Endpoint para verificar si el usuario ya tiene un cambio aprobado para una fecha.
    Devuelve información sobre la solicitud que creó el turno si existe.
    """
    def get(self, request):
        fecha = request.GET.get('fecha')
        
        if not fecha:
            return json_error('Falta el parámetro fecha', status=400, code='missing_fecha')
        
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=400, code='no_empleado')
        
        try:
            from django.db.models import Q

            from turnos.models import Turno
            
            fecha_obj = DateUtils.parse_date(fecha)
            empleado = request.user.empleado
            
            # Buscar si existe un Turno para este empleado y fecha
            turno = Turno.objects.filter(
                explorador=empleado,
                fecha=fecha_obj
            ).first()
            
            if not turno:
                return json_ok({
                    'tiene_cambio_aprobado': False,
                    'mensaje': None,
                    'informacion_cambio': None
                })
            
            # Si existe turno, buscar la solicitud que lo creó
            solicitud = SolicitudCambio.objects.filter(
                Q(turno_origen=turno) | Q(turno_destino=turno),
                estado='aprobada'
            ).order_by('-fecha_resolucion').select_related(
                'explorador_solicitante',
                'explorador_receptor'
            ).first()
            
            if solicitud:
                # Determinar si el empleado es el solicitante o receptor
                es_solicitante = solicitud.explorador_solicitante.id == empleado.id
                companero = solicitud.explorador_receptor if es_solicitante else solicitud.explorador_solicitante
                
                informacion_cambio = {
                    'solicitud_id': solicitud.id,
                    'jornada_actual': turno.jornada.nombre if turno.jornada else 'N/A',
                    'companero_nombre': f"{companero.nombre} {companero.apellido}",
                    'fecha_aprobacion': DateUtils.format_datetime_display(solicitud.fecha_resolucion) or 'N/A',
                    'es_solicitante': es_solicitante
                }
                
                mensaje = (
                    f"Ya tienes un cambio aprobado para esta fecha. "
                    f"Tu jornada actual es {turno.jornada.nombre} (intercambio con {companero.nombre} {companero.apellido}). "
                    f"Este nuevo cambio lo reemplazará."
                )
                
                return json_ok({
                    'tiene_cambio_aprobado': True,
                    'mensaje': mensaje,
                    'informacion_cambio': informacion_cambio
                })
            else:
                # Hay turno pero no se encontró la solicitud (caso raro)
                return json_ok({
                    'tiene_cambio_aprobado': True,
                    'mensaje': f"Ya tienes un turno asignado para esta fecha (jornada: {turno.jornada.nombre if turno.jornada else 'N/A'}). Este nuevo cambio lo reemplazará.",
                    'informacion_cambio': {
                        'jornada_actual': turno.jornada.nombre if turno.jornada else 'N/A',
                        'solicitud_id': None
                    }
                })
                
        except Exception:
            logger.exception('Error en ObtenerCambioAprobadoView')
            return json_error('Error al verificar cambio aprobado', status=500, code='internal_error')


