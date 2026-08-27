"""
El correo deja de estar duplicado: pasa a vivir solo en la cuenta.

`Empleado.email` y `User.email` guardaban el mismo dato sin nada que los
mantuviera iguales, y se separaban por dos caminos distintos (editar la ficha
solo escribia la copia del `Empleado`; crear un empleado sobre una cuenta ya
existente dejaba en el `User` el correo antiguo). A partir de aqui `Empleado.email`
es una propiedad de solo-delegacion sobre `self.user.email`.

Antes de borrar la columna se vuelca su contenido a la cuenta, para no perder los
correos ya cargados. Solo se rellenan las cuentas SIN correo: si el `User` ya
tiene uno, es el que Django usa hoy para el restablecimiento de contrasena y
pisarlo cambiaria a donde llega ese enlace. Ante dos valores en conflicto se
conserva el que ya gobierna el acceso.
"""
from django.conf import settings
from django.db import migrations


def volcar_email_a_la_cuenta(apps, schema_editor):
    Empleado = apps.get_model('empleados', 'Empleado')
    User = apps.get_model('auth', 'User')

    pendientes = []
    for empleado in Empleado.objects.select_related('user').exclude(email=''):
        cuenta = empleado.user
        if cuenta and not (cuenta.email or '').strip():
            cuenta.email = empleado.email
            pendientes.append(cuenta)

    if pendientes:
        User.objects.bulk_update(pendientes, ['email'], batch_size=500)


def restaurar_email_en_la_ficha(apps, schema_editor):
    """
    Al revertir, la columna vuelve vacia y sin esto quedaria asi. Se rellena
    desde la cuenta, que es de donde salio.
    """
    Empleado = apps.get_model('empleados', 'Empleado')

    pendientes = []
    for empleado in Empleado.objects.select_related('user'):
        if empleado.user and empleado.user.email:
            empleado.email = empleado.user.email
            pendientes.append(empleado)

    if pendientes:
        Empleado.objects.bulk_update(pendientes, ['email'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('empleados', '0009_historicalsancionempleado_nivel_reincidencia_and_more'),
    ]

    operations = [
        migrations.RunPython(volcar_email_a_la_cuenta, restaurar_email_en_la_ficha),
        migrations.RemoveField(
            model_name='empleado',
            name='email',
        ),
        migrations.RemoveField(
            model_name='historicalempleado',
            name='email',
        ),
    ]
