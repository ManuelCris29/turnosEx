# Punto ciego de TEMPORADA en `estado_dia`

> **Estado: RESUELTO COMO "NO SE ARREGLA (POR AHORA)" — 2026-08-06.**
>
> Detectado auditando doblada permanente. La política de temporada quedó **confirmada**: solo
> CT PERMANENTE y DOBLADA PERMANENTE la rechazan; el resto la permite, y esa estructura es la
> correcta. Como **ningún comportamiento debe cambiar**, se decidió NO tocar `estado_dia`:
> modificar la fuente de verdad de "Mis Turnos" a cambio de cero cambio funcional es asumir
> riesgo sin contrapartida.
>
> En su lugar se blindó la trampa (§6): advertencia en el docstring de `estado_dia` y un test
> que fija la política de los seis formularios. El análisis se conserva porque el punto ciego
> sigue existiendo y volverá a ser relevante si algún día cambia una política.

---

## 1. El hecho

`TurnoService.estado_dia` **no marca los días de temporada** para el explorador que en
temporada conserva su jornada normal. Ese día le llega como `fuente='base'`, indistinguible
de un día ordinario.

Comprobado con datos reales el **miércoles 16/12/2026** (día de temporada):

```
DiaEspecial: tipo='temporada'  es_temporada=True  descripcion='Día de temporada'
DiaEspecial.es_temporada_en(16/12/2026) -> True
```

Y sin embargo:

```
Jhon      trabaja=True  jornada=AM   fuente=base
Vanesa    trabaja=True  jornada=AM   fuente=base
Marco     trabaja=True  jornada=PM   fuente=base
...        9 de 12 exploradores activos con fuente='base'
```

Comparado con un miércoles corriente (02/12/2026), la respuesta es **idéntica campo a campo**:

| Explorador | 16/dic (temporada) | 02/dic (normal) | ¿Distinguibles? |
|---|---|---|---|
| Jhon | `AM / base` | `AM / base` | **No** |
| Vanesa | `AM / base` | `AM / base` | **No** |
| arley | `AM / base` | `AM / base` | **No** |

Un consumidor que solo lea `estado_dia` **no dispone de ningún dato** con el que saber que
el día es de temporada.

---

## 2. Por qué ocurre

La capa L4 de `estado_dia` ([`turnos/services/turno_service.py`](../../../turnos/services/turno_service.py),
~línea 481) no pregunta *"¿es temporada?"*. Pregunta si hay un **descanso de semana manual**:

```python
# L4 (lado del que DESCANSA)
if DescansoSemanaService.es_descanso_semana_manual(jornada_base, fecha):
    return _r(False, None, 'temporada', motivo='descanso de temporada')

# L4 (lado del que CUBRE el día completo)
jornada_contraria = 'PM' if jornada_base == 'AM' else 'AM'
if DescansoSemanaService.es_descanso_semana_manual(jornada_contraria, fecha):
    return _r(True, 'DOBLADA', 'temporada')

# ...y si no aplica ninguna:
return _r(True, jornada_base, 'base')      # <-- aquí cae la temporada "invisible"
```

La capa contempla **dos** situaciones —*descansas* por temporada, o *doblas* porque el grupo
contrario descansa— y **no contempla la tercera**: sigues con tu jornada normal en un día que
aun así es de temporada. Ese caso cae al `return` final sin marca alguna.

Consecuencia adicional: si un mes de temporada **no tiene cargados** los descansos de semana
manuales, la capa no se activa para *nadie* y el mes entero pasa como días ordinarios. Es lo
que ocurre hoy en la base de desarrollo con diciembre de 2026.

> Relacionado: el mantenimiento anual se carga manualmente cada diciembre. Un año sin cargar
> es intencional, no un bug — pero mientras no esté cargado, esta capa no puede activarse.

---

## 3. Alcance real HOY (importante: menor de lo que parece)

**La primera lectura fue alarmista y hay que corregirla.** Los formularios que *deben*
rechazar temporada **ya no dependen de `estado_dia`** para eso: consultan el calendario **por
regla**. Y los que sí leen `estado_dia` a secas son precisamente los que **permiten** operar
en temporada, de forma deliberada.

