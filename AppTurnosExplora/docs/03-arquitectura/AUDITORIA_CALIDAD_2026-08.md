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
| django-csp 4.0 | — | **No indexado en Context7.** Nonces sin verificar contra doc oficial |

---

## Veredicto: **55 % de adherencia a buenas prácticas**

| Dimensión | Peso | Nota | Comentario |
|---|---|---|---|
| Arquitectura por capas | 20 % | **6,0** | Las capas existen y están bien nombradas; se saltan sistemáticamente |
| Principios SOLID | 20 % | **3,6** | SRP 3 · OCP 3 · LSP 5 · ISP 4 · DIP 3 |
| Código limpio | 15 % | **4,0** | Naming y docstrings excelentes; tamaños de función catastróficos |
| Tests | 15 % | **6,5** | 959 tests reales, 65 % cobertura, sin factories ni `conftest.py` |
| Seguridad y configuración | 10 % | **8,0** | Lo mejor del proyecto junto con la documentación |
| Tooling / CI | 10 % | **6,0** | *Corregido:* el CI existía (falso positivo de la 1ª pasada). Faltaba linter y pre-commit |
| Frontend | 5 % | **3,0** | 47 scripts globales, duplicación masiva |
| Documentación | 5 % | **9,0** | Manuales, ADRs, docstrings que explican el *porqué*. Ejemplar |

**Total ponderado: 5,50 / 10 → 55 %** *(revisado al alza tras retirar dos falsos positivos; ver §5.1 y §4)*

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

1. `base_strategy.py:74-93`: `_datos_desde_solicitud` devuelve `None` por defecto y `revalidar_para_aprobar`
   traduce ese `None` a `return True, 'Sin re-validación para este tipo'`. **Una strategy futura que olvide
   implementar el hook aprobará solicitudes sin revalidar, en silencio.** Es un *fail-open*: el default inseguro.
   Hoy las 6 strategies lo implementan, así que el bug está latente, no activo.
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
**116 ramas**, `ct_permanente_helper.py` **102**, `cambio_descanso_strategy.py` **93**.

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
2. **django-axes bloquea solo por `username`** (`settings.py:341`, `AXES_LOCKOUT_PARAMETERS = ['username']`): un atacante rota usuarios y evade el límite. *Matizado tras Context7:* la doc de axes documenta `['username']` como elección legítima por privacidad/GDPR (evita almacenar IPs), así que es una decisión defendible, no un descuido — pero deja abierto el credential stuffing. **Ver §7 para el bloqueante de proxy antes de cambiarlo.**
3. **CSP con `'unsafe-inline'`** en `script-src` y `style-src`, incluso en `_REPORT_ONLY`. La causa raíz son los 14 bloques `<script>` inline en `solicitar_doblada.html`, `solicitar_ct_permanente.html` y `solicitar_cambio_turno.html`. *Nota positiva:* la política `_REPORT_ONLY` ya eliminó jsDelivr, cdnjs e ionicons — solo queda Google Fonts. **`'unsafe-inline'` es el único bloqueante real** para promoverla a política activa; el proyecto está más cerca de lo que sugiere el resto del informe.
4. `DB_PASSWORD: swalp_docker_2026` versionada en `docker-compose.hostdb.yml:36`. Es local, pero queda en el historial de git.
5. Dockerfile sin `HEALTHCHECK` pese a que `/health/` y `/health/ready/` ya existen y están exentos de redirect; no es multi-stage; el `CMD` ejecuta `migrate` antes de gunicorn (carrera con ≥2 tareas, ya auto-documentada).
6. **`--workers 3` hardcodeado** en el `CMD` del Dockerfile, independientemente de la máquina. La doc de Gunicorn recomienda `2 × núcleos + 1`. Con 2 vCPU faltan workers; con 0,5 vCPU sobran y compiten por CPU. Falta también `--max-requests` para reciclar workers (mitiga fugas de memoria). Y esos 3 workers **confirman** el riesgo del punto 1: 3 cachés locmem incoherentes.
7. ~~Sin `pip-audit` ni Dependabot; no detecto vulnerabilidades abiertas.~~ **CORREGIDO — la segunda mitad era infundada.** La afirmación se hizo sin ejecutar ninguna herramienta. Al añadir `pip-audit` al CI (2026-08-19) reporta **15 vulnerabilidades conocidas en 3 paquetes**:
   - `django==5.2.16` → PYSEC-2026-3717, corregido en **5.2.17** (parche dentro de la misma LTS).
   - `sqlparse==0.5.3` → 5 avisos, corregidos en 0.5.4 / 0.6.0.
   - `cryptography==46.0.3` → 8 avisos; 5 se cierran en la serie 46.0.5-46.0.7, 3 exigen saltar a 48/49/50.
   
   Lección: **no afirmar «no hay CVE» sin correr la herramienta.** El proceso automático ya existe (job `seguridad` del CI, informativo a propósito para que un CVE nuevo no bloquee los merges). Falta decidir y aplicar las subidas de versión.
