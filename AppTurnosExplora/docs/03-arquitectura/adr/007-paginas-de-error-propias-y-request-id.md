# ADR 007: páginas de error propias, autocontenidas, con identificador de petición

**Estado:** Implementado
**Fecha:** 2026-08

## Contexto

Con `DEBUG=True`, Django responde a una URL inexistente con su pantalla técnica, que imprime el
**URLconf completo**: todos los endpoints de la aplicación, incluidos los de aprobación y rechazo
de solicitudes. Y responde a un 500 con el traceback, el código fuente alrededor de la línea que
falló y las variables locales de cada marco. Eso es divulgación de información:

- **CWE-215** — Insertion of Sensitive Information Into Debugging Code.
- **CWE-209** — Generation of Error Message Containing Sensitive Information.
- **OWASP A05:2021** — Security Misconfiguration.

El fallo es real y reproducible: `/solicitudes/cambio-turno/loquesea` devolvía el mapa de rutas
entero (`core/tests/test_paginas_error.py:8-10`).

Poner `DEBUG=False` corta la fuga, pero abre otro problema: el usuario ve una página muda y el
equipo se queda sin forma de relacionar «me falló a las 3» con una línea concreta del log
(`core/errors.py:12-14`).

Hay una tercera restricción que condiciona el diseño: `handler500` se ejecuta **cuando algo ya ha
fallado**, muy probablemente la base de datos. Cualquier página de error que consulte la BD, herede
del layout de la aplicación o dependa de un CDN es una página de error que no funciona justo el día
que se necesita.

## Decisión

Un sistema de errores propio en `core/errors.py`, cinco plantillas autocontenidas y un
identificador de petición que viaja del navegador al log.

1. **`RequestIDMiddleware`** (`core/errors.py:51-76`) genera `uuid4().hex[:12].upper()` por
   petición, lo guarda en un `ContextVar` y en `request.request_id`, y lo publica en la cabecera
   `X-Request-ID`. Es el **primer** middleware de la lista (`config/settings.py:71`).
   - Se usa un `ContextVar` y no solo un atributo del `request` porque el filtro de logging no
     recibe el `request` (`core/errors.py:41-43`).
   - **No** se acepta un `X-Request-ID` entrante del cliente: sería un valor controlado por el
     atacante escrito en los logs — inyección de log y envenenamiento de trazas
     (`core/errors.py:58-61`).
   - El identificador es aleatorio, no correlativo: no revela el volumen de peticiones ni permite
     adivinar el de otro usuario (`core/errors.py:28-29`).
2. **`RequestIDFilter`** (`core/errors.py:79-84`) inyecta `record.request_id` para que los
   formatters lo impriman en cada línea.
3. **Handlers** `bad_request`, `permission_denied`, `page_not_found`, `server_error` y
   `csrf_failure` (`core/errors.py:114-164`), enlazados en `config/urls.py:56-59` y
   `config/settings.py:445`.
4. **Plantillas** `templates/errors/_base_error.html` + `400/403/403_csrf/404/500.html`, sin
   herencia de `base.html` y sin ningún recurso externo.
5. **`LOGGING`** con consola y fichero rotatorio, ambos con el filtro
   (`config/settings.py:509-578`).

### El detalle que sostiene todo: `_render` no recibe el `request`

`_render` usa `loader.get_template(...).render(context)` y **no** `render(request, ...)`
(`core/errors.py:96-111`). La razón está escrita en el propio módulo (`core/errors.py:90-94`):
`render()` activa los context processors, y `core.context_processors.permisos` consulta la base de
datos. En un `handler500` provocado precisamente por la BD caída, eso lanzaría una segunda
excepción y Django acabaría devolviendo su 500 de emergencia en texto plano. Además Django renderiza
`handler500` con contexto **vacío**: no hay `request`, ni `user`, ni context processors
(`core/tests/test_paginas_error.py:117-128`).

Hay una última red: si la propia plantilla falla, se registra la excepción y se devuelve un HTML
mínimo, antes que dejar salir la pantalla técnica (`core/errors.py:101-110`).

### Por qué las plantillas son autocontenidas

Tres razones, documentadas en la cabecera de la base (`templates/errors/_base_error.html:1-35`):

| Razón | Qué evita |
|---|---|
| Seguridad | No se muestra ruta pedida, excepción ni nombre de vista. Solo un código opaco |
| Robustez | Heredar de `base.html` renderizaría el sidebar, que consulta `user.empleado.notificaciones_no_leidas_count` y tocaría la BD posiblemente caída |
| Disponibilidad | CSS y SVG en línea: la página se ve aunque WhiteNoise/S3 estén caídos |