| Formulario | ¿Permite temporada? | Cómo lo decide hoy | ¿Le afecta el punto ciego? |
|---|---|---|---|
| **CT sencillo** (1) | **SÍ**, por diseño | `permitirTemporada: true` — *"En temporada sí se pueden hacer cambios de turno sencillos"* ([`solicitar_cambio_turno.js:585`](../../../static/js/cambio-turno/solicitar_cambio_turno.js)) | No — el comportamiento actual es el querido |
| **DOBLADA** (3) | **SÍ**, por diseño | `permitirTemporada: true` — *"En temporada sí se pueden hacer solicitudes de doblada"* ([`solicitar_doblada.js:820`](../../../static/js/cambio-turno/solicitar_doblada.js)) | No — ídem |
| **CAMBIO DESCANSO** (6) | **SÍ**, es su razón de ser | Tiene una modalidad *entre semana* que **solo existe en temporada** ([`solicitar_cambio_descanso.js:11`](../../../static/js/cambio-turno/solicitar_cambio_descanso.js)) | No |
| **D FDS** (4) | N/A | Opera sobre fines de semana; no usa el datepicker de días especiales | No |
| **CT PERMANENTE** (2) | **NO** | Regla explícita en backend: `if _es_temporada(fecha): razones.append('Temporada')` en `_razones_exclusion_ct_permanente` | **Ya cubierto** |
| **DOBLADA PERMANENTE** (5) | **NO** | Regla explícita en backend: `_dia_calendario_no_apto()` (añadida el 2026-08-06) | **Ya cubierto** |

**Conclusión honesta:** a día de hoy no hay un agujero explotable conocido. El ejemplo que
sirvió para ilustrar el punto ciego —"Vanesa podría pedir una doblada el 16/dic"— resulta ser
**comportamiento correcto y deliberado**: doblada sí se permite en temporada.

---

## 4. Por qué documentarlo igualmente

El riesgo no es de hoy, es **estructural y futuro**:

1. **La fuente de verdad miente por omisión.** `estado_dia` se presenta como la fuente única
   del estado real del día. Quien la lea razonablemente asumirá que refleja la temporada.
   No lo hace, y nada en su respuesta lo advierte.

2. **Cada formulario que deba rechazar temporada tiene que acordarse de comprobarlo aparte.**
   Hoy son dos y ambos lo hacen. El día que se añada un tercero —o que a doblada sencilla se
   le cambie la política— el error será silencioso: no falla nada, simplemente se ofrecen días
   que no debían ofrecerse. Es exactamente el bug que se corrigió en doblada permanente, donde
   el docstring de la vista *afirmaba* descontar temporada y no lo hacía.

3. **La única defensa restante en varios sitios es el calendario del front.** Deshabilitar
   fechas en el datepicker no cubre un POST directo ni un rango precargado. Defensa de una
   sola capa.

4. **Depende de que los datos estén cargados.** Un diciembre sin descansos de semana cargados
   desactiva la capa por completo, sin ningún aviso.

---

## 5. La política, CONFIRMADA

La duda que bloqueaba la decisión —*"hay formularios en donde en temporada sí se pueden
modificar las jornadas, pero no sé si todos o algunos"*— quedó resuelta el 2026-08-06:

> **Los únicos que NO permiten temporada son CT PERMANENTE y DOBLADA PERMANENTE.
> Los demás sí. La estructura actual es correcta.**

Eso convierte la tabla de §3 en la política vigente, no en una hipótesis. Está fijada en
`solicitudes/tests/test_politica_temporada.py`, que comprueba los dos lados:

- el **front**, leyendo el flag `permitirTemporada` de cada datepicker (todos los del mismo
  formulario deben declarar lo mismo: doblada tiene dos y podían divergir);
- el **backend**, comprobando que CT permanente y doblada permanente rechazan un día de
  temporada POR REGLA.

Si mañana cambia una política, ese test falla y dice exactamente cuál y dónde.

---

## 6. La decisión tomada: blindar la trampa, no cambiar la lógica

Confirmada la política de §5, **ningún comportamiento tiene que cambiar**. Por tanto no se
toca `estado_dia`: cambiar la fuente de verdad de "Mis Turnos" a cambio de cero cambio
funcional es riesgo sin contrapartida, y una bandera `es_temporada` que nadie consume es API
que envejece mal.

Lo que sí se arregló es la **trampa**, que es el daño real y es futuro.

### El bug que esto previene

Dentro de unos meses se decide *"la DOBLADA ya no se permite en temporada"*. Quien lo
implemente abre la estrategia, ve que ya consulta la fuente de verdad, y escribe lo natural:

```python
estado = TurnoService.estado_dia(explorador, fecha)
if estado['fuente'] == 'temporada':
    return {'valido': False, 'mensaje': 'No se permiten dobladas en temporada'}
```

Se ve correcto, pasa la revisión, se despliega — y **no rechaza nada**, porque a quien conserva
su jornada le llega `fuente='base'`. Sin excepción, sin log, y probablemente con tests en verde
(el caso de prueba natural es un explorador que descansa por temporada, justo donde sí
funciona). El formulario seguiría aceptando solicitudes durante meses.

