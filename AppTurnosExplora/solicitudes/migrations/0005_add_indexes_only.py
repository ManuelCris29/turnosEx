# Generated manually - Índices ya agregados en 0004 (evitar duplicado)
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0004_remove_historicalpermisodetalle_history_user_and_more'),
    ]

    operations = [
        # Los índices sol_turno_origen_estado_idx, sol_turno_destino_estado_idx y
        # sol_fecha_resol_estado_idx ya se crean en 0004. Esta migración queda como no-op
        # para mantener el historial de migraciones.
    ]

