"""
Servicio para gestión de turnos.

Responsabilidad única: Obtener y procesar información de turnos de exploradores.
"""
import logging
import re
from datetime import timedelta

from core.constants import JornadaDisplay
from core.interfaces import ITurnoService
from core.utils.date_utils import DateUtils
from empleados.models import CompetenciaEmpleado, Empleado, Jornada
from turnos.models import AsignarJornadaExplorador, Turno

logger = logging.getLogger(__name__)

# Un finde o festivo sin alternancia publicada NO se resuelve inventando un grupo: se
# reporta con esta fuente para que la UI y los formularios lo distingan de un descanso.
_MOTIVO_SIN_PLANIFICAR = 'El año %s aún no tiene la alternancia de findes y festivos publicada'


class TurnoService(ITurnoService):
    @staticmethod
    def get_exploradores_por_jornada(fecha):
        """
        Obtiene exploradores agrupados por jornada (AM/PM) para una fecha específica.
        
        OPTIMIZACIÓN: Pre-carga todos los turnos y asignaciones en consultas batch
        para evitar N+1 queries.
        
        Args:
            fecha: Fecha en formato string 'YYYY-MM-DD'
        
        Returns:
            Diccionario con listas de exploradores por jornada: {'am': [...], 'pm': [...]}
        """
        fecha_str = re.match(r"\d{4}-\d{2}-\d{2}", fecha).group(0)
        fecha_obj = DateUtils.parse_date(fecha_str)
        
        # OPTIMIZACIÓN: Pre-cargar todos los exploradores activos con relaciones
        exploradores = Empleado.objects.filter(activo=True).select_related('supervisor')
        explorador_ids = list(exploradores.values_list('id', flat=True))
        
        # OPTIMIZACIÓN: Pre-cargar todos los turnos de la fecha en una sola consulta
        turnos_fecha = (
            Turno.objects
            .filter(explorador_id__in=explorador_ids, fecha=fecha_obj)
            .select_related('jornada', 'explorador')
        )
        
        # Crear diccionario para acceso rápido: {explorador_id: turno}
        turnos_por_explorador = {
            turno.explorador_id: turno
            for turno in turnos_fecha
        }
        
        # OPTIMIZACIÓN: Pre-cargar todas las asignaciones de jornada relevantes
        asignaciones = (
            AsignarJornadaExplorador.objects
            .filter(explorador_id__in=explorador_ids, fecha_inicio__lte=fecha_obj)
            .select_related('jornada', 'explorador')
            .order_by('explorador', '-fecha_inicio')
        )
        
        # Agrupar por explorador y tomar la más reciente
        asignaciones_por_explorador = {}
        for asignacion in asignaciones:
            if asignacion.explorador_id not in asignaciones_por_explorador:
                asignaciones_por_explorador[asignacion.explorador_id] = asignacion
        
        # Procesar en memoria usando datos pre-cargados
        am, pm = [], []
        for explorador in exploradores:
            jornada = None
            tipo = None
            
            # 1. Buscar primero en Turnos (cambios aprobados tienen prioridad)
            turno = turnos_por_explorador.get(explorador.id)
            if turno:
                jornada = turno.jornada
                tipo = 'cambio'
            else:
                # 2. Si no hay turno, buscar en asignaciones fijas
                asignacion = asignaciones_por_explorador.get(explorador.id)
                if asignacion:
                    jornada = asignacion.jornada
                    tipo = 'oficial'
            
            if jornada:
                item = {
                    'id': explorador.id,
                    'nombre': explorador.nombre,
                    'apellido': explorador.apellido,
                    'tipo': tipo
                }
                jornada_nombre = jornada.nombre.strip().lower()
                if jornada_nombre == 'am':
                    am.append(item)
                elif jornada_nombre == 'pm':
                    pm.append(item)
        
        return {'am': am, 'pm': pm}

    @staticmethod
    def get_exploradores_por_jornada_rango(fecha_inicio, fecha_fin):
        inicio_str = re.match(r"\d{4}-\d{2}-\d{2}", fecha_inicio).group(0)
        fin_str = re.match(r"\d{4}-\d{2}-\d{2}", fecha_fin).group(0)
        inicio = DateUtils.parse_date(inicio_str)
        fin = DateUtils.parse_date(fin_str)
        dias = (fin - inicio).days + 1
        resultado = {}
        for i in range(dias):
            dia = inicio + timedelta(days=i)
            resultado[str(dia)] = TurnoService.get_exploradores_por_jornada(str(dia))
        return resultado
    
    @staticmethod
    def get_turno_explorador(explorador_id, fecha):
        """
        Obtiene el turno de un explorador para una fecha específica.
        
        Prioridad:
        1. Turno específico para esa fecha
        2. Jornada predeterminada con asignación de sala especial
        3. Jornada predeterminada con salas de competencia
        
        Args:
            explorador_id: ID del explorador
            fecha: Fecha en formato string 'YYYY-MM-DD'
        
        Returns:
            Diccionario con información del turno o None si hay error
        """
        try:
            fecha_obj = DateUtils.parse_date(fecha)
            explorador = Empleado.objects.get(id=explorador_id)
            
            # 1. Buscar turnos específicos para esa fecha (puede haber múltiples si es doblada)
            turnos = Turno.objects.select_related('jornada', 'sala').filter(
                explorador_id=explorador_id,
                fecha=fecha_obj
            )
            
            if turnos.exists():
                # Usar helper para obtener jornada display (detecta dobladas)
                jornada_display = TurnoService.obtener_jornada_display(explorador, fecha_obj)
                
                # Obtener el primer turno para datos de sala y horarios
                turno = turnos.first()
                
                # Si es doblada, obtener horarios combinados (AM inicio, PM fin)
                if jornada_display == JornadaDisplay.DOBLADA:
                    turno_am = turnos.filter(jornada__nombre__iexact='AM').first()
                    turno_pm = turnos.filter(jornada__nombre__iexact='PM').first()
                    hora_inicio = turno_am.jornada.hora_inicio.strftime('%H:%M') if turno_am else turno.jornada.hora_inicio.strftime('%H:%M')
                    hora_fin = turno_pm.jornada.hora_fin.strftime('%H:%M') if turno_pm else turno.jornada.hora_fin.strftime('%H:%M')
                else:
                    hora_inicio = turno.jornada.hora_inicio.strftime('%H:%M')
                    hora_fin = turno.jornada.hora_fin.strftime('%H:%M')
                
                return {
                    'id': turno.id,
                    'jornada': jornada_display,  # JornadaDisplay: DOBLADA | AM | PM
                    # La sala es opcional (informativa): puede no estar cargada.
                    'sala': turno.sala.nombre if turno.sala else 'Por asignar',
                    'sala_id': turno.sala.id if turno.sala else None,
                    'hora_inicio': hora_inicio,
                    'hora_fin': hora_fin,
                    'es_turno_virtual': False,
                    'tipo_cambio': turno.tipo_cambio,
                    'tipo_sala': 'turno',
                    'es_doblada': jornada_display == JornadaDisplay.DOBLADA
                }
            
            # 2. Sin turno real: FUENTE DE VERDAD ÚNICA (estado_dia) para el estado virtual.
            #    Cubre TODAS las capas igual que "Mis Turnos": descanso por solicitud aprobada,
            #    temporada (descanso o día completo), festivos, alternancia de finde y su
            #    override manual, mantenimiento y jornada base. Solo si ninguna capa aplica
            #    queda la jornada predeterminada (base).
            estado = TurnoService.estado_dia(explorador, fecha_obj)
            if not estado['trabaja']:
                # Descansa ese día (igual contrato que antes: sin jornada → None)
                return None

            jornada_display = estado['jornada']  # JornadaDisplay: AM | PM | DOBLADA
            competencias = CompetenciaEmpleado.objects.filter(empleado=explorador).select_related('sala')
            salas_competencia = [
                {'id': c.sala.id, 'nombre': c.sala.nombre} for c in competencias
            ]

            if jornada_display == JornadaDisplay.DOBLADA:
                jornada_am = Jornada.objects.filter(nombre__iexact='AM').first()
                jornada_pm = Jornada.objects.filter(nombre__iexact='PM').first()
                return {
                    'id': None,
                    'jornada': JornadaDisplay.DOBLADA,
                    'sala': None,
                    'sala_id': None,
                    'hora_inicio': jornada_am.hora_inicio.strftime('%H:%M') if jornada_am and jornada_am.hora_inicio else None,
                    'hora_fin': jornada_pm.hora_fin.strftime('%H:%M') if jornada_pm and jornada_pm.hora_fin else None,
                    'es_turno_virtual': True,
                    'tipo_sala': 'competencia',
                    'salas_competencia': salas_competencia,
                    'es_doblada': True,
                    'fuente': estado['fuente'],
                }

            jornada_dia = Jornada.objects.filter(nombre__iexact=jornada_display).first() if jornada_display else None
            if jornada_dia is None:
                return None
            return {
                'id': None,
                'jornada': jornada_dia.nombre,
                'sala': None,
                'sala_id': None,
                'hora_inicio': jornada_dia.hora_inicio.strftime('%H:%M') if jornada_dia.hora_inicio else None,
                'hora_fin': jornada_dia.hora_fin.strftime('%H:%M') if jornada_dia.hora_fin else None,
                'es_turno_virtual': True,
                'tipo_sala': 'competencia',
                'salas_competencia': salas_competencia,
                'fuente': estado['fuente'],
            }
        except ValueError:
            return None

    # ------------------------------------------------------------------ #
    # FUENTE DE VERDAD ÚNICA DEL ESTADO DE UN DÍA
    # Ver docs/AUDITORIA_FUENTE_VERDAD_TURNOS.md
    # ------------------------------------------------------------------ #
    @staticmethod
    def _descanso_por_solicitud(empleado, fecha, excluir_id=None):
        """
        L2: ¿el empleado descansa `fecha` por una solicitud APROBADA (sin registro Turno)?
        Devuelve dict {motivo, companero, ...} o None. Cubre DOBLADA, D FDS, CAMBIO DESCANSO
        y DOBLADA PERMANENTE.

        Delega en `DescansoPorSolicitudService` (FUENTE ÚNICA compartida con `estado_mes` y el
        endpoint de Mis Turnos), para que la atribución de descanso/compañero sea idéntica en
        todos lados. `excluir_id`: ignora esa solicitud (la PROPIA, al aplicarla ya aprobada).
        """
        from solicitudes.services.descanso_solicitud_service import DescansoPorSolicitudService
        return DescansoPorSolicitudService.en_fecha(empleado, fecha, excluir_id=excluir_id)

    @staticmethod
    def dia_comprometido_por_solicitud(empleado, fecha, excluir_id=None):
        """
        L2 aislado: ¿el empleado YA tiene `fecha` comprometida (descansa) por una solicitud
        APROBADA (cambio descanso, doblada, d_fds, doblada permanente)?

        Útil para los formularios que SÍ permiten operar en temporada/festivo (p. ej. DOBLADA),
        donde no se quiere usar `estado_dia` completo (que bloquearía temporada), pero sí evitar
        el doble-compromiso del mismo día. Devuelve dict {motivo, companero} o None.

        `excluir_id`: ignora esa solicitud (la PROPIA, al aplicarla ya aprobada).
        """
        if isinstance(fecha, str):
            fecha = DateUtils.parse_date(fecha)
        return TurnoService._descanso_por_solicitud(empleado, fecha, excluir_id=excluir_id)

    @staticmethod
    def dia_cubriendo_por_solicitud(empleado, fecha, excluir_id=None):
        """
        Espejo de `dia_comprometido_por_solicitud`: ¿el empleado TRABAJA `fecha` porque está
        CUBRIENDO a otro por una solicitud APROBADA?

        Dos formas de estar cubriendo:
          - es el RECEPTOR y `fecha` es la fecha de cesión (tomó el día del compañero),
          - es el SOLICITANTE y `fecha` es la fecha de pago (devuelve el favor).

        Hace falta porque `dia_comprometido_por_solicitud` solo ve DESCANSOS: un día que se
        trabaja por un compromiso previo parece un día normal de trabajo, y así se podía ceder
        (o vaciar) dejando sin cobertura al acreedor de la solicitud original.

        Devuelve {motivo, companero, solicitud_id, tipo, fecha_cesion, fecha_pago, jornada} o None.
        `jornada` ('AM'/'PM' o None si no se puede determinar) es la MITAD del día que está
        comprometida por el favor. Hace falta porque en una DOBLADA (AM+PM) solo una de las dos
        mitades viene del favor: la otra es jornada propia y se puede mover libremente. Sin este
        dato el chequeo era a nivel de DÍA y bloqueaba también ceder la mitad propia.
        `excluir_id`: ignora esa solicitud (la PROPIA, al re-validarla o re-aplicarla).
        """
        from django.db.models import Q

        from solicitudes.models import SolicitudCambio

        if isinstance(fecha, str):
            fecha = DateUtils.parse_date(fecha)
        if not fecha:
            return None

        # CAMBIO DESCANSO queda FUERA a propósito: en el finde es un INTERCAMBIO puro (cada uno
        # sigue trabajando un solo día, solo cambia cuál). El día recibido ya se pagó con el día
        # propio, así que es jornada propia y sí se puede volver a mover. Aquí solo interesan los
        # días que se trabajan por un FAVOR pendiente: doblada/D FDS.
        TIPOS = ['DOBLADA', 'D FDS']
        qs = (SolicitudCambio.objects
              .filter(estado='aprobada', doblada__isnull=False, tipo_cambio__nombre__in=TIPOS)
              .filter(Q(explorador_receptor=empleado, fecha_cambio_turno=fecha)
                      | Q(explorador_solicitante=empleado, doblada__fecha_pago=fecha))
              .select_related('doblada', 'tipo_cambio',
                              'explorador_solicitante', 'explorador_receptor')
              .order_by('-id'))
        if excluir_id:
            qs = qs.exclude(id=excluir_id)
        s = qs.first()
        if not s:
            return None

        es_pago = s.explorador_solicitante_id == getattr(empleado, 'id', empleado)
        # El "compañero" es SIEMPRE la otra parte del favor: si estoy pagando, es quien me cubrió
        # (el receptor); si estoy cubriendo su cesión, es quien me cedió el día (el solicitante).
        companero = s.explorador_receptor if es_pago else s.explorador_solicitante
        det = getattr(s, 'doblada', None)

        # Mitad del día que ocupa el favor. Pagando: la jornada que se le cubre al acreedor
        # (la elegida si el pago es en sábado, si no su jornada base). Cubriendo una cesión:
        # la jornada cedida (o la base del cedente cuando la cesión fue completa).
        def _base(emp):
            asg = (AsignarJornadaExplorador.objects
                   .filter(explorador=emp, fecha_inicio__lte=fecha)
                   .select_related('jornada').order_by('-fecha_inicio').first())
            return asg.jornada.nombre.upper() if asg and asg.jornada else None

        if es_pago:
            _jps = (getattr(det, 'jornada_pago_sabado', '') or '').upper()
            jornada_favor = _jps if _jps in ('AM', 'PM') else _base(s.explorador_receptor)
        else:
            _jc = (getattr(det, 'jornada_cedida', '') or '').upper()
            jornada_favor = _jc if _jc in ('AM', 'PM') else _base(s.explorador_solicitante)

        return {
            # `motivo` va en 2ª persona (para mensajes dirigidos al propio interesado) y
            # `motivo_3p` en 3ª (para mensajes que hablan DE esa persona a otro). Sin las dos
            # formas, un mensaje sobre el compañero acababa diciéndole "cubres" al lector.
            'motivo': ('devuelves el favor (pago) de tu solicitud'
                       if es_pago else 'cubres el día que te cedió tu compañero'),
            'motivo_3p': ('está devolviendo el favor (pago) de su solicitud'
                          if es_pago else 'está cubriendo el día que le cedió un compañero'),
            'tipo': 'pago' if es_pago else 'cubre_cesion',
            'companero': {'id': companero.id,
                          'nombre': f'{companero.nombre} {companero.apellido}'},
            'solicitud_id': s.id,
            'tipo_solicitud': s.tipo_cambio.nombre if s.tipo_cambio else None,
            'fecha_cesion': s.fecha_cambio_turno,
            'fecha_pago': det.fecha_pago if det else None,
            'jornada': jornada_favor,
        }

    @staticmethod
    def dobla_en_festivo(empleado, fecha):
        """
        ¿Al empleado le corresponde DOBLAR (AM+PM) ese festivo por rotación?

        Regla prístina del festivo (misma que aplica `estado_dia`, líneas L5): en un
        festivo entre semana trabaja SOLO el grupo cuya jornada base coincide con el
        grupo que dobla ese día (rotación o override manual); el grupo contrario DESCANSA.
        Ignora turnos reales y solicitudes: refleja lo que el empleado haría por defecto.

        Devuelve False si la fecha no es festivo de semana, si no hay jornada base, o si
        al empleado le toca descansar (dobla el grupo contrario).
        """
        from turnos.models import DiaEspecial
        if isinstance(fecha, str):
            fecha = DateUtils.parse_date(fecha)
        if fecha.weekday() >= 5:
            return False
        if not DiaEspecial.es_festivo(fecha):
            return False
        asg = (AsignarJornadaExplorador.objects.filter(explorador=empleado, fecha_inicio__lte=fecha)
               .select_related('jornada').order_by('-fecha_inicio').first())
        jb = asg.jornada.nombre.upper() if asg and asg.jornada else None
        if not jb:
            return False
        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        grupo = AsignacionEspecialService.grupo_trabaja(fecha)
        return bool(grupo and jb == grupo.upper())

    @staticmethod
    def estado_dia(empleado, fecha):
        """
        FUENTE DE VERDAD ÚNICA: estado real de un día para un explorador, aplicando las
        6 capas en orden (ver docs/AUDITORIA_FUENTE_VERDAD_TURNOS.md):

          L1 Turno real → L2 descanso por solicitud aprobada → L6 alternancia fin de semana
          → L3 mantenimiento → L4 temporada → base.
          (L5 festivos se expone como bandera `es_festivo`; la regla la aplica cada formulario.)

        Devuelve:
          {
            'trabaja': bool,
            'jornada': 'AM'|'PM'|'DOBLADA'|None,
            'fuente': 'turno'|'solicitud'|'alternancia'|'mantenimiento'|'temporada'|'base',
            'motivo': str|None,        # descripción cuando descansa
            'es_festivo': bool,
            'companero': dict|None,    # {id, nombre} si descansa por una solicitud
          }

        ⚠️ NO SIRVE PARA SABER SI EL DÍA ES DE TEMPORADA.

        `fuente='temporada'` solo aparece para quien DESCANSA por temporada (y `DOBLADA` para
        quien cubre el día completo porque el grupo contrario descansa). Al explorador que en
        temporada CONSERVA su jornada normal se le devuelve `fuente='base'`, indistinguible de
        un día ordinario: L4 se activa vía `es_descanso_semana_manual`, que no contempla ese
        tercer caso. Comprobado el 16/12/2026 (día de temporada): 9 de 12 exploradores activos
        salen con `fuente='base'`.

        Si tu formulario DEBE rechazar la temporada, compruébalo POR REGLA contra el calendario
        (`DiaEspecial.es_temporada_en(fecha)`, o `_dia_calendario_no_apto()` en
        `solicitudes/services/cambios_permanentes_helper.py`) — NUNCA con `fuente == 'temporada'`,
        que no se cumplirá para el caso que te interesa y fallará EN SILENCIO.

        Hoy esto no rompe nada: los únicos formularios que rechazan temporada (CT PERMANENTE y
        DOBLADA PERMANENTE) ya la comprueban por regla; los demás la permiten a propósito. La
        política de cada formulario está fijada en `solicitudes/tests/test_politica_temporada.py`
        y el análisis completo, con las opciones de arreglo, en
        `docs/05-referencia/turnos/PUNTO_CIEGO_TEMPORADA_ESTADO_DIA.md`.
        """
        from turnos.models import AsignarJornadaExplorador, DiaEspecial, Turno
        from turnos.services.descanso_semana_service import DescansoSemanaService

        if isinstance(fecha, str):
            fecha = DateUtils.parse_date(fecha)

        es_festivo = DiaEspecial.es_festivo(fecha)

        def _r(trabaja, jornada, fuente, motivo=None, companero=None):
            return {'trabaja': trabaja, 'jornada': jornada, 'fuente': fuente,
                    'motivo': motivo, 'es_festivo': es_festivo, 'companero': companero}

        # L5 FESTIVO entre semana: la jornada que dobla por rotación trabaja AM+PM (DOBLADA)
        # y la jornada contraria DESCANSA. La regla de festivo MANDA sobre el horario
        # predeterminado/importado; solo un cambio EXPLÍCITO (turno con tipo_cambio, p. ej.
        # festivo-por-festivo) se respeta por encima.
        if fecha.weekday() < 5 and es_festivo:
            turnos_fv = list(Turno.objects.filter(explorador=empleado, fecha=fecha).select_related('jornada'))
            explicitos = [t for t in turnos_fv if t.tipo_cambio]
            if explicitos:
                js = {t.jornada.nombre.upper() for t in explicitos if t.jornada}
                jornada = ('DOBLADA' if {'AM', 'PM'} <= js else ('AM' if 'AM' in js else ('PM' if 'PM' in js else None)))
                return _r(True, jornada, 'turno')
            # L2 también aquí: si cedió el festivo por una solicitud aprobada y la aplicación no
            # dejó turno (cesión completa), la rotación no puede ponerlo a trabajar igualmente.
            desc_fv = TurnoService._descanso_por_solicitud(empleado, fecha)
            if desc_fv:
                return _r(False, None, 'solicitud', motivo=desc_fv['motivo'],
                          companero=desc_fv.get('companero'))
            asg_fv = (AsignarJornadaExplorador.objects.filter(explorador=empleado, fecha_inicio__lte=fecha)
                      .select_related('jornada').order_by('-fecha_inicio').first())
            jb_fv = asg_fv.jornada.nombre.upper() if asg_fv else None
            # Alternancia publicada por el supervisor. Si el año no está sembrado no se
            # inventa un grupo: se dice que falta publicarlo.
            from turnos.services.asignacion_especial_service import AsignacionEspecialService
            grupo = AsignacionEspecialService.grupo_trabaja(fecha)
            if not grupo:
                return _r(False, None, 'sin_planificar', motivo=_MOTIVO_SIN_PLANIFICAR % fecha.year)
            if jb_fv and jb_fv == grupo.upper():
                return _r(True, 'DOBLADA', 'festivo')
            return _r(False, None, 'festivo', motivo='festivo: descansa el grupo contrario')

        # L1: Turno real (máxima prioridad).
        turnos = list(Turno.objects.filter(explorador=empleado, fecha=fecha).select_related('jornada'))
        if turnos:
            js = {t.jornada.nombre.upper() for t in turnos if t.jornada}
            if 'AM' in js and 'PM' in js:
                jornada = 'DOBLADA'
            elif 'AM' in js:
                jornada = 'AM'
            elif 'PM' in js:
                jornada = 'PM'
            else:
                jornada = None
            return _r(True, jornada, 'turno')

        # L2: descanso por solicitud aprobada.
        desc = TurnoService._descanso_por_solicitud(empleado, fecha)
        if desc:
            return _r(False, None, 'solicitud', motivo=desc['motivo'], companero=desc.get('companero'))

        # Jornada base (grupo).
        asg = (AsignarJornadaExplorador.objects
               .filter(explorador=empleado, fecha_inicio__lte=fecha)
               .select_related('jornada').order_by('-fecha_inicio').first())
        jornada_base = asg.jornada.nombre.upper() if asg else None
        if not jornada_base:
            return _r(False, None, 'base', motivo='sin jornada asignada')

        # L6: fin de semana. Alternancia PUBLICADA por el supervisor (ya no se calcula).
        # Quien trabaja el finde lo hace AM+PM (DOBLADA); el otro grupo descansa.
        if fecha.weekday() in (5, 6):
            from turnos.services.asignacion_especial_service import AsignacionEspecialService
            trabaja_grp = AsignacionEspecialService.grupo_trabaja(fecha)
            if not trabaja_grp:
                return _r(False, None, 'sin_planificar', motivo=_MOTIVO_SIN_PLANIFICAR % fecha.year)
            if jornada_base == trabaja_grp.upper():
                return _r(True, 'DOBLADA', 'alternancia')
            return _r(False, None, 'alternancia', motivo='descanso de fin de semana')

        # Entre semana: L4 temporada y L3 mantenimiento.
        if DescansoSemanaService.es_descanso_semana_manual(jornada_base, fecha):
            return _r(False, None, 'temporada', motivo='descanso de temporada')
        if DiaEspecial.es_mantenimiento_efectivo(fecha):
            return _r(False, None, 'mantenimiento', motivo='lunes de mantenimiento')

        # L4 (día especial de temporada, lado del que TRABAJA): si el grupo contrario
        # descansa hoy por temporada, este grupo cubre el DÍA COMPLETO (AM+PM).
        jornada_contraria = 'PM' if jornada_base == 'AM' else 'AM'
        if DescansoSemanaService.es_descanso_semana_manual(jornada_contraria, fecha):
            return _r(True, 'DOBLADA', 'temporada')

        # Base: trabaja su jornada.
        return _r(True, jornada_base, 'base')

    @staticmethod
    def estado_mes(empleado, anio, mes):
        """
        Versión BATCH de `estado_dia` para un mes completo (~8 consultas en vez de N×día).
        Devuelve { date: <mismo dict que estado_dia> } para cada día del mes.
        Mantiene EXACTAMENTE el mismo orden de capas que `estado_dia`.

        Atajo sobre `estado_rango_multiple`, que es la implementación real (antes esta función
        tenía su propia copia del cálculo por capas).
        """
        from calendar import monthrange
        from datetime import date as _date

        ndias = monthrange(anio, mes)[1]
        return TurnoService.estado_rango(empleado, _date(anio, mes, 1), _date(anio, mes, ndias))

    @staticmethod
    def estado_rango(empleado, ini, fin):
        """
        Versión BATCH de `estado_dia` para un rango arbitrario: { date: <dict de estado_dia> }.
        Atajo de un solo empleado sobre `estado_rango_multiple`.
        """
        return TurnoService.estado_rango_multiple([empleado], ini, fin).get(
            getattr(empleado, 'id', empleado), {}
        )

    @staticmethod
    def estado_rango_multiple(empleados, ini, fin):
        """
        Versión BATCH de `estado_dia` para VARIOS empleados y un rango arbitrario, con un número
        CONSTANTE de consultas (no N×empleado×día): { emp_id: { fecha: <dict de estado_dia> } }.

        Mantiene EXACTAMENTE el mismo orden de capas que `estado_dia`:
          L1 turno real → L2 descanso por solicitud → L5 festivo (entre semana, antes que L1 salvo
          cambio explícito) → L6 alternancia de finde → L4 temporada → L3 mantenimiento → base.

        La necesitan los formularios que evalúan una MATRIZ empleado×día (CT permanente y sus
        primos): resolver esa matriz con `estado_dia` costaba ~13 consultas y ~17 ms por celda,
        de modo que un rango de 90 días con una decena de candidatos se iba a decenas de miles de
        consultas y ~40 s. Aquí el coste por celda es de microsegundos.

        ⚠️ Hereda el punto ciego de TEMPORADA de `estado_dia` (mismo orden de capas, misma L4):
        a quien conserva su jornada en temporada se le devuelve `fuente='base'`. Ver la
        advertencia completa en el docstring de `estado_dia`.

        DIFERENCIA DELIBERADA con la antigua `estado_mes`: la jornada base se resuelve POR FECHA
        (la asignación vigente ese día), no con la asignación vigente al final del rango. Si un
        explorador cambia de grupo a mitad del periodo, `estado_mes` devolvía la jornada nueva
        también para los días anteriores al cambio y contradecía a `estado_dia`, que siempre miró
        `fecha_inicio__lte=fecha`. Ahora ambas coinciden.
        """
        from bisect import bisect_right
        from datetime import timedelta as _td

        from solicitudes.services.descanso_solicitud_service import DescansoPorSolicitudService
        from turnos.models import AsignarJornadaExplorador, DescansoSemanaManual, DiaEspecial, Turno
        from turnos.services.asignacion_especial_service import AsignacionEspecialService

        if isinstance(ini, str):
            ini = DateUtils.parse_date(ini)
        if isinstance(fin, str):
            fin = DateUtils.parse_date(fin)

        empleados = list(empleados or [])
        ids = [getattr(e, 'id', e) for e in empleados]
        if not ids or fin < ini:
            return {i: {} for i in ids}

        # --- L1: turnos reales de todos los empleados (1 consulta) ---
        turnos_por_emp = {i: {} for i in ids}
        for t in (Turno.objects.filter(explorador_id__in=ids, fecha__range=(ini, fin))
                  .select_related('jornada')):
            turnos_por_emp[t.explorador_id].setdefault(t.fecha, []).append(t)

        # --- Jornada base vigente POR FECHA (1 consulta) ---
        # Se guardan las asignaciones ordenadas por fecha_inicio y luego se busca por bisección
        # la vigente en cada día. Incluye las anteriores al rango (la vigente al empezar).
        asg_por_emp = {i: ([], []) for i in ids}  # (fechas_inicio, jornadas)
        for a in (AsignarJornadaExplorador.objects
                  .filter(explorador_id__in=ids, fecha_inicio__lte=fin)
                  .select_related('jornada').order_by('fecha_inicio')):
            fechas, jornadas = asg_por_emp[a.explorador_id]
            fechas.append(a.fecha_inicio)
            jornadas.append(a.jornada.nombre.upper() if a.jornada else None)

        def _jornada_base(emp_id, d):
            fechas, jornadas = asg_por_emp[emp_id]
            pos = bisect_right(fechas, d) - 1
            return jornadas[pos] if pos >= 0 else None

        # --- Días especiales del rango (1 consulta para festivo + mantenimiento + temporada) ---
        festivos, mantenimiento_raw, temporada_especial = set(), set(), set()
        for f, tipo, es_temp in DiaEspecial.objects.filter(
                fecha__range=(ini, fin), activo=True).values_list('fecha', 'tipo', 'es_temporada'):
            if tipo == 'festivo':
                festivos.add(f)
            elif tipo == 'mantenimiento':
                mantenimiento_raw.add(f)
            if es_temp:
                temporada_especial.add(f)
        # Misma regla que `DiaEspecial.es_mantenimiento_efectivo`: la temporada manda.
        mantenimiento = mantenimiento_raw - temporada_especial

        # --- L2: descansos por solicitud aprobada (batch, ~8 consultas para todos) ---
        rest_por_emp = DescansoPorSolicitudService.en_rango_multiple(empleados, ini, fin)

        # --- L4: descansos de semana manuales del rango (1 consulta) → {fecha: {jornadas}} ---
        dsm_por_fecha = {}
        for dsm in (DescansoSemanaManual.objects
                    .filter(fecha__range=(ini, fin), activo=True).select_related('jornada')):
            if dsm.fecha.weekday() >= 5 or not dsm.jornada:
                continue
            dsm_por_fecha.setdefault(dsm.fecha, set()).add(dsm.jornada.nombre.upper())

        # --- L6/L5: alternancia publicada de findes y festivos (1 consulta) ---
        alternancia = AsignacionEspecialService.mapa_grupo_trabaja(ini, fin)

        # --- Decisión por celda (MISMO orden que estado_dia), ya sin tocar la BD ---
        salida = {}
        for emp_id in ids:
            turnos_por_fecha = turnos_por_emp[emp_id]
            rest_sol = rest_por_emp.get(emp_id, {})
            out = {}
            d = ini
            while d <= fin:
                es_festivo = d in festivos
                jornada_base = _jornada_base(emp_id, d)

                def _r(trabaja, jornada, fuente, motivo=None, companero=None, _f=es_festivo):
                    return {'trabaja': trabaja, 'jornada': jornada, 'fuente': fuente,
                            'motivo': motivo, 'es_festivo': _f, 'companero': companero}

                # L5 FESTIVO entre semana: la jornada que dobla trabaja AM+PM; la otra descansa.
                # Manda sobre el predeterminado; un cambio EXPLÍCITO (tipo_cambio) se respeta.
                if d.weekday() < 5 and es_festivo:
                    explicitos = [t for t in turnos_por_fecha.get(d, []) if t.tipo_cambio]
                    if explicitos:
                        js = {t.jornada.nombre.upper() for t in explicitos if t.jornada}
                        jornada = ('DOBLADA' if {'AM', 'PM'} <= js
                                   else ('AM' if 'AM' in js else ('PM' if 'PM' in js else None)))
                        out[d] = _r(True, jornada, 'turno')
                    elif d in rest_sol:
                        # Mismo orden que `estado_dia`: la cesión por solicitud manda sobre la rotación.
                        info = rest_sol[d]
                        out[d] = _r(False, None, 'solicitud', motivo=info['motivo'],
                                    companero=info.get('companero'))
                    else:
                        grupo = alternancia.get(d)
                        if not grupo:
                            out[d] = _r(False, None, 'sin_planificar',
                                        motivo=_MOTIVO_SIN_PLANIFICAR % d.year)
                        elif jornada_base and jornada_base == grupo.upper():
                            out[d] = _r(True, 'DOBLADA', 'festivo')
                        else:
                            out[d] = _r(False, None, 'festivo',
                                        motivo='festivo: descansa el grupo contrario')
                    d += _td(days=1)
                    continue

                turnos = turnos_por_fecha.get(d)
                if turnos:
                    js = {t.jornada.nombre.upper() for t in turnos if t.jornada}
                    jornada = ('DOBLADA' if ('AM' in js and 'PM' in js)
                               else ('AM' if 'AM' in js else ('PM' if 'PM' in js else None)))
                    out[d] = _r(True, jornada, 'turno')
                elif d in rest_sol:
                    info = rest_sol[d]
                    out[d] = _r(False, None, 'solicitud', motivo=info['motivo'],
                                companero=info.get('companero'))
                elif not jornada_base:
                    out[d] = _r(False, None, 'base', motivo='sin jornada asignada')
                elif d.weekday() in (5, 6):
                    trabaja_grp = alternancia.get(d)
                    if not trabaja_grp:
                        out[d] = _r(False, None, 'sin_planificar',
                                    motivo=_MOTIVO_SIN_PLANIFICAR % d.year)
                    elif jornada_base == trabaja_grp.upper():
                        out[d] = _r(True, 'DOBLADA', 'alternancia')
                    else:
                        out[d] = _r(False, None, 'alternancia', motivo='descanso de fin de semana')
                elif jornada_base in dsm_por_fecha.get(d, ()):
                    out[d] = _r(False, None, 'temporada', motivo='descanso de temporada')
                elif d in mantenimiento:
                    out[d] = _r(False, None, 'mantenimiento', motivo='lunes de mantenimiento')
                elif ('PM' if jornada_base == 'AM' else 'AM') in dsm_por_fecha.get(d, ()):
                    # Día especial de temporada: el grupo contrario descansa,
                    # este grupo cubre el día completo (AM+PM).
                    out[d] = _r(True, 'DOBLADA', 'temporada')
                else:
                    out[d] = _r(True, jornada_base, 'base')
                d += _td(days=1)
            salida[emp_id] = out
        return salida

    @staticmethod
    def get_salas_explorador(explorador_id):
        """
        Obtiene las salas asignadas a un explorador.
        
        Args:
            explorador_id: ID del explorador
        
        Returns:
            QuerySet de CompetenciaEmpleado
        """
        return CompetenciaEmpleado.objects.filter(
            empleado_id=explorador_id
        ).select_related('sala')
    
    @staticmethod
    def get_turnos_por_fecha(explorador, fecha_inicio, fecha_fin):
        """
        Obtiene turnos de un explorador en un rango de fechas.
        
        Args:
            explorador: Objeto Empleado
            fecha_inicio: Fecha de inicio (date object)
            fecha_fin: Fecha de fin (date object)
        
        Returns:
            Diccionario {fecha: turno} para acceso rápido
        """
        turnos = (
            Turno.objects
            .filter(
                explorador=explorador,
                fecha__gte=fecha_inicio,
                fecha__lte=fecha_fin
            )
            .select_related('jornada', 'sala')
            .order_by('fecha')
        )
        return {t.fecha: t for t in turnos}
    
    @staticmethod
    def obtener_jornada_display(explorador: Empleado, fecha) -> str:
        """
        Jornada EFECTIVA (real) para mostrar/validar: 'DOBLADA' | 'AM' | 'PM' | None (descansa).

        Delega en la FUENTE DE VERDAD `estado_dia` (turno real → descanso por solicitud → alternancia
        de fin de semana → mantenimiento → temporada → base). Antes era un híbrido que solo miraba
        turnos reales o la jornada base, y se le escapaban temporada, mantenimiento y descansos por
        solicitud → devolvía la base en días de descanso, causando incongruencias con Mis Turnos
        (p. ej. validar una doblada como si el explorador trabajara cuando en realidad descansa).

        Para la jornada BASE/predeterminada (sin overlays) usar
        `JornadaService.get_jornada_explorador_fecha` — es un concepto distinto (lo predeterminado),
        NO la fuente de verdad.
        """
        return TurnoService.estado_dia(explorador, fecha).get('jornada')