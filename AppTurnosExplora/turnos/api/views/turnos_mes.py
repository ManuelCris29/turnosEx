from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.views.generic import View

from core.utils.date_utils import DateUtils
from core.utils.json_responses import json_error_inesperado
from turnos.models import AsignarJornadaExplorador, Turno
from turnos.services import mis_turnos_dia
from turnos.services.turno_service import TurnoService


class TurnosPorDiaView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            fecha = request.GET.get('fecha')
            if not fecha:
                return JsonResponse({'error': 'Debe seleccionar una fecha'}, status=400)
            data = TurnoService.get_exploradores_por_jornada(fecha)
            # Los datos ya vienen como diccionarios desde el servicio
            # Solo necesitamos retornarlos directamente
            return JsonResponse({'am': data.get('am', []), 'pm': data.get('pm', [])})
        except Exception as e:
            return json_error_inesperado(
                request, e, 'No pudimos cargar los turnos de ese día. Inténtalo de nuevo.')


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
    """Vista para obtener jornadas de un mes específico (cálculo dinámico)
    FASE 3.5: Optimizada con caché para mejorar rendimiento
    """

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
            # Normalizar representaciones
            mes = f"{mes_int:02d}"
            anio = str(anio_int)
        except ValueError:
            return JsonResponse({'error': 'anio/mes deben ser numéricos'}, status=400)

        # FASE 3.5: Generar clave de caché única para este empleado y mes (normalizados)
        from core.services.cache_service import CacheService

        cache_key = f'turnos_mes_{empleado.id}_{anio}_{mes}'

        # FASE 3.5: Intentar obtener datos del caché
        cached_data = CacheService.get(cache_key)
        if cached_data is not None:
            return JsonResponse(cached_data)

        try:
            # Calcular inicio y fin del mes solicitado
            fecha_inicio = DateUtils.parse_date(f"{anio}-{mes}-01")
            if int(mes) == 12:
                fecha_fin = DateUtils.parse_date(f"{int(anio)+1}-01-01") - timedelta(days=1)
            else:
                fecha_fin = DateUtils.parse_date(f"{anio}-{int(mes)+1:02d}-01") - timedelta(days=1)

            # Obtener turnos del mes solicitado (optimizado, evitando N+1)
            turnos_mes = (
                Turno.objects
                .filter(explorador=empleado, fecha__gte=fecha_inicio, fecha__lte=fecha_fin)
                .select_related('jornada', 'sala')
                .order_by('fecha', 'jornada__nombre')
            )

            # CORRECCIÓN: Agrupar turnos por fecha para manejar dobladas (AM+PM)
            # En lugar de sobrescribir, crear listas de turnos por fecha
            turnos_por_fecha = {}
            for t in turnos_mes:
                if t.fecha not in turnos_por_fecha:
                    turnos_por_fecha[t.fecha] = []
                turnos_por_fecha[t.fecha].append(t)

            # FASE 3.2: Obtener jornada predeterminada (usar first() en lugar de get() para evitar errores)
            # Obtener la jornada más reciente por fecha_inicio
            jornada_predeterminada = (
                AsignarJornadaExplorador.objects
                .filter(explorador=empleado)
                .select_related('jornada')
                .order_by('-fecha_inicio')
                .first()
            )
            jornada_base = (jornada_predeterminada.jornada.nombre if jornada_predeterminada else None)

            # Validar que el empleado tenga jornada asignada
            if not jornada_base:
                return JsonResponse({
                    'error': f'El empleado {empleado.nombre} {empleado.apellido} no tiene jornada asignada. '
                             'Todos los exploradores deben tener una jornada (AM o PM) asignada.'
                }, status=400)

            from core.utils.jornada_utils import JornadaUtils
            def calcular_jornada_dia(j_base, fecha):
                return JornadaUtils.calcular_jornada_dia(j_base, fecha)

            from turnos.services.descanso_semana_service import DescansoSemanaService as _DSS
            def calcular_predeterminado(fecha):
                """
                Jornada PREDETERMINADA del día (lo que sería SIN ningún cambio), considerando la
                TEMPORADA además de base+alternancia. En un día de temporada donde el grupo del
                empleado descansa, lo predeterminado es DESCANSO (no su jornada base); si el grupo
                CONTRARIO descansa, este cubre el día completo (DOBLADA). Sin esto, el detalle de
                Mis Turnos decía "tu jornada predeterminada era PM" cuando en realidad ese día
                descansaba. Devuelve 'AM'/'PM'/'DOBLADA'/'DESCANSO'.
                """
                if fecha.weekday() < 5:
                    if _DSS.es_descanso_semana_manual(jornada_base, fecha):
                        return 'DESCANSO'
                    contraria = 'PM' if jornada_base == 'AM' else 'AM'
                    if _DSS.es_descanso_semana_manual(contraria, fecha):
                        return 'DOBLADA'
                    from turnos.models import DiaEspecial as _DE
                    if _DE.es_mantenimiento_efectivo(fecha):
                        return 'DESCANSO'
                return calcular_jornada_dia(jornada_base, fecha)

            # FUENTE DE VERDAD ÚNICA (batch): estado predeterminado/calculado por día
            # (alternancia de finde, temporada, mantenimiento, base). Reemplaza la lógica
            # de capas duplicada que antes vivía en este bucle. Ver
            # docs/AUDITORIA_FUENTE_VERDAD_TURNOS.md
            from turnos.services.turno_service import TurnoService as _TSestado
            estados_mes = _TSestado.estado_mes(empleado, int(anio), int(mes))

            # La sala es informativa (especialidad del explorador vía CompetenciaEmpleado);
            # ya no existe asignación de sala por período.
            asignaciones_activas = None

            # DESCANSOS por solicitud aprobada (DOBLADA, D FDS, CAMBIO DESCANSO y DOBLADA
            # PERMANENTE): FUENTE UNICA compartida con estado_dia/estado_mes. Un solo batch,
            # SIEMPRE por FECHA especifica (no por patron de weekday), con la info que consume
            # el detalle del dia. Reemplaza los antiguos dicts inline (que reimplementaban esta
            # regla y divergian, causando atribuciones al companero equivocado).
            from solicitudes.services.descanso_solicitud_service import DescansoPorSolicitudService
            descansos_sol = DescansoPorSolicitudService.en_rango(empleado, fecha_inicio, fecha_fin)

            permisos_por_fecha = MisTurnosPorMesView._permisos_por_fecha(empleado, fecha_inicio, fecha_fin)
            restricciones_por_fecha = MisTurnosPorMesView._restricciones_por_fecha(empleado, fecha_inicio, fecha_fin)
            sanciones_por_fecha = MisTurnosPorMesView._sanciones_por_fecha(empleado, fecha_inicio, fecha_fin)
            # Crear estructura de datos para el mes
            _ctx_mes = mis_turnos_dia.ContextoMes(
                turnos_por_fecha=turnos_por_fecha,
                estados_mes=estados_mes,
                descansos_sol=descansos_sol,
                jornada_base=jornada_base,
                asignaciones_activas=asignaciones_activas,
                calcular_jornada_dia=calcular_jornada_dia,
                calcular_predeterminado=calcular_predeterminado,
            )

            turnos_mes_dict = {}
            dias_mes = (fecha_fin - fecha_inicio).days + 1
            for i in range(dias_mes):
                fecha = fecha_inicio + timedelta(days=i)
                # La decisión de QUÉ ve el explorador ese día vive en
                # `turnos/services/mis_turnos_dia.py`: eran 184 líneas dentro de este
                # bucle, y esta vista ya tenía bastante con validar, cachear y responder.
                mis_turnos_dia.escribe_en(turnos_mes_dict, fecha, _ctx_mes)

            MisTurnosPorMesView._enriquecer_solicitud_info(
                turnos_mes_dict, turnos_por_fecha, empleado, fecha_inicio, fecha_fin)
            # Adjuntar el permiso especial (si lo hay) a cada día — antes de cachear
            for _fstr, _pinfo in permisos_por_fecha.items():
                if _fstr in turnos_mes_dict:
                    turnos_mes_dict[_fstr]['permiso'] = _pinfo

            # Adjuntar la restricción (si la hay) a cada día
            for _fstr, _rinfo in restricciones_por_fecha.items():
                if _fstr in turnos_mes_dict:
                    turnos_mes_dict[_fstr]['restriccion'] = _rinfo

            # Adjuntar la sanción (si la hay) a cada día
            for _fstr, _sinfo in sanciones_por_fecha.items():
                if _fstr in turnos_mes_dict:
                    turnos_mes_dict[_fstr]['sancion'] = _sinfo

            # FASE 3.5: Guardar en caché usando CacheService
            # Los datos de turnos no cambian frecuentemente, así que 1 hora es seguro
            from core.services.cache_service import CACHE_TTL_LONG
            CacheService.set(cache_key, turnos_mes_dict, ttl=CACHE_TTL_LONG)

            return JsonResponse(turnos_mes_dict)

        except Exception as e:
            # Aquí había código de depuración que se quedó puesto: dos `print`
            # y, en el propio JSON, `'traceback': error_trace if
            # request.user.is_staff else None`. Es decir, la aplicación
            # publicaba el traceback COMPLETO —rutas de fichero, líneas de
            # código y nombres de variables— a cualquier usuario `is_staff`,
            # que aquí incluye a los supervisores. Los `print`, además, salían
            # sin nivel y sin el identificador de la petición, así que en
            # CloudWatch quedaban sueltos y sin poder cruzarlos con nada.
            return json_error_inesperado(
                request, e, 'No pudimos cargar tus turnos de ese mes. Inténtalo de nuevo.')

    @staticmethod
    def _permisos_por_fecha(empleado, fecha_inicio, fecha_fin):
        # PERMISOS ESPECIALES del explorador que caen en el mes (puntual o permanente).
        # No cambian la jornada; se muestran como indicador en el día.
        from django.db.models import Q

        from permisos.models import PermisoEspecial
        permisos_por_fecha = {}
        # El permiso entra si su RANGO se solapa con el mes, o si su día de COMPENSACIÓN cae
        # dentro. Lo segundo no es redundante: la compensación de MEDIA_JORNADA_TEMPORADA es un
        # día de la misma SEMANA, y una semana puede cruzar el cambio de mes. Filtrando solo por
        # el rango, un permiso del 31 de enero con compensación el 2 de febrero no se traía al
        # consultar febrero, y el bloque que marca `fecha_compensacion` de más abajo quedaba
        # muerto justo en el caso que lo justifica.
        pe_qs = (
            PermisoEspecial.objects
            .filter(
                Q(fecha_inicio__lte=fecha_fin, fecha_fin__gte=fecha_inicio)
                | Q(fecha_compensacion__range=(fecha_inicio, fecha_fin)),
                empleado=empleado, estado__in=['APROBADO', 'PENDIENTE'],
            )
            .select_related('cubre')
        )
        for p in pe_qs:
            p_info = {
                'horas': float(p.tiempo or 0),
                'especificacion': p.especificacion or '',
                'tipo': p.get_tipo_display(),
                'cubre': f"{p.cubre.nombre} {p.cubre.apellido}" if p.cubre else None,
                'estado': p.estado,
                'es_permanente': p.es_permanente,
            }
            if p.es_permanente:
                dias_set = {int(x) for x in p.dias_semana.split(',') if x.strip().isdigit()}
                di = max(p.fecha_inicio, fecha_inicio)
                dfin = min(p.fecha_fin, fecha_fin)
                while di <= dfin:
                    if di.weekday() in dias_set:
                        permisos_por_fecha[di.strftime('%Y-%m-%d')] = p_info
                    di += timedelta(days=1)
            else:
                if fecha_inicio <= p.fecha_inicio <= fecha_fin:
                    permisos_por_fecha[p.fecha_inicio.strftime('%Y-%m-%d')] = p_info
                # Media jornada de temporada: el permiso también toca el día de COMPENSACIÓN
                # (trabajas la otra media ahí), así que se marca también ese día.
                fcomp = getattr(p, 'fecha_compensacion', None)
                if fcomp and fecha_inicio <= fcomp <= fecha_fin:
                    permisos_por_fecha[fcomp.strftime('%Y-%m-%d')] = p_info

        return permisos_por_fecha

    @staticmethod
    def _restricciones_por_fecha(empleado, fecha_inicio, fecha_fin):
        # RESTRICCIONES del empleado vigentes en el mes (aplican TODOS los días del rango;
        # fecha_fin nula = indefinida/en curso).
        from empleados.models import RestriccionEmpleado
        restricciones_por_fecha = {}
        rest_qs = RestriccionEmpleado.objects.filter(
            empleado=empleado, fecha_inicio__lte=fecha_fin
        ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio))
        for r in rest_qs:
            r_info = {
                'tipo': r.tipo_restriccion or 'Restricción',
                'recomendacion': r.recomendacion or '',
                'indefinida': r.fecha_fin is None,
            }
            ini = max(r.fecha_inicio, fecha_inicio)
            fin = min(r.fecha_fin, fecha_fin) if r.fecha_fin else fecha_fin
            di = ini
            while di <= fin:
                restricciones_por_fecha[di.strftime('%Y-%m-%d')] = r_info
                di += timedelta(days=1)

        return restricciones_por_fecha

    @staticmethod
    def _sanciones_por_fecha(empleado, fecha_inicio, fecha_fin):
        """
        Días del mes marcados como sancionados (el explorador no puede solicitar nada).

        Una sanción LEVANTADA solo pinta hasta el día anterior al levantamiento: a partir
        de ahí ya no bloquea, y seguir marcando el calendario haría creer al explorador
        que sigue castigado cuando el formulario ya le deja pedir.
        """
        from empleados.models import SancionEmpleado
        sanciones_por_fecha = {}
        sanc_qs = SancionEmpleado.objects.filter(
            explorador=empleado, fecha_inicio__lte=fecha_fin
        ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio))
        for s in sanc_qs:
            # Fin REAL: el levantamiento manda sobre la fecha de fin planeada.
            fin_real = s.fecha_fin_efectiva
            s_info = {
                'motivo': s.motivo or '',
                'desde': s.fecha_inicio.strftime('%d/%m/%Y'),
                'hasta': fin_real.strftime('%d/%m/%Y') if fin_real else None,
                'levantada': s.esta_levantada,
            }
            ini = max(s.fecha_inicio, fecha_inicio)
            fin = min(fin_real, fecha_fin) if fin_real else fecha_fin
            di = ini
            while di <= fin:
                sanciones_por_fecha[di.strftime('%Y-%m-%d')] = s_info
                di += timedelta(days=1)

        return sanciones_por_fecha

    @staticmethod
    def _enriquecer_solicitud_info(turnos_mes_dict, turnos_por_fecha, empleado,
                                   fecha_inicio, fecha_fin):
        """
        Adjunta a cada día el ACUERDO que lo modificó: con quién es, qué papel juega cada
        uno y cuándo se aprobó. Es lo que hace que el detalle del día pueda decir "estás
        cubriendo a X" en vez de solo "ahora trabajas DOBLADA".

        FUENTE ÚNICA: `AcuerdoPorDiaService`. Aquí vivían 240 líneas con OCHO consultas que
        reimplementaban a mano la geometría de cada tipo (quién trabaja qué fecha), y esa
        copia nunca estuvo completa: DOBLADA PERMANENTE no tenía ninguna consulta, CT
        PERMANENTE solo cubría el primer día del rango —`turno_origen`/`turno_destino`
        apuntan al primer turno creado— y CAMBIO DESCANSO entre semana solo dos de sus
        cuatro combinaciones. Los días que se caían del mapeo salían sin compañero.

        `turno_origen`/`turno_destino` se conserva como RESPALDO, para un día con cambio
        que ningún snapshot reclame.
        """
        from solicitudes.services.acuerdo_por_dia_service import AcuerdoPorDiaService

        acuerdos = AcuerdoPorDiaService.en_rango(empleado, fecha_inicio, fecha_fin)
        respaldo = MisTurnosPorMesView._solicitud_por_turno(turnos_por_fecha)

        for fecha_str, info in turnos_mes_dict.items():
            fecha = DateUtils.parse_date(fecha_str)
            solicitud_info = acuerdos.get(fecha)
            if solicitud_info is None and (info.get('es_cambio') or info.get('es_doblada')):
                solicitud_info = MisTurnosPorMesView._respaldo_por_turno(
                    respaldo, info, turnos_por_fecha, fecha)
            info['solicitud_info'] = solicitud_info

    @staticmethod
    def _solicitud_por_turno(turnos_por_fecha):
        """
        { turno_id: info } para los turnos que una solicitud enlazó explícitamente.

        Solo los tipos que guardan `turno_origen`/`turno_destino` (CAMBIO TURNO y, en su
        primer día, CT PERMANENTE) llegan aquí. Es el respaldo del mapeo por snapshot.
        """
        from solicitudes.models import SolicitudCambio

        turno_ids = [t.id for turnos in turnos_por_fecha.values() for t in turnos
                     if t.tipo_cambio is not None]
        if not turno_ids:
            return {}

        por_turno = {}
        solicitudes = (
            SolicitudCambio.objects
            .filter(Q(turno_origen_id__in=turno_ids) | Q(turno_destino_id__in=turno_ids),
                    estado='aprobada')
            .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor')
            .order_by('-fecha_resolucion', '-id')[:50]
        )
        for solicitud in solicitudes:
            for turno_id, rol, companero in (
                (solicitud.turno_origen_id, 'solicitante', solicitud.explorador_receptor),
                (solicitud.turno_destino_id, 'receptor', solicitud.explorador_solicitante),
            ):
                if turno_id and turno_id in turno_ids and turno_id not in por_turno:
                    por_turno[turno_id] = {
                        'solicitud_id': solicitud.id,
                        'tipo': solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else None,
                        'tipo_cambio': solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else None,
                        'companero_id': companero.id,
                        'companero_nombre': f'{companero.nombre} {companero.apellido}'.strip(),
                        'rol': rol,
                        'fecha_solicitud': DateUtils.format_datetime_display(solicitud.fecha_solicitud),
                        'fecha_resolucion': DateUtils.format_datetime_display(solicitud.fecha_resolucion),
                        'fecha_relacionada': None,
                    }
        return por_turno

    @staticmethod
    def _respaldo_por_turno(por_turno, info, turnos_por_fecha, fecha):
        """El acuerdo enlazado a cualquiera de los turnos de ese día, o None."""
        if not por_turno:
            return None
        turno_id = info.get('turno_id')
        if turno_id and turno_id in por_turno:
            return por_turno[turno_id]
        # Una doblada tiene DOS turnos ese día y `turno_id` solo guarda el primero.
        for turno in turnos_por_fecha.get(fecha, []):
            if turno.id in por_turno:
                return por_turno[turno.id]
        return None
