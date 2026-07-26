# Test Manual DOBLADA - Matriz de Combinaciones

## Objetivo
Validar en el formulario `solicitudes/cambio-turno/solicitar/3/` que las combinaciones de cesion y pago para DOBLADA cumplen las reglas de negocio definidas (casos 1.x, 2, 3.x, 4.x, 5, 6.x, 7, 8, 9).

## Alcance
- Tipo de solicitud: `DOBLADA` (`tipo_id=3`).
- Flujo: seleccion de fecha de cesion, receptor, fecha de pago, validacion previa y envio.
- Incluye validacion de mensajes en UI y bloqueo/permiso de envio.

## Precondiciones
- Tener usuarios de prueba activos con jornadas base opuestas (AM/PM), por ejemplo:
  - Mariana (solicitante/deudor)
  - Jhon (receptor/acreedor)
  - Mildrey (receptor alterno)
- Tener fechas de prueba con escenarios controlados:
  - Fecha de cesion (sin domingo ni mantenimiento).
  - Fecha de pago (sin domingo ni mantenimiento).
- Tener datos para simular estado en pago:
  - una_jornada
  - doblada
  - descansando
- Limpiar solicitudes pendientes viejas que interfieran en la misma fecha de cesion.

## Resumen de cobertura actual (segun implementacion)
- Implementado: casos 1.1 a 1.10, 2, 4.x, 5, 6.x, 7, 8, 9.
- Implementado con aviso/redireccion CT sencillo: casos con misma jornada en pago (1.6, 3.6, 4.4, 6.6 y equivalentes).
- Ajuste reciente incluido: en cesion parcial se cargan tambien companeros en descanso cuando aplica (series 3.x y 6.x).

## Guion rapido (10-15 minutos)

### 1) Caso 1.2 (rechazado)
- Cesion: emisor una_jornada, receptor una_jornada contraria.
- Pago: ambos descansando.
- Esperado: bloqueo con mensaje equivalente a `Los dos estan descansando...`.

### 2) Caso 1.3 (valido)
- Cesion: emisor una_jornada, receptor una_jornada contraria.
- Pago: emisor descansando, receptor una_jornada.
- Esperado: permite envio.

### 3) Caso 1.4 (valido)
- Cesion: emisor una_jornada, receptor una_jornada contraria.
- Pago: emisor descansando, receptor doblada.
- Esperado: permite envio y muestra resumen de cobertura (AM/PM/AMBAS cuando aplique).

### 4) Caso 1.5 (rechazado)
- Pago: emisor una_jornada, receptor descansando.
- Esperado: bloqueo con mensaje equivalente a `El receptor se encuentra descansando...`.

### 5) Caso 1.6 (condicional)
- Pago: emisor una_jornada, receptor una_jornada.
- Si misma jornada: no envia; pide CT sencillo.
- Si jornada contraria: envia.

### 6) Caso 1.9 (rechazado)
- Pago: emisor doblada, receptor una_jornada.
- Esperado: bloqueo con mensaje equivalente a `No puedes realizar el pago... tienes una doblada...`.

### 7) Caso 1.10 (rechazado)
- Pago: emisor doblada y receptor doblada.
- Esperado: bloqueo con mensaje equivalente a `Ambos tienen doblada...`.

### 8) Caso 2 (invalidar receptor doblada en cesion)
- Cesion: emisor una_jornada, receptor doblada.
- Esperado: receptor no debe salir en lista; si forzado, backend rechaza por triple turno.

### 9) Caso 3.2 / 6.1 (valido con receptor descansando en cesion)
- Cesion: receptor descansando.
- Esperado: receptor aparece disponible en lista parcial y permite flujo si pago cumple regla.

### 10) Caso 7/8/9 (rechazado por emisor sin jornada cedible)
- Cesion: emisor descansando (sin AM/PM ni doblada existente).
- Esperado: bloqueo con mensaje `El solicitante no tiene jornada asignada para esa fecha`.

## Matriz operativa para ejecucion detallada

### Grupo A - Emisor una_jornada en cesion
- A1 (1.1): pago una_jornada vs una_jornada contraria -> valido.
- A2 (1.2): pago descansando vs descansando -> rechazado.
- A3 (1.3): pago descansando vs una_jornada -> valido.
- A4 (1.4): pago descansando vs doblada -> valido.
- A5 (1.5/1.8): pago una_jornada vs descansando -> rechazado.
- A6 (1.6): pago una_jornada vs una_jornada misma -> requiere CT sencillo.
- A7 (1.6): pago una_jornada vs una_jornada contraria -> valido.
- A8 (1.7): pago una_jornada vs doblada -> valido (puede requerir CT sencillo segun jornada cedida).
- A9 (1.9): pago doblada vs una_jornada -> rechazado.
- A10 (1.10): pago doblada vs doblada -> rechazado.

### Grupo B - Receptor doblada en cesion
- B1 (2): emisor una_jornada vs receptor doblada -> invalido (no listar / rechazar backend).
- B2 (5): emisor doblada vs receptor doblada -> invalido.

### Grupo C - Receptor descansando en cesion
- C1 (3.2 / 6.1): pago descansando vs una_jornada -> valido.
- C2 (3 / 6.2): pago descansando vs descansando -> rechazado.
- C3 (3.4 / 6.3): pago descansando vs doblada -> valido.
- C4 (3.5 / 6.5): pago una_jornada vs descansando -> rechazado.
- C5 (3.6 / 6.6): pago una_jornada vs una_jornada -> valido (misma jornada requiere CT sencillo).
- C6 (3.7 / 6.7): pago una_jornada vs doblada -> valido (puede requerir CT sencillo).
- C7 (3.9 / 6.8): pago doblada vs descansando -> rechazado.
- C8 (3.14 / 6.9): pago doblada vs una_jornada -> rechazado.
- C9 (3.14 / 6.10): pago doblada vs doblada -> rechazado.

### Grupo D - Emisor sin jornada cedible en cesion
- D1 (7): emisor descansando, receptor una_jornada -> rechazado por emisor.
- D2 (8): emisor descansando, receptor doblada -> rechazado por emisor (error de emisor prevalece).
- D3 (9): ambos descansando -> rechazado por emisor.

## Evidencias que debes guardar por caso
- Captura 1: estado de jornada en cesion (ambos).
- Captura 2: estado de jornada en pago (ambos).
- Captura 3: mensaje mostrado (bloqueo o confirmacion).
- Captura 4: resultado final (envio exitoso o bloqueo).

## Criterios de aceptacion
- Cada caso debe coincidir con su salida esperada (valido/rechazado/requiere CT sencillo).
- No debe permitirse envio cuando el caso es rechazado por negocio.
- En casos de misma jornada en pago, debe aparecer flujo de CT sencillo.
- En cesion parcial, deben poder aparecer receptores en descanso cuando aplique negocio.

## Checklist de regresion tecnica
- Verificar que no se ofrezcan receptores con doblada activa en fecha de cesion.
- Verificar que el backend siga rechazando forzados por API fuera de regla.
- Verificar mismo mes cesion/pago y no mismo dia.
- Verificar bloqueo de domingo y mantenimiento.
- Verificar que comentarios obligatorios sigan funcionando.
