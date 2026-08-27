"""
Errores de validación que llevan datos, no solo texto.

Casi todos los rechazos de `validar_solicitud` son una frase para el usuario. Uno
no: cuando la doblada se bloquea porque ambos tienen la misma jornada, el
formulario necesita además la fecha de pago y la jornada en común para pintar el
recuadro con el botón «Ir a Cambio de Turno Sencillo».

CÓMO ESTABA Y POR QUÉ SE CAMBIÓ
Ese dato extra viajaba metiendo un JSON dentro del mensaje: tres `json.dumps` en
`doblada_strategy` y, arriba, un `json.loads` para deshacerlo. La forma del
diccionario —`code`, `message`, `fecha_pago`, `jornada_comun`— estaba escrita tres
veces sin una definición única, y eso ya costó un fallo real: un refactor renombró
la clave `fecha_pago` en dos de los tres sitios y nadie se enteró, porque el
frontend hacía `data.fecha_pago || valorDelFormulario` y el `||` tapaba la avería.
Ningún test miraba esa clave y el CI pasó en verde.

Había además un segundo lector aún más frágil, que decidía si un mensaje era JSON
mirando **si contenía una llave `{`**: cualquier frase con una llave habría entrado
por esa rama sin querer.

Aquí la forma se define UNA vez, quien la produce no escribe claves a mano y quien
la consume la reconoce con `isinstance`.

POR QUÉ HEREDA DE `str`
El mensaje viaja por sitios que lo tratan como texto: se le antepone el nombre del
compañero en el alta multi-compañero, se registra en logs, y otras vistas
inspeccionan el contenido de mensajes de validación. Siendo `str`, todo eso sigue
funcionando sin tocar nada. Lo que cambia es que ahora, además, lleva los datos
colgados y se puede reconocer sin adivinar.

Como efecto secundario el mensaje pasa a ser legible: antes en los logs aparecía un
blob JSON, ahora la frase que lee el usuario.
"""


class RequiereCambioTurnoPrevio(str):
    """
    Rechazo de doblada que el formulario debe convertir en «Ir a CT Sencillo».

    Se usa como un mensaje normal —porque lo es— y además expone `fecha_pago` y
    `jornada_comun` para construir la respuesta.
    """

    CODE = 'requiere_cambio_turno_previo'

    def __new__(cls, mensaje: str, *, fecha_pago, jornada_comun: str):
        obj = super().__new__(cls, mensaje)
        # `str(...)` porque llega indistintamente como `date` o como texto ya
        # formateado, y la respuesta JSON siempre lo envía como cadena.
        obj.fecha_pago = str(fecha_pago)
        obj.jornada_comun = jornada_comun
        return obj

    def como_payload(self) -> dict:
        """
        El cuerpo JSON que espera el formulario. Las claves se escriben AQUÍ y en
        ningún otro sitio: `solicitar_doblada.js` lee `code`, `message`,
        `fecha_pago` y `jornada_comun`, y cambiar cualquiera de ellas rompe la
        pantalla sin que el servidor dé error.
        """
        return {
            'success': False,
            'code': self.CODE,
            'message': str(self),
            'fecha_pago': self.fecha_pago,
            'jornada_comun': self.jornada_comun,
        }


class ErrorDelCompanero(str):
    """
    Rechazo que habla del COMPAÑERO, no de quien envía la solicitud.

    El alta multi-compañero de la doblada permanente valida una vez por compañero y antepone su
    nombre al mensaje, porque con varios en el mismo formulario no se sabría cuál falló. El
    problema es que lo anteponía a TODOS los rechazos: "Ya tienes una solicitud pendiente" —que
    habla del solicitante— salía como "Isabel Parra: Ya tienes una solicitud pendiente", y el
    usuario cancelaba la solicitud de Isabel buscando un choque que era suyo.

    Con este marcador el nombre solo se antepone a lo que de verdad es del compañero. La decisión
    la toma quien valida, que es el único que sabe de quién habla cada frase; no se adivina
    leyendo el texto —el mismo error de bulto que documenta `RequiereCambioTurnoPrevio`—.

    Hereda de `str` por lo mismo: viaja por logs y respuestas que lo tratan como texto.
    """
