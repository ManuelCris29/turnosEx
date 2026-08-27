"""
Servicio de Pago de Horas (PDH) apuntando a deudas concretas.

Un PDH no es un pago "ciego" de horas: el supervisor selecciona QUÉ deudas paga. Las
deudas de un explorador provienen de dos fuentes:
  - Dobladas: `DeudaCorporativa` (estado='activa'), 0.5 h por día.
  - Permisos: `DeudaPermisoMes`, la parte de un permiso que corresponde a UN mes.

Todo se presenta AGRUPADO POR MES, porque el mes es la unidad en que la deuda vence y en
que se sanciona: un supervisor que solo viera una lista plana de deudas no podría saber
cuál está a punto de costarle una sanción al explorador.

Las deudas de permiso admiten PAGO PARCIAL. Antes la unidad mínima era el permiso entero,
lo que tenía dos consecuencias malas: no se podía abonar una parte, y un permiso permanente
largo era directamente impagable porque su total superaba el tope de un solo registro.

Al pagar, las deudas quedan marcadas y vinculadas al PDH; al borrarlo, se reactivan con el
importe exacto que este cubría.
"""
import logging
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from solicitudes.models import DeudaCorporativa

from .models import PDH, DeudaPermisoMes, PagoDeudaPermisoMes

logger = logging.getLogger(__name__)

# Tope por registro de pago (coincide con PDH.clean()). Pagos mayores se dividen, y ahora
# SIEMPRE se pueden dividir: la deuda de un permiso se puede abonar por partes.
MAX_HORAS_POR_PAGO = 24

_MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
          'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']


def _fmt(d):
    return d.strftime('%d/%m/%Y') if d else ''


def _horas(minutos):
    return round(minutos / 60, 2)


