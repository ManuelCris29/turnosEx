# Ramas borradas el 2026-08-23

Las 39 ramas remotas y 2 locales que quedaban de sesiones anteriores, todas ya
mergeadas. Se borraron para que la lista de ramas vuelva a ser legible.

VERIFICACION previa, una por una: `git cherry main <rama>` no reporto NINGUN
commit sin aplicar en main. Se uso `git cherry` y no `--merged` a proposito:
`--merged` pregunta si el commit es ancestro, y con rebases de por medio eso da
falsos negativos. `git cherry` pregunta si el CAMBIO ya esta aplicado, que es lo
que importa.

Borrar estas ramas no borro ni un commit: su contenido vive en `main`.
Para recrear cualquiera:  `git branch <nombre> <sha>`

```
e7426a6  origin/chore/csp-politica-estricta
2a53052  origin/chore/cve-actualizar-dependencias
fe8e4a7  origin/chore/fase1-endurecimiento-produccion
9c44e60  origin/chore/quitar-console-log
10f4039  origin/docs/auditoria-verificacion-final
e7d8a88  origin/docs/cierre-fase2
e8f4095  origin/docs/cierre-fase4
463ab7e  origin/docs/corregir-alcance-festivo
0340d7e  origin/docs/punto17
519507c  origin/docs/punto18
9868067  origin/feat/cancelacion-consensuada
f6f48e2  origin/fix/auditoria-integridad-y-cierre
9dc4af1  origin/fix/cambio-descanso-temporada
9d87547  origin/fix/doblada-permanente-motivo-no-cubre
4e3db5e  origin/fix/failopen-revalidacion
b5e1af0  origin/fix/idor-edicion-empleado
759658c  origin/fix/log-rotacion-windows
f3995e9  origin/fix/mysql-local-solo-loopback
91a9b1d  origin/fix/turno-explorador-sin-dict-vacio
d0dcf16  origin/limpieza/rutas-huerfanas
b8c3e83  origin/refactor/bloqueo-partes-a-services
1a5111e  origin/refactor/constantes-dominio
cae858d  origin/refactor/error-estructurado-ct-previo
9468602  origin/refactor/fase0-cobertura-y-limpieza
84bd8c8  origin/refactor/fase0-red-de-seguridad
742b06f  origin/refactor/fase2-cancelacion
d9eb7b5  origin/refactor/fase2-fechas-helper
33ff598  origin/refactor/fase2-reconciliacion
3b39d66  origin/refactor/fase3-god-objects
304c3d9  origin/refactor/fase3-reglas-comunes
89c4b02  origin/refactor/trocear-obtener-turno
7b57103  origin/refactor/trocear-verificar-doblada
0625d4e  origin/test/caracterizacion-api-turno
55b9850  origin/test/caracterizacion-doblada-api
ac6c46e  origin/test/fallbacks-api-turno
81f14aa  origin/test/fase3-resolucion-permisos
4cce064  origin/test/festivo-sin-planificar
8620a14  origin/test/js-api-client-y-dom-utils
88c7b60  origin/test/red-de-pruebas-javascript
```
