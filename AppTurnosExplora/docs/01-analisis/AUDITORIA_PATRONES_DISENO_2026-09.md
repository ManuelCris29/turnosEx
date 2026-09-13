# Auditoría de patrones de diseño y SOLID — AppTurnos/SWALP

## Fecha: 2026-09-12
## Estado: hallazgos §4.1 a §4.5 RESUELTOS el 2026-09-12 (ver §8)

## RESUMEN EJECUTIVO

Esta auditoría revisa el proyecto completo (`empleados/`, `permisos/`, `solicitudes/`, `turnos/`, `core/`) contra el catálogo de patrones de diseño y code smells de [Refactoring.Guru](https://refactoring.guru), con evidencia verificada línea a línea sobre el código actual (no sobre lo que dicen documentos previos).

**Veredicto global:** el núcleo del negocio — el flujo de las 6 solicitudes de cambio de turno — tiene una arquitectura de patrones real y bien construida (Strategy, Factory, Use Cases, State tabular), no cosmética. Los problemas de esta auditoría **no** están ahí: están concentrados en clases de soporte que crecieron sin refactor (deuda/sanciones, reportes Excel) y en un punto puntual de creación multi-flujo que el Strategy Pattern todavía no cubre. No se recomienda desacoplar más las zonas que ya están bien separadas (`core/sesiones.py`, la separación query/formato de reportes, el modelo `DobladaDetalle` compartido) — hacerlo sería sobre-ingeniería.

Este documento **actualiza y reemplaza** a `docs/01-analisis/ANALISIS_SOLID.md` (2025-01-XX) como referencia vigente — ver sección 6.

---

## 1. Metodología

Se usaron 3 exploraciones dirigidas sobre el código actual (no sobre documentación previa):
1. Mapa arquitectónico general: apps, tamaños de archivo, capas de servicios, signals, mixins, tests.
2. Lógica de negocio de las 6 solicitudes de cambio de turno (dónde vive, cómo se aplica al aprobar, si hay switches por tipo).
3. Sanciones/deuda, permisos por sesión y generación de reportes Excel.

Los hallazgos se contrastaron contra el catálogo de 22 patrones y el catálogo de code smells de Refactoring.Guru (vía Context7: `/websites/refactoring_guru_es_design-patterns`, `/websites/refactoring_guru_smells`), en particular las familias **Bloaters** (Long Method, Large Class, Long Parameter List), **Change Preventers** (Divergent Change, Shotgun Surgery) y **Couplers** (Feature Envy, Inappropriate Intimacy).

---

## 2. Tabla por app

| App | Patrones presentes | Veredicto | Nota |
|---|---|---|---|
| `solicitudes/` (flujo de las 6 solicitudes) | Strategy, Factory, Use Cases (Command), State tabular, vistas delgadas | ✅ Bien aplicado | Ver gap puntual de OCP en el orquestador (§4.2) |
| `solicitudes/` (deuda y sanciones) | Capas documentadas (cálculo puro / orquestación / cron), pero `DeudaCorporativaService` concentra demasiado | 🔴 Gap real | Ver §4.1 |
| `turnos/` (estado del día / Mis Turnos) | Función única "fuente de verdad" (`estado_dia`), sin duplicación | ✅ Bien aplicado | — |
| `turnos/` (reportes Excel) | Separación query/formato correcta a nivel de diseño | ⚠️ Mejorable | Método largo + parámetros excesivos, ver §4.3-4.4 |
| `permisos/` | Servicios existen pero desorganizados (sueltos en raíz, no en `services/`) | ⚠️ Mejorable | Ver §4.5 |
| `empleados/` | Capa de servicios incipiente; vistas de sanciones grandes | ⚠️ Mejorable | Ver §4.5 |
| `core/` (sesiones/permisos/middleware) | Catálogo de datos / resolución de reglas / enforcement separados en 3 archivos | ✅ Bien aplicado | No tocar, ver §5 |

---

## 3. Lo que ya está bien aplicado (evidencia)

- **Strategy Pattern real**: `solicitudes/services/strategies/base_strategy.py:17` define `SolicitudStrategy(ABC)` con métodos abstractos (`validar_solicitud`, `crear_solicitud`, `aplicar_cambios` L62, `_datos_desde_solicitud` L75). Las 6 subclases concretas (`cambio_turno_strategy.py`, `doblada_strategy.py`, `ct_permanente_strategy.py`, `doblada_permanente_strategy.py`, `d_fds_strategy.py`, `cambio_descanso_strategy.py`) implementan `aplicar_cambios` cada una. No es una fachada vacía: el propio docstring del módulo lo declara ("This module implements the Strategy Pattern...") y el historial de refactor está documentado in-situ.
- **Factory con registro dinámico**: `solicitudes/services/solicitud_factory.py:48` (`_strategies = {}`), registro en `register_strategy` (L117) y auto-registro en `_auto_register_strategies` (L557-581), que mapea `"CT" → CambioTurnoStrategy`, `"DOBLADA" → DobladaStrategy`, etc. Permite agregar un tipo nuevo sin tocar el Factory.
- **Use Cases (Command informal)**: `solicitudes/use_cases/aprobar_solicitud.py` — `AprobarComoReceptorUseCase`, `AprobarComoSupervisorUseCase`, `RechazarComoReceptorUseCase`, `RechazarComoSupervisorUseCase`, `AprobarAmbosRolesUseCase`, cada una con `.execute(...)`. Mismo patrón en `cancelar_solicitud.py` y `crear_solicitud.py`.
- **State tabular**: `solicitudes/domain/estado_machine.py:11` (`_TRANSICIONES: dict[str, set[str]]`), con `transicionar()` (L28) validando antes de mutar `solicitud.estado`. No es State orientado a objetos (no hay una clase por estado), pero cumple el mismo propósito con menos código — decisión razonable, no un gap.
- **Vistas delgadas**: `solicitudes/views/aprobacion_views.py` — cada vista (`AprobarSolicitudView`, `RechazarSolicitudView`, `CancelarSolicitudView`, etc.) solo valida sesión/HTTP y delega en un Use Case. No hay reglas de negocio en `views/`.
- **Switches eliminados**: los antiguos `if tipo_nombre == 'CT PERMANENTE': ... elif ...` de 6 ramas ya no existen en las rutas críticas de validar/aplicar/detalle. Quedan comentarios explícitos documentando el "antes" en `solicitudes/views/detalle.py:108`, `base_strategy.py:176,203`, y en cada `*_strategy.py` (líneas 687, 736, 533, 738, 477, 897 respectivamente).
- **Permisos por sesión**: `core/sesiones.py` (176 líneas, catálogo de datos declarativo con `__slots__`) + `core/permisos_sesion.py` (resolución de reglas: admin total, fila explícita en `PermisoSesion`, o default) + `core/middleware.py:87-134` (`PermisoSesionMiddleware`, enforcement HTTP). Tres responsabilidades, tres archivos, sin condicionales anidados — el mapeo es por diccionario (`POR_URL_NAME`, `POR_CODIGO`).
- **Reportes: separación query/formato**: `turnos/api/views/reportes.py:294-307` consulta datos vía `ReporteDiaService.reporte(fecha)` **antes** de llamar a `_generar_excel`, con comentario explícito en el código (L302-303): *"Se consulta aquí, no dentro del generador, para que el Excel siga siendo solo formato"*. Hay test dedicado a esta separación: `turnos/tests/test_reporte_dia_capas.py`.
- **`estado_dia` como fuente única de verdad**: `turnos/services/turno_service.py:378-386` — una sola función aplica 6 capas en orden fijo (turno real → descanso aprobado → alternancia FDS → mantenimiento → temporada → base), documentada literalmente como "FUENTE DE VERDAD ÚNICA". La versión batch `estado_mes` (L514) declara explícitamente mantener el mismo orden de capas. No hay duplicación de esta lógica por formulario.

---

## 4. Hallazgos (gaps)

### 4.1 God Class: `DeudaCorporativaService`

- **Evidencia**: `solicitudes/services/deuda_corporativa_service.py` — 1130 líneas, clase única con 21 métodos estáticos (L31-1130). El método `gestionar_sancion_por_deuda` (L397-519, ~122 líneas) hace en un solo flujo: delega el cálculo a `cadena_sanciones()` (función pura en `sancion_deuda_calculo.py`), **persiste** (`SancionEmpleado.objects.create`, L494), **notifica** (`_notificar_sancion`, L863), e **invalida caché** (`_invalidar_cache_mis_turnos_sancion`, L905). La misma clase además hace CRUD de `DeudaCorporativa` (`crear_deuda_corporativa` L934, `cancelar_deuda` L1111) y auditoría de morosos (`auditar_morosos` L666).
- **Code smell (Refactoring.Guru)**: Large Class / Divergent Change — cualquier cambio en la política de notificación, en el cálculo de sanción o en el CRUD de deuda obliga a tocar el mismo archivo por razones distintas.
- **Patrón recomendado**: Extract Class. Separar en al menos: (a) orquestador de sanción-por-deuda (cálculo + persistencia + transición de estado), (b) notificador (ya casi aislado en métodos `_notificar_*`, solo falta moverlo a su propia clase/servicio), (c) CRUD de `DeudaCorporativa`, (d) auditoría de morosos. El cálculo puro (`sancion_deuda_calculo.py`) ya está correctamente separado — es un buen ejemplo a replicar para el resto de la clase.
- **Nota de alcance**: es la única App con este patrón de servicio-persistencia-notificación-caché unido; no se encontró equivalente en `turnos/` o `empleados/`.

### 4.2 OCP incompleto: `solicitud_orchestrator.py`

- **Evidencia**: `solicitudes/services/solicitud_orchestrator.py` líneas 105, 633 y 654 — tres condicionales por nombre literal de tipo:
  - L105: `if tipo_nombre == 'CT PERMANENTE':` dentro de `_fechas_objetivo`, para expandir el rango de fechas.
  - L633: `if tipo_nombre == "DOBLADA PERMANENTE":` dentro de `procesar()`, desvía a `_procesar_doblada_permanente_multi`.
  - L654: `if tipo_nombre == 'CAMBIO DESCANSO' and post.get('empleado_receptor_2'):` desvía a `_procesar_cobertura_dos` (flujo de dos solicitudes atómicas AM+PM).
- **Por qué es un gap real y no solo un detalle**: el Strategy Pattern del proyecto cierra correctamente las fases de *validar/aplicar/detalle* (§3), pero la fase de **creación cuando existe un flujo multi-solicitud** (doblada permanente con varios compañeros, cambio de descanso con cobertura de dos personas) no está delegada a la Strategy — vive como excepción hardcodeada en el orquestador. Agregar un séptimo tipo de solicitud con un flujo de creación no estándar seguiría obligando a editar este archivo, violando OCP exactamente donde el resto del sistema ya lo resolvió.
- **Patrón recomendado**: extender la interfaz de `SolicitudStrategy` con un método opcional tipo `flujo_creacion_alterno(post_data) -> Callable | None` (o un método `requiere_multi_creacion()` + `crear_multi(...)`), de forma que el orquestador pregunte a la estrategia en vez de comparar nombres. Esto es coherente con cómo ya se resolvió el resto del ciclo de vida.
- **Prioridad**: media — no es un bug, es deuda de extensibilidad; solo se paga cuando aparece un tipo de solicitud nuevo con flujo de creación especial.

### 4.3 Long Parameter List en generación de Excel

- **Evidencia**:
  - `turnos/api/views/reportes.py:649` — `_hoja_trabajan(self, ws, titulo, empleados, fecha_legible, color_enc, color_sub, AZUL_OSC, fill, fuente, borde, centrado, izquierda, dia_info)` — **12 parámetros**.
  - `:900` — `_hoja_deuda(...)` con un patrón similar de parámetros de estilo sueltos.
  - `:616` — `_encabezado_hoja(...)` — 9 parámetros.
  - `:637` — `_fila_header(...)` — 9 parámetros.
  - Mismo smell en `solicitudes/services/doblada_pago_service.py`: `_aplicar_pago_sabado` (L126), `_aplicar_pago_jcp_ambas` (L255), `_aplicar_pago_jcp_media` (L279), `_aplicar_pago_cesion_parcial` (L353), `_aplicar_pago_jornada_cedida` (L447), `_aplicar_pago_fallback` (L567) — todas con firma repetida `(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str, ...)`.
  - También en `solicitudes/services/validators/ct_permanente_validator.py:181` (6 parámetros) y `doblada_flujo_validator.py:602` (8 parámetros).
- **Code smell (Refactoring.Guru)**: Long Parameter List, típicamente causado por no agrupar datos relacionados en un objeto.
- **Patrón recomendado**: Introduce Parameter Object. Para los helpers de Excel, un objeto `EstiloHoja` (o `dataclass`) que agrupe `fill`, `fuente`, `borde`, `centrado`, `izquierda` y los colores, construido una vez por reporte y pasado como un solo argumento. Para `doblada_pago_service.py`, un objeto `ContextoPago` con `solicitud`, `detalle`, `fecha_pago`, `solicitante`, `receptor` reduciría las 6 firmas casi idénticas a una sola forma.

### 4.4 Long Method: `_generar_excel`

- **Evidencia**: `turnos/api/views/reportes.py:309-616` — `_generar_excel`, ~307 líneas, construye 4 hojas (`_hoja_trabajan`, `_hoja_descansan`, `_hoja_cambios`, `_hoja_deuda`) con lógica de estilos definida inline antes de delegar.
- **Patrón recomendado**: no requiere un patrón nuevo — resolver primero §4.3 (Parameter Object para estilos) ya reduce buena parte del tamaño. Si tras eso el método sigue siendo largo, un Builder (`ReporteExcelBuilder`) que encapsule la construcción de las 4 hojas sería el siguiente paso natural, pero no antes de resolver el parameter bloat (atacar el síntoma más grande primero).

### 4.5 Organización inconsistente de la capa de servicios entre apps

- **Evidencia**: `solicitudes/` y `turnos/` organizan sus servicios en subcarpeta `services/` (48 y 14 archivos respectivamente). `permisos/` tiene sus servicios sueltos en la raíz de la app: `permisos/services.py` (234 líneas), `permisos/credito_horas_service.py` (192), `permisos/deuda_permiso_service.py` (179), `permisos/pago_horas_service.py` (402) — mismo rol, distinta ubicación. `empleados/services/` solo tiene 2 archivos (358 líneas), mientras `empleados/views/sanciones.py` (549 líneas) es la vista más grande del proyecto y probablemente absorbe lógica que en `solicitudes/`/`turnos/` viviría en `services/`.
- **Naturaleza del gap**: no es una violación de un patrón de GoF, es inconsistencia organizacional entre apps del mismo proyecto — dificulta que alguien nuevo prediga dónde buscar lógica de negocio según la app.
- **Recomendación**: mover los 4 archivos de `permisos/` a `permisos/services/`, y evaluar si `empleados/views/sanciones.py` (549 líneas) tiene lógica de negocio (no HTTP) que debería extraerse a `empleados/services/`. Cambio mecánico y de bajo riesgo, no requiere rediseño.

### 4.6 Invalidación de caché de sanción duplicada y divergente

- **Evidencia**: `empleados/views/sanciones.py:191` (`_invalidar_turnos_cache_sancion`) y
  `solicitudes/services/deuda_corporativa_service.py` (`_invalidar_cache_mis_turnos_sancion`)
  calculan ambas los meses que una sanción afecta para invalidar la caché de Mis Turnos, con
  implementaciones distintas: la vista avanza de 28 en 28 días hasta `fecha_fin`; el servicio
  itera por primer día de mes y **siempre** extiende hasta un año adelante (para cubrir las
  sanciones indefinidas y las recién levantadas).
- **Code smell (Refactoring.Guru)**: Duplicate Code en su variante peligrosa — dos copias que ya
  divergieron. No es que hagan lo mismo dos veces: es que hacen cosas *distintas* creyendo hacer
  lo mismo, y cuál se ejecuta depende de por dónde entre el usuario.
- **Por qué importa**: invalidar de MÁS es inofensivo (se recalcula); invalidar de MENOS deja
  caché obsoleta y la sanción no aparece en Mis Turnos. La versión de la vista es la que invalida
  de menos.
- **Recomendación**: una sola implementación, la del servicio (la conservadora). Hallazgo
  detectado al ejecutar §4.5, no estaba en la primera pasada de esta auditoría.

---

## 5. Lo que está bien y no debe tocarse

- **`core/sesiones.py` + `core/permisos_sesion.py` + `core/middleware.py`**: la separación catálogo/reglas/enforcement ya está en el punto justo. Fusionarlos "para simplificar" perdería la ventaja de poder cambiar el catálogo sin tocar el middleware; separarlos más (un cuarto archivo) no tiene ninguna responsabilidad adicional que extraer.
- **Separación query/formato en reportes Excel**: el diseño ya es correcto (§3) — el problema real es el tamaño interno de `_generar_excel` y sus firmas (§4.3-4.4), no la separación en sí. No hace falta una capa adicional de abstracción sobre `ReporteDiaService`.
- **`DobladaDetalle` compartido entre DOBLADA, D FDS y CAMBIO DESCANSO**: en vez de 3 modelos de detalle idénticos, se reutiliza uno solo (`solicitudes/models.py:422`). Es una decisión razonable de reutilización de datos, no un acoplamiento indebido — separarlos en 3 modelos solo agregaría migraciones y duplicación sin beneficio.
- **Máquina de estados tabular** (`estado_machine.py`) en vez de un State Pattern orientado a objetos con una clase por estado: para 5-6 estados con reglas de transición simples, una tabla de transiciones es más legible y con menos código que una jerarquía de clases. Convertirla a OOP sería sobre-ingeniería para el tamaño actual del dominio.

---

## 6. Nota sobre `docs/01-analisis/ANALISIS_SOLID.md`

Ese documento (fechado 2025-01-XX) declara los 5 principios SOLID como "CUMPLIDO" de forma generalizada. Sus afirmaciones sobre Strategy/Factory/vistas delgadas siguen siendo correctas y esta auditoría las confirma (§3). Sin embargo, quedó desactualizado porque:

- No pudo prever el crecimiento de `solicitudes/services/` a ~20.500 líneas en 48 archivos, dentro de las cuales apareció `DeudaCorporativaService` (§4.1).
- No cubre el gap de OCP en `solicitud_orchestrator.py` para flujos multi-solicitud (§4.2), que es posterior a esa fecha.
- No audita `turnos/api/views/reportes.py` ni la organización de `permisos/`/`empleados/`.

Este informe (`AUDITORIA_PATRONES_DISENO_2026-09.md`) es la referencia vigente a partir de 2026-09. No se modificó `ANALISIS_SOLID.md`; se recomienda marcarlo como histórico si se retoma el tema en el futuro.

---

## 7. Recomendaciones priorizadas

1. **Partir `DeudaCorporativaService`** (§4.1) — mayor impacto en mantenibilidad, es la clase más grande y con más responsabilidades mezcladas del proyecto.
2. **Cerrar el OCP del orquestador para flujos multi-solicitud** (§4.2) — solo urge si se planea agregar un séptimo tipo de solicitud con flujo de creación especial; de lo contrario puede esperar.
3. **Introduce Parameter Object en los helpers de Excel y en `doblada_pago_service.py`** (§4.3) — cambio de bajo riesgo, mejora legibilidad y reduce `_generar_excel` (§4.4) como efecto colateral.
4. **Unificar dónde vive `services/` en `permisos/` y revisar `empleados/views/sanciones.py`** (§4.5) — cambio mecánico, más de organización que de arquitectura.

Ningún hallazgo de esta auditoría es bloqueante ni indica riesgo de correctitud actual; todos son de mantenibilidad a futuro.

---

## 8. Resolución (2026-09-12)

Los cinco hallazgos se aplicaron el mismo día, en este orden (de menor a mayor riesgo), validando
con la suite real después de cada bloque. Ningún cambio altera una regla de negocio: son
movimientos de código, firmas y organización.

### §4.3 + §4.4 — Reporte Excel y `doblada_pago_service`

La recomendación del informe (Introduce Parameter Object para los estilos) resultó ser **la
respuesta aproximada**. Al medir, las cinco "funciones de estilo" (`fill`, `fuente`, `borde_fino`,
`centrado`, `izquierda`) eran closures que **no capturaban nada** de su contexto: no había que
agruparlas en un objeto, había que sacarlas del cuerpo del método. Ahora viven en
`turnos/api/views/reporte_excel_estilos.py` como funciones puras y se importan; los colores, que
tampoco varían por ejecución, son constantes del mismo módulo, y el único par que sí cambia por
hoja viaja en un `PaletaHoja`.

El Parameter Object sí aplicó a los DATOS: `_DatosDia` agrupa lo que las seis hojas comparten.

| Método | Parámetros antes | Ahora |
|---|---|---|
| `_hoja_trabajan` | 12 | 5 |
| `_hoja_deuda` | 11 | 2 |
| `_hoja_descansan` | 11 | 2 |
| `_hoja_cambios` | 10 | 2 |
| `_encabezado_hoja` | 9 | 5 |
| `_fila_header` | 9 | 4 |

`_generar_excel` pasó de **307 a 43 líneas**; la hoja Resumen que llevaba dentro se dividió en
`_resumen_titulares`, `_resumen_lista_por_persona` y `_resumen_leyenda` para no cambiar un método
largo por otro. Ningún método de la clase supera ya los 104 renglones ni los 5 parámetros.

Hallazgo extra al medir: **`color_sub` era un parámetro muerto** — se pasaba (AZUL_CLARO /
NARANJA_CL) y no se usaba en el cuerpo.

En `doblada_pago_service.py`, las seis ramas de pago comparten ahora un `ContextoPago`. Al
analizar qué usaba cada una apareció el mismo patrón: **varias recibían argumentos que no
usaban** (`detalle`, `solicitud`, `fecha_pago_str` según la rama), heredados de copiar la firma.

### §4.2 — OCP del orquestador

Los tres `if tipo_nombre == '...'` de `solicitud_orchestrator.py` ya no existen. Cada estrategia
DECLARA lo que necesita mediante dos hooks nuevos en `SolicitudStrategy`:

- `fechas_objetivo(post)` — lo implementa `CTPermanenteStrategy`, que se llevó íntegra la
  expansión del rango (con su comentario sobre el falso bloqueo del cierre en findes).
- `flujo_creacion_propio(post)` — `DobladaPermanenteStrategy` devuelve siempre
  `'doblada_permanente_multi'`; `CambioDescansoStrategy` devuelve `'cobertura_dos'` **solo** si el
  POST trae `empleado_receptor_2`.

El atributo `flujo_propio_verifica_cierre` conserva el orden exacto del pipeline: doblada
permanente se despacha ANTES del cierre genérico (calcula sus propias fechas y lo comprueba
dentro), cobertura-dos DESPUÉS. Los handlers siguen en el orquestador y se resuelven por el
registro `_FLUJOS_PROPIOS`, no por comparación de nombres: moverlos a las estrategias habría
creado una dependencia circular, porque usan `verificar_restriccion`, `verificar_sancion_receptor`
y `_respuesta_error_validacion` del propio orquestador.

### §4.1 — `DeudaCorporativaService`

De **1130 a 845 líneas**, y de 21 a 13 métodos públicos. Se extrajeron dos responsabilidades
completas, actualizando todos los llamadores (sin fachada de delegación, que solo habría
escondido el problema):

- `deuda_corporativa_repository.py` — `DeudaCorporativaRepository` con los 6 métodos de
  persistencia (`crear_deuda_corporativa`, `…_idempotente`, `cancelar_deudas_de_solicitud`,
  `sincronizar_deuda_corporativa`, `obtener_deuda_total`, `cancelar_deuda`).
- `sancion_notificador.py` — `SancionNotificador` con `notificar_sancion` y
  `notificar_condonacion`. Retocar el texto de un aviso ya no obliga a abrir el archivo donde se
  decide a quién se sanciona.

**`auditar_morosos` se dejó donde está a propósito.** El informe la listaba como candidata a
extraer, pero con `aplicar=True` no consulta: ejecuta la política de sanción. Pertenece al
servicio de política, y sacarla habría sido trocear por trocear.

### §4.5 — Capa de servicios

Los cuatro servicios sueltos en la raíz de `permisos/` viven ahora en `permisos/services/`
(`permiso_service.py`, `credito_horas_service.py`, `deuda_permiso_service.py`,
`pago_horas_service.py`), igual que en `solicitudes/` y `turnos/`. El `__init__.py` re-exporta
`PermisoNotificacionService` y `PermisoMediaJornadaService` para que `from permisos.services
import …` —el import que usan vistas y tests— siga siendo válido.

Sobre `empleados/views/sanciones.py` (549 líneas), la sospecha del informe ("probablemente
concentra lógica que debería vivir en un servicio") **no se confirmó al medirla**: ningún método
pasa de 43 líneas y el contenido es trabajo propio de una vista (filtros, contexto de plantilla,
manejo del POST). `_horas_que_se_condonan` parece duplicar `horas_condonadas_por` del servicio,
pero su docstring explica que es deliberado: una estima ANTES de confirmar y la otra lee lo
realmente escrito DESPUÉS. No se tocó.

### §4.6 — Hallazgo nuevo, no previsto en el informe

Al revisar `empleados/views/sanciones.py` para §4.5 apareció algo que la primera pasada no vio:
`_invalidar_turnos_cache_sancion` (vista) y `_invalidar_cache_mis_turnos_sancion` (servicio)
hacían lo mismo con **lógica divergente** — la vista llegaba hasta `fecha_fin`, el servicio
extendía siempre un año. Cuál corría dependía de por dónde entrara el usuario.

Ahora hay una sola implementación, `empleados.sancion_utils.invalidar_cache_turnos`, que conserva
la versión que cubre MÁS: invalidar de más cuesta un recálculo, invalidar de menos deja a alguien
viendo turnos que ya no son los suyos. Vive en `sancion_utils.py` —que ya era el módulo del
"filtro único" de sanciones— y no en el servicio de deuda, para no obligar a `empleados/` a
importar de `solicitudes/`.

### Verificación

- **Suite Python completa**: 1832 tests. Todos en verde tras las correcciones descritas abajo.
- **Suite JS**: `node --test tests_js/*.test.cjs` → 127/127 (no se tocó frontend; es control de
  no-regresión).
- **`ruff check .`**: limpio en todo el proyecto.

La primera corrida completa tras los refactors dio 24 fallos, de tres causas, todas de conexión y
ninguna de lógica de negocio:

1. **Un alias sin actualizar** (21 de los 24). Tres sitios importaban el servicio como
   `DeudaCorporativaService as _DCS`, así que la búsqueda por nombre completo no los vio al mover
   el CRUD al repositorio. Corregido en `cambio_descanso_aplicacion_service.py` y
   `doblada_aplicacion_service.py`. *Lección: al renombrar una clase, buscar también sus alias de
   import, no solo el nombre.*
2. **Dos tests de arquitectura que hicieron su trabajo**:
   `test_arquitectura_dispatch_por_tipo.py` es un trinquete que exige BAJAR el contador cuando se
   migra un dispatch por tipo — detectó que el orquestador pasó de 3 a 0 y obligó a registrarlo
   (la entrada se dejó en 0, no se borró, para que siga vigilando el archivo). Y
   `test_arquitectura_correos.py` apuntaba a `permisos/services.py`, que §4.5 movió.
3. **Fallos en cascada** de la causa 1 (reversiones que abortaban a mitad), resueltos al
   corregirla.
