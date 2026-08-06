# Manual: ejecutar SonarQube localmente

Guía paso a paso para volver a levantar el servidor SonarQube y correr un
análisis del proyecto SWALP (AppTurnosExplora).

## 1. Componentes involucrados

- **Servidor SonarQube**: contenedor Docker definido en
  [docker-compose.yml](../../../docker-compose.yml) (raíz del repositorio,
  ⚠ no confundir con los `docker-compose*.yml` de `AppTurnosExplora/`, que
  son de la aplicación).
- **Scanner**: `pysonar-scanner`, ya instalado en el entorno virtual
  (`venvturnos\Scripts\pysonar.exe`). Lee la configuración desde
  [AppTurnosExplora/sonar-project.properties](../../sonar-project.properties).
- **Resultado del último análisis**: `AppTurnosExplora/.sonar/report-task.txt`
  (generado por el scanner, no se versiona).

## 2. Levantar el servidor

Desde la raíz del repositorio (`c:\appTurnos`):

```powershell
docker compose up -d
```

Esto arranca el contenedor `sonarqube` (imagen `sonarqube:lts-community`) y
expone la interfaz en:

```
http://localhost:9000
```

La primera vez, el arranque tarda 1–2 minutos (SonarQube inicializa su base
de datos interna). Verificar estado con:

```powershell
docker compose logs -f sonarqube
```

Esperar el mensaje `SonarQube is operational`.

Para detenerlo (sin perder datos, quedan en los volúmenes `sonarqube_data`,
`sonarqube_logs`, `sonarqube_extensions`):

```powershell
docker compose down
```

## 3. Primer acceso / credenciales

- Login por defecto: usuario `admin`, contraseña `admin` (pide cambiarla en
  el primer ingreso).
- Crear un **token** de usuario para el scanner:
  `Mi cuenta > Security > Generate Tokens`. Guardarlo, no se vuelve a
  mostrar.

## 4. Crear el proyecto (solo la primera vez)

El `sonar.projectKey=SWALP` en `sonar-project.properties` debe existir en el
servidor antes de analizar. En la interfaz: `Projects > Create Project >
Local project`, usar la key `SWALP`. También se puede dejar que el scanner
lo cree automáticamente si el token tiene permisos suficientes.

## 5. Ejecutar el análisis

Desde `AppTurnosExplora/` (misma carpeta que `sonar-project.properties`),
con el entorno virtual activo:

```powershell
..\venvturnos\Scripts\pysonar.exe --sonar-host-url=http://localhost:9000 --sonar-token=<TOKEN> --sonar-project-key=SWALP
```

Validado en la práctica: termina con `ANALYSIS SUCCESSFUL, you can find the
results at: http://localhost:9000/dashboard?id=SWALP`. Es normal ver líneas
`ERROR`/`WARNING` del sensor JS/CSS al parsear tags de plantillas Django
(p. ej. `Unknown word {% endif %}` en archivos de `templates/`) — son ruido
de ese sensor, no interrumpen el análisis.

El scanner toma automáticamente `sonar.sources`, `sonar.exclusions`,
`sonar.tests`, etc. desde `sonar-project.properties` — no hace falta
repetirlos por línea de comandos.

Alternativa: exportar el token como variable de entorno para no pasarlo en
cada corrida:

```powershell
$env:SONAR_TOKEN = "<TOKEN>"
..\venvturnos\Scripts\pysonar.exe --sonar-host-url http://localhost:9000 --sonar-project-key=SWALP
```

⚠ No compartas el token en chats, commits ni tickets: si lo escribiste en
texto plano en algún lado, revócalo en `Mi cuenta > Security > Tokens` y
generá uno nuevo.

## 6. Ver resultados

Ir a `http://localhost:9000/dashboard?id=SWALP`. El archivo local
`.sonar/report-task.txt` (generado tras cada corrida) trae la URL directa al
análisis (`dashboardUrl`).

## 7. QUÉ SE ESCANEA Y QUÉ NO (leer antes de interpretar resultados)

Esta es la sección clave: sin entenderla, los números del dashboard se
malinterpretan. **Lo que Sonar no ve, no reporta** — eso no significa que
esté bien, significa que se decidió no mirarlo.

### 7.1. Qué se excluye del análisis (`sonar.exclusions`)

Nada de esto genera issues, a propósito:

