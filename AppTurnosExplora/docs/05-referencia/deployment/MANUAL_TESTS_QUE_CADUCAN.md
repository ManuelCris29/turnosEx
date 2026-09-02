# ⏳ Tests que caducan solos — comprobación antes de desplegar

> **Qué es esto:** un paso opcional de pre-despliegue que tarda 10 minutos y responde
> una pregunta que la suite normal no puede responder: *¿hay algo que vaya a ponerse
> rojo dentro de unas semanas sin que nadie toque el código?*
>
> **Decisión pendiente:** si esto merece un job automático en el CI o se queda como
> comando a mano. Está deliberadamente sin decidir — al final del documento están los
> dos caminos con sus costes reales, para elegir el día que toque.

---

## 1. El problema, con el caso real que lo motivó

**2 de septiembre de 2026.** Se abre el proyecto y hay **17 tests en rojo**. Nadie
había tocado nada desde el día anterior. Había además trabajo a medias sin commitear
(sala opcional, migración `0016`), así que la primera pregunta razonable era *"¿lo he
roto yo?"*.

No lo había roto nadie. Las causas eran tres, y ninguna era un bug de producción:

| Tests | Causa |
|---|---|
| 15 en `test_pago_parcial_pdh` | El archivo fijaba `2026-08` a mano porque en agosto era el mes abierto. Al llegar septiembre, agosto quedó vencido — y **solo se puede pagar el mes en curso**. Fallaban por una regla que ninguna de las 15 estaba probando. |
| 1 en `test_pago_horas` | Creaba una deuda con `hoy - 2 días`. El día 2 del mes, eso cae en el mes anterior, que ya está vencido. Habría fallado los primeros días de **cualquier** mes. |
| 1 en `test_d_fds` | Un fixture fabricaba un día como `cesión + 7 días`, que según cómo cayera el calendario aterrizaba justo encima del día bajo prueba. Aparecía y desaparecía según el mes. |

Resolverlo costó cerca de una hora, y la mayor parte se fue solo en llegar a *"no era
tuyo, y no era un bug"*.

**Lo que de verdad cuesta esto** no es la hora. Es que un rojo que no es culpa tuya
enseña a desconfiar del rojo. Ese día la suite no podía decir si el cambio de sala
opcional había roto algo, porque ya estaba roja por otro motivo. Una red de seguridad
no se estropea fallando: se estropea fallando por razones que no significan nada.

---

## 2. Por qué el CI no puede verlo

Porque **este fallo no llega con un commit, llega con el calendario**.

Un test que hoy está sano y se pudre el 1 de octubre pasa en verde en *todos* los
pushes de septiembre, se corran una vez o cincuenta. Y el día que se pudre se pone
rojo aunque nadie haya tocado el repositorio en tres semanas.

La suite normal siempre corre con el reloj de hoy, así que solo se entera el día que
ya es tarde.

---

## 3. La comprobación

```bash
cd AppTurnosExplora
pytest -n auto --dias-en-el-futuro=45
```

Corre la suite entera como si hoy fuese dentro de 45 días. Tarda lo mismo que la suite
normal (~10 min). Requiere `freezegun`, que ya está en `requirements-dev.txt`.

**Cómo leer el resultado:**

- **Todo verde** → no hay nada que se vaya a pudrir en el próximo mes y medio. Es el
  resultado esperado y no hay nada que hacer.
- **Algo en rojo** → **eso es el hallazgo, no un error de la corrida**. Ese test va a
  fallar solo dentro de unas semanas. Se arregla ahora, con calma, en vez de un
  miércoles cualquiera en mitad de otra cosa.

**Cómo se arregla lo que salga.** Casi siempre el test fija una fecha que solo vale
"por ahora". Los servicios de este proyecto ya aceptan un `hoy` inyectable
(`deudas_pendientes`, `esta_vencido`, `anio_objetivo`, `situacion`…): esa es la forma
correcta de escribirlo. El viaje en el tiempo es **el detector**; la inyección de `hoy`
es **el arreglo**.

Medido el 2026-09-02, tras corregir los tres casos de arriba: **1642 pasan, 0 fallan.**

---

## 4. El desfase importa: no uses +90 sin leer esto

