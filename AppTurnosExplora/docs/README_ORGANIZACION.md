# Estructura de Documentación y Archivos del Proyecto

Este documento explica la organización de todos los archivos del proyecto AppTurnosExplora.

## Estructura de Carpetas

### 📁 `docs/`
Contiene toda la documentación del proyecto organizada por categorías:

#### `docs/analisis/`
Análisis técnicos y de código:
- ANALISIS_DUPLICACIONES.md
- ANALISIS_DUPLICADOS_RESTANTES.md
- ANALISIS_FASE1_1.md
- ANALISIS_MIGRACION_AWS.md
- ANALISIS_SOLID.md
- ANALISIS_VIOLACIONES_SRP.md

#### `docs/arquitectura/`
Documentación sobre arquitectura y estructura del proyecto:
- ARQUITECTURA.md
- ESTRUCTURA_OBJETIVO.md
- CONTEXTO_PROYECTO.md

#### `docs/festivos/`
Documentación relacionada con la lógica de festivos:
- COMO_FUNCIONAN_CALENDARIOS_FESTIVOS.md
- CORRECCION_LEY_EMILIANI.md
- EXPLICACION_FESTIVOS.md
- LIMITES_FESTIVOS_EXPLICACION.md
- REFACTORIZACION_FESTIVOS.md
- RESUMEN_CORRECCION_FESTIVOS.md
- SOLUCION_FESTIVOS_PRECISA.md

#### `docs/guias/`
Guías y manuales de uso:
- GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md
- GUIA_EXPORTAR_CHATS_CURSOR.md
- MANUAL_ENTORNO_VIRTUAL.md
- MANUAL_GITHUB.md
- INSTRUCCIONES_GOOGLE_APPS_SCRIPT.md
- INSTRUCCIONES_OPTIMIZACION.md
- MODIFICACION_GOOGLE_APPS_SCRIPT.md
- VALIDACION_IFRAME_GOOGLE_APPS_SCRIPT.md

#### `docs/planes/`
Planes de implementación y optimización:
- PLAN_IMPLEMENTACION_FASES.md
- PLAN_OPTIMIZACION_FASE3.md

#### `docs/pruebas/`
Documentación de pruebas y testing:
- PRUEBAS_FASE1_5.md
- PRUEBAS_FASE1_16.md
- PRUEBAS_FASE2_6.md
- INVENTARIO_TESTS.md
- TESTS_README.md

#### `docs/resumenes/`
Resúmenes de fases y refactorizaciones:
- RESUMEN_FASE2_PENDIENTES.md
- RESUMEN_REFACTORIZACION.md

#### `docs/soluciones/`
Soluciones a problemas específicos:
- SOLUCION_ERROR_403_XFRAME.md
- SOLUCION_IFRAME_CON_AUTENTICACION.md

#### `docs/verificaciones/`
Documentos de verificación:
- VERIFICACION_FASE2_2.md
- VERIFICACION_FASE2_3.md
- VERIFICACION_FASE2_4.md
- VERIFICACION_FASE2_5.md
- VERIFICACION_ROLLBACK_FASE1_8.md

#### `docs/implementaciones/`
Documentación de implementaciones completas:
- IMPLEMENTACION_BENEFICIOS_COMPLETA.md

#### `docs/manuales/`
Manuales en formato Word:
- Ciclo de Desarrollo Típico para una App en Django.docx
- Manual_Git subir.docx
- Manual_Git_Corto.docx
- Proceso completo doblada.docx
- requisito doblada.docx
- estrucutra sql.docx

#### `docs/database/`
Modelos y diagramas de base de datos:
- modelo relacional.mwb
- modelo relacional.mwb.bak
- modelorelacional.pdf
- pruebas.mwb
- relaciones para ver.mwb

#### `docs/images/`
Imágenes y diagramas:
- diagrama.png
- monitoring.png
- Diagrama.drawio

#### `docs/notas/`
Notas y archivos de texto temporales:
- pendientes que hay que organizar.txt
- solicitud de doblada.txt
- git gurdar lf siempre.txt
- learng.txt

#### `docs/test/`
Documentación de pruebas manuales y reglas de negocio:
- TEST_MANUAL_CAMBIO_TURNO_SENCILLO.md
- REGLAS_NEGOCIO_CAMBIO_TURNO_SENCILLO.md

### 📁 `scripts/`
Scripts organizados por categoría:

#### `scripts/diagnostic/`
Scripts de diagnóstico y análisis:
- analisis_detallado_festivos.py
- debug_luisa.py
- verificar_todos_festivos_2026.py

#### `scripts/utils/`
Scripts de utilidad:
- validar_jornadas.py
- buscar_chats_cursor.ps1

#### `scripts/tests/`
Scripts y archivos de prueba:
- test_iframe_beneficios.html

### 📁 Raíz del Proyecto
Archivos de configuración principales:
- `pytest.ini` - Configuración de pytest

## Convenciones

1. **Documentación Markdown**: Todos los archivos `.md` están organizados en subcarpetas temáticas dentro de `docs/`
2. **Scripts Python**: Todos los scripts están en `scripts/` con subcarpetas por propósito
3. **Archivos de Configuración**: Archivos de configuración del proyecto (como `pytest.ini`) están en la raíz
4. **Documentos Word**: Manuales y documentos extensos están en `docs/manuales/`
5. **Modelos de BD**: Diagramas y modelos de base de datos están en `docs/database/`
6. **Imágenes**: Todas las imágenes y diagramas están en `docs/images/`

## Mantenimiento

- Al agregar nueva documentación, seguir la estructura de carpetas existente
- Scripts temporales deben ir en `scripts/diagnostic/` o `scripts/tests/`
- Scripts de utilidad permanente van en `scripts/utils/`
- Actualizar este README cuando se agreguen nuevas categorías


