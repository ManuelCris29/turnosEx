"""
Fuente ÚNICA del ACUERDO que puso a alguien a TRABAJAR un día concreto.

Es el hermano de `DescansoPorSolicitudService`, que resuelve el lado contrario ("¿por qué
descanso este día y con quién?"). Este contesta: "este día trabajo por una solicitud
aprobada — ¿cuál, con quién, y en qué papel?".

POR QUÉ EXISTE
--------------
`MisTurnosPorMesView._enriquecer_solicitud_info` reimplementaba a mano la GEOMETRÍA de
cada tipo (quién trabaja qué fecha) con ocho consultas encadenadas. Esa copia nunca
estuvo completa, y el detalle del día se quedaba sin decir con quién era el acuerdo:

  · DOBLADA PERMANENTE no tenía ninguna consulta: el día doblado salía sin compañero.
  · CT PERMANENTE solo tenía compañero el PRIMER día del rango, porque
    `turno_origen`/`turno_destino` apuntan al primer turno creado.
  · CAMBIO DESCANSO entre semana cubría dos de las cuatro combinaciones; las
    sub-modalidades de temporada (cobertura, jornadas partidas, cambio de doblada) tienen
    otra geometría y se caían del mapeo.

Añadir una novena consulta arreglaba un caso y dejaba el patrón intacto para el
siguiente tipo.

DE DÓNDE SALE EL DATO
---------------------
De `snapshot_turnos_resultantes`: lo que CADA solicitud dejó en cada par
(empleado, fecha), con claves `"<empleado_id>:<YYYY-MM-DD>"` y valor la lista de turnos
resultantes (ver `DobladaSnapshotService.capturar_snapshot_resultante`). Lista NO vacía
significa "esta solicitud dejó a esta persona trabajando ese día"; lista vacía, "la dejó
libre".

Lo escribe el mismo código que aplica el cambio, así que no puede divergir de la
geometría real: no hay que re-derivar nada por tipo ni por sub-modalidad. Cuando una
solicitud no tiene resultante —se empezó a capturar después que el previo— se cae a
`snapshot_turnos_previos`, que dice qué FECHAS tocó aunque no qué dejó en ellas; ahí es la
guarda de realidad la que decide. Ver `_dias_reclamados`.

Los dos snapshots viven en tres sitios según el tipo:

    SolicitudCambio           → CAMBIO TURNO, CT PERMANENTE
    DobladaDetalle            → DOBLADA, D FDS, CAMBIO DESCANSO
    DobladaPermanenteDetalle  → DOBLADA PERMANENTE

PAGO REPROGRAMADO no pasa por ninguno de los tres (lo escribe el módulo de
reprogramación de dobladas), así que tiene su propia rama al final.

FORMA DE LA RESPUESTA
---------------------
    {
        fecha: {
            'solicitud_id': int,
            'tipo': str,               # nombre del TIPO DE SOLICITUD ('DOBLADA PERMANENTE')
            'tipo_cambio': str,        # lo que se escribe en Turno.tipo_cambio ('DOBLADA PERM')
            'companero_id': int,
            'companero_nombre': str,   # nombre Y apellido
            'rol': str,                # 'solicitante' | 'receptor' (el papel del EMPLEADO)
            'fecha_solicitud': str|None,
            'fecha_resolucion': str|None,
            'fecha_relacionada': str|None,   # la fecha de la contraparte, si el tipo la tiene
        }
    }
"""
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from core.utils.date_utils import DateUtils

# `fecha_resolucion` no debería faltar en una aprobada, pero si falta la solicitud se
# ordena como la MÁS ANTIGUA posible: así nunca gana un día por un dato ausente.
_INSTANTE_MINIMO = datetime.min.replace(tzinfo=dt_timezone.utc)


