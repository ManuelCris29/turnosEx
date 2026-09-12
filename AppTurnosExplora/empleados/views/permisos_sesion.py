"""
Pantalla de permisos de sesión: qué módulos del menú ve cada empleado.

Solo la abre un `is_staff` (`StaffRequiredMixin`). Un supervisor no puede tocar
esta matriz, ni la suya ni la de nadie: si pudiera, se devolvería en dos clics
cualquier sesión que el administrador le hubiera quitado.

La regla que se edita aquí está descrita en `core.permisos_sesion`; esta vista
solo persiste las excepciones.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from core.mixins import StaffRequiredMixin, es_supervisor
from core.permisos_sesion import defectos_para, excepciones_de
from core.sesiones import CODIGOS, grupos

from ..models import Empleado, PermisoSesion


class PermisosSesionUpdateView(LoginRequiredMixin, StaffRequiredMixin, View):
    """Matriz de casillas: una fila por sesión del catálogo, para un empleado."""

    template_name = 'empleados/permisos_sesion.html'

    def get(self, request, empleado_id):
        empleado = self._empleado(empleado_id)
        return render(request, self.template_name, self._contexto(empleado))

    @transaction.atomic
    def post(self, request, empleado_id):
        empleado = self._empleado(empleado_id)

        # Se descarta lo que no esté en el catálogo: el POST llega del navegador
        # y sin esto cualquiera podría sembrar filas con códigos inventados que
        # nunca se leerían y solo ensuciarían la tabla.
        marcadas = CODIGOS & set(request.POST.getlist('sesiones'))

        for codigo in CODIGOS:
            PermisoSesion.objects.update_or_create(
                empleado=empleado,
                sesion=codigo,
                defaults={'habilitado': codigo in marcadas},
            )

        # La invalidación del caché de `sesiones_habilitadas` la dispara la señal
        # post_save/post_delete de PermisoSesion (empleados/signals.py), no esta
        # vista: PermisoSesion también se edita desde /admin/, y un solo punto de
        # invalidación en la señal cubre ambos caminos.
        messages.success(
            request,
            f'Permisos de sesión actualizados para {empleado.nombre} {empleado.apellido}.',
        )
        return redirect(reverse('permisos_sesion_edit', args=[empleado.id]))

    def _empleado(self, empleado_id):
        return get_object_or_404(
            Empleado.objects.select_related('user').prefetch_related('permisos_sesion'),
            pk=empleado_id,
        )

    def _contexto(self, empleado):
        """Prepara la matriz ya resuelta, para que la plantilla no calcule nada.

        Cada sesión llega con `activa` (lo que se ve marcado ahora) y `heredado`
        (si ese valor viene del rol o de una decisión guardada). Distinguirlos
        importa: sin la marca, el administrador no puede saber si una casilla
        está apagada porque él la apagó o porque el rol nunca la trajo.
        """
        usuario = getattr(empleado, 'user', None)
        es_admin_total = bool(getattr(usuario, 'is_staff', False)
                              or getattr(usuario, 'is_superuser', False))

        defectos = defectos_para(es_supervisor(usuario))
        guardadas = excepciones_de(empleado)

        matriz = []
        for nombre_grupo, sesiones in grupos():
            filas = [{
                'codigo': s.codigo,
                'etiqueta': s.etiqueta,
                'activa': guardadas.get(s.codigo, defectos[s.codigo]),
                'heredado': s.codigo not in guardadas,
                'por_defecto': defectos[s.codigo],
            } for s in sesiones]
            matriz.append({'grupo': nombre_grupo, 'filas': filas})

        return {
            'empleado': empleado,
            'matriz': matriz,
            'es_admin_total': es_admin_total,
            'es_supervisor_empleado': es_supervisor(usuario),
        }