| Exclusión | Por qué |
|---|---|
| `static/plugins/**`, `static/lib/**`, `static/css/alt/**` | Librerías de terceros (jquery, codemirror, datatables, select2, fullcalendar, flatpickr, chart.js…). Se actualizan reemplazando la librería, no editando su fuente. |
| `*.min.css`, `*.min.js` | Minificados: ilegibles y de terceros. |
| `staticfiles/**` | Generado por `collectstatic`, es copia de lo anterior. |
| `migrations/**` | Autogenerado por Django. |
| `venvturnos/**` | Entorno virtual, dependencias de terceros. |
| `scripts/**` | Herramientas de dev/mantenimiento que corre un admin a mano, **no se despliegan**. Aquí viven 8 `S2077` (SQL con tablas hardcodeadas) que son falsos positivos. Para auditarlas puntualmente, quitar esta entrada. |
| `*.png`, `*.jpg`, `*.jpeg`, `*.ico`, `*.docx`, `*.pdf`, `*.mwb`, `*.mwb.bak` | Binarios (imágenes, manuales Word, PDF, modelos MySQL Workbench). No son código; el sensor intentaba leerlos como UTF-8 y por eso salía el warning de encoding. |

**Importante — las plantillas HTML propias SÍ se analizan.** `templates/**`
no está excluido y hoy reporta 110 issues (lenguaje `web`). Si alguien
recuerda "se omitieron unos HTML", eso es impreciso: lo que se excluyó fue
JS/CSS de terceros. Con HTML solo hubo dos casos puntuales (ver 7.2).

### 7.2. Qué se suprime puntualmente (`sonar.issue.ignore`)

Distinto de excluir: el archivo **sí se analiza**, solo se calla **una regla**
sobre él. Hoy hay 12 supresiones (`e1`-`e12`), cada una con su justificación
comentada en `sonar-project.properties`:

| Entradas | Regla | Motivo resumido |
|---|---|---|
| `e1` | `Web:S5247` | El `|safe` aplica al `help_text` de Django, no a input de usuario |
| `e2`-`e6` | `S1135` | "Todo" español ≠ marcador `TODO` (falso positivo por idioma) |
| `e7`-`e9` | `S8572` | `logger.error(…, exc_info=True)` ya equivale a `logger.exception()` |
| `e10` | `docker:S6470` | El `.dockerignore` ya excluye lo sensible; Sonar no lo lee |
| `e11` | `javascript:S2486` | El `catch` sí maneja el error con fallback |
| `e12` | `python:S1192` | Literales del CSP en `settings.py` se leen mejor sin constante |

**Criterio**: se suprime **por archivo**, nunca la regla entera, para no
perder su cobertura en el resto del proyecto. Ejemplo: `S1135` se calla en
los 5 archivos con "Todo" en español, pero un `TODO` real en cualquier otro
archivo sigue reportándose.

**Por qué acá y no marcándolos "Accepted" en la interfaz**: el token de
análisis (`sqp_…`) no puede administrar issues (devuelve *403*). Y aunque
pudiera, la configuración es preferible: queda versionada en git, se aplica
sola en cada análisis y en cualquier máquina, y la justificación vive junto
a la regla.

Un tercer caso de HTML **no se suprimió, se arregló de verdad**:
`diasespeciales_temporadas_anual.html` pasó de `|safe` a `json_script`
(patrón XSS-safe de Django) en el commit `a376506`.

### 7.3. Qué se separa como tests (`sonar.tests`)

`sonar.tests=.` con `sonar.test.inclusions=**/tests/**,**/test_*.py,**/*_test.py`.
Los tests se analizan, pero no cuentan como código de producción en las
métricas de calidad.

### 7.4. Otros ajustes

- `sonar.sourceEncoding=UTF-8` — codificación del código fuente.
- `sonar.python.version=3.14` — versión del venv `venvturnos`; sin esto,
  Sonar analiza asumiendo compatibilidad con todo Python 3 y avisa.
- `sonar.python.coverage.reportPaths=coverage.xml` — ver sección 9.

### 7.5. Efecto de las exclusiones (por qué el dashboard muestra ~1.6k y no 25k)

| | Issues |
|---|---|
| Sin exclusiones (antes de julio 2026) | **25.275** |
| Con exclusiones (estado actual) | **~1.637 abiertos** |

Los ~23.7k restantes figuran como **cerrados/resueltos** en el servidor: son
los de terceros que las exclusiones dejaron fuera. Si consultás la API con
`api/issues/search` sin `resolved=false`, vas a ver el total de 25k y
parecer que las exclusiones no funcionan — **siempre filtrar por
`resolved=false`**.

