# Auditoría de arquitectura, SOLID y código limpio — AppTurnosExplora

**Fecha:** 2026-08-19 · **Stack:** Django 5.2.16 (LTS), Python 3.12, MySQL/PyMySQL, Redis, gunicorn, AdminLTE/JS vanilla
**Tamaño:** 64.705 líneas Python (sin migraciones), 47 archivos JS propios (~12.600 líneas), 114 templates, 959 tests
**Alcance acordado:** informe únicamente. No se toca código de aplicación.

---

## Contexto

El proyecto está en pre-producción y funciona. La auditoría busca establecer una línea base objetiva de calidad
—arquitectura, SOLID, código limpio— y un orden de ataque para la deuda antes de que el sistema entre en
producción, momento a partir del cual refactorizar cuesta 5-10× más.

**Documentación oficial contrastada vía Context7** — ver §7 para el detalle de qué se verificó, qué
correcciones produjo y qué no pudo comprobarse:

| Librería | ID Context7 | Verificado |
|---|---|---|
| Django 5.2 | `/websites/djangoproject_en_5_2` | System checks `deploy=True`, `on_commit`, `select_for_update`, caché multiproceso, política de deprecación |
| django-axes | `/jazzband/django-axes` | Semántica de `AXES_LOCKOUT_PARAMETERS`, ajustes `AXES_IPWARE_PROXY_*` |
| Gunicorn | `/benoitc/gunicorn` | Fórmula de workers, `--max-requests`, timeouts en Docker |
| django-csp 4.0 | — | No indexado en Context7. **Resuelto sin doc: verificado EJECUTÁNDOLO** (2026-08-21) — se comprobó que la cabecera `Content-Security-Policy` se emite con los valores del diccionario. Los nonces quedaron descartados por coste/beneficio, así que su sintaxis ya no hace falta |

---

## Veredicto: 55 % (19 ago) → **62 % re-medido el 26 ago 2026**

> ⚠ **Esta tabla es la LÍNEA BASE del 19 de agosto y estaba en contradicción con su
> propia hoja de ruta.** Conservaba `OCP 3` cuando la Fase 2 —que arregló justamente
> el OCP— aparece marcada **HECHA** más abajo en este mismo archivo (§Fase 2, puntos
> 11 y 12). Las Fases 0, 1 y 2 se cerraron entre el 19 y el 22 de agosto y nadie
> subió el resultado a la portada.
>
> Se conservan las dos columnas: la línea base para no perder la trazabilidad, y la
> re-medición para saber dónde estamos.

| Dimensión | Peso | 19 ago | **26 ago** | Comentario de la re-medición |
|---|---|---|---|---|
| Arquitectura por capas | 20 % | 6,0 | **6,5** | Las capas existen; los repositorios siguen sin adoptarse (19 llamadas frente a 467 accesos ORM crudos) |
| Principios SOLID | 20 % | 3,6 | **4,2** | SRP 3 · **OCP 8** · LSP 6 · ISP 3 · DIP 3. El salto es la Fase 2: despacho por strategy, con test-trinquete |
| Código limpio | 15 % | 4,0 | **4,5** | 62 funciones > 100 líneas (eran más); type hints en 34 % de 1 250 funciones; 0 `TextChoices` |
| Tests | 15 % | 6,5 | **7,5** | **1 439 tests** (eran 959), factories ya existen, `tests_js/` con 85 tests bloqueantes. Sigue sin `conftest.py` |
| Seguridad y configuración | 10 % | 8,0 | **8,5** | CSP estricta, IDOR cerrado, `AXES_IPWARE_*` corregido |
| Tooling / CI | 10 % | 6,0 | **7,5** | `ruff check .` **en cero** y bloqueante; pre-commit; gate de cobertura al 68 %; bandit + pip-audit |
| Frontend | 5 % | 3,0 | **4,0** | 40 scripts, ~16 000 líneas. La red de pruebas JS ya existe; la duplicación se midió y era de nombres, no de código |
| Documentación | 5 % | 9,0 | **9,5** | 11 ADRs y bitácora por sesiones. *(Descontando los 12 documentos caducados corregidos el 26 ago)* |

**Total ponderado: 5,50 → 6,22 / 10 → 62 %**

Techo realista y sano para un Django de este tamaño: **~78-80 %**. Pasar de ahí es
ceremonia, no calidad — y perseguir el número es exactamente lo que produjo un
`EmpleadoRepository` que nadie usó y acabó borrado.

Lectura honesta: **no es un proyecto mal hecho, es un proyecto bien pensado y mal contenido.** Alguien diseñó
las capas correctas (`domain/`, `repositories/`, `use_cases/`, `strategies/`, interfaces en `core/interfaces`)
y luego la presión de entrega hizo que la lógica se depositara donde era más rápido escribirla. La brecha entre
la arquitectura *declarada* y la *ejecutada* es el hallazgo central.

> ⚠️ **Nota metodológica — leer antes de fiarse de cualquier hallazgo de este informe.**
> **CUATRO** afirmaciones de la primera pasada resultaron falsas, y las cuatro son del mismo tipo: **decir que
> algo no existe sin haberlo buscado**.
>
> | Se afirmó | Realidad |
> |---|---|
> | «no hay system check para la caché» (§5.1) | `core/checks.py:15` ya lo implementaba, con test |
> | «no hay CI» (§4) | `.github/workflows/ci.yml` existía en la **raíz del repo**, un nivel por encima |
> | «no detecto CVE abiertos» (§5.7) | `pip-audit` encontró 15 en 3 paquetes |
> | «el runner del outbox no está planificado» (§9) | estaba en los dos checklists y en su manual |
>
> Dos causas: explorar `AppTurnosExplora/` ignorando la raíz real del repositorio (donde viven `.github/`,
> `.gitignore` y `PROTECTION_PATTERNS.md`), y afirmar ausencias sin ejecutar la herramienta que las
> comprobaría. Los cuatro están retirados y marcados en su sitio; la nota global subió de 52 % a 55 %.
>
> **Regla para el futuro: un hallazgo del tipo «esto no existe» no vale nada sin el `grep` o el comando que
> lo demuestre.** Los hallazgos sobre código que sí se leyó (SOLID, tamaños, duplicación) no están afectados.

---

## 1. Arquitectura — la brecha entre lo declarado y lo real

Lo que existe y está bien:

- Separación en 6 capas con nombres correctos (`solicitudes/domain`, `repositories`, `use_cases`, `services/strategies`, `services`, `views`).
- Patrón Strategy con contrato explícito: `solicitudes/services/strategies/base_strategy.py:18`, 3 abstractos + 4 hooks.
- **Inversión de dependencias bien hecha** en `core/services/__init__.py:20-42` (interfaces + factory functions).
- ADRs versionados en `docs/03-arquitectura/adr/`.
- `transaction.on_commit` usado correctamente en el flujo de aprobación (`solicitud_aprobacion_service.py:237,333,398,459`) — exactamente el patrón que recomienda la doc de Django para efectos laterales.

Lo que la rompe:

| Problema | Evidencia |
|---|---|
| El orquestador de negocio devuelve HTTP | `services/solicitud_orchestrator.py:12,57,74-77` importa y devuelve `JsonResponse`, mientras su docstring `:6` afirma "No contiene lógica HTTP" |
| El flujo de creación no pasa por `use_cases/` | `crear_solicitud.py` = 41 líneas vacías; el trabajo real está en `SolicitudOrchestrator` (681 L) |
| Los repositorios existen y nadie los usa | `repositories/solicitud_repository.py` (192 L) no se importa desde ninguna strategy |
| ORM dentro del dominio | `domain/bloqueo_partes.py:62` hace `Empleado.objects.select_for_update()` — justo lo que `domain/` debía evitar |
| El mecanismo DIP correcto está puenteado | `core/services` solo se invoca desde `base_strategy.py:104,171` |

---

## 2. SOLID — violaciones con evidencia

### SRP (3/10)

`strategies/doblada_strategy.py` es una sola clase que valida (`:66`), persiste (`:882`), compensa borrando a
mano (`solicitud.delete()` `:885`), notifica (`:900-905`), aplica turnos (`:920+`) e invalida caché (`:981`).
Mismo patrón en `cambio_descanso_strategy.py:735,771-773`, `use_cases/cancelar_solicitud.py` (711 L: máquina de
estados + locking + reversión por tipo + notificaciones) y `permisos/views.py:639,647,662,676` (vistas que
crean notificaciones directamente).

