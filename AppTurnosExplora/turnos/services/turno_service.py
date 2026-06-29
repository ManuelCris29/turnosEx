"""
Servicio para gestión de turnos.

Responsabilidad única: Obtener y procesar información de turnos de exploradores.
"""
from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from turnos.models import AsignarJornadaExplorador, Turno
from turnos.services.jornada_service import JornadaService
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
from core.utils.jornada_utils import JornadaUtils
from datetime import datetime, timedelta
from django.db.models import Q
import re
import logging
from core.interfaces import ITurnoService

logger = logging.getLogger(__name__)


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
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        
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
        inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
        fin = datetime.strptime(fin_str, '%Y-%m-%d').date()
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
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
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
                if jornada_display == 'DOBLADA':
                    turno_am = turnos.filter(jornada__nombre__iexact='AM').first()
                    turno_pm = turnos.filter(jornada__nombre__iexact='PM').first()
                    hora_inicio = turno_am.jornada.hora_inicio.strftime('%H:%M') if turno_am else turno.jornada.hora_inicio.strftime('%H:%M')
                    hora_fin = turno_pm.jornada.hora_fin.strftime('%H:%M') if turno_pm else turno.jornada.hora_fin.strftime('%H:%M')
                else:
                    hora_inicio = turno.jornada.hora_inicio.strftime('%H:%M')
                    hora_fin = turno.jornada.hora_fin.strftime('%H:%M')
                
                return {
                    'id': turno.id,
                    'jornada': jornada_display,  # 'DOBLADA', 'AM', o 'PM'
                    'sala': turno.sala.nombre,
                    'sala_id': turno.sala.id,
                    'hora_inicio': hora_inicio,
                    'hora_fin': hora_fin,
                    'es_turno_virtual': False,
                    'tipo_cambio': turno.tipo_cambio,
                    'tipo_sala': 'turno',
                    'es_doblada': jornada_display == 'DOBLADA'
                }
            
            # 2. Si no hay turno, calcular jornada usando alternancia de fines de semana
            jornada_predeterminada = JornadaService.get_jornada_predeterminada(explorador)
            jornada_base_obj = jornada_predeterminada.jornada if jornada_predeterminada else None
            
            # Calcular jornada real del día (considera alternancia de fines de semana)
            jornada_dia = None
            if jornada_base_obj:
                try:
                    jornada_dia_calculada = JornadaUtils.calcular_jornada_dia(
                        jornada_base_obj.nombre, fecha_obj
                    )
                    # Si está en descanso, retornar None (no tiene jornada ese día)
                    if jornada_dia_calculada == "Descanso":
                        jornada_dia = None
                    else:
                        # Buscar objeto Jornada con el nombre calculado
                        jornada_dia = Jornada.objects.filter(nombre=jornada_dia_calculada).first()
                except Exception as e:
                    logger.warning(f"Error calculando jornada día para {explorador.id} en {fecha_obj}: {e}")
                    jornada_dia = jornada_base_obj  # Fallback a jornada base
            
            # Si está en descanso (jornada_dia es None), retornar None
            if jornada_dia is None:
                return None
            
            # 2b. Sábado: si por alternancia le corresponde trabajar ese sábado, mostrar DOBLADA (AM+PM)
            if fecha_obj.weekday() == 5:
                jornada_trabaja_sab = AlternanciaFinesSemanaService.jornada_trabaja_sabado(fecha_obj)
                if jornada_trabaja_sab and jornada_dia.nombre.upper() == jornada_trabaja_sab.upper():
                    jornada_am = Jornada.objects.filter(nombre__iexact='AM').first()
                    jornada_pm = Jornada.objects.filter(nombre__iexact='PM').first()
                    if jornada_am and jornada_pm:
                        competencias = CompetenciaEmpleado.objects.filter(empleado=explorador).select_related('sala')
                        salas_competencia = [{'id': c.sala.id, 'nombre': c.sala.nombre} for c in competencias]
                        return {
                            'id': None,
                            'jornada': 'DOBLADA',
                            'sala': None,
                            'sala_id': None,
                            'hora_inicio': jornada_am.hora_inicio.strftime('%H:%M') if jornada_am.hora_inicio else None,
                            'hora_fin': jornada_pm.hora_fin.strftime('%H:%M') if jornada_pm.hora_fin else None,
                            'es_turno_virtual': True,
                            'tipo_sala': 'competencia',
                            'salas_competencia': salas_competencia,
                            'es_doblada_sabado': True,
                        }
            
            # 3. Usar todas las salas de competencia (la sala es informativa: especialidad del explorador)
            competencias = CompetenciaEmpleado.objects.filter(empleado=explorador).select_related('sala')
            salas_competencia = [
                {'id': c.sala.id, 'nombre': c.sala.nombre} for c in competencias
            ]
            return {
                'id': None,
                'jornada': jornada_dia.nombre if jornada_dia else None,
                'sala': None,
                'sala_id': None,
                'hora_inicio': jornada_dia.hora_inicio.strftime('%H:%M') if jornada_dia and jornada_dia.hora_inicio else None,
                'hora_fin': jornada_dia.hora_fin.strftime('%H:%M') if jornada_dia and jornada_dia.hora_fin else None,
                'es_turno_virtual': True,
                'tipo_sala': 'competencia',
                'salas_competencia': salas_competencia
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
        Devuelve dict {motivo, companero} o None. Cubre DOBLADA, D FDS, CAMBIO DESCANSO y
        DOBLADA PERMANENTE (misma lógica que pinta "Mis Turnos").

        `excluir_id`: ignora esa solicitud (la PROPIA, al aplicarla ya aprobada) para no
        auto-detectar su efecto.
        """
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio
        from turnos.models import DiaEspecial

        def _comp(emp):
            return {'id': emp.id, 'nombre': f'{emp.nombre} {emp.apellido}'}

        def _exc(qs):
            return qs.exclude(id=excluir_id) if excluir_id else qs

        # DOBLADA / D FDS: solicitante descansa en cesión; receptor descansa en pago.
        s = (_exc(SolicitudCambio.objects
             .filter(tipo_cambio__nombre__in=['DOBLADA', 'D FDS'], estado='aprobada',
                     explorador_solicitante=empleado, fecha_cambio_turno=fecha))
             .select_related('explorador_receptor').first())
        if s:
            return {'motivo': 'cedió su jornada', 'companero': _comp(s.explorador_receptor)}
        s = (_exc(SolicitudCambio.objects
             .filter(tipo_cambio__nombre__in=['DOBLADA', 'D FDS'], estado='aprobada',
                     explorador_receptor=empleado, doblada__fecha_pago=fecha))
             .select_related('explorador_solicitante').first())
        if s:
            return {'motivo': 'paga doblada', 'companero': _comp(s.explorador_solicitante)}

        # CAMBIO DESCANSO (su día cedido).
        from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService
        if fecha in CambioDescansoAplicacionService.dias_en_descanso(empleado, fecha, fecha, excluir_id=excluir_id):
            return {'motivo': 'cambio de día de descanso', 'companero': None}

        # DOBLADA PERMANENTE (descanso recurrente; nunca domingo ni festivo).
        if fecha.weekday() != 6 and not DiaEspecial.objects.filter(
                fecha=fecha, tipo='festivo', activo=True).exists():
            perm = (_exc(SolicitudCambio.objects
                    .filter(tipo_cambio__nombre='DOBLADA PERMANENTE', estado='aprobada')
                    .filter(Q(explorador_solicitante=empleado) | Q(explorador_receptor=empleado)))
                    .select_related('doblada_permanente', 'explorador_solicitante', 'explorador_receptor'))
            for sp in perm:
                det = getattr(sp, 'doblada_permanente', None)
                if not det or not (det.fecha_inicio <= fecha <= det.fecha_fin):
                    continue
                es_sol = sp.explorador_solicitante_id == empleado.id
                dias_txt = det.dias_cesion if es_sol else det.dias_devolucion
                dias_set = {int(x) for x in (dias_txt or '').split(',') if x.strip().isdigit()}
                if fecha.weekday() in dias_set:
                    comp = sp.explorador_receptor if es_sol else sp.explorador_solicitante
                    return {'motivo': 'doblada permanente', 'companero': _comp(comp)}
        return None

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
        from datetime import datetime as _dt
        if isinstance(fecha, str):
            fecha = _dt.strptime(fecha, '%Y-%m-%d').date()
        return TurnoService._descanso_por_solicitud(empleado, fecha, excluir_id=excluir_id)

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
        """
        from datetime import datetime as _dt
        from turnos.models import Turno, DiaEspecial, AsignarJornadaExplorador
        from turnos.services.descanso_semana_service import DescansoSemanaService
        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService

        if isinstance(fecha, str):
            fecha = _dt.strptime(fecha, '%Y-%m-%d').date()

        es_festivo = DiaEspecial.objects.filter(fecha=fecha, tipo='festivo', activo=True).exists()

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
            asg_fv = (AsignarJornadaExplorador.objects.filter(explorador=empleado, fecha_inicio__lte=fecha)
                      .select_related('jornada').order_by('-fecha_inicio').first())
            jb_fv = asg_fv.jornada.nombre.upper() if asg_fv else None
            try:
                from turnos.services.festivos_rotacion_service import FestivosRotacionService
                grupo = FestivosRotacionService.get_grupo_que_dobla_en_festivo(fecha)
            except Exception:
                grupo = None
            if jb_fv and grupo and jb_fv == grupo.upper():
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

        # L6: fin de semana (alternancia). Quien trabaja el finde lo hace AM+PM (DOBLADA).
        if fecha.weekday() in (5, 6):
            trabaja_grp = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(fecha)
            if trabaja_grp and jornada_base == trabaja_grp.upper():
                return _r(True, 'DOBLADA', 'alternancia')
            return _r(False, None, 'alternancia', motivo='descanso de fin de semana')

        # Entre semana: L4 temporada y L3 mantenimiento.
        if DescansoSemanaService.es_descanso_semana_manual(jornada_base, fecha):
            return _r(False, None, 'temporada', motivo='descanso de temporada')
        if DiaEspecial.es_mantenimiento_efectivo(fecha):
            return _r(False, None, 'mantenimiento', motivo='lunes de mantenimiento')

        # Base: trabaja su jornada.
        return _r(True, jornada_base, 'base')

    @staticmethod
    def estado_mes(empleado, anio, mes):
        """
        Versión BATCH de `estado_dia` para un mes completo (~8 consultas en vez de N×día).
        Devuelve { date: <mismo dict que estado_dia> } para cada día del mes.
        Mantiene EXACTAMENTE el mismo orden de capas que `estado_dia`.
        """
        from calendar import monthrange
        from datetime import date as _date, timedelta as _td
        from django.db.models import Q
        from turnos.models import (Turno, DiaEspecial, AsignarJornadaExplorador,
                                   DescansoSemanaManual)
        from turnos.services.descanso_semana_service import DescansoSemanaService
        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
        from solicitudes.models import SolicitudCambio
        from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService

        ndias = monthrange(anio, mes)[1]
        ini = _date(anio, mes, 1)
        fin = _date(anio, mes, ndias)

        # L1: turnos reales (batch)
        turnos_por_fecha = {}
        for t in Turno.objects.filter(explorador=empleado, fecha__range=(ini, fin)).select_related('jornada'):
            turnos_por_fecha.setdefault(t.fecha, []).append(t)

        # Jornada base (asignación más reciente <= fin de mes)
        asg = (AsignarJornadaExplorador.objects.filter(explorador=empleado, fecha_inicio__lte=fin)
               .select_related('jornada').order_by('-fecha_inicio').first())
        jornada_base = asg.jornada.nombre.upper() if asg else None

        # Festivos del mes
        festivos = set(DiaEspecial.objects.filter(
            fecha__range=(ini, fin), tipo='festivo', activo=True).values_list('fecha', flat=True))

        # L2: descansos por solicitud aprobada (batch)
        rest_sol = {}  # fecha -> {motivo, companero}

        def _comp(emp):
            return {'id': emp.id, 'nombre': f'{emp.nombre} {emp.apellido}'}

        for s in (SolicitudCambio.objects.filter(
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'], estado='aprobada',
                explorador_solicitante=empleado, fecha_cambio_turno__range=(ini, fin))
                .select_related('explorador_receptor')):
            rest_sol.setdefault(s.fecha_cambio_turno,
                                {'motivo': 'cedió su jornada', 'companero': _comp(s.explorador_receptor)})
        for s in (SolicitudCambio.objects.filter(
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'], estado='aprobada',
                explorador_receptor=empleado, doblada__fecha_pago__range=(ini, fin))
                .select_related('explorador_solicitante', 'doblada')):
            fp = s.doblada.fecha_pago if s.doblada else None
            if fp:
                rest_sol.setdefault(fp, {'motivo': 'paga doblada', 'companero': _comp(s.explorador_solicitante)})
        for dcd in CambioDescansoAplicacionService.dias_en_descanso(empleado, ini, fin):
            rest_sol.setdefault(dcd, {'motivo': 'cambio de día de descanso', 'companero': None})
        for s in (SolicitudCambio.objects.filter(tipo_cambio__nombre='DOBLADA PERMANENTE', estado='aprobada')
                  .filter(Q(explorador_solicitante=empleado) | Q(explorador_receptor=empleado))
                  .select_related('doblada_permanente', 'explorador_solicitante', 'explorador_receptor')):
            det = getattr(s, 'doblada_permanente', None)
            if not det:
                continue
            es_sol = s.explorador_solicitante_id == empleado.id
            dias_set = {int(x) for x in ((det.dias_cesion if es_sol else det.dias_devolucion) or '').split(',')
                        if x.strip().isdigit()}
            comp = s.explorador_receptor if es_sol else s.explorador_solicitante
            dd = max(det.fecha_inicio, ini)
            dlast = min(det.fecha_fin, fin)
            while dd <= dlast:
                if dd.weekday() in dias_set and dd.weekday() != 6 and dd not in festivos:
                    rest_sol.setdefault(dd, {'motivo': 'doblada permanente', 'companero': _comp(comp)})
                dd += _td(days=1)

        # L4: temporada (descanso de semana manual de la jornada base)
        temporada = set()
        if jornada_base:
            for dsm in DescansoSemanaManual.objects.filter(
                    fecha__range=(ini, fin), activo=True, jornada__nombre__iexact=jornada_base):
                if dsm.fecha.weekday() < 5:
                    temporada.add(dsm.fecha)

        # L5: festivos entre semana → grupo que dobla por rotación (cacheado por fecha)
        grupo_festivo = {}
        try:
            from turnos.services.festivos_rotacion_service import FestivosRotacionService
            for fdia in festivos:
                if fdia.weekday() < 5:
                    grupo_festivo[fdia] = FestivosRotacionService.get_grupo_que_dobla_en_festivo(fdia)
        except Exception:
            grupo_festivo = {}

        # Decisión por día (MISMO orden que estado_dia)
        out = {}
        d = ini
        while d <= fin:
            es_festivo = d in festivos

            def _r(trabaja, jornada, fuente, motivo=None, companero=None):
                return {'trabaja': trabaja, 'jornada': jornada, 'fuente': fuente,
                        'motivo': motivo, 'es_festivo': es_festivo, 'companero': companero}

            # L5 FESTIVO entre semana: la jornada que dobla trabaja AM+PM; la otra descansa.
            # Manda sobre el predeterminado; un cambio EXPLÍCITO (tipo_cambio) se respeta.
            if d.weekday() < 5 and es_festivo:
                turnos_fv = turnos_por_fecha.get(d, [])
                explicitos = [t for t in turnos_fv if t.tipo_cambio]
                if explicitos:
                    js = {t.jornada.nombre.upper() for t in explicitos if t.jornada}
                    jornada = ('DOBLADA' if {'AM', 'PM'} <= js else ('AM' if 'AM' in js else ('PM' if 'PM' in js else None)))
                    out[d] = _r(True, jornada, 'turno')
                else:
                    grupo = grupo_festivo.get(d)
                    if jornada_base and grupo and jornada_base == grupo.upper():
                        out[d] = _r(True, 'DOBLADA', 'festivo')
                    else:
                        out[d] = _r(False, None, 'festivo', motivo='festivo: descansa el grupo contrario')
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
                out[d] = _r(False, None, 'solicitud', motivo=info['motivo'], companero=info.get('companero'))
            elif not jornada_base:
                out[d] = _r(False, None, 'base', motivo='sin jornada asignada')
            elif d.weekday() in (5, 6):
                trabaja_grp = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(d)
                if trabaja_grp and jornada_base == trabaja_grp.upper():
                    out[d] = _r(True, 'DOBLADA', 'alternancia')
                else:
                    out[d] = _r(False, None, 'alternancia', motivo='descanso de fin de semana')
            elif d in temporada:
                out[d] = _r(False, None, 'temporada', motivo='descanso de temporada')
            elif DiaEspecial.es_mantenimiento_efectivo(d):
                out[d] = _r(False, None, 'mantenimiento', motivo='lunes de mantenimiento')
            else:
                out[d] = _r(True, jornada_base, 'base')
            d += _td(days=1)
        return out

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
        Obtiene la jornada para mostrar en UI.
        
        Si hay AM+PM en la misma fecha → "DOBLADA"
        Si hay solo AM → "AM"
        Si hay solo PM → "PM"
        Si no hay turnos → jornada predeterminada
        
        Args:
            explorador: Instancia de Empleado
            fecha: Fecha (date object o string 'YYYY-MM-DD')
        
        Returns:
            String con la jornada para mostrar: 'DOBLADA', 'AM', 'PM', o jornada predeterminada
        """
        from datetime import date as date_type
        
        # Convertir fecha a objeto date si es string
        if isinstance(fecha, str):
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        elif isinstance(fecha, date_type):
            fecha_obj = fecha
        else:
            fecha_obj = fecha
        
        # Obtener todos los turnos del explorador en esa fecha
        turnos = Turno.objects.filter(
            explorador=explorador,
            fecha=fecha_obj
        ).select_related('jornada')
        
        jornadas = [t.jornada.nombre.upper() for t in turnos]
        
        # Si hay AM+PM → DOBLADA
        if 'AM' in jornadas and 'PM' in jornadas:
            return 'DOBLADA'
        elif 'AM' in jornadas:
            return 'AM'
        elif 'PM' in jornadas:
            return 'PM'
        else:
            # No hay turnos, calcular jornada usando alternancia de fines de semana
            jornada_predeterminada = JornadaService.get_jornada_explorador_fecha(
                explorador.id, fecha_obj.strftime('%Y-%m-%d')
            )
            if jornada_predeterminada:
                try:
                    # REGLA DE NEGOCIO: Para sábados y domingos, la jornada predeterminada es DOBLADA si corresponde trabajar
                    if fecha_obj.weekday() == 5:  # Sábado
                        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
                        jornada_trabaja_sabado = AlternanciaFinesSemanaService.jornada_trabaja_sabado(fecha_obj)
                        if jornada_trabaja_sabado and jornada_predeterminada.nombre.upper() == jornada_trabaja_sabado.upper():
                            # Le corresponde trabajar ese sábado → jornada predeterminada es DOBLADA (AM+PM)
                            return 'DOBLADA'
                        # Si no corresponde trabajar, está en descanso
                        return None
                    elif fecha_obj.weekday() == 6:  # Domingo
                        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
                        jornada_trabaja_domingo = AlternanciaFinesSemanaService.jornada_trabaja_domingo(fecha_obj)
                        if jornada_trabaja_domingo and jornada_predeterminada.nombre.upper() == jornada_trabaja_domingo.upper():
                            # Le corresponde trabajar ese domingo → jornada predeterminada es DOBLADA (AM+PM)
                            return 'DOBLADA'
                        # Si no corresponde trabajar, está en descanso
                        return None
                    
                    # Para otros días (lunes-viernes), usar JornadaUtils
                    jornada_dia_calculada = JornadaUtils.calcular_jornada_dia(
                        jornada_predeterminada.nombre, fecha_obj
                    )
                    # Si está en descanso, retornar None (no tiene jornada ese día)
                    if jornada_dia_calculada == "Descanso":
                        return None
                    return jornada_dia_calculada.upper()
                except Exception as e:
                    logger.warning(f"Error calculando jornada día para {explorador.id} en {fecha_obj}: {e}")
                    # Fallback a jornada predeterminada si hay error
                    return jornada_predeterminada.nombre.upper()
            return None