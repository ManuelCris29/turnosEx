# Generated manually - Solo para agregar índices
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0004_remove_historicalpermisodetalle_history_user_and_more'),
    ]

    operations = [
        # Solo agregar los índices, sin tocar las tablas que no existen
        migrations.AddIndex(
            model_name='solicitudcambio',
            index=models.Index(fields=['turno_origen', 'estado'], name='sol_turno_origen_estado_idx'),
        ),
        migrations.AddIndex(
            model_name='solicitudcambio',
            index=models.Index(fields=['turno_destino', 'estado'], name='sol_turno_destino_estado_idx'),
        ),
        migrations.AddIndex(
            model_name='solicitudcambio',
            index=models.Index(fields=['-fecha_resolucion', 'estado'], name='sol_fecha_resol_estado_idx'),
        ),
    ]