### OCP (3/10) — **el fallo arquitectónico principal**

Cinco cadenas `if/elif` sobre el tipo de solicitud, fuera de las strategies que existen precisamente para eso:

- `use_cases/cancelar_solicitud.py:651-704` — 6 ramas por tipo. Debería ser `strategy.revertir_cambios(sol)`.
- `views/detalle.py:124-140` — 6 ramas. Debería ser `strategy.detalle(sol)`.
- `services/solicitud_request_parser.py:40-62` y `:106-148` — doble cadena. Debería ser `strategy.parse(post)`.
- `services/doblada_snapshot_service.py:258,267,460,463,510,513`.
- `services/fechas_helper.py:99,135,165,168,174` — reglas de fecha por tipo.

**Consecuencia medible:** añadir un séptimo tipo de solicitud obliga hoy a tocar ≥5 archivos ajenos a la nueva
strategy. Ese es el coste real de esta violación.

### LSP (5/10) — dos roturas, una peligrosa

1. ~~`base_strategy.py:74-93`: `_datos_desde_solicitud` devuelve `None` por defecto…~~ **CORREGIDO
   (2026-08-21), y eran TRES fail-opens, no uno.** El hook es hoy `@abstractmethod` —olvidarlo impide
   instanciar la clase— y el `None` dejó de significar «déjalo pasar»: ahora falla CERRADO. Los otros dos
   los encontró la auditoría y **no estaban en este informe**: las tres estrategias con detalle devolvían
   `None` si faltaba su fila, y `SolicitudFactory` usaba `get_strategy`, que devuelve `None` para un tipo
   INACTIVO — o sea que desactivar un tipo hacía que se aprobaran **todas** sus pendientes sin comprobar
   ninguna. Ver punto 13 y `solicitudes/tests/test_failopen_revalidacion.py`.
2. `d_fds_strategy.py:391,429` invierte la precondición de `disponibilidad_companero` de la base. Está
   documentado (`base_strategy.py:117-121`) y es deliberado, pero significa que la clase base no es una
   abstracción sino una implementación concreta que una subclase contradice.

### ISP (4/10)

`SolicitudStrategy` mezcla ciclo de vida (`validar/crear/aplicar`) con consultas de UI
(`get_empleados_disponibles:99`, `disponibilidad_companero:110`, `etiqueta_companero:143`). Deberían ser dos
interfaces.

### DIP (3/10)

Todas las strategies importan el ORM directo (`doblada_strategy.py:13-15`). Más de 20 imports diferidos dentro
de métodos solo en ese archivo (`:254,352,361,458,475,544,583,638,651,736,901,939,981,1028,1038,1060,1112,1149`):
ocultan ciclos de importación reales, el acoplamiento sigue ahí pero el linter ya no lo ve.

---

## 3. Código limpio (4/10)

**Métodos monstruo** — los 6 peores:

| Líneas | Ubicación |
|---|---|
| **515** | `strategies/doblada_strategy.py:66` `validar_solicitud` |
| **343** | `views/doblada_api.py:137` `get` |
| **308** | `views/api_turno_jornada.py:33` `get` |
| **297** | `strategies/cambio_turno_strategy.py:337` `aplicar_cambios` |
| **267** | `turnos/api/views/turnos_mes.py:129` `calcular_predeterminado` (closure anidada) |
| **216** | `turnos/api/views/reportes.py:253` `izquierda` (closure) |

Hay 25 métodos por encima de 80 líneas. Complejidad ciclomática aparente por archivo: `doblada_strategy.py`
**116 ramas**, `cambios_permanentes_helper.py` **102**, `cambio_descanso_strategy.py` **93**.

**God Objects:** 14 de los 25 archivos más grandes lo son claramente, 6 más están en el límite.

**Duplicación:**
- Tres `_parse` de fechas privados (`cambio_descanso:39`, `d_fds:43`, `doblada_permanente:64`) cuando ya existe `core.utils.date_utils.DateUtils.parse_date` — que `doblada_strategy.py:126` sí usa.
- `_trabaja_dia` duplicado con firmas divergentes: `cambio_descanso_strategy.py:91` vs `cambio_descanso_aplicacion_service.py:235`. Divergencia latente en una regla de negocio.
- Aritmética sábado/domingo triplicada: `cambio_descanso_strategy.py:63`, `base_strategy.py:126-129` y `:147-150`.
- **Dos mecanismos anti-duplicado no coordinados**: `_es_duplicado_pendiente` (`cambio_descanso_strategy.py:73`) y el dedupe por hash SHA-256 del orquestador (`solicitud_orchestrator.py:60-88`).

**Lo bueno:** los modelos NO son Fat Models (`solicitudes/models.py` es casi todo declaración), no hay queries
en templates, no hay `except:` desnudos, y las docstrings explican el *porqué* con una calidad muy por encima
de la media.

**Lo malo:** 209 `except Exception`, de los cuales **12 son silenciosos (`: pass`)**, tres de ellos en el
corazón transaccional: `solicitud_orchestrator.py:314,358,450`. Y `print()` en producción:
`notificacion_service.py:432,434,436` (uno es un `[ERROR]` que se pierde de CloudWatch) y
`views/api_disponibles_ct_preview.py:97,102,105`.

---

## 4. Tests y tooling (6,5 / 6,0)

- **65,19 % de cobertura de línea** (`coverage.xml`, 18.569/28.484), sin cobertura de ramas.
- 959 funciones `test_` en 91 archivos. Volumen serio.
- **Puntos ciegos:** `permisos` **38,6 %**, `solicitudes/domain` **23,7 %**, `empleados/repositories` **0 %**, `solicitudes/management/commands` **3,5 %**, `scripts/**` 0 % (excluido de `testpaths`, 18 tests huérfanos).
- **Sin `conftest.py` en todo el repo** ni `factory_boy`: cada test construye objetos a mano → duplicación de setup.
- Integración: **1 solo test** (`integration_tests/integration/test_solicitud_flow.py`) frente a 950+ unitarios.
- ~~**Sin CI (`.github/` no existe)**~~ **HALLAZGO RETIRADO (falso positivo).** El CI **sí existía**: `.github/workflows/ci.yml` en la **raíz del repositorio** (`C:ppTurnos`), no dentro de `AppTurnosExplora/`. Corre desde el commit `cd57317` con MySQL 8.0, carga de tablas TZ, `manage.py check`, `check --deploy` con entorno de producción simulado y `pytest`. **La auditoría exploró solo el subdirectorio del proyecto Django y no la raíz del repo** — misma causa que el falso positivo de `core.E001` (§5.1). Lo que sí faltaba y se añadió el 2026-08-19: ejecución en todas las ramas (antes solo `main`), `-n auto`, gate de cobertura y job de lint.
- **Sin linter (ni ruff, black, flake8 ni mypy) y sin pre-commit** — esto sí era cierto. Corregido el 2026-08-19: `[tool.ruff]` en `pyproject.toml` y `.pre-commit-config.yaml` en la raíz del repo.
- `sonar.python.version=3.14` vs `python:3.12-slim` en el Dockerfile: desalineado.
- `pytest.ini` usa `--disable-warnings`. *Preciso tras Context7:* el flag no desactiva la captura, solo **oculta el resumen** al final de la corrida — los `DeprecationWarning` se registran pero nadie los ve. La doc de Django insiste en resolverlos *antes* de actualizar y recuerda que Python los silencia por defecto, por lo que hay que forzarlos con `-Wa` / `PYTHONWARNINGS`. El arreglo es un `filterwarnings` en `pytest.ini`, no quitar el flag. Política de deprecación confirmada: lo obsoleto en 5.2 (LTS) se elimina en **Django 6.1**.

---

## 5. Seguridad y despliegue (8,0)

Bien: secretos vía `django-environ` con `.env` no versionado y `SECRET_KEY` sin default (falla al arrancar,
correcto); HSTS 1 año + preload, `X_FRAME_OPTIONS DENY`, nosniff, cookies `Secure`/`HttpOnly`/SameSite;
`CSRF_FAILURE_VIEW` propio; logging estructurado con `request_id` y fallback si el directorio no es escribible;
Dockerfile con usuario no root; requirements 100 % pineados; **system checks propios** para caché y TLS (`core/checks.py`).

Riesgos concretos:

