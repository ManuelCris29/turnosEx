# Checklist de mantenimiento — Año AAAA

> Copia este archivo a `bitacora/AAAA.md`, reemplaza `AAAA` por el año y complétalo.
> Fecha de ejecución: ____________  ·  Responsable: ____________

## Estado de partida
- [ ] Working tree limpio (`git status`)
- [ ] Rama creada: `mantenimiento-anual-AAAA`
- Versión de Python: __________  (¿sigue con soporte? → https://devguide.python.org/versions/)
- Versión de Django antes: __________  →  después: __________

## Django (seguridad)
- [ ] Revisé https://docs.djangoproject.com/en/stable/releases/security/
- [ ] Apliqué el último parche de la serie LTS (`pip install --upgrade "Django>=5.2,<5.3"`)
- [ ] Actualicé el pin en `requirements.txt` (raíz, UTF-16)
- [ ] Actualicé el pin en `AppTurnosExplora/requirements.txt` (UTF-16)
- [ ] Actualicé el pin en `AppTurnosExplora/requirements-dev.txt` (UTF-8)
- CVEs relevantes encontrados: ______________________________________________

## Auditoría de vulnerabilidades
- [ ] Corrí `pip audit` (o `pip-audit`)
- Hallazgos / acciones: ______________________________________________

## Paquetes (opcional)
- [ ] Revisé `pip list --outdated`
- Paquetes actualizados: ______________________________________________
- Paquetes que decidí NO actualizar (y por qué): ____________________________

## Validación
- [ ] `manage.py check` sin problemas
- [ ] `manage.py check --deploy` revisado
- [ ] `manage.py test` en OK  →  resultado: ______ tests, ______ fallos

## Decisión sobre versión mayor
- ¿Existe una nueva LTS que valga la pena? (5.2 → siguiente): ______
- Decisión: [ ] posponer   [ ] planificar migración aparte
- Notas: ______________________________________________

## Cierre
- [ ] Commit y PR creados
- Commit / PR: ______________________________________________
