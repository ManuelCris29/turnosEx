"""
Servicio de Pago de Horas (PDH) apuntando a deudas concretas.

Un PDH ya no es un pago "ciego" de horas: el supervisor selecciona QUÉ deudas paga.
Las deudas de un explorador provienen de dos fuentes:
  - Dobladas: DeudaCorporativa (estado='activa'), 0.5 h por día.
  - Permisos: PermisoEspecial (estado='APROBADO', pagado=False), sus horas solicitadas.

Las horas del PDH = suma de las deudas seleccionadas. Al pagar, las deudas quedan marcadas
(pagada / pagado=True) y vinculadas al PDH. Al borrar el PDH, se reactivan.
"""
from datetime import date
import logging

from django.db import transaction

from solicitudes.models import DeudaCorporativa
from .models import PermisoEspecial, PDH

logger = logging.getLogger(__name__)


def _fmt(d):
    return d.strftime('%d/%m/%Y') if d else ''


class PagoHorasService:

    @staticmethod
    def deudas_pendientes(explorador):
        """
        Lista unificada de deudas pendientes del explorador (dobladas + permisos),
        ordenada de la más antigua a la más reciente. Cada item:
            {key, tipo, id, fecha, fecha_str, horas, descripcion}
        key = 'doblada:<id>' | 'permiso:<id>' (lo que viaja en el form).
        """
        items = []

        dobladas = (
            DeudaCorporativa.objects
            .filter(explorador=explorador, estado='activa')
            .select_related('solicitud_origen__tipo_cambio')
            .order_by('fecha_doblada', 'id')
        )
        for d in dobladas:
            origen = (d.solicitud_origen.tipo_cambio.nombre
                      if d.solicitud_origen and d.solicitud_origen.tipo_cambio else 'Doblada')
            items.append({
                'key': f'doblada:{d.id}',
                'tipo': 'doblada',
                'id': d.id,
                'fecha': d.fecha_doblada,
                'fecha_str': _fmt(d.fecha_doblada),
                'horas': round(d.minutos / 60, 2),
                'descripcion': f'{origen} — {_fmt(d.fecha_doblada)}',
            })

        permisos = (
            PermisoEspecial.objects
            .filter(empleado=explorador, estado='APROBADO', pagado=False)
            .order_by('fecha_inicio', 'id')
        )
        for p in permisos:
            items.append({
                'key': f'permiso:{p.id}',
                'tipo': 'permiso',
                'id': p.id,
                'fecha': p.fecha_inicio,
                'fecha_str': _fmt(p.fecha_inicio),
                'horas': round(p.horas_totales(), 2),
                'descripcion': f'Permiso {p.get_tipo_display()} — {_fmt(p.fecha_inicio)}',
            })

        items.sort(key=lambda x: (x['fecha'] or date.max, x['tipo']))
        return items

    @staticmethod
    def _split_keys(keys):
        dobladas, permisos = [], []
        for k in keys:
            if ':' not in k:
                continue
            tipo, _, sid = k.partition(':')
            if not sid.isdigit():
                continue
            (dobladas if tipo == 'doblada' else permisos if tipo == 'permiso' else []).append(int(sid))
        return dobladas, permisos

    @staticmethod
    @transaction.atomic
    def aplicar_pago(supervisor, explorador, fecha, keys, comentario=''):
        """
        Crea el PDH por las deudas seleccionadas y las marca como pagadas.
        Devuelve (pdh, error). Si error != None, no se creó nada.
        """
        dob_ids, per_ids = PagoHorasService._split_keys(keys)
        if not dob_ids and not per_ids:
            return None, 'Debes seleccionar al menos una deuda a pagar.'

        dobladas = list(
            DeudaCorporativa.objects.filter(id__in=dob_ids, explorador=explorador, estado='activa')
        )
        permisos = list(
            PermisoEspecial.objects.filter(id__in=per_ids, empleado=explorador, estado='APROBADO', pagado=False)
        )
        if len(dobladas) != len(dob_ids) or len(permisos) != len(per_ids):
            return None, 'Alguna deuda seleccionada ya no está pendiente. Recarga la lista e intenta de nuevo.'

        total_horas = round(sum(d.minutos for d in dobladas) / 60
                            + sum(p.horas_totales() for p in permisos), 2)
        if total_horas <= 0:
            return None, 'Las deudas seleccionadas no suman horas a pagar.'

        pdh = PDH.objects.create(
            explorador=explorador,
            fecha=fecha,
            horas=total_horas,
            supervisor=supervisor,
            tipo_registro='pago_horas',
            comentario=comentario or '',
        )

        for d in dobladas:
            d.estado = 'pagada'
            d.fecha_pago = fecha
            d.save(update_fields=['estado', 'fecha_pago'])
        for p in permisos:
            p.pagado = True
            p.fecha_pago = fecha
            p.save(update_fields=['pagado', 'fecha_pago'])

        if dobladas:
            pdh.deudas_pagadas.add(*dobladas)
        if permisos:
            pdh.permisos_pagados.add(*permisos)

        logger.info("PDH %s creado: %s dobladas + %s permisos = %s h (explorador %s)",
                    pdh.id, len(dobladas), len(permisos), total_horas, explorador.id)
        return pdh, None

    @staticmethod
    @transaction.atomic
    def revertir_pago(pdh):
        """Reactiva las deudas que pagaba un PDH (al borrarlo/editarlo)."""
        for d in pdh.deudas_pagadas.all():
            if d.estado == 'pagada':
                d.estado = 'activa'
                d.fecha_pago = None
                d.save(update_fields=['estado', 'fecha_pago'])
        for p in pdh.permisos_pagados.all():
            if p.pagado:
                p.pagado = False
                p.fecha_pago = None
                p.save(update_fields=['pagado', 'fecha_pago'])
        pdh.deudas_pagadas.clear()
        pdh.permisos_pagados.clear()
