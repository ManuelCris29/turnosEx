# ADR 011 — La sanción por deuda se cumple entera, y la deuda se mide por meses

- **Estado:** Implementado
- **Fecha:** 2026-08
- **Ámbito:** `solicitudes` (sanciones y deuda corporativa), `permisos` (permisos especiales
  y PDH), `empleados` (modelo de sanción)

## Contexto

El sistema sancionaba a quien dejaba vencer una deuda de horas, pero tenía dos defectos que
se reforzaban entre sí.

**Pagar levantaba la sanción.** En cuanto el explorador saldaba la deuda, su sanción
automática se levantaba sola y volvía a poder solicitar. En la práctica eso convertía el
castigo en una **fianza reembolsable**: el moroso decidía cuándo dejar de estar bloqueado, y
la consecuencia de incumplir se reducía a adelantar un pago que iba a hacer de todos modos.

**Un permiso especial permanente era una deuda de todo o nada.** `PermisoEspecial` tenía un
único booleano `pagado` para su rango completo, y `horas_totales()` colapsaba todos sus
meses en una cifra. De ahí salían tres problemas:

- No se podía reclamar agosto al cerrar agosto; había que esperar al fin del permiso.
- No se admitía pago parcial.
- Un permanente largo era **literalmente impagable**: su total superaba el tope de 24 h de
  un solo PDH y no existía forma de trocearlo.

Y, sobre todo: los permisos **no sancionaban en absoluto**. La detección de deuda vencida
solo miraba `DeudaCorporativa`, que es exclusiva de dobladas.

## Decisión

### 1. La sanción es independiente del pago

Pagar cambia el estado de la deuda. La sanción sigue su curso hasta cumplir su duración.
Un supervisor puede seguir levantándola a mano —esa es una decisión humana sobre un castigo
concreto—, pero el sistema ya no la levanta solo.

### 2. La unidad sancionable es el periodo mensual, no la doblada

Antes el nivel de reincidencia se derivaba de una cadena de ventanas consecutivas sobre una
misma deuda: si la primera expiraba sin pago, empezaba la segunda, más larga. Ese modelo
dejó de ser posible al decidir que cumplir la sanción **extingue** la deuda (punto 3): una
deuda consumida no puede generar una segunda ventana.

La unidad pasa a ser `(explorador, año, mes)`, alimentada por las dos fuentes —dobladas y
permisos—, que así quedan unificadas. El nivel es cuántos meses ha cerrado debiendo.

### 3. Cumplir la sanción salda la deuda de ese mes

Estado nuevo `consumida_por_sancion`, con FK a la sanción que la extinguió. Sin esto, el
explorador terminaría sus 15 días con el mismo saldo vencido que lo metió en ellos y
volvería a ser sancionado por lo mismo: un bucle sin salida.

Una sanción **levantada a mano no salda nada**. Perdona el castigo, no las horas.

### 4. El nivel sale de la cadena de sanciones, y prescribe

```
sin antecedente, o antecedente fuera de ventana  ->  nivel 1  (15 días)
antecedente dentro de la ventana                 ->  nivel anterior + 1
duración = nivel × 15 días
```

La ventana arranca cuando **termina** la sanción anterior (su fin efectivo: `fecha_fin`, o
`levantada_en - 1` si se levantó antes) y es configurable en `ConfiguracionSanciones`. Si
se agota sin sanciones nuevas, el contador vuelve a cero.

El valor por defecto es **45 días**, y el número no es redondo por una razón: entre el fin
de una sanción y el vencimiento del mes siguiente hay días muertos (la sanción por enero
acaba el 16/02; la deuda de marzo no vence hasta el 01/04 → 44 días). Con 30 bastaba un
mes limpio para borrar el antecedente, y encima de forma desigual —quien venía de una
sanción larga seguía escalando y quien venía de una corta no—. Con 45 hacen falta dos meses
limpios, y el comportamiento es el mismo en todos los niveles.

Sin esa caducidad la escalada era acumulativa de por vida: un descuido aislado de hace dos
años seguía encareciendo la sanción de hoy, y el castigo por un tropiezo puntual acababa
siendo de meses.

Cuenta como antecedente **cualquier** sanción, incluidas las manuales del supervisor y las
levantadas. Levantar perdona ese castigo concreto; no borra que ocurrió, igual que tampoco
condona la deuda.

