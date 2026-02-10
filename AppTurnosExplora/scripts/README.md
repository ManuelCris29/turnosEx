# Scripts del Proyecto AppTurnosExplora

Este directorio contiene scripts de utilidad, pruebas, debugging y mantenimiento del proyecto.

## 📁 Estructura

```
scripts/
├── tests/              # Scripts de prueba temporales
│   ├── test_architecture.py
│   ├── test_cancelacion_solicitudes.py
│   ├── test_counter.py
│   ├── test_ct_permanente.py
│   ├── test_email_from_user.py
│   ├── test_jornadas_corregidas.py
│   ├── test_manual_request.py
│   └── test_new_notification.py
│
├── debug/              # Scripts de debugging
│   ├── debug_luisa_notifications.py
│   ├── debug_manuel_notifications.py
│   └── debug_solicitud.py
│
├── utils/              # Scripts de utilidad general
│   ├── check_recent_requests.py
│   ├── clean_corrupt_data.py
│   ├── create_luisa_request.py
│   ├── fix_solicitud_10.py
│   ├── validar_jornadas.py
│   └── verificar_cambios_permanentes.py
│
├── migrations/         # Scripts relacionados con migraciones de BD
│   ├── agregar_columna_historica_jornada_pago_sabado.py
│   ├── agregar_columna_jornada_pago_sabado.py
│   ├── corregir_tabla_historica_jornada_pago_sabado.py
│   ├── crear_tabla_historica_completa.py
│   ├── forzar_reconocimiento_columna_historica.py
│   └── verificar_y_corregir_tabla_historica.py
│
├── data/               # Scripts de corrección de datos
│   ├── corregir_dobladas_existentes.py
│   ├── corregir_solicitud_110.py
│   ├── resetear_aprobaciones_110.py
│   ├── resetear_solicitud_108.py
│   ├── resetear_solicitud_111.py
│   └── verificar_solicitud_110.py
│
├── diagnostic/         # Scripts de diagnóstico
│   ├── diagnosticar_doblada_28_29.py
│   ├── diagnosticar_doblada_marco.py
│   └── diagnosticar_solicitud_111.py
│
└── maintenance/        # Scripts de mantenimiento
    ├── debug_sql_historico.py
    ├── limpiar_cache_turnos.py
    ├── test_alternancia_31_enero.py
    ├── test_crear_doblada_detalle.py
    ├── test_envio_correos.py
    └── verificar_columna_jornada_pago_sabado.py
```

## 🚀 Uso

Los scripts deben ejecutarse desde la raíz del proyecto con el entorno virtual activado:

```bash
# Activar entorno virtual
cd C:\appTurnos
.\venvturnos\Scripts\Activate.ps1

# Ejecutar un script
python scripts/tests/test_architecture.py
python scripts/debug/debug_solicitud.py
python scripts/utils/validar_jornadas.py
```

## 📝 Notas

- **Scripts de prueba**: Son temporales y pueden eliminarse después de su uso
- **Scripts de debug**: Útiles para diagnosticar problemas específicos
- **Scripts de utilidad**: Herramientas reutilizables para tareas comunes
- **Scripts de migraciones**: Relacionados con cambios en la estructura de BD
- **Scripts de datos**: Para corregir o verificar datos existentes
- **Scripts de diagnóstico**: Para analizar problemas específicos
- **Scripts de mantenimiento**: Para tareas de mantenimiento periódico

## ⚠️ Advertencias

- Siempre revisa el script antes de ejecutarlo
- Haz backup de la base de datos antes de ejecutar scripts que modifiquen datos
- Los scripts de prueba pueden modificar datos de prueba
- Algunos scripts pueden requerir parámetros específicos

---

**Última actualización**: 2026-01-XX

