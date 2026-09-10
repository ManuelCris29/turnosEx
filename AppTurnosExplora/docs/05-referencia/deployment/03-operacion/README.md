# 03 · Operación

Lo que se consulta después del despliegue, en el día a día.

| Documento | Cuándo se abre |
|---|---|
| **[CONFIGURACION_PRODUCCION.md](./CONFIGURACION_PRODUCCION.md)** | La referencia de **cada variable de entorno y qué se rompe si falta**. Es el que más se consulta |
| [MANUAL_SANCIONES_DEUDA.md](./MANUAL_SANCIONES_DEUDA.md) | El cron diario de sanciones: qué hace, cómo se programa, cómo se vigila |
| [MANUAL_TESTS_QUE_CADUCAN.md](./MANUAL_TESTS_QUE_CADUCAN.md) | `pytest --dias-en-el-futuro=45`: qué tests se pondrán rojos solos dentro de unas semanas |
| [MANUAL_DOCKER_LOCAL.md](./MANUAL_DOCKER_LOCAL.md) | Probar la imagen de producción en tu máquina antes de subir nada |
| [MANUAL_ARCHIVADO_ANUAL.md](./MANUAL_ARCHIVADO_ANUAL.md) | ⏳ **Pendiente, no implementado.** Analiza el borrado anual de datos y lo descarta |

## Las cuatro trampas de producción

Están explicadas en `CONFIGURACION_PRODUCCION.md`, pero conviene tenerlas a la vista:

1. **`LocMemCache` sirve datos viejos.** Con varios workers, invalidar "Mis Turnos" limpia
   solo uno. `core.E001` bloquea el despliegue si `CACHE_URL` queda vacío.
2. **`AXES_IPWARE_PROXY_COUNT` mal puesto bloquea a los 300 empleados.** Se mide con
   `python manage.py verificar_ip_cliente`, no se adivina.
3. **Formatos:** `ALLOWED_HOSTS` sin esquema, `CSRF_TRUSTED_ORIGINS` y `SITE_URL` con
   esquema, y `SITE_URL` sin barra final.
4. **Conexiones persistentes muertas:** `CONN_MAX_AGE` exige `CONN_HEALTH_CHECKS`.