1. ~~**`CACHE_URL` por defecto es LocMemCache** sin prevención.~~ **HALLAZGO RETIRADO (falso positivo).** El proyecto **ya lo previene**: `core/checks.py:15` registra `@register(Tags.caches, deploy=True)` que devuelve el error `core.E001` si `IS_PRODUCTION` y el backend es LocMemCache, con hint accionable. Cubierto por `core/tests/test_checks_cache.py:24`. Hay además un segundo check propio, `core.W002` (`core/checks.py:47`), que avisa si la conexión a RDS no usa TLS. Está deliberadamente restringido a `--deploy` para no romper el `collectstatic` del build. **Es una de las mejores piezas del proyecto y la auditoría la pasó por alto en la primera pasada.**
2. ~~**django-axes bloquea solo por `username`**: un atacante rota usuarios y evade el límite.~~ **CORREGIDO.** Hoy `AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']` (lista PLANA, o sea usuario **O** IP). Se hizo en el orden obligatorio del punto 6: primero resolver la IP real detrás del balanceador, después endurecer. Y ese primer paso destapó que `AXES_IPWARE_PROXY_COUNT` estaba **INERTE** —faltaba el extra `[ipware]` y el orden de precedencia—, así que los ajustes existían pero no hacían nada. Verificado **ejecutándolo** con `manage.py verificar_ip_cliente`; vigilado por el check `core.E004`.
3. ~~**CSP con `'unsafe-inline'`** … `'unsafe-inline'` es el único bloqueante real para promoverla a política activa.~~ **CERRADO Y PARCIALMENTE CORREGIDO (2026-08-21).**

   La frase tachada contenía un **error de razonamiento**: `'unsafe-inline'` estaba en las **dos** políticas, la activa y la `_REPORT_ONLY`, así que nunca fue un bloqueante para promoverla. La única diferencia entre ambas eran los CDN retirados. La promoción se hizo sin tocar `'unsafe-inline'`: barridas las 116 plantillas, el único origen externo que queda es Google Fonts, la estricta pasó a ser la activa y la `_REPORT_ONLY` se borró.

   **`'unsafe-inline'` se queda en `script-src`, como decisión documentada.** Quitarlo se evaluó con números y no compensa: los nonces cubren los 13 `<script>` inline, pero **no** los `onclick=` de 20 plantillas ni los `style="…"` de 72 — más de 90 plantillas reescritas, con riesgo real de regresión. Y no cerraría ninguna amenaza viva: el renderizado en servidor está limpio (2 `|safe`, ambos sobre `help_text` de Django, que es constante; **cero `mark_safe`**), y el único vector real —texto sin escapar en los `innerHTML` del JS propio— se cerró por su origen (ver punto 3-bis). El razonamiento completo vive en el comentario de `settings.py`. Rehacer esto es tarea de un rediseño del frontend, no de esta auditoría.

   Vigilado por `core/tests/test_csp.py`, cuyo test central automatiza el riesgo que de verdad tiene una CSP: **falla en silencio**. Si una plantilla pide un origen fuera de la allowlist, el navegador lo bloquea sin que el servidor dé error. El test recorre las plantillas en cada push y falla nombrando el archivo.

3-bis. **HALLAZGO NUEVO, GRAVE — IDOR en `EmpleadoEditView`.** Encontrado al auditar la CSP, buscando quién controlaba los datos que llegan a `innerHTML`. `empleados/views/empleado.py:137` llevaba solo `LoginRequiredMixin`, mientras sus tres vistas hermanas (`EmpleadoDeleteView`, `EmpleadoUsuarioCreateView`, `AsignarRolesSalasView`) sí llevaban `AdminRequiredMixin`: un olvido, no una decisión. Cualquier explorador con sesión podía hacer POST a `/empleados/edit/<id>/` y reescribir la ficha de **cualquier** compañero — nombre, cédula, email, supervisor y `activo`, con el que se le deja fuera del sistema. Comprobado ejecutándolo: la respuesta era 302 y el nombre de la víctima quedaba reescrito.

   Encadenado, era también el vector de XSS: el nombre se interpola sin escapar en varios `innerHTML` del formulario de cambio de descanso, así que se ejecutaba en el navegador de quien lo abriera, supervisor incluido — y la CSP no lo frenaba, por el `'unsafe-inline'`. **Corregido** añadiendo `AdminRequiredMixin` (y metiendo el botón "Editar" dentro del `{% if is_admin_user %}` de la plantilla, donde faltaba por el mismo descuido). Cubierto por `empleados/tests/test_permisos_edicion_empleado.py`.

   Revisadas las demás fuentes de texto que llegan a `innerHTML` —salas, jornadas, tipos de solicitud— todas estaban ya tras `AdminRequiredMixin`. Ésta era el único hueco.
4. ~~`DB_PASSWORD` versionada en `docker-compose.hostdb.yml:36`.~~ **CORREGIDO (2026-08-22), y el riesgo real era otro.** La contraseña sale ahora de `.env` (gitignored) con `${DB_PASSWORD:?...}`. Pero medido, lo grave no era esa línea: `docker-compose.local.yml` publicaba el MySQL como `"3307:3306"` —o sea en `0.0.0.0`, accesible desde **cualquier equipo de la red** con una contraseña escrita en el mismo fichero— y el manual pedía crear `'swalp'@'%'`, un usuario alcanzable desde **cualquier host** con todos los privilegios. Corregidos los tres: puerto a `127.0.0.1`, usuario a `172.%`, contraseña fuera del repo. **NO se reescribe el historial de git**: para un repositorio privado con credenciales locales no compensa; lo que hace falta es no reutilizarla, y eso queda escrito donde se crea el usuario.
5. ~~Dockerfile sin `HEALTHCHECK`…~~ **`HEALTHCHECK` AÑADIDO** (verificado en el Dockerfile). Siguen abiertos, y son decisiones de despliegue más que de código: el multi-stage y mover el `migrate` fuera del `CMD` (esto último solo importa con ≥2 tareas — ver §despliegue, punto 2).
6. ~~**`--workers 3` hardcodeado**; falta `--max-requests`.~~ **CORREGIDO.** El `CMD` usa hoy `${GUNICORN_WORKERS:-3}` —ajustable por entorno sin reconstruir la imagen— y lleva `--max-requests 1000 --max-requests-jitter 100`.

   **Efecto colateral detectado el 2026-08-22, ~~NO corregido~~ CORREGIDO el 2026-08-23.** Se dijo entonces que la rotación *racy* «no molesta porque el fichero es secundario». Al medirlo, el diagnóstico se quedaba corto en la dirección contraria: **el fichero de log de producción no servía para nada**.

   - **No sobrevive.** No hay ningún volumen montado para logs, ni en el `Dockerfile` ni en los compose: vive en la capa efímera del contenedor y desaparece cuando ECS reinicia la tarea.
   - **No se puede leer.** El `tail -f` por SSH que lo justificaba no existe en Fargate: no hay máquina a la que entrar.
   - **Y encima corrompe.** Con `--workers 3`, al rotar los tres renombran a la vez; en Linux no da error, se pierden líneas y algún worker sigue escribiendo en un fichero ya desenlazado.

   Es decir: se pagaba una condición de carrera por escribir en un disco que se borra solo. `LOG_A_FICHERO` pasa a `False` en producción, y con ello desaparecen la rama de producción y el `RotatingFileHandler` — **el arreglo quita código**. El fichero queda como lo que era, una comodidad de desarrollo. Fijado por `core/tests/test_logging_destinos.py` (4 tests, verificados por mutación).
7. ~~Sin `pip-audit` ni Dependabot; no detecto vulnerabilidades abiertas.~~ **CORREGIDO — la segunda mitad era infundada.** La afirmación se hizo sin ejecutar ninguna herramienta. Al añadir `pip-audit` al CI (2026-08-19) reporta **15 vulnerabilidades conocidas en 3 paquetes**:
   - `django==5.2.16` → PYSEC-2026-3717, corregido en **5.2.17** (parche dentro de la misma LTS).
   - `sqlparse==0.5.3` → 5 avisos, corregidos en 0.5.4 / 0.6.0.
   - `cryptography==46.0.3` → 8 avisos; 5 se cierran en la serie 46.0.5-46.0.7, 3 exigen saltar a 48/49/50.
   
   Lección: **no afirmar «no hay CVE» sin correr la herramienta.** El proceso automático ya existe (job `seguridad` del CI, informativo a propósito para que un CVE nuevo no bloquee los merges). Falta decidir y aplicar las subidas de versión.
