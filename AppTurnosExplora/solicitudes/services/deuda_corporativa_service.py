"""
Política de SANCIÓN POR DEUDA: quién cierra un mes debiendo, qué sanción le corresponde y
cuándo una deuda vieja queda saldada por haber cumplido la sanción.

Este módulo decide; no persiste deudas ni redacta avisos. Eso vive aparte desde que la clase
llegó a 1130 líneas mezclando cuatro motivos de cambio distintos:

- el CÁLCULO puro (duración, reincidencia, plazos) → `sancion_deuda_calculo.py`
- la PERSISTENCIA de `DeudaCorporativa`            → `deuda_corporativa_repository.py`
- los AVISOS al explorador                         → `sancion_notificador.py`
- la POLÍTICA y su orquestación                    → este archivo
"""
import logging
from datetime import date, timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from empleados.models import Empleado
from empleados.sancion_utils import invalidar_cache_turnos
from solicitudes.models import ConfiguracionSanciones, DeudaCorporativa
from solicitudes.services.sancion_deuda_calculo import (
    DURACION_BASE_DIAS as _DURACION_BASE_DIAS,
)
from solicitudes.services.sancion_deuda_calculo import (
    Antecedente,
    Periodo,
    cadena_sanciones,
    fin_de_plazo,
)
from solicitudes.services.sancion_notificador import SancionNotificador

logger = logging.getLogger(__name__)


