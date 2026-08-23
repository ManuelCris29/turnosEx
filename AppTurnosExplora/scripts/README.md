# Scripts del proyecto AppTurnosExplora

Scripts de utilidad, diagnóstico, corrección de datos y mantenimiento. **No son parte de
la aplicación**: nada en `AppTurnosExplora/` importa esta carpeta.

> **Auditado contra el disco el 2026-08-23.** El inventario de abajo es el real.

## Advertencia previa: esto es código de usar y tirar

La mayoría de estos ficheros se escribieron para un incidente concreto de la base de
**desarrollo** (nombres propios y números de solicitud en el nombre lo delatan:
`corregir_solicitud_110.py`, `diagnosticar_marco_28_feb.py`, `debug_luisa.py`). Producción
arranca limpia, así que **no sirven como herramienta operativa**: son histórico. Léelos
antes de ejecutar ninguno, y no ejecutes los de `data/` ni `migrations/` contra una base
que te importe.

## Estructura real

```
scripts/
├── __init__.py
├── diagnosticar_doblada_jhon_14_feb.py    ← sueltos en la raíz: sin clasificar
├── diagnosticar_doblada_jhon_28_feb.py
├── diagnosticar_marco_28_feb.py
├── test_buscar_marco.py
├── verificar_solicitud_doblada.py
│
├── tests/          test_architecture, test_cancelacion_solicitudes, test_counter,
│                   test_ct_permanente, test_email_from_user, test_jornadas_corregidas,
│                   test_manual_request, test_new_notification, test_iframe_beneficios.html
│
├── debug/          debug_luisa_notifications, debug_manuel_notifications, debug_solicitud
│
├── diagnostic/     analisis_detallado_festivos, debug_luisa, diagnosticar_doblada_28_29,
│                   diagnosticar_doblada_marco, diagnosticar_solicitud_111,
│                   verificar_todos_festivos_2026
│
├── utils/          check_recent_requests, clean_corrupt_data, create_luisa_request,
│                   fix_solicitud_10, validar_jornadas, verificar_cambios_permanentes,
│                   buscar_chats_cursor.ps1
│
├── migrations/     agregar_columna_jornada_pago_sabado,
│                   agregar_columna_historica_jornada_pago_sabado,
│                   corregir_tabla_historica_jornada_pago_sabado,
│                   crear_tabla_historica_completa,
│                   forzar_reconocimiento_columna_historica,
│                   solucion_completa_historial_jornada_pago_sabado,
│                   verificar_y_corregir_tabla_historica
│
├── data/           corregir_dobladas_existentes, corregir_solicitud_110,
│                   resetear_aprobaciones_110, resetear_solicitud_108,
│                   resetear_solicitud_111, verificar_solicitud_110
│
└── maintenance/    debug_sql_historico, limpiar_cache_turnos, test_alternancia_31_enero,
                    test_crear_doblada_detalle, test_envio_correos,
                    verificar_columna_jornada_pago_sabado
```

## Los `test_*.py` de aquí NO son la suite de tests

Se llaman `test_*` pero no lo son: son scripts manuales. La suite real vive en
`integration_tests/`, `core/tests/`, `solicitudes/tests/`, `turnos/tests/`,
`empleados/tests/` y `permisos/tests/`, que son exactamente los `testpaths` de
`pytest.ini`.

Por eso el CI ejecuta `pytest` **sin `.` final**: con `.` recogería estos ficheros y la
suite intentaría correr scripts que tocan datos. Si añades un script aquí, no lo llames
`test_*` — o al menos no lo esperes fuera de esta carpeta.

Las pruebas de JavaScript son otra cosa distinta y viven en
[`tests_js/`](../tests_js/README.md).

## Cómo se ejecutan

Desde la raíz del proyecto, con el entorno virtual activado:

```powershell
cd C:\appTurnos
.\venvturnos\Scripts\Activate.ps1
python AppTurnosExplora\scripts\utils\validar_jornadas.py
```

Los scripts que hablan con la base necesitan el entorno de Django configurado
(`DJANGO_SETTINGS_MODULE=config.settings`); varios lo hacen ellos mismos con
`django.setup()`. Revisa la cabecera del script antes de lanzarlo.

## Alternativa recomendada: comandos de gestión

Para tareas **operativas y repetibles** no uses esta carpeta: usa los comandos de
gestión de Django, que sí son código mantenido y con tests. Los que existen hoy:

```bash
# solicitudes
python manage.py procesar_email_outbox          # obligatorio por cron en producción
python manage.py archivar_solicitudes_antiguas
python manage.py cancelar_deudas_fin_semana
python manage.py cancelar_deudas_huerfanas
python manage.py actualizar_codigos_estrategia
python manage.py verificar_integridad_dobladas
python manage.py reaplicar_doblada
python manage.py validar_jornadas

# turnos
python manage.py materializar_alternancia
python manage.py archivar_turnos_antiguos
python manage.py limpiar_festivos_futuros
python manage.py verificar_apertura_anio

# core
python manage.py verificar_ip_cliente           # antes de publicar la URL (django-axes)
```

(La lista completa está en `*/management/commands/`.)

## Reglas

- Lee el script antes de ejecutarlo.
- Backup de la base antes de cualquier script de `data/` o `migrations/`.
- Un script nuevo va en la subcarpeta que le toque, **no en la raíz** de `scripts/`.
- Si un script sobrevive a su incidente y se vuelve rutina, conviértelo en comando de
  gestión y bórralo de aquí.
