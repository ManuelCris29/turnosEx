"""
Alta masiva de empleados desde un Excel.

POR QUE EXISTE
--------------
La aplicación crea empleados de uno en uno, que es lo correcto para el día a día:
un alta puntual la hace el supervisor desde su pantalla. Pero el arranque en
producción es otra cosa — son ~111 fichas de golpe, cada una con su cuenta de
usuario, su rol, su jornada base y su sala. A mano son horas y, sobre todo, son
horas con el riesgo de un dedazo en una cédula que luego nadie sabe de dónde salió.

QUE CREA POR CADA FILA
----------------------
    User                        cuenta de acceso (usuario, correo, contraseña)
    Empleado                    ficha (nombre, apellido, cédula)
    EmpleadoRole                el rol de la columna `Rol`
    AsignarJornadaExplorador    la jornada base de la columna `Jornada`
    CompetenciaEmpleado         la sala de la columna `Grupo Base`

CATALOGOS: QUE CREA Y QUE EXIGE
-------------------------------
Crea solos los `Role` y las `Sala` que falten: son catálogos de solo-nombre, así
que no hay nada que inventar.

Las `Jornada` NO las crea, y es deliberado: el modelo exige `hora_inicio` y
`hora_fin`, y esos horarios son una decisión de la operación que este comando no
puede adivinar. Si faltan, aborta y lo dice. Créalas antes desde el admin.

SEGURIDAD
---------
El Excel trae las contraseñas en texto plano. Se guardan cifradas (`set_password`),
pero el fichero de origen es material sensible: no lo dejes en Descargas ni lo
subas a ningún repositorio. Conviene que la gente las cambie al primer acceso.

USO
---
    python manage.py importar_empleados --archivo ruta/al/DatosExplo.xlsx --dry-run
    python manage.py importar_empleados --archivo ruta/al/DatosExplo.xlsx

Acepta `.xlsx` y `.csv`, y tambien `--archivo -` para leer un CSV por la entrada
estandar. Ese ultimo modo existe por una razon concreta: en produccion la base solo
es alcanzable DESDE DENTRO del contenedor, pero el fichero de origen vive en el PC
de quien hace la carga. Canalizar el CSV evita tener que exponer la base o subir a
un repositorio un fichero con datos personales:

    docker exec -i <contenedor> python /app/manage.py importar_empleados \
        --archivo - --dry-run < empleados.csv

SIEMPRE con `--dry-run` primero: valida el fichero entero y te dice exactamente qué
haría, sin escribir nada. La ejecución real va dentro de una transacción, así que
o entran todos o no entra ninguno; no existe el caso de "se cayó a la mitad y ahora
hay 47 empleados a medias".
"""
import csv
import sys
from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from empleados.models import CompetenciaEmpleado, Empleado, EmpleadoRole, Jornada, Role, Sala
from turnos.models import AsignarJornadaExplorador

# Columna del Excel -> significado. El orden no importa: se busca por encabezado.
COLUMNAS = {
    'usuario': ('usuario',),
    'password': ('contraseña', 'contrasena', 'password', 'clave'),
    'nombre': ('nombre', 'nombres'),
    'apellido': ('apellido', 'apellidos'),
    'cedula': ('documento', 'cedula', 'cédula'),
    'correo': ('correos', 'correo', 'email'),
    'sala': ('grupo base', 'grupobase', 'sala'),
    'jornada': ('jornada',),
    'rol': ('rol', 'role'),
}


def _normalizar(valor):
    return '' if valor is None else str(valor).strip()