Es el mismo bug que se corrigió en doblada permanente, donde el docstring de la vista
*afirmaba* descontar temporada y llevaba tiempo sin hacerlo.

### Lo aplicado (2026-08-06)

| # | Cambio | Dónde |
|---|---|---|
| 1 | Advertencia ⚠️ en el docstring: `estado_dia` NO sirve para detectar temporada; usar una regla de calendario | `turnos/services/turno_service.py` → `estado_dia` |
| 2 | Misma advertencia, abreviada, en la versión batch (hereda el punto ciego) | `turnos/services/turno_service.py` → `estado_rango_multiple` |
| 3 | Test que fija la política de los seis formularios (front + backend) y el punto ciego como comportamiento conocido | `solicitudes/tests/test_politica_temporada.py` (5 tests) |

Cero cambios de lógica. La advertencia va en el docstring porque es **el único sitio donde no
se pierde**: es lo que lee quien va a usar la función.

### Descartado explícitamente

- **Replicar el chequeo de calendario en los cuatro formularios que permiten temporada.** Sería
  cambiar comportamiento correcto.
- **Cambiar `fuente` a `'temporada'` para quien trabaja normal.** Rompería a todo el que hoy
  distingue por `fuente`.

---

## 6-bis. Opciones de arreglo (si algún día cambia la política)

### Opción A — Regla de calendario en cada formulario que la necesite
Replicar lo que ya hacen CT permanente y doblada permanente: preguntar al calendario por regla
(`_dia_calendario_no_apto` o equivalente) en los formularios que deban rechazar temporada.

- ✅ Cambio local, sin riesgo para "Mis Turnos" ni para nada que cuelgue de `estado_dia`.
- ✅ Cada formulario declara su propia política, que es justo lo que hace falta si las políticas
  difieren entre formularios (que es el caso).
- ❌ La fuente de verdad sigue mintiendo por omisión; el próximo formulario volverá a olvidarlo.

### Opción B — Arreglar la capa L4 de `estado_dia`
Que `estado_dia` marque el día de temporada **también** para quien conserva su jornada, sin
cambiar `trabaja` ni `jornada`. Por ejemplo, añadiendo una bandera análoga a la que ya existe
para festivos:

```python
# hoy ya se hace esto con los festivos:
'es_festivo': bool,     # la BANDERA se expone; la REGLA la aplica cada formulario
```

Es decir, añadir `'es_temporada': bool` al dict de retorno y dejar que cada formulario decida.

- ✅ Arregla la causa raíz y sigue el precedente que ya existe para festivos (L5 se expone como
  bandera precisamente porque la regla varía según el formulario).
- ✅ **No cambia el comportamiento de nadie** mientras nadie lea la bandera nueva: es aditivo.
  Esto la hace mucho más segura que cambiar `trabaja`/`jornada`/`fuente`.
- ❌ Toca `estado_dia` y `estado_rango_multiple`, que alimentan "Mis Turnos" y todo lo demás:
  exige revisar que ningún consumidor asuma la forma exacta del dict.

**Recomendación provisional: Opción B**, precisamente por ser aditiva y por tener el precedente
de `es_festivo`. Cambiar `fuente` a `'temporada'` para quien trabaja normal sería la variante
peligrosa y **no** se recomienda: rompería a todo el que hoy distingue por `fuente`.

---

## 7. Cómo reproducirlo

```python
from datetime import date
from empleados.models import Empleado
from turnos.models import DiaEspecial
from turnos.services.turno_service import TurnoService

F = date(2026, 12, 16)          # día de temporada
print(DiaEspecial.es_temporada_en(F))            # True

for e in Empleado.objects.filter(activo=True):
    st = TurnoService.estado_dia(e, F)
    print(e.nombre, st['trabaja'], st['jornada'], st['fuente'])
    # varios salen  True / AM|PM / 'base'  → el día de temporada es invisible
```

---

## 8. Referencias

- [`AUDITORIA_FUENTE_VERDAD_TURNOS.md`](AUDITORIA_FUENTE_VERDAD_TURNOS.md) — las 6 capas y su orden.
- `turnos/services/turno_service.py` — `estado_dia` (L4, ~línea 481) y `estado_rango_multiple`
  (la versión batch, que replica el MISMO orden de capas y por tanto el mismo punto ciego).
- `solicitudes/services/ct_permanente_helper.py` — `_dia_calendario_no_apto()`: la comprobación
  por regla que hoy protege a doblada permanente; el modelo a seguir para la Opción A.
- `solicitudes/tests/test_doblada_permanente.py` — clase `DobladaPermanenteDiasCalendarioTest`:
  tests que fijan que un día de temporada no se ofrece como doblable.