class AcuerdoPorDiaService:

    # El finde de un CAMBIO DESCANSO mueve el día al sábado/domingo contiguo, así que la
    # ventana de consulta se abre unos días a cada lado. Es inofensivo: quien decide de
    # verdad es el snapshot, que va por FECHA exacta.
    MARGEN_DIAS = 3

    @staticmethod
    def en_rango(empleado, ini, fin):
        """Acuerdo que hace trabajar a `empleado` en cada día de `[ini, fin]`: {fecha: info}."""
        from django.db.models import Q

        from solicitudes.models import SolicitudCambio

        if isinstance(ini, str):
            ini = date.fromisoformat(ini)
        if isinstance(fin, str):
            fin = date.fromisoformat(fin)

        emp_id = getattr(empleado, 'id', empleado)
        qini = ini - timedelta(days=AcuerdoPorDiaService.MARGEN_DIAS)
        qfin = fin + timedelta(days=AcuerdoPorDiaService.MARGEN_DIAS)

        # UNA consulta para las candidatas. El filtro de fechas es DELIBERADAMENTE amplio
        # (un superconjunto): solo sirve para no traerse el histórico entero del empleado.
        # Quién reclama cada día lo decide el snapshot, más abajo.
        candidatas = (
            SolicitudCambio.objects
            .filter(estado='aprobada')
            .filter(Q(explorador_solicitante_id=emp_id) | Q(explorador_receptor_id=emp_id))
            .filter(
                Q(fecha_cambio_turno__range=(qini, qfin))
                | Q(doblada__fecha_pago__range=(qini, qfin))
                | Q(doblada__fecha_pago_semana__range=(qini, qfin))
                | Q(doblada_permanente__fecha_inicio__lte=fin,
                    doblada_permanente__fecha_fin__gte=ini)
                | Q(cambio_permanente__fecha_inicio__lte=fin,
                    cambio_permanente__fecha_fin__gte=ini)
                | Q(cambio_permanente__fecha_inicio__lte=fin,
                    cambio_permanente__fecha_fin__isnull=True)
            )
            .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor',
                            'doblada', 'doblada_permanente')
            .distinct()
        )

        # GUARDA DE REALIDAD (L1 manda sobre L2), el mismo patrón que
        # `DescansoPorSolicitudService`: un snapshot solo puede hablar de un día si sigue
        # describiendo el turno que HAY. Sin esto, una solicitud vieja cuyo día fue
        # reescrito después por otra seguiría nombrando a su compañero, que es justo el
        # error que este servicio viene a cerrar.
        from turnos.models import Turno
        tipos_reales = {}
        for _f, _tc in Turno.objects.filter(
                explorador_id=emp_id, fecha__range=(ini, fin)
        ).values_list('fecha', 'tipo_cambio'):
            if _tc:
                tipos_reales.setdefault(_f, set()).add(_tc)

        # LA ÚLTIMA APROBADA GANA EL DÍA: se recorren de más reciente a más antigua y la
        # primera que reclame una fecha se la queda (`setdefault`). Es el principio central
        # del sistema — los acuerdos no se encadenan, el último cancela al anterior.
        ordenadas = sorted(
            candidatas,
            key=lambda s: (s.fecha_resolucion or _INSTANTE_MINIMO, s.id),
            reverse=True,
        )

        salida = {}
        for sol in ordenadas:
            for fecha, tipos_esperados in AcuerdoPorDiaService._dias_reclamados(sol, emp_id):
                if not (ini <= fecha <= fin):
                    continue
                if not (tipos_esperados & tipos_reales.get(fecha, set())):
                    continue
                salida.setdefault(fecha, AcuerdoPorDiaService._info(sol, emp_id, fecha))

        AcuerdoPorDiaService._agregar_pagos_reprogramados(salida, emp_id, ini, fin, tipos_reales)
        return salida

    @staticmethod
    def en_fecha(empleado, fecha):
        """Atajo de conveniencia: el acuerdo de UN día (o None)."""
        if isinstance(fecha, str):
            fecha = date.fromisoformat(fecha)
        return AcuerdoPorDiaService.en_rango(empleado, fecha, fecha).get(fecha)

    # ------------------------------------------------------------------ internos

    @staticmethod
    def _snapshot(solicitud, campo):
        """`snapshot_turnos_previos` o `..._resultantes` de la solicitud, viva donde viva."""
        for obj in (solicitud,
                    getattr(solicitud, 'doblada', None),
                    getattr(solicitud, 'doblada_permanente', None)):
            if obj is None:
                continue
            snap = getattr(obj, campo, None)
            if snap:
                return snap
        return None

    @staticmethod
    def _fecha_de_clave(clave, emp_id):
        """La fecha de una clave `"<emp_id>:<YYYY-MM-DD>"`, o None si no es de este empleado."""
        clave = str(clave)
        if not clave.startswith(f'{emp_id}:'):
            return None
        try:
            return date.fromisoformat(clave.split(':', 1)[1])
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _dias_reclamados(solicitud, emp_id):
        """
        `(fecha, {tipos_cambio aceptables})` de los días que ESTA solicitud puede reclamar.

        Dos niveles, del más preciso al menos, porque los dos snapshots no dicen lo mismo:

        1. **`snapshot_turnos_resultantes`** dice exactamente QUÉ dejó en cada (persona, fecha):
           lista no vacía = la dejó trabajando, y los tipos salen del propio snapshot. Cuando
           está, manda.

        2. **`snapshot_turnos_previos`** solo dice QUÉ FECHAS tocó, no qué dejó en ellas —sus
           valores describen el mundo ANTERIOR—. Sirve igual, porque quien decide de verdad es
           la guarda de realidad de `en_rango`: el día se reclama solo si el `Turno` que HAY es
           del tipo de esta solicitud, y quien ese día quedó libre no tiene turno que enseñar.

        El nivel 2 no es un adorno: el resultante se empezó a capturar DESPUÉS que el previo,
        así que sin él toda solicitud anterior a ese cambio deja su día sin compañero. Medido
        sobre la base de desarrollo (mariana.villa): 51 de 61 días con cambio se quedaban
        mudos, entre ellos un CT permanente entero de septiembre cuyo previo sí existe.
        """
        resultante = AcuerdoPorDiaService._snapshot(solicitud, 'snapshot_turnos_resultantes')
        if resultante:
            for clave, turnos in resultante.items():
                fecha = AcuerdoPorDiaService._fecha_de_clave(clave, emp_id)
                if fecha is None or not turnos:
                    continue
                tipos = {t.get('tipo_cambio') for t in turnos if t.get('tipo_cambio')}
                if tipos:
                    yield fecha, tipos
            return

        previo = AcuerdoPorDiaService._snapshot(solicitud, 'snapshot_turnos_previos')
        if not previo:
            return
        tipo_turno = AcuerdoPorDiaService._tipo_cambio_de(solicitud)
        if not tipo_turno:
            return
        for clave in previo:
            fecha = AcuerdoPorDiaService._fecha_de_clave(clave, emp_id)
            if fecha is not None:
                yield fecha, {tipo_turno}

    @staticmethod
    def _tipo_cambio_de(solicitud):
        """Lo que ESTA solicitud escribe en `Turno.tipo_cambio` (no es su `nombre`)."""
        nombre = solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else None
        return _TIPO_SOLICITUD_A_TIPO_CAMBIO.get(nombre, nombre)

    @staticmethod
    def _info(solicitud, emp_id, fecha):
        es_solicitante = solicitud.explorador_solicitante_id == emp_id
        companero = (solicitud.explorador_receptor if es_solicitante
                     else solicitud.explorador_solicitante)
        return {
            'solicitud_id': solicitud.id,
            'tipo': solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else None,
            'tipo_cambio': AcuerdoPorDiaService._tipo_cambio_de(solicitud),
            'companero_id': companero.id,
            'companero_nombre': f'{companero.nombre} {companero.apellido}'.strip(),
            'rol': 'solicitante' if es_solicitante else 'receptor',
            'fecha_solicitud': DateUtils.format_datetime_display(solicitud.fecha_solicitud),
            'fecha_resolucion': DateUtils.format_datetime_display(solicitud.fecha_resolucion),
            'fecha_relacionada': AcuerdoPorDiaService._fecha_contraparte(solicitud, fecha),
        }

    @staticmethod
    def _fecha_contraparte(solicitud, fecha):
        """
        La OTRA fecha del acuerdo: si este día es el de cesión, el de pago, y al revés.

        Solo la tienen los tipos que se materializan con `DobladaDetalle` (DOBLADA, D FDS,
        CAMBIO DESCANSO). Los permanentes son un rango con varias fechas por lado, no un
        par, así que ahí no hay "la otra fecha" que enseñar.
        """
        det = getattr(solicitud, 'doblada', None)
        if det is None:
            return None
        cesion = solicitud.fecha_cambio_turno
        pago = det.fecha_pago
        if cesion and fecha == cesion:
            return pago.strftime('%d/%m/%Y') if pago else None
        if pago and fecha == pago:
            return cesion.strftime('%d/%m/%Y') if cesion else None
        return None

    @staticmethod
    def _agregar_pagos_reprogramados(salida, emp_id, ini, fin, tipos_reales):
        """
        PAGO REPROGRAMADO: el día que el supervisor programó para pagar una doblada que no
        se pudo cumplir. No pasa por ningún snapshot —lo escribe el módulo de
        reprogramación—, pero SÍ tiene contraparte: el compañero de la doblada original.
        """
        from core.constants import TipoCambioTurno
        from solicitudes.models import ReprogramacionDiaDoblada

        reprogramaciones = (
            ReprogramacionDiaDoblada.objects
            .filter(explorador_id=emp_id, fecha_reprogramada__range=(ini, fin))
            .exclude(estado='cancelada')
            .select_related('doblada_origen__tipo_cambio',
                            'doblada_origen__explorador_solicitante',
                            'doblada_origen__explorador_receptor')
            .order_by('-creado_en')
        )
        for r in reprogramaciones:
            fecha = r.fecha_reprogramada
            if fecha in salida:
                continue
            if TipoCambioTurno.PAGO_REPROGRAMADO not in tipos_reales.get(fecha, set()):
                continue
            origen = r.doblada_origen
            es_solicitante = origen.explorador_solicitante_id == emp_id
            companero = (origen.explorador_receptor if es_solicitante
                         else origen.explorador_solicitante)
            salida[fecha] = {
                'solicitud_id': origen.id,
                'tipo': origen.tipo_cambio.nombre if origen.tipo_cambio else None,
                'tipo_cambio': TipoCambioTurno.PAGO_REPROGRAMADO,
                'companero_id': companero.id,
                'companero_nombre': f'{companero.nombre} {companero.apellido}'.strip(),
                'rol': 'solicitante' if es_solicitante else 'receptor',
                'fecha_solicitud': DateUtils.format_datetime_display(origen.fecha_solicitud),
                'fecha_resolucion': DateUtils.format_datetime_display(origen.fecha_resolucion),
                'fecha_relacionada': (r.fecha_original.strftime('%d/%m/%Y')
                                      if r.fecha_original else None),
            }


# El vocabulario de `TipoSolicitudCambio.nombre` NO es el de `Turno.tipo_cambio`
# (ver `core.constants.TipoCambioTurno`). Solo estos dos nombres se traducen; los demás
# coinciden literalmente y pasan tal cual. El frontend rotula por `tipo_cambio`, así que
# sin esta traducción una doblada permanente se anunciaría como "Cambio de turno".
_TIPO_SOLICITUD_A_TIPO_CAMBIO = {
    'CAMBIO TURNO': 'CT',
    'DOBLADA PERMANENTE': 'DOBLADA PERM',
}