## 7-bis. Estado de brechas abiertas (snapshot: 4 ago 2026)

Punto de partida para saber qué falta arreglar. Regenerar tras cada
análisis.

**Totales**: 86.790 líneas de código, 396 archivos, 1.637 issues abiertos.

Por tipo de calidad:

| Tipo | Abiertos | Rating |
|---|---|---|
| Maintainability | 1.540 | A |
| Reliability | 151 | D |
| Security | 3 | D |

Por lenguaje: `css` 842 · `js` 374 · `py` 309 · `web` (plantillas) 110 · `docker` 2

Por severidad: HIGH 271 · MEDIUM 1.291 · LOW 121 · INFO 10 · **BLOCKER 0**

**Los 3 de seguridad (los más urgentes, hacen que el rating sea D):**

1. `docker:S6471` — `Dockerfile:4`: la imagen `python` corre como `root` por
   defecto.
2. `docker:S6470` — `Dockerfile:33`: `COPY` recursivo podría meter datos
   sensibles en el contenedor.
3. `python:S1313` — `config/settings.py:506`: IP hardcodeada
   `192.168.2.102`.

**Reglas HIGH con más incidencias** (por dónde empezar a bajar los 271):

| Regla | Cant. | Qué es |
|---|---|---|
| `python:S3776` | 108 | Complejidad cognitiva demasiado alta |
| `python:S1192` | 48 | Cadenas literales duplicadas |
| `javascript:S3504` | 42 | `var` en vez de `let`/`const` |
| `python:S8572` | 26 | — |
| `javascript:S7761` | 24 | — |
| `javascript:S3776` | 16 | Complejidad cognitiva en JS |

**Cobertura**: 50,2% global · 75,6% en código nuevo (requiere ≥ 80%).
**Duplicación**: 5,3% global · 1,2% en código nuevo (requiere ≤ 3%).

## 8. Quality Gate: "2 conditions failed" en la primera corrida

Es normal ver fallar **Coverage** (0.0%, requiere ≥ 80%) mientras no se
importe un reporte de cobertura de pytest. **New issues** sí refleja
hallazgos reales del análisis — revisar en la pestaña *Issues* del
dashboard.

## 9. Conectar la cobertura de pytest (para que Coverage deje de dar 0%)

SonarQube no ejecuta los tests, solo analiza código estático. Para que sepa
cuánto código está cubierto por tests, hay que generarle un reporte con
`pytest-cov` y decirle dónde está.

**9.1. Instalar la dependencia** (una sola vez; ya agregada a
`requirements-dev.txt`):

```powershell
..\venvturnos\Scripts\pip.exe install -r requirements-dev.txt
```

**9.2. Generar el reporte de cobertura** antes de correr el scanner, desde
`AppTurnosExplora/`:

```powershell
..\venvturnos\Scripts\python.exe -m pytest --cov=. --cov-report=xml -n 4
```

Esto crea `coverage.xml` en `AppTurnosExplora/` (archivo generado, ignorado
en `.gitignore`, no se versiona — hay que regenerarlo en cada máquina/CI
antes de cada análisis).

**9.3. Configuración ya aplicada** en `sonar-project.properties`:

```
sonar.python.coverage.reportPaths=coverage.xml
```

**9.4. Correr el scanner** (paso 5) normalmente — al encontrar `coverage.xml`
ya reporta el % real de cobertura en vez de 0.0%.

### 9.5. ⚠ El orden importa: pytest ANTES que el scanner

El scanner **no ejecuta tests**, solo lee el `coverage.xml` que encuentre en
disco. Hay tres escenarios:

| Situación | Qué reporta Sonar |
|---|---|
| No existe `coverage.xml` | **0%** — obvio que algo falta. |
| Existe pero es **viejo** (se cambió código después de generarlo) | Un % **desactualizado**, sin ningún aviso. ⚠ El más peligroso: parece correcto pero miente. |
| Se generó justo antes del scanner | El % real. |

**Regla práctica**: si tocaste código desde la última vez, regenerá la
cobertura antes de analizar. Si no cambió nada, reutilizar el `coverage.xml`
existente es válido (y ahorra ~7 min de suite).

### 9.6. Flujo completo de un análisis desde cero

Desde `AppTurnosExplora/`, en orden:

```powershell
# 1. Servidor arriba (desde la raíz c:\appTurnos, solo si no está corriendo)
#    docker compose up -d

# 2. Cobertura fresca (~7 min) — omitir solo si no se tocó código
..\venvturnos\Scripts\python.exe -m pytest --cov=. --cov-report=xml -n 4

# 3. Análisis (~1 min)
..\venvturnos\Scripts\pysonar.exe --sonar-host-url=http://localhost:9000 --sonar-token=<TOKEN> --sonar-project-key=SWALP

# 4. Ver resultados
#    http://localhost:9000/dashboard?id=SWALP
```

Nota sobre el paso 2: si algún test falla, `pytest` **igual genera** el
`coverage.xml` y el análisis puede continuar — pero la cobertura reflejará
la corrida con el fallo. Conviene revisar por qué falló antes de tomar el
número como bueno.

## 10. Regenerar el snapshot de brechas (sección 7-bis)

Después de cada análisis, para actualizar los números de la sección 7-bis
sin depender de leer el dashboard a ojo:

```bash
# Métricas generales
curl -s -u <TOKEN>: "http://localhost:9000/api/measures/component?component=SWALP&metricKeys=ncloc,files,coverage,duplicated_lines_density,software_quality_security_issues,software_quality_reliability_issues,software_quality_maintainability_issues"

# Issues ABIERTOS por lenguaje/severidad (¡ojo con resolved=false!)
curl -s -u <TOKEN>: "http://localhost:9000/api/issues/search?componentKeys=SWALP&resolved=false&facets=languages,impactSeverities,impactSoftwareQualities&ps=1"

# Los de seguridad, con archivo y línea
curl -s -u <TOKEN>: "http://localhost:9000/api/issues/search?componentKeys=SWALP&resolved=false&impactSoftwareQualities=SECURITY&ps=10"
```

⚠ **Sin `resolved=false` los totales incluyen ~23.7k issues ya cerrados** de
las exclusiones de terceros, y da la falsa impresión de que el proyecto tiene
25k problemas abiertos.

## 11. Historial de decisiones sobre SonarQube

| Fecha | Commit | Qué se hizo |
|---|---|---|
| 23 jul 2026 | `a376506` | Se crea `sonar-project.properties`. Exclusiones de terceros/generado: issues **25.275 → 1.630**. Fix XSS real (`|safe` → `json_script`) en `diasespeciales_temporadas_anual.html`. Limpieza de imports/variables muertas. |
| 23 jul 2026 | `81c47d2` | Se resuelve el único blocker JS (`javascript:S2703`, global implícita en el calendario de festivos). Se suprime el FP `Web:S5247` de `change_password.html`. Blockers **1 → 0**, vulnerabilities **4 → 2**. |
| 4 ago 2026 | (este manual) | `sonar.sourceEncoding`, `sonar.python.version=3.14`, cobertura vía `pytest-cov` (0% → 75,6% en código nuevo) y exclusión de binarios que causaban el warning de encoding. |

**Decisiones aceptadas que no se van a "arreglar":**

- Los 8 `S2077` (SQL en `scripts/`) son falsos positivos: tablas
  hardcodeadas, sin input de usuario.
- Los `S125` marcados son comentarios explicativos o rutas deshabilitadas a
  propósito.
- 2 vulnerabilities de SRI (`chart.js`, `sweetalert2`) aceptadas por usar
  versiones por rango.

## 12. Triaje y seguimiento de los issues

[sonarqube-triage.md](../05-referencia/sonarqube-triage.md) es el documento
de seguimiento: qué se arregló, qué falta y por qué se decidió cada cosa.
Abre con una sección **📊 ESTADO DE AVANCE** con la tabla de resueltos vs.
pendientes.

**Al arreglar issues, actualizarlo así:**

1. Correr el análisis y anotar el total **antes**.
2. Aplicar los arreglos.
3. **Volver a analizar** y comparar. Este paso no es opcional: al arreglar
   `docker:S6471` se introdujo sin querer un `docker:S7031` nuevo, y solo se
   detectó por re-analizar.
4. Mover los ítems de "⬜ Pendientes" a "✅ Resueltos" con el conteo
   verificado.

Comparación rápida antes/después:

```bash
curl -s -u <TOKEN>: "http://localhost:9000/api/issues/search?componentKeys=SWALP&resolved=false&inNewCodePeriod=true&facets=rules&ps=1"
```

**Nunca marcar algo como resuelto sin confirmarlo contra Sonar.**

Ver también: [semgrep-triage.md](../05-referencia/semgrep-triage.md) para el
criterio equivalente usado con Semgrep (mismas exclusiones de terceros/
generado) y [.semgrepignore](../../.semgrepignore).
