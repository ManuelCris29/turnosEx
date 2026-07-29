"""
Checklist de APERTURA DE AÑO: los procesos que el supervisor debe dejar listos antes de
que empiece el año siguiente.

Todo lo que hay aquí se DERIVA de los datos reales. No existe un campo "ya lo hice": si lo
hubiera, se podría marcar sin haberlo hecho y el checklist dejaría de significar nada. La
consecuencia práctica es que un ítem se pone en verde solo, en cuanto el supervisor guarda
en la pantalla correspondiente.

Los cinco procesos y su orden importan: la alternancia de findes y festivos depende de que
los festivos del año existan (si no, sus fechas no se pueden publicar), y los descansos de
semana dependen de las temporadas.

El ítem de alternancia es el único que exige cobertura COMPLETA en vez de "al menos un
registro": es lo que garantiza que ningún explorador vea un día `sin_planificar`.
"""
from dataclasses import dataclass, field
from datetime import date

from django.urls import reverse

from turnos.models import AperturaAnioConfig, DescansoSemanaManual, DiaEspecial
from turnos.services.asignacion_especial_service import AsignacionEspecialService


@dataclass
class ItemChecklist:
    clave: str
    titulo: str
    descripcion: str
    completo: bool
    detalle: str
    url: str
    # Ítems que deben estar completos antes de poder trabajar en este.
    depende_de: tuple = field(default_factory=tuple)

    @property
    def bloqueado_por_dependencia(self):
        return False  # lo resuelve el servicio al construir la lista


class AperturaAnioService:

    @staticmethod
    def anio_objetivo(hoy=None):
        """El año que hay que dejar planificado: siempre el siguiente al corriente."""
        hoy = hoy or date.today()
        return hoy.year + 1

    @staticmethod
    def estado(anio) -> list:
        """Los 5 ítems del checklist con su completitud, en orden de dependencia."""
        festivos = DiaEspecial.objects.filter(
            fecha__year=anio, tipo='festivo', activo=True).count()
        mantenimiento = DiaEspecial.objects.filter(
            fecha__year=anio, tipo='mantenimiento', activo=True).count()
        temporadas = DiaEspecial.objects.filter(
            fecha__year=anio, es_temporada=True, activo=True).count()
        descansos = DescansoSemanaManual.objects.filter(
            fecha__year=anio, motivo='temporada', activo=True).count()
        faltan_alternancia = len(AsignacionEspecialService.fechas_sin_planificar(anio))

        url_dias = reverse('dias_especiales_festivos_mantenimiento_anual')
        return [
            ItemChecklist(
                clave='festivos', titulo=f'Festivos {anio}',
                descripcion='Días festivos del año. Son la base de la alternancia de festivos.',
                completo=festivos > 0,
                detalle=f'{festivos} festivo(s) cargados' if festivos else 'ninguno cargado',
                url=f'{url_dias}?tipo=festivo&anio={anio}',
            ),
            ItemChecklist(
                clave='mantenimiento', titulo=f'Mantenimiento {anio}',
                descripcion='Lunes de mantenimiento en que descansan ambos grupos.',
                completo=mantenimiento > 0,
                detalle=f'{mantenimiento} día(s) cargados' if mantenimiento else 'ninguno cargado',
                url=f'{url_dias}?tipo=mantenimiento&anio={anio}',
            ),
            ItemChecklist(
                clave='temporadas', titulo=f'Temporadas {anio}',
                descripcion='Semanas de temporada alta, que definen los descansos entre semana.',
                completo=temporadas > 0,
                detalle=f'{temporadas} día(s) de temporada' if temporadas else 'ninguna cargada',
                url=f"{reverse('dias_especiales_temporadas_anual')}?anio={anio}",
            ),
            ItemChecklist(
                clave='descansos_semana', titulo=f'Descansos de semana {anio}',
                descripcion='Qué grupo descansa cada día de las semanas de temporada.',
                completo=descansos > 0,
                detalle=f'{descansos} descanso(s) programados' if descansos else 'ninguno programado',
                url=f"{reverse('descanso_semana_anual')}?anio={anio}",
                depende_de=('temporadas',),
            ),
            ItemChecklist(
                clave='alternancia', titulo=f'Fines de semana y festivos {anio}',
                descripcion='Qué grupo trabaja cada sábado, domingo y festivo. Debe quedar COMPLETO: '
                            'los días sin publicar salen como "sin planificar" en Mis Turnos.',
                completo=faltan_alternancia == 0,
                detalle=('año completo' if faltan_alternancia == 0
                         else f'faltan {faltan_alternancia} día(s)'),
                url=f"{reverse('asignacion_especial_anual')}?anio={anio}",
                depende_de=('festivos',),
            ),
        ]

    @staticmethod
    def completo(anio) -> bool:
        return all(i.completo for i in AperturaAnioService.estado(anio))

    @staticmethod
    def pendientes(anio) -> list:
        return [i for i in AperturaAnioService.estado(anio) if not i.completo]

    @staticmethod
    def situacion(hoy=None, cfg=None):
        """
        Qué toca hoy respecto de la apertura del año siguiente:
          'nada'      → aún no es época, o ya está todo listo.
          'aviso'     → hay que recordarlo (banner), pero se navega con normalidad.
          'bloqueo'   → hay que bloquear al supervisor hasta que lo complete.

        Devuelve (situacion, anio_objetivo).
        """
        hoy = hoy or date.today()
        cfg = cfg or AperturaAnioConfig.obtener()
        anio = AperturaAnioService.anio_objetivo(hoy)

        if AperturaAnioService.completo(anio):
            return 'nada', anio
        if cfg.bloqueo_duro and hoy >= cfg.fecha_bloqueo(hoy.year):
            return 'bloqueo', anio
        if hoy >= cfg.fecha_recordatorio(hoy.year):
            return 'aviso', anio
        return 'nada', anio
