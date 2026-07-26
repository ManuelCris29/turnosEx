# ✅ Checklist: Solución Doblada Fallida Mariana → Vanesa

## 📋 Fase 1: Reaplicar la Doblada Fallida

### Paso 1: Identificar la Solicitud
- [ ] Activar entorno virtual: `cd C:\appTurnos; .\venvturnos\Scripts\Activate.ps1`
- [ ] Abrir shell de Django: `python manage.py shell`
- [ ] Ejecutar script para encontrar ID:
  ```python
  from solicitudes.models import SolicitudCambio
  from empleados.models import Empleado
  mariana = Empleado.objects.get(id=13)
  vanesa = Empleado.objects.get(id=11)
  sol = SolicitudCambio.objects.filter(
      explorador_solicitante=mariana,
      explorador_receptor=vanesa,
      tipo_solicitud__nombre='DOBLADA',
      estado='aprobada'
  ).order_by('-fecha_solicitud').first()
  if sol:
      print(f"ID: {sol.id}, Cesión: {sol.fecha_cambio_turno}, Pago: {sol.doblada.fecha_pago}")
  exit()
  ```
- [ ] Anotar el **ID de la solicitud**: _____________

### Paso 2: Verificar Estado Actual
- [ ] Ejecutar: `python manage.py verificar_doblada <ID>`
- [ ] Revisar output y confirmar que falta la doblada
- [ ] Anotar qué falta:
  - [ ] Turnos AM+PM para Vanesa en fecha de cesión
  - [ ] Turnos AM+PM para Mariana en fecha de pago

### Paso 3: Simular Reaplicación (Dry-Run)
- [ ] Ejecutar: `python manage.py reaplicar_doblada <ID> --dry-run`
- [ ] Revisar que las operaciones planeadas sean correctas
- [ ] ¿Todo se ve bien? → Continuar al Paso 4

### Paso 4: Reaplicar Doblada
- [ ] Ejecutar: `python manage.py reaplicar_doblada <ID>`
- [ ] Verificar mensaje de éxito: "✅ ¡ÉXITO! La doblada se reaplicó correctamente."
- [ ] Anotar hora de ejecución: _____________

### Paso 5: Verificar Post-Aplicación
- [ ] Ejecutar: `python manage.py verificar_doblada <ID>`
- [ ] Confirmar:
  - [ ] ✅ Vanesa tiene DOBLADA (AM+PM) en fecha de cesión
  - [ ] ✅ Mariana tiene DOBLADA (AM+PM) en fecha de pago
  - [ ] ✅ Deudas generadas correctamente

### Paso 6: Verificar en UI (Vanesa)
- [ ] Abrir navegador e ingresar a la aplicación
- [ ] Login como Vanesa (ID: 11)
- [ ] Ir a "Mis Turnos"
- [ ] Buscar la fecha de cesión
- [ ] Confirmar: Se muestra **"DOBLADA (AM + PM)"**
- [ ] Capturar screenshot (opcional): _____________

### Paso 7: Verificar en UI (Mariana)
- [ ] Cerrar sesión de Vanesa
- [ ] Login como Mariana (ID: 13)
- [ ] Ir a "Mis Turnos"
- [ ] Buscar la fecha de pago
- [ ] Confirmar: Se muestra **"DOBLADA (AM + PM)"**
- [ ] Capturar screenshot (opcional): _____________

### Paso 8: Verificar Deudas Corporativas (Opcional)
- [ ] Como Vanesa: Ir a "Mis Deudas Corporativas"
- [ ] Verificar si hay deuda de 30 min para fecha de cesión (solo si es sábado/domingo)
- [ ] Como Mariana: Ir a "Mis Deudas Corporativas"
- [ ] Verificar si hay deuda de 30 min para fecha de pago (solo si es sábado/domingo)

---

## 📋 Fase 2: Crear y Probar Nueva Doblada

### Paso 9: Crear Nueva Solicitud de Doblada
- [ ] Elegir solicitante (ej: Manuel)
- [ ] Elegir receptor con jornada contraria (ej: Ronal)
- [ ] Elegir fecha de cesión (próxima semana)
- [ ] Elegir fecha de pago (posterior a cesión)
- [ ] Tipo: Cesión completa
- [ ] Enviar solicitud
- [ ] Anotar ID de la nueva solicitud: _____________