8. `settings.py` es un único archivo, en lugar de `settings/base|dev|prod.py`. **MATIZADO tras medirlo (2026-08-22): el número engaña.** Son 679 líneas, sí, pero **305 son comentarios** — el 45 %. El código real son ~374 líneas con **6 ramas** por entorno, y cuatro de ellas son de una sola línea (`default=X if IS_PRODUCTION else Y`).

    Y esos comentarios no son relleno: son el razonamiento que estas sesiones fueron acumulando —por qué `axes` necesita el extra `[ipware]`, por qué la CSP conserva `'unsafe-inline'`, por qué el logging no rota fuera de producción—. Partir el fichero los **dispersaría en tres**, y justo la pregunta que uno hace al abrir `settings.py` es «¿qué cambia entre entornos?», que hoy se responde leyendo seis líneas seguidas.

    **Sigue abierto**, pero baja de prioridad: el coste es real (los errores de configuración son silenciosos y peligrosos) y la ganancia, discutible. Reconsiderarlo si las ramas por entorno se multiplican.

---

## 6. Frontend (3,0)

- `static/js/cambio-turno/solicitar_doblada.js`: **3.297 líneas / 179 KB**. `solicitar_ct_permanente.js` 1.788, `solicitar_cambio_descanso.js` 1.396, `mis_turnos.js` 1.306.
- **Cero módulos ES**: 0 `<script type="module">` en 114 templates. Todo cuelga del ámbito global.
- Duplicación literal: `cargarCompaneros`, `cargarJornadaSolicitante`, `cargarMes`, `enviarSolicitud`, `actualizarResumen`, `renderTurnoYSalas`, `seleccionarPago`… aparecen 2-3 veces con el mismo nombre en distintos `solicitar_*.js`. `static/js/utils/dom-utils.js` y `services/datepicker-service.js` existen y apenas se usan.
- **94 `console.log`** enviados a producción.
- Templates: herencia bien usada (90 de 114 con `{% extends %}`), pero lógica excesiva en `aprobacion_exitosa.html` (50 `{% if %}`), `sanciones_list.html` (30), `restricciones_list.html` (26).
- `home.html` y `second.html` parecen restos de la plantilla AdminLTE — candidatos a borrar.

---

## 7. Verificación contra documentación oficial (Context7)

Esta sección registra qué se contrastó contra doc oficial y qué correcciones produjo, para que nadie tenga que
repetir el trabajo. **Importante:** el ~95 % del informe procede de lectura directa del código, no de Context7;
la herramienta sirve para doc de librerías, no para auditar arquitectura propia.

### Hallazgo nuevo — bloqueante de proxy en django-axes

El proyecto tiene `SECURE_PROXY_SSL_HEADER` configurado, es decir corre detrás de un ALB/proxy. La doc de axes
v6+ renombró los ajustes de proxy al prefijo `AXES_IPWARE_PROXY_*` y **no hay ninguno configurado**.
Consecuencia: axes vería la IP del balanceador para todos los usuarios. Si se añade `ip_address` a
`AXES_LOCKOUT_PARAMETERS` sin configurar antes `AXES_IPWARE_PROXY_COUNT`, **el quinto fallo de cualquier
empleado bloquea a toda la plantilla**. Este hallazgo es la razón por la que la Fase 1 se reestimó.

### Correcciones al informe original

| # | Lo que dije | Lo que dice la doc |
|---|---|---|
| 1 | `AXES_LOCKOUT_PARAMETERS = [["username"], ["ip_address"]]` | Sintaxis válida pero confusa. Plana `["username", "ip_address"]` = criterios independientes (OR). Anidada `[["username","ip_address"]]` = la pareja (AND). Para frenar rotación de usuarios hace falta la **plana**. |
| 2 | Bloquear solo por username es un descuido | Es una elección documentada por privacidad/GDPR. Defendible; solo deja abierto el credential stuffing. |
| 3 | `--disable-warnings` oculta los DeprecationWarning | No desactiva la captura, oculta el **resumen**. El arreglo es `filterwarnings`, no quitar el flag. |

### Confirmaciones (hallazgos que la doc respalda)

- **`@register(deploy=True)`**: la doc confirma el patrón, y al verificarlo se descubrió que **el proyecto ya lo implementa** (`core/checks.py`). Ver §5.1: hallazgo retirado.
- **`transaction.on_commit`** es el patrón oficial para efectos laterales → verifica que `solicitud_aprobacion_service.py:237,333,398,459` lo hace **bien**. Por eso NO figura como hallazgo negativo.
- **Fórmula de workers `2 × núcleos + 1`** → `--workers 3` hardcodeado es un antipatrón; falta `--max-requests`.
- **Deprecaciones**: lo obsoleto en 5.2 se elimina en Django 6.1.

### Punto abierto resuelto después

El informe original dejaba abierta la pregunta "¿cuántos proxies hay delante?". **Resuelta en §9 leyendo la
documentación de despliegue del propio proyecto: es 1 en ambas arquitecturas candidatas.**

### No verificable

**django-csp 4.0 no está indexado en Context7** (la búsqueda solo devuelve una librería JS homónima). La
sintaxis de nonces para eliminar `'unsafe-inline'` **no está verificada** contra doc oficial y no debe darse
por buena hasta consultar la doc de django-csp directamente en la Fase 4.

---

## 8. Estimación de esfuerzo

El cuello de botella no es escribir el código: es **validar que 64.700 líneas de reglas de negocio siguen
comportándose igual** con 65 % de cobertura y un solo test de integración.

| Fase | Calendario con revisión seria |
|---|---|
| 0 — Red de seguridad | 1-2 semanas |
| 1 — Endurecimiento producción | 3-4 días *(ver §7 y §9)* |
| 2 — Cerrar el OCP | 2-4 semanas |
| 3 — God Objects | 4-8 semanas |
| 4 — Frontend | 2-4 semanas |

**Total: 3-5 meses de calendario.** Comprimido y asumiendo riesgo: 6-8 semanas.

### Recomendación: no hacerlo todo

El ROI cae en picado después de la Fase 2.

- **Con dos-tres semanas:** Fase 0 + Fase 1 + cerrar el *fail-open* de `base_strategy.py:74-93`. Es el ~20 % del esfuerzo con el ~70 % de la reducción de riesgo.
- **Fase 3 solo bajo demanda:** cuando toque modificar `doblada_strategy`, se refactoriza *esa* parte. Un God Object que funciona, tiene tests alrededor y nadie va a tocar en 6 meses paga interés cero.
- **Condición innegociable:** la Fase 2 va **antes** de añadir un séptimo tipo de solicitud. Si ese tipo entra con las cadenas `if/elif` como están, la deuda pasa de 5 archivos a 6.

---

## 9. Decisión de despliegue pendiente: EC2 vs Fargate

Añadido el 2026-08-19 al detectar que la elección de arquitectura interactúa con tres hallazgos de esta
auditoría. La decisión **sigue abierta**; lo que sigue es el análisis, no una decisión tomada.

### El dato que suele decidirla mal

| | EC2 ([arquitectura §2](../05-referencia/deployment/99-aws/arquitectura-aws-rds-recomendada.md)) — **camino elegido (2026-09-04)** | Fargate ([§8](../05-referencia/deployment/99-aws/arquitectura-aws-rds-recomendada.md)) — **descartada por presupuesto**; su checklist se borró |
|---|---|---|
| CPU / RAM | t4g.small = **2 vCPU / 2 GB** | **0,5 vCPU / 1 GB** |
| Coste | ~$32/mes | ~$56/mes (1 task) · ~$74 (2 tasks) |

**Elegir Fargate *por rendimiento* con la especificación actual del checklist da 4× menos CPU por un 75 % más
de coste.** Y el propio análisis de arquitectura concluye que el cuello de botella es *"CPU/workers de la app,
no la BD"* (la base son 7,4 MB y cabe entera en RAM).

El argumento válido para Fargate es **operativo**, no de rendimiento: cero parches de SO/Nginx/systemd,
despliegue sin SSH (`build → push → update-service`), escalado por número de tasks. A un equipo pequeño eso
puede valer bastante más que los ~$24/mes de diferencia. Pero conviene elegirlo por ese motivo, no por otro.

### Si se elige Fargate, tres hallazgos de esta auditoría se activan

