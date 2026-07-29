"""DobladaPagoService: aplicacion de la doblada en la fecha de PAGO.

Extraido de DobladaAplicacionService para aislar la logica de pago (el caso mas
complejo: reparto de sabado, cobertura jcp AM/PM/AMBAS, cesion parcial, jornada
cedida y fallback legacy) y el pago residual en semana. DobladaAplicacionService
delega en este servicio; dependencia en un solo sentido.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from solicitudes.models import SolicitudCambio, DobladaDetalle
from turnos.models import Turno
from turnos.services.jornada_service import JornadaService
from turnos.services.doblada_turno_service import DobladaTurnoService
from core.utils.jornada_utils import obtener_jornadas_am_pm as _obtener_jornadas_cache
import logging

logger = logging.getLogger(__name__)


class DobladaPagoService:
    @staticmethod
    @transaction.atomic
    def aplicar_doblada_pago(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Aplica la doblada en la fecha de pago.
        
        Orden de prioridad:
        1. Sábado con jornada_pago_sabado → reparto sábado.
        2. jornada_cubre_en_pago AM/PM → deudor SOLO esa media jornada, acreedor la otra.
        3. jornada_cubre_en_pago AMBAS  → deudor AM+PM, acreedor sin turnos.
        4. Cesión parcial sin jcp        → deudor la jornada cedida, acreedor la otra.
        5. jornada_cedida (quirúrgico)   → doblada completa en deudor.
        6. Fallback (legacy)             → doblada completa en deudor.
        
        Args:
            solicitud: Solicitud de doblada aprobada
            detalle: Detalle de la doblada
        
        Raises:
            ValidationError: Si hay errores al aplicar los cambios
        """
        fecha_pago = detalle.fecha_pago
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        
        fecha_pago_str = fecha_pago.strftime('%Y-%m-%d')
        
        # ===========================
        # Caso especial: Pago en Sábado
        # ===========================
        # Regla de negocio:
        # - En un sábado (fin de semana), el explorador que "tiene el fin de semana"
        #   normalmente tiene AM+PM (doblada completa) en BD o por asignación.
        # - Al pagar en sábado, el solicitante elige qué jornada trabajará (AM o PM)
        # - El receptor trabaja la jornada contraria (la que queda disponible).
        #
        # Implementación:
        # - Asegurar que el solicitante tenga SOLO la jornada seleccionada.
        # - Asegurar que el receptor tenga SOLO la jornada contraria.
        #
        if fecha_pago.weekday() == 5 and detalle.jornada_pago_sabado:
            return DobladaPagoService._aplicar_pago_sabado(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str)
        # ===========================
        # jornada_cubre_en_pago: elección explícita del deudor (AM / PM / AMBAS)
        # ===========================
        # TIENE PRIORIDAD sobre tipo_cesion, jornada_cedida y fallback.
        # Si el deudor eligió "solo AM", queda solo AM; si eligió "AMBAS", queda AM+PM.
        jcp = (getattr(detalle, 'jornada_cubre_en_pago', None) or '').strip().upper()

        if jcp == 'AMBAS':
            return DobladaPagoService._aplicar_pago_jcp_ambas(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str)
        if jcp in ('AM', 'PM'):
            return DobladaPagoService._aplicar_pago_jcp_media(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str, jcp)
        # ===========================
        # Cesión parcial SIN jornada_cubre_en_pago
        # ===========================
        # Regla de negocio: en la fecha de pago el DEUDOR cubre la jornada que trabaja el
        # ACREEDOR ese día (el favor que devuelve) y el ACREEDOR DESCANSA. El deudor conserva
        # lo que ya tenía, así que:
        #   - si el deudor ya trabajaba la otra jornada → queda con AM+PM (dobla).
        #   - si el deudor NO tenía turno ese día → trabaja SOLO la jornada del acreedor.
        if detalle.tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm'):
            return DobladaPagoService._aplicar_pago_cesion_parcial(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str)
        # ===========================
        # Pago con jornada_cedida conocida (quirúrgico: unión de jornadas del deudor)
        # ===========================
        # Cuando jornada_cedida está definida y no es sábado ni festivo especial,
        # el deudor (solicitante) debe terminar trabajando su jornada natural del día
        # MÁS la jornada cedida (doblada completa), y el acreedor descansa o pierde
        # solo la jornada cedida según su configuración.
        if detalle.jornada_cedida:
            return DobladaPagoService._aplicar_pago_jornada_cedida(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str)
        return DobladaPagoService._aplicar_pago_fallback(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str)

    @staticmethod
    def _aplicar_pago_sabado(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str) -> None:
        jornada_sel = detalle.jornada_pago_sabado.upper()

        # ===========================
        # AMBAS: el solicitante cubre el día completo (AM+PM) y el receptor descansa.
        # Como el solicitante trabaja de más, el receptor le queda debiendo media jornada
        # (se registra en generar_deudas_doblada y se paga en semana).
        # ===========================
        if jornada_sel == "AMBAS":
            jornadas_cache = _obtener_jornadas_cache()
            # Receptor descansa ese sábado: se eliminan sus turnos
            Turno.objects.filter(explorador=receptor, fecha=fecha_pago).delete()
            # Solicitante: dejar AM + PM
            Turno.objects.filter(explorador=solicitante, fecha=fecha_pago).delete()
            sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
            for jn in ("AM", "PM"):
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_pago,
                    jornada=jornadas_cache[jn],
                    sala=sala_solicitante,
                    tipo_cambio="DOBLADA",
                )
            logger.info(
                f"Pago en sábado (AMBAS): {solicitante.nombre} cubre AM+PM en {fecha_pago}, "
                f"{receptor.nombre} descansa (queda media jornada a favor del solicitante)."
            )
            return

        if jornada_sel not in ("AM", "PM"):
            raise ValidationError("jornada_pago_sabado inválida. Debe ser 'AM', 'PM' o 'AMBAS'")

        jornada_contraria = "PM" if jornada_sel == "AM" else "AM"

        jornadas_cache = _obtener_jornadas_cache()
        jornada_sel_obj = jornadas_cache[jornada_sel]
        jornada_contraria_obj = jornadas_cache[jornada_contraria]

        # 1) Solicitante: dejar la jornada seleccionada. Normalmente el sábado se reparte en dos
        # (el deudor trabaja una mitad), así que se limpia el día y se deja SOLO la seleccionada.
        # EXCEPCIÓN: si la mitad CONTRARIA ya la trabaja como pago de OTRA doblada aprobada ese
        # mismo sábado (cediste ambas jornadas a dos personas distintas), se ACUMULA — el deudor
        # termina doblado AM+PM, cada mitad pagando a una persona. En ese caso no se borra la
        # contraria, solo se recrea la seleccionada.
        _otra_mitad_pagada = SolicitudCambio.objects.filter(
            explorador_solicitante=solicitante,
            tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
            estado='aprobada',
            doblada__fecha_pago=fecha_pago,
            doblada__jornada_pago_sabado__iexact=jornada_contraria,
        ).exclude(id=solicitud.id).exists()
        if _otra_mitad_pagada:
            # Conservar la mitad contraria (otra doblada); rehacer solo la seleccionada.
            Turno.objects.filter(explorador=solicitante, fecha=fecha_pago, jornada=jornada_sel_obj).delete()
        else:
            Turno.objects.filter(explorador=solicitante, fecha=fecha_pago).delete()
        sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
        Turno.objects.create(
            explorador=solicitante,
            fecha=fecha_pago,
            jornada=jornada_sel_obj,
            sala=sala_solicitante,
            tipo_cambio="DOBLADA"
        )

        # 2) Receptor: se le quita la jornada que ahora cubre el deudor (jornada_sel). Normalmente
        # CONSERVA la contraria (reparto del sábado). EXCEPCIÓN: si esa contraria también se la
        # cubre el MISMO deudor con OTRA doblada suya ese mismo sábado (le pagas las DOS mitades al
        # mismo compañero), entonces el receptor NO trabaja ninguna → DESCANSA el día completo.
        _contraria_tambien_cubierta = SolicitudCambio.objects.filter(
            explorador_solicitante=solicitante,
            explorador_receptor=receptor,
            tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
            estado='aprobada',
            doblada__fecha_pago=fecha_pago,
            doblada__jornada_pago_sabado__iexact=jornada_contraria,
        ).exclude(id=solicitud.id).exists()

        if _contraria_tambien_cubierta:
            # Le pagas AM y PM al mismo compañero ese sábado → descansa completo (tú doblas).
            Turno.objects.filter(explorador=receptor, fecha=fecha_pago).delete()
            logger.info(
                f"Pago en sábado aplicado: {solicitante.nombre} cubre {jornada_sel} en {fecha_pago}; "
                f"{receptor.nombre} DESCANSA el día completo (le cubres ambas mitades)."
            )
        else:
            # Reparto normal: el receptor conserva la jornada contraria.
            Turno.objects.filter(explorador=receptor, fecha=fecha_pago, jornada=jornada_sel_obj).delete()
            if not Turno.objects.filter(explorador=receptor, fecha=fecha_pago, jornada=jornada_contraria_obj).exists():
                sala_receptor = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_pago)
                Turno.objects.create(
                    explorador=receptor,
                    fecha=fecha_pago,
                    jornada=jornada_contraria_obj,
                    sala=sala_receptor,
                    tipo_cambio="DOBLADA"
                )
            logger.info(
                f"Pago en sábado aplicado: {solicitante.nombre} trabaja {jornada_sel} en {fecha_pago}, "
                f"{receptor.nombre} trabaja {jornada_contraria} (jornada restante)"
            )
        return


    @staticmethod
    def _aplicar_pago_jcp_ambas(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str) -> None:
        jornadas_cache = _obtener_jornadas_cache()
        Turno.objects.filter(explorador=receptor, fecha=fecha_pago).delete()
        for jn in ('AM', 'PM'):
            j_obj = jornadas_cache[jn]
            if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, j_obj):
                sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(
                    solicitante, fecha_pago
                )
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_pago,
                    jornada=j_obj,
                    sala=sala_solicitante,
                    tipo_cambio="DOBLADA",
                )
        logger.info(
            f"Doblada pago (jcp=AMBAS): {solicitante.nombre} AM+PM en {fecha_pago}, "
            f"{receptor.nombre} descansa"
        )
        return


    @staticmethod
    def _aplicar_pago_jcp_media(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str, jcp) -> None:
        # jcp = jornada del ACREEDOR (que tiene doblada) que el deudor CUBRE al pagar.
        # El acreedor pierde la jornada cubierta y conserva la otra. Del lado del deudor:
        #   - si ESE día TRABAJA su propia jornada (la contraria a jcp) → DOBLA (su jornada + jcp).
        #   - si ese día está LIBRE (cedió, temporada, fin de semana...) → cubre SOLO jcp, quedando
        #     con UNA jornada (no tiene jornada propia que sumar).
        j_cubre = jcp                                   # ej. AM (la del acreedor que cubro)
        j_propia = 'PM' if j_cubre == 'AM' else 'AM'    # mi propia jornada ese día (contraria)
        jornadas_cache = _obtener_jornadas_cache()
        j_cubre_obj = jornadas_cache[j_cubre]
        j_propia_obj = jornadas_cache[j_propia]

        from turnos.services.turno_service import TurnoService as _TS_jcp
        deudor_trabaja_jcp = bool(_TS_jcp.estado_dia(solicitante, fecha_pago).get('trabaja'))
        # Si trabaja, suma su jornada propia (queda doblado); si está libre, solo cubre jcp.
        jornadas_deudor_crear = (j_propia_obj, j_cubre_obj) if deudor_trabaja_jcp else (j_cubre_obj,)
        for j_obj in jornadas_deudor_crear:
            if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, j_obj):
                sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_pago,
                    jornada=j_obj,
                    sala=sala_solicitante,
                    tipo_cambio="DOBLADA",
                )

        # Acreedor: pierde la jornada que cubre el deudor (jcp) y conserva la otra.
        Turno.objects.filter(
            explorador=receptor, fecha=fecha_pago, jornada=j_cubre_obj
        ).delete()
        if not DobladaTurnoService.tiene_jornada_en_fecha(receptor, fecha_pago, j_propia_obj):
            sala_receptor = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_pago)
            Turno.objects.create(
                explorador=receptor,
                fecha=fecha_pago,
                jornada=j_propia_obj,
                sala=sala_receptor,
                tipo_cambio="DOBLADA",
            )

        logger.info(
            f"Doblada pago (jcp={j_cubre}): {solicitante.nombre} dobla (su {j_propia} + cubre {j_cubre}); "
            f"{receptor.nombre} conserva {j_propia} en {fecha_pago}"
        )
        return


    @staticmethod
    def _aplicar_pago_cesion_parcial(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str) -> None:
        # Jornadas que el acreedor trabaja ese día = lo que el deudor va a cubrir.
        jornadas_acreedor = list(
            Turno.objects.filter(explorador=receptor, fecha=fecha_pago)
            .select_related('jornada')
        )
        if jornadas_acreedor:
            jornadas_a_cubrir = [t.jornada for t in jornadas_acreedor]
        else:
            # Sin turno explícito: usar la jornada base (predeterminada) del acreedor. Si no hay
            # jornada base no se puede adivinar cuál cubre — antes se asumía 'AM' en silencio, lo
            # que materializaba un turno arbitrario. Ahora falla explícito.
            jb = JornadaService.get_jornada_explorador_fecha(receptor.id, fecha_pago_str)
            if not jb:
                raise ValidationError(
                    f"El compañero {receptor.nombre} no tiene jornada asignada el "
                    f"{fecha_pago.strftime('%d/%m/%Y')}: no se puede determinar qué jornada cubrir "
                    f"al pagar la doblada."
                )
            jornadas_cache = _obtener_jornadas_cache()
            jornadas_a_cubrir = [jornadas_cache.get(jb.nombre.upper())]

        # IMPORTANTE: materializar la jornada BASE (virtual) del deudor como Turno explícito.
        # En un día de semana la jornada propia del deudor no tiene fila en BD (es virtual,
        # viene de la jornada predeterminada). Si no la materializamos y el deudor además
        # cubre la jornada del acreedor, queda UNA sola fila explícita y
        # TurnoService.obtener_jornada_display() NO lo reconoce como DOBLADA → se pierden
        # los 30 min de deuda corporativa aunque físicamente trabaje AM+PM.
        # OJO: solo se materializa si el deudor TRABAJA ese día. Si está LIBRE (descansa por
        # otra solicitud, fin de semana, temporada, etc.) NO tiene jornada propia que sumar:
        # solo cubre la del acreedor → queda con UNA jornada, no doblada.
        from turnos.services.turno_service import TurnoService as _TS_deudor_pago
        deudor_trabaja = bool(_TS_deudor_pago.estado_dia(solicitante, fecha_pago).get('trabaja'))
        deudor_sin_turnos = not Turno.objects.filter(explorador=solicitante, fecha=fecha_pago).exists()
        if deudor_sin_turnos and deudor_trabaja:
            jb_deudor = JornadaService.get_jornada_explorador_fecha(solicitante.id, fecha_pago_str)
            if jb_deudor and jb_deudor.nombre.upper() in ('AM', 'PM'):
                jbd_obj = _obtener_jornadas_cache().get(jb_deudor.nombre.upper())
                if jbd_obj and not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, jbd_obj):
                    sala_base = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                    Turno.objects.create(
                        explorador=solicitante,
                        fecha=fecha_pago,
                        jornada=jbd_obj,
                        sala=sala_base,
                        tipo_cambio="DOBLADA",
                    )

        # El acreedor descansa.
        Turno.objects.filter(explorador=receptor, fecha=fecha_pago).delete()
        # El deudor cubre esas jornadas (además de las suyas).
        for j_obj in jornadas_a_cubrir:
            if j_obj and not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, j_obj):
                sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_pago,
                    jornada=j_obj,
                    sala=sala_solicitante,
                    tipo_cambio="DOBLADA",
                )
        cubiertas = ', '.join(sorted({j.nombre for j in jornadas_a_cubrir if j}))
        logger.info(
            f"Doblada pago (cesión parcial): {solicitante.nombre} cubre {cubiertas} de "
            f"{receptor.nombre} (que descansa) en {fecha_pago}"
        )
        return


    @staticmethod
    def _aplicar_pago_jornada_cedida(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str) -> None:
        _jc_nombre = detalle.jornada_cedida.upper()
        _jcache = _obtener_jornadas_cache()
        _jc_obj = _jcache[_jc_nombre]

        turnos_deudor_antes = list(
            Turno.objects.filter(explorador=solicitante, fecha=fecha_pago)
            .select_related('jornada')
            .values('id', 'jornada__nombre', 'tipo_cambio')
        )

        # Materializar la base del deudor SOLO si ese día trabaja (no si descansa): un deudor
        # libre no suma su jornada propia, solo cubre la que devuelve.
        from turnos.services.turno_service import TurnoService as _TS_deudor_pago2
        _deudor_trabaja_cc = bool(_TS_deudor_pago2.estado_dia(solicitante, fecha_pago).get('trabaja'))
        if not turnos_deudor_antes and _deudor_trabaja_cc:
            jornada_base_deudor = JornadaService.get_jornada_explorador_fecha(
                solicitante.id, fecha_pago_str
            )
            if jornada_base_deudor:
                _jb_nombre = jornada_base_deudor.nombre.upper()
                if _jb_nombre != _jc_nombre:
                    _jb_obj = _jcache.get(_jb_nombre)
                    if _jb_obj and not DobladaTurnoService.tiene_jornada_en_fecha(
                        solicitante, fecha_pago, _jb_obj
                    ):
                        sala_sol_base = DobladaTurnoService.obtener_sala_explorador_fecha(
                            solicitante, fecha_pago
                        )
                        Turno.objects.create(
                            explorador=solicitante,
                            fecha=fecha_pago,
                            jornada=_jb_obj,
                            sala=sala_sol_base,
                            tipo_cambio="DOBLADA",
                        )

        # La jornada cedida es la parte PROPIA del deudor en la doblada de pago: solo se suma
        # si ese día TRABAJA. Si está LIBRE no dobla — únicamente cubre la del acreedor (abajo),
        # quedando con UNA sola jornada.
        if _deudor_trabaja_cc and not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, _jc_obj):
            sala_sol = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
            Turno.objects.create(
                explorador=solicitante,
                fecha=fecha_pago,
                jornada=_jc_obj,
                sala=sala_sol,
                tipo_cambio="DOBLADA",
            )

        # El deudor SIEMPRE cubre la jornada del acreedor (es el pago). Se garantiza aunque
        # coincida con la cedida (tiene_jornada evita duplicados): así el deudor libre queda
        # con esa jornada aunque el bloque de arriba se haya omitido.
        jornada_acreedor = JornadaService.get_jornada_explorador_fecha(
            receptor.id, fecha_pago_str
        )
        if jornada_acreedor:
            _ja_nombre = jornada_acreedor.nombre.upper()
            _ja_obj = _jcache.get(_ja_nombre)
            if _ja_obj and not DobladaTurnoService.tiene_jornada_en_fecha(
                solicitante, fecha_pago, _ja_obj
            ):
                sala_sol_acre = DobladaTurnoService.obtener_sala_explorador_fecha(
                    solicitante, fecha_pago
                )
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_pago,
                    jornada=_ja_obj,
                    sala=sala_sol_acre,
                    tipo_cambio="DOBLADA",
                )

        if getattr(detalle, 'tipo_cesion', None) == 'cesion_completa':
            DobladaTurnoService.eliminar_turnos_explorador(receptor, fecha_pago)
        else:
            Turno.objects.filter(
                explorador=receptor,
                fecha=fecha_pago,
                jornada=_jc_obj,
            ).delete()
            _jo_nombre = 'PM' if _jc_nombre == 'AM' else 'AM'
            _jo_obj = _jcache.get(_jo_nombre)
            if _jo_obj and not DobladaTurnoService.tiene_jornada_en_fecha(
                receptor, fecha_pago, _jo_obj
            ):
                sala_rec = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_pago)
                Turno.objects.create(
                    explorador=receptor,
                    fecha=fecha_pago,
                    jornada=_jo_obj,
                    sala=sala_rec,
                    tipo_cambio="DOBLADA",
                )

        _jornadas_deudor_final = sorted(
            Turno.objects.filter(explorador=solicitante, fecha=fecha_pago)
            .values_list('jornada__nombre', flat=True)
        )
        logger.info(
            f"Doblada pago (quirúrgico) aplicada: {solicitante.nombre} queda con "
            f"{_jornadas_deudor_final or 'sin turnos'}, {receptor.nombre} cede su jornada en {fecha_pago}"
        )
        return
    

    @staticmethod
    def _aplicar_pago_fallback(solicitud, detalle, fecha_pago, solicitante, receptor, fecha_pago_str) -> None:
        # ===========================
        # Caso fallback: Pago sin jornada_cedida (legacy)
        # ===========================
        jornada_deudor = JornadaService.get_jornada_explorador_fecha(
            solicitante.id, fecha_pago_str
        )
        jornada_acreedor = JornadaService.get_jornada_explorador_fecha(
            receptor.id, fecha_pago_str
        )
        
        # Sin jornada del acreedor no hay nada que devolverle: fallar con un mensaje de negocio
        # en vez de reventar con AttributeError sobre None y abortar la aprobación con un traceback.
        if not jornada_acreedor:
            raise ValidationError(
                f"El compañero {receptor.nombre} no tiene jornada asignada el "
                f"{fecha_pago.strftime('%d/%m/%Y')}: no hay jornada que cubrir para pagar la doblada."
            )

        jornadas_cache = _obtener_jornadas_cache()
        jornada_acreedor_obj = jornadas_cache[jornada_acreedor.nombre.upper()]

        # El deudor solo DOBLA (suma su jornada propia) si ESE día trabaja. Si está LIBRE —descansa
        # por otra solicitud (cedió), temporada o fin de semana— únicamente cubre la jornada del
        # acreedor y queda con UNA sola jornada. Sin esta comprobación, un deudor libre cuya jornada
        # base coincide con la del acreedor terminaba con la jornada DUPLICADA (dos filas AM/PM).
        from turnos.services.turno_service import TurnoService as _TS_fb
        deudor_trabaja_fb = bool(_TS_fb.estado_dia(solicitante, fecha_pago).get('trabaja'))
        # Sin jornada base propia no hay nada que sumar a la del acreedor: se trata igual que un
        # deudor libre (cubre solo la del acreedor) en vez de propagar None a crear_doblada_completa.
        if deudor_trabaja_fb and not jornada_deudor:
            logger.warning(
                "Doblada pago (legacy): %s figura como que trabaja el %s pero no tiene jornada base; "
                "cubrirá solo la jornada del acreedor.", solicitante.nombre, fecha_pago,
            )
            deudor_trabaja_fb = False

        if not deudor_trabaja_fb:
            if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, jornada_acreedor_obj):
                sala_fb = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                Turno.objects.create(
                    explorador=solicitante, fecha=fecha_pago,
                    jornada=jornada_acreedor_obj, sala=sala_fb, tipo_cambio='DOBLADA',
                )
        else:
            turno_deudor_existente = DobladaTurnoService.tiene_jornada_en_fecha(
                solicitante, fecha_pago, jornada_deudor
            )
            if turno_deudor_existente:
                jornadas_deudor = DobladaTurnoService.obtener_jornadas_en_fecha(solicitante, fecha_pago)
                jornada_acreedor_nombre = jornada_acreedor.nombre.upper()

                if jornada_acreedor_nombre not in jornadas_deudor:
                    DobladaTurnoService.agregar_jornada_a_doblada(
                        solicitante, fecha_pago, jornada_acreedor_obj, 'DOBLADA'
                    )
            else:
                DobladaTurnoService.crear_doblada_completa(
                    solicitante, fecha_pago, jornada_deudor, jornada_acreedor_obj, 'DOBLADA'
                )

        DobladaTurnoService.eliminar_turnos_explorador(receptor, fecha_pago)

        logger.info(
            f"Doblada pago (legacy) aplicada: {solicitante.nombre} "
            f"{'cubre la jornada del acreedor (libre)' if not deudor_trabaja_fb else 'dobla'} en "
            f"{fecha_pago}, Acreedor {receptor.nombre} descansa"
        )

    @staticmethod
    @transaction.atomic
    def aplicar_pago_residual_semana(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Aplica la devolución en semana de la deuda residual generada por un pago en sábado AMBAS.

        Ese día (detalle.fecha_pago_semana) el RECEPTOR dobla para cubrir al SOLICITANTE:
        - El solicitante DESCANSA su jornada (la que el receptor le devuelve).
        - El receptor trabaja DOBLE: su propia jornada + la del solicitante.

        Requiere jornadas contrarias ese día (ya validado en la estrategia).
        """
        fecha = detalle.fecha_pago_semana
        if not fecha:
            return

        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fstr = fecha.strftime('%Y-%m-%d')

        j_sol = JornadaService.get_jornada_explorador_fecha(solicitante.id, fstr)
        j_rec = JornadaService.get_jornada_explorador_fecha(receptor.id, fstr)
        if not j_sol or not j_rec:
            raise ValidationError("No se pudo determinar la jornada para el pago en semana.")

        jornadas_cache = _obtener_jornadas_cache()
        j_sol_obj = jornadas_cache[j_sol.nombre.upper()]
        j_rec_obj = jornadas_cache[j_rec.nombre.upper()]

        # Solicitante descansa su jornada (el receptor se la devuelve)
        Turno.objects.filter(explorador=solicitante, fecha=fecha, jornada=j_sol_obj).delete()

        # Receptor dobla: su jornada + la del solicitante
        if DobladaTurnoService.tiene_jornada_en_fecha(receptor, fecha, j_rec_obj):
            jornadas_receptor = DobladaTurnoService.obtener_jornadas_en_fecha(receptor, fecha)
            if j_sol.nombre.upper() not in jornadas_receptor:
                DobladaTurnoService.agregar_jornada_a_doblada(receptor, fecha, j_sol_obj, 'DOBLADA')
        else:
            DobladaTurnoService.crear_doblada_completa(receptor, fecha, j_rec_obj, j_sol_obj, 'DOBLADA')

        logger.info(
            f"Pago en semana aplicado: {receptor.nombre} dobla cubriendo a {solicitante.nombre} "
            f"en {fecha} (el solicitante descansa su jornada {j_sol.nombre.upper()})."
        )

