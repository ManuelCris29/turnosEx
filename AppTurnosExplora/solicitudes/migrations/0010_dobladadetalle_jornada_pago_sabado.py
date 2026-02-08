from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("solicitudes", "0009_dobladadetalle_empleado_receptor_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="dobladadetalle",
            name="jornada_pago_sabado",
            field=models.CharField(
                blank=True,
                choices=[("AM", "AM"), ("PM", "PM")],
                help_text="Si la fecha de pago es sábado, jornada (AM/PM) que el solicitante elige trabajar ese sábado",
                max_length=2,
                null=True,
            ),
        ),
    ]



