import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from ..models import TipoSolicitudCambio

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core

# Create your views here.

class CambioTurnoInicioView(LoginRequiredMixin, TemplateView):
    template_name = 'solicitudes/cambio_turno_inicio.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from empleados.sancion_utils import mensaje_sancion, refrescar_y_sancion

        from ..services.solicitud_consulta_service import SolicitudConsultaService
        context['tipos_solicitud'] = SolicitudConsultaService.get_tipos_solicitud_activos()

        # Un explorador sancionado ve las tarjetas, pero desactivadas y con el motivo.
        # Antes esta pantalla no miraba la sanción en absoluto: el moroso entraba, elegía
        # tipo, llenaba el formulario entero y solo chocaba con el 403 al enviarlo.
        sancion = refrescar_y_sancion(getattr(self.request.user, 'empleado', None))
        if sancion:
            context['sancion_msg'] = mensaje_sancion(sancion)
        return context
    
class SolicitarCambioTurnoView(LoginRequiredMixin, View):
    """
    Sirve el formulario que corresponde al tipo de solicitud.

    El despacho va por `codigo_estrategia`, NO por `nombre`: es el mismo campo con el que
    `SolicitudFactory` elige la estrategia que valida y aplica la solicitud, así que pantalla y
    backend no pueden apuntar a cosas distintas. Con el nombre, además, renombrar una fila de la
    maestra (o añadir un tipo nuevo) caía en el `else` y entregaba el formulario de CT sencillo
    SIN ningún error visible; ahora un código desconocido da 404 en vez de un formulario que
    guarda otra cosa.
    """

    # codigo_estrategia -> método que renderiza su formulario
    _RENDERERS = {
        'CT': '_render_cambio_turno_normal',
        'CT PERMANENTE': '_render_ct_permanente',
        'DOBLADA': '_render_doblada',
        'D FDS': '_render_d_fds',
        'DOBLADA PERMANENTE': '_render_doblada_permanente',
        'CAMBIO DESCANSO': '_render_cambio_descanso',
    }

    def get(self, request, tipo_id):
        # Sanción ANTES de servir el formulario: el POST ya rechaza al sancionado
        # (`SolicitudOrchestrator.procesar`, paso 1), pero llegar hasta ahí obliga a llenar
        # todo el formulario para descubrirlo. Se comprueba aquí también, no en vez de allí:
        # la pantalla es comodidad, el POST es la puerta que de verdad cierra.
        from empleados.sancion_utils import mensaje_sancion, refrescar_y_sancion
        sancion = refrescar_y_sancion(getattr(request.user, 'empleado', None))
        if sancion:
            messages.warning(request, mensaje_sancion(sancion))
            return redirect('solicitudes:cambio_turno_inicio')

        tipo_solicitud = get_object_or_404(TipoSolicitudCambio, id=tipo_id)

        codigo = (tipo_solicitud.codigo_estrategia or '').strip().upper()
        metodo = self._RENDERERS.get(codigo)
        if not metodo:
            logger.error(
                "SolicitarCambioTurnoView - codigo_estrategia sin formulario asociado",
                extra={'tipo_id': tipo_id, 'nombre': tipo_solicitud.nombre,
                       'codigo_estrategia': tipo_solicitud.codigo_estrategia},
            )
            raise Http404(
                f"El tipo de solicitud '{tipo_solicitud.nombre}' no tiene un formulario asociado "
                f"(codigo_estrategia={tipo_solicitud.codigo_estrategia!r})."
            )
        return getattr(self, metodo)(request, tipo_solicitud)

    def _render_cambio_descanso(self, request, tipo_solicitud):
        """Renderizar formulario de Cambio de Día de Descanso (fin de semana)."""
        # Jornada base (AM/PM) del solicitante, para marcar en el calendario qué día
        # trabaja y cuál descansa según la alternancia.
        jornada_base = ''
        try:
            from turnos.models import AsignarJornadaExplorador
            emp = request.user.empleado
            asg = (AsignarJornadaExplorador.objects
                   .filter(explorador=emp, fecha_inicio__lte=timezone.localdate())
                   .select_related('jornada').order_by('-fecha_inicio').first())
            if asg:
                jornada_base = asg.jornada.nombre.upper()
        except Exception:
            logger.warning("Error obteniendo jornada base del empleado", exc_info=True)
        context = {
            'tipo_solicitud': tipo_solicitud,
            # Mañana: el día en curso ya se está trabajando y no hay jornada que intercambiar
            # sin reescribir un turno que la persona está cubriendo (misma regla que el backend).
            'fecha_minima': timezone.localdate() + timezone.timedelta(days=1),
            'fecha_seleccionada': None,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
            'jornada_base': jornada_base,
            # Para resaltar "tú eres ..." en el distintivo del fin de semana.
            'mi_jornada': jornada_base,
        }
        return render(request, 'solicitudes/solicitar_cambio_descanso.html', context)

    def _render_doblada_permanente(self, request, tipo_solicitud):
        """Renderizar formulario específico para DOBLADA PERMANENTE"""
        # El rango ya no se limita a un mes: se admite uno largo (enero-junio) con el mismo tope
        # que CT permanente. El número viaja al template para que el calendario no deje elegir un
        # rango que el validador va a rechazar; la regla sigue viviendo en Python, no en el JS.
        from ..services.validators.ct_permanente_validator import MAX_DIAS_RANGO_PERMANENTE
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.localdate(),
            'max_dias_rango': MAX_DIAS_RANGO_PERMANENTE,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
        }
        return render(request, 'solicitudes/solicitar_doblada_permanente.html', context)
    
    def _render_ct_permanente(self, request, tipo_solicitud):
        """Renderizar formulario específico para CT PERMANENTE"""
        # No establecer fecha inicial por defecto - el usuario debe seleccionarla
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.localdate() + timezone.timedelta(days=1),
            'fecha_inicio': None,  # Sin fecha inicial - usuario debe seleccionar
            'fecha_fin': None,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
            'comentarios': '',
        }
        return render(request, 'solicitudes/solicitar_ct_permanente.html', context)
    
    def _render_doblada(self, request, tipo_solicitud):
        """Renderizar formulario específico para DOBLADA"""
        # No establecer fecha inicial - el usuario debe seleccionarla
        context = {
            'tipo_solicitud': tipo_solicitud,
            # Mañana, no hoy: ceder el día EN CURSO no da margen a nadie (el compañero puede haber
            # trabajado ya su jornada, y la solicitud todavía tiene que aprobarse), así que el
            # backend lo rechaza. Si el calendario lo ofreciera, la persona llenaría el formulario
            # entero para chocar contra el error al enviarlo.
            'fecha_minima': timezone.localdate() + timezone.timedelta(days=1),
            # El pago tiene su propio mínimo porque debe ser posterior a la creación de la solicitud
            # (`validar_acuerdo_previo_obligatorio`). Hoy coincide con el de la cesión, pero son dos
            # reglas distintas: se mantienen separadas para que cambiar una no arrastre la otra.
            'fecha_minima_pago': timezone.localdate() + timezone.timedelta(days=1),
            'fecha_seleccionada': None,  # Sin fecha inicial - usuario debe seleccionar
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
        }
        return render(request, 'solicitudes/solicitar_doblada.html', context)
    
    def _render_d_fds(self, request, tipo_solicitud):
        """Renderizar formulario específico para D FDS (Doblada de Fin de Semana)"""
        context = {
            'tipo_solicitud': tipo_solicitud,
            # Mañana, no hoy: `D_FDSStrategy.validar_solicitud` rechaza el día en curso. El
            # calendario lo ofrecía igualmente, así que se llenaba el formulario entero para chocar
            # con el error al enviarlo.
            'fecha_minima': timezone.localdate() + timezone.timedelta(days=1),
            'fecha_seleccionada': None,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
            # Jornada predeterminada del solicitante (AM/PM) para resaltar "tú eres ..." en el distintivo.
            'mi_jornada': self._obtener_mi_jornada(request),
        }
        return render(request, 'solicitudes/solicitar_d_fds.html', context)

    @staticmethod
    def _obtener_mi_jornada(request):
        """Devuelve el nombre de la jornada predeterminada (AM/PM) del usuario actual, o ''."""
        from turnos.models import AsignarJornadaExplorador
        empleado = getattr(request.user, 'empleado', None)
        if not empleado:
            return ''
        asignacion = (
            AsignarJornadaExplorador.objects
            .filter(explorador=empleado)
            .select_related('jornada')
            .order_by('-fecha_inicio')
            .first()
        )
        return (asignacion.jornada.nombre if asignacion and asignacion.jornada else '') or ''

    def _render_cambio_turno_normal(self, request, tipo_solicitud):
        """Renderizar formulario para cambio de turno normal.

        La fecha mínima es MAÑANA: el día en curso ya se está trabajando, así que no hay
        jornada que intercambiar sin reescribir un turno que la persona ya está cubriendo
        (misma regla que valida el backend). Sin fecha preseleccionada: el usuario elige.
        """
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.localdate() + timezone.timedelta(days=1),
            'fecha_seleccionada': None,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
        }
        return render(request, 'solicitudes/solicitar_cambio_turno.html', context)