1. **Dimensionar a 1 vCPU / 2 GB, no 0,5/1.** Con 0,5 vCPU y `--workers 3` (hardcodeado en el `CMD` del Dockerfile) hay 3 procesos compitiendo por medio núcleo. La fórmula oficial `2 × núcleos + 1` da exactamente **3 workers para 1 vCPU**: eso convierte el `--workers 3` actual de accidente en decisión correcta. Ver §5.6.
2. **Con ≥2 tasks, `migrate` en el `CMD` deja de ser cómodo y pasa a ser una carrera real.** Hay que moverlo a un task ECS aparte antes de subir a alta disponibilidad. Ver §5.5.
3. **`CACHE_URL` deja de ser opcional** (≥2 tasks = ≥2 cachés). Aquí el proyecto está cubierto: `core.E001` impide desplegar mal. Ver §5.1.

### ~~Pieza no planificada en ninguno de los dos caminos~~ — RETIRADO (falso positivo)

Se afirmó que el runner del outbox (`procesar_email_outbox`) no aparecía en el checklist de Fargate. **Es
falso y estaba documentado en los tres sitios**: el checklist de Fargate (ya borrado; regla EventBridge
`rate(5 minutes)` con override del comando), `CHECKLIST_DESPLIEGUE_AWS_RDS.md:273-275` (cron cada 5 min) y el
paso a paso completo en `MANUAL_OUTBOX_CORREOS.md` §3, que cubre **ambos** caminos. Los tres lo marcan además
como "⚠️ paso obligatorio". No hay pieza suelta ni diferencia entre EC2 y Fargate en este punto.

### Qué NO depende de esta decisión

Toda la **Fase 0** (CI, ruff, `conftest.py`, cobertura) es idéntica en ambos caminos. Lo único que esperaba la
decisión era `AXES_IPWARE_PROXY_COUNT`, y resulta ser **1 en ambos casos** (un intermediario: Nginx o ALB;
ninguna arquitectura contempla CloudFront). **La decisión de despliegue no bloquea la refactorización.**

---

## Hoja de ruta recomendada (para cuando decidas ejecutar)

> **Baseline real de ruff medido el 2026-08-19** con `select = ["F", "E9"]`: **582 avisos** — F401 imports sin
> usar 470 · F405 `import *` 54 · F841 variables sin usar 21 · F541 f-string sin placeholder 19 · F811
> redefinición 16 · F821 nombre indefinido 2. **Ninguno es un bug de ejecución**: los 2 F821 son anotaciones
> de tipo en cadena (`solicitud: 'SolicitudCambio'` en `solicitud_factory.py:249,293`) que Python no evalúa;
> se arreglan con un import bajo `TYPE_CHECKING`. 513 son autocorregibles. La estimación previa de
> 1.000-1.500 incluía E501 (líneas largas), que no está en el `select` inicial.

**Fase 0 — Red de seguridad (1-2 semanas). Sin esto, refactorizar es a ciegas.**
1. ~~Crear `.github/workflows/ci.yml`.~~ **Ya existía**; ampliado el 2026-08-19 con ejecución en todas las ramas, `-n auto`, gate de cobertura ≥64 % y job de lint (ruff + bandit + pip-audit).
2. ~~`ruff` (lint + format) en `pyproject.toml` + `pre-commit`.~~ **HECHO.** Verificado el 2026-08-22: `[tool.ruff]` en `pyproject.toml`, `.pre-commit-config.yaml` activo, y `ruff check .` en cero durante toda la refactorización (es bloqueante en el CI).
3. ~~`conftest.py` raíz con fixtures compartidos.~~ **Corregido:** las fixtures de pytest no son accesibles
   desde `TestCase.setUp`, y 67 de los 68 archivos de test usan `TestCase`. Sustituido por
   `core/tests/factories.py`, con **funciones planas** llamables desde ambos mundos (Sesión 6).
4. ~~Subir `permisos` (38 %) y `solicitudes/domain` (24 %) al 70 %.~~ **Hecho en la Sesión 6**, con una
   corrección importante al diagnóstico: ver abajo.

