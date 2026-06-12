"""
Notificaciones de Permisos Especiales.

Replica el flujo de las solicitudes de cambio de turno:
- Notificación in-app al supervisor del explorador.
- Email al supervisor con enlaces para Aprobar / Rechazar (token firmado).
- Al resolverse, se notifica al explorador.

El destinatario siempre es `permiso.empleado.supervisor` (cada empleado tiene su
supervisor asignado), por lo que funciona aunque existan varios supervisores.
"""
import hashlib
import hmac
import logging

from django.conf import settings

from solicitudes.models import Notificacion
from solicitudes.services.notificacion_service import NotificacionService

logger = logging.getLogger(__name__)

_SECRET = b'secret_key_change_this'  # mismo esquema que las solicitudes de cambio


class PermisoNotificacionService:

    # ------------------------------------------------------------------ tokens
    @staticmethod
    def generar_token(permiso_id, supervisor_id):
        data = f"permiso_{permiso_id}_{supervisor_id}"
        return hmac.new(_SECRET, data.encode(), hashlib.sha256).hexdigest()

    @staticmethod
    def verificar_token(permiso, token):
        supervisor = permiso.empleado.supervisor
        if not supervisor:
            return False
        esperado = PermisoNotificacionService.generar_token(permiso.id, supervisor.id)
        return hmac.compare_digest(token, esperado)

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _fechas(permiso):
        if permiso.es_permanente:
            return (f"{permiso.fecha_inicio:%d/%m/%Y} – {permiso.fecha_fin:%d/%m/%Y} "
                    f"({permiso.dias_semana_legible()})")
        return f"{permiso.fecha_inicio:%d/%m/%Y}"

    @staticmethod
    def _detalle_texto(permiso):
        emp = permiso.empleado
        cubre = f"{permiso.cubre.nombre} {permiso.cubre.apellido}" if permiso.cubre else '—'
        return (
            f"Explorador: {emp.nombre} {emp.apellido}\n"
            f"Fecha(s): {PermisoNotificacionService._fechas(permiso)}\n"
            f"Tiempo: {permiso.horas_totales()} h\n"
            f"Tipo: {permiso.get_tipo_display()} ({'Permanente' if permiso.es_permanente else 'Puntual'})\n"
            f"Especificación: {permiso.especificacion or '—'}\n"
            f"Quién cubre: {cubre}\n"
            f"Motivo: {permiso.motivo}"
        )

    # ---------------------------------------------------- notificar solicitud
    @staticmethod
    def notificar_solicitud(permiso):
        """Notifica al supervisor (in-app + email con enlaces de aprobación)."""
        supervisor = permiso.empleado.supervisor
        if not supervisor:
            logger.warning("Permiso %s sin supervisor asignado; no se notifica.", permiso.id)
            return False

        emp = permiso.empleado
        titulo = f"Nueva solicitud de permiso — {emp.nombre} {emp.apellido}"
        detalle = PermisoNotificacionService._detalle_texto(permiso)

        # 1) Notificación in-app
        try:
            Notificacion.objects.create(
                destinatario=supervisor,
                tipo='solicitud_permiso',
                titulo=titulo,
                mensaje=detalle + "\n\nApruébalo o recházalo en «Permisos Especiales».",
                solicitud=None,
            )
        except Exception:
            logger.exception("Error creando notificación in-app de permiso %s", permiso.id)

        # 2) Email con enlaces de aprobar/rechazar
        token = PermisoNotificacionService.generar_token(permiso.id, supervisor.id)
        base = settings.SITE_URL.rstrip('/')
        url_aprobar = f"{base}/permisos/permisos-especiales/{permiso.id}/aprobar-email/{token}/"
        url_rechazar = f"{base}/permisos/permisos-especiales/{permiso.id}/rechazar-email/{token}/"

        texto = (
            f"{detalle}\n\n"
            f"Aprobar:  {url_aprobar}\n"
            f"Rechazar: {url_rechazar}\n"
        )
        html = PermisoNotificacionService._email_html(permiso, url_aprobar, url_rechazar)

        try:
            return NotificacionService._enviar_email_desde_usuario(
                subject=titulo,
                message=texto,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[supervisor.email],
                html_message=html,
            )
        except Exception:
            logger.exception("Error enviando email de permiso %s al supervisor", permiso.id)
            return False

    # ---------------------------------------------------- notificar resolución
    @staticmethod
    def notificar_resolucion(permiso):
        """Avisa al explorador que su permiso fue aprobado o rechazado."""
        emp = permiso.empleado
        estado = permiso.get_estado_display()
        titulo = f"Tu permiso fue {estado.lower()}"
        detalle = (
            f"Tu solicitud de permiso ({PermisoNotificacionService._fechas(permiso)}, "
            f"{permiso.horas_totales()} h) fue {estado.lower()}"
            + (f" por {permiso.supervisor.nombre} {permiso.supervisor.apellido}." if permiso.supervisor else ".")
        )
        try:
            Notificacion.objects.create(
                destinatario=emp,
                tipo='aprobacion' if permiso.estado == 'APROBADO' else 'rechazo',
                titulo=titulo,
                mensaje=detalle,
                solicitud=None,
            )
        except Exception:
            logger.exception("Error creando notificación de resolución de permiso %s", permiso.id)

        if emp.email:
            try:
                NotificacionService._enviar_email_desde_usuario(
                    subject=titulo, message=detalle,
                    from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[emp.email],
                )
            except Exception:
                logger.exception("Error enviando email de resolución de permiso %s", permiso.id)

    # --------------------------------------------------------------- email html
    @staticmethod
    def _email_html(permiso, url_aprobar, url_rechazar):
        emp = permiso.empleado
        cubre = f"{permiso.cubre.nombre} {permiso.cubre.apellido}" if permiso.cubre else '—'
        return f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
          <div style="background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;padding:18px 22px">
            <h2 style="margin:0;font-size:18px">Nueva solicitud de permiso</h2>
            <p style="margin:4px 0 0;opacity:.9">{emp.nombre} {emp.apellido}</p>
          </div>
          <div style="padding:20px 22px;color:#1f2937">
            <table style="width:100%;font-size:14px;border-collapse:collapse">
              <tr><td style="padding:4px 0;color:#6b7280">Fecha(s)</td><td><b>{PermisoNotificacionService._fechas(permiso)}</b></td></tr>
              <tr><td style="padding:4px 0;color:#6b7280">Tiempo</td><td><b>{permiso.horas_totales()} h</b></td></tr>
              <tr><td style="padding:4px 0;color:#6b7280">Tipo</td><td>{permiso.get_tipo_display()} ({'Permanente' if permiso.es_permanente else 'Puntual'})</td></tr>
              <tr><td style="padding:4px 0;color:#6b7280">Especificación</td><td>{permiso.especificacion or '—'}</td></tr>
              <tr><td style="padding:4px 0;color:#6b7280">Quién cubre</td><td>{cubre}</td></tr>
              <tr><td style="padding:4px 0;color:#6b7280">Motivo</td><td>{permiso.motivo}</td></tr>
            </table>
            <div style="margin-top:22px;text-align:center">
              <a href="{url_aprobar}" style="display:inline-block;background:#16a34a;color:#fff;text-decoration:none;padding:11px 22px;border-radius:8px;font-weight:600;margin:4px">✓ Aprobar</a>
              <a href="{url_rechazar}" style="display:inline-block;background:#ef4444;color:#fff;text-decoration:none;padding:11px 22px;border-radius:8px;font-weight:600;margin:4px">✗ Rechazar</a>
            </div>
            <p style="color:#9ca3af;font-size:12px;margin-top:18px">También puedes aprobarlo desde la app, en «Permisos Especiales».</p>
          </div>
        </div>
        """
