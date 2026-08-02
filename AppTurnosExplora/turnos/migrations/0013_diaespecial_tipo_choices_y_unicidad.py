from django.db import migrations, models


def normalizar_dias_especiales(apps, schema_editor):
    """
    Deja los datos en el estado que la nueva constraint exige.

    1. Normaliza `tipo` a minúsculas: antes era texto libre y `es_festivo()` compara
       por igualdad exacta, así que un "Festivo" quedaba sin efecto.
    2. Sincroniza `mes`/`año_planificacion` con `fecha` (ahora son siempre derivados).
    3. Elimina duplicados de (fecha, tipo) conservando el más antiguo, para que se
       pueda crear el índice único.
    """
    DiaEspecial = apps.get_model('turnos', 'DiaEspecial')

    for dia in DiaEspecial.objects.all().iterator():
        tipo_norm = (dia.tipo or '').strip().lower()
        mes = dia.fecha.month if dia.fecha else dia.mes
        anio = dia.fecha.year if dia.fecha else dia.año_planificacion
        if (tipo_norm, mes, anio) != (dia.tipo, dia.mes, dia.año_planificacion):
            dia.tipo = tipo_norm
            dia.mes = mes
            dia.año_planificacion = anio
            dia.save(update_fields=['tipo', 'mes', 'año_planificacion'])

    vistos = set()
    duplicados = []
    for pk, fecha, tipo in DiaEspecial.objects.order_by('id').values_list('id', 'fecha', 'tipo'):
        clave = (fecha, tipo)
        if clave in vistos:
            duplicados.append(pk)
        else:
            vistos.add(clave)

    if duplicados:
        DiaEspecial.objects.filter(id__in=duplicados).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('turnos', '0012_aperturaanioconfig_historicalaperturaanioconfig'),
    ]

    operations = [
        migrations.RunPython(normalizar_dias_especiales, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='diaespecial',
            name='tipo',
            field=models.CharField(
                choices=[('festivo', 'Festivo'), ('mantenimiento', 'Mantenimiento'), ('temporada', 'Temporada')],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='historicaldiaespecial',
            name='tipo',
            field=models.CharField(
                choices=[('festivo', 'Festivo'), ('mantenimiento', 'Mantenimiento'), ('temporada', 'Temporada')],
                max_length=50,
            ),
        ),
        migrations.AddConstraint(
            model_name='diaespecial',
            constraint=models.UniqueConstraint(fields=('fecha', 'tipo'), name='dia_esp_fecha_tipo_uniq'),
        ),
    ]