class Command(BaseCommand):
    help = 'Da de alta empleados en lote desde un Excel (usuario, ficha, rol, jornada y sala).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--archivo', required=True,
            help='Ruta de un .xlsx o .csv, o "-" para leer un CSV por entrada estandar')
        parser.add_argument(
            '--hoja', default=None,
            help='Nombre de la hoja del Excel (por defecto, la primera)')
        parser.add_argument(
            '--desde', default=None,
            help='Fecha de inicio de la jornada base (YYYY-MM-DD). Por defecto, hoy.')
        parser.add_argument(
            '--supervisor', default=None,
            help='Usuario del empleado que quedara como supervisor de TODOS los importados. '
                 'Debe existir ya como Empleado.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Valida y reporta sin escribir nada. Uselo SIEMPRE la primera vez.')

    def handle(self, *args, **opciones):
        dry_run = opciones['dry_run']
        desde = self._fecha_inicio(opciones['desde'])
        filas = self._leer_datos(opciones['archivo'], opciones['hoja'])

        self.stdout.write(f'Filas con datos: {len(filas)}')

        # Se valida TODO antes de escribir NADA. Reportar el primer fallo y parar
        # obligaria a reejecutar tantas veces como errores tenga el fichero.
        problemas, nuevas = self._validar(filas)
        supervisor, problema_supervisor = self._resolver_supervisor(opciones['supervisor'])
        if problema_supervisor:
            problemas.append(problema_supervisor)

        if problemas:
            self.stdout.write(self.style.ERROR(f'\n{len(problemas)} problema(s):'))
            for p in problemas:
                self.stdout.write(f'  {p}')
            raise CommandError('Corrige el Excel y vuelve a ejecutar. No se escribio nada.')

        self._resumen(filas, nuevas, desde, supervisor)

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\n--dry-run: no se escribio nada. Repite sin esa opcion para aplicarlo.'))
            return

        creados = self._importar(filas, desde, supervisor)
        self.stdout.write(self.style.SUCCESS(f'\nListo: {creados} empleado(s) creados.'))

    # ---------------------------------------------------------------- lectura

    def _fecha_inicio(self, texto):
        if not texto:
            return date.today()
        try:
            return date.fromisoformat(texto)
        except ValueError as exc:
            raise CommandError(f'--desde invalida: {texto!r}. Formato YYYY-MM-DD.') from exc

    def _leer_datos(self, ruta, hoja):
        """Devuelve las filas del origen, sea `.xlsx`, `.csv` o la entrada estandar."""
        if ruta == '-':
            # La entrada estandar hereda la codificacion del sistema, que en Windows
            # es cp1252: sin esto, un encabezado como "contraseña" llega roto y el
            # mapeo de columnas falla sin motivo aparente. `utf-8-sig` ademas se come
            # el BOM que deja Excel al exportar a CSV.
            try:
                sys.stdin.reconfigure(encoding='utf-8-sig')
            except (AttributeError, ValueError):
                pass  # ya venia envuelto o no admite reconfiguracion; se usa tal cual
            return self._filas_desde(csv.reader(sys.stdin), origen='la entrada estandar')
        if str(ruta).lower().endswith('.csv'):
            try:
                with open(ruta, encoding='utf-8-sig', newline='') as fichero:
                    return self._filas_desde(csv.reader(fichero), origen=str(ruta))
            except FileNotFoundError as exc:
                raise CommandError(f'No encuentro el archivo: {ruta}') from exc
        return self._leer_excel(ruta, hoja)

    def _leer_excel(self, ruta, hoja):
        try:
            import openpyxl
        except ImportError as exc:
            raise CommandError('Falta openpyxl. Esta en requirements.txt.') from exc
        try:
            libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
        except FileNotFoundError as exc:
            raise CommandError(f'No encuentro el archivo: {ruta}') from exc

        pagina = libro[hoja] if hoja else libro.active
        filas = self._filas_desde(pagina.iter_rows(values_only=True), origen=str(ruta))
        libro.close()
        return filas

    def _filas_desde(self, iterador, origen):
        """Mapea un iterable de filas (Excel o CSV) a diccionarios por nombre de columna."""
        try:
            encabezados = [_normalizar(c).lower() for c in next(iter(iterador))]
        except StopIteration as exc:
            raise CommandError(f'{origen} no tiene datos.') from exc

        # Se mapea por nombre de encabezado y no por posicion: si alguien reordena
        # las columnas, el import seguiria funcionando en vez de meter cedulas en
        # el campo del correo sin avisar.
        indices = {}
        for campo, alias in COLUMNAS.items():
            for i, encabezado in enumerate(encabezados):
                if encabezado in alias:
                    indices[campo] = i
                    break

        faltan = [c for c in COLUMNAS if c not in indices]
        if faltan:
            raise CommandError(
                f'Faltan columnas en {origen}: {", ".join(faltan)}.\n'
                f'Encabezados encontrados: {encabezados}')

        filas = []
        for numero, cruda in enumerate(iterador, start=2):
            if not any(v is not None and _normalizar(v) for v in cruda):
                continue  # fila en blanco
            fila = {campo: _normalizar(cruda[i]) if i < len(cruda) else ''
                    for campo, i in indices.items()}
            fila['_fila'] = numero
            filas.append(fila)

        return filas

    # -------------------------------------------------------------- validacion

    def _validar(self, filas):
        problemas = []

        jornadas = {j.nombre: j for j in Jornada.objects.all()}
        if not jornadas:
            problemas.append(
                'No hay ninguna Jornada creada. Este comando no las crea porque exigen '
                'hora_inicio y hora_fin, que son decision de la operacion. Creala antes '
                'en /admin/empleados/jornada/.')

        usuarios_bd = set(User.objects.values_list('username', flat=True))
        cedulas_bd = set(Empleado.objects.values_list('cedula', flat=True))

        vistos_usuario, vistos_cedula = {}, {}
        nuevas_salas, nuevos_roles = set(), set()

        for fila in filas:
            n = fila['_fila']

            for campo in ('usuario', 'nombre', 'apellido', 'cedula', 'correo', 'jornada', 'rol'):
                if not fila[campo]:
                    problemas.append(f'fila {n}: falta "{campo}"')

            if len(fila['cedula']) > 10:
                problemas.append(
                    f'fila {n}: cedula "{fila["cedula"]}" tiene {len(fila["cedula"])} caracteres; '
                    f'el modelo admite 10')

            # Duplicados DENTRO del fichero
            for campo, vistos in (('usuario', vistos_usuario), ('cedula', vistos_cedula)):
                clave = fila[campo].lower()
                if clave and clave in vistos:
                    problemas.append(
                        f'fila {n}: {campo} "{fila[campo]}" repetido (ya estaba en la fila {vistos[clave]})')
                elif clave:
                    vistos[clave] = n

            # Choques con lo que YA existe en la base
            if fila['usuario'] in usuarios_bd:
                problemas.append(f'fila {n}: el usuario "{fila["usuario"]}" ya existe en la base')
            if fila['cedula'] in cedulas_bd:
                problemas.append(f'fila {n}: la cedula "{fila["cedula"]}" ya existe en la base')

            if jornadas and fila['jornada'] not in jornadas:
                problemas.append(
                    f'fila {n}: jornada "{fila["jornada"]}" no existe. Disponibles: {sorted(jornadas)}')

            if fila['sala']:
                nuevas_salas.add(fila['sala'])
            if fila['rol']:
                nuevos_roles.add(fila['rol'])

        salas_bd = set(Sala.objects.values_list('nombre', flat=True))
        roles_bd = set(Role.objects.values_list('nombre', flat=True))
        return problemas, {
            'salas': sorted(nuevas_salas - salas_bd),
            'roles': sorted(nuevos_roles - roles_bd),
        }

    def _resolver_supervisor(self, usuario):
        """Busca el Empleado que quedara como supervisor. Devuelve (empleado, problema)."""
        if not usuario:
            return None, None
        empleado = Empleado.objects.filter(user__username=usuario).first()
        if empleado is None:
            return None, (
                f'--supervisor: no existe ningun Empleado con usuario "{usuario}". '
                f'Creelo antes (o revise el nombre exacto de usuario).')
        return empleado, None

    def _resumen(self, filas, nuevas, desde, supervisor):
        self.stdout.write(self.style.SUCCESS('\nValidacion OK. Se crearia:'))
        self.stdout.write(f'  {len(filas)} empleado(s), cada uno con su cuenta, rol, jornada y sala')
        self.stdout.write(f'  jornada base con fecha_inicio = {desde}')
        if supervisor:
            self.stdout.write(
                f'  supervisor de todos: {supervisor.nombre} {supervisor.apellido} '
                f'({supervisor.user.username})')
        else:
            self.stdout.write('  supervisor: ninguno (quedan sin supervisor asignado)')
        if nuevas['roles']:
            self.stdout.write(f'  roles nuevos: {nuevas["roles"]}')
        if nuevas['salas']:
            self.stdout.write(f'  salas nuevas: {nuevas["salas"]}')

    # -------------------------------------------------------------- escritura

    @transaction.atomic
    def _importar(self, filas, desde, supervisor=None):
        jornadas = {j.nombre: j for j in Jornada.objects.all()}
        roles, salas = {}, {}
        creados = 0

        for fila in filas:
            if fila['rol'] not in roles:
                roles[fila['rol']], _ = Role.objects.get_or_create(nombre=fila['rol'])
            if fila['sala'] and fila['sala'] not in salas:
                salas[fila['sala']], _ = Sala.objects.get_or_create(nombre=fila['sala'])

            usuario = User.objects.create_user(
                username=fila['usuario'],
                email=fila['correo'],
                password=fila['password'] or None,
            )
            empleado = Empleado.objects.create(
                user=usuario,
                nombre=fila['nombre'],
                apellido=fila['apellido'],
                cedula=fila['cedula'],
                supervisor=supervisor,
            )
            EmpleadoRole.objects.create(empleado=empleado, role=roles[fila['rol']])
            AsignarJornadaExplorador.objects.create(
                explorador=empleado, jornada=jornadas[fila['jornada']], fecha_inicio=desde)
            if fila['sala']:
                CompetenciaEmpleado.objects.create(empleado=empleado, sala=salas[fila['sala']])

            creados += 1

        return creados
