# Generated by Django 5.2.2 on 2025-07-03 17:23

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('empleados', '0001_initial'),
        ('turnos', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TipoSolicitudCambio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=50)),
                ('activo', models.BooleanField(default=True)),
                ('genera_deuda', models.BooleanField(default=False, help_text='¿Este tipo de solicitud genera deuda de horas?')),
            ],
        ),
        migrations.CreateModel(
            name='HistoricalTipoSolicitudCambio',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('nombre', models.CharField(max_length=50)),
                ('activo', models.BooleanField(default=True)),
                ('genera_deuda', models.BooleanField(default=False, help_text='¿Este tipo de solicitud genera deuda de horas?')),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical tipo solicitud cambio',
                'verbose_name_plural': 'historical tipo solicitud cambios',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='SolicitudCambio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente'), ('aprobada', 'Aprobada'), ('rechazada', 'Rechazada'), ('pagada', 'Pagada')], default='pendiente', max_length=20)),
                ('fecha_solicitud', models.DateTimeField(auto_now_add=True)),
                ('fecha_resolucion', models.DateTimeField(blank=True, null=True)),
                ('comentario', models.TextField(blank=True, null=True)),
                ('aprobado_receptor', models.BooleanField(default=False)),
                ('fecha_aprobacion_receptor', models.DateTimeField(blank=True, null=True)),
                ('aprobado_supervisor', models.BooleanField(default=False)),
                ('fecha_aprobacion_supervisor', models.DateTimeField(blank=True, null=True)),
                ('explorador_receptor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='solicitudes_recibidas', to='empleados.empleado')),
                ('explorador_solicitante', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='solicitudes_enviadas', to='empleados.empleado')),
                ('solicitud_origen', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transferencias', to='solicitudes.solicitudcambio')),
                ('turno_destino', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='solicitud_destino', to='turnos.turno')),
                ('turno_origen', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='solicitud_origen', to='turnos.turno')),
                ('tipo_cambio', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='solicitudes.tiposolicitudcambio')),
            ],
        ),
        migrations.CreateModel(
            name='PermisoDetalle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('horas_solicitadas', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('fecha_pago', models.DateField(blank=True, null=True)),
                ('solicitud', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='permiso', to='solicitudes.solicitudcambio')),
            ],
        ),
        migrations.CreateModel(
            name='HistoricalPermisoDetalle',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('horas_solicitadas', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('fecha_pago', models.DateField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('solicitud', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='solicitudes.solicitudcambio')),
            ],
            options={
                'verbose_name': 'historical permiso detalle',
                'verbose_name_plural': 'historical permiso detalles',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalDobladaDetalle',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('minutos_deuda', models.IntegerField(default=30)),
                ('fecha_pago', models.DateField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('solicitud', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='solicitudes.solicitudcambio')),
            ],
            options={
                'verbose_name': 'historical doblada detalle',
                'verbose_name_plural': 'historical doblada detalles',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalCambioPermanenteDetalle',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('fecha_inicio', models.DateField()),
                ('fecha_fin', models.DateField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('solicitud', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='solicitudes.solicitudcambio')),
            ],
            options={
                'verbose_name': 'historical cambio permanente detalle',
                'verbose_name_plural': 'historical cambio permanente detalles',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='DobladaDetalle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('minutos_deuda', models.IntegerField(default=30)),
                ('fecha_pago', models.DateField(blank=True, null=True)),
                ('solicitud', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='doblada', to='solicitudes.solicitudcambio')),
            ],
        ),
        migrations.CreateModel(
            name='CambioPermanenteDetalle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_inicio', models.DateField()),
                ('fecha_fin', models.DateField(blank=True, null=True)),
                ('solicitud', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='cambio_permanente', to='solicitudes.solicitudcambio')),
            ],
        ),
        migrations.CreateModel(
            name='HistoricalSolicitudCambio',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente'), ('aprobada', 'Aprobada'), ('rechazada', 'Rechazada'), ('pagada', 'Pagada')], default='pendiente', max_length=20)),
                ('fecha_solicitud', models.DateTimeField(blank=True, editable=False)),
                ('fecha_resolucion', models.DateTimeField(blank=True, null=True)),
                ('comentario', models.TextField(blank=True, null=True)),
                ('aprobado_receptor', models.BooleanField(default=False)),
                ('fecha_aprobacion_receptor', models.DateTimeField(blank=True, null=True)),
                ('aprobado_supervisor', models.BooleanField(default=False)),
                ('fecha_aprobacion_supervisor', models.DateTimeField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('explorador_receptor', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='empleados.empleado')),
                ('explorador_solicitante', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='empleados.empleado')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('turno_destino', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='turnos.turno')),
                ('turno_origen', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='turnos.turno')),
                ('solicitud_origen', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='solicitudes.solicitudcambio')),
                ('tipo_cambio', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='solicitudes.tiposolicitudcambio')),
            ],
            options={
                'verbose_name': 'historical solicitud cambio',
                'verbose_name_plural': 'historical solicitud cambios',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