8. `settings.py` es un único archivo de 584 líneas con 5 ramas por entorno, en lugar de `settings/base|dev|prod.py`.

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

| | EC2 ([arquitectura §2](../05-referencia/deployment/arquitectura-aws-rds-recomendada.md)) | Fargate ([§8](../05-referencia/deployment/arquitectura-aws-rds-recomendada.md), [checklist](../05-referencia/deployment/CHECKLIST_DESPLIEGUE_FARGATE.md)) |
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
falso y estaba documentado en los tres sitios**: `CHECKLIST_DESPLIEGUE_FARGATE.md:190-192` (regla EventBridge
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
2. `ruff` (lint + format) en `pyproject.toml` + `pre-commit`. Coste bajo: hoy no hay ningún linter.
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
7. Sustituir los 6 `print()` por `logger`, auditar los 12 `except: pass` (prioridad: `solicitud_orchestrator.py:314,358,450`).
8. `HEALTHCHECK` en Dockerfile; `--workers $((2*$(nproc)+1))` y `--max-requests` en el `CMD`; alinear `sonar.python.version` a 3.12; rotar la contraseña de compose.
9. `filterwarnings` en `pytest.ini` para hacer visibles los `DeprecationWarning`.
10. ~~Planificar el runner del outbox de correos.~~ **Ya estaba planificado** en los dos checklists y en `MANUAL_OUTBOX_CORREOS.md` §3, marcado como paso obligatorio. Ver §9.

**Fase 2 — Cerrar el OCP (2-4 semanas). El mayor retorno arquitectónico.**
11. Añadir a `SolicitudStrategy`: `revertir_cambios()`, `detalle()`, `parse()`, `fechas_objetivo()`.
12. Mover ahí las 5 cadenas `if/elif` (`cancelar_solicitud.py:651`, `detalle.py:124`, `solicitud_request_parser.py:40`, `doblada_snapshot_service.py:258`, `fechas_helper.py:135`).
13. Convertir `_datos_desde_solicitud` en `@abstractmethod` — cerrar el *fail-open* de `base_strategy.py:74-93`.
14. Test de arquitectura que falle si aparece un `if tipo == "..."` fuera de las strategies.

**Fase 3 — Descomponer los God Objects (4-8 semanas).**
15. `doblada_strategy.validar_solicitud` (515 L) → mover a `services/validators/` (que ya existe e infrautiliza).
16. Vaciar de negocio `views/doblada_api.py`, `views/api_turno_jornada.py` y `permisos/views.py` (este último no tiene capa de servicios propia: crearla).
17. `SolicitudOrchestrator` deja de devolver `JsonResponse`; devuelve un `Result` y la vista lo serializa.
18. Sacar el ORM de `domain/bloqueo_partes.py:62`.

**Fase 4 — Frontend (2-4 semanas).**
19. Extraer los `<script>` inline de los 3 `solicitar_*.html` → eliminar `'unsafe-inline'` del CSP.
20. Factorizar las funciones duplicadas de `cambio-turno/*.js` a los `utils/` y `services/` existentes.
21. Migrar a `<script type="module">`; eliminar los 94 `console.log`.

---

## Cómo verificar el progreso

- `pytest --cov --cov-fail-under=65` (subir el umbral 5 puntos por fase).
- `python manage.py check --deploy` — incluye los checks propios `core.E001` (caché) y `core.W002` (TLS a RDS) de `core/checks.py`. Debe ser un paso **obligatorio del pipeline de despliegue**, no manual.
- `ruff check .` — línea base y tendencia descendente.
- Métrica de OCP: `grep -rn 'tipo.*==.*DOBLADA\|CT PERMANENTE' --include=*.py` fuera de `strategies/` → objetivo 0.
- Métrica de código limpio: ningún método por encima de 80 líneas (hoy hay 25).
