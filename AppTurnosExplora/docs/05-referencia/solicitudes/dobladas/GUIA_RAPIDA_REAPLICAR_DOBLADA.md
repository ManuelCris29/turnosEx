# 🚀 Guía Rápida: Reaplicar Doblada Fallida

> ## ⚠️ Antes de ejecutar `reaplicar_doblada`: comprueba el día
>
> **Este comando NO valida nada.** Entra directamente al servicio de aplicación, saltándose
> las validaciones del formulario, la re-validación de la aprobación y la guardia LIFO. Escribe
> los turnos tal como diga la solicitud, aunque el día ya no encaje con la realidad.
>
> El riesgo es real porque este comando se usa justo cuando algo está descuadrado, y el día pudo
> cambiar desde que la doblada se aprobó (al compañero le cancelaron su jornada, entró en
> temporada, le movieron el descanso…).
>
> **Qué puede pasar:** si el ACREEDOR ya no trabaja la fecha de pago, algunas modalidades de pago
> dejan al deudor cubriendo jornadas que nadie iba a trabajar — acaba con AM+PM (y sus 30 minutos
> de deuda corporativa) por un turno que no existía. El comando termina diciendo
> `✅ Doblada de pago aplicada`: el fallo es **silencioso**.
>
> **Antes de ejecutarlo, comprueba a mano:**
> 1. Que el **acreedor TRABAJE** la fecha de pago (mírala en Mis Turnos, no la jornada asignada:
>    la jornada base dice "es AM" aunque ese día descanse).
> 2. Que el **deudor** siga teniendo sentido en la fecha de cesión.
> 3. Usa **siempre `--dry-run` primero** y lee la salida; no des por bueno el `✅`.
>
> Si el día ya no encaja, **no reapliques**: la doblada debe rehacerse con otra fecha de pago.
>
> Algunas modalidades ya se niegan solas (lanzan un error explicando el problema), pero **no
> todas**. Ver `PROTECTION_PATTERNS.md` (patrón 39) y el manual técnico, § 16.2.

## TL;DR (Resumen Ultra-Rápido)

**Problema**: Solicitud Mariana → Vanesa aprobada, pero no se ven las dobladas en "Mis Turnos"  
**Causa**: Error en creación de turnos durante aprobación  
**Solución**: Script de reaplicación ya creado y listo para usar  

---

## ⚡ Pasos Inmediatos

### 1. Encontrar el ID de la Solicitud

```powershell
# Activar entorno
cd C:\appTurnos
.\venvturnos\Scripts\Activate.ps1

# Abrir shell de Django
python manage.py shell
```

```python
from solicitudes.models import SolicitudCambio
from empleados.models import Empleado

# Buscar la solicitud Mariana → Vanesa
mariana = Empleado.objects.get(id=13)
vanesa = Empleado.objects.get(id=11)

sol = SolicitudCambio.objects.filter(
    explorador_solicitante=mariana,
    explorador_receptor=vanesa,
    tipo_solicitud__nombre='DOBLADA',
    estado='aprobada'
).order_by('-fecha_solicitud').first()

if sol:
    print(f"ID: {sol.id}")
    print(f"Fecha cesión: {sol.fecha_cambio_turno}")
    print(f"Fecha pago: {sol.doblada.fecha_pago}")
else:
    print("No se encontró la solicitud")

# Salir del shell
exit()
```

### 2. Verificar el Estado Actual (Opcional pero recomendado)

```powershell
python manage.py verificar_doblada <ID_SOLICITUD>
```

**Ejemplo:**
```powershell
python manage.py verificar_doblada 456
```

Esto te mostrará:
- ✅ Qué turnos existen actualmente
- ❌ Qué falta
- 💡 Diagnóstico completo

### 3. Simular la Reaplicación (Dry-Run)

```powershell
python manage.py reaplicar_doblada <ID_SOLICITUD> --dry-run
```

**Ejemplo:**
```powershell
python manage.py reaplicar_doblada 456 --dry-run
```

**¿Qué hace?**: Simula sin hacer cambios. Te muestra qué va a hacer.

### 4. Reaplicar la Doblada (Real)

```powershell
python manage.py reaplicar_doblada <ID_SOLICITUD>
```

**Ejemplo:**
```powershell
python manage.py reaplicar_doblada 456
```

