"""Vistas de autenticación: entrar, salir, cambiar contraseña y recuperarla.

Todas las de contraseña son subclases finas de las de `django.contrib.auth`: la
parte delicada —generar y validar el token firmado, comprobar la contraseña
actual, aplicar los AUTH_PASSWORD_VALIDATORS, guardar con el hash correcto— viene
resuelta por Django y aquí no se reimplementa nada de eso. Lo que se añade es lo
que Django no puede saber: el diseño de la app, el límite de peticiones (axes no
cubre estas pantallas) y el aviso al titular de la cuenta.
"""
import logging

from django.contrib.auth import logout
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeDoneView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.shortcuts import redirect
from django.urls import reverse_lazy

from core import rate_limit
from core.services.aviso_seguridad_service import (
    ORIGEN_CAMBIO,
    ORIGEN_RESET,
    notificar_cambio_password,
)

logger = logging.getLogger('core.seguridad')


def _ip_cliente(request):
    """IP real del visitante, no la del balanceador.

    Se usa `django-ipware` (ya es dependencia: `django-axes[ipware]`) y el mismo
    ajuste de confianza en proxies que axes. Leer `REMOTE_ADDR` a pelo detrás del
    ALB devolvería SIEMPRE la IP del balanceador, con lo que el límite por IP
    contaría a todos los usuarios como si fueran uno solo y bloquearía la
    aplicación entera al quinto intento.
    """
    try:
        from ipware import get_client_ip

        ip, _ = get_client_ip(request)
        return ip
    except Exception:
        logger.warning('No se pudo determinar la IP del cliente', exc_info=True)
        return None


# Create your views here.
class LoginFormView(LoginView):
    template_name = 'login.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title']= 'Iniciar sesión'
        return context

class LogoutUserView(LogoutView):
    http_method_names = ['post', 'options', 'get']

    next_page = 'login'

    def get(self, request, *args, **kwargs):
        logout(request)
        return redirect(self.next_page)


# ---------------------------------------------------------------------------
# Cambiar mi contraseña (con sesión iniciada)
# ---------------------------------------------------------------------------
class PasswordChangeSWALPView(PasswordChangeView):
    """Autoservicio desde el menú de sesión.

    Usa `PasswordChangeForm`, que **exige la contraseña actual**. Es la
    diferencia deliberada con `empleados.views.empleado.ChangePasswordView`, la
    pantalla del administrador, que usa `SetPasswordForm` y no la pide: allí
    quien actúa es un tercero autorizado que por definición no la conoce; aquí
    es el propio titular, y pedirla es lo que impide que una sesión abierta y
    sin vigilar se convierta en una cuenta perdida.

    Django reasigna la sesión actual tras el cambio (`update_session_auth_hash`),
    así que quien cambia la contraseña NO se queda fuera. Las **demás** sesiones
    de esa cuenta sí caen, porque su `session_auth_hash` deja de casar: eso es lo
    que hace que cambiar la contraseña realmente expulse a un intruso.
    """

    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('password_change_done')

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        # Un acierto borra el contador: unos fallos ya resueltos no deben
        # sumarse a los de dentro de dos meses.
        rate_limit.limpiar('pwd_change', str(self.request.user.pk))
        logger.info('PASSWORD_CAMBIADA user_id=%s', self.request.user.pk)
        notificar_cambio_password(self.request.user, ORIGEN_CAMBIO, _ip_cliente(self.request))
        return respuesta

    def form_invalid(self, form):
        # Se cuentan los FALLOS, no las visitas: axes no vigila esta pantalla, y
        # con una sesión robada se podría probar la contraseña actual sin freno.
        usuario = str(self.request.user.pk)
        if not rate_limit.consumir('pwd_change', usuario, rate_limit.LIMITE_CAMBIO_POR_USUARIO):
            logger.warning('PASSWORD_CAMBIO_BLOQUEADO user_id=%s', usuario)
            form.add_error(
                None,
                'Demasiados intentos fallidos. Espera una hora antes de volver a intentarlo.',
            )
        return super().form_invalid(form)