class PagoHorasService:

    @staticmethod
    def deudas_pendientes(explorador):
        """
        Deudas pendientes del explorador AGRUPADAS POR MES, del más antiguo al más reciente.

        Cada grupo:
            {periodo, anio, mes, etiqueta, vencido,
             horas_debidas, horas_pagadas, horas_pendientes, items: [...]}

        Cada item:
            {key, tipo, id, fecha, fecha_str, horas, parcial, descripcion}

        `key` = 'doblada:<id>' | 'permisomes:<id>' (lo que viaja en el formulario). Los
        ítems con `parcial=True` aceptan un importe; los demás se pagan enteros.

        `vencido` marca los meses ya cerrados: son los que sancionan, y por eso la pantalla
        tiene que poder destacarlos.
        """
        # Red de seguridad: un permiso aprobado por una vía que no sincronizara sus meses
        # sería invisible aquí, y el explorador parecería no deber nada.
        from .deuda_permiso_service import asegurar_deudas
        try:
            asegurar_deudas(explorador)
        except Exception:
            logger.warning('No se pudieron asegurar las deudas mensuales de %s',
                           getattr(explorador, 'id', '?'), exc_info=True)

        grupos = {}

        def _grupo(anio, mes):
            clave = (anio, mes)
            if clave not in grupos:
                grupos[clave] = {
                    'periodo': f'{anio}-{mes:02d}', 'anio': anio, 'mes': mes,
                    'etiqueta': f'{_MESES[mes - 1]} {anio}',
                    'minutos_debidos': 0, 'minutos_pagados': 0, 'items': [],
                }
            return grupos[clave]

        dobladas = (
            DeudaCorporativa.objects
            .filter(explorador=explorador, estado='activa')
            .select_related('solicitud_origen__tipo_cambio')
            .order_by('fecha_doblada', 'id')
        )
        for d in dobladas:
            origen = (d.solicitud_origen.tipo_cambio.nombre
                      if d.solicitud_origen and d.solicitud_origen.tipo_cambio else 'Doblada')
            grupo = _grupo(d.fecha_doblada.year, d.fecha_doblada.month)
            grupo['minutos_debidos'] += d.minutos
            grupo['items'].append({
                'key': f'doblada:{d.id}',
                'tipo': 'doblada',
                'id': d.id,
                'fecha': d.fecha_doblada,
                'fecha_str': _fmt(d.fecha_doblada),
                'horas': _horas(d.minutos),
                'horas_pendientes': _horas(d.minutos),
                'parcial': False,
                'descripcion': f'{origen} — {_fmt(d.fecha_doblada)}',
            })

        permisos_mes = (
            DeudaPermisoMes.objects
            .filter(explorador=explorador, estado='activa')
            .select_related('permiso')
            .order_by('anio', 'mes', 'id')
        )
        for d in permisos_mes:
            if d.minutos_pendientes <= 0:
                continue
            permiso = d.permiso
            grupo = _grupo(d.anio, d.mes)
            grupo['minutos_debidos'] += d.minutos_generados
            grupo['minutos_pagados'] += d.minutos_pagados
            if permiso.es_permanente:
                detalle = f'permanente, {permiso.dias_semana_legible().lower()}'
            else:
                detalle = permiso.especificacion or 'puntual'
            grupo['items'].append({
                'key': f'permisomes:{d.id}',
                'tipo': 'permisomes',
                'id': d.id,
                'fecha': None,
                'fecha_str': '',
                'horas': d.horas_pendientes,
                'horas_pendientes': d.horas_pendientes,
                'parcial': True,
                'descripcion': (f'Permiso {permiso.get_tipo_display()} ({detalle}) — '
                                f'{d.ocurrencias} día(s) en el mes'),
            })

        hoy = date.today()
        salida = []
        for (anio, mes), grupo in sorted(grupos.items()):
            pendientes = sum(i['horas_pendientes'] for i in grupo['items'])
            salida.append({
                'periodo': grupo['periodo'],
                'anio': anio, 'mes': mes,
                'etiqueta': grupo['etiqueta'],
                'vencido': (anio, mes) < (hoy.year, hoy.month),
                'horas_debidas': _horas(grupo['minutos_debidos']),
                'horas_pagadas': _horas(grupo['minutos_pagados']),
                'horas_pendientes': round(pendientes, 2),
                'items': grupo['items'],
            })
        return salida

    @staticmethod
    def _split_keys(keys):
        """IDs únicos por tipo. Un mismo checkbox repetido en el POST cuenta una sola vez."""
        dobladas, permisos_mes = [], []
        for k in keys:
            if ':' not in k:
                continue
            tipo, _, sid = k.partition(':')
            if not sid.isdigit():
                continue
            destino = (dobladas if tipo == 'doblada'
                       else permisos_mes if tipo == 'permisomes' else None)
            if destino is not None and int(sid) not in destino:
                destino.append(int(sid))
        return dobladas, permisos_mes

    @staticmethod
    @transaction.atomic
    def aplicar_pago(supervisor, explorador, fecha, keys, comentario='', importes=None):
        """
        Crea el PDH por las deudas seleccionadas y las marca como pagadas.
        Devuelve (pdh, error). Si error != None, no se creó nada.

        `fecha` debe ser un `date` ya validado por la vista.
        `importes` es {'permisomes:<id>': horas} para los pagos PARCIALES; lo que no venga
        se abona íntegro. Un importe mayor que lo pendiente se rechaza en vez de recortarse
        en silencio: casi siempre es un error de quien lo teclea, y aceptarlo dejaría el
        PDH diciendo que se pagó más de lo que se debía.
        """
        dob_ids, permes_ids = PagoHorasService._split_keys(keys)
        if not dob_ids and not permes_ids:
            return None, 'Debes seleccionar al menos una deuda a pagar.'

        # select_for_update: sin el bloqueo, dos supervisores pagando a la vez pasan ambos
        # la comprobación de "sigue pendiente" y saldan la misma deuda dos veces.
        dobladas = list(
            DeudaCorporativa.objects
            .select_for_update()
            .filter(id__in=dob_ids, explorador=explorador, estado='activa')
        )
        deudas_mes = list(
            DeudaPermisoMes.objects
            .select_for_update()
            .filter(id__in=permes_ids, explorador=explorador, estado='activa')
        )
        if len(dobladas) != len(dob_ids) or len(deudas_mes) != len(permes_ids):
            return None, 'Alguna deuda seleccionada ya no está pendiente. Recarga la lista e intenta de nuevo.'

        importes = importes or {}
        a_pagar = {}
        for d in deudas_mes:
            bruto = importes.get(f'permisomes:{d.id}')
            if bruto in (None, ''):
                minutos = d.minutos_pendientes
            else:
                try:
                    minutos = round(float(bruto) * 60)
                except (TypeError, ValueError):
                    return None, f'El importe indicado para {d.periodo.nombre()} no es un número válido.'
            if minutos <= 0:
                return None, f'El importe a pagar de {d.periodo.nombre()} debe ser mayor que cero.'
            if minutos > d.minutos_pendientes:
                return None, (f'De {d.periodo.nombre()} solo quedan {d.horas_pendientes} h '
                              f'pendientes y se han indicado {round(minutos / 60, 2)} h.')
            a_pagar[d.id] = minutos

        # La fecha de pago no se valida contra hoy ni contra la fecha de la deuda: el pago se
        # acuerda entre supervisor y explorador (normalmente dentro del mes de la deuda, pero el
        # supervisor le da manejo). Deudas con fecha futura, de hecho, solo se pueden pagar así.

        total_horas = round(sum(d.minutos for d in dobladas) / 60
                            + sum(a_pagar.values()) / 60, 2)
        if total_horas <= 0:
            return None, 'Las deudas seleccionadas no suman horas a pagar.'
        if total_horas > MAX_HORAS_POR_PAGO:
            return None, (f'Un solo pago no puede superar {MAX_HORAS_POR_PAGO} h y has seleccionado '
                          f'{total_horas} h. Divide el pago en varios registros.')

        pdh = PDH(
            explorador=explorador,
            fecha=fecha,
            horas=total_horas,
            supervisor=supervisor,
            tipo_registro='pago_horas',
            comentario=comentario or '',
        )
        try:
            # El límite de horas del modelo solo se aplica si alguien llama a full_clean().
            pdh.full_clean(exclude=['solicitud'])
        except ValidationError as e:
            return None, ' '.join(e.messages)
        pdh.save()

        for d in dobladas:
            d.estado = 'pagada'
            d.fecha_pago = fecha
            d.save(update_fields=['estado', 'fecha_pago'])

        permisos_tocados = set()
        for d in deudas_mes:
            minutos = a_pagar[d.id]
            d.minutos_pagados += minutos
            # `fecha_pago` es la del abono que SALDA el mes, no la del primer pago a cuenta:
            # de ella depende si el periodo cuenta como cumplido, y hasta que no se salda
            # del todo el explorador seguía debiendo.
            if d.minutos_pendientes <= 0:
                d.estado = 'pagada'
                d.fecha_pago = fecha
            d.save(update_fields=['minutos_pagados', 'estado', 'fecha_pago', 'actualizado_en'])
            PagoDeudaPermisoMes.objects.create(pdh=pdh, deuda=d, minutos=minutos)
            permisos_tocados.add(d.permiso_id)

        if dobladas:
            pdh.deudas_pagadas.add(*dobladas)

        PagoHorasService._recalcular_permisos(permisos_tocados)

        logger.info("PDH %s creado: %s dobladas + %s meses de permiso = %s h (explorador %s)",
                    pdh.id, len(dobladas), len(deudas_mes), total_horas, explorador.id)
        return pdh, None

    @staticmethod
    def _recalcular_permisos(permiso_ids):
        """Rehace el `pagado` de los permisos afectados a partir de sus meses."""
        if not permiso_ids:
            return
        from .deuda_permiso_service import recalcular_roll_up
        from .models import PermisoEspecial
        for permiso in PermisoEspecial.objects.filter(id__in=permiso_ids):
            try:
                recalcular_roll_up(permiso)
            except Exception:
                logger.warning('Error recalculando el permiso %s tras un pago',
                               permiso.id, exc_info=True)

    @staticmethod
    @transaction.atomic
    def sincronizar_fecha_pago(pdh):
        """
        Propaga la fecha del PDH a las deudas que salda. Al editar un pago, si no se hace,
        el PDH dice una fecha y sus deudas otra (la que tenían al crearse).
        """
        pdh.deudas_pagadas.filter(estado='pagada').update(fecha_pago=pdh.fecha)
        DeudaPermisoMes.objects.filter(
            pagos__pdh=pdh, estado='pagada').update(fecha_pago=pdh.fecha)

    @staticmethod
    @transaction.atomic
    def revertir_pago(pdh):
        """
        Reactiva las deudas que pagaba un PDH (al borrarlo/editarlo).

        Para las deudas mensuales devuelve el importe EXACTO que este pago cubría, que es
        para lo que existe la tabla intermedia: con un M2M plano no se sabría si el PDH
        pagó el mes entero o solo una parte, y revertirlo dejaría el saldo mal.
        """
        for d in pdh.deudas_pagadas.select_for_update():
            if d.estado == 'pagada':
                d.estado = 'activa'
                d.fecha_pago = None
                d.save(update_fields=['estado', 'fecha_pago'])
        pdh.deudas_pagadas.clear()

        permisos_tocados = set()
        for detalle in (PagoDeudaPermisoMes.objects
                        .filter(pdh=pdh).select_related('deuda')):
            deuda = DeudaPermisoMes.objects.select_for_update().get(id=detalle.deuda_id)
            # Una deuda ya extinguida por una sanción cumplida no vuelve a la vida porque se
            # borre el pago: la sanción la saldó, y resucitarla haría que el explorador
            # volviera a deber —y a poder ser sancionado— por algo que ya cumplió.
            if deuda.estado == 'consumida_por_sancion':
                logger.warning(
                    'El PDH %s pagaba la deuda %s, que ya fue consumida por una sanción: '
                    'no se revierte.', pdh.id, deuda.id)
                detalle.delete()
                continue
            deuda.minutos_pagados = max(0, deuda.minutos_pagados - detalle.minutos)
            if deuda.minutos_pendientes > 0 and deuda.estado == 'pagada':
                deuda.estado = 'activa'
                deuda.fecha_pago = None
            deuda.save(update_fields=['minutos_pagados', 'estado', 'fecha_pago',
                                      'actualizado_en'])
            permisos_tocados.add(deuda.permiso_id)
            detalle.delete()

        PagoHorasService._recalcular_permisos(permisos_tocados)
