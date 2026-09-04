# 🗄️ Archivado anual de datos — análisis y plan

> **Estado: PENDIENTE, no implementado.** Este documento no describe algo que exista;
> describe una petición, el análisis que se hizo de ella y la decisión de **no
> ejecutarla todavía**. Está aquí para que el día que se retome no haya que rehacer el
> razonamiento.
>
> **Fecha del análisis:** 2026-09-03
> **Decisión:** archivar sí (dump anual), purgar no. Revisar cuando la base pase de ~1 GB.

---

## 1. La petición original

> «No necesitamos tener datos de la BD de años pasados. Que se haga un backup, se pueda
> guardar local o donde sea, y para el año siguiente empiece en limpio en cuestión de
> turnos — conservando los usuarios registrados y la configuración de apertura de año,
> pero los permisos y solicitudes de años pasados ya no se necesitan. Esto ayudaría a
> que no se vaya incrementando el almacenamiento.»

El objetivo declarado es **contener el consumo de almacenamiento**. Ese es el punto que
el análisis desmonta.

---

## 2. El almacenamiento no es el problema (y no va a serlo)

La base medida el 2026-07-24 pesaba **7,4 MB**, pero era una base de pruebas con pocos
usuarios reales. Proyección de un año de producción real, con 500 exploradores
inscritos y un máximo de 30 solicitudes/día:

| Tabla | Filas por año | Peso aprox. |
|---|---:|---:|
| `Turno` | 500 × 365 ≈ **182.500** | ~35 MB |
| `HistoricalTurno` | 1,5–3× la anterior | ~70 MB |
| `SolicitudCambio` + los 6 detalles + sus históricos | 30/día × ~250 días ≈ **7.500** | ~5 MB |
| `Notificacion`, `EmailOutbox`, deudas y sanciones | — | ~5 MB |
| **Total por año** | | **~100–120 MB** |

**RDS no se puede contratar por debajo de 20 GB.** Ese mínimo ya está pagado
(~$2,30/mes) y no varía. A 120 MB al año hacen falta **más de 150 años** para rozarlo.

> **Conclusión:** purgar para ahorrar almacenamiento optimiza un costo que es
> exactamente **cero**, y a cambio introduce el riesgo más caro que existe — el borrado
> de datos.

Ver [arquitectura-aws-rds-recomendada.md](./arquitectura-aws-rds-recomendada.md) § 4.2 y § 5.

---

## 3. Lo que sí crece, y por qué tampoco se arregla borrando

`Turno` + `HistoricalTurno` suman unas **500.000 filas al año**. Eso no es un problema de
disco: es un problema **potencial** de latencia en las consultas del calendario.

Y si algún día aparece, se resuelve con un índice o filtrando por año en la consulta.
Nunca borrando: una consulta lenta se arregla; un dato borrado no se recupera.

---

## 4. Por qué un «empezar en limpio» es peligroso en este modelo

El dominio **cruza deliberadamente la frontera del año**. Un borrado por año natural
rompe reglas de negocio vivas:

| Riesgo | Detalle |
|---|---|
| **Deudas y sanciones** | Quien cierra diciembre debiendo arrastra la sanción a enero. El mes vencido y los días bloqueados **no son el mismo periodo**. Borrar el año anterior borra la deuda que justifica el bloqueo vigente. |
| **Cambios permanentes** | `CambioPermanenteDia` y `DobladaPermanenteDetalle` son *permanentes* justamente porque no caducan en diciembre. |
| **`on_delete=CASCADE`** | `SolicitudCambio` cascadea a `Notificacion`, `CambioPermanenteDetalle`, `DobladaDetalle`, `ReprogramacionDiaDoblada` y `DeudaExplorador`. Un `.delete()` mal filtrado arrastra mucho más de lo previsto. |
| **Auditoría** | `HistoricalRecords` está en casi todos los modelos. Existe para responder *«¿quién aprobó esto?»* tres años después. Un conflicto laboral por un turno viejo es **mucho más probable** que quedarse sin disco. |

---

## 5. Plan recomendado

### 5.1 Ahora — archivar, no purgar

**Dump anual cada diciembre**, junto al mantenimiento anual que ya se hace a mano
(ver la nota de memoria `mantenimiento-anual-carga-manual`). Un `mysqldump` comprimido
del año pesa unos pocos MB y se guarda en S3 (centavos al mes, gratis en free tier) o en
un disco de la oficina.

Da lo que se pedía —«tener el respaldo del año guardado»— **sin tocar producción**.

> **Ojo:** los snapshots automáticos de RDS **no sirven para esto**. Son recuperación
> ante desastre: caducan a los 7–35 días y viven dentro de AWS. Un dump anual es otra
> cosa y es la que cubre la petición.

### 5.2 No borrar nada durante los primeros 2–3 años

Cuando la base se acerque a **~1 GB** se vuelve a evaluar, con datos reales medidos en
lugar de proyecciones.

### 5.3 Si algún día hay una razón legítima para purgar

Una política de retención de datos de RRHH **sí** sería una razón válida (el
almacenamiento no lo es). En ese caso, el orden correcto es:

1. Purgar **solo** `HistoricalTurno` y `Notificacion` de años cerrados — ahí está ~70 %
   del volumen y es lo que menos falta hace.
2. Dejar intactos `Turno`, `SolicitudCambio` y **todo** lo relacionado con deudas y
   sanciones.
3. Nunca purgar un año cuyas deudas o sanciones sigan abiertas.

---

## 6. Qué habría que construir el día que se retome

Un comando de gestión de Django (~40 líneas) que:

1. Haga `mysqldump` del año indicado, comprimido.
2. Lo suba a S3 con nombre `swalp-<año>.sql.gz` (o lo deje en una ruta local).
3. Verifique el dump antes de dar el OK.
4. **No borre nada** — la purga, si llega, va en un comando separado y con `--dry-run`
   obligatorio.

Encaja con el mantenimiento anual manual que ya se ejecuta cada diciembre.

---

## 7. Resumen en una línea

Se pidió purgar por almacenamiento; el almacenamiento cuesta cero y sobra para 150 años.
Se conserva el valor de la petición (**tener el año archivado y a mano**) mediante un
dump anual, y se descarta la parte peligrosa (**borrar**) hasta que exista una razón que
no sea el disco.