class PasswordChangeDoneSWALPView(PasswordChangeDoneView):
    template_name = 'registration/password_change_done.html'


# ---------------------------------------------------------------------------
# Recuperar contraseña olvidada (sin sesión, pantallas públicas)
# ---------------------------------------------------------------------------
class PasswordResetSWALPView(PasswordResetView):
    """Envía el enlace de recuperación.

    DOS DECISIONES QUE NO SON OBVIAS:

    1. **El correo NO pasa por `EmailOutbox`.** El resto de la aplicación encola
       sus correos y un cron los reintenta cada 5 minutos; aquí se usa el
       `send_mail` de Django directamente. A propósito: con `EMAIL_SEND_ASYNC` y
       ese cron, el enlace podría tardar minutos en salir, y la persona está
       esperando delante de la pantalla. Se acepta el precio —si SMTP falla justo
       ahí, el correo se pierde sin reintento— porque **un reset lo puede
       reintentar el propio usuario**, a diferencia del correo de una aprobación,
       que ocurre una sola vez. Si alguien "arregla" esto metiéndolo en el
       outbox, romperá el flujo sin que ningún test de correo se queje.

    2. **Superado el límite se responde exactamente igual que en el caso
       normal.** Ni error, ni aviso. Django ya responde lo mismo exista o no la
       cuenta, para no revelar quién tiene usuario; delatar aquí el límite
       desharía esa discreción por otra vía.
    """

    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    success_url = reverse_lazy('password_reset_done')

    def form_valid(self, form):
        email = form.cleaned_data.get('email', '')
        ip = _ip_cliente(self.request)

        # Doble llave: por IP frena el abuso masivo desde un origen; por email
        # impide bombardear a UNA persona rotando de IP. Hacen falta las dos.
        permitido_ip = rate_limit.consumir('pwd_reset_ip', ip or '', rate_limit.LIMITE_RESET_POR_IP)
        permitido_email = rate_limit.consumir(
            'pwd_reset_email', email, rate_limit.LIMITE_RESET_POR_EMAIL
        )

        if not (permitido_ip and permitido_email):
            logger.warning('PASSWORD_RESET_BLOQUEADO por=%s', 'ip' if not permitido_ip else 'email')
            # Redirección idéntica a la del camino bueno, sin enviar nada.
            return redirect(self.get_success_url())

        logger.info('PASSWORD_RESET_SOLICITADO')
        return super().form_valid(form)


class PasswordResetDoneSWALPView(PasswordResetDoneView):
    template_name = 'registration/password_reset_done.html'


class PasswordResetConfirmSWALPView(PasswordResetConfirmView):
    """Fija la contraseña nueva tras validar el token del correo."""

    template_name = 'registration/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        usuario = form.user
        logger.info('PASSWORD_RESET_CONSUMIDO user_id=%s', usuario.pk)

        # Levantar el bloqueo de axes. Si alguien falló 5 veces al entrar quedó
        # bloqueado una hora; recuperar la contraseña por correo y SEGUIR
        # bloqueado, sin explicación, es el final más frustrante posible de este
        # flujo. No abre ningún hueco: para llegar hasta aquí hay que controlar
        # el buzón de la cuenta, que es más de lo que exige el propio login.
        self._resetear_axes(usuario)

        notificar_cambio_password(usuario, ORIGEN_RESET, _ip_cliente(self.request))
        return respuesta

    @staticmethod
    def _resetear_axes(usuario):
        try:
            from axes.utils import reset as axes_reset

            axes_reset(username=usuario.get_username())
        except Exception:
            # Que no se pueda limpiar el contador no puede impedir que la
            # contraseña —ya guardada— se dé por buena.
            logger.warning('No se pudo resetear axes tras el reset', exc_info=True)


class PasswordResetCompleteSWALPView(PasswordResetCompleteView):
    template_name = 'registration/password_reset_complete.html'
