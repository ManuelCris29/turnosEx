# Dobladas: cesión en día de semana → pago en sábado

Guía de los sub‑casos (AM / PM / AMBAS) y las deudas que quedan para cada quién.

## Roles
- **Tú** = solicitante / emisor / **deudor**: pides que se doblen por ti.
- **Compañero** = receptor / **acreedor**: se dobla por ti en la fecha de cesión.

## Escenario base
- **Fecha de cesión = un día de semana** (ej. **martes**): el compañero se dobla (trabaja AM+PM) y **tú descansas** ese martes.
- **Fecha de pago = sábado**: ese sábado, por la **alternancia**, **tu grupo descansa** y el **grupo del compañero trabaja**. Devuelves el favor trabajando el sábado.
- Solo se permite el sábado en **un** lado (semana ↔ sábado). Sábado ↔ sábado va por **Doblada de Fin de Semana (D FDS)**.

## Regla de oro de los 30 minutos
Los **30 min de deuda corporativa** (los que se pagan luego vía PDH) se generan **solo cuando alguien se dobla de LUNES A VIERNES**.
- **Sábado, domingo y festivos → NO generan 30 min** (ese día se trabaja jornada completa por alternancia/rotación).

---

## Sub‑caso 1 — Pagas **AM** (o **PM**): reparto del sábado

| Día | Tú (deudor) | Compañero (acreedor) |
|---|---|---|
| **Martes** (cesión) | Descansas | Se dobla **AM+PM** |
| **Sábado** (pago) | Trabajas **la media jornada elegida** (AM o PM) | Trabaja **la media contraria** |

**Deudas resultantes:**
- **30 min corporativos:** Compañero **+30** (por doblarse el martes). **Tú: 0.**
- **Entre ustedes:** la media jornada que le debías del martes queda **saldada** al trabajar tu media del sábado.

> El sábado se **reparte**: cada uno hace media jornada. El sábado de pago debe corresponder al grupo del compañero (el que se dobló).

---

## Sub‑caso 2 — Pagas **AMBAS**: cubres el sábado completo

| Día | Tú (deudor) | Compañero (acreedor) |
|---|---|---|
| **Martes** (cesión) | Descansas | Se dobla **AM+PM** |
| **Sábado** (pago) | Trabajas **AM+PM** (día completo) | **Descansa** |
| **Día de semana del mismo mes** (devolución) | Descansas | Se dobla **AM+PM** (te devuelve la media jornada) |

**Deudas resultantes:**
- **30 min corporativos:** Compañero **+30 (martes) +30 (día de semana de devolución) = +60**. **Tú: 0.**
- **Entre ustedes:** tú le debías media jornada (martes) y, al cubrir el sábado completo, **él te queda debiendo media jornada**; se salda con el día de semana de devolución → **netas 0**.

> Como tomas el sábado entero, el compañero te devuelve la media jornada un **día hábil del mismo mes** (obligatorio elegirlo). Ese día ambos deben tener **jornadas contrarias**; si coinciden, primero un **cambio de turno sencillo**.

---

## Resumen rápido de los 30 min

| Sub‑caso | Tú (deudor) | Compañero (acreedor) |
|---|---|---|
| **AM / PM** | 0 | 30 min |
| **AMBAS** | 0 | 60 min (30 martes + 30 día de semana) |

**Conclusión:** por **pagar el sábado nunca se te generan 30 min** (el sábado no cuenta). Los 30 min los acumula quien se dobla **entre semana**.

---

## Excepción (para tenerla clara)
Si **ese martes tú ya tenías DOBLADA (AM+PM)** y cediste una de tus jornadas teniendo doblada, el sistema **sí te carga 30 min, pero por el martes** (por la jornada que cediste), **nunca por el sábado**. En el caso normal (el martes tenías una sola jornada, AM o PM), a ti no se te genera nada.

---

## Validaciones que aplica el formulario
- Bloquea **sábado ↔ sábado** (te dirige a D FDS).
- En pago sábado: eliges **AM / PM / AMBAS**; el compañero debe ser del **grupo que trabaja ese sábado** (alternancia) y el sábado debe coincidir con el turno de quien se dobló.
- En **AMBAS**: exige el **día de la semana** de devolución (lun‑vie, mismo mes, no festivo ni mantenimiento, no en el pasado, y jornadas contrarias ese día).

---

### Referencias en el código
- Regla de los 30 min (solo lun‑vie): `solicitudes/services/deuda_corporativa_service.py` → `aplica_deuda_doblada()`.
- Generación de deudas (entre exploradores, corporativas y residual del sábado): `solicitudes/services/doblada_deuda_service.py` → `generar_deudas_doblada()`.
- Aplicación de turnos en el pago sábado (AM/PM/AMBAS) y devolución en semana: `solicitudes/services/doblada_aplicacion_service.py` → `aplicar_doblada_pago()` / `aplicar_pago_residual_semana()`.
- Validaciones semana↔sábado: `solicitudes/services/strategies/doblada_strategy.py`.
