"""Tokens de los enlaces de aprobación por correo.

Estos enlaces aprueban SIN sesión iniciada: el token es la única credencial. Lo
que se prueba aquí es justo lo que antes no se cumplía — la firma depende de
SECRET_KEY, el enlace caduca, y un token no sirve para otra solicitud, otro rol
ni otra persona.
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings

from solicitudes.services import tokens_aprobacion


class TokenFalso:
    """Solicitud mínima: solo lo que mira el verificador."""

    class _Empleado:
        def __init__(self, id_):
            self.id = id_

    class _Solicitante:
        def __init__(self, supervisor_id):
            self.supervisor = (
                TokenFalso._Empleado(supervisor_id) if supervisor_id else None
            )

    def __init__(self, id_=1, supervisor_id=10, receptor_id=20):
        self.id = id_
        self.explorador_solicitante = TokenFalso._Solicitante(supervisor_id)
        self.explorador_receptor = (
            TokenFalso._Empleado(receptor_id) if receptor_id else None
        )


class GenerarYVerificarTests(TestCase):
    def test_token_recien_emitido_es_valido(self):
        s = TokenFalso()
        t = tokens_aprobacion.generar(s.id, 10, 'supervisor')
        self.assertTrue(tokens_aprobacion.verificar(s, t, 'supervisor'))

    def test_token_de_receptor_tambien(self):
        s = TokenFalso()
        t = tokens_aprobacion.generar(s.id, 20, 'receptor')
        self.assertTrue(tokens_aprobacion.verificar(s, t, 'receptor'))

    def test_el_token_no_lleva_la_clave_en_claro(self):
        t = tokens_aprobacion.generar(1, 10, 'supervisor')
        self.assertNotIn('secret_key_change_this', t)


class NoSePuedeFabricarTests(TestCase):
    """El agujero original: la clave estaba en el código, cualquiera firmaba."""

    def test_token_inventado_se_rechaza(self):
        s = TokenFalso()
        self.assertFalse(tokens_aprobacion.verificar(s, 'a' * 64, 'supervisor'))

    def test_token_firmado_con_la_clave_antigua_se_rechaza(self):
        """Un enlace emitido por la versión vulnerable ya no vale."""
        import hashlib
        import hmac

        data = "1_10_supervisor"
        viejo = hmac.new(
            b'secret_key_change_this', data.encode(), hashlib.sha256
        ).hexdigest()
        self.assertFalse(tokens_aprobacion.verificar(TokenFalso(), viejo, 'supervisor'))

    def test_token_manipulado_se_rechaza(self):
        s = TokenFalso()
        t = tokens_aprobacion.generar(s.id, 10, 'supervisor')
        manipulado = t[:-1] + ('x' if t[-1] != 'x' else 'y')
        self.assertFalse(tokens_aprobacion.verificar(s, manipulado, 'supervisor'))

    @override_settings(SECRET_KEY='otra-clave-distinta-para-la-prueba')
    def test_con_otra_secret_key_no_valida(self):
        """Si cada instancia de AWS tuviera su SECRET_KEY, esto pasaría en producción."""
        s = TokenFalso()
        t = tokens_aprobacion.generar(s.id, 10, 'supervisor')
        with override_settings(SECRET_KEY='clave-de-la-otra-instancia'):
            self.assertFalse(tokens_aprobacion.verificar(s, t, 'supervisor'))

    def test_token_vacio_o_none(self):
        s = TokenFalso()
        self.assertFalse(tokens_aprobacion.verificar(s, '', 'supervisor'))
        self.assertFalse(tokens_aprobacion.verificar(s, None, 'supervisor'))


class NoSirveParaOtraCosaTests(TestCase):
    def test_token_de_otra_solicitud(self):
        t = tokens_aprobacion.generar(999, 10, 'supervisor')
        self.assertFalse(tokens_aprobacion.verificar(TokenFalso(id_=1), t, 'supervisor'))

    def test_token_de_supervisor_no_vale_como_receptor(self):
        s = TokenFalso()
        t = tokens_aprobacion.generar(s.id, 10, 'supervisor')
        self.assertFalse(tokens_aprobacion.verificar(s, t, 'receptor'))

    def test_token_de_otra_persona(self):
        """Un explorador no aprueba con el enlace de otro."""
        s = TokenFalso(supervisor_id=10)
        t = tokens_aprobacion.generar(s.id, 77, 'supervisor')
        self.assertFalse(tokens_aprobacion.verificar(s, t, 'supervisor'))

    def test_si_cambia_el_supervisor_el_enlace_anterior_muere(self):
        t = tokens_aprobacion.generar(1, 10, 'supervisor')
        nueva = TokenFalso(id_=1, supervisor_id=55)  # le cambiaron de supervisor
        self.assertFalse(tokens_aprobacion.verificar(nueva, t, 'supervisor'))

    def test_sin_supervisor_no_valida(self):
        s = TokenFalso(supervisor_id=None)
        t = tokens_aprobacion.generar(1, 10, 'supervisor')
        self.assertFalse(tokens_aprobacion.verificar(s, t, 'supervisor'))

    def test_tipo_desconocido(self):
        s = TokenFalso()
        t = tokens_aprobacion.generar(s.id, 10, 'supervisor')
        self.assertFalse(tokens_aprobacion.verificar(s, t, 'administrador'))
        with self.assertRaises(ValueError):
            tokens_aprobacion.generar(1, 10, 'administrador')


class CaducidadTests(TestCase):
    @override_settings(APPROVAL_LINK_MAX_AGE_DAYS=30)
    def test_dentro_del_plazo_vale(self):
        s = TokenFalso()
        t = tokens_aprobacion.generar(s.id, 10, 'supervisor')
        futuro = tokens_aprobacion.signing.time.time() + timedelta(days=29).total_seconds()
        with mock.patch('django.core.signing.time.time', return_value=futuro):
            self.assertTrue(tokens_aprobacion.verificar(s, t, 'supervisor'))

    @override_settings(APPROVAL_LINK_MAX_AGE_DAYS=30)
    def test_pasado_el_plazo_caduca(self):
        s = TokenFalso()
        t = tokens_aprobacion.generar(s.id, 10, 'supervisor')
        futuro = tokens_aprobacion.signing.time.time() + timedelta(days=31).total_seconds()
        with mock.patch('django.core.signing.time.time', return_value=futuro):
            self.assertFalse(tokens_aprobacion.verificar(s, t, 'supervisor'))

    @override_settings(APPROVAL_LINK_MAX_AGE_DAYS=1)
    def test_el_plazo_es_configurable(self):
        s = TokenFalso()
        t = tokens_aprobacion.generar(s.id, 10, 'supervisor')
        futuro = tokens_aprobacion.signing.time.time() + timedelta(days=2).total_seconds()
        with mock.patch('django.core.signing.time.time', return_value=futuro):
            self.assertFalse(tokens_aprobacion.verificar(s, t, 'supervisor'))


class PermisoFalso:
    """Permiso mínimo: solo lo que mira el verificador."""

    class _Empleado:
        def __init__(self, supervisor_id):
            self.supervisor = (
                TokenFalso._Empleado(supervisor_id) if supervisor_id else None
            )

    def __init__(self, id_=5, supervisor_id=10):
        self.id = id_
        self.empleado = PermisoFalso._Empleado(supervisor_id)


class TokensDePermisoTests(TestCase):
    """Los permisos especiales tenían la misma clave escrita en el código."""

    def test_token_valido(self):
        p = PermisoFalso()
        t = tokens_aprobacion.generar_permiso(p.id, 10)
        self.assertTrue(tokens_aprobacion.verificar_permiso(p, t))

    def test_token_inventado_se_rechaza(self):
        self.assertFalse(tokens_aprobacion.verificar_permiso(PermisoFalso(), 'a' * 64))

    def test_token_de_otro_permiso(self):
        t = tokens_aprobacion.generar_permiso(999, 10)
        self.assertFalse(tokens_aprobacion.verificar_permiso(PermisoFalso(id_=5), t))

    def test_token_de_otro_supervisor(self):
        t = tokens_aprobacion.generar_permiso(5, 77)
        self.assertFalse(tokens_aprobacion.verificar_permiso(PermisoFalso(supervisor_id=10), t))

    def test_sin_supervisor(self):
        p = PermisoFalso(supervisor_id=None)
        t = tokens_aprobacion.generar_permiso(5, 10)
        self.assertFalse(tokens_aprobacion.verificar_permiso(p, t))

    def test_un_token_de_solicitud_no_vale_como_permiso(self):
        """Sales distintas: no se pueden cruzar los dos circuitos."""
        t = tokens_aprobacion.generar(5, 10, 'supervisor')
        self.assertFalse(tokens_aprobacion.verificar_permiso(PermisoFalso(), t))

    def test_un_token_de_permiso_no_vale_como_solicitud(self):
        t = tokens_aprobacion.generar_permiso(1, 10)
        self.assertFalse(tokens_aprobacion.verificar(TokenFalso(), t, 'supervisor'))

    @override_settings(APPROVAL_LINK_MAX_AGE_DAYS=30)
    def test_caduca(self):
        p = PermisoFalso()
        t = tokens_aprobacion.generar_permiso(p.id, 10)
        futuro = tokens_aprobacion.signing.time.time() + timedelta(days=31).total_seconds()
        with mock.patch('django.core.signing.time.time', return_value=futuro):
            self.assertFalse(tokens_aprobacion.verificar_permiso(p, t))
