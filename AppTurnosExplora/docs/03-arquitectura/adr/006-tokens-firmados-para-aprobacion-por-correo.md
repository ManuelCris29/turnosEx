# ADR 006: django.core.signing para los tokens de aprobación por correo

**Estado:** Implementado
**Fecha:** 2026-08

## Contexto

Los correos de solicitud llevan enlaces que **aprueban o rechazan sin iniciar sesión**. El token de
la URL es la credencial completa: no identifica una sesión, la sustituye.

Ese token se generaba con `hmac.new()` sobre una clave escrita en el código —
`b'secret_key_change_this'`, acompañada del comentario `# Cambiar en producción` — y el dato
firmado era `solicitud_id_empleado_id_tipo`. Tres consecuencias:

1. Cualquiera con acceso al repositorio podía fabricar un enlace válido para cualquier solicitud y
   aprobarla en nombre del supervisor.
2. El token no caducaba ni se invalidaba tras usarse.
3. La misma lógica estaba **duplicada en seis sitios**: `services/email_service.py`, cuatro vistas
   de `views/aprobacion_email.py` y —fuera de la app `solicitudes`— `permisos/services.py`.

La sexta copia es la parte importante del contexto: se pasó por alto en la primera revisión
precisamente por estar en otra app. Con la lógica duplicada, cerrar cinco de seis agujeros deja el
sistema igual de abierto.

## Decisión

**Una fuente única**, `solicitudes/services/tokens_aprobacion.py`, que firma con
`django.core.signing` (HMAC-SHA256 sobre `SECRET_KEY`, con marca de tiempo incorporada). Los seis
llamadores delegan en ella.

- **Caducidad**: `APPROVAL_LINK_MAX_AGE_DAYS`, 30 días por defecto.
- **Sal por circuito**: `solicitudes.aprobacion-email` y `permisos.aprobacion-email`, de modo que un
  token de un circuito no vale en el otro aunque los firme la misma clave.
- **Vínculo con el rol actual**: se compara contra quien ocupa el rol hoy, no contra quien lo
  ocupaba al enviarse el correo.
- **Falla cerrada**: firma inválida, caducada o ajena devuelven `False`; nunca una excepción.

### Alternativas descartadas

**Seguir con HMAC propio, cambiando solo la clave por `SECRET_KEY`.** Habría cerrado el agujero
inmediato sin resolver la caducidad ni la duplicación, y deja a mano de cada llamador un detalle
criptográfico que no le corresponde. `signing` trae la marca de tiempo y las sales ya resueltas.

**Guardar los tokens emitidos en una tabla y marcarlos como gastados.** Es la forma clásica de
lograr un solo uso, pero añade escrituras en el camino del envío de correo y una consulta en el de
la verificación, y con ello una dependencia de estado compartido. No hacía falta: el estado de la
solicitud **ya** impide la segunda aprobación (`_ya_resuelto_para()` en
`views/aprobacion_email.py`), vive en la base de datos —que es el almacén compartido entre
instancias— y además cubre el caso de que el cliente de correo pre-cargue el enlace.

**Tokens en caché (Redis) con expiración nativa.** Habría atado una función de seguridad a
`CACHE_URL`, que puede estar vacío o apuntar a memoria local. Un enlace que deja de validarse porque
se reinició un contenedor es peor que uno que caduca a fecha fija.

## Consecuencias

- Un token no se puede fabricar sin conocer `SECRET_KEY`.
- La verificación es **stateless**: no consulta base de datos ni caché, así que cualquier instancia
  detrás del balanceador valida un token emitido por otra. Esto es lo que hace la solución apta para
  la arquitectura de AWS, con varias instancias o tareas tras un ALB.
- **A cambio, todas las instancias deben compartir la MISMA `SECRET_KEY`** — una entrada de Secrets
  Manager/SSM, no un valor generado por tarea. Si cada una tuviera la suya, los enlaces fallarían de
  forma intermitente según a dónde encaminara el ALB, que es un fallo especialmente difícil de
  diagnosticar. Está en el checklist de despliegue (§13.3 del manual técnico).

  **Auditado el 2026-08-09: la condición ya se cumple en las dos rutas documentadas.** En Fargate,
  el checklist crea `swalp/SECRET_KEY` como secreto único y el task definition lo inyecta por
  `secrets:`, de modo que todas las tareas leen la misma entrada aunque se suba `--desired-count`.
  En la ruta EC2 hay una sola instancia con Elastic IP y un único `.env`. Y el escenario temido es
  imposible por construcción: `SECRET_KEY = env('SECRET_KEY')` no tiene valor por defecto —una
  instancia sin clave lanza `ImproperlyConfigured` y no arranca— y el repositorio no contiene
  ninguna llamada a `get_random_secret_key()` ni equivalente, así que el código no puede fabricarse
  una clave propia. Detalle y evidencias en §9.2 del manual técnico.
- **Rotar `SECRET_KEY` invalida los enlaces ya enviados.** Es el comportamiento correcto ante una
  filtración; hay que tenerlo en cuenta al planificar rotaciones rutinarias. Las solicitudes
  pendientes se resuelven entrando a la aplicación.
- Los enlaces emitidos por la versión vulnerable dejaron de funcionar. Es lo buscado: eran
  exactamente los falsificables.
- Cubierto por `solicitudes/tests/test_tokens_aprobacion.py` (25 tests), incluido uno que comprueba
  que un token firmado con la clave antigua ya no se acepta y otro que reproduce el escenario de dos
  instancias con `SECRET_KEY` distinta.

## Relacionado

- Patrón de protección **#38** en `PROTECTION_PATTERNS.md`, que generaliza la regla: una credencial
  que actúa sin sesión se firma en un solo sitio, caduca y falla cerrada.
- Manual técnico §9.2 (seguridad), §10 (configuración) y §16.4 (resueltos que conviene recordar).
