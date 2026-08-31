"""
Doblada Permanente Strategy.

Doblada recurrente en días fijos de la semana dentro de un rango, con mutuo
acuerdo: el receptor cubre los días de cesión del solicitante y el solicitante
devuelve el favor doblándose en los días de devolución. Misma regla de negocio
que la doblada (jornadas contrarias, sin domingos ni festivos), pero recurrente.
"""
import logging
from typing import Any, Dict, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction

logger = logging.getLogger(__name__)

from django.utils import timezone

from core.utils.date_utils import DateUtils
from empleados.models import Empleado
from solicitudes.models import DobladaPermanenteDetalle, SolicitudCambio

from .base_strategy import SolicitudStrategy


def _csv(dias):
    """Normaliza una lista o csv de días a 'a,b,c' (enteros 0..6)."""
    if isinstance(dias, (list, tuple)):
        vals = dias
    else:
        vals = str(dias or '').split(',')
    out = [str(int(v)) for v in vals if str(v).strip().isdigit()]
    return ','.join(out)


def _set(dias_str):
    return {int(x) for x in (dias_str or '').split(',') if str(x).strip().isdigit()}


def _csv_fechas(fechas):
    """Normaliza una lista o csv de fechas ISO a 'YYYY-MM-DD,...' (descarta las mal formadas)."""
    from datetime import datetime as _d
    vals = fechas if isinstance(fechas, (list, tuple)) else str(fechas or '').split(',')
    out = []
    for v in vals:
        s = str(v).strip()
        try:
            _d.strptime(s, '%Y-%m-%d')
            out.append(s)
        except ValueError:
            continue
    return ','.join(out)


def _fechas_set(fechas):
    """Convierte una lista/csv de fechas ISO en un set de `date` (descarta las mal formadas)."""
    from datetime import date as _date
    return {_date.fromisoformat(s) for s in _csv_fechas(fechas).split(',') if s}


