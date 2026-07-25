# Mantenimiento anual — Actualizaciones y seguridad

> **Para qué existe esta carpeta**
> Es la guía que debes revisar **una vez al año** (recomendado: cada **diciembre**, o cuando salga una nueva versión LTS de Django) para mantener la aplicación actualizada y segura: versión de Django, paquetes de Python, parches de seguridad y versión de Python.
>
> No necesitas recordar el procedimiento de memoria: sigue esta guía paso a paso, registra lo que hiciste en la [bitácora](./bitacora/) y quedará el histórico para el año siguiente.

---

## 1. Qué se revisa cada año

| Área | Qué revisar | Dónde |
|------|-------------|-------|
| **Django (seguridad)** | Parches nuevos de la serie LTS en uso; CVEs publicados | [Django security releases](https://docs.djangoproject.com/en/stable/releases/security/) |
| **Django (versión mayor)** | ¿Conviene subir de serie LTS? (ej. 5.2 → siguiente LTS) | [Django download / roadmap](https://www.djangoproject.com/download/) |
| **Paquetes Python** | Dependencias desactualizadas | `pip list --outdated` |
| **Python** | ¿La versión de Python sigue con soporte? | [Python EOL](https://devguide.python.org/versions/) |
| **Vulnerabilidades** | CVEs conocidos en las dependencias instaladas | `pip-audit` |

---

## 2. Conceptos clave (para decidir bien)

- **Serie LTS (Long-Term Support):** actualmente **Django 5.2 LTS**. Los parches dentro de la misma serie (`5.2.16 → 5.2.17 → …`) son **solo correcciones de bugs y seguridad**, sin cambios de API. Son **seguros de aplicar** y solo requieren correr los tests.
- **Versión mayor (5.2 → 6.x):** trae **cambios de API** y puede romper compatibilidad. Es una decisión aparte, con más pruebas. **No la mezcles** con el parche de seguridad anual.
- **Rango seguro en `pip`:** usar `"Django>=X.Y,<X.(Y+1)"` toma el último parche de la serie **sin saltar** a la mayor.
- **"Último en PyPI":** `pip` solo instala lo que está **publicado** en el índice. Si un CVE se anuncia en el blog pero el parche aún no está en PyPI, hay que esperar a que se publique. Lo fiable es `pip index versions Django`, no la fecha del anuncio.

---

## 3. Procedimiento paso a paso

> Ejecutar desde la raíz del proyecto. El entorno virtual es `venvturnos`.
> En estos ejemplos `PY` = `C:\appTurnos\venvturnos\Scripts\python.exe`

### Paso 0 — Punto de partida seguro
```bash
git status                      # working tree limpio antes de empezar
git checkout -b mantenimiento-anual-AAAA
```

### Paso 1 — Ver qué está desactualizado
```bash
PY -m pip list --outdated       # todos los paquetes con versión más nueva disponible
PY -m pip index versions Django # últimos parches disponibles de cada serie
```

### Paso 2 — Parche de seguridad de Django (lo prioritario)
```bash
# Sube al último parche de la serie LTS actual (5.2.x), sin saltar a 6.x
PY -m pip install --upgrade "Django>=5.2,<5.3"
```
Actualiza el pin en **los tres** archivos de requerimientos:
- [requirements.txt](../../../requirements.txt) *(raíz, UTF-16 LE — editar con cuidado de codificación)*
- [AppTurnosExplora/requirements.txt](../../../AppTurnosExplora/requirements.txt) *(UTF-16 LE)*
- [AppTurnosExplora/requirements-dev.txt](../../../AppTurnosExplora/requirements-dev.txt) *(UTF-8)*

> ⚠️ Los dos `requirements.txt` están en **UTF-16 LE con BOM**. Si los editas, preserva esa codificación
> (o normalízalos a UTF-8 de forma intencional). El `requirements-dev.txt` es UTF-8 normal.

### Paso 3 — Auditar vulnerabilidades conocidas
```bash
PY -m pip install pip-audit     # si no está instalado
PY -m pip audit                 # reporta CVEs en las dependencias instaladas
```

### Paso 4 — (Opcional) Actualizar otros paquetes
Actualiza de a pocos, corriendo los tests entre cada grupo. Prioriza paquetes de seguridad
(`cryptography`, `django-axes`, `django-csp`, `PyMySQL`). Ver notas en [PAQUETES.md](./PAQUETES.md).

### Paso 5 — Validar
```bash
cd AppTurnosExplora
PY manage.py check
PY manage.py check --deploy      # revisa configuración de seguridad para producción
PY manage.py test                # suite completa (debe quedar en OK)
```

### Paso 6 — Registrar y cerrar
1. Copia la plantilla [CHECKLIST-anual.md](./CHECKLIST-anual.md) a `bitacora/AAAA.md` y complétala.
2. Commit y PR:
   ```bash
   git add -A
   git commit -m "Mantenimiento anual AAAA: actualizar Django y dependencias"
   ```

---

## 4. Regla de oro

> **Parche de seguridad ≠ upgrade mayor.**
> Aplica siempre el parche de la serie LTS (bajo riesgo, solo tests).
> Evalúa el salto de versión mayor por separado, con su propia rama y pruebas.

---

## Contenido de esta carpeta

- **README.md** — esta guía (el "qué" y el "cómo").
- **[CHECKLIST-anual.md](./CHECKLIST-anual.md)** — plantilla para copiar cada año a `bitacora/AAAA.md`.
- **[PAQUETES.md](./PAQUETES.md)** — inventario de dependencias y notas de riesgo por paquete.
- **[bitacora/](./bitacora/)** — histórico de lo actualizado cada año.
