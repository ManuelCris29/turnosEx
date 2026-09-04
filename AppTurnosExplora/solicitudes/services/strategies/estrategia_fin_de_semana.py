"""
El contrato del selector de compañeros de FIN DE SEMANA.

QUÉ RESUELVE
------------
`disponibilidad_companero` y `etiqueta_companero` contestan a una pregunta que solo
existe en los dos formularios de fin de semana: «¿puede este compañero participar en
un cambio sobre este sábado o domingo, y por qué?». Las usa un único sitio,
`views/api_fin_semana.py`, y solo tienen sentido para CAMBIO DESCANSO y D FDS.

Vivían en `SolicitudStrategy`, la base de las SEIS estrategias, y con la regla del
INTERCAMBIO como comportamiento por defecto. Eso tenía dos consecuencias malas:

  1. La base tomaba partido por un subtipo. D FDS —cuya regla es la de la CESIÓN—
     tenía que sobrescribirla para contradecir a su propia base, y quien leía la base
     no podía saber que ese "por defecto" era en realidad la regla de otro formulario.

  2. Las otras cuatro estrategias (CT, DOBLADA, CT PERMANENTE, DOBLADA PERMANENTE)
     heredaban una respuesta a una pregunta que no les corresponde. Y el endpoint
     acepta `?tipo_solicitud_id=` de CUALQUIER tipo: pidiéndole los compañeros de un
     sábado con el id de DOBLADA, contestaba aplicando la regla del intercambio. No
     fallaba: devolvía una lista verosímil y sin sentido, en silencio.

Con este mixin, cada regla vive en el formulario que la usa y las otras cuatro
estrategias dejan de poder contestar. El endpoint lo comprueba con `isinstance` y
responde un error claro en vez de una lista inventada.

POR QUÉ UN MIXIN Y NO PARTIR `SolicitudStrategy` EN DOS
--------------------------------------------------------
La auditoría proponía separar el contrato en `ISolicitudCicloVida` e
`ISolicitudPantalla`. Medido, esa división no separa nada: las seis estrategias
implementan métodos de ambos lados —las seis tienen `validar_solicitud`,
`crear_solicitud` y `aplicar_cambios`, y las seis tienen `get_empleados_disponibles`
y `detalle`—. Dos interfaces que siempre se implementan juntas son una sola con más
ceremonia.

Lo que sí estaba mal repartido eran exactamente estos dos métodos: los únicos que
pertenecen a 2 de 6, y los únicos que obligaban a una estrategia a contradecir a su
base.
"""
from abc import abstractmethod
from typing import Optional, Tuple

from empleados.models import Empleado


class EstrategiaFinDeSemana:
    """
    Lo implementan las estrategias que aparecen en el selector de fin de semana.

    No hereda de `ABC` a propósito: se combina con `SolicitudStrategy`, que ya lo es,
    y sus `@abstractmethod` se hacen valer igual a través de esa metaclase.
    """

    @abstractmethod
    def disponibilidad_companero(self, candidato: Empleado, fecha_cesion) -> Tuple[bool, Optional[str]]:
        """
        ¿Puede este compañero participar en un cambio de fin de semana sobre `fecha_cesion`?

        Devuelve `(disponible, motivo)`. El motivo se muestra en el formulario cuando no
        lo está: no se esconde a nadie de la lista, se explica por qué no puede.

        Cada formulario tiene su regla y por eso no hay implementación por defecto: el
        INTERCAMBIO (CAMBIO DESCANSO) necesita que el compañero trabaje el OTRO día del
        finde para poder canjearlo; la CESIÓN (D FDS) solo necesita que tenga libre el
        día que recibe.
        """

    @abstractmethod
    def etiqueta_companero(self, candidato: Empleado, fecha_cesion) -> str:
        """
        Texto que describe a un compañero DISPONIBLE en el selector.

        Va pegado a `disponibilidad_companero`: dice POR QUÉ ese compañero sirve, así que
        depende de la misma regla. Antes el texto se armaba en la vista desde el
        calendario ("trabaja <el otro día del finde>"), igual para todos; con el
        intercambio era cierto por construcción, pero al abrir la cesión a cualquiera que
        descanse ese día pasó a afirmar cosas falsas —"trabaja sábado 08/08" de alguien
        que ese sábado descansa—.
        """