Son compatibles con la CSP activa (`style-src` y `script-src` admiten `'unsafe-inline'`) y también
con la política estricta en report-only, porque no añaden ningún origen externo (§ 9.3 del manual
técnico).

### Por qué el motivo del CSRF no se muestra

`csrf_failure` registra el `reason` con `logger.warning` pero al usuario le enseña un mensaje
genérico de sesión expirada (`core/errors.py:154-164`). Decirle a un atacante si falló por «CSRF
token missing» o por «Referer checking failed» le indica exactamente qué comprobación esquivar en
el siguiente intento.

### Cómo se revisan las páginas en desarrollo

Con `DEBUG=True` Django nunca llega a usar los handlers, así que las páginas no se podrían revisar.
Se enruta `/__error__/<codigo>/` **solo** bajo `DEBUG` (`config/urls.py:38-48`,
`core/errors.py:134-151`), con 400, 403, 404, 500 y 419 —código libre para distinguir el CSRF del
403 genérico— (`core/errors.py:142-148`). Esa ruta no existe en producción.

### La vía que no pasa por ninguna plantilla: los envíos AJAX

Los seis formularios de solicitud envían por `fetch` y **no recargan la página**, así que un 500
durante el envío no pasa por `handler500` ni por ninguna plantilla de error: cada formulario pinta
su propio aviso. El identificador viajaba en la cabecera `X-Request-ID` de esa misma respuesta,
pero nadie lo leía. El resultado era que el código de referencia existía en la mitad tranquila de
la aplicación y desaparecía justo en la crítica: una solicitud que pudo quedar a medias en la base
era precisamente el caso en el que el usuario no tenía nada que reportar.

Se cierra con `static/js/utils/codigo-referencia.js`, que **envuelve `window.fetch`** y guarda el
identificador de las respuestas con error. Es un *monkey-patch*, y conviene dejar escrito por qué,
porque a primera vista pide ser sustituido por algo más limpio.

Salvaguardas que hacen aceptable el shim, y que **no se deben deshacer**: no altera los argumentos
ni la respuesta —devuelve la misma `Response`—, **no encadena `.catch`**, de modo que un fallo de
red sigue rechazando la promesa igual que antes, y envuelve la lectura de la cabecera en
`try/catch`. Solo guarda el identificador de respuestas con error, y caduca a los 60 s.

Un stub define `window.CodigoReferencia` en `base.html` **antes** de cargar el fichero. Sin él, si
el script no llegara a cargarse los `.catch()` de los formularios lanzarían `ReferenceError`
*dentro* del manejador de error, antes de rehabilitar el botón de enviar: el usuario se quedaría
sin aviso y con el formulario bloqueado. Una ayuda de diagnóstico no puede convertirse en un punto
de fallo en la propia ruta de error.

### La otra vía sin plantilla: los enlaces de aprobación por correo

`solicitudes/error_token.html` es una respuesta normal de una vista, no un handler, así que quedó
fuera del barrido inicial. Cuatro `except Exception` de `solicitudes/views/aprobacion_email.py`
hacían `render_error_token(request, f'Error al procesar la solicitud: {str(e)}')`: el mismo CWE-209
que este ADR viene a cerrar, en una página que ve quien llega desde un correo, posiblemente sin
sesión iniciada. Se sustituye por `render_error_token_inesperado()`, que deja la traza en el log y
muestra el código de referencia. De paso, esas vistas devolvían **200 OK** en los fallos, lo que
los hacía invisibles para cualquier alarma que vigile códigos de error; ahora usan 403, 409 y 500
según el caso.

### La tercera vía sin plantilla: las APIs JSON

Ocho `except Exception` de vistas API devolvían `JsonResponse({'error': f'...: {str(e)}'},
status=500)`. Tampoco pasan por ningún handler. `str(e)` de MySQL puede ser
`(1054, "Unknown column ...")` o `(2003, "Can't connect to MySQL server on
'swalp-prod.xxxx.rds.amazonaws.com'")`, que expone el endpoint de RDS. Atenuante: las ocho exigen
sesión iniciada —cinco cualquier empleado, tres solo un supervisor—, a diferencia de la fuga
original del 404. Se sustituyen por `json_error_inesperado()`
(`core/utils/json_responses.py:68`), hermano de `render_error_token_inesperado()`.

