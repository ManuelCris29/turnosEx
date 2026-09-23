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
        from axes.helpers import get_client_ip_address
        from django.conf import settings

        proxies = getattr(settings, 'AXES_IPWARE_PROXY_COUNT', None)
        self.stdout.write(f'AXES_IPWARE_PROXY_COUNT = {proxies}')
        self.stdout.write(f'AXES_LOCKOUT_PARAMETERS = {getattr(settings, "AXES_LOCKOUT_PARAMETERS", None)}')
        self.stdout.write('')

        self.stdout.write(
            f'AXES_IPWARE_META_PRECEDENCE_ORDER = '
            f'{getattr(settings, "AXES_IPWARE_META_PRECEDENCE_ORDER", ("REMOTE_ADDR",))}')
        self.stdout.write('')

        # Se prueban las DOS formas de cabecera que existen en la práctica, y no una
        # sola, porque probar únicamente la del ALB fue lo que dejó pasar el fallo del
        # despliegue en Dokploy (2026-09-18): la configuración parecía correcta contra
        # una cabecera que ese servidor nunca manda.
        #
        # ipware valida en modo estricto con una igualdad exacta
        # (`len(ips) - 1 == AXES_IPWARE_PROXY_COUNT`), así que el número que hay que
        # poner NO es "cuántos proxies hay" sino "cuántas direcciones trae la cabecera
        # por delante de la del cliente". Un proxy que reescribe la cabecera —Traefik,
        # y también Nginx con `$remote_addr`— deja UNA sola: ahí el número es 0.
        escenarios = [
            ('Traefik / Nginx que REESCRIBE la cabecera', CLIENTE, 0),
            ('ALB o proxy que AÑADE a la cabecera', f'{CLIENTE}, {BALANCEADOR}', 1),
        ]

        aciertos = []
        for titulo, cabecera, cuenta_correcta in escenarios:
            peticion = RequestFactory().post('/login/')
            peticion.META['REMOTE_ADDR'] = BALANCEADOR
            peticion.META['HTTP_X_FORWARDED_FOR'] = cabecera

            try:
                resuelta = get_client_ip_address(peticion)
            except Exception as exc:  # noqa: BLE001 - queremos ver el fallo, no ocultarlo
                resuelta = f'ERROR: {exc!r}'

            ok = resuelta == CLIENTE
            if ok:
                aciertos.append(titulo)

            marca = 'ok' if ok else '!!'
            self.stdout.write(f'[{marca}] {titulo}')
            self.stdout.write(f'       X-Forwarded-For: {cabecera}')
            self.stdout.write(f'       axes resuelve  : {resuelta}')
            if not ok:
                self.stdout.write(f'       (para este caso AXES_IPWARE_PROXY_COUNT seria {cuenta_correcta})')
            self.stdout.write('')

        if aciertos:
            self.stdout.write(self.style.SUCCESS(
                f'CORRECTO para: {", ".join(aciertos)}. Con esa forma de cabecera axes ve la IP '
                f'del cliente y el bloqueo por IP alcanza solo a quien falla.'))
        elif not proxies and 'HTTP_X_FORWARDED_FOR' not in tuple(
                getattr(settings, 'AXES_IPWARE_META_PRECEDENCE_ORDER', ('REMOTE_ADDR',))):
            self.stdout.write(self.style.WARNING(
                'Sin intermediarios y sin leer X-Forwarded-For: axes usa REMOTE_ADDR. Es lo '
                'correcto en local, donde el trafico llega directo, y ademas impide que un '
                'cliente se invente la cabecera. DETRAS DE UN PROXY hay que volver a ejecutar '
                'esto: alli REMOTE_ADDR es el proxy, igual para todo el mundo.'))
        else:
            self.stdout.write(self.style.ERROR(
                'PELIGRO: con esta configuracion axes NO resuelve la IP del cliente en NINGUNA '
                'de las dos formas de cabecera. O devuelve nulo, o devuelve la del intermediario '
                '—y en los dos casos TODA la plantilla comparte grupo: cinco fallos de cualquiera '
                'bloquean a todos. Ajusta AXES_IPWARE_PROXY_COUNT al numero que indica el caso '
                'que corresponda a tu servidor.'))

        self.stdout.write('')
        self.stdout.write('Esto valida la ARITMETICA contra cabeceras SIMULADAS, y eso NO BASTA:')
        self.stdout.write('no sabe cual manda de verdad tu servidor. Con trafico real, y antes de')
        self.stdout.write('dar la URL a nadie:')
        self.stdout.write('  1. Entra desde DOS REDES DISTINTAS (una con datos moviles).')
        self.stdout.write('  2. Mira /admin/axes/accesslog/: tienen que salir DOS IPs PUBLICAS')
        self.stdout.write('     distintas. Si sale la misma, o una 10.x/172.x, o vacia, esta roto.')
        self.stdout.write('  3. Recien ahi: falla 5 veces desde una red y comprueba que la otra entra.')
        self.stdout.write('  4. Limpia el bloqueo:  python manage.py axes_reset')