**¿Qué hace?**: 
- ✅ Crea turnos AM+PM para Vanesa (fecha de cesión)
- ✅ Crea turnos AM+PM para Mariana (fecha de pago)
- ✅ Regenera deudas
- ✅ Limpia el caché

### 5. Verificar en la UI

1. **Como Vanesa (ID: 11)**:
   - Ingresar → "Mis Turnos"
   - Buscar fecha de cesión
   - Debe mostrar: **"DOBLADA (AM + PM)"** ✅

2. **Como Mariana (ID: 13)**:
   - Ingresar → "Mis Turnos"
   - Buscar fecha de pago
   - Debe mostrar: **"DOBLADA (AM + PM)"** ✅

---

## 🔧 Comandos Creados

### `verificar_doblada`
Verifica el estado completo de una doblada (turnos, deudas, visualización).

```powershell
python manage.py verificar_doblada <ID_SOLICITUD>
```

**Úsalo para**:
- Ver diagnóstico completo
- Identificar qué falta
- Verificar después de reaplicar

### `reaplicar_doblada`
Reaplica una doblada que no se aplicó correctamente.

```powershell
# Ver qué haría (sin hacer cambios)
python manage.py reaplicar_doblada <ID> --dry-run

# Aplicar realmente
python manage.py reaplicar_doblada <ID>

# Solo turnos (sin regenerar deudas)
python manage.py reaplicar_doblada <ID> --skip-deudas
```

**Úsalo para**:
- Corregir dobladas fallidas
- Recrear turnos faltantes
- Sincronizar BD con estado aprobado

---

## 🎯 Flujo Completo Recomendado

```powershell
# 1. Activar entorno
cd C:\appTurnos
.\venvturnos\Scripts\Activate.ps1

# 2. Encontrar ID (ver sección 1 arriba)

# 3. Verificar estado actual
python manage.py verificar_doblada 456

# 4. Simular reaplicación
python manage.py reaplicar_doblada 456 --dry-run

# 5. Reaplicar (si todo se ve bien)
python manage.py reaplicar_doblada 456

# 6. Verificar resultado
python manage.py verificar_doblada 456

# 7. Verificar en UI (navegador)
#    - Login como Vanesa → Mis Turnos → Ver fecha de cesión
#    - Login como Mariana → Mis Turnos → Ver fecha de pago
```

---

## 📊 Output Esperado

### Después de `verificar_doblada` (ANTES de reaplicar):
```
❌ Receptor (Vanesa) NO tiene DOBLADA en fecha de cesión
❌ Solicitante (Mariana) NO tiene DOBLADA en fecha de pago
❌ DOBLADA CON ERRORES - Se requiere reaplicación
```

### Después de `reaplicar_doblada`:
```
✅ Doblada de cesión aplicada
✅ Doblada de pago aplicada
✅ Deudas regeneradas
✅ Caché limpiado
✅ ¡ÉXITO! La doblada se reaplicó correctamente.
```

### Después de `verificar_doblada` (DESPUÉS de reaplicar):
```
✅ Receptor (Vanesa) tiene DOBLADA en fecha de cesión
✅ Solicitante (Mariana) tiene DOBLADA en fecha de pago
✅ DOBLADA APLICADA CORRECTAMENTE
```

---

## ⚠️ Advertencias Importantes

1. **Siempre usa `--dry-run` primero**: Para ver qué va a pasar sin romper nada
2. **No ejecutes múltiples veces**: El script es idempotente, pero no es necesario ejecutarlo más de una vez
3. **Verifica en UI después**: Asegúrate de que "Mis Turnos" muestre las dobladas correctamente

---

## 🐛 Si Algo Sale Mal

### "No se encontró la solicitud"
- Verifica que el ID sea correcto
- Verifica que sea una solicitud de tipo DOBLADA
- Verifica que esté aprobada

### "Doblada ya está aplicada correctamente"
- ✅ ¡Perfecto! No es necesario reaplicar
- Si no la ves en UI, limpia el caché del navegador (Ctrl+F5)

### "Error al aplicar doblada"
- Revisa los logs: `python manage.py shell` y busca errores
- Asegúrate de que las exploradoras tengan sala asignada
- Contacta soporte si persiste

---

## 📚 Documentación Completa

Para más detalles, consulta:
- **`SOLUCION_DOBLADA_FALLIDA_MARIANA_VANESA.md`**: Documentación completa con ejemplos SQL, troubleshooting, etc.

---

**Creado**: 2026-02-11  
**Última actualización**: 2026-02-11  