### Paso 10: Aprobar Nueva Solicitud
- [ ] Receptor aprueba la solicitud
- [ ] Supervisor aprueba la solicitud
- [ ] Anotar hora de aprobación: _____________

### Paso 11: Verificar Inmediatamente en BD
- [ ] Ejecutar: `python manage.py verificar_doblada <ID_NUEVA_SOLICITUD>`
- [ ] Confirmar:
  - [ ] ✅ Receptor tiene AM+PM en fecha de cesión
  - [ ] ✅ Solicitante tiene AM+PM en fecha de pago
  - [ ] ✅ Deudas generadas
  - [ ] ✅ Sin errores en el diagnóstico

### Paso 12: Verificar en UI (Receptor)
- [ ] Login como receptor
- [ ] Ir a "Mis Turnos"
- [ ] Buscar fecha de cesión
- [ ] Confirmar: Se muestra **"DOBLADA (AM + PM)"**

### Paso 13: Verificar en UI (Solicitante)
- [ ] Login como solicitante
- [ ] Ir a "Mis Turnos"
- [ ] Buscar fecha de pago
- [ ] Confirmar: Se muestra **"DOBLADA (AM + PM)"**

### Paso 14: Verificar Criterio de Deuda Corporativa
- [ ] Si fecha es sábado/domingo Y tiene AM+PM → debe haber deuda de 30 min
- [ ] Si fecha NO es sábado/domingo → NO debe haber deuda corporativa
- [ ] Si solo tiene AM o PM (cesión parcial) → NO debe haber deuda corporativa
- [ ] Verificar en "Mis Deudas Corporativas" que la regla se cumpla

---

## 📋 Fase 3: Prueba de Cesión Parcial (Opcional)

### Paso 15: Crear Solicitud de Cesión Parcial
- [ ] Crear solicitud de doblada
- [ ] Tipo: Cesión parcial (solo AM o solo PM)
- [ ] Aprobar solicitud

### Paso 16: Verificar Cesión Parcial
- [ ] Ejecutar: `python manage.py verificar_doblada <ID>`
- [ ] Confirmar:
  - [ ] Receptor tiene solo 1 jornada (AM o PM)
  - [ ] NO se muestra como "DOBLADA" en "Mis Turnos"
  - [ ] NO se genera deuda corporativa (porque no es AM+PM completo)

---

## ✅ Resultado Esperado

### Doblada Fallida (Mariana → Vanesa)
- [x] Reaplicada correctamente
- [x] Se ve en "Mis Turnos" como "DOBLADA (AM + PM)"
- [x] Deudas generadas

### Nueva Doblada de Prueba
- [x] Se crea sin errores
- [x] Turnos AM+PM en BD
- [x] Se ve en "Mis Turnos"
- [x] Deuda corporativa solo si hay AM+PM completo

### Criterio de Deuda Corporativa Validado
- [x] Se genera SOLO si hay AM+PM en BD (doblada completa)
- [x] NO se genera si solo hay AM o PM (cesión parcial o media jornada)

---

## 🐛 Troubleshooting

### Si no se ve en "Mis Turnos" después de reaplicar:
1. Limpiar caché del navegador (Ctrl+F5)
2. Verificar en BD con `verificar_doblada`
3. Limpiar caché de Django manualmente (ver documentación completa)

### Si aparece error al reaplicar:
1. Verificar logs del script
2. Asegurarse de que las exploradoras tengan sala asignada
3. Revisar que la solicitud esté realmente aprobada

### Si las deudas no se generan:
1. Verificar que sea sábado/domingo (para deuda corporativa)
2. Verificar que haya AM+PM en BD (no solo AM o PM)
3. Revisar logs de `DobladaAplicacionService.generar_deudas_doblada`

---

## 📚 Documentación de Referencia

- 📖 **Guía Rápida**: `GUIA_RAPIDA_REAPLICAR_DOBLADA.md`
- 📚 **Documentación Completa**: `SOLUCION_DOBLADA_FALLIDA_MARIANA_VANESA.md`
- 📋 **Recomendaciones**: `RECOMENDACIONES_DOBLADA_FDS_Y_PERMANENTE.md`

---

## 📝 Notas y Observaciones

### Fecha de ejecución: _____________

### Problemas encontrados:
- 
- 
- 

### Soluciones aplicadas:
- 
- 
- 

### Observaciones adicionales:
- 
- 
- 

---

**Creado**: 2026-02-11  
**Última actualización**: 2026-02-11  


