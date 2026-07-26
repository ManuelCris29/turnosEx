# RESUMEN: Pendientes de FASE 2

## Estado General
✅ **FASE 2.1**: COMPLETADA - Cambio sobre cambio (actualizar Turno existente)
✅ **FASE 2.2**: COMPLETADA - Validación jornada actual
✅ **FASE 2.3**: IMPLEMENTADA - Falta prueba de límite excedido
✅ **FASE 2.4**: IMPLEMENTADA - Falta verificación de historial
✅ **FASE 2.5**: IMPLEMENTADA - Falta prueba manual de UI
✅ **FASE 2.6**: COMPLETADA - Pruebas básicas de cambio sobre cambio

---

## Pendientes Detallados

### 1. FASE 2.3: Prueba de Límite Excedido ⏳

**Estado:** Implementado pero falta prueba específica

**Límite configurado:** 3 cambios por explorador/fecha

**Lo que falta:**
- Crear prueba que intente hacer un 4to cambio
- Verificar que se rechaza con mensaje de error apropiado
- Verificar que no se aplican cambios cuando se excede el límite

**Prueba necesaria:**
1. Crear 3 solicitudes aprobadas para el mismo explorador/fecha
2. Intentar crear y aprobar una 4ta solicitud
3. Verificar que se rechaza con error: "Se ha alcanzado el límite de cambios para esta fecha"
4. Verificar que no se crean turnos para la 4ta solicitud

**Archivo a modificar:**
- Crear nuevo comando de prueba: `test_limite_cambios.py`
- O agregar caso de prueba al comando existente `test_cambio_sobre_cambio.py`

---

### 2. FASE 2.4: Verificación de Historial ⏳

**Estado:** Implementado pero falta verificación del historial de Django Simple History

**Lo que falta:**
- Verificar que `HistoricalRecords` captura los cambios en `Turno`
- Verificar que `HistoricalRecords` captura los cambios en `SolicitudCambio`
- Verificar que se pueden consultar versiones anteriores usando el historial

**Verificación necesaria:**
1. Crear cambio de turno
2. Actualizar turno (cambio sobre cambio)
3. Consultar historial del turno usando `turno.historial.all()`
4. Verificar que hay registros históricos:
   - Primera creación del turno
   - Actualización del turno
5. Verificar que se pueden obtener estados anteriores

**Comando de verificación:**
```python
# Ver historial de un turno
turno = Turno.objects.get(id=XXX)
historial = turno.historial.all()
for registro in historial:
    print(f"Fecha: {registro.history_date}, Jornada: {registro.jornada.nombre}, Tipo: {registro.history_type}")
```

---

### 3. FASE 2.5: Prueba Manual de UI ⏳

**Estado:** Implementado pero requiere prueba manual en navegador

**Lo que falta:**
- Probar que la advertencia se muestra cuando el usuario tiene cambio aprobado
- Probar que la advertencia se oculta cuando cambia a fecha sin cambio aprobado
- Probar que los detalles mostrados son correctos
- Probar que el botón de cerrar funciona

**Prueba manual necesaria:**
1. Iniciar sesión como usuario con cambio aprobado
2. Ir a `/solicitudes/cambio-turno/solicitar/{tipo_id}/`
3. Seleccionar fecha con cambio aprobado
4. Verificar que aparece advertencia con:
   - Mensaje correcto
   - Jornada actual correcta
   - Nombre del compañero correcto
   - Fecha de aprobación correcta
5. Cambiar a fecha sin cambio aprobado
6. Verificar que la advertencia se oculta
7. Volver a fecha con cambio aprobado
8. Verificar que la advertencia se muestra nuevamente
9. Cerrar advertencia con botón "×"
10. Verificar que se cierra correctamente

**Endpoint a probar:**
- `GET /solicitudes/obtener-cambio-aprobado/?fecha=YYYY-MM-DD`

---

## Resumen de Acciones Pendientes

1. **Crear prueba de límite excedido** (FASE 2.3)
   - Crear comando `test_limite_cambios.py`
   - Probar que 4to cambio se rechaza correctamente

2. **Verificar historial** (FASE 2.4)
   - Crear comando de verificación de historial
   - Verificar que Django Simple History captura cambios

3. **Prueba manual de UI** (FASE 2.5)
   - Probar en navegador que las advertencias funcionan
   - Documentar resultados

---

## Notas

- El límite actual es **3 cambios** (no 2 como dice en algunos documentos)
- Las pruebas automatizadas cubren los casos básicos
- Las pruebas manuales son necesarias para verificar la experiencia del usuario
- El historial de Django Simple History debe estar funcionando automáticamente, solo falta verificar

---

## Prioridad

1. **Alta:** Prueba de límite excedido (FASE 2.3) - Crítico para validar la funcionalidad
2. **Media:** Verificación de historial (FASE 2.4) - Importante para trazabilidad
3. **Media:** Prueba manual de UI (FASE 2.5) - Importante para UX