> ✅ **SESIÓN 6 — cierre de la Fase 0 (2026-08-20).** Rama `refactor/fase0-cobertura-y-limpieza`.
>
> - **🔴 El «24 % de `solicitudes/domain`» era un promedio que mentía.** Medido por módulo:
>   `estado_machine.py` **100 %** y `bloqueo_partes.py` 92 % (ambos en uso), frente a `solicitud.py`,
>   `fechas.py` y `jornada.py` al **0 % y sin un solo importador** — ni estático ni dinámico.
>   No eran restos inofensivos: contenían **implementaciones paralelas y desfasadas de reglas críticas**.
>   `hay_conflicto_lifo()` era la versión ANTIGUA de la guardia LIFO (con el conjunto vacío devuelve «sin
>   conflicto», justo el fallo que cerró el patrón #25), y `VentanaCancelacion` decía 30 minutos cuando la
>   regla viva son **24 horas con consenso** (ADR 009). Conectarlos por error habría reintroducido bugs ya
>   cerrados. **Borrados** (100 sentencias), tras verificar que cada regla existe en el código vivo.
>   *Escribirles tests habría sido peor que no hacer nada: habría dado cobertura verde a código trampa.*
> - **`fechas_helper.py`: 0 % → 77 %** (22 tests). Aquí la hipótesis contraria resultó falsa: **no** estaba
>   muerto. Lo llama la rama de CAMBIO TURNO de `views/detalle.py:429` y alimenta el análisis de fecha que
>   ve el supervisor al aprobar. Los tests fijan la **matriz por tipo**, que es donde está la regla de
>   negocio: mantenimiento y temporada invalidan todos los tipos; festivo, sábado y domingo invalidan
>   los dos cambios de turno pero no la DOBLADA.
> - **🔴 Al escribir esos tests apareció una CONTRADICCIÓN entre la pantalla y el motor.** El helper daba
>   por válido un CT en día **festivo** y en **sábado**, mientras `cambio_turno_strategy.py:179,185` los
>   rechaza. La regla real, confirmada por el usuario el 2026-08-20: **los festivos solo se cambian con
>   una DOBLADA, nunca con un CT** — en festivo una jornada trabaja el día completo (AM+PM) por rotación,
>   así que no hay un AM y un PM que intercambiar; el intercambio válido es festivo por festivo.
>   El comentario del código decía «Permite festivos si ambos tienen jornada» y ni siquiera comprobaba
>   esa condición: descartaba el festivo siempre. Corregidos los dos casos.
>   *No abría la puerta a crear solicitudes prohibidas —eso lo cierra la strategy—, pero mostraba «fecha
>   válida» al supervisor en la pantalla donde decide si aprobar.* Es el argumento de la Fase 2 en
>   miniatura: la misma regla escrita dos veces acaba divergiendo.
> - **`permisos/views.py`: 50 % → 61 %** (9 tests), atacando el bloque sin cubrir más grande: la creación
>   de permisos, con sus cuatro reglas (sanción activa, día que se trabaja según `estado_dia`, cierre
>   semanal, y el aviso cuando no hay supervisor). Los tests van por la vista, no por el formulario,
>   porque tres de las cuatro reglas viven en `form_valid`/`dispatch`.
> - **`core/tests/factories.py`**: 55 archivos repetían el montaje de `User` + `Empleado` y 40 el de
>   `Jornada`, cada uno eligiendo a mano cédulas y nombres de usuario sobre campos ÚNICOS. Ahora se
>   generan solos.
>
> Detalle metodológico que se repitió dos veces: **una fecha fija en un test de turnos es una trampa.** Si
> cae en descanso por la rotación, el test falla por el motivo equivocado y parece un bug del código. Las
> fechas se preguntan a `estado_dia`.
>
> Suite: **991 → 1022 tests**. ruff en cero.

> ✅ **FASE 1 EJECUTADA el 2026-08-20** (rama `chore/fase1-endurecimiento-produccion`). Resumen de lo que
> cambió y de lo que deliberadamente NO cambió:
>
> - **`print()` en producción: 6 → 0.** El `[ERROR]` de `notificacion_service.py` pasa a `logger.exception`
>   (iba a stdout sin traza ni `request_id`, se perdía del pipeline); los 3 de
>   `api_disponibles_ct_preview.py` eran duplicados literales del `logger` de la línea de encima y se borraron.
> - **`except: pass`: 12 → 4, y los 4 restantes documentados uno a uno.** No se cambió ningún flujo de
>   control: solo se añadió visibilidad. Dos eran *fail-open* contra el patrón #25 y quedaron marcados a la
>   espera de decisión de dominio: **ya están cerrados** (ver el bloque de la Sesión 5, abajo).
> - **Deprecación que rompía en Django 6.0:** `solicitudes/models.py` usaba `CheckConstraint(check=...)`,
>   eliminado en 6.0. Cambiado a `condition=` (sin migración nueva). Estaba emitiéndose desde hacía tiempo y
>   `--disable-warnings` lo ocultaba — exactamente lo que este informe señalaba en §4.
> - **`pytest.ini`:** los `RemovedInDjango60/61Warning` pasan a **error**, para que una deprecación nueva
>   falle la suite en vez de acumularse hasta que la migración a Django 6 sea un muro.
> - **axes:** `AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']` (lista **plana**) y
>   `AXES_IPWARE_PROXY_COUNT` configurable, 1 en producción. Protegido por un **check nuevo, `core.E003`**,
>   que aborta el despliegue si hay proxy + bloqueo por IP + proxies sin contar — la combinación que dejaría
>   fuera a toda la plantilla. 11 tests nuevos en `core/tests/test_checks_axes.py`.
> - **Dockerfile:** `HEALTHCHECK` sobre `/health/` con `http.client` (la imagen slim no trae curl) que acepta
>   cualquier respuesta < 500, porque en producción `ALLOWED_HOSTS` hace que una petición a 127.0.0.1
>   responda 400 y exigir 200 mataría el contenedor en bucle. Añadido `--max-requests` con jitter.
> - **`--workers` sigue en 3, y es deliberado.** Se probó la fórmula `2 × nproc + 1` del informe y **es
>   incorrecta dentro de un contenedor**: `nproc` devuelve los núcleos del ANFITRIÓN, no los del task
>   (Fargate limita por cuota de cgroup, que nproc no ve). En una máquina de 14 núcleos daba 29 workers. Se
>   deja el valor conocido y se expone `GUNICORN_WORKERS` con la tabla por tamaño de task.
> - **`sonar.python.version`: 3.14 → 3.12**, la de producción.
> - **NO se rotó la contraseña de `docker-compose.hostdb.yml`:** es de una base local ya inicializada con
>   ella; cambiarla rompería el entorno de desarrollo a cambio de nada, porque el valor viejo sigue en el
>   historial de git de todas formas. Lo que importa es que la de producción nunca se versione.

> ✅ **SESIÓN 5 — cierre de los pendientes de la Fase 1 (2026-08-20).** Los cuatro puntos que quedaban:
>
> - **Los dos *fail-open* del patrón #25, CERRADOS.** No se cerraron a ciegas: primero se auditaron los
>   llamadores, que es lo que convertía la decisión en técnica y no de negocio.
>   - `validar_no_dia_mantenimiento()`: sus **tres** llamadores ya garantizan fecha parseable
>     (`cambio_turno_strategy.py:67` rechaza el vacío y la `:75` parsea antes; `d_fds_strategy.py:154-155`
>     pasan `strftime()` de objetos `date`). La rama era inalcanzable por el flujo normal, así que cerrarla
>     **no rechaza ninguna petición legítima** — pero deja la garantía viviendo en la validación y no en el
>     orden de llamada.
>   - Cierre semanal de la doblada permanente: `solicitar_doblada_permanente.js:586` solo envía el `value`
>     de checkboxes marcados (fechas ISO generadas por el servidor). Lo único que se empieza a rechazar es
>     un POST malformado, que es justo lo que debe rechazarse.
>   - 6 tests nuevos (`test_auditoria_fail_open.py`), con **prueba negativa**: 3 fallan contra el código
>     anterior. Incluyen los controles del #25 — "fallar cerrado" no puede degenerar en "bloquear siempre".
> - **🔴 `AXES_IPWARE_PROXY_COUNT` estaba puesto y era INERTE. Fallo de la Fase 1, corregido aquí.**
>   `django-ipware` **no estaba instalado** —axes lo trae como extra opcional (`django-axes[ipware]`)— y sin
>   él `get_client_ip_address` ignora todos los ajustes `AXES_IPWARE_*` y devuelve `REMOTE_ADDR`. Además,
>   `AXES_IPWARE_META_PRECEDENCE_ORDER` por defecto vale `("REMOTE_ADDR",)`, así que ni instalándolo se
>   miraría `X-Forwarded-For`. Detrás del ALB eso es **exactamente la denegación de servicio que la Fase 1
>   creía haber evitado**, y `core.E003` la aprobaba. Confirmado contra la doc oficial vía Context7.
>   Corregido: extra obligatorio en `requirements.txt`, `AXES_IPWARE_META_PRECEDENCE_ORDER` activo **solo**
>   cuando hay proxy declarado (confiar en la cabecera sin proxy permitiría falsear la IP en cada intento) y
>   **check nuevo `core.E004`** que caza las dos causas. 9 tests más.
>   *Lección, anotada en `PROTECTION_PATTERNS.md`: una guardia se verifica EJECUTÁNDOLA, no leyendo su
>   configuración.* Lo destapó `manage.py verificar_ip_cliente`, comando nuevo que resuelve una IP de verdad.
> - **`docker build` REAL ejecutado** (Docker Desktop arrancado): imagen de 916 MB, `appuser` no root
>   (uid 1000), 2 406 estáticos recolectados, bundle CA de RDS presente, Python 3.12.14, gunicorn 23.0.0.
>   El `HEALTHCHECK` se probó **dentro del contenedor**: devuelve `400 DisallowedHost` y **exit 0**, tal
>   como se diseñó. Ya no es una afirmación del comentario: está comprobado.
> - **axes en staging:** queda un paso humano, pero ya no a mano. `python manage.py verificar_ip_cliente`
>   dice si axes ve al cliente o al balanceador, y trae el procedimiento con tráfico real.
>
> Suite: **991 tests** (976 → 991). ruff en cero. `check --deploy` limpio en configuración de producción.

**Fase 1 — Endurecimiento de producción (~3-4 días).** *Reestimada dos veces: al alza por el bloqueante de
proxy de axes, y de nuevo a la baja al resolverse esa incógnita en §9. Queda la verificación en staging.*
5. ~~`@register(deploy=True)` para la caché.~~ **Ya existe** en `core/checks.py`. En su lugar: añadir `manage.py check --deploy` como paso obligatorio del pipeline de despliegue, que es lo que falta para que el check sirva de algo.
6. **axes, en este orden obligatorio** (invertirlo tira a todos los empleados fuera):
   a. `AXES_IPWARE_PROXY_COUNT = 1`. **Resuelto (ver §9):** ambas arquitecturas candidatas tienen exactamente un intermediario — Nginx en el camino EC2, ALB en el camino Fargate — y ninguna contempla CloudFront. El valor es 1 se decida lo que se decida, así que **esto ya no bloquea nada**.
   b. Verificar **en staging** que axes ve la IP real del cliente y no la del intermediario.
   c. Solo entonces: `AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]` (lista **plana** = bloqueo por usuario O por IP; la anidada `[["username","ip_address"]]` cuenta la pareja y NO frena la rotación de usuarios).

   *Sin el paso (a), axes vería la IP del intermediario para todos: 5 fallos de cualquier empleado bloquearían a toda la plantilla una hora.*
7. ~~Sustituir los 6 `print()` por `logger`, auditar los 12 `except: pass`.~~ **HECHO.** Verificado con AST el 2026-08-22: quedan **2 `print()`**, ambos legítimos (un script de `tools/` y una migración, donde imprimir ES la salida esperada), y **6 `except ...: pass`**, todos capturando un tipo CONCRETO (`ValueError`, `OSError`, `TypeError`, `ImportError`). No queda ningún `except:` desnudo ni `except Exception: pass`, que era la preocupación real.
8. `HEALTHCHECK` en Dockerfile; `--workers $((2*$(nproc)+1))` y `--max-requests` en el `CMD`; alinear `sonar.python.version` a 3.12; rotar la contraseña de compose.
9. ~~`filterwarnings` en `pytest.ini`.~~ **HECHO.** `pytest.ini` convierte en error los `RemovedInDjango60Warning` y `RemovedInDjango61Warning`.
10. ~~Planificar el runner del outbox de correos.~~ **Ya estaba planificado** en los dos checklists y en `MANUAL_OUTBOX_CORREOS.md` §3, marcado como paso obligatorio. Ver §9.

**Fase 2 — Cerrar el OCP (2-4 semanas). El mayor retorno arquitectónico.**
11. ~~Añadir a `SolicitudStrategy`: `revertir_cambios()`, `detalle()`, `parse()`, `fechas_objetivo()`.~~ **HECHO en la Fase 2.** El contrato de la base incluye hoy `detalle()`, `parsear_datos()`, `revertir_cambios()`, `reaplicar()`, `pares_que_reescribe()`, `fecha_valida()` y `validar_campos_requeridos()`. Algunos nombres difieren de los propuestos porque se eligieron según lo que la pieza hace de verdad, no según el boceto.
12. ~~Mover ahí las 5 cadenas `if/elif`.~~ **HECHO en la Fase 2.** Verificado el 2026-08-22: cero comparaciones contra un nombre de tipo en los cinco ficheros. La única coincidencia que queda (`detalle.py:106`) es un COMENTARIO que documenta la cadena que se retiró. Vigilado por el trinquete `solicitudes/tests/test_arquitectura_dispatch_por_tipo.py` (punto 14).
13. ~~Convertir `_datos_desde_solicitud` en `@abstractmethod` — cerrar el *fail-open* de `base_strategy.py:74-93`.~~ **HECHO (2026-08-21), y eran TRES fail-opens, no uno.** El informe veía solo el defecto por defecto de la base. Auditando aparecieron dos más, ambos confirmados **ejecutándolos** antes de tocar nada: (b) las tres estrategias con detalle devuelven `None` si falta su fila, y eso *aprobaba* con el mensaje `(True, 'Sin re-validación para este tipo')`; y (c) `SolicitudFactory.revalidar_para_aprobar` usaba `get_strategy`, que devuelve `None` cuando el tipo está **inactivo** — devolvía `(True, '')`, o sea que **desactivar un tipo con solicitudes pendientes hacía que se aprobaran todas sin comprobar ninguna**. Es la misma confusión que ya se corrigió al revertir: `activo` significa «se pueden CREAR solicitudes de este tipo», no dice nada sobre las que ya existen. Los tres fallan ahora cerrado. Queda **uno a propósito** —el `except Exception` de la factory— porque bloquear todas las aprobaciones por un bug en la red de seguridad es peor que aprobar algo que quizá dejó de ser válido; está declarado en un test para que sea decisión visible y no descuido. Cubierto por `solicitudes/tests/test_failopen_revalidacion.py`.
14. ~~Test de arquitectura que falle si aparece un `if tipo == "..."` fuera de las strategies.~~ **HECHO (2026-08-21), como TRINQUETE y no como cero absoluto.** Exigir cero habría forzado un refactor discutible: de las 4 comparaciones que quedan, tres **enrutan a flujos de orquestación completos** (dos solicitudes atómicas que solo tienen sentido juntas, alta multi-compañero) o son banderas de presentación — meterlas en una estrategia sería la misma dependencia, escondida. Solo una (`descanso_solicitud_service.py`, `_mitad_pago`) es deuda real y queda anotada como tal. Se congelan como base conocida que **solo puede menguar**, con un segundo test que falla si alguien migra una y no baja el número, para que la lista no deje hueco. El propio test **encontró 4 casos que el grep manual se había dejado**. Ver `solicitudes/tests/test_arquitectura_dispatch_por_tipo.py`.

**Fase 3 — Descomponer los God Objects (4-8 semanas).**
15. `doblada_strategy.validar_solicitud` (515 L) → mover a `services/validators/`. **A MEDIAS.** El método se descompuso de **512 a 244 líneas** en ocho métodos con nombre (`_validar_pago_sabado`, `_validar_dia_no_comprometido`, `_validar_cobertura_en_pago`…), que era el problema real: 512 líneas no se pueden leer. **NO se movió a `services/validators/`**, y hay una razón para dudarlo: esos ocho métodos leen del objeto `EntradaDoblada` y de `self`, así que moverlos exigiría pasar la estrategia entera o duplicar el contexto. Antes de hacerlo conviene medir qué gana el traslado más allá de la simetría con los cuatro validadores que ya existen.
16. ~~Vaciar de negocio `views/doblada_api.py`, `views/api_turno_jornada.py` y `permisos/views.py`.~~ **CERRADO (2026-08-22), aunque no como decía el enunciado.**

    **`permisos/views.py`:** medido, no era un God Object —25 vistas, la mayor de 97 líneas—. Su problema era de TESTS, no de tamaño: los caminos donde el permiso cambia de estado no tenían ninguno. Cubiertos; la cobertura pasó del 61 % al 71 %.

    **`api_turno_jornada.py`:** el `get()` de 310 líneas se troceó a **167**, en cuatro cortes (`_responder_jornada_base`, `_detectar_descanso`, `_normalizar_jornada_mostrada`, `_extras_sabado`), a mano y ejecutando los 26 tests después de cada uno.

    Se hizo AHORA y no antes porque su cobertura funcional era **CERO**: el 5 % que reportaba el CI eran los imports y las líneas de `class` y `def`. Cortar sin red habría sido a ciegas.

    **Queda dentro a propósito** la detección de doblada y el bloque de festivos: ese muta CINCO variables compartidas en secuencia, así que extraerlo obligaría a devolver cinco valores y dejaría el llamador PEOR. Sacarlo bien pide un objeto de contexto — otro refactor, otra decisión.

    **`doblada_api.py`** (504 líneas, un `get()` de 342) sigue sin tocar, y por el mismo motivo que tenía el anterior: hay que medir su cobertura y ponerle red antes de cortar nada.

    Lo que este punto destapó de camino, y valía más que el troceo: el `{}` que las estrategias devolvían al tragarse una excepción, que hacía responder `200` con `tiene_turno: true` y un objeto vacío ante un `explorador_id` inventado en la URL.
17. ~~`SolicitudOrchestrator` deja de devolver `JsonResponse`; devuelve un `Result` y la vista lo serializa.~~ **REENCUADRADO (2026-08-21): era el síntoma, no la causa.** Medido, el `Result` cuesta **~42 puntos de retorno y 20 archivos de test** para desacoplar de HTTP una capa cuyo **único consumidor es una vista HTTP** (el único consumidor no-HTTP que existe es un script de depuración desechable). Coste sin comprador.

    Lo que sí había, una capa más abajo: el error `requiere_cambio_turno_previo` viajaba **metiendo un JSON dentro del mensaje de texto** —tres `json.dumps` en `doblada_strategy`, un `json.loads` arriba— con la forma del diccionario escrita **tres veces sin definición única**. Así fue exactamente como un refactor renombró la clave `fecha_pago` en dos de los tres sitios sin que nadie se enterara: el frontend hace `data.fecha_pago || fechaPagoInput.value` y el `||` tapaba la avería. Había además un segundo lector que decidía si un mensaje era JSON **mirando si contenía una llave `{`**.

    Resuelto con `services/errores_validacion.py`: la forma se define una vez, se reconoce con `isinstance` y el mensaje vuelve a ser legible en los logs. Radio: 3 productores, 2 consumidores, 1 ayudante de test. Los tests del contrato **mejoraron** al hacerlo — antes inspeccionaban el código fuente contando apariciones literales porque no había objeto que interrogar; ahora comprueban comportamiento.

    El `Result` queda pendiente y sin prisa: reconsiderarlo **si aparece un segundo consumidor** (un comando, una tarea en segundo plano, otra forma de API). Hasta entonces es refactorizar por principio.
18. ~~Sacar el ORM de `domain/bloqueo_partes.py:62`.~~ **HECHO (2026-08-21), pero el planteamiento estaba del revés: ahí no sobra ORM, sobra el archivo en esa carpeta.**

    `bloqueo_partes` no es dominio: es una primitiva de bloqueo del motor. Su razón de existir ES el `SELECT ... FOR UPDATE`, y todo lo que importa de ella es específico de MySQL —el nivel REPEATABLE READ, el `order_by` que evita interbloqueos, y el `list()` que fuerza la ejecución (sin consumir el queryset el lock **no llega a tomarse**)—. Lo que parece negocio, qué exploradores intervienen, son diez líneas de leer atributos.

    Un repositorio o un puerto delante habría envuelto **una línea** en ceremonia, y la abstracción mentiría: `select_for_update` no es un concepto de dominio, es SQL. Un `bloquear_empleados()` genérico escondería que el orden importa y que el lock dura hasta que confirma la transacción más externa. Y romperlo sería **silencioso**: un lock mal tomado no falla en los tests, solo bajo concurrencia real.

    Solución: mover el archivo a `services/` sin tocar una línea de su lógica (4 imports, 2 archivos). `domain/` queda genuinamente libre de ORM, que era el objetivo de fondo. Vigilado por `solicitudes/tests/test_arquitectura_domain_sin_orm.py`, cuya segunda comprobación —importar el dominio SIN Django configurado— manda sobre la primera: buscar nombres es una aproximación, esa es la propiedad en sí.

    Nota metodológica: la heurística del test marcó también el `solicitud.save()` de `estado_machine`. En vez de darlo por malo se comprobó **ejecutándolo**: el módulo corre entero con un objeto falso y sin Django, porque nunca importa Django. Prohibirlo habría obligado a partir la función en dos por una regla de estilo, sin ganar nada.

**Fase 4 — Frontend (2-4 semanas).**
19. ~~Extraer los `<script>` inline de los 3 `solicitar_*.html` → eliminar `'unsafe-inline'` del CSP.~~ **DESCARTADO tras auditar (2026-08-21): era sobreingeniería.** Los `<script>` inline no son la causa raíz que el informe suponía. Medido: 13 plantillas con `<script>` inline (los nonces sí las cubren), pero **20** con `onclick=` y **72** con `style="…"`, que los nonces **no** cubren — habría que reescribir el marcado a `addEventListener` y a clases CSS. Son más de 90 plantillas, con riesgo real de regresión visual y funcional en una app que entra a producción. Y no cerraría ninguna amenaza viva (ver §riesgo 3). **Lo que sí se hizo** en su lugar: promover la política estricta, cerrar el IDOR de `EmpleadoEditView` —que era el vector real— y automatizar la vigilancia de la allowlist. Reconsiderar solo si algún día se rehace el frontend.
20. ~~Factorizar las funciones duplicadas de `cambio-turno/*.js` a los `utils/` y `services/` existentes.~~ **DESCARTADO tras medirlo (2026-08-22): la duplicación es de NOMBRES, no de código.**

    Las funciones que se repiten en varios formularios tienen **firmas distintas**, o sea que no son copias sino implementaciones paralelas: `notificar(icon,title,html)` frente a `(icon,title,text)`; `verificarDiaFestivo(fecha,indicador,descripcion)` frente a `verificarDiaFestivo(fecha)`; `renderTurnoYSalas` con 3 parámetros frente a la de doblada con 6; `enviarSolicitud()` frente a `enviarSolicitud(confirmarRestriccion)`. Unificarlas no sería factorizar: sería reescribir comportamientos distintos hasta hacerlos uno.

    Duplicación **literal** encontrada: **una** función de 4 líneas (`notificar` en `solicitar_d_fds.js:47` y `solicitar_doblada_permanente.js:42`, idénticas byte a byte). Extraer 4 líneas no compensa el riesgo, porque —y esto es lo que decide— **el proyecto no tiene NINGUNA infraestructura de pruebas para JavaScript**. Cero tests sobre 9 790 líneas de formularios. Refactorizar ahí es exactamente lo que la Fase 0 quería evitar.

    **PRIMER PASO DADO (2026-08-22): la red ya existe.** `tests_js/` con **76 tests** sobre `date-utils.js`, `validators.js`, `api-client.js` y las funciones puras de `dom-utils.js`, en un job **bloqueante** del CI que corre en **11 segundos**. Sin `package.json` ni dependencias: se usa el runner que trae Node, porque los `utils` ya exponían `module.exports` además del global y fueron probables **sin tocar una línea de código de producción**.

    Y encontró dos fallos el primer día, los dos de zona horaria y los dos por parsear `new Date('YYYY-MM-DD')`, que es medianoche **UTC**:

    * `getMonthRange` retrocedía un día en husos positivos (enero de 2026 salía `2025-12-31 .. 2026-01-30` en Madrid o Tokio). Latente: la app corre en UTC-5. Corregido, y verificado que la salida en Bogotá y UTC es **idéntica** a la anterior en 168 meses comparados.

    * `Validators.futureDate` **rechazaba HOY** y `pastDate` daba HOY por pasado, en Colombia — pese a que el mensaje dice «hoy o una fecha futura». Corregido.

    `api-client.js` se cubrió **sin jsdom** tras medirlo: solo usa `fetch` (nativo en Node), `document.cookie` (una cadena) y `document.querySelector` (para leer un `.value`). No recorre el árbol ni escucha eventos, así que un doble es **fiel**. Incluye el token CSRF, con un test que exige `startsWith` y no `includes` para que una cookie `xcsrftoken` no pueda suplantarlo.

    Queda sin cubrir lo que sí manipula el DOM (la otra mitad de `dom-utils`, `codigo-referencia`, `datepicker-service` y los formularios). Ahí fingir `classList` o `appendChild` sería **peor que no probar**: el doble pasa siempre y daría por bueno código que en el navegador falla. Eso espera a jsdom. Ver `tests_js/README.md`.

    **HALLAZGO QUE REENFOCA ESTE PUNTO (medido el 2026-08-22): la capa `utils/` está casi entera sin usar.** Las cuatro plantillas de solicitudes cargan `date-utils`, `validators`, `api-client` y `dom-utils`, y los usos reales son:

    | Módulo | Cargado en | Usos |
    |---|---|---|
    | `date-utils.js` | 4 plantillas | **0** |
    | `validators.js` | 4 plantillas | **0** |
    | `api-client.js` | 4 plantillas | **0** (solo aparece en comentarios) |
    | `dom-utils.js` | 4 plantillas | **1** — `DomUtils.ready()` en `core/app.js`, con guarda |
    | `codigo-referencia.js` | 1 plantilla | 8 — este sí se usa |

    Eso explica qué quiso decir este punto: **la duplicación no está entre formularios, sino entre los formularios y estos utils**. Cada `solicitar_*.js` reimplementó por su cuenta lo que ya existía al lado. Por eso las funciones con el mismo nombre tienen firmas distintas: no son copias, son reinvenciones.

    El trabajo real, entonces, es **hacer que los formularios usen los utils** — un refactor de comportamiento sobre 9 790 líneas sin cobertura, que sigue necesitando jsdom antes.

    **NO se borran los utils muertos**, aunque sean ~700 líneas que cuatro páginas descargan para nada: son el DESTINO previsto de ese refactor. Borrarlos dejaría el punto sin sitio adonde ir, y los dos bugs de zona horaria que la red encontró y corrigió habría que volver a escribirlos desde cero.
21. Migrar a `<script type="module">`; ~~eliminar los 94 `console.log`.~~ **Los `console.log` HECHOS (2026-08-22): 92 eliminados** (los otros 2 son de `adminlte`, código de terceros, y no se tocan).

    Todos eran restos de depuración con prefijo `[DEBUG]` que viajaban al navegador de cada usuario volcando estado interno —meses cargados, contenido de `Set`s y, en siete de ellos, `new Error().stack`—. Reparto: `mis_turnos.js` 69, `solicitar_ct_permanente.js` 14, `solicitar_doblada.js` 7, y uno en `core/app.js` y en `calendario_festivos_mantenimiento.js`.

    Sin tests de JS, el borrado se hizo por **balance de paréntesis** (siete llamadas eran multilínea y abrían un objeto literal: borrarlas por líneas habría dejado las propiedades sueltas), con **autoverificación** que aborta si alguna línea eliminada contiene `function`, `return`, `if (`, `=>` o una declaración, y con `node --check` en los cinco ficheros tocados.

    La migración a `<script type="module">` **sigue pendiente** y comparte el bloqueante del punto 20: sin red de pruebas de JS no debería tocarse.

---

## Cómo verificar el progreso

- `pytest --cov --cov-fail-under=65` (subir el umbral 5 puntos por fase).
- `python manage.py check --deploy` — incluye los checks propios `core.E001` (caché) y `core.W002` (TLS a RDS) de `core/checks.py`. Debe ser un paso **obligatorio del pipeline de despliegue**, no manual.
- `ruff check .` — línea base y tendencia descendente.
- Métrica de OCP: `grep -rn 'tipo.*==.*DOBLADA\|CT PERMANENTE' --include=*.py` fuera de `strategies/` → objetivo 0.
- Métrica de código limpio: ningún método por encima de 80 líneas (hoy hay 25).
