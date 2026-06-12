# HistoricalDobladaDetalle debe reflejar campos rastreados (jornada_cubre_en_pago no está en excluded_fields).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0013_dobladadetalle_jornada_cubre_en_pago'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicaldobladadetalle',
            name='jornada_cubre_en_pago',
            field=models.CharField(
                blank=True,
                choices=[('AM', 'AM'), ('PM', 'PM'), ('AMBAS', 'Ambas (receptor descansa el día completo)')],
                max_length=5,
                null=True,
            ),
        ),
    ]
