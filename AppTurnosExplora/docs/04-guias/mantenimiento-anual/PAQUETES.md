# Inventario de dependencias y notas de riesgo

> Inventario de las dependencias **de la aplicación** (las que están fijadas en los `requirements`).
> Se actualiza cada mantenimiento anual. Base: diciembre 2026 (ver [bitacora/2026.md](./bitacora/2026.md)).

## Cómo leer esta tabla
- **Prioridad seguridad**: paquetes que conviene mantener al día sí o sí (criptografía, auth, framework, driver de BD).
- **Serie fija**: paquetes donde conviene quedarse en una serie y no saltar a la mayor sin pruebas.

| Paquete | Rol | Prioridad seguridad | Notas |
|---------|-----|:---:|-------|
| `Django` | Framework web | 🔴 Alta | Quedarse en serie LTS **5.2**. Subir de mayor es proyecto aparte. |
| `cryptography` | Cifrado (TLS, hashing) | 🔴 Alta | Actualizar siempre; suele traer parches de CVE. |
| `PyMySQL` | Driver MySQL | 🟠 Media | Probar bien contra la BD tras actualizar. |
| `django-axes` | Bloqueo de fuerza bruta en login | 🔴 Alta | Componente de seguridad; revisar changelog. |
| `django-csp` | Content-Security-Policy | 🔴 Alta | Ver [[csp-allowlist-nuevos-cdn]] y notas de CSP en settings. |
| `django-cors-headers` | CORS | 🟠 Media | Revisar cambios de configuración entre versiones. |
| `django-environ` | Lectura de variables de entorno | 🟢 Baja | Estable. |
| `django-simple-history` | Auditoría/histórico de modelos | 🟠 Media | Puede generar migraciones al actualizar; revisar. |
| `django-widget-tweaks` | Utilidad de formularios | 🟢 Baja | Estable. |
| `django-debug-toolbar` | **Solo desarrollo** | 🟢 Baja | No va a producción. |
| `python-dateutil` | Manejo de fechas | 🟢 Baja | Estable. |
| `openpyxl` | Exportación a Excel | 🟢 Baja | Estable. |
| `tzdata` | Base de datos de zonas horarias | 🟠 Media | Actualizar por cambios de husos/DST. |
| `sqlparse`, `asgiref` | Dependencias internas de Django | 🟢 Baja | Suben junto con Django. |

## Notas importantes
- El entorno `venvturnos` contiene además paquetes que **no** son de la app (herramientas de
  desarrollo/MCP como `mcp`, `opentelemetry-*`, `peewee`, `boltons`, etc.). **No los pinees** en
  los `requirements` de la app; céntrate en las dependencias listadas arriba.
- Los dos `requirements.txt` están en **UTF-16 LE con BOM**; `requirements-dev.txt` en UTF-8.
- Migraciones: `django-simple-history` y a veces Django generan migraciones nuevas al actualizar.
  Tras actualizar corre `manage.py makemigrations --check` para detectarlas.
