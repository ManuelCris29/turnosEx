# ADR 004: Variables de entorno con django-environ

**Estado:** Implementado  
**Fecha:** 2026-06

## Contexto

Las credenciales de base de datos, la SECRET_KEY y la contraseña de email estaban hardcodeadas en `config/settings.py` y `config/db.py`, ambos archivos trackeados por git. Cualquier persona con acceso al repositorio tenía acceso a producción.

## Decisión

Se adoptó `django-environ` para leer toda configuración sensible desde un archivo `.env` que **nunca se sube al repositorio**.

Archivos afectados:
- `.env` — valores reales, en `.gitignore`
- `.env.example` — plantilla sin valores, sí en el repo
- `config/settings.py` — reescrito para usar `env(...)`
- `config/db.py` — vaciado de credenciales

La variable `ENVIRONMENT=development|production` controla qué settings adicionales se activan (debug toolbar, HTTPS, HSTS, cookie segura).

## Consecuencias

- Ninguna credencial viaja al repositorio
- Cambiar entre entornos es cambiar el `.env`, no el código
- Al desplegar en AWS, las variables se inyectan como ECS Task Environment Variables o via SSM Parameter Store
- El `.env.example` sirve como documentación viva de qué variables se necesitan
