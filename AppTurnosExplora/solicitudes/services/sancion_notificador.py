"""Avisos al explorador sobre sus sanciones por deuda: nueva sanción y condonación.

Extraído de `DeudaCorporativaService`. Estaba mezclado con el cálculo de la sanción y su
persistencia, de modo que retocar el TEXTO de un aviso —cambiar una fecha de sitio, suavizar
una frase— obligaba a abrir el mismo archivo donde se decide a quién se sanciona y por
cuántos días. Son dos motivos de cambio distintos y ahora viven separados.

Las dos funciones tragan sus excepciones a propósito: que falle un aviso no puede tumbar la
sanción ni la condonación, que ya están grabadas cuando se llama aquí.
"""
import logging

logger = logging.getLogger(__name__)


class SancionNotificador:
    """Notificaciones de sanción por deuda. Nunca propaga errores al flujo que la invoca."""

    @staticmethod
    def notificar_condonacion(sancion, horas: float) -> None:
        """
        Avisa al explorador de que le levantaron la sanción y, si las hubo, le perdonaron
        las horas de ese mes.

        Se le avisa a él y no solo al supervisor porque es un hecho irreversible que le
        cambia el saldo: sin esto, el afectado solo podía enterarse entrando por su cuenta
        al Consolidado de Horas. Va por la campana y no por correo, como el aviso de la
        propia sanción, para que las dos mitades de la misma historia lleguen por el mismo
        sitio.

        Es pública —sin guion bajo— porque la llama `SancionEmpleado.levantar()`, que vive
        en otra aplicación. Marcarla como privada invitaría a moverla o renombrarla
        creyéndola interna, y el aviso desaparecería sin que nada fallara.

        Nunca lanza, igual que `_notificar_sancion`: un fallo avisando no puede tumbar un
        levantamiento ya decidido. Ese `try` es además lo que hace seguro llamarla DENTRO
        de la transacción del levantamiento —quitarlo haría que un error creando la
        notificación revirtiera el levantamiento entero—, así que no se retira sin mover
        antes la llamada fuera de la transacción.
        """
        try:
            from solicitudes.models import Notificacion

            desde = sancion.levantada_en.strftime('%d/%m/%Y')
            if horas:
                titulo = f'✅ Sanción levantada y {horas} h condonadas'
                cuerpo = (
                    f'Tu supervisor levantó la sanción el {desde}. Ya puedes volver a '
                    f'realizar solicitudes de cambio de turno y permisos.\n\n'
                    f'Además se te condonaron las {horas} h que debías de ese mes: dejan '
                    f'de figurar como pendientes en tu Consolidado de Horas y nadie te las '
                    f'va a reclamar.\n\n'
                    f'La sanción sigue en tu historial y cuenta como antecedente: si '
                    f'vuelves a cerrar un mes debiendo, la siguiente será más larga.'
                )
            else:
                titulo = '✅ Sanción levantada'
                cuerpo = (
                    f'Tu supervisor levantó la sanción el {desde}. Ya puedes volver a '
                    f'realizar solicitudes de cambio de turno y permisos.\n\n'
                    f'La sanción sigue en tu historial y cuenta como antecedente.'
                )
            if sancion.levantada_motivo:
                cuerpo += f'\n\nMotivo indicado: {sancion.levantada_motivo}'

            Notificacion.objects.create(
                destinatario=sancion.explorador,
                tipo='sancion_levantada',
                titulo=titulo,
                mensaje=cuerpo,
                solicitud=None,
            )
        except Exception:
            logger.warning('Error creando la notificación de levantamiento de la sanción %s',
                           getattr(sancion, 'id', '?'), exc_info=True)

    @staticmethod
    def notificar_sancion(explorador, sancion, ventana) -> None:
        """
        Avisa al explorador de su nueva sanción.

        La notificación nace cuando se MATERIALIZA el registro, y con el cálculo derivado eso
        puede ocurrir después del inicio de la ventana (el sistema se enteró tarde). Por eso
        el texto dice explícitamente desde cuándo rige: si empezó hace días, la persona tiene
        que poder leerlo, no deducirlo.
        """
        try:
            from solicitudes.models import Notificacion
            dias = ventana.duracion_dias
            mes = ventana.periodo.nombre()
            if ventana.reincidencia == 0:
                titulo = f"⚠️ Sanción automática: {dias} días bloqueado"
                intro = (f"Cerraste {mes} debiendo horas y no las pagaste dentro del mes, "
                         f"que es el plazo que había.")
            else:
                titulo = (f"⚠️ Sanción ampliada: {dias} días bloqueados "
                          f"(reincidencia #{ventana.reincidencia})")
                intro = (f"Has vuelto a cerrar un mes debiendo horas: {mes}. "
                         f"Esta es la reincidencia #{ventana.reincidencia}.")
            Notificacion.objects.create(
                destinatario=explorador,
                tipo='sancion',
                titulo=titulo,
                mensaje=(
                    f"{intro}\n\n"
                    f"Rige desde el {ventana.inicio.strftime('%d/%m/%Y')} "
                    f"hasta el {ventana.fin.strftime('%d/%m/%Y')} ({dias} días).\n\n"
                    f"Durante este período NO puedes realizar solicitudes de cambio de turno ni permisos. "
                    f"La sanción se cumple completa: pagar la deuda ahora no la levanta ni la "
                    f"acorta. Al terminar, lo que debías de {mes} queda saldado por la propia "
                    f"sanción. Si vuelves a cerrar un mes debiendo, la siguiente será de "
                    f"{ventana.duracion_siguiente} días."
                ),
                solicitud=None,
            )
        except Exception:
            logger.warning("Error creando notificación de sanción por deuda", exc_info=True)
