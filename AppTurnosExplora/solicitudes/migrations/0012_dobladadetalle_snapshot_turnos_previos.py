# Generated manually for revertir doblada con CT previo

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0011_alter_cambiopermanentedetalle_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='dobladadetalle',
            name='snapshot_turnos_previos',
            field=models.JSONField(
                blank=True,
                help_text='Turnos de solicitante/receptor en fechas de cesión y pago ANTES de aplicar la doblada. '
                'Clave "explorador_id:YYYY-MM-DD", valor lista de {jornada_nombre, sala_id, tipo_cambio}. '
                'Permite revertir la cancelación en 30 min restaurando CT sencillos u otros turnos previos.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='historicaldobladadetalle',
            name='snapshot_turnos_previos',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
