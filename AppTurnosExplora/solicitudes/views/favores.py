"""
Mis favores: el registro de días de finde que te cubrieron y que cubriste.

`DeudaExplorador` guarda cada favor entre dos exploradores (quién cede su día y quién lo cubre),
pero no tenía NINGUNA pantalla: solo se veía por el admin de Django. Un explorador no podía
saber quién le cubrió un día ni a quién se lo devolvió.

Nota sobre los estados: en este proyecto la fecha de pago se pacta EN LA MISMA solicitud
("no existen dobladas abiertas"), así que la deuda nace ya con `fecha_pago_real` y en estado
'pagada'. Por eso esta pantalla no es una lista de "lo que debes" —que estaría siempre vacía—
sino el HISTORIAL de favores: quién te cubrió, cuándo, y cuándo quedó devuelto.

Qué formularios llegan aquí: los que generan `DeudaExplorador`, o sea DOBLADA, D FDS y
DOBLADA PERMANENTE. CT, CT PERMANENTE y CAMBIO DESCANSO son permutas simétricas (ambos ceden y
reciben en el mismo acto), no dejan a nadie a deber y por eso no aparecen. El estudio completo
está en `docs/05-referencia/solicitudes/COBERTURA_MIS_FAVORES.md`.
"""
from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render
from django.views import View

from solicitudes.models import DeudaExplorador

# Tope por tarjeta. El historial solo crece, y renderizarlo entero es gasto puro en cuanto
# lleve un par de temporadas. Con `?todo=1` se ve completo.
LIMITE_POR_TARJETA = 100


class MisFavoresView(LoginRequiredMixin, View):
    """Favores del explorador conectado: los que recibió y los que hizo."""

    template_name = 'solicitudes/mis_favores.html'

    def get(self, request):
        empleado = getattr(request.user, 'empleado', None)
        if not empleado:
            return render(request, self.template_name,
                          {'recibidos': [], 'hechos': [], 'sin_empleado': True})

        # Las canceladas no se listan: corresponden a acuerdos deshechos.
        base = (DeudaExplorador.objects
                .filter(Q(deudor=empleado) | Q(acreedor=empleado))
                .exclude(estado='cancelada')
                .select_related('deudor', 'acreedor', 'solicitud_origen',
                                'solicitud_origen__tipo_cambio',
                                'solicitud_origen__doblada'))

        recibidos, hechos = [], []
        for d in base:
            fila = {
                'deuda': d,
                'fecha_cubierta': self._fecha_cubierta(d),
                'tipo': (d.solicitud_origen.tipo_cambio.nombre
                         if d.solicitud_origen and d.solicitud_origen.tipo_cambio else '—'),
                'jornada': self._jornada(d),
                'devuelto': d.estado == 'pagada',
            }
            if d.deudor_id == empleado.id:
                fila['companero'] = d.acreedor      # él te cubrió a ti
                recibidos.append(fila)
            else:
                fila['companero'] = d.deudor        # tú lo cubriste a él
                hechos.append(fila)

        # Se ordena por la fecha que la tabla enseña —el día cubierto—, no por la de pago:
        # ordenar por una columna que no se ve hace que el listado parezca arbitrario.
        # `date.min` mantiene abajo las filas sin fecha en vez de reventar comparando con None.
        def clave(fila):
            return fila['fecha_cubierta'] or date.min

        recibidos.sort(key=clave, reverse=True)
        hechos.sort(key=clave, reverse=True)

        # Los contadores cuentan sobre el total, no sobre la página: si dicen "3 sin devolver"
        # tienen que ser los 3 que existen, aunque el recorte deje alguno fuera de la vista.
        pendientes_de_devolver = sum(1 for f in recibidos if not f['devuelto'])
        pendientes_de_cobrar = sum(1 for f in hechos if not f['devuelto'])

        todo = request.GET.get('todo') == '1'
        recortados = not todo and (len(recibidos) > LIMITE_POR_TARJETA
                                   or len(hechos) > LIMITE_POR_TARJETA)
        if not todo:
            recibidos = recibidos[:LIMITE_POR_TARJETA]
            hechos = hechos[:LIMITE_POR_TARJETA]

        return render(request, self.template_name, {
            'recibidos': recibidos,
            'hechos': hechos,
            'pendientes_de_devolver': pendientes_de_devolver,
            'pendientes_de_cobrar': pendientes_de_cobrar,
            'recortados': recortados,
            'limite': LIMITE_POR_TARJETA,
        })

    @staticmethod
    def _fecha_cubierta(deuda):
        """
        El día que la otra persona trabajó por ti (o tú por ella).

        Normalmente es la fecha de CESIÓN de la solicitud (`fecha_pago_pactada`/`fecha_pago_real`
        son el día de la DEVOLUCIÓN). La excepción es la deuda RESIDUAL que genera
        `DobladaDeudaService` cuando el pago cae en sábado cubriendo AMBAS jornadas: esa segunda
        deuda invierte deudor y acreedor pero reutiliza la MISMA `solicitud_origen`, así que su
        favor no ocurrió el día de la cesión sino el sábado del pago. Se reconoce porque el
        deudor NO es el solicitante de la solicitud.
        """
        solicitud = deuda.solicitud_origen
        if not solicitud:
            return None
        es_residual = deuda.deudor_id != solicitud.explorador_solicitante_id
        if es_residual:
            detalle = getattr(solicitud, 'doblada', None)
            if detalle and detalle.fecha_pago:
                return detalle.fecha_pago
        return solicitud.fecha_cambio_turno

    @staticmethod
    def _jornada(deuda):
        """
        Cuánto se cubrió: un día de finde entero (D FDS) o media jornada AM/PM (doblada).
        El dato estaba en el modelo y no se enseñaba, así que ambos casos se veían idénticos.
        """
        if not deuda.media_jornada:
            return 'Día completo'
        return deuda.jornada_cedida or 'Media jornada'
