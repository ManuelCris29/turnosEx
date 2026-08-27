from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from simple_history.models import HistoricalRecords


class Jornada(models.Model):
    """Modelo para representar las jornadas de trabajo (AM, PM).

    Catálogo ESTRUCTURAL: el motor de turnos asume exactamente estas dos
    jornadas y las busca por nombre literal (``Jornada.objects.get(nombre='AM')``),
    además de derivar la "jornada contraria" de forma binaria. Por eso el
    nombre está restringido a AM/PM, es único, y las dos filas base no se
    pueden eliminar (ver JornadaDeleteView).
    """
    AM = 'AM'
    PM = 'PM'
    NOMBRE_CHOICES = [(AM, 'AM'), (PM, 'PM')]
    #: Jornadas que el motor de turnos requiere y que no se pueden eliminar.
    NOMBRES_PROTEGIDOS = (AM, PM)

    nombre = models.CharField(max_length=5, unique=True, choices=NOMBRE_CHOICES)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Jornada'
        verbose_name_plural = 'Jornadas'
        ordering = ['nombre']

    def __str__(self):
        return str(self.nombre)

    @property
    def es_protegida(self):
        """True si es una de las jornadas base que el sistema requiere."""
        return self.nombre in self.NOMBRES_PROTEGIDOS

class Empleado(models.Model):
    """Modelo principal para representar empleados/exploradores del sistema."""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    cedula = models.CharField(max_length=10, unique=True)
    activo = models.BooleanField(default=True) #type:ignore
    supervisor = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='empleados_supervisados')
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Empleado'
        verbose_name_plural = 'Empleados'
        ordering = ['apellido', 'nombre']
        indexes = [
            models.Index(fields=['activo'], name='empleado_activo_idx'),
            models.Index(fields=['supervisor', 'activo'], name='empleado_super_activo_idx'),
        ]
    
    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.user.username})"

    @property
    def email(self):
        """
        El correo del empleado ES el de su cuenta. No hay copia.

        Hasta la migración 0010 el correo estaba en dos sitios —
        `Empleado.email` y `User.email`— y nada garantizaba que coincidieran.
        Se desincronizaban por dos puertas: editar la ficha solo escribía la
        copia del `Empleado`, y crear un empleado sobre una cuenta ya existente
        dejaba en el `User` el correo de su vida anterior. El resultado era que
        los avisos de solicitudes salían a un buzón y el restablecimiento de
        contraseña de Django —que lee del `User`— a otro, sin que nadie viera
        la discrepancia.

        Arreglar cada punto de escritura solo habría tapado los conocidos: la
        duplicación seguiría ahí, esperando al tercero. Aquí no hay nada que
        sincronizar porque solo existe un dato.

        Se mantiene el nombre `empleado.email` a propósito: es como lo leen los
        servicios de correo y las plantillas, y esa lectura no tenía por qué
        cambiar. El coste es que tocarlo sin `select_related('user')` dispara
        una consulta por empleado; los listados que lo muestran ya lo traen.
        """
        return self.user.email if self.user_id else ''

    @email.setter
    def email(self, valor):
        # Escribir aquí NO guarda: deja el valor en el `User` en memoria, igual
        # que asignar cualquier atributo de un modelo. Quien asigna es quien
        # llama a `user.save()` — y es intencionado que se vea, porque el dato
        # que se toca vive en otra fila.
        try:
            cuenta = self.user
        except User.DoesNotExist:
            # Sin cuenta no hay donde escribir. Fallar aqui es mejor que aceptar
            # el valor y perderlo en silencio al guardar.
            raise ValueError(
                'No se puede asignar el email: el empleado aun no tiene cuenta. '
                'Asigna primero `user`.'
            )
        cuenta.email = valor or ''
    
    def notificaciones_no_leidas_count(self):
        """Retorna el número de notificaciones no leídas"""
        return self.notificaciones.filter(leida=False).count()

