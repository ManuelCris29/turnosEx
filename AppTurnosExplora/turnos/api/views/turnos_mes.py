from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.views.generic import View

from core.constants import JornadaDisplay
from core.utils.date_utils import DateUtils
from core.utils.json_responses import json_error_inesperado
from turnos.models import AsignarJornadaExplorador, Turno
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
            turnos_mes_dict = {}
            dias_mes = (fecha_fin - fecha_inicio).days + 1
            for i in range(dias_mes):
                fecha = fecha_inicio + timedelta(days=i)
                turnos_dia = turnos_por_fecha.get(fecha, [])

                # FESTIVO entre semana: la fuente de verdad manda sobre el horario
                # predeterminado (la jornada que dobla por rotación trabaja AM+PM, la otra
                # descansa). Solo un cambio EXPLÍCITO se respeta: en ese caso estado_mes
                # devuelve fuente='turno' y caemos al flujo normal de abajo.
                _est_fv = estados_mes.get(fecha)
                if _est_fv and _est_fv.get('fuente') == 'festivo':
                    if _est_fv['trabaja']:
                        turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                            'jornada': 'DOBLADA',
                            'sala': 'Por asignar',
                            'tipo': 'predeterminado',
                            'es_cambio': False,
                            'es_doblada': True,
                            'jornada_predeterminada': 'DOBLADA',
                            'coincide_con_predeterminada': True,
                            'turno_id': None,
                            'es_festivo': True,
                        }
                    else:
                        turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                            'jornada': None,
                            'sala': None,
                            'tipo': 'descanso',
                            'es_cambio': False,
                            'es_descanso': True,
                            'jornada_predeterminada': None,
                            'coincide_con_predeterminada': False,
                            'turno_id': None,
                            'es_festivo': True,
                            'descanso_info': {'tipo': 'festivo'},
                        }
                    continue

                # Una cesión COMPLETA aprobada tiene prioridad sobre cualquier Turno residual
                # (el empleado cedió TODO el día aunque queden registros huérfanos). Una cesión
                # PARCIAL, en cambio, deja la otra jornada como Turno real válido: NO se borra,
                # para que Mis Turnos muestre la jornada restante (no "día libre"). La fuente única
                # solo incluye la fecha cuando el día quedó libre COMPLETO (cesión completa o ambas
                # medias jornadas), así que su presencia como 'cedió su jornada' equivale a completa.
                _desc_ced = descansos_sol.get(fecha)
                if _desc_ced and _desc_ced.get('motivo') == 'cedió su jornada' and turnos_dia:
                    turnos_dia = []

                if turnos_dia:
                    # Hay turno(s) asignado(s) (puede ser cambio aprobado o doblada)
                    # OPTIMIZACIÓN: Calcular jornada_display desde turnos_dia sin consultas extra
                    jornadas_turnos = [t.jornada.nombre.upper() for t in turnos_dia if t.jornada]
                    if 'AM' in jornadas_turnos and 'PM' in jornadas_turnos:
                        jornada_display = JornadaDisplay.DOBLADA
                    elif 'AM' in jornadas_turnos:
                        jornada_display = 'AM'
                    elif 'PM' in jornadas_turnos:
                        jornada_display = 'PM'
                    else:
                        jornada_display = calcular_jornada_dia(jornada_base, fecha) or ''

                    jornada_predeterminada = calcular_predeterminado(fecha)

                    # Detectar si es doblada
                    es_doblada = jornada_display == JornadaDisplay.DOBLADA

                    # Determinar tipo de cambio (si todos los turnos tienen el mismo tipo_cambio)
                    tipos_cambio = [t.tipo_cambio for t in turnos_dia if t.tipo_cambio]
                    es_cambio = len(tipos_cambio) > 0
                    tipo_cambio_principal = tipos_cambio[0] if tipos_cambio else None

                    # Determinar sala(s)
                    salas = [t.sala.nombre for t in turnos_dia if t.sala]
                    if len(set(salas)) == 1:
                        # Todas las salas son iguales
                        sala_display = salas[0]
                    else:
                        # Salas diferentes (raro, pero posible)
                        sala_display = ', '.join(set(salas)) if salas else 'Por asignar'

                    coincide_con_predeterminada = jornada_display == jornada_predeterminada if jornada_display else False

                    # Usar el primer turno como referencia (para compatibilidad con código existente)
                    turno_principal = turnos_dia[0]

                    turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                        'jornada': jornada_display,  # Usar jornada_display (puede ser JornadaDisplay.DOBLADA)
                        'sala': sala_display,
                        # 'asignado' solo cuando fue creado por CT/DOBLADA (tipo_cambio != null).
                        # 'predeterminado' cuando el turno existe en BD pero sin tipo_cambio (horario importado).
                        'tipo': 'asignado' if es_cambio else 'predeterminado',
                        'es_cambio': es_cambio,
                        'es_doblada': es_doblada,  # Flag para frontend
                        'tipo_cambio': tipo_cambio_principal,  # p. ej. 'PAGO REPROGRAMADO' (detalle en Mis Turnos)
                        'jornada_predeterminada': jornada_predeterminada,
                        'coincide_con_predeterminada': coincide_con_predeterminada,
                        'turno_id': turno_principal.id
                    }
                else:
                    # No hay turno asignado: descansa por una solicitud aprobada?
                    # FUENTE UNICA (descansos_sol): DOBLADA, D FDS, CAMBIO DESCANSO y DOBLADA PERM.
                    desc = descansos_sol.get(fecha)
                    esta_descansando = desc is not None

                    if esta_descansando:
                        _cmp = desc.get("companero") or {}
                        _tipo = desc.get("tipo")
                        turnos_mes_dict[fecha.strftime("%Y-%m-%d")] = {
                            "jornada": None,
                            "sala": None,
                            "tipo": "descanso",
                            "es_cambio": False,
                            "es_descanso": True,
                            "jornada_predeterminada": calcular_jornada_dia(jornada_base, fecha),
                            "coincide_con_predeterminada": False,
                            "turno_id": None,
                            "descanso_info": {
                                "tipo": _tipo,
                                "origen": desc.get("origen"),
                                "companero_nombre": _cmp.get("nombre"),
                                "companero_id": _cmp.get("id"),
                                "solicitud_id": desc.get("solicitud_id"),
                                "fecha_relacionada": (desc.get("fecha_pago") if _tipo == "cedio" else desc.get("fecha_cesion")),
                                "fecha_cesion": desc.get("fecha_cesion"),
                                "fecha_pago": desc.get("fecha_pago"),
                                "fecha_solicitud": desc.get("fecha_solicitud"),
                                "fecha_aprobacion": desc.get("fecha_aprobacion"),
                                "tipo_cesion": desc.get("tipo_cesion"),
                                "jornada_cedida": desc.get("jornada_cedida"),
                            }
                        }
                    else:
                        # No hay turno asignado: el estado lo resuelve la FUENTE DE VERDAD
                        # única (estado_mes), que ya aplica alternancia de finde, temporada y
                        # mantenimiento en el orden correcto. Antes esta lógica estaba duplicada
                        # aquí; ahora solo se mapea su resultado al formato de la respuesta.
                        est = estados_mes.get(fecha) or {}

                        if est.get('trabaja') and est.get('jornada') == JornadaDisplay.DOBLADA:
                            # Fin de semana que le corresponde trabajar → jornada predeterminada DOBLADA
                            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                                'jornada': 'DOBLADA',
                                'sala': 'Por asignar',
                                'tipo': 'predeterminado',
                                'es_cambio': False,
                                'es_doblada': True,  # Flag para frontend
                                'jornada_predeterminada': 'DOBLADA',
                                'coincide_con_predeterminada': True,
                                'turno_id': None
                            }
                        elif (not est.get('trabaja')) and est.get('fuente') in ('temporada', 'mantenimiento'):
                            # Descanso de ENTRE SEMANA (temporada/mantenimiento)
                            motivo_descanso_semana = 'temporada' if est.get('fuente') == 'temporada' else 'mantenimiento'
                            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                                'jornada': None,
                                'sala': None,
                                'tipo': 'descanso',
                                'es_cambio': False,
                                'es_descanso': True,
                                'jornada_predeterminada': calcular_jornada_dia(jornada_base, fecha),
                                'coincide_con_predeterminada': False,
                                'turno_id': None,
                                'descanso_info': {
                                    'tipo': 'descanso_semana',
                                    'motivo': motivo_descanso_semana,  # 'manual' o 'mantenimiento'
                                },
                            }
                        else:
                            # Día normal (jornada base entre semana) o descanso de fin de semana
                            # (que conserva el comportamiento histórico: jornada = "Descanso").
                            jornada_nombre = calcular_jornada_dia(jornada_base, fecha)

                            sala_nombre = 'Por asignar'
                            if asignaciones_activas:
                                sala_nombre = asignaciones_activas.sala.nombre

                            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                                'jornada': jornada_nombre,
                                'sala': sala_nombre,
                                'tipo': 'predeterminado',
                                'es_cambio': False,
                                'es_descanso': False,
                                'jornada_predeterminada': jornada_nombre,
                                'coincide_con_predeterminada': True,
                                'turno_id': None
                            }

            MisTurnosPorMesView._enriquecer_solicitud_info(turnos_mes_dict, turnos_por_fecha, empleado)
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
    def _enriquecer_solicitud_info(turnos_mes_dict, turnos_por_fecha, empleado):
        # FASE 3.3: Obtener información de solicitudes para turnos con cambios (optimizado)
        # Limitar a las solicitudes más recientes para mejorar rendimiento
        from solicitudes.models import SolicitudCambio
        # CORRECCIÓN: turnos_por_fecha ahora contiene listas de turnos, no turnos individuales
        turno_ids_con_cambio = []
        for turnos_lista in turnos_por_fecha.values():
            for turno in turnos_lista:
                if turno.tipo_cambio is not None:
                    turno_ids_con_cambio.append(turno.id)
        solicitudes_info = {}

        if turno_ids_con_cambio:
            # FASE 3.3: Limitar a las 50 solicitudes más recientes para evitar consultas lentas
            # Obtener todas las solicitudes que afectaron estos turnos
            solicitudes = SolicitudCambio.objects.filter(
                Q(turno_origen_id__in=turno_ids_con_cambio) | Q(turno_destino_id__in=turno_ids_con_cambio),
                estado='aprobada'
            ).select_related('explorador_solicitante', 'explorador_receptor').order_by('-fecha_resolucion', '-id')[:50]

            # Procesar solicitudes en orden descendente (más reciente primero)
            # Para cada turno, solo guardar la primera solicitud encontrada (más reciente)
            for solicitud in solicitudes:
                # Para turno_origen (solicitante)
                if solicitud.turno_origen_id and solicitud.turno_origen_id in turno_ids_con_cambio:
                    if solicitud.turno_origen_id not in solicitudes_info:
                        solicitudes_info[solicitud.turno_origen_id] = {
                            'solicitud_id': solicitud.id,
                            'companero_nombre': solicitud.explorador_receptor.nombre,
                            'rol': 'solicitante',
                            'fecha_resolucion': DateUtils.format_datetime_display(solicitud.fecha_resolucion)
                        }

                # Para turno_destino (receptor)
                if solicitud.turno_destino_id and solicitud.turno_destino_id in turno_ids_con_cambio:
                    if solicitud.turno_destino_id not in solicitudes_info:
                        solicitudes_info[solicitud.turno_destino_id] = {
                            'solicitud_id': solicitud.id,
                            'companero_nombre': solicitud.explorador_solicitante.nombre,
                            'rol': 'receptor',
                            'fecha_resolucion': DateUtils.format_datetime_display(solicitud.fecha_resolucion)
                        }

        # Agregar información de solicitudes a los turnos
        # Para dobladas, buscar en todos los turnos de esa fecha
        for fecha_str, info in turnos_mes_dict.items():
            turno_id = info.get('turno_id')
            solicitud_encontrada = None

            # Si hay turno_id, buscar directamente
            if turno_id and turno_id in solicitudes_info:
                solicitud_encontrada = solicitudes_info[turno_id]
            else:
                # Si no se encontró, puede ser una doblada con múltiples turnos
                # Buscar en todos los turnos de esa fecha
                fecha_obj = DateUtils.parse_date(fecha_str)
                turnos_fecha = turnos_por_fecha.get(fecha_obj, [])
                for turno in turnos_fecha:
                    if turno.id in solicitudes_info:
                        solicitud_encontrada = solicitudes_info[turno.id]
                        break  # Usar la primera encontrada

            info['solicitud_info'] = solicitud_encontrada

        # BÚSQUEDA ADICIONAL PARA DOBLADAS
        # Las dobladas no tienen turno_origen/turno_destino asignados, así que buscamos por fecha y empleado
        # Solo buscar para fechas que aún no tienen solicitud_info y tienen cambios (es_cambio o es_doblada)
        fechas_sin_solicitud = [
            fecha_str for fecha_str, info in turnos_mes_dict.items()
            if not info.get('solicitud_info') and (info.get('es_cambio', False) or info.get('es_doblada', False))
        ]

        if fechas_sin_solicitud:
            # Convertir fechas string a objetos date
            fechas_obj = [DateUtils.parse_date(f) for f in fechas_sin_solicitud]

            # D FDS va junto a DOBLADA en las cuatro consultas: la geometría es la misma (el
            # receptor trabaja la fecha de cesión, el solicitante la de pago), solo cambia la
            # unidad (un día de finde completo en vez de media jornada). Sin esto, un día de
            # doblada de fin de semana no traía compañero y el detalle no podía decir a quién se
            # está cubriendo.
            # IMPORTANTE: Para dobladas, necesitamos buscar en ambos escenarios:
            # 1. Empleado como SOLICITANTE en fecha de cesión (empleado cedió, receptor trabaja)
            # 2. Empleado como RECEPTOR en fecha de cesión (empleado trabaja/dobla, solicitante descansa)
            # 3. Empleado como RECEPTOR en fecha de pago (empleado descansa, solicitante trabaja/dobla)
            # 4. Empleado como SOLICITANTE en fecha de pago (empleado trabaja/dobla, receptor descansa)

            # Buscar donde el empleado es SOLICITANTE y la fecha es de CESIÓN (empleado descansa, receptor trabaja)
            solicitudes_solicitante_cesion = SolicitudCambio.objects.filter(
                explorador_solicitante=empleado,
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                fecha_cambio_turno__in=fechas_obj,
                estado='aprobada'
            ).select_related('explorador_receptor', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')

            # Buscar donde el empleado es RECEPTOR y la fecha es de CESIÓN (empleado trabaja/dobla, solicitante descansa)
            solicitudes_receptor_cesion = SolicitudCambio.objects.filter(
                explorador_receptor=empleado,
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                fecha_cambio_turno__in=fechas_obj,
                estado='aprobada'
            ).select_related('explorador_solicitante', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')

            # Buscar donde el empleado es RECEPTOR y la fecha es de PAGO (empleado descansa, solicitante trabaja/dobla)
            solicitudes_receptor_pago = SolicitudCambio.objects.filter(
                explorador_receptor=empleado,
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                doblada__fecha_pago__in=fechas_obj,
                estado='aprobada'
            ).select_related('explorador_solicitante', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')

            # Buscar donde el empleado es SOLICITANTE y la fecha es de PAGO (empleado trabaja/dobla, receptor descansa)
            solicitudes_solicitante_pago = SolicitudCambio.objects.filter(
                explorador_solicitante=empleado,
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                doblada__fecha_pago__in=fechas_obj,
                estado='aprobada'
            ).select_related('explorador_receptor', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')

            # Crear diccionarios para búsqueda rápida (solo la más reciente por fecha)
            dobladas_dict = {}

            # Solicitudes donde empleado es solicitante en fecha de cesión
            for sol in solicitudes_solicitante_cesion:
                fecha_str = sol.fecha_cambio_turno.strftime('%Y-%m-%d')
                if fecha_str not in dobladas_dict:
                    dobladas_dict[fecha_str] = {
                        'solicitud': sol,
                        'companero': sol.explorador_receptor.nombre,
                        'rol': 'solicitante'
                    }

            # Solicitudes donde empleado es receptor en fecha de cesión
            for sol in solicitudes_receptor_cesion:
                fecha_str = sol.fecha_cambio_turno.strftime('%Y-%m-%d')
                if fecha_str not in dobladas_dict:
                    dobladas_dict[fecha_str] = {
                        'solicitud': sol,
                        'companero': sol.explorador_solicitante.nombre,
                        'rol': 'receptor'
                    }

            # Solicitudes donde empleado es receptor en fecha de pago
            for sol in solicitudes_receptor_pago:
                if sol.doblada and sol.doblada.fecha_pago:
                    fecha_str = sol.doblada.fecha_pago.strftime('%Y-%m-%d')
                    if fecha_str not in dobladas_dict:
                        dobladas_dict[fecha_str] = {
                            'solicitud': sol,
                            'companero': sol.explorador_solicitante.nombre,
                            'rol': 'receptor'
                        }

            # Solicitudes donde empleado es solicitante en fecha de pago
            for sol in solicitudes_solicitante_pago:
                if sol.doblada and sol.doblada.fecha_pago:
                    fecha_str = sol.doblada.fecha_pago.strftime('%Y-%m-%d')
                    if fecha_str not in dobladas_dict:
                        dobladas_dict[fecha_str] = {
                            'solicitud': sol,
                            'companero': sol.explorador_receptor.nombre,
                            'rol': 'solicitante'
                        }

            # CAMBIO DESCANSO (intercambio de día de descanso de temporada): el solicitante
            # trabaja su día completo en fecha_cambio_turno y el receptor en doblada.fecha_pago.
            # Adjuntamos el compañero (mismo dict que las dobladas) para que Mis Turnos muestre
            # "con X" en el día doblado por el intercambio.
            cd_sol = SolicitudCambio.objects.filter(
                explorador_solicitante=empleado, tipo_cambio__nombre='CAMBIO DESCANSO',
                fecha_cambio_turno__in=fechas_obj, estado='aprobada'
            ).select_related('explorador_receptor', 'doblada').order_by('-fecha_resolucion', '-id')
            for sol in cd_sol:
                if sol.fecha_cambio_turno.weekday() >= 5:
                    continue  # el finde tiene otra geometría, se resuelve abajo
                fecha_str = sol.fecha_cambio_turno.strftime('%Y-%m-%d')
                dobladas_dict.setdefault(fecha_str, {
                    'solicitud': sol, 'companero': sol.explorador_receptor.nombre, 'rol': 'solicitante'})

            cd_rec = SolicitudCambio.objects.filter(
                explorador_receptor=empleado, tipo_cambio__nombre='CAMBIO DESCANSO',
                doblada__fecha_pago__in=fechas_obj, estado='aprobada'
            ).select_related('explorador_solicitante', 'doblada').order_by('-fecha_resolucion', '-id')
            for sol in cd_rec:
                if sol.doblada and sol.doblada.fecha_pago and sol.doblada.fecha_pago.weekday() < 5:
                    fecha_str = sol.doblada.fecha_pago.strftime('%Y-%m-%d')
                    dobladas_dict.setdefault(fecha_str, {
                        'solicitud': sol, 'companero': sol.explorador_solicitante.nombre, 'rol': 'receptor'})

            # CAMBIO DESCANSO de FIN DE SEMANA: la geometría es DISTINTA de la de entre semana y
            # las dos consultas de arriba no la describen. En el finde es un TRUEQUE de días
            # (`CambioDescansoAplicacionService.aplicar`):
            #   · el RECEPTOR trabaja la fecha de cesión y la de pago;
            #   · el SOLICITANTE trabaja los días OPUESTOS de esos dos findes (sáb↔dom).
            # Con el mapeo de entre semana, quien trabajaba su sábado por un intercambio salía sin
            # compañero, y el detalle del día no podía decir con quién había cambiado (era el caso
            # de Marco el 15/08: trabajaba por el trueque con jeison y el mensaje no lo nombraba).
            # `otro_dia` es el MISMO helper que usa el aplicador: una sola fuente para sáb↔dom.
            from solicitudes.services.cambio_descanso_aplicacion_service import otro_dia
            fechas_set = set(fechas_obj)
            cd_finde = (SolicitudCambio.objects
                        .filter(tipo_cambio__nombre='CAMBIO DESCANSO', estado='aprobada')
                        .filter(Q(explorador_solicitante=empleado) | Q(explorador_receptor=empleado))
                        .select_related('explorador_solicitante', 'explorador_receptor', 'doblada')
                        .order_by('-fecha_resolucion', '-id'))
            for sol in cd_finde:
                fc = sol.fecha_cambio_turno
                if not fc or fc.weekday() < 5:
                    continue
                fp = sol.doblada.fecha_pago if sol.doblada else None
                es_solicitante = sol.explorador_solicitante_id == empleado.id
                if es_solicitante:
                    dias_que_trabaja = [otro_dia(f) for f in (fc, fp) if f]
                    companero, rol = sol.explorador_receptor, 'solicitante'
                else:
                    dias_que_trabaja = [f for f in (fc, fp) if f]
                    companero, rol = sol.explorador_solicitante, 'receptor'
                for f in dias_que_trabaja:
                    if f in fechas_set:
                        dobladas_dict.setdefault(f.strftime('%Y-%m-%d'), {
                            'solicitud': sol, 'companero': companero.nombre, 'rol': rol})

            # Asociar información de dobladas a los turnos
            for fecha_str in fechas_sin_solicitud:
                if fecha_str not in turnos_mes_dict:
                    continue

                info = turnos_mes_dict[fecha_str]
                if info.get('solicitud_info'):
                    continue  # Ya tiene información

                doblada_info = dobladas_dict.get(fecha_str)
                if doblada_info:
                    sol = doblada_info['solicitud']
                    info['solicitud_info'] = {
                        'solicitud_id': sol.id,
                        'companero_nombre': doblada_info['companero'],
                        'rol': doblada_info['rol'],
                        'fecha_resolucion': DateUtils.format_datetime_display(sol.fecha_resolucion)
                    }

