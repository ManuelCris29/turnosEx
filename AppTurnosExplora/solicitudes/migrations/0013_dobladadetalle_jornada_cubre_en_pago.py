# Generated manually for jornada_cubre_en_pago

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0012_dobladadetalle_snapshot_turnos_previos'),
    ]

    operations = [
        migrations.AddField(
            model_name='dobladadetalle',
            name='jornada_cubre_en_pago',
            field=models.CharField(
                blank=True,
                choices=[('AM', 'AM'), ('PM', 'PM'), ('AMBAS', 'Ambas (receptor descansa el día completo)')],
                help_text='Si el receptor tiene doblada (AM+PM) en fecha de pago: qué parte cubre el deudor, o ambas.',
                max_length=5,
                null=True,
            ),
        ),
    ]