class Role(models.Model):
    """Modelo para representar roles de empleados (ej: supervisor, explorador).

    Catálogo ESTRUCTURAL: "Supervisor" y "Explorador" no son etiquetas libres.
    El permiso de administración (``core.mixins.es_supervisor``) y el conjunto
    de exploradores sancionables se resuelven buscando el rol **por nombre**,
    así que renombrarlos o borrarlos dejaría a la aplicación sin supervisores
    o sin exploradores. Por eso el nombre es único, esos dos están protegidos
    y RoleForm rechaza nombres que se confundan con ellos: un rol llamado
    "Supervisor de sala" antes concedía acceso total (la búsqueda era
    ``icontains``), lo que convertía este CRUD en una vía de escalada.
    """
    SUPERVISOR = 'Supervisor'
    EXPLORADOR = 'Explorador'
    #: Roles que el sistema requiere y que no se pueden renombrar ni eliminar.
    NOMBRES_PROTEGIDOS = (SUPERVISOR, EXPLORADOR)

    nombre = models.CharField(max_length=50, unique=True)
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'
        ordering = ['nombre']

    def __str__(self):
        return str(self.nombre)

    @property
    def es_protegido(self):
        """True si es uno de los roles base que el sistema requiere.

        Sin distinguir mayúsculas, igual que la búsqueda del permiso: un rol
        guardado como "supervisor" concede acceso, así que también hay que
        protegerlo de renombrados y borrados.
        """
        nombre = (self.nombre or '').strip().lower()
        return nombre in {n.lower() for n in self.NOMBRES_PROTEGIDOS}

class EmpleadoRole(models.Model):
    """Modelo intermedio para la relación muchos a muchos entre Empleado y Role."""
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    # PROTECT y no CASCADE: borrar el rol "Supervisor" arrastraba en silencio
    # todas sus asignaciones y dejaba a la operación sin supervisores.
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Rol de Empleado'
        verbose_name_plural = 'Roles de Empleados'
        ordering = ['empleado', 'role']
        unique_together = [['empleado', 'role']]
        indexes = [
            models.Index(fields=['empleado', 'role'], name='empleado_role_comp_idx'),
        ]
    
    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.role.nombre}"

class Sala(models.Model):
    """Modelo para representar las salas del Parque Explora."""
    nombre = models.CharField(max_length=50)
    activo = models.BooleanField(default=True) #type:ignore
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Sala'
        verbose_name_plural = 'Salas'
        ordering = ['nombre']
        indexes = [
            models.Index(fields=['activo'], name='sala_activo_idx'),
        ]
    
    def __str__(self):
        return str(self.nombre)

class CompetenciaEmpleado(models.Model):
    """Modelo para representar las competencias de empleados en salas específicas."""
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE)
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Competencia de Empleado'
        verbose_name_plural = 'Competencias de Empleados'
        ordering = ['empleado', 'sala']
        unique_together = [['empleado', 'sala']]
        indexes = [
            models.Index(fields=['empleado', 'sala'], name='comp_emp_sala_idx'),
        ]
    
    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.sala.nombre}"

class RestriccionEmpleado(models.Model):
    """Modelo para representar restricciones temporales de empleados."""
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    recomendacion = models.TextField()
    tipo_restriccion = models.CharField(max_length=50)
    creado_en=models.DateTimeField(auto_now_add=True)
    actualizado_en=models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Restricción de Empleado'
        verbose_name_plural = 'Restricciones de Empleados'
        ordering = ['-fecha_inicio', 'empleado']
        indexes = [
            models.Index(fields=['empleado', 'fecha_inicio'], name='rest_emp_fecha_idx'),
            models.Index(fields=['tipo_restriccion'], name='rest_tipo_idx'),
        ]
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio.')
    
    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.tipo_restriccion}"