El nivel se **guarda** en `SancionEmpleado.nivel_reincidencia` en vez de recalcularse: la
ventana es configurable, y si cambia mañana lo que ya se comunicó a un explorador no puede
reinterpretarse con la regla nueva.

### 5. Los permisos se descomponen en obligaciones mensuales

Modelo nuevo `DeudaPermisoMes`: un permiso × un mes, con `minutos_generados`,
`minutos_pagados` y su propio estado. Es la única tabla de dominio nueva, y hace falta
porque el saldo parcial y la sanción consumidora son estado propio que no cabe en
`PermisoEspecial`. `PermisoEspecial.pagado` se conserva como valor **derivado**.

El pago parcial necesita además una tabla intermedia (`PagoDeudaPermisoMes`) que guarde
cuántos minutos cubre cada PDH: con un M2M plano, borrar un pago no sabría cuánto devolver.

## Consecuencias

**A favor:**

- La sanción vuelve a ser una consecuencia y no un depósito recuperable.
- Un permiso permanente se reclama mes a mes, en cuanto vence cada uno.
- El pago parcial existe, y de paso desaparece el permiso impagable.
- Dobladas y permisos se sancionan con el mismo mecanismo.

**En contra, asumido:**

- **Sanciones largas.** Cuatro meses seguidos sin pagar encadenan 15+30+45+60 = 150 días.
  Se decidió no poner tope: la escalada pierde su sentido si se aplana justo cuando más se
  incumple.
- **Una deuda que nace vencida desplaza las fechas de su sanción.** La ventana teórica de
  un mes ya cerrado puede haber expirado antes de que la deuda exista siquiera. El caso
  corriente no es un cron caído: es un **permiso pendiente desde hace meses que se aprueba
  hoy** — su deuda es de aquel mes, y hasta ese momento no había nada que materializar.
  Igual con una doblada registrada con retraso o una corrección.

  Grabar la ventana teórica daría un castigo nacido muerto: se consumiría en el acto,
  extinguiendo la deuda sin haber bloqueado ni un día. Se desplaza al presente
  **conservando duración y nivel**, así que llegar tarde retrasa el castigo pero nunca lo
  abarata. Se pierde la coincidencia exacta de fechas en ese caso.
- **La fecha de pago decide si un mes cuenta como cumplido.** Un supervisor que edite la
  fecha de un PDH hacia atrás puede abaratar la escalada retroactivamente. Es un poder
  legítimo suyo, pero conviene saber que existe.

### 6. Lo que se cuenta como "pendiente" es un MES sin juzgar, no una persona sin bloquear

Consecuencia directa de la decisión 2, y la que se olvidó al principio: si la unidad
sancionable es el mes, el aviso al supervisor también tiene que contar meses. Contar
personas sin sanción vigente producía dos errores opuestos a la vez.

Escondía a quien estaba **cumpliendo** la sanción de un mes y cerraba otro debiendo —le
faltaba un juicio, pero "ya estaba sancionado"—, durante tanto tiempo como durase el
castigo en curso: hasta 60 días en los niveles altos, que son justo los casos peores. Y
señalaba en cambio a quien tenía una sanción **levantada**, un caso ya juzgado que el
sistema no recrea por diseño (decisión del supervisor), dejando un aviso que ninguna acción
podía apagar.

La regla que lo ordena: **el aviso solo se enciende cuando el botón de aplicar de verdad va
a crear algo**. Eso obliga a que la consulta del aviso sea LA MISMA que decide qué se
materializa (`_periodos_ya_evaluados`), y no una aproximación parecida. La divergencia
entre ambas no falla ruidosamente: produce una pantalla que miente con seguridad.

## Alternativas descartadas

- **Derivar el nivel del ledger** (contar los meses cerrados debiendo) en vez de la cadena
  de sanciones: fue la primera implementación. Era inmune a los levantamientos manuales,
  pero acumulaba el antecedente indefinidamente y no permitía que prescribiera, que es
  justo lo que se necesitaba.
- **Derivar las obligaciones mensuales al vuelo** en vez de materializarlas: no puede
  recordar un pago parcial ni qué sanción consumió cada mes.
- **Invertir la regla solo para permisos**, dejando las dobladas como estaban: convivirían
  dos reglas disciplinarias distintas para el mismo hecho.