class DobladaPermanenteStrategy(SolicitudStrategy):

    def __init__(self):
        super().__init__("DOBLADA PERMANENTE")

    @staticmethod
    def _parse(fecha):
        if not fecha:
            return None
        if isinstance(fecha, str):
            try:
                return DateUtils.parse_date(fecha)
            except ValueError:
                return None
        return fecha

    # NOTA: aquí vivía `_grupo_base` (grupo AM/PM por asignación). La elegibilidad de este
    # formulario se decide día a día con la jornada REAL (`jornada_doblada_perm` sobre
    # `estado_dia`), que además exige que sean contrarias, así que dejó de usarse.

    def _datos_desde_solicitud(self, solicitud):
        """Reconstruye los datos para re-validar al aprobar (ver base)."""
        det = getattr(solicitud, 'doblada_permanente', None)
        if not det:
            return None
        return {
            'explorador_solicitante': solicitud.explorador_solicitante,
            'explorador_receptor': solicitud.explorador_receptor,
            'tipo_cambio': solicitud.tipo_cambio,
            'comentario': solicitud.comentario or '',
            'fecha_inicio': det.fecha_inicio.strftime('%Y-%m-%d'),
            'fecha_fin': det.fecha_fin.strftime('%Y-%m-%d') if det.fecha_fin else None,
            'dias_cesion': det.dias_cesion,
            'dias_devolucion': det.dias_devolucion,
            'fechas_cesion': getattr(det, 'fechas_cesion', '') or '',
            'fechas_devolucion': getattr(det, 'fechas_devolucion', '') or '',
        }

    # --------------------------------------------------------------- validación
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            from ..solicitud_validator import SolicitudValidator

            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            fi = self._parse(datos.get('fecha_inicio'))
            ff = self._parse(datos.get('fecha_fin'))
            dias_cesion = _set(_csv(datos.get('dias_cesion')))
            dias_devolucion = _set(_csv(datos.get('dias_devolucion')))
            comentario = datos.get('comentario') or ''

            if not solicitante:
                return False, "Explorador solicitante es requerido"
            if not receptor:
                return False, "Debe seleccionar el compañero que cubrirá la doblada"
            if not fi or not ff:
                return False, "El rango de fechas (inicio y fin) es obligatorio"
            if not dias_cesion:
                return False, "Selecciona al menos un día de la semana que cedes"
            if not dias_devolucion:
                return False, "Selecciona al menos un día de la semana en que devolverás la doblada"

            from ..errores_validacion import ErrorDelCompanero

            SolicitudValidator.validar_empleado_activo(solicitante)
            try:
                SolicitudValidator.validar_empleado_activo(receptor)
            except ValidationError as e:
                # Se marca como del COMPAÑERO: 'El empleado no está activo' no dice cuál, y en el
                # alta multi-compañero el nombre es lo único que lo identifica.
                return False, ErrorDelCompanero(str(e))
            SolicitudValidator.validar_no_mismo_empleado(solicitante, receptor)
            SolicitudValidator.validar_comentario_obligatorio(comentario, 'la solicitud de doblada permanente')

            # (Los DUPLICADOS pendientes se comprueban más abajo, cuando ya se sabe qué fechas
            #  concretas tocaría el acuerdo: mirar solo `fecha_inicio` dejaba fuera todo el resto
            #  del rango.)

            # Rango válido y no pasado
            from django.utils import timezone
            hoy = timezone.localdate()
            if ff < fi:
                return False, "La fecha de fin debe ser posterior a la fecha de inicio"
            if fi < hoy:
                return False, "El rango no puede iniciar en el pasado"

            # Tope del rango: el MISMO que CT PERMANENTE (un año).
            #
            # La doblada permanente ya no está limitada a un solo mes: un acuerdo de enero a junio
            # es legítimo y el resto del flujo (aplicación, deuda de 30 min por fecha, agrupación
            # mensual en PDH y sanción por mes vencido) ya trabaja por fecha, no por mes. Pero
            # acotado: un acuerdo recurrente de más de un año no tiene sentido operativo, y el
            # preview evalúa el rango día a día para DOS exploradores.
            #
            # Se REUTILIZA la constante del validador de CT permanente en vez de duplicar el número:
            # es la misma regla de negocio y debe tener un solo sitio donde cambiarla.
            #
            # Solo al CREAR. Al re-validar para aprobar, el rango es un hecho consumado y volver a
            # medirlo solo podría tumbar una aprobación legítima —mismo criterio que
            # `CTPermanenteValidator.validar_fechas_cambio_permanente(es_revalidacion=True)`—.
            if not datos.get('solicitud_actual_id') and not datos.get('es_revalidacion'):
                from ..validators.ct_permanente_validator import MAX_DIAS_RANGO_PERMANENTE
                dias_rango = (ff - fi).days + 1
                if dias_rango > MAX_DIAS_RANGO_PERMANENTE:
                    return False, (
                        f"El rango no puede superar {MAX_DIAS_RANGO_PERMANENTE} días (un año). "
                        f"Has seleccionado {dias_rango}. Ajusta la fecha de fin."
                    )

            # Sanción: NO bloquea la solicitud, se OMITEN sus días.
            #
            # Antes bastaba una sanción que rozara el rango para rechazarlo entero. Con rangos de
            # un mes se notaba poco; con enero-junio es inaceptable: quien cierra enero debiendo
            # cumple 15 días de sanción —que empiezan DESPUÉS del vencimiento, ya en febrero— y eso
            # tumbaba los seis meses. La sanción castiga su ventana, no el acuerdo completo.
            #
            # Ahora es un motivo de exclusión POR FECHA, como el festivo o el descanso: se saltan
            # los días de la ventana punitiva (`SancionEmpleado.fecha_inicio..fecha_fin_efectiva`) y
            # el resto del rango se aplica. La política vive en `_dias_sancionados`, dentro del
            # servicio de aplicación, que es la fuente ÚNICA que usan validación, preview,
            # disponibilidad y aplicación. Si al final no queda ningún día válido en alguno de los
            # dos lados, se rechaza más abajo por falta de días —igual que CT permanente—.
            #
            # Esto NO toca el bloqueo transversal de formularios: mientras la sanción esté vigente,
            # el explorador sigue sin poder abrir solicitudes ni permisos hasta su fecha de fin.
            # NOTA: la restricción médica tampoco bloquea; se avisa como advertencia en el
            # procesamiento (ver vista).
            from django.db.models import Q as _Q

            # Solo lunes a viernes: la doblada permanente es RECURRENTE y los fines de semana se
            # rigen por alternancia (un sábado de media jornada es una excepción puntual, no
            # permanente). Para intercambiar un sábado puntual se usa Doblada de Fin de Semana.
            if (dias_cesion | dias_devolucion) & {5, 6}:
                return False, ("La doblada permanente es solo de lunes a viernes (no aplica fines de "
                               "semana). Para intercambiar un sábado usa una Doblada de Fin de Semana.")

            # Cesión y devolución no pueden compartir día de la semana (mismo día: descansar y doblar a la vez)
            interseccion = dias_cesion & dias_devolucion
            if interseccion:
                return False, ("Un mismo día de la semana no puede ser de cesión y de devolución a la vez. "
                               "Revisa los días seleccionados.")

            # Balance: a cada compañero le devuelves la misma cantidad de jornadas que te cubrió.
            # Si vienen FECHAS específicas se cuentan las fechas (permite balancear cuando los
            # weekdays tienen distinto número de ocurrencias); si no, se cuentan los weekdays.
            fechas_cesion = [f for f in _csv_fechas(datos.get('fechas_cesion')).split(',') if f]
            fechas_devolucion = [f for f in _csv_fechas(datos.get('fechas_devolucion')).split(',') if f]
            if fechas_cesion or fechas_devolucion:
                if len(fechas_cesion) != len(fechas_devolucion):
                    return False, (
                        f"Debes devolver la misma cantidad de fechas que te cubren: te cubren "
                        f"{len(fechas_cesion)} y estás devolviendo {len(fechas_devolucion)}. Ajústalas para que queden iguales."
                    )
            elif len(dias_cesion) != len(dias_devolucion):
                return False, (
                    f"Debes devolver la misma cantidad de días que te cubren: te cubren {len(dias_cesion)} "
                    f"día(s) y estás devolviendo {len(dias_devolucion)}. Ajusta los días para que queden iguales."
                )

            # El compañero no puede tener YA otra doblada permanente (pendiente o aprobada) que
            # solape el rango y comparta días: quedaría doblemente comprometido.
            from solicitudes.models import DobladaPermanenteDetalle
            dias_acuerdo = dias_cesion | dias_devolucion
            otros = (
                DobladaPermanenteDetalle.objects
                .filter(solicitud__estado__in=['pendiente', 'aprobada'],
                        fecha_inicio__lte=ff, fecha_fin__gte=fi)
                .filter(_Q(solicitud__explorador_receptor=receptor) | _Q(solicitud__explorador_solicitante=receptor))
                .select_related('solicitud')
            )
            # Al re-validar para aprobar, excluir la PROPIA solicitud (no solapa consigo misma).
            _excluir = datos.get('solicitud_actual_id')
            if _excluir:
                otros = otros.exclude(solicitud_id=_excluir)
            # El choque se mide por FECHA, no por día de la semana: dos acuerdos pueden usar el
            # mismo weekday dentro de rangos que se solapan y no tocar ni una fecha en común
            # (p. ej. uno los miércoles 9 y 16, otro los miércoles 2, 23 y 30). Comparar weekdays
            # rechazaba esos casos aunque el formulario los dejara armar y `aplicar` los aceptara.
            # Se comparan las dos partes en bloque (cesión ∪ devolución) porque el conflicto es de
            # DISPONIBILIDAD: en una fecha ya comprometida da igual el rol, el compañero no puede
            # doblarse ni descansar dos veces.
            # Solo se cae al chequeo por weekday cuando faltan las fechas concretas (acuerdos
            # legacy anteriores a `fechas_cesion`/`fechas_devolucion`).
            fechas_acuerdo = _fechas_set(datos.get('fechas_cesion')) | _fechas_set(datos.get('fechas_devolucion'))
            for det in otros:
                dias_otro = _set(det.dias_cesion) | _set(det.dias_devolucion)
                fechas_otro = _fechas_set(getattr(det, 'fechas_cesion', '')) | _fechas_set(
                    getattr(det, 'fechas_devolucion', ''))

                if fechas_acuerdo and fechas_otro:
                    choque = fechas_acuerdo & fechas_otro
                elif fechas_acuerdo:
                    # El otro acuerdo es legacy: sus fechas reales son las ocurrencias de sus
                    # weekdays dentro de SU rango.
                    choque = {f for f in fechas_acuerdo
                              if det.fecha_inicio <= f <= det.fecha_fin and f.weekday() in dias_otro}
                else:
                    # Este acuerdo viene sin fechas (legacy): no hay más que weekdays que cruzar.
                    choque = None
                    if not (dias_acuerdo & dias_otro):
                        continue

                if choque is not None and not choque:
                    continue

                detalle = ''
                if choque:
                    detalle = ' (' + ', '.join(f.strftime('%d/%m/%Y') for f in sorted(choque)) + ')'
                return False, (
                    f"{receptor.nombre} {receptor.apellido} ya tiene una doblada permanente en esas "
                    f"fechas{detalle}. Elige otras fechas u otro compañero."
                )

            # ===========================
            # Jornadas contrarias por FECHA REAL (no por la base): OMITIR los días inválidos.
            # ===========================
            # La doblada permanente se aplica solo en los días VÁLIDOS del rango; los inválidos se
            # SALTAN (no se rechaza toda la solicitud). Un día es válido si el solicitante y el
            # compañero tienen ese día una jornada ÚNICA real (AM/PM) y CONTRARIA entre sí —usando la
            # jornada REAL del día (incluye cambios por CT sencillo/permanente), no la predeterminada—
            # y ninguno descansa, está libre, ni tiene doblada/festivo/temporada/mantenimiento ese día.
            # Esta política vive en `_fechas_validas`/`_ocurrencias` (fuente única con la aplicación).
            from solicitudes.services.doblada_permanente_aplicacion_service import (
                DobladaPermanenteAplicacionService as _DPAS,
            )
            # BALANCE: deben quedar días válidos en AMBOS lados (cubrir Y devolver). Si un lado
            # queda en 0, la doblada sería injusta (pagar sin cobertura o al revés) → se rechaza.
            #
            # IMPORTANTE: se valida EXACTAMENTE lo que se va a aplicar. Si la solicitud trae FECHAS
            # específicas (formulario nuevo) se re-validan ESAS fechas con `_fechas_validas` —igual que
            # `aplicar`—, no el barrido por día de la semana; así el formulario, la re-validación al
            # aprobar y la aplicación miran lo mismo (evita "el form me dejó pero al aprobar falla" y
            # permite señalar la FECHA exacta que bloquea). Sin fechas (legacy) se expanden los weekdays.
            _ex = datos.get('solicitud_actual_id')
            from datetime import date as _date

            def _parse_fechas(csv):
                out = []
                for s in (csv or '').split(','):
                    s = s.strip()
                    if not s:
                        continue
                    try:
                        out.append(_date.fromisoformat(s))
                    except ValueError:
                        # Igual que en reprogramacion_doblada_service: este CSV viene de la
                        # BD, así que un valor que no parsea es dato corrupto y no entrada
                        # del usuario. Se omite (comportamiento original) pero se registra.
                        logger.warning('Fecha corrupta %r en el CSV de fechas de doblada '
                                       'permanente; se omite', s)
                return out

            # Fechas que el acuerdo tocaría de verdad; con ellas se comprueban las pendientes.
            fechas_afectadas = []

            if fechas_cesion or fechas_devolucion:
                # Fechas concretas elegidas por el usuario (las que realmente se aplicarán).
                # `datos.get(...)` puede venir como lista (POST) o csv (reconstrucción desde BD);
                # se normaliza a csv con `_csv_fechas` ANTES de parsear/consultar (evita
                # AttributeError: 'list' object has no attribute 'split').
                csv_ces = _csv_fechas(datos.get('fechas_cesion'))
                csv_dev = _csv_fechas(datos.get('fechas_devolucion'))
                pedidas_ces = _parse_fechas(csv_ces)
                pedidas_dev = _parse_fechas(csv_dev)
                validas_ces = _DPAS._fechas_validas(csv_ces, fi, ff, solicitante, receptor, _ex)
                validas_dev = _DPAS._fechas_validas(csv_dev, fi, ff, solicitante, receptor, _ex)
                fechas_afectadas = sorted(set(validas_ces) | set(validas_dev))
                # Si alguna fecha pedida ya NO es válida, se nombra para que el usuario la ajuste.
                invalidas = sorted(set(pedidas_ces) - set(validas_ces)) + sorted(set(pedidas_dev) - set(validas_dev))
                if invalidas:
                    faltan = ', '.join(d.strftime('%d/%m/%Y') for d in invalidas)
                    return False, (
                        f"Estas fechas ya no son válidas para la doblada: {faltan}. "
                        "Ese día tú y el compañero deben tener jornadas CONTRARIAS (AM↔PM) según su jornada "
                        "real, y no puede caer en festivo, fin de semana, mantenimiento, temporada, descanso, "
                        "día libre ni un día ya doblado. Ajusta esas fechas o el compañero."
                    )
                if min(len(validas_ces), len(validas_dev)) == 0:
                    return False, (
                        "No quedan fechas válidas para CUBRIR y DEVOLVER a la vez. Revisa que en esas fechas "
                        "tú y el compañero tengan jornadas CONTRARIAS (AM↔PM) según su jornada real. "
                        "Ajusta las fechas o el compañero."
                    )
            else:
                ocur_ces = list(_DPAS._ocurrencias(fi, ff, dias_cesion, solicitante, receptor, _ex))
                ocur_dev = list(_DPAS._ocurrencias(fi, ff, dias_devolucion, solicitante, receptor, _ex))
                fechas_afectadas = sorted(set(ocur_ces) | set(ocur_dev))
                if min(len(ocur_ces), len(ocur_dev)) == 0:
                    return False, (
                        "En este rango no quedan días válidos para CUBRIR y DEVOLVER a la vez. "
                        "Revisa que en esos días tú y el compañero tengan jornadas CONTRARIAS (AM↔PM) "
                        "según su jornada real, y que no caigan en festivo, fin de semana, mantenimiento, "
                        "temporada, descanso, día libre o un día ya doblado. Ajusta el rango, los días o el compañero."
                    )

            # DUPLICADOS pendientes (regla de CREACIÓN; se OMITE al re-validar para aprobar).
            #
            # Se comprueban TODAS las fechas que el acuerdo tocaría, no solo `fecha_inicio`, y por
            # los DOS lados. Antes solo se miraba el primer día del rango y del solicitante, así
            # que una solicitud pendiente sobre cualquier otro día afectado —o cualquiera del
            # compañero— pasaba desapercibida y podía aprobarse en paralelo sobre el mismo día.
            #
            # Se usan las fechas VÁLIDAS (las que de verdad se aplicarían), no todo el rango: un
            # día que este acuerdo va a saltarse igualmente no tiene por qué bloquear nada.
            #
            # El solape con OTRA doblada permanente se comprueba aparte, más arriba: sus fechas
            # viven en `dias_*`/`fechas_*` y no en un campo que esta consulta pueda cruzar.
            if not datos.get('es_revalidacion') and fechas_afectadas:
                # La del SOLICITANTE se deja subir tal cual: habla de él ("Ya tienes una solicitud
                # pendiente..."), así que el alta multi-compañero no debe ponerle delante el nombre
                # de ningún compañero. La del COMPAÑERO sí se marca: dice "El compañero..." y sin
                # el nombre no se sabe cuál de todos es.
                SolicitudValidator.validar_sin_pendiente_en_fechas(solicitante, fechas_afectadas)
                try:
                    SolicitudValidator.validar_sin_pendiente_en_fechas(
                        receptor, fechas_afectadas, es_receptor=True)
                except ValidationError as e:
                    return False, ErrorDelCompanero(str(e))

            return True, "Solicitud de doblada permanente válida"

        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Error validando doblada permanente: {str(e)}"

    # ------------------------------------------------------------------- crear
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        try:
            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fi = self._parse(datos.get('fecha_inicio'))
            ff = self._parse(datos.get('fecha_fin'))

            solicitud = SolicitudCambio.objects.create(
                explorador_solicitante=solicitante,
                explorador_receptor=receptor,
                tipo_cambio=tipo_cambio,
                comentario=comentario,
                fecha_cambio_turno=fi,  # fecha principal = inicio del rango
                estado='pendiente',
            )
            try:
                DobladaPermanenteDetalle.objects.create(
                    solicitud=solicitud,
                    fecha_inicio=fi,
                    fecha_fin=ff,
                    dias_cesion=_csv(datos.get('dias_cesion')),
                    dias_devolucion=_csv(datos.get('dias_devolucion')),
                    fechas_cesion=_csv_fechas(datos.get('fechas_cesion')),
                    fechas_devolucion=_csv_fechas(datos.get('fechas_devolucion')),
                    empleado_receptor=receptor,
                )
            except Exception:
                solicitud.delete()
                raise

            # Notificaciones + email (reutiliza el flujo de cambio de turno)
            try:
                from ..notificacion_service import NotificacionService
                NotificacionService.crear_notificacion_solicitud(solicitud)
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Error notificando doblada permanente %s", solicitud.id)

            return solicitud, "Solicitud de doblada permanente creada correctamente"

        except Exception as e:
            return None, f"Error creando solicitud de doblada permanente: {str(e)}"

    # ----------------------------------------------------------------- aplicar
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        try:
            from core.services.cache_service import CacheService

            from ..doblada_permanente_aplicacion_service import DobladaPermanenteAplicacionService

            with transaction.atomic():
                detalle = solicitud.doblada_permanente
                n_ces, n_dev = DobladaPermanenteAplicacionService.aplicar(solicitud, detalle)

            # Invalidar caché de ambos en los meses del rango
            solicitante = solicitud.explorador_solicitante
            receptor = solicitud.explorador_receptor
            detalle = solicitud.doblada_permanente
            meses = set()
            from datetime import timedelta
            d = detalle.fecha_inicio
            while d <= detalle.fecha_fin:
                meses.add((d.month, d.year))
                d += timedelta(days=28)
            meses.add((detalle.fecha_fin.month, detalle.fecha_fin.year))
            for (m, y) in meses:
                CacheService.invalidar_cache_turnos_empleado(solicitante.id, m, y)
                CacheService.invalidar_cache_turnos_empleado(receptor.id, m, y)

            return True, f"Doblada permanente aplicada ({n_ces} días de cesión, {n_dev} de devolución)."

        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Error aplicando doblada permanente")
            return False, f"Error aplicando doblada permanente: {str(e)}"

    # --------------------------------------------------- empleados disponibles
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """
        Compañeros candidatos para la doblada permanente. Se ofrecen los que ese día tienen una
        jornada ÚNICA real (AM o PM), de **cualquiera de los dos grupos** — porque dentro del rango
        la jornada real del solicitante puede variar por fecha (por CT sencillo/permanente): unos
        días es AM (necesita compañero PM) y otros PM (necesita compañero AM). La validez fecha a
        fecha (jornadas contrarias, sin descanso/doblada) la resuelve la disponibilidad por día
        (`DiasDisponiblesDobladaPermanenteView`, compañero-aware) y la validación al guardar.

        Se usa la jornada REAL del día (no la predeterminada); se excluye a quien ese día está en
        DOBLADA, descanso o sin jornada. Cada empleado lleva `jornada_real` para etiquetar el picker.
        """
        try:
            fecha_obj = self._parse(fecha)
            if not fecha_obj:
                return []
            from ..cambios_permanentes_helper import jornadas_unicas_reales
            empleados = list(
                Empleado.objects.operativos()
                .exclude(id=usuario_actual.id)
                .select_related('supervisor')
            )
            # Resolución en LOTE (2 consultas para toda la plantilla). Antes se llamaba a
            # `_jornada_unica_real` empleado a empleado: ~1,8 consultas cada uno, que con 400
            # exploradores son ~730 consultas y más de un segundo para abrir el desplegable.
            jornadas = jornadas_unicas_reales(empleados, fecha_obj)
            candidatos = []
            for e in empleados:
                jr = jornadas.get(e.id)
                if jr in ('AM', 'PM'):
                    e.jornada_real = jr
                    candidatos.append(e)
            return candidatos
        except Exception:
            return []

    def detalle(self, solicitud, datos):
        """
        Detalle propio de DOBLADA PERMANENTE para la pantalla de consulta.

        Movido desde `views/detalle.py` en la Fase 2 (cerrar el OCP): la vista
        elegía con una cadena `if tipo_nombre == ...`, así que cada tipo nuevo
        obligaba a editarla. El cuerpo se trasladó SIN cambios de lógica; solo
        los imports relativos pasaron a absolutos al cambiar de paquete.
        """
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

                from solicitudes.services.doblada_permanente_aplicacion_service import (
                    DobladaPermanenteAplicacionService,
                )
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

    def validar_campos_requeridos(self, post):
        """Campos obligatorios de DOBLADA PERMANENTE (movido del parser en la Fase 2)."""
        if not post.get('fecha_inicio') or not post.get('fecha_fin'):
            return False, 'El rango de fechas (inicio y fin) es obligatorio'
        if not post.getlist('cesion_companero'):
            return False, 'Agrega al menos un día de cesión con su compañero'
        if not post.getlist('devolucion_companero'):
            return False, 'Agrega al menos un día de devolución con su compañero'
        return True, ''

    def parsear_datos(self, post, solicitante, receptor):
        """
        Traduce el POST de DOBLADA PERMANENTE (movido del parser en la Fase 2).
        """
        dias_cesion = (post.getlist('dias_cesion')
                       or [d for d in post.get('dias_cesion', '').split(',') if d.strip()])
        dias_devolucion = (post.getlist('dias_devolucion')
                           or [d for d in post.get('dias_devolucion', '').split(',') if d.strip()])
        return {
            'explorador_solicitante': solicitante,
            'explorador_receptor': receptor,
            'comentario': post.get('comentarios', ''),
            'fecha_inicio': post.get('fecha_inicio'),
            'fecha_fin': post.get('fecha_fin'),
            'dias_cesion': [d for d in dias_cesion if str(d).strip()],
            'dias_devolucion': [d for d in dias_devolucion if str(d).strip()],
            'fecha_creacion_solicitud': timezone.localdate(),
        }

    def reaplicar(self, solicitud, fechas):
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService,
        )

        perm = getattr(solicitud, 'doblada_permanente', None)
        if perm is None:
            return
        n = DobladaPermanenteAplicacionService.reaplicar_fechas(solicitud, perm, fechas)
        if n:
            logger.info(
                "Reconciliacion post-revert: re-materializada doblada permanente %s en %d dia(s).",
                solicitud.id, n,
            )

    def revertir_cambios(self, solicitud):
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService,
        )

        detalle = getattr(solicitud, 'doblada_permanente', None)
        if not detalle:
            return
        DobladaPermanenteAplicacionService.revertir(solicitud)
        self._invalidar_rango(solicitud, detalle.fecha_inicio, detalle.fecha_fin)