class DeudaCorporativaService:
    """
    Servicio para gestión de deudas corporativas.

    Responsabilidad única: Operaciones sobre deudas corporativas acumuladas.
    """

    @staticmethod
    def aplica_deuda_doblada(fecha: date) -> bool:
        """
        Regla de negocio: los 30 minutos de deuda corporativa por doblada solo
        aplican de LUNES A VIERNES. Los sábados, domingos y festivos NO generan
        deuda, porque ese día se trabaja una jornada completa de todos modos.
        """
        if fecha.weekday() >= 5:  # 5=sábado, 6=domingo
            return False
        try:
            from solicitudes.services.cambios_permanentes_helper import es_festivo
            if es_festivo(fecha):
                return False
        except Exception:
            logger.warning("Error verificando festivo para deuda (fecha=%s)", fecha, exc_info=True)
        return True

    # Marca para identificar las sanciones generadas automáticamente por deuda vencida
    AUTO_SANCION_PREFIJO = '[AUTO-DEUDA]'

    # Criterio ÚNICO de "esta sanción la creó el sistema por una deuda vencida". Es el
    # PERIODO, no el prefijo del motivo: el motivo es texto libre que el supervisor puede
    # reescribir desde la pantalla de edición, y el periodo es un dato del ledger que nadie
    # edita. Con el criterio anterior, retocar la redacción de una sanción automática la
    # volvía invisible para TODAS estas consultas a la vez, con dos efectos: su deuda no se
    # consumía al cumplirse el castigo, y su mes dejaba de contar como juzgado, así que el
    # sistema podía sancionar por segunda vez un mes ya castigado.
    #
    # El prefijo se sigue escribiendo en el motivo (`_texto_motivo`), pero solo como
    # etiqueta para quien lo lee. Ninguna decisión depende ya de él.
    ES_AUTOMATICA = Q(periodo_anio__isnull=False)
    ES_MANUAL = Q(periodo_anio__isnull=True)

    @staticmethod
    def _periodos_con_deuda(explorador: Empleado, solo_cerrados: bool = True):
        """
        Meses en los que el explorador TODAVÍA debe algo, de cualquiera de las dos fuentes.

        Las dos fuentes son las dobladas (`DeudaCorporativa`, cuyo mes es el de la doblada)
        y los permisos (`DeudaPermisoMes`, que ya nace con su mes). Antes solo contaban las
        primeras, así que un permiso impagado no sancionaba nunca.

        Con `solo_cerrados` se descartan los meses que aún no han terminado: mientras el mes
        corre todavía se está en plazo, y sancionar ahí sería castigar antes del vencimiento.

        Quedan fuera 'pagada', 'cancelada' y los dos estados de extinción por sanción,
        'consumida_por_sancion' (cumplida) y 'condonada' (levantada). Esos dos son los que
        garantizan que una deuda ya resuelta por una sanción no vuelva a sancionar.
        """
        from permisos.models import DeudaPermisoMes

        limite = Periodo.de_fecha(timezone.localdate())
        periodos = set()

        for fecha in (DeudaCorporativa.objects
                      .filter(explorador=explorador, estado='activa')
                      .values_list('fecha_doblada', flat=True)):
            periodos.add(Periodo.de_fecha(fecha))

        for anio, mes, generados, pagados in (
                DeudaPermisoMes.objects
                .filter(explorador=explorador, estado='activa')
                .values_list('anio', 'mes', 'minutos_generados', 'minutos_pagados')):
            if generados > pagados:
                periodos.add(Periodo(anio, mes))

        if solo_cerrados:
            periodos = {p for p in periodos if p < limite}
        return sorted(periodos)

    # La duración vive en la capa de cálculo (`sancion_deuda_calculo`), que es quien
    # decide las ventanas. Se reexporta aquí porque hay código y tests que la leen desde
    # el servicio; no debe redefinirse, o cálculo y mensajes dejarían de coincidir.
    DURACION_BASE_DIAS = _DURACION_BASE_DIAS

    @staticmethod
    def _consumir_deudas_de_sanciones_cumplidas(explorador: Empleado) -> int:
        """
        Una sanción CUMPLIDA extingue la deuda del mes que la originó: el castigo ES el pago.

        Sin esto, el explorador terminaría de cumplir sus 15 días y su deuda seguiría viva,
        lista para sancionarlo otra vez por lo mismo — un bucle del que no se sale.

        Solo consumen las cumplidas de verdad: aquí se trata el castigo que se pagó
        cumpliéndolo. Una sanción LEVANTADA también extingue su deuda, pero por otra vía
        —`condonar_deudas_por_levantamiento`, disparada en el propio levantamiento— y
        dejándola en un estado distinto ('condonada'). No se atienden las dos aquí a
        propósito: son decisiones distintas, con responsable distinto y momento distinto,
        y un informe tiene que poder separar lo cumplido de lo perdonado.

        Idempotente: solo toca lo que sigue 'activa', así que repetirla no hace nada. Por eso
        puede llamarse desde los cinco disparadores sin coordinarlos.
        """
        from empleados.models import SancionEmpleado
        from permisos.models import DeudaPermisoMes

        hoy = timezone.localdate()
        cumplidas = (
            SancionEmpleado.objects
            .filter(DeudaCorporativaService.ES_AUTOMATICA,
                    explorador=explorador,
                    levantada_en__isnull=True,
                    fecha_fin__lt=hoy)
        )

        consumidas = 0
        permisos_tocados = set()
        for sancion in cumplidas:
            consumidas += (
                DeudaCorporativa.objects
                .filter(explorador=explorador, estado='activa',
                        fecha_doblada__year=sancion.periodo_anio,
                        fecha_doblada__month=sancion.periodo_mes)
                .update(estado='consumida_por_sancion',
                        sancion_consumidora=sancion, fecha_consumo=hoy)
            )
            pendientes = (
                DeudaPermisoMes.objects
                .filter(explorador=explorador, estado='activa',
                        anio=sancion.periodo_anio, mes=sancion.periodo_mes)
            )
            permisos_tocados.update(pendientes.values_list('permiso_id', flat=True))
            consumidas += pendientes.update(
                estado='consumida_por_sancion',
                sancion_consumidora=sancion, fecha_consumo=hoy)

        if permisos_tocados:
            from permisos.models import PermisoEspecial
            from permisos.services.deuda_permiso_service import recalcular_roll_up
            for permiso in PermisoEspecial.objects.filter(id__in=permisos_tocados):
                try:
                    recalcular_roll_up(permiso)
                except Exception:
                    logger.warning('Error recalculando el permiso %s tras consumir su deuda',
                                   permiso.id, exc_info=True)

        if consumidas:
            logger.info('Consumidas %s deuda(s) de %s por sanciones ya cumplidas.',
                        consumidas, explorador.id)
        return consumidas

    @staticmethod
    @transaction.atomic
    def condonar_deudas_por_levantamiento(sancion, hoy=None) -> int:
        """
        Levantar una auto-sanción CONDONA la deuda del mes que la originó.

        Sin esto la deuda quedaba en un limbo del que no salía nunca: su mes ya venció, así
        que no se puede pagar (`Periodo.esta_vencido` cierra el PDH); la sanción no la va a
        consumir al llegar a su fin, porque el consumo exige `levantada_en IS NULL`; y no
        nace otra sanción que la consuma, porque `_periodos_ya_evaluados` cuenta las
        levantadas como mes ya juzgado. Resultado: horas activas para siempre, ni cobrables
        ni saldables, engordando el saldo del explorador sin ninguna forma de bajarlo.

        La regla que cierra ese hueco es que levantar perdona el hecho entero, no solo el
        castigo: si el motivo era una excusa certificable, no hay falta que cobrar. Lo que
        NO se borra es el antecedente —`_periodos_ya_evaluados` y `_antecedente` siguen
        viendo esta sanción—, así que la reincidencia se mide igual. Se perdona la deuda,
        no el expediente.

        Solo actúa sobre auto-sanciones por deuda, y las reconoce por `periodo_anio/mes`, no
        por el prefijo del motivo. El periodo existe justamente para esto: es un dato del
        ledger, mientras que el motivo es texto libre y editable desde la pantalla de
        edición. Mirando el texto, retocar la redacción de una sanción automática la
        convertiría en irreconocible y sus horas volverían al limbo que esto cierra. Una
        sanción manual no tiene periodo —no nació de un mes impagado— y no condona nada.

        Idempotente: toca solo lo que sigue 'activa'. Llamarla dos veces —doble clic,
        reintento— no condona nada nuevo ni reescribe quién lo hizo.

        Devuelve cuántas deudas se condonaron.
        """
        from permisos.models import DeudaPermisoMes

        if not sancion or not sancion.levantada_en:
            return 0
        if not sancion.periodo_anio or not sancion.periodo_mes:
            return 0

        fecha = hoy or sancion.levantada_en
        marca = {'estado': 'condonada',
                 'sancion_consumidora': sancion,
                 'fecha_consumo': fecha}

        condonadas = (
            DeudaCorporativa.objects
            .filter(explorador_id=sancion.explorador_id, estado='activa',
                    fecha_doblada__year=sancion.periodo_anio,
                    fecha_doblada__month=sancion.periodo_mes)
            .update(**marca)
        )

        pendientes = (
            DeudaPermisoMes.objects
            .filter(explorador_id=sancion.explorador_id, estado='activa',
                    anio=sancion.periodo_anio, mes=sancion.periodo_mes)
        )
        permisos_tocados = set(pendientes.values_list('permiso_id', flat=True))
        condonadas += pendientes.update(**marca)

        # El permiso guarda un `pagado` agregado que se calcula desde sus meses. Sin
        # rehacerlo, un permiso con todos sus meses ya extinguidos seguiría figurando como
        # impagado en las pantallas que leen el agregado y no el detalle.
        if permisos_tocados:
            from permisos.models import PermisoEspecial
            from permisos.services.deuda_permiso_service import recalcular_roll_up
            for permiso in PermisoEspecial.objects.filter(id__in=permisos_tocados):
                try:
                    recalcular_roll_up(permiso)
                except Exception:
                    logger.warning('Error recalculando el permiso %s tras condonar su deuda',
                                   permiso.id, exc_info=True)

        if condonadas:
            logger.info('Condonadas %s deuda(s) de %s (%s-%s) al levantar la sanción %s.',
                        condonadas, sancion.explorador_id, sancion.periodo_anio,
                        sancion.periodo_mes, sancion.id)
        return condonadas

    @staticmethod
    def horas_condonadas_por(sancion) -> float:
        """
        Horas que esta sanción llegó a condonar REALMENTE, leídas de lo ya escrito.

        Es la fuente de verdad para todo lo que se cuenta después del hecho: el mensaje al
        supervisor y el aviso al explorador. Antes, el mensaje repetía la estimación
        calculada para el aviso previo, y entre una y otra podía entrar un pago; se
        anunciaba una cifra y se perdonaba otra. Leyendo lo escrito eso no puede pasar.
        """
        from permisos.models import DeudaPermisoMes

        if not sancion or not sancion.pk:
            return 0.0
        minutos = sum(
            DeudaCorporativa.objects
            .filter(sancion_consumidora=sancion, estado='condonada')
            .values_list('minutos', flat=True))
        minutos += sum(
            DeudaPermisoMes.objects
            .filter(sancion_consumidora=sancion, estado='condonada')
            .values_list('minutos_generados', flat=True))
        return round(minutos / 60, 2)


    @staticmethod
    def _antecedente(explorador: Empleado):
        """
        La última sanción que ya tuvo efecto sobre esta persona, para medir la reincidencia.

        Cuenta CUALQUIER sanción, no solo las automáticas por deuda: una sanción manual del
        supervisor es un antecedente disciplinario igual de real, y quien acaba de cumplir
        un castigo por otro motivo no está estrenando expediente.

        También cuentan las levantadas a mano, y la ventana se mide desde el día en que
        dejaron de aplicar (`fecha_fin_efectiva`). Levantar perdona ESE castigo y la deuda
        de su mes (`condonar_deudas_por_levantamiento`), pero no borra que ocurrió: se
        perdona la deuda, no el expediente.

        Es la ÚNICA consulta del subsistema que no filtra por `ES_AUTOMATICA`, y es
        deliberado: aquí se mide el expediente completo, no solo lo automático. Nadie debe
        "completar" la migración al criterio por periodo en este punto por simetría —lo
        haría, dejaría de contar las sanciones manuales y la reincidencia se abarataría.

        Devuelve None si no hay ninguna, o si la más reciente es indefinida (sin fecha de
        fin): de una sanción que aún no ha terminado no se puede medir ninguna ventana.
        """
        from empleados.models import SancionEmpleado

        ultima = None
        for sancion in (SancionEmpleado.objects
                        .filter(explorador=explorador)
                        .only('fecha_fin', 'levantada_en', 'nivel_reincidencia')):
            fin = sancion.fecha_fin_efectiva
            if fin is None:
                continue
            if ultima is None or fin > ultima.fin:
                ultima = Antecedente(fin=fin, nivel=sancion.nivel_reincidencia or 1)
        return ultima

    @staticmethod
    def _periodos_ya_evaluados(explorador: Empleado) -> set[tuple[int, int]]:
        """
        Meses de este explorador que el sistema YA juzgó, hayan acabado como hayan acabado.

        Cuenta también las sanciones levantadas a mano. No es un descuido: levantar es una
        decisión del supervisor sobre un caso que el sistema ya evaluó, y volver a crearla
        la anularía en el acto. Un botón que se deshace solo no es un botón.

        Por eso mismo esta consulta tiene que ser la MISMA que decide qué se materializa y
        la que decide qué se le enseña al supervisor. Si divergen aparece el peor de los
        estados: una fila que dice "nadie ha evaluado esto" sobre un caso ya evaluado, con
        un botón de aplicar que no puede hacer nada. Se arregla teniéndola en un solo sitio.
        """
        from empleados.models import SancionEmpleado

        return set(
            SancionEmpleado.objects
            .filter(DeudaCorporativaService.ES_AUTOMATICA, explorador=explorador)
            .values_list('periodo_anio', 'periodo_mes')
        )

    @staticmethod
    def gestionar_sancion_por_deuda(explorador: Empleado):
        """
        Pone al día las sanciones automáticas por deuda vencida de UN explorador.

        Es idempotente y su resultado NO depende de cuándo se la llame: las fechas salen del
        vencimiento de cada mes, no del reloj, así que ejecutarla el día 1 o tres semanas
        más tarde graba exactamente los mismos registros. Esa propiedad es la que permite
        tener cinco disparadores distintos (revisión diaria, pantallas, POST, aprobación y
        pago) sin que compitan entre sí.

        Qué hace, en orden:

        1. Consume las deudas de las sanciones ya cumplidas (el castigo salda la deuda).
        2. Calcula qué meses quedaron incumplidos y qué sanción corresponde a cada uno.
        3. Materializa las que faltan de los meses que TODAVÍA tienen saldo.

        Reglas:
        - 1ª sanción: 15 días. Cada mes incumplido más, otros 15 (30, 45, 60…). Sin tope.
        - Pagar NO levanta la sanción. La deuda cambia de estado, el castigo sigue su curso
          hasta cumplir su duración. Antes el pago la levantaba en el acto, lo que convertía
          la sanción en una fianza reembolsable en vez de en una consecuencia.
        - Una sanción que el supervisor levantó a mano no se recrea: su decisión manda.
        - La reincidencia PRESCRIBE. Si desde que terminó la anterior pasa la ventana
          configurada (`ConfiguracionSanciones`) sin sanciones nuevas, el contador vuelve a
          cero y la siguiente es otra vez de 15 días.

        Las sanciones MANUALES siguen siendo una vía paralela en cuanto a su gestión: este
        proceso solo CREA y TOCA las automáticas (`ES_AUTOMATICA`), no las levanta, y
        que exista una manual no impide crear la automática —son hechos disciplinarios
        distintos, con fechas distintas—.

        Pero sí las LEE para medir la reincidencia: cualquier sanción cumplida es un
        antecedente, venga de donde venga. Quien acaba de cumplir un castigo por otro
        motivo no está estrenando expediente. Ver `_antecedente`.

        Devuelve {'creadas': int, 'consumidas': int}.
        """
        from empleados.models import SancionEmpleado

        if not explorador:
            return {'creadas': 0, 'consumidas': 0}

        consumidas = DeudaCorporativaService._consumir_deudas_de_sanciones_cumplidas(explorador)

        con_saldo = set(DeudaCorporativaService._periodos_con_deuda(explorador))
        if not con_saldo:
            return {'creadas': 0, 'consumidas': consumidas}

        # Qué periodos tienen ya un registro. La clave es el PERIODO y no la fecha de
        # inicio: el periodo es un hecho del ledger y no se mueve, mientras que la fecha de
        # inicio depende del encadenado y podría cambiar si aparece un mes anterior.
        ya_materializados = DeudaCorporativaService._periodos_ya_evaluados(explorador)

        pendientes = sorted(p for p in con_saldo
                            if (p.anio, p.mes) not in ya_materializados)
        if not pendientes:
            return {'creadas': 0, 'consumidas': consumidas}

        ventana = ConfiguracionSanciones.ventana_reincidencia()
        cadena = cadena_sanciones(
            pendientes, ventana,
            DeudaCorporativaService._antecedente(explorador))

        creadas = 0
        hoy = timezone.localdate()
        ultimo_fin = None
        for sancion in cadena:

            # Un castigo no se puede cumplir en el pasado. La ventana calculada puede haber
            # expirado ya, y grabarla tal cual daría una sanción nacida muerta: se
            # consumiría en el acto (extinguiendo la deuda) sin haber bloqueado a nadie ni
            # un día. Un incumplimiento saldado sin consecuencia.
            #
            # Y esto NO es una compensación por un cron poco fiable: pasa con el proceso
            # funcionando a la perfección, porque la deuda puede NACER ya vencida. El caso
            # corriente es un permiso pendiente desde hace meses que el supervisor aprueba
            # hoy: su deuda es de aquel mes, y hasta este momento no existía, así que no hay
            # revisión diaria que hubiera podido materializarla antes. Lo mismo con una
            # doblada registrada con retraso o una corrección de deuda.
            #
            # Se desplaza al presente CONSERVANDO duración y nivel: llegar tarde retrasa el
            # castigo, nunca lo abarata. La duración sigue saliendo del ledger, que es la
            # garantía que importa; lo que se pierde es la coincidencia exacta de fechas.
            inicio, fin = sancion.inicio, sancion.fin
            if fin < hoy:
                inicio = hoy
                fin = hoy + timedelta(days=sancion.duracion_dias)
            # Y si el desplazamiento la solapa con la que se acaba de crear, se encadena:
            # dos sanciones vigentes a la vez harían ambiguo cuándo termina el bloqueo.
            if ultimo_fin is not None and inicio <= ultimo_fin:
                inicio = ultimo_fin + timedelta(days=1)
                fin = inicio + timedelta(days=sancion.duracion_dias)
            ultimo_fin = fin

            supervisor = getattr(explorador, 'supervisor', None) or explorador
            reincidencia = (f' (reincidencia #{sancion.reincidencia})'
                            if sancion.reincidencia else '')
            nueva = SancionEmpleado.objects.create(
                explorador=explorador,
                supervisor=supervisor,
                fecha_inicio=inicio,
                fecha_fin=fin,
                periodo_anio=sancion.periodo.anio,
                periodo_mes=sancion.periodo.mes,
                nivel_reincidencia=sancion.nivel,
                motivo=(
                    f"{DeudaCorporativaService.AUTO_SANCION_PREFIJO} Sanción automática"
                    f"{reincidencia}: cerró {sancion.periodo.nombre()} con deuda de horas "
                    f"sin pagar. Sanción del {inicio.strftime('%d/%m/%Y')} al "
                    f"{fin.strftime('%d/%m/%Y')} ({sancion.duracion_dias} días). "
                    f"Se cumple completa aunque pagues la deuda; al terminar, lo que debías "
                    f"de ese mes queda saldado. Si vuelves a cerrar un mes debiendo, la "
                    f"siguiente será de {sancion.duracion_siguiente} días."
                ),
            )
            SancionNotificador.notificar_sancion(explorador, nueva, sancion)
            invalidar_cache_turnos(nueva)
            logger.info('Sanción automática creada para %s por %s: %s -> %s (%s días, nivel %s)',
                        explorador.id, sancion.periodo, inicio, fin,
                        sancion.duracion_dias, sancion.nivel)
            creadas += 1

        return {'creadas': creadas, 'consumidas': consumidas}

    # ------------------------------------------------------------------ auditoría
    # El plazo lo define la capa de cálculo. Se expone aquí como alias para que la auditoría
    # y las pantallas no tengan que conocer dos módulos, pero la fórmula vive en un solo
    # sitio: si divergieran, la tabla de morosos mostraría un plazo distinto del que de
    # verdad dispara la sanción.
    _fin_de_plazo = staticmethod(fin_de_plazo)

    @staticmethod
    def contar_pendientes_de_sancion() -> int:
        """
        Cuántos exploradores tienen un mes vencido que el sistema todavía no ha juzgado.

        Es exactamente lo que crearía `gestionar_sancion_por_deuda` si se la llamara ahora
        mismo para todo el mundo, y de ahí sale su utilidad: el aviso solo aparece cuando el
        botón "Aplicar sanciones" de verdad va a hacer algo. Antes contaba otra cosa —quién
        no tiene una sanción VIGENTE— y eso incluía casos que ningún botón podía resolver:
        una sanción levantada a mano dejaba el aviso encendido para siempre, invitando a
        pulsar una y otra vez algo que no cambiaba nada.

        La comparación es por MES, no por persona: quien está cumpliendo la sanción de julio
        y cierra agosto debiendo vuelve a contar, porque le falta un juicio, aunque hoy esté
        bloqueado. Y quien tiene todos sus meses juzgados no cuenta aunque ya no lo esté.

        Versión barata de `auditar_morosos` para el dashboard, que se pinta en cada visita:
        tres consultas agregadas y ninguna por explorador. Ambas deben dar el mismo número;
        si divergen, manda `auditar_morosos`, que además explica cada caso.
        """
        from empleados.models import SancionEmpleado

        hoy = timezone.localdate()
        # Deuda vencida = de un mes ANTERIOR al actual y todavía activa.
        primero_de_mes = hoy.replace(day=1)
        periodos = {
            (exp, f.year, f.month)
            for exp, f in DeudaCorporativa.objects
            .filter(estado='activa', fecha_doblada__lt=primero_de_mes)
            .values_list('explorador_id', 'fecha_doblada')
        }
        # Los permisos también sancionan, así que también cuentan aquí. Si solo se miraran
        # las dobladas, el aviso del supervisor diría "0 pendientes" mientras el sistema
        # sanciona a gente por deuda de permisos.
        from permisos.models import DeudaPermisoMes
        periodos |= {
            (exp, anio, mes)
            for exp, anio, mes in DeudaPermisoMes.objects
            .filter(estado='activa', minutos_pagados__lt=F('minutos_generados'))
            .exclude(anio__gt=primero_de_mes.year)
            .exclude(anio=primero_de_mes.year, mes__gte=primero_de_mes.month)
            .values_list('explorador_id', 'anio', 'mes')
        }
        if not periodos:
            return 0

        # Solo las AUTOMÁTICAS, y por el periodo que juzgaron. Una sanción manual del
        # supervisor bloquea a la persona hoy, pero es una vía paralela con sus propias
        # fechas: no salda la deuda ni sustituye a la automática. Contarla aquí escondería
        # al moroso del aviso mientras durase el castigo manual.
        juzgados = set(
            SancionEmpleado.objects
            .filter(DeudaCorporativaService.ES_AUTOMATICA,
                    explorador_id__in={p[0] for p in periodos})
            .values_list('explorador_id', 'periodo_anio', 'periodo_mes')
        )
        return len({p[0] for p in periodos - juzgados})

    @staticmethod
    def deuda_a_corte(corte: date) -> list[dict]:
        """
        Quién debe, del día 1 del mes de `corte` hasta `corte` incluido. NO escribe nada.

        Responde una pregunta distinta a `auditar_morosos`, y por eso es otra función. Aquélla
        mira la deuda YA VENCIDA para decidir sanciones, siempre con la vara de hoy. Ésta mira
        el mes EN CURSO, cuando todavía se está en plazo y nadie está sancionado: es el momento
        en que avisar sirve de algo. Parametrizar `auditar_morosos` con una fecha habría hecho
        que 'sancionado' y 'en plazo' significaran cosas distintas según el filtro.

        No se arrastra deuda de meses anteriores porque a estas alturas ya no existe: o se
        pagó, o la extinguió la sanción de ese mes —cumpliéndola ('consumida_por_sancion') o
        al levantarla el supervisor ('condonada').

        Devuelve una fila por explorador con saldo > 0, la mayor deuda arriba:
        {explorador, minutos, minutos_dobladas, minutos_permisos, dias, deuda_mas_antigua}.
        """
        from permisos.models import DeudaPermisoMes

        primero = corte.replace(day=1)
        por_explorador: dict[int, dict] = {}

        def _fila(explorador):
            return por_explorador.setdefault(explorador.id, {
                'explorador': explorador, 'fechas': [], 'dias': 0,
                'minutos_dobladas': 0, 'minutos_permisos': 0,
            })

        for d in (DeudaCorporativa.objects
                  .filter(estado='activa', fecha_doblada__gte=primero, fecha_doblada__lte=corte)
                  .select_related('explorador')):
            fila = _fila(d.explorador)
            fila['fechas'].append(d.fecha_doblada)
            fila['dias'] += 1
            fila['minutos_dobladas'] += d.minutos

        # El permiso permanente se guarda agregado por mes, sin desglose diario, así que aquí
        # se prorratea: solo cuentan las ocurrencias que YA cayeron a la fecha de corte. Lo que
        # aún no ha pasado todavía no se debe, y mostrar el mes entero inflaría la cifra.
        for d in (DeudaPermisoMes.objects
                  .filter(estado='activa', anio=corte.year, mes=corte.month,
                          minutos_pagados__lt=F('minutos_generados'))
                  .select_related('explorador', 'permiso')):
            ocurrencias = sum(n for _, _, n in d.permiso.ocurrencias_por_mes(hasta=corte))
            if not ocurrencias:
                continue
            minutos_por_ocurrencia = round(float(d.permiso.tiempo or 0) * 60)
            # El pago se imputa a lo más antiguo, así que se descuenta de lo ya devengado.
            pendiente = max(0, ocurrencias * minutos_por_ocurrencia - d.minutos_pagados)
            if not pendiente:
                continue
            fila = _fila(d.explorador)
            # El permiso no dice qué día concreto se debe, solo el mes; para "la más antigua"
            # se toma el día 1, que es el suelo del periodo consultado.
            fila['fechas'].append(primero)
            fila['dias'] += ocurrencias
            fila['minutos_permisos'] += pendiente

        filas = []
        for fila in por_explorador.values():
            minutos = fila['minutos_dobladas'] + fila['minutos_permisos']
            if minutos <= 0:
                continue
            filas.append({
                'explorador': fila['explorador'],
                'minutos': minutos,
                # En horas porque es la unidad en la que se paga (el PDH se registra en
                # horas): la pantalla no debería obligar a dividir entre 60 mentalmente.
                'horas': round(minutos / 60, 2),
                'minutos_dobladas': fila['minutos_dobladas'],
                'minutos_permisos': fila['minutos_permisos'],
                'dias': fila['dias'],
                'deuda_mas_antigua': min(fila['fechas']),
            })

        filas.sort(key=lambda f: (-f['minutos'], f['explorador'].id))
        return filas

    @staticmethod
    def auditar_morosos(aplicar: bool = False) -> list[dict]:
        """
        Radiografía de quién debe horas de doblada, y en qué situación está cada uno.

        Existe porque la auto-sanción es PEREZOSA: solo se calcula cuando el propio
        explorador abre una pantalla. Hasta entonces su deuda vencida no aparece en ningún
        sitio, así que el supervisor no tiene forma de verla. Esto la calcula desde fuera.

        Con `aplicar=True` además crea (o levanta) las sanciones que correspondan, que es
        exactamente lo mismo que haría el explorador al entrar. Sin él, no escribe nada:
        el diagnóstico se puede mirar sin efectos, y decidir después.

        Devuelve una fila por explorador con deuda activa, ordenadas por urgencia
        (vencidas primero, y dentro de ellas la deuda más antigua arriba).
        """
        from empleados.models import SancionEmpleado
        from empleados.sancion_utils import vigentes_en

        hoy = timezone.localdate()
        deudas = (
            DeudaCorporativa.objects
            .filter(estado='activa')
            .select_related('explorador')
            .order_by('fecha_doblada', 'id')
        )

        por_explorador: dict[int, dict] = {}
        for d in deudas:
            fila = por_explorador.setdefault(d.explorador_id, {
                'explorador': d.explorador, 'fechas': [], 'minutos': 0,
                'minutos_permisos': 0,
            })
            fila['fechas'].append(d.fecha_doblada)
            fila['minutos'] += d.minutos

        # La deuda de permisos entra en la misma tabla: es exigible y sanciona igual, así
        # que un supervisor que solo viera las dobladas no entendería por qué el sistema
        # sanciona a alguien que, según su pantalla, no debe nada. Se le asigna como fecha
        # el último día de su mes, que es cuando vence.
        from permisos.models import DeudaPermisoMes
        permisos_deuda = (
            DeudaPermisoMes.objects
            .filter(estado='activa', minutos_pagados__lt=F('minutos_generados'))
            .select_related('explorador')
        )
        for d in permisos_deuda:
            fila = por_explorador.setdefault(d.explorador_id, {
                'explorador': d.explorador, 'fechas': [], 'minutos': 0,
                'minutos_permisos': 0,
            })
            fila['fechas'].append(d.periodo.fin_de_plazo())
            fila['minutos'] += d.minutos_pendientes
            fila['minutos_permisos'] += d.minutos_pendientes

        filas = []
        for fila in por_explorador.values():
            explorador = fila['explorador']
            # Vencida = de un mes ANTERIOR al actual. Mismo criterio que
            # `_periodos_con_deuda`; se recalcula aquí sobre las fechas ya cargadas para no
            # repetir una consulta por explorador, pero la regla es la misma y no debe
            # divergir.
            vencidas = [f for f in fila['fechas']
                        if (f.year, f.month) < (hoy.year, hoy.month)]

            if aplicar:
                DeudaCorporativaService.gestionar_sancion_por_deuda(explorador)
            # Solo la AUTOMÁTICA decide el estado, igual que en `contar_pendientes_de_sancion`:
            # una sanción manual del supervisor bloquea hoy pero no salda la deuda, y si la
            # contáramos aquí el moroso desaparecería de la lista mientras dure el castigo manual.
            sancion = (
                SancionEmpleado.objects
                .filter(vigentes_en(hoy), DeudaCorporativaService.ES_AUTOMATICA,
                        explorador=explorador)
                .order_by('-fecha_inicio')
                .first()
            )
            # La manual se muestra igualmente en la tabla: el supervisor debe saber que la
            # persona ya está bloqueada por otra razón antes de decidir nada.
            sancion_manual = (
                SancionEmpleado.objects
                .filter(vigentes_en(hoy), DeudaCorporativaService.ES_MANUAL,
                        explorador=explorador)
                .order_by('-fecha_inicio')
                .first()
            )

            # Un mes vencido que el sistema aún no ha juzgado es lo único que el botón
            # "Aplicar sanciones" puede resolver. Lo demás ya tiene una decisión detrás.
            sin_juzgar = ({(f.year, f.month) for f in vencidas}
                          - DeudaCorporativaService._periodos_ya_evaluados(explorador))

            mas_antigua = min(fila['fechas'])
            if not vencidas:
                estado = 'en_plazo'
            elif sin_juzgar:
                # Un mes vencido sin juzgar manda sobre todo lo demás, INCLUSO si ahora mismo
                # está cumpliendo la sanción de otro mes: son juicios independientes y el de
                # este mes falta. Preguntar antes "¿está sancionado?" lo escondía del aviso
                # mientras durase el castigo anterior, que es cuando más fácil es acumular
                # otro mes impago.
                estado = 'pendiente'
            elif sancion:
                estado = 'sancionado'
            else:
                # Se evaluó, se sancionó, y el supervisor levantó el castigo: una decisión
                # tomada, no un pendiente. Mezclarla con los pendientes dejaba un aviso
                # encendido para siempre que ninguna acción apagaba, y con el texto
                # exactamente al revés de lo ocurrido.
                #
                # Desde que levantar CONDONA la deuda del mes, esta rama solo la alcanzan
                # las levantadas anteriores a ese cambio (cuya deuda quedó activa) o una
                # deuda de otro mes que aún no ha vencido. Se conserva por eso: retirarla
                # devolvería esas filas al montón de 'pendiente', con un botón de aplicar
                # que no puede hacer nada.
                estado = 'levantada'
                sancion = (
                    SancionEmpleado.objects
                    .filter(DeudaCorporativaService.ES_AUTOMATICA,
                            explorador=explorador, levantada_en__isnull=False)
                    .order_by('-levantada_en', '-fecha_inicio')
                    .first()
                )

            filas.append({
                'explorador': explorador,
                'minutos': fila['minutos'],
                'minutos_permisos': fila['minutos_permisos'],
                'dias': len(fila['fechas']),
                'vencidas': sorted(vencidas),
                'deuda_mas_antigua': mas_antigua,
                'plazo_hasta': DeudaCorporativaService._fin_de_plazo(mas_antigua),
                'sancion': sancion,
                'sancion_manual': sancion_manual,
                'estado': estado,
            })

        orden = {'pendiente': 0, 'sancionado': 1, 'levantada': 2, 'en_plazo': 3}
        filas.sort(key=lambda f: (orden[f['estado']], f['deuda_mas_antigua']))
        return filas

    @staticmethod
    def revisar_todos() -> dict:
        """
        CAPA 2 — Pasa la revisión a TODOS los exploradores implicados y devuelve el resumen.

        "Implicados" son dos grupos, y hacen falta los dos: quien tiene deuda activa (puede
        haber que sancionarlo) y quien tiene una sanción automática vigente pero ya NO debe
        nada (hay que levantársela). El segundo grupo se escapa si solo se recorre el
        primero, porque pagar es justamente lo que te saca de él.

        Devuelve {'creadas': int, 'consumidas': int, 'detalle': str} para que el comando
        pueda dejar constancia de lo que hizo en `RevisionSancionesDeuda`.
        """
        from empleados.models import Empleado, SancionEmpleado
        from permisos.models import DeudaPermisoMes

        ids = set(
            DeudaCorporativa.objects.filter(estado='activa')
            .values_list('explorador_id', flat=True)
        )
        ids |= set(
            DeudaPermisoMes.objects.filter(estado='activa')
            .values_list('explorador_id', flat=True)
        )
        # Los ya sancionados, para consumirles la deuda en cuanto cumplan. Aquí NO se filtra
        # por vigencia: son justamente las sanciones ya terminadas las que interesan.
        ids |= set(
            SancionEmpleado.objects
            .filter(DeudaCorporativaService.ES_AUTOMATICA)
            .values_list('explorador_id', flat=True)
        )

        creadas, consumidas, lineas = 0, 0, []
        for explorador in Empleado.objects.filter(id__in=ids).select_related('supervisor'):
            try:
                resultado = DeudaCorporativaService.gestionar_sancion_por_deuda(explorador)
            except Exception:
                # Un explorador con datos raros no puede impedir que se revise el resto:
                # si la excepción subiera, los que quedan detrás se quedarían sin revisar
                # hasta mañana. Se registra y se sigue.
                logger.exception('Error revisando la sanción por deuda de %s', explorador.id)
                lineas.append(f'  ! {explorador.nombre} {explorador.apellido}: error, ver logs')
                continue

            if resultado['creadas']:
                creadas += resultado['creadas']
                lineas.append(f'  + sancionado: {explorador.nombre} {explorador.apellido}')
            if resultado['consumidas']:
                consumidas += resultado['consumidas']
                lineas.append(f'  · deuda saldada al cumplir la sanción: '
                              f'{explorador.nombre} {explorador.apellido}')

        logger.info('Revisión de sanciones por deuda: %s creada(s), %s deuda(s) consumida(s) '
                    'sobre %s explorador(es).', creadas, consumidas, len(ids))
        return {'creadas': creadas, 'consumidas': consumidas, 'detalle': '\n'.join(lineas)}



    



    
    