class SancionEmpleado(models.Model):
    """
    Sanción aplicada a un explorador: durante su vigencia no puede participar en
    ninguna solicitud (ni como solicitante ni como compañero).

    Una sanción NO se borra: es un hecho disciplinario y su registro debe sobrevivir.
    Para terminarla antes de tiempo se LEVANTA (`levantar`), que deja constancia de
    quién, cuándo y por qué. Los errores ("se la puse a quien no era") también se
    corrigen levantándola con ese motivo, no haciéndola desaparecer.

    `fecha_fin` es el fin PLANEADO y no se toca nunca después de crearla. El fin REAL
    lo da `levantada_en` cuando existe. Antes ambos vivían en `fecha_fin`: levantar
    consistía en moverla a `hoy - 1 día`, lo que borraba la duración original y, si la
    sanción se levantaba el mismo día en que nacía, dejaba `fecha_fin < fecha_inicio`
    —un rango imposible que el propio `clean()` de este modelo prohíbe—. Ver
    PROTECTION_PATTERNS.md.
    """
    explorador = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='sanciones_explorador')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    motivo = models.TextField()
    creado_en=models.DateTimeField(auto_now_add=True)
    actualizado_en=models.DateTimeField(auto_now=True)
    supervisor = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='sanciones_supervisor')
    levantada_en = models.DateField(
        null=True, blank=True,
        help_text='Fecha en que se levantó la sanción. Vacío = sigue su curso normal.')
    levantada_por = models.ForeignKey(
        Empleado, on_delete=models.PROTECT, null=True, blank=True,
        related_name='sanciones_levantadas',
        help_text='Supervisor que la levantó (vacío si la levantó el sistema por pago de deuda).')
    levantada_motivo = models.TextField(blank=True, default='')
    # Mes cuya deuda originó la sanción (solo las automáticas). Se guarda en vez de
    # deducirse del `motivo` porque de él depende QUÉ deuda extingue la sanción al
    # cumplirse: leerlo de un texto libre haría que un retoque de redacción cambiara
    # silenciosamente qué se condona.
    periodo_anio = models.PositiveSmallIntegerField(null=True, blank=True)
    periodo_mes = models.PositiveSmallIntegerField(null=True, blank=True)
    # Qué número de la cadena de reincidencia es esta sanción: 1 = primera (15 días),
    # 2 = primera reincidencia (30 días)… Se GUARDA en vez de recalcularse porque el nivel
    # depende de una ventana configurable: si el supervisor la cambia mañana, las sanciones
    # ya notificadas no pueden reinterpretarse con la regla nueva. Aquí queda lo que se le
    # dijo al explorador en su momento.
    nivel_reincidencia = models.PositiveSmallIntegerField(
        default=1,
        help_text='1 = primera sanción; 2, 3… reincidencias sucesivas. Duración = nivel × 15 días.')
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Sanción de Empleado'
        verbose_name_plural = 'Sanciones de Empleados'
        ordering = ['-fecha_inicio', 'explorador']
        indexes = [
            models.Index(fields=['explorador', 'fecha_inicio'], name='sanc_exp_fecha_idx'),
            models.Index(fields=['supervisor'], name='sanc_supervisor_idx'),
            models.Index(fields=['explorador', 'periodo_anio', 'periodo_mes'],
                         name='sanc_exp_periodo_idx'),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio.')
        # Ambos FK son obligatorios pero pueden no estar asignados todavía
        # cuando la validación corre desde un formulario que los excluye.
        if self.explorador_id and self.supervisor_id and self.explorador_id == self.supervisor_id:
            raise ValidationError('Un empleado no puede sancionarse a sí mismo.')

    # ------------------------------------------------------------------ estado
    @property
    def esta_levantada(self) -> bool:
        return self.levantada_en is not None

    @property
    def fecha_fin_efectiva(self):
        """
        Último día en que la sanción tuvo efecto real. Al levantarla deja de aplicar
        DESDE ese mismo día, así que el último día sancionado es el anterior. Puede
        quedar antes que `fecha_inicio` (levantada el día que empezó): eso significa
        que no llegó a surtir efecto ningún día, y por eso se calcula en vez de
        guardarse — un rango invertido en la BD sería un dato corrupto.
        """
        if self.levantada_en:
            return self.levantada_en - timedelta(days=1)
        return self.fecha_fin

    @property
    def estado(self) -> str:
        """
        'levantada' | 'finalizada' | 'activa', para pintar en las listas. Vive aquí y no
        en las plantillas porque antes cada tabla lo recalculaba a mano y ninguna sabía
        de los levantamientos. Debe coincidir con `_FILTROS_ESTADO` de la vista.
        """
        from django.utils import timezone
        if self.levantada_en:
            return 'levantada'
        if self.fecha_fin and self.fecha_fin < timezone.localdate():
            return 'finalizada'
        return 'activa'

    def esta_vigente(self, fecha=None) -> bool:
        """¿Bloquea a este explorador en la fecha dada (hoy por defecto)?"""
        from django.utils import timezone
        f = fecha or timezone.localdate()
        if self.levantada_en and f >= self.levantada_en:
            return False
        if f < self.fecha_inicio:
            return False
        return self.fecha_fin is None or f <= self.fecha_fin

    def levantar(self, motivo: str, supervisor=None, fecha=None):
        """
        Termina la sanción a partir de `fecha` (hoy por defecto) dejando constancia.
        Idempotente: levantar una ya levantada no cambia nada, para que un doble clic
        o un reintento del proceso automático no reescriba quién la levantó.
        """
        from django.utils import timezone
        if self.levantada_en:
            return self
        self.levantada_en = fecha or timezone.localdate()
        self.levantada_por = supervisor
        self.levantada_motivo = (motivo or '').strip()
        self.save(update_fields=['levantada_en', 'levantada_por', 'levantada_motivo', 'actualizado_en'])
        return self

    def __str__(self):
        return f"{self.explorador.nombre} {self.explorador.apellido} - {self.fecha_inicio} supervisado por {self.supervisor.nombre} {self.supervisor.apellido}"



class PermisoSesion(models.Model):
    """Habilita o deshabilita UNA sesión del menú para UN empleado concreto.

    La tabla guarda solo las EXCEPCIONES: si no hay fila para (empleado, sesión),
    manda el valor por defecto del rol que define `core.sesiones`. Se hizo así, y
    no sembrando una fila por empleado y sesión, para que añadir una sesión nueva
    al catálogo no requiera una migración de datos ni deje a nadie fuera de una
    pantalla que antes veía: lo que no está escrito se comporta como siempre.

    ⚠ Este permiso NO puede dar acceso a algo que el rol no concede: es una reja
    ADICIONAL. Un explorador con `pdh` habilitado aquí sigue chocando contra
    `AdminRequiredMixin`, que exige rol Supervisor. Encender una sesión de
    Administración solo tiene efecto sobre alguien que ya es supervisor.

    ⚠ Tampoco aplica a `is_staff`/`is_superuser`: esos usuarios lo ven todo por
    diseño (ver `core.permisos_sesion.sesiones_habilitadas`). Si se quiere
    limitar a alguien, hay que quitarle el flag de staff, no marcarle casillas.
    """

    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE,
                                 related_name='permisos_sesion')
    #: Código del catálogo (`core.sesiones.CODIGOS`). Se guarda como texto y no
    #: como FK a una tabla de sesiones porque el catálogo vive en el código: es
    #: la lista de pantallas que existen, no un dato que el usuario administre.
    sesion = models.CharField(max_length=50)
    habilitado = models.BooleanField(default=True)
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Permiso de sesión'
        verbose_name_plural = 'Permisos de sesión'
        ordering = ['empleado', 'sesion']
        unique_together = [['empleado', 'sesion']]
        indexes = [
            models.Index(fields=['empleado'], name='permiso_sesion_emp_idx'),
        ]

    def __str__(self):
        estado = 'habilitada' if self.habilitado else 'deshabilitada'
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.sesion} ({estado})"