Hallazgo del camino: **seis de los ocho no dejaban traza útil** (tres no registraban nada, tres
usaban `logger.error` sin `exc_info`). Se estaba en lo peor de ambos mundos —el detalle para quien
no lo necesita, nada para quien sí—, así que el cambio es tanto de observabilidad como de
seguridad.

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Dejar `DEBUG=True` en desarrollo y confiar en que producción tendrá `DEBUG=False` | Un despliegue mal configurado publica el URLconf entero. El test de regresión no dependería de nada verificable |
| Plantillas de error heredando de `base.html` | El sidebar consulta la BD; el 500 por BD caída se convertiría en un 500 desnudo |
| Aceptar el `X-Request-ID` del cliente para correlacionar con un proxy | Valor controlado por el atacante escrito en el log |
| Un contador incremental como identificador | Revela volumen de peticiones y permite adivinar el de otro usuario |
| Enviar el traceback al usuario en un bloque plegable «para soporte» | Es exactamente CWE-209 con otro envoltorio |
| Migrar las ~50 llamadas a `fetch` de los formularios a `ApiClient` en vez de envolver `fetch` | Es la opción "limpia", y por eso hay que dejar constancia de por qué se rechazó: son cincuenta puntos de **lógica de envío** que habría que tocar por una mejora de **diagnóstico**. El riesgo de regresión en el flujo crítico supera con mucho el de un shim que solo lee una cabecera. Sigue siendo el destino deseable a largo plazo, pero como refactor propio y con su propia validación |
| Mostrar el código de referencia leyendo `X-Request-ID` en cada `.catch()` | Mismo problema repartido en cincuenta sitios, y varios `.catch()` ni siquiera reciben la respuesta: la descartan antes |
| Dejar que los avisos de **carga** de listas (compañeros, dobladas) también muestren el código | No hay nada que reportar: se reintenta solo al cambiar de selección. Enseñar un código en un fallo que se resuelve solo entrena al usuario a ignorarlos |
| Unificar los ocho `except Exception` de las APIs bajo un mensaje genérico único, como el `MENSAJE_INESPERADO` de la página del token | Más barato de mantener y perfectamente seguro, pero degrada la experiencia más de lo que exige la seguridad: en una API que alimenta un desplegable, "Ha ocurrido un error" deja al usuario sin saber **qué** falló ni si merece reintentar. La seguridad la garantiza la regla "solo texto redactado por nosotros", no la uniformidad del texto; y hay un test que la vigila. Se conserva un mensaje específico por endpoint |
| Sentry / APM externo desde el primer día | Dependencia y coste que no hacían falta: stdout ya llega a CloudWatch por el log driver `awslogs`. La correlación por `request_id` es la pieza que faltaba, no el proveedor |

## Consecuencias

- El usuario reporta un código de 12 caracteres y el equipo reconstruye la petición entera con un
  único filtro: `aws logs filter-log-events --log-group-name /swalp/app --filter-pattern '"A3F91C2B"'`
  (`config/settings.py:487-490`).
- Toda respuesta lleva `X-Request-ID`, verificado por test
  (`core/tests/test_paginas_error.py:62-66`).
- 17 tests de regresión bloquean las tres formas de reintroducir la fuga: heredar de `base.html`,
  pasar el `request` al renderizar o desplegar con `DEBUG=True`
  (`core/tests/test_paginas_error.py:4-6`).
- Si el directorio de logs no es escribible —contenedor con filesystem de solo lectura, que es lo
  recomendable en Fargate— la aplicación **no se cae**: se renuncia al fichero y todo sale por
  stdout (`config/settings.py:499-507`).
- Los logs contienen nombres de empleado y detalles de solicitudes: son datos personales. La
  retención se configura en el grupo de CloudWatch y el acceso se restringe por IAM
  (`config/settings.py:492-494`).

## Pendiente

`DEBUG=False SECURE_HTTPS=True python manage.py check --deploy` pasa con un único aviso:
**`security.W009`** — la `SECRET_KEY` sigue siendo la autogenerada con prefijo `django-insecure-`.
Rotarla invalida todas las sesiones activas y los enlaces de aprobación por correo ya enviados
([ADR 006](./006-tokens-firmados-para-aprobacion-por-correo.md)); en AWS debe vivir en Secrets
Manager como entrada única (§ 13.3 del manual técnico). Conviene añadir
`manage.py check --deploy --fail-level WARNING` como puerta del pipeline.
