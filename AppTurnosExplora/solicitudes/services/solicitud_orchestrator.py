"""
SolicitudOrchestrator

Orquesta el flujo completo de creación de una solicitud:
  sanción → restricción médica → parseo → validación → creación.

No contiene lógica HTTP: recibe los datos crudos del POST y devuelve un
`ResultadoSolicitud` (éxito/error, mensaje, código y datos). Quien lo convierte en
`JsonResponse` es la vista — así el alta se puede ejecutar desde un test de
integración o un comando sin fabricar una petición.
Toda la lógica de negocio la delega en Factory/strategies.
"""
import json
import logging

from django.utils import timezone

from core.utils.date_utils import DateUtils
from empleados.models import Empleado

from ..models import TipoSolicitudCambio
from .errores_validacion import ErrorDelCompanero, RequiereCambioTurnoPrevio
from .resultado import ResultadoSolicitud
from .solicitud_factory import SolicitudFactory
from .solicitud_request_parser import SolicitudRequestParser

logger = logging.getLogger(__name__)

# Mensaje generico de los 500: el detalle real va al log, nunca a la respuesta.
_MSG_ERROR_INTERNO = 'Error al procesar la solicitud'

# Ventana del candado anti doble-submit. Ver `_verificar_dedupe`: tiene que durar MÁS que el
# request más lento que protege, o caduca a mitad de la operación y deja de servir.
_DEDUPE_TTL_SEGUNDOS = 30


class _CreacionAbortada(Exception):
    """
    Aborta la creación en lote para que la transacción haga rollback.

    Las strategies devuelven `(None, mensaje)` en vez de lanzar, y un `return` dentro de un
    `atomic()` NO deshace lo ya creado: hace falta una excepción. Lleva el mensaje que verá el
    usuario.
    """