| Desfase | Resultado medido (2026-09-02) | Para qué sirve |
|---|---|---|
| **+45 días** | 1642 ✓ / 0 ✗ | El desfase normal. Cae en un mes corriente y solo señala tests caducos. **Es el que se usa antes de desplegar.** |
| **+90 días** | 1479 ✓ / **149 ✗** | Cae en el **1 de diciembre**. La mayoría de esos 149 **no son tests podridos**. |

Los 149 fallos de +90 días tienen una única causa y es correcta: el 1 de diciembre
`AperturaAnioMiddleware` empieza a redirigir a **cualquier administrador** a la
pantalla de apertura mientras el año siguiente no esté planificado. Los tests de
vistas de administración fallan en bloque porque la aplicación hace lo que debe.

Es un ensayo valioso de lo que le pasará a la operación en diciembre — **pero tapa
todo lo demás**. Para cazar tests caducos, usa un desfase que no cruce el 1 de
diciembre.

> **Media historia sin probar.** Hoy sabemos que esa puerta **se cierra** el 1-dic.
> Nadie ha comprobado nunca que **se abra sola** una vez planificado el año siguiente.
> Correr `--dias-en-el-futuro=90` con el año ya abierto responde esa pregunta, y es la
> que va a importar cuando toque planificar el año.

---

## 5. La decisión: ¿a mano o en el CI?

**Estado actual: a mano.** `ci.yml` no se tocó a propósito.

### Opción A — dejarlo como está (recomendada)

Lanzar `pytest -n auto --dias-en-el-futuro=45` antes de cada despliegue, y al tocar
sanciones, deudas o vencimientos.

- **Coste:** 10 minutos, solo cuando se despliega.
- **A favor:** el despliegue es justo el momento en que descubrir esto tarde duele.
- **En contra:** depende de que alguien se acuerde — el mismo tipo de defensa que
  `verificar_crons` vino a sustituir en el checklist.

### Opción B — un job semanal en el CI

Añadir a `.github/workflows/ci.yml` un `schedule:` semanal y un job `reloj_futuro` con
`if: github.event_name == 'schedule'`, reutilizando el MySQL y las variables del job
`test`, corriendo `pytest -n auto --dias-en-el-futuro=45` **sin cobertura** (el gate
del 68 % no aporta nada aquí y quitarlo lo acelera). Son unas 15 líneas.

- **Coste:** `turnosEx` es **privado**, así que GitHub factura por minuto de runner.
  El job duplica los minutos del job más caro, **una vez por semana**.
- **Nadie espera más:** los jobs de `ci.yml` no tienen `needs:`, corren en paralelo. El
  reloj de pared del pipeline no cambia.
- **A favor:** la ventana entre que la podredumbre entra y que se ve es de 7 días como
  máximo. Con un desfase de 45, cuando llega el aviso todavía quedan más de cinco
  semanas de margen: se ve humo, no fuego.
- **Por qué semanal y no en cada push:** la respuesta solo cambia cuando cambia la
  fecha, no cuando alguien empuja código. Un job por push contestaría cincuenta veces a
  la misma pregunta. Además, los workflows programados de GitHub corren sobre la rama
  por defecto — vigilan `main`, que es exactamente lo que interesa vigilar.

### Lo que NO se recomienda automatizar

El desfase **+90 días**. Un job de CI solo sabe decir verde o rojo, y ese resultado
necesita a alguien que lo interprete: hoy da 149 fallos y está bien que los dé.
Automatizarlo deja dos salidas, ambas malas — un rojo permanente (que se ignora en una
semana, peor que no tenerlo) o un verde que tolera 149 fallos y ya no detecta nada.
Además su resultado caduca solo: en noviembre, +90 días ya no cae en diciembre.

---

## 6. Referencias

- Implementación y documentación del desfase: `AppTurnosExplora/conftest.py`.
- Dependencia: `freezegun`, en `requirements-dev.txt`.
- La regla que destapó todo esto (solo se paga el mes en curso):
  `permisos/pago_horas_service.py` y `Periodo.esta_vencido` en
  `solicitudes/services/sancion_deuda_calculo.py`.
- La puerta del 1 de diciembre: `core/middleware.py` (`AperturaAnioMiddleware`).
