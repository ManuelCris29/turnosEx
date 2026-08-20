"""
Comprobación de despliegue: ¿qué IP ve django-axes detrás del balanceador?

Complementa al check `core.E003` (core/checks.py). El check mira la CONFIGURACIÓN;
este comando ejecuta la resolución REAL de axes sobre cabeceras de ejemplo, que es
lo único que demuestra que el número de proxies es el correcto.

Por qué importa (patrón #25, fallar cerrado sin romper a nadie): si axes ve la IP
del ALB en lugar de la del cliente, la ve IGUAL para todo el mundo. Cinco intentos
fallidos de un solo empleado dejarían bloqueada a la plantilla entera durante una
hora: una denegación de servicio provocada por la propia protección antifuerza bruta.

    python manage.py verificar_ip_cliente
"""
from django.core.management.base import BaseCommand
from django.test import RequestFactory

CLIENTE = '203.0.113.45'      # IP pública del explorador (RFC 5737, de ejemplo)
BALANCEADOR = '10.0.1.20'     # IP privada del ALB / Nginx


class Command(BaseCommand):
    help = 'Comprueba qué IP de cliente resuelve django-axes con la configuración actual.'

    def handle(self, *args, **options):
        from django.conf import settings

        from axes.helpers import get_client_ip_address

        proxies = getattr(settings, 'AXES_IPWARE_PROXY_COUNT', None)
        self.stdout.write(f'AXES_IPWARE_PROXY_COUNT = {proxies}')
        self.stdout.write(f'AXES_LOCKOUT_PARAMETERS = {getattr(settings, "AXES_LOCKOUT_PARAMETERS", None)}')
        self.stdout.write('')

        peticion = RequestFactory().post('/login/')
        peticion.META['REMOTE_ADDR'] = BALANCEADOR
        peticion.META['HTTP_X_FORWARDED_FOR'] = f'{CLIENTE}, {BALANCEADOR}'

        try:
            resuelta = get_client_ip_address(peticion)
        except Exception as exc:  # noqa: BLE001 - queremos ver cualquier fallo, no ocultarlo
            self.stderr.write(self.style.ERROR(f'axes no pudo resolver la IP: {exc!r}'))
            return

        self.stdout.write(f'Cabecera simulada : X-Forwarded-For: {CLIENTE}, {BALANCEADOR}')
        self.stdout.write(f'REMOTE_ADDR       : {BALANCEADOR}')
        self.stdout.write(f'axes resuelve     : {resuelta}')
        self.stdout.write('')

        # El veredicto depende del entorno: con 0 proxies configurados, resolver el
        # REMOTE_ADDR es lo CORRECTO (la app recibe tráfico directo, como en local).
        # La cabecera simulada es precisamente la mentira contra la que protege ese 0.
        if resuelta == CLIENTE:
            self.stdout.write(self.style.SUCCESS(
                'CORRECTO: axes ve la IP del cliente. El bloqueo por IP afecta solo a quien falla.'))
        elif not proxies:
            self.stdout.write(self.style.WARNING(
                'Configurado SIN intermediarios (0): axes ignora X-Forwarded-For y usa REMOTE_ADDR. '
                'Es lo correcto en local y en cualquier despliegue con tráfico directo —y además '
                'impide que un cliente se invente la cabecera para falsear su IP—. '
                'PERO detrás del ALB de Fargate o de Nginx en EC2 hay que subirlo a 1, o axes verá '
                'la IP del intermediario para TODO el mundo. Vuelve a ejecutar esto allí.'))
        else:
            self.stdout.write(self.style.ERROR(
                f'PELIGRO: con {proxies} proxy(s) configurados axes ve {resuelta}, que no es el '
                f'cliente. El bloqueo por IP alcanzaría a TODA la plantilla. Ajusta '
                f'AXES_IPWARE_PROXY_COUNT al número real (ALB solo = 1; ALB + CloudFront = 2).'))

        self.stdout.write('')
        self.stdout.write('Esto valida la ARITMÉTICA de la configuración. Para cerrarlo del todo en')
        self.stdout.write('staging, con tráfico real:')
        self.stdout.write('  1. Falla el login 5 veces desde un equipo.')
        self.stdout.write('  2. Comprueba que OTRO equipo, en otra red, sí puede entrar.')
        self.stdout.write('  3. Limpia el bloqueo:  python manage.py axes_reset')