class SolicitudOrchestrator:

    # ------------------------------------------------------------------
    # Checks transversales
    # ------------------------------------------------------------------

    @staticmethod
    def _refrescar_y_sancion(empleado):
        """Refresca la auto-sanción por deuda del empleado y devuelve su sanción activa (o None)."""
        from empleados.sancion_utils import refrescar_y_sancion
        return refrescar_y_sancion(empleado)

    @staticmethod
    def _verificar_dedupe(post, tipo_nombre: str, solicitante) -> ResultadoSolicitud | None:
        """
        Bloquea un reenvío inmediato del MISMO POST (doble-clic, doble-tap, reintento del
        navegador). La clave incluye el contenido del formulario: dos solicitudes distintas
        del mismo empleado y tipo (p. ej. dos CAMBIO DESCANSO con compañeros distintos) no
        chocan entre sí, solo el reenvío idéntico. TTL corto: pasado ese margen, un reenvío
        ya es una acción deliberada del usuario, no un doble-clic.

        EL TTL DEBE SOBREVIVIR AL REQUEST QUE PROTEGE. Estuvo en 10 s, y los flujos que crean
        VARIAS solicitudes (cobertura con 2 compañeros, doblada permanente con N) tardan más
        que eso: con 3 correos síncronos por solicitud se midieron ~13 s con dos compañeros y
        ~19 s con tres. El candado caducaba antes de que terminara el propio request, así que
        dejaba de proteger justo en los casos donde más falta hace — un segundo POST idéntico
        a los 11 s pasaba limpio y creaba el acuerdo por duplicado. 30 s cubre el peor caso
        medido y sigue siendo "inmediato" para el usuario.
        """
        import hashlib

        from core.services.cache_service import CacheService

        datos_relevantes = {k: v for k, v in post.items() if k not in ('csrfmiddlewaretoken',)}
        huella = hashlib.sha256(
            json.dumps(datos_relevantes, sort_keys=True, default=str).encode()
        ).hexdigest()
        clave = f"solreq_dedupe_{solicitante.id}_{tipo_nombre}_{huella}"

        if not CacheService.acquire_lock(clave, ttl=_DEDUPE_TTL_SEGUNDOS):
            return ResultadoSolicitud.error(
                'Ya se está procesando esta solicitud. Espera unos segundos antes de reintentar.',
                status=409, code='duplicate_request')
        return None

    @staticmethod
    def _fechas_objetivo(post, strategy) -> list:
        """Fechas concretas que la solicitud agenda, para comprobar el cierre semanal.

        Se lo pregunta a la estrategia: los tipos cuyo POST no trae las fechas ya resueltas
        (CT PERMANENTE manda un rango + días) las expanden en su `fechas_objetivo`. El resto
        devuelve None y aquí se usan las fechas puntuales del POST.
        """
        propias = strategy.fechas_objetivo(post) if strategy else None
        if propias is not None:
            return propias
        return SolicitudRequestParser.get_fechas_del_post(post)

    @staticmethod
    def _expandir_weekdays_doblada_perm(post, fecha_inicio, fecha_fin) -> list:
        """
        Fechas concretas del rango para el flujo ANTIGUO de doblada permanente (el que manda solo
        días de la semana, sin fechas). Sirve para poder aplicarle el cierre semanal: sin esto no
        había ninguna fecha que comprobar y esa vía se saltaba el cierre entera.
        """
        from datetime import timedelta as _td

        try:
            ini = DateUtils.parse_date(fecha_inicio)
            fin = DateUtils.parse_date(fecha_fin)
        except (ValueError, TypeError):
            return []
        if not ini or not fin or fin < ini:
            return []

        dias = set()
        for campo in ('cesion_dia', 'devolucion_dia'):
            for v in post.getlist(campo):
                if str(v).strip().isdigit():
                    dias.add(int(v))
        if not dias:
            return []

        out, d = [], ini
        while d <= fin:
            if d.weekday() in dias:
                out.append(d)
            d += _td(days=1)
        return out

    @classmethod
    def verificar_cierre(cls, fechas) -> ResultadoSolicitud | None:
        """Cierre semanal: bloquea si alguna fecha objetivo cae en una ventana cerrada habilitada.

        Fail-open deliberado: si la verificación se rompe, se deja pasar la solicitud (romper el
        formulario a todos los exploradores es peor que colar una solicitud fuera de plazo, que el
        supervisor todavía puede rechazar). Se registra en CRITICAL para que el fallo sea visible en
        alertas y no desactive el cierre en silencio.
        """
        try:
            from solicitudes.services.cierre_solicitudes_service import CierreSolicitudesService
            _f, msg = CierreSolicitudesService.validar_fechas([f for f in fechas if f])
            if msg:
                return ResultadoSolicitud.error(msg, status=400, code='cierre_semanal')
        except Exception:
            logger.critical('CIERRE SEMANAL INOPERATIVO: falló la verificación para las fechas %s; '
                            'la solicitud se permite sin validar el cierre.', fechas, exc_info=True)
        return None

    @classmethod
    def verificar_sancion(cls, solicitante) -> ResultadoSolicitud | None:
        """Gestiona la sanción automática y bloquea si el SOLICITANTE está sancionado."""
        sancion = cls._refrescar_y_sancion(solicitante)
        if sancion:
            from empleados.sancion_utils import mensaje_sancion
            return ResultadoSolicitud.error(mensaje_sancion(sancion), status=403, code='sancionado')
        return None

    @classmethod
    def verificar_sancion_receptor(cls, receptor) -> ResultadoSolicitud | None:
        """
        Bloquea si el COMPAÑERO/receptor está sancionado. Un sancionado no puede
        participar en NINGUNA solicitud ni siquiera como compañero: de lo contrario
        bastaría con que otro enviara la solicitud en su nombre para saltarse la sanción.
        """
        sancion = cls._refrescar_y_sancion(receptor)
        if sancion:
            nombre = getattr(receptor, 'nombre', None) or str(receptor)
            return ResultadoSolicitud.error(
                f'El compañero {nombre} está sancionado y no puede participar en la solicitud. '
                'Elige otro compañero o espera a que termine su sanción.',
                status=403, code='sancionado_receptor')
        return None

    # ------------------------------------------ CAMBIO DESCANSO: cobertura con 2 compañeros
    @staticmethod
    def _pago_dos_debe_estar_libre(solicitante, fecha_pago_raw):
        """
        Cobertura de día completo con DOS compañeros: el día de pago tiene que estar libre.

        Ese día se devuelven las DOS medias jornadas (una a cada compañero), o sea que se
        termina trabajando AM+PM. Quien ya tiene media jornada propia solo podría pagarle a
        uno. Devuelve `ResultadoSolicitud` de error, o None si el día está libre.
        """
        from .cambio_descanso_aplicacion_service import CambioDescansoAplicacionService as _App
        try:
            fecha_pago = DateUtils.parse_date(fecha_pago_raw) if fecha_pago_raw else None
        except (ValueError, TypeError):
            fecha_pago = None
        if not fecha_pago:
            return ResultadoSolicitud.error('Elige el día de pago (de la misma semana).',
                                            status=400, code='missing_fields')
        mias = _App._jornadas_actuales(solicitante, fecha_pago)
        if not mias:
            return None
        dia = fecha_pago.strftime('%d/%m/%Y')
        tengo = 'AM+PM (doblada)' if mias >= {'AM', 'PM'} else next(iter(mias))
        # REDACCIÓN ESPEJO del aviso del formulario (`mostrarAvisoDosDiaLibre` en
        # static/js/cambio-turno/solicitar_cambio_descanso.js). El usuario puede llegar aquí
        # por el aviso en pantalla o directo por POST, y leer dos textos distintos para la
        # MISMA regla desorienta. Las tres frases núcleo son idénticas en los dos lados y
        # `test_cobertura_dos_companeros.py` lo verifica; lo único que el formulario añade es
        # el día libre concreto, que aquí no se sugiere porque el servidor no lo consulta.
        return ResultadoSolicitud.error(
            f'Para el día completo el día de pago debe estar LIBRE. '
            f'Ese día le devuelves media jornada a cada compañero (AM a uno y PM al otro), '
            f'o sea que trabajas AM+PM. El {dia} ya trabajas {tengo}, así que solo podrías '
            f'pagarle a uno. Un Cambio de Turno no lo arregla: te dejaría chocando con el otro. '
            f'Elige un día de esa semana en el que estés libre, o pide que te cubran solo la '
            f'AM o solo la PM.',
            status=400, code='validation_error')

    @classmethod
    def _procesar_cobertura_dos(cls, post, tipo_solicitud, solicitante, comentario):
        """
        Cobertura de día completo con DOS compañeros: uno cubre la AM y otro la PM.

        Son dos solicitudes (cada una con su receptor y su propia aprobación), pero solo tienen
        sentido JUNTAS: media cobertura deja al explorador con media jornada suya sin resolver.
        Por eso se validan las dos ANTES de crear nada y se crean dentro de una sola transacción:
        o quedan ambas o ninguna.

        Las dos se validan contra el MISMO estado previo, que es lo correcto: ceden jornadas
        distintas (AM y PM) del mismo día y una solicitud pendiente no altera el estado del día
        (solo lo hace al aprobarse), así que la validación de la PM no depende de que la AM exista.

        Nota: las notificaciones se envían dentro de `crear_solicitud`. Si la creación de la 2ª
        fallara, el rollback deshace ambas filas pero un email ya enviado por la 1ª no se puede
        retirar. Es poco probable —la validación completa ya pasó— y el explorador no queda con
        datos inconsistentes, que es lo que importa.
        """
        from django.db import transaction

        rid1 = post.get('empleado_receptor')
        rid2 = post.get('empleado_receptor_2')
        if not rid1:
            return ResultadoSolicitud.error('Selecciona el compañero que te cubre la jornada AM.',
                              status=400, code='missing_fields')
        if str(rid1) == str(rid2):
            return ResultadoSolicitud.error('Los dos compañeros deben ser personas distintas.',
                              status=400, code='validation_error')
        try:
            receptor_am = Empleado.objects.get(id=rid1)
            receptor_pm = Empleado.objects.get(id=rid2)
        except Empleado.DoesNotExist:
            return ResultadoSolicitud.error('Alguno de los compañeros seleccionados no existe.',
                              status=400, code='validation_error')

        for receptor in (receptor_am, receptor_pm):
            sancion_resp = cls.verificar_sancion_receptor(receptor)
            if sancion_resp:
                return sancion_resp

        # Restricción médica: con AMBOS receptores (el flujo normal solo mira 'empleado_receptor').
        confirmar = str(post.get('confirmar_restriccion', '')).lower() in ('1', 'true', 'si', 'sí')
        fechas = SolicitudRequestParser.get_fechas_del_post(post)
        restriccion = cls.verificar_restriccion(solicitante, {str(rid1), str(rid2)}, fechas, confirmar)
        if restriccion:
            return ResultadoSolicitud.desde_payload(restriccion, status=400)

        # El día de pago tiene que estar LIBRE. Aquí se pagan DOS medias jornadas (la AM a un
        # compañero y la PM al otro) en el MISMO día, así que ese día se termina trabajando
        # AM+PM: solo cabe si no se tenía nada. Con media jornada propia solo se le podría
        # pagar a uno, y el otro se quedaría cubriendo gratis.
        #
        # La validación por solicitud ya lo rechaza (choca la jornada que coincide), pero su
        # mensaje manda a hacer un Cambio de Turno, que aquí NO resuelve nada: girar la jornada
        # propia solo traslada el choque al otro compañero. Por eso el par se corta antes, con
        # el motivo real.
        error_pago = cls._pago_dos_debe_estar_libre(solicitante, post.get('fecha_pago'))
        if error_pago:
            return error_pago

        def _datos(receptor, jornada):
            return {
                'explorador_solicitante': solicitante,
                'explorador_receptor': receptor,
                'tipo_cambio': tipo_solicitud,
                'comentario': comentario,
                'fecha_cambio_turno': post.get('fecha_solicitud'),
                'fecha_pago': post.get('fecha_pago'),
                'submodalidad_semana': 'cobertura_misma_semana',
                'tipo_cesion': f'cesion_parcial_{jornada.lower()}',
                'jornada_cedida': jornada,
                'jornada_cubre_en_pago': None,
                'fecha_creacion_solicitud': timezone.localdate(),
            }

        datos_am = _datos(receptor_am, 'AM')
        datos_pm = _datos(receptor_pm, 'PM')

        class _FalloParcial(Exception):
            pass

        # Un solo lote de correo para las DOS solicitudes: seis correos por una única
        # conexión SMTP en vez de seis saludos. El grupo se abre POR FUERA del atomic a
        # propósito — al cerrarse es cuando se intenta la entrega, y hacerlo dentro
        # devolvería el SMTP al interior de la transacción, que es justo de donde se sacó.
        # Si la transacción revierte, el rollback se lleva las filas del outbox y el lote
        # se queda vacío solo.
        from .email_outbox_service import EmailOutboxService

        try:
            with EmailOutboxService.envio_agrupado():
                # Validar las DOS antes de crear ninguna. Dentro del try: un fallo INESPERADO de la
                # validación (ya no se disfraza de rechazo de negocio) debe salir como 500 logueado.
                for datos, etiqueta in ((datos_am, 'AM'), (datos_pm, 'PM')):
                    es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_solicitud, datos)
                    if not es_valida:
                        return cls._respuesta_error_validacion(f'Jornada {etiqueta}: {mensaje}')

                with transaction.atomic():
                    creadas = []
                    for datos, etiqueta in ((datos_am, 'AM'), (datos_pm, 'PM')):
                        solicitud, mensaje = SolicitudFactory.crear_solicitud(tipo_solicitud, datos)
                        if solicitud is None:
                            raise _FalloParcial(f'Jornada {etiqueta}: {mensaje}')
                        creadas.append(solicitud)
        except _FalloParcial as e:
            logger.warning('Cobertura con 2 compañeros revertida (solicitante=%s): %s',
                           solicitante.id, e)
            return ResultadoSolicitud.error(
                f'No se pudo crear la cobertura completa, no se creó ninguna solicitud. {e}',
                status=400, code='creation_failed')
        except Exception:
            logger.exception('Error creando cobertura con 2 compañeros (solicitante=%s)', solicitante.id)
            return ResultadoSolicitud.error(_MSG_ERROR_INTERNO, status=500, code='internal_error')

        logger.info('Cobertura con 2 compañeros creada — solicitudes %s solicitante=%s',
                    [s.id for s in creadas], solicitante.id)
        return ResultadoSolicitud.exito({
            'message': 'Se crearon las 2 solicitudes de cobertura (AM y PM). '
                       'Cada compañero la aprueba por separado.',
            'solicitud_ids': [s.id for s in creadas],
        }, status=201)

    @staticmethod
    def verificar_restriccion(solicitante, receptor_ids: set, fechas: list, confirmar: bool) -> dict | None:
        """
        Verifica restricciones médicas activas sobre los exploradores involucrados.
        Retorna el payload de advertencia o None si no hay restricciones.
        """
        if confirmar or not fechas:
            return None

        from django.db.models import Q

        from empleados.models import RestriccionEmpleado

        fmin, fmax = min(fechas), max(fechas)
        vistos = {solicitante.id}
        emps = [solicitante]
        for rid in receptor_ids:
            try:
                emp = Empleado.objects.get(id=rid)
                if emp.id not in vistos:
                    emps.append(emp)
                    vistos.add(emp.id)
            except Empleado.DoesNotExist:
                # Se sigue adelante con los receptores que SÍ existen (comportamiento
                # original), pero deja de ser invisible: que el formulario mande un id
                # inexistente significa o un catálogo desincronizado o una petición
                # manipulada, y hasta ahora la solicitud se creaba con menos compañeros
                # de los que el usuario eligió sin que nadie se enterara.
                logger.warning('Receptor id=%s no existe; se omite de la solicitud de %s',
                               rid, getattr(solicitante, 'id', '?'))

        advertencias = []
        for emp in emps:
            qs = RestriccionEmpleado.objects.filter(
                empleado=emp, fecha_inicio__lte=fmax,
            ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fmin))
            for r in qs:
                advertencias.append({
                    'explorador': f"{emp.nombre} {emp.apellido}",
                    'tipo': r.tipo_restriccion or 'Restricción',
                    'nota': r.recomendacion or '—',
                })

        if advertencias:
            return {
                'success': False,
                'code': 'advertencia_restriccion',
                'message': 'Hay una restricción médica vigente en las fechas. Revisa la nota antes de continuar.',
                'restricciones': advertencias,
            }
        return None

    # ------------------------------------------------------------------
    # Manejo de errores de validación
    # ------------------------------------------------------------------

    @staticmethod
    def _respuesta_error_validacion(mensaje: str) -> ResultadoSolicitud:
        """
        Convierte el mensaje de error del Factory en la respuesta JSON adecuada.
        Maneja el caso especial de 'requiere_cambio_turno_previo'.

        Antes esto intentaba `json.loads` sobre CUALQUIER mensaje y descartaba el
        fallo, porque el dato extra viajaba como un JSON metido dentro del texto.
        Ahora el mensaje llega tipado y basta reconocerlo: las claves del cuerpo se
        escriben en `RequiereCambioTurnoPrevio.como_payload()` y en ningún otro sitio.
        """
        if isinstance(mensaje, RequiereCambioTurnoPrevio):
            return ResultadoSolicitud.desde_payload(mensaje.como_payload(), status=400)
        return ResultadoSolicitud.error(mensaje, status=400, code='validation_error')

    # ------------------------------------------------------------------
    # DOBLADA PERMANENTE (flujo multi-compañero independiente)
    # ------------------------------------------------------------------

    @classmethod
    def _procesar_doblada_permanente_multi(cls, post, tipo_solicitud, solicitante, comentario) -> ResultadoSolicitud:
        """
        DOBLADA PERMANENTE con varios compañeros: agrupa días por compañero
        y crea una solicitud independiente por cada uno. Valida todo antes de crear ninguna.
        """
        if not comentario or not comentario.strip():
            return ResultadoSolicitud.error('Ingresa un comentario.', status=400, code='missing_fields')

        from .doblada_permanente_plan import construir_plan, error_de_balance

        fecha_inicio = post.get('fecha_inicio')
        fecha_fin = post.get('fecha_fin')

        # Parseo del formulario y choques ENTRE companeros (una fecha en dos manos, o el
        # mismo dia como cesion y como devolucion). Vive en `doblada_permanente_plan`
        # porque es aritmetica sobre listas: no toca la base de datos y se prueba sola.
        plan, error = construir_plan(post)
        if error:
            return error
        usa_fechas = plan.usa_fechas

        # Cierre semanal: ninguna fecha de cesión/devolución puede caer en una ventana cerrada.
        # Si la solicitud llega por el flujo antiguo (solo días de la semana, sin fechas), hay que
        # EXPANDIR el rango para tener fechas que comprobar; si no, la lista iba vacía y el cierre
        # no se validaba en absoluto por esa vía.
        # FALLA CERRADO (patrón #25 de PROTECTION_PATTERNS.md). Antes, una fecha que no
        # parseaba se CAÍA de `_cierre_fechas` en silencio: el cierre semanal no la
        # comprobaba y podía colarse una solicitud sobre una ventana cerrada.
        #
        # Auditado antes de cerrarlo: `solicitar_doblada_permanente.js:586` solo envía el
        # `value` de los checkboxes marcados —fechas ISO que genera el propio servidor—, así
        # que ningún envío legítimo trae aquí una cadena vacía ni un valor corrupto. Lo único
        # que se empieza a rechazar es un POST malformado, que es justo lo que debe rechazarse.
        #
        # El bucle solo corre en el flujo por fechas: en el antiguo (por weekday) el resultado
        # se descartaba y se recalculaba, así que parsear allí era trabajo tirado.
        _cierre_fechas = []
        if usa_fechas:
            for _s in plan.fechas_iso:
                try:
                    _cierre_fechas.append(DateUtils.parse_date(_s))
                except (ValueError, TypeError):
                    logger.warning(
                        'Fecha no parseable (%r) en la doblada permanente: se RECHAZA la '
                        'solicitud (no se puede comprobar la ventana de cierre)', _s)
                    return ResultadoSolicitud.error(
                        'Una de las fechas seleccionadas no es válida, así que no se puede '
                        'comprobar si cae en una semana cerrada. Vuelve a marcar las fechas.',
                        status=400, code='validation_error')
        else:
            _cierre_fechas = cls._expandir_weekdays_doblada_perm(post, fecha_inicio, fecha_fin)
        cierre_resp = cls.verificar_cierre(_cierre_fechas)
        if cierre_resp:
            return cierre_resp

        # Las cuentas del acuerdo. Va DESPUES del cierre, igual que antes de la
        # extraccion: adelantarlo cambiaria que error ve quien tiene las dos cosas mal.
        error = error_de_balance(plan)
        if error:
            return error
        cesion_por_comp = plan.cesion_por_comp

        # Verificar restricción médica sobre el rango completo
        confirmar = str(post.get('confirmar_restriccion', '')).lower() in ('1', 'true', 'si', 'sí')
        try:
            fechas_rango = [
                DateUtils.parse_date(fecha_inicio),
                DateUtils.parse_date(fecha_fin),
            ]
        except (ValueError, TypeError):
            fechas_rango = []

        restriccion = cls.verificar_restriccion(
            solicitante, set(cesion_por_comp.keys()), fechas_rango, confirmar,
        )
        if restriccion:
            restriccion['message'] = 'Hay una restricción médica vigente en el rango. Revisa la nota antes de continuar.'
            return ResultadoSolicitud.desde_payload(restriccion, status=400)

        # Validar TODAS antes de crear ninguna (todo o nada)
        pendientes = []
        for comp_id, dias_c in cesion_por_comp.items():
            try:
                receptor = Empleado.objects.get(id=comp_id)
            except Empleado.DoesNotExist:
                return ResultadoSolicitud.error('Compañero no válido.', status=400, code='validation_error')

            # Sanción del compañero: un sancionado no puede participar en la doblada.
            sancion_receptor_resp = cls.verificar_sancion_receptor(receptor)
            if sancion_receptor_resp:
                return sancion_receptor_resp

            datos = {
                'explorador_solicitante': solicitante,
                'explorador_receptor': receptor,
                'tipo_cambio': tipo_solicitud,
                'comentario': comentario,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'dias_cesion': sorted(dias_c),
                'dias_devolucion': sorted(plan.devol_por_comp.get(comp_id, set())),
                'fechas_cesion': sorted(plan.cesion_fechas_por_comp.get(comp_id, set())) if usa_fechas else [],
                'fechas_devolucion': sorted(plan.devol_fechas_por_comp.get(comp_id, set())) if usa_fechas else [],
                'fecha_creacion_solicitud': timezone.localdate(),
            }
            es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_solicitud, datos)
            if not es_valida:
                # El nombre del compañero se antepone SOLO a lo que habla de él.
                #
                # Antes se le ponía a todos los rechazos, y eso mentía: "Ya tienes una
                # solicitud pendiente" —que habla de quien envía— llegaba como
                # "Isabel Parra: Ya tienes una solicitud pendiente", así que el usuario
                # iba a cancelar la solicitud de Isabel a buscar un choque que era suyo.
                # Quien valida marca con `ErrorDelCompanero` las frases que son del
                # compañero; no se adivina leyendo el texto.
                #
                # A `RequiereCambioTurnoPrevio` tampoco se le antepone: se envía tal cual
                # para que conserve sus datos y el formulario pueda pintar su recuadro
                # (concatenar produciría un `str` normal y perdería los atributos).
                if isinstance(mensaje, ErrorDelCompanero):
                    mensaje = f"{receptor.nombre} {receptor.apellido}: {mensaje}"
                return cls._respuesta_error_validacion(mensaje)
            pendientes.append((receptor, datos))

        # Crear todas, TODO O NADA. El acuerdo con varios compañeros solo tiene sentido completo:
        # si la segunda falla, la primera no puede quedarse viva (el usuario vería un error y aun
        # así tendría media doblada pendiente). Antes el bucle no estaba en transacción.
        #
        # El `envio_agrupado` de fuera hace dos cosas, y la segunda no es solo rendimiento:
        #   - Los 3 correos de CADA solicitud —y los de todas las del bucle— salen por UNA
        #     conexión SMTP. Con tres compañeros son 9 correos: nueve saludos TLS+AUTH
        #     (~2 s cada uno) pasan a ser uno.
        #   - Nada se envía hasta que el bloque termina, YA COMMITADO. Eso cierra el agujero
        #     que describía este comentario: si la segunda solicitud falla, el rollback se
        #     lleva también las filas del outbox y el correo de la primera no llega a salir
        #     — antes ya se había "desenviado" imposible.
        # Va por fuera del atomic para que la entrega no ocurra con la transacción abierta.
        from django.db import transaction as _tx

        from .email_outbox_service import EmailOutboxService

        creadas = 0
        try:
            with EmailOutboxService.envio_agrupado():
                with _tx.atomic():
                    for receptor, datos in pendientes:
                        solicitud, mensaje = SolicitudFactory.crear_solicitud(tipo_solicitud, datos)
                        if solicitud is None:
                            raise _CreacionAbortada(
                                f"Error creando la solicitud para {receptor.nombre}: {mensaje}")
                        creadas += 1
        except _CreacionAbortada as exc:
            return ResultadoSolicitud.error(str(exc), status=400, code='creation_failed')

        msg = (
            'Doblada permanente solicitada. Se notificó al compañero y al supervisor.'
            if creadas == 1 else
            f'Se crearon {creadas} solicitudes de doblada permanente (una por compañero). '
            f'Se notificó a cada uno y al supervisor.'
        )
        return ResultadoSolicitud.exito({'message': msg, 'solicitudes_creadas': creadas}, status=201)

    # ------------------------------------------------------------------
    # Punto de entrada principal
    # ------------------------------------------------------------------

    #: Flujos de creación propios, por el nombre que declara cada estrategia en
    #: `flujo_creacion_propio`. Registro en vez de `if tipo_nombre == ...`: un tipo nuevo con
    #: flujo propio se añade aquí y en su estrategia, sin tocar `procesar()`.
    _FLUJOS_PROPIOS = {
        'doblada_permanente_multi': '_procesar_doblada_permanente_multi',
        'cobertura_dos': '_procesar_cobertura_dos',
    }

    @classmethod
    def _flujo_propio(cls, strategy, post):
        """El flujo de creación propio que pide la estrategia, ya resuelto a método, o None."""
        nombre = strategy.flujo_creacion_propio(post) if strategy else None
        if not nombre:
            return None
        metodo = cls._FLUJOS_PROPIOS.get(nombre)
        if not metodo:
            logger.error("Estrategia %s pide el flujo '%s', que no está registrado en "
                         "_FLUJOS_PROPIOS", type(strategy).__name__, nombre)
            return None
        return getattr(cls, metodo)

    @classmethod
    def procesar(cls, post, tipo_solicitud: TipoSolicitudCambio, solicitante) -> ResultadoSolicitud:
        """
        Flujo principal de creación de solicitud:
          1. Verificar sanción
          2. Despachar el flujo propio que declare la estrategia (si comprueba el cierre él mismo)
          3. Verificar cierre semanal y restricción médica
          4. Resolver receptor
          5. Parsear datos según tipo
          6. Validar con Factory
          7. Crear con Factory
        """
        tipo_nombre = tipo_solicitud.nombre
        comentario = post.get('comentarios', '')
        strategy = SolicitudFactory.get_strategy(tipo_solicitud)

        # 0. Dedupe de doble-clic/doble-submit: un POST idéntico (mismo solicitante, tipo
        # y datos) que llega dos veces en un margen de segundos no debe crear dos solicitudes
        # — cada una dispararía sus propias notificaciones/emails, y si ambas se aprobaran
        # generaría un segundo "última aprobada gana" espurio. `acquire_lock` es atómico
        # (cache.add), así que entre dos requests concurrentes solo uno pasa.
        dedupe_resp = cls._verificar_dedupe(post, tipo_nombre, solicitante)
        if dedupe_resp:
            return dedupe_resp

        # 1. Sanción
        sancion_resp = cls.verificar_sancion(solicitante)
        if sancion_resp:
            return sancion_resp

        # 2. Flujo de creación propio, si la estrategia declara uno (doblada permanente
        # multi-compañero, cobertura de día completo con dos…). Los que comprueban el cierre
        # por su cuenta van ANTES del chequeo genérico, porque calculan sus propias fechas.
        flujo_propio = cls._flujo_propio(strategy, post)
        if flujo_propio and strategy.flujo_propio_verifica_cierre:
            # Con try/except propio: estos flujos validan dentro de un bucle por compañero y no
            # tenían manejo genérico. Ahora que la validación propaga los fallos inesperados en
            # vez de devolverlos como rechazo de negocio, hace falta convertirlos aquí en un 500
            # logueado en lugar de dejar escapar un traceback sin controlar.
            try:
                return flujo_propio(post, tipo_solicitud, solicitante, comentario)
            except Exception:
                logger.exception('Error procesando el flujo propio de %s — solicitante=%s',
                                 tipo_nombre, solicitante.id)
                return ResultadoSolicitud.error(_MSG_ERROR_INTERNO, status=500,
                                  code='internal_error')

        # 2b. Cierre semanal (programación del fin de semana ya cerrada)
        cierre_resp = cls.verificar_cierre(cls._fechas_objetivo(post, strategy))
        if cierre_resp:
            return cierre_resp

        # 2c. El resto de flujos propios, ya con el cierre comprobado.
        if flujo_propio:
            return flujo_propio(post, tipo_solicitud, solicitante, comentario)

        # 3. Restricción médica
        confirmar = str(post.get('confirmar_restriccion', '')).lower() in ('1', 'true', 'si', 'sí')
        fechas = SolicitudRequestParser.get_fechas_del_post(post)
        receptor_ids = {v for c in ['empleado_receptor'] if (v := post.get(c))}
        restriccion = cls.verificar_restriccion(solicitante, receptor_ids, fechas, confirmar)
        if restriccion:
            return ResultadoSolicitud.desde_payload(restriccion, status=400)

        # 4. Resolver receptor
        receptor_id = post.get('empleado_receptor')
        if not receptor_id:
            return ResultadoSolicitud.error('Debe seleccionar un compañero para el intercambio',
                              status=400, code='missing_fields')
        try:
            receptor = Empleado.objects.get(id=receptor_id)
        except Empleado.DoesNotExist:
            return ResultadoSolicitud.error('El compañero seleccionado no existe.', status=400, code='validation_error')

        # 4b. Sanción del receptor: un sancionado no puede participar ni como compañero.
        sancion_receptor_resp = cls.verificar_sancion_receptor(receptor)
        if sancion_receptor_resp:
            return sancion_receptor_resp

        # 5. Parsear datos
        datos = SolicitudRequestParser.parse_datos(tipo_nombre, post, solicitante, receptor)
        datos['tipo_cambio'] = tipo_solicitud

        # 6 y 7. Validar y crear.
        # La validación va DENTRO del try: ahora que las estrategias propagan los fallos
        # inesperados en vez de disfrazarlos de rechazo de validación, un bug aquí debe salir
        # como 500 'internal_error' logueado — visible y accionable— y no como un traceback
        # sin controlar ni, peor, como un mensaje que el usuario lee como "mi solicitud está mal".
        try:
            es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_solicitud, datos)
            if not es_valida:
                return cls._respuesta_error_validacion(mensaje)

            solicitud, mensaje = SolicitudFactory.crear_solicitud(tipo_solicitud, datos)
            if solicitud is None:
                return ResultadoSolicitud.error(mensaje, status=400, code='creation_failed')
            logger.info("Solicitud %d creada — tipo=%s solicitante=%s receptor=%s",
                        solicitud.id, tipo_nombre, solicitante.id, receptor.id)
            return ResultadoSolicitud.exito({
                'message': 'Solicitud enviada correctamente. Se han enviado notificaciones al supervisor y al compañero.',
                'solicitud_id': solicitud.id,
            }, status=201)
        except Exception:
            logger.exception("Error validando o creando solicitud — tipo=%s solicitante=%s",
                             tipo_nombre, solicitante.id)
            return ResultadoSolicitud.error(_MSG_ERROR_INTERNO, status=500, code='internal_error')
