"""
Vocabularios de dominio: fuente única de los literales que se persisten.

Vive en `core` porque lo consumen `solicitudes`, `turnos` y `permisos`, y este
módulo no importa ninguno de ellos: no hay import circular en ninguna dirección.

⚠ Lo importante de este archivo son las TRES clases separadas. En el proyecto
conviven tres campos llamados `tipo_cambio` que NO comparten vocabulario:

    SolicitudCambio.tipo_cambio  FK  → TipoSolicitudCambio   (usa TipoSolicitud)
    Turno.tipo_cambio            CharField, texto plano      (usa TipoCambioTurno)
    TurnoArchivo.tipo_cambio     CharField, copia histórica  (usa TipoCambioTurno)

Mezclarlos no da error: da un filtro que no casa con ninguna fila y una
validación que deja de aplicarse en silencio. Ya pasó — ver el fix del filtro
`tipo_cambio__nombre='CT'` en `solicitudes/views/doblada_api.py`, donde se
comparaba un `codigo_estrategia` contra un `nombre`.
"""


class EstadoSolicitud:
    """Valores de `SolicitudCambio.estado`."""

    PENDIENTE = 'pendiente'
    APROBADA = 'aprobada'
    RECHAZADA = 'rechazada'
    CANCELADA = 'cancelada'
    PAGADA = 'pagada'
    # Una solicitud queda REEMPLAZADA cuando otra posterior pisa el mismo día:
    # no se encadenan cambios, gana la última aprobada.
    REEMPLAZADA = 'reemplazada'

    CHOICES = [
        (PENDIENTE, 'Pendiente'),
        (APROBADA, 'Aprobada'),
        (RECHAZADA, 'Rechazada'),
        (CANCELADA, 'Cancelada'),
        (PAGADA, 'Pagada'),
        (REEMPLAZADA, 'Reemplazada'),
    ]


class TipoSolicitud:
    """
    Valores de `TipoSolicitudCambio.nombre` — la tabla maestra, alcanzable por la
    FK `SolicitudCambio.tipo_cambio`.

    Se usan en filtros `tipo_cambio__nombre=...` y en comparaciones
    `solicitud.tipo_cambio.nombre == ...`.

    NO sirven para filtrar `Turno.tipo_cambio`: ese campo guarda otro
    vocabulario. Ver `TipoCambioTurno` y `MAPA_SOLICITUD_A_TURNO`.
    """

    CAMBIO_TURNO = 'CAMBIO TURNO'
    CAMBIO_DESCANSO = 'CAMBIO DESCANSO'
    CT_PERMANENTE = 'CT PERMANENTE'
    DOBLADA = 'DOBLADA'
    DOBLADA_PERMANENTE = 'DOBLADA PERMANENTE'
    D_FDS = 'D FDS'

    TODOS = (
        CAMBIO_TURNO, CAMBIO_DESCANSO, CT_PERMANENTE,
        DOBLADA, DOBLADA_PERMANENTE, D_FDS,
    )


class TipoCambioTurno:
    """
    Valores que se ESCRIBEN en `Turno.tipo_cambio` y `TurnoArchivo.tipo_cambio`.

    Marcan de dónde viene un turno. `NULL` es legítimo y significa "turno normal,
    sin cambio de por medio".

    ⚠ Este vocabulario NO coincide con el de `TipoSolicitud`. Tres de estos
    valores no tienen equivalente ahí:

    - `CT` es el `codigo_estrategia` del tipo, no su `nombre` ('CAMBIO TURNO').
    - `DOBLADA_PERM` es una abreviatura propia de 'DOBLADA PERMANENTE'.
    - `PAGO_REPROGRAMADO` y `PERMISO` no existen como tipo de solicitud: los
      escriben la reprogramación de dobladas y el módulo de permisos.
    """

    CT = 'CT'
    DOBLADA_PERM = 'DOBLADA PERM'
    PAGO_REPROGRAMADO = 'PAGO REPROGRAMADO'
    PERMISO = 'PERMISO'
    # Estos cuatro sí coinciden textualmente con el `nombre` de la maestra.
    DOBLADA = 'DOBLADA'
    CAMBIO_DESCANSO = 'CAMBIO DESCANSO'
    CT_PERMANENTE = 'CT PERMANENTE'
    D_FDS = 'D FDS'

    TODOS = (
        CT, DOBLADA_PERM, PAGO_REPROGRAMADO, PERMISO,
        DOBLADA, CAMBIO_DESCANSO, CT_PERMANENTE, D_FDS,
    )

    CHOICES = [
        (CT, 'Cambio de turno'),
        (DOBLADA_PERM, 'Doblada permanente'),
        (PAGO_REPROGRAMADO, 'Pago reprogramado'),
        (PERMISO, 'Permiso'),
        (DOBLADA, 'Doblada'),
        (CAMBIO_DESCANSO, 'Cambio de descanso'),
        (CT_PERMANENTE, 'CT permanente'),
        (D_FDS, 'Día fin de semana'),
    ]


# Traducción de un vocabulario al otro. Existe para que la correspondencia sea
# explícita y verificable en un test, en vez de estar implícita en cada servicio.
#
# Las dos entradas que importan son las que NO son la identidad: si alguna vez se
# unifican los textos, este mapa es el único sitio que debe cambiar.
MAPA_SOLICITUD_A_TURNO = {
    TipoSolicitud.CAMBIO_TURNO: TipoCambioTurno.CT,                    # ← no es identidad
    TipoSolicitud.DOBLADA_PERMANENTE: TipoCambioTurno.DOBLADA_PERM,    # ← no es identidad
    TipoSolicitud.CAMBIO_DESCANSO: TipoCambioTurno.CAMBIO_DESCANSO,
    TipoSolicitud.CT_PERMANENTE: TipoCambioTurno.CT_PERMANENTE,
    TipoSolicitud.DOBLADA: TipoCambioTurno.DOBLADA,
    TipoSolicitud.D_FDS: TipoCambioTurno.D_FDS,
}
