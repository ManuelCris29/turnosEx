# Plan de Organización de Archivos en la Raíz

## Objetivo
Organizar todos los archivos dispersos en la raíz del proyecto (`C:\appTurnos`) siguiendo las mejores prácticas de Django y estructura de proyectos profesionales.

## Estructura Propuesta

### 1. Documentación (.md)
**Destino**: `AppTurnosExplora/docs/` con subcarpetas:

- **Análisis**: `docs/analisis/`
  - ANALISIS_DUPLICACIONES.md
  - ANALISIS_DUPLICADOS_RESTANTES.md
  - ANALISIS_FASE1_1.md
  - ANALISIS_MIGRACION_AWS.md
  - ANALISIS_SOLID.md
  - ANALISIS_VIOLACIONES_SRP.md

- **Arquitectura**: `docs/arquitectura/`
  - ARQUITECTURA.md
  - ESTRUCTURA_OBJETIVO.md
  - CONTEXTO_PROYECTO.md

- **Guías y Manuales**: `docs/guias/`
  - GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md
  - GUIA_EXPORTAR_CHATS_CURSOR.md
  - MANUAL_ENTORNO_VIRTUAL.md
  - MANUAL_GITHUB.md
  - INSTRUCCIONES_GOOGLE_APPS_SCRIPT.md
  - INSTRUCCIONES_OPTIMIZACION.md
  - MODIFICACION_GOOGLE_APPS_SCRIPT.md
  - VALIDACION_IFRAME_GOOGLE_APPS_SCRIPT.md

- **Festivos**: `docs/festivos/`
  - COMO_FUNCIONAN_CALENDARIOS_FESTIVOS.md
  - CORRECCION_LEY_EMILIANI.md
  - EXPLICACION_FESTIVOS.md
  - LIMITES_FESTIVOS_EXPLICACION.md
  - REFACTORIZACION_FESTIVOS.md
  - RESUMEN_CORRECCION_FESTIVOS.md
  - SOLUCION_FESTIVOS_PRECISA.md

- **Planes**: `docs/planes/`
  - PLAN_IMPLEMENTACION_FASES.md
  - PLAN_OPTIMIZACION_FASE3.md

- **Pruebas**: `docs/pruebas/`
  - PRUEBAS_FASE1_5.md
  - PRUEBAS_FASE1_16.md
  - PRUEBAS_FASE2_6.md
  - INVENTARIO_TESTS.md
  - TESTS_README.md

- **Resúmenes**: `docs/resumenes/`
  - RESUMEN_FASE2_PENDIENTES.md
  - RESUMEN_REFACTORIZACION.md

- **Soluciones**: `docs/soluciones/`
  - SOLUCION_ERROR_403_XFRAME.md
  - SOLUCION_IFRAME_CON_AUTENTICACION.md

- **Verificaciones**: `docs/verificaciones/`
  - VERIFICACION_FASE2_2.md
  - VERIFICACION_FASE2_3.md
  - VERIFICACION_FASE2_4.md
  - VERIFICACION_FASE2_5.md
  - VERIFICACION_ROLLBACK_FASE1_8.md

- **Implementaciones**: `docs/implementaciones/`
  - IMPLEMENTACION_BENEFICIOS_COMPLETA.md

### 2. Scripts Python (.py)
**Destino**: `AppTurnosExplora/scripts/` con subcarpetas:

- **Diagnostic**: `scripts/diagnostic/`
  - analisis_detallado_festivos.py
  - debug_luisa.py
  - verificar_todos_festivos_2026.py

- **Utils**: `scripts/utils/`
  - validar_jornadas.py

### 3. Archivos Word (.docx)
**Destino**: `AppTurnosExplora/docs/manuales/`
- Ciclo de Desarrollo Típico para una App en Django.docx
- Manual_Git subir.docx
- Manual_Git_Corto.docx
- Proceso completo doblada.docx
- requisito doblada.docx
- estrucutra sql.docx

### 4. Modelos de Base de Datos
**Destino**: `AppTurnosExplora/docs/database/`
- modelo relacional.mwb
- modelo relacional.mwb.bak
- modelorelacional.pdf
- pruebas.mwb
- relaciones para ver.mwb

### 5. Archivos de Configuración
**Destino**: `AppTurnosExplora/`
- pytest.ini

### 6. Scripts PowerShell (.ps1)
**Destino**: `AppTurnosExplora/scripts/utils/`
- buscar_chats_cursor.ps1

### 7. Archivos HTML de Prueba
**Destino**: `AppTurnosExplora/scripts/tests/`
- test_iframe_beneficios.html

### 8. Imágenes y Diagramas
**Destino**: `AppTurnosExplora/docs/images/`
- diagrama.png
- monitoring.png
- Diagrama.drawio (si es necesario mantenerlo)

### 9. Archivos de Texto (Notas)
**Destino**: `AppTurnosExplora/docs/notas/`
- pendientes que hay que organizar.txt
- solicitud de doblada.txt
- git gurdar lf siempre.txt
- learng.txt

### 10. Archivos Temporales
**Eliminar o ignorar**:
- ~$*.docx (archivos temporales de Word)
- .$Diagrama.drawio.dtmp

### 11. Archivos Especiales
- **turnos** (archivo sin extensión): Verificar qué es y mover apropiadamente
- **Explora** (archivo sin extensión): Verificar qué es y mover apropiadamente

## Orden de Ejecución

1. Crear todas las subcarpetas necesarias
2. Mover archivos de documentación (.md)
3. Mover scripts Python
4. Mover archivos Word
5. Mover modelos de BD
6. Mover archivos de configuración
7. Mover scripts PowerShell
8. Mover archivos HTML
9. Mover imágenes
10. Mover archivos de texto
11. Eliminar archivos temporales
12. Verificar archivos especiales
13. Actualizar .gitignore si es necesario

## Consideraciones

- Mantener referencias en código si algún script hace referencia a rutas absolutas
- Actualizar documentación que haga referencia a ubicaciones de archivos
- Verificar que no se rompan enlaces o referencias en documentos
- Crear README.md en cada carpeta principal explicando su contenido




