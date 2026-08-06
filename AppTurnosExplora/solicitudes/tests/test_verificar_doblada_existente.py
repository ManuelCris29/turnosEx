"""
Tests para VerificarDobladaExistenteView
Específicamente para validar que el descanso por DOBLADA aprobada tiene prioridad sobre la regla de sábado
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from empleados.models import Empleado, Jornada
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio, DobladaDetalle
from turnos.models import Turno, DiaEspecial, AsignarJornadaExplorador, Sala
from datetime import date
import json


class VerificarDobladaExistenteTest(TestCase):
    """Tests para VerificarDobladaExistenteView"""
    
    def setUp(self):
        """Configuración inicial para los tests"""
        self.client = Client()
        
        # Crear usuarios y empleados
        self.user_jeison = User.objects.create_user(
            username='jeison.mora',
            password='test123'
        )
        self.jeison = Empleado.objects.create(
            user=self.user_jeison,
            nombre='Jeison',
            apellido='Mora',
            cedula='1234567890',
            activo=True
        )
        
        self.user_marco = User.objects.create_user(
            username='marco.castillo',
            password='test123'
        )
        self.marco = Empleado.objects.create(
            user=self.user_marco,
            nombre='Marco',
            apellido='Castillo',
            cedula='0987654321',
            activo=True
        )
        
        # Crear tipo de cambio DOBLADA
        self.tipo_doblada = TipoSolicitudCambio.objects.create(
            nombre='DOBLADA'
        )
        
        # Crear jornadas
        self.jornada_am = Jornada.objects.create(
            nombre='AM',
            hora_inicio='06:00:00',
            hora_fin='14:00:00'
        )
        self.jornada_pm = Jornada.objects.create(
            nombre='PM',
            hora_inicio='14:00:00',
            hora_fin='22:00:00'
        )

        # Sala requerida por la FK NOT NULL de Turno
        self.sala = Sala.objects.create(nombre='Sala Test', activo=True)

        # Fecha de prueba: 14 de febrero de 2026 (sábado)
        self.fecha_test = date(2026, 2, 14)
    
    def test_verificar_doblada_sin_doblada_aprobada_sabado(self):
        """Test: Usuario en sábado sin DOBLADA aprobada - debe mostrar doblada por regla de negocio"""
        self.client.login(username='jeison.mora', password='test123')
        
        # No crear ninguna solicitud de doblada
        # El sábado 14/02/2026 debería mostrar doblada por regla de negocio
        
        url = reverse('solicitudes:verificar_doblada_existente')
        response = self.client.get(url, {'fecha': '2026-02-14'})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        # Si es sábado y le corresponde trabajar, debería mostrar doblada por regla
        # (Este test puede variar según la lógica de alternancia)
        self.assertTrue(data.get('success', False))
    
    def test_verificar_doblada_con_doblada_aprobada_sabado(self):
        """Test: Usuario en sábado CON DOBLADA aprobada - NO debe mostrar doblada por regla, debe mostrar descanso"""
        self.client.login(username='jeison.mora', password='test123')
        
        # Crear solicitud de DOBLADA aprobada: Jeison cede a Marco el 14/02/2026
        solicitud_doblada = SolicitudCambio.objects.create(
            explorador_solicitante=self.jeison,
            explorador_receptor=self.marco,
            tipo_cambio=self.tipo_doblada,
            fecha_cambio_turno=self.fecha_test,
            estado='aprobada',
            fecha_solicitud=date(2026, 2, 10)
        )
        
        # Crear detalle de doblada
        detalle_doblada = DobladaDetalle.objects.create(
            solicitud=solicitud_doblada,
            fecha_pago=date(2026, 2, 18),  # Fecha de pago diferente
            jornada_cedida='AM',
            tipo_cesion='parcial'
        )
        
        # NO crear turnos para Jeison (está descansando)
        # Esto simula el caso real donde Jeison cedió su jornada
        
        url = reverse('solicitudes:verificar_doblada_existente')
        response = self.client.get(url, {'fecha': '2026-02-14'})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        # VALIDACIÓN CRÍTICA: Debe detectar que está descansando por DOBLADA aprobada
        self.assertTrue(data.get('success', False))
        self.assertFalse(data.get('tiene_doblada', True), 
                        "NO debe tener doblada si está descansando por DOBLADA aprobada")
        self.assertTrue(data.get('esta_descansando', False),
                        "Debe estar descansando por DOBLADA aprobada")
        self.assertFalse(data.get('puede_ceder', True),
                        "NO debe poder ceder si está descansando")
        self.assertEqual(data.get('solicitud_id'), solicitud_doblada.id,
                        "Debe retornar el ID de la solicitud de doblada")
        
        # El mensaje debe indicar que está descansando o que cedió su jornada
        mensaje = data.get('mensaje', '').lower()
        self.assertTrue(
            'descansando' in mensaje or 'cediste' in mensaje,
            "El mensaje debe indicar que está descansando o que cedió su jornada"
        )
    
    def test_verificar_doblada_con_ct_aprobado(self):
        """Un CT aprobado NO impide pedir doblada ese mismo día.

        Regla 18 de REGLAS_NEGOCIO_SOLICITUDES.md: no hay tope de cambios por
        fecha. Lo que gobierna el día es su estado real —el explorador trabaja una
        jornada, y esa jornada es cedible como cualquier otra— más el principio de
        "la última aprobada gana".

        Este test asertaba lo contrario y pasaba por partida doble: la vista
        filtraba `tipo_cambio__nombre='CT'` (el `codigo_estrategia`, no el
        `nombre`) y el fixture fabricaba un `TipoSolicitudCambio(nombre='CT')` que
        no existe en producción. Dato incorrecto contra filtro incorrecto.
        """
        self.client.login(username='jeison.mora', password='test123')

        # 'CAMBIO TURNO' es el `nombre` real en la maestra; 'CT' su `codigo_estrategia`
        # y el valor que se escribe en `Turno.tipo_cambio`.
        tipo_ct, _ = TipoSolicitudCambio.objects.get_or_create(
            nombre='CAMBIO TURNO', defaults={'codigo_estrategia': 'CT'}
        )
        
        # Crear solicitud de CT aprobada
        solicitud_ct = SolicitudCambio.objects.create(
            explorador_solicitante=self.jeison,
            explorador_receptor=self.marco,
            tipo_cambio=tipo_ct,
            fecha_cambio_turno=self.fecha_test,
            estado='aprobada',
            fecha_solicitud=date(2026, 2, 10)
        )
        
        # Crear turno para Jeison con jornada del receptor (resultado del CT)
        turno_jeison = Turno.objects.create(
            explorador=self.jeison,
            fecha=self.fecha_test,
            jornada=self.jornada_pm,  # Jornada del receptor
            sala=self.sala,
            tipo_cambio='CT'
        )
        solicitud_ct.turno_origen = turno_jeison
        solicitud_ct.save()
        
        url = reverse('solicitudes:verificar_doblada_existente')
        response = self.client.get(url, {'fecha': '2026-02-14'})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        self.assertTrue(data.get('success', False))
        self.assertTrue(data.get('puede_ceder', False),
                        "Un CT aprobado no debe impedir ceder: la jornada que trabaja es cedible")
        self.assertIn('PM', data.get('jornadas', []),
                      "Debe ver la jornada que le quedó tras el CT (la del receptor)")
    
    def test_verificar_doblada_con_turnos_am_pm(self):
        """Test: Usuario con turnos AM+PM - debe mostrar que tiene doblada"""
        self.client.login(username='jeison.mora', password='test123')
        
        # Crear turnos AM y PM para Jeison
        Turno.objects.create(
            explorador=self.jeison,
            fecha=self.fecha_test,
            jornada=self.jornada_am,
            sala=self.sala,
            tipo_cambio='DOBLADA'
        )
        Turno.objects.create(
            explorador=self.jeison,
            fecha=self.fecha_test,
            jornada=self.jornada_pm,
            sala=self.sala,
            tipo_cambio='DOBLADA'
        )

        url = reverse('solicitudes:verificar_doblada_existente')
        response = self.client.get(url, {'fecha': '2026-02-14'})

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # Debe detectar que tiene doblada
        self.assertTrue(data.get('success', False))
        self.assertTrue(data.get('tiene_doblada', False),
                        "Debe tener doblada si tiene turnos AM+PM")
        self.assertFalse(data.get('esta_descansando', True),
                        "NO debe estar descansando si tiene turnos")
        self.assertTrue(data.get('puede_ceder', False),
                        "Debe poder ceder si tiene doblada")
        self.assertIn('AM', data.get('jornadas', []))
        self.assertIn('PM', data.get('jornadas', []))
    
    def test_verificar_doblada_con_turnos_am_pm_y_doblada_aprobada(self):
        """Test: Usuario con turnos AM+PM en BD Y DOBLADA aprobada - debe priorizar turnos físicos"""
        self.client.login(username='jeison.mora', password='test123')
        
        # Crear turnos AM y PM para Jeison (doblada real en BD)
        Turno.objects.create(
            explorador=self.jeison,
            fecha=self.fecha_test,
            jornada=self.jornada_am,
            sala=self.sala,
            tipo_cambio='DOBLADA'
        )
        Turno.objects.create(
            explorador=self.jeison,
            fecha=self.fecha_test,
            jornada=self.jornada_pm,
            sala=self.sala,
            tipo_cambio='DOBLADA'
        )
        
        # Crear también una DOBLADA aprobada donde Jeison es solicitante (cedió)
        # Esto NO debería afectar el resultado porque hay turnos físicos
        solicitud_doblada = SolicitudCambio.objects.create(
            explorador_solicitante=self.jeison,
            explorador_receptor=self.marco,
            tipo_cambio=self.tipo_doblada,
            fecha_cambio_turno=self.fecha_test,
            estado='aprobada',
            fecha_solicitud=date(2026, 2, 10)
        )
        
        DobladaDetalle.objects.create(
            solicitud=solicitud_doblada,
            fecha_pago=date(2026, 2, 18),
            jornada_cedida='AM',
            tipo_cesion='parcial'
        )
        
        url = reverse('solicitudes:verificar_doblada_existente')
        response = self.client.get(url, {'fecha': '2026-02-14'})
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        # VALIDACIÓN CRÍTICA: Los turnos físicos tienen prioridad absoluta
        # Debe detectar que tiene doblada por los turnos, NO por la solicitud
        self.assertTrue(data.get('success', False))
        self.assertTrue(data.get('tiene_doblada', False),
                        "Debe tener doblada si tiene turnos AM+PM en BD, independientemente de DOBLADA aprobada")
        self.assertFalse(data.get('esta_descansando', True),
                        "NO debe estar descansando si tiene turnos físicos")
        self.assertTrue(data.get('puede_ceder', False),
                        "Debe poder ceder si tiene doblada")
        self.assertIn('AM', data.get('jornadas', []))
        self.assertIn('PM', data.get('jornadas', []))
        
        # El mensaje debe indicar que tiene doblada, no que está descansando
        mensaje = data.get('mensaje', '').lower()
        self.assertIn('doblada', mensaje,
                     "El mensaje debe mencionar doblada")
        self.assertNotIn('descansando', mensaje,
                        "El mensaje NO debe mencionar descansando cuando hay turnos físicos")

    def test_verificar_doblada_festivo_semana_usuario_grupo_que_dobla(self):
        """Test: Festivo entre semana - usuario del grupo que dobla ese día debe ver doblada y opciones."""
        # 1. Crear festivos de semana: 2026-01-01 (lunes) y 2026-04-03 (viernes)
        #    Rotación: índice 0 -> PM, índice 1 -> AM. Así el 3 de abril le toca a AM.
        DiaEspecial.objects.create(
            fecha=date(2026, 1, 1),
            tipo='festivo',
            descripcion='Año Nuevo',
            activo=True
        )
        DiaEspecial.objects.create(
            fecha=date(2026, 4, 3),
            tipo='festivo',
            descripcion='Día festivo',
            activo=True
        )
        # Publicar la alternancia: es un DATO, no una fórmula (ver alternancia_helpers).
        from turnos.tests.alternancia_helpers import publicar_alternancia
        publicar_alternancia(2026)
        # 2. Asignar jornada AM a Jeison (fecha_inicio antes del festivo)
        AsignarJornadaExplorador.objects.create(
            explorador=self.jeison,
            jornada=self.jornada_am,
            fecha_inicio=date(2025, 1, 1)
        )
        self.client.login(username='jeison.mora', password='test123')
        url = reverse('solicitudes:verificar_doblada_existente')
        response = self.client.get(url, {'fecha': '2026-04-03'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get('success', False), f"Response: {data}")
        self.assertTrue(
            data.get('tiene_doblada', False),
            f"Usuario AM debe tener doblada el 3-abr-2026 (festivo para grupo AM). Response: {data}"
        )
        self.assertFalse(data.get('esta_descansando', True))
        self.assertTrue(data.get('puede_ceder', False))
        self.assertIn('AM', data.get('jornadas', []))
        self.assertIn('PM', data.get('jornadas', []))

    def test_verificar_doblada_festivo_semana_usuario_grupo_que_descansa(self):
        """Festivo entre semana - usuario del grupo que DESCANSA ese día NO puede ceder.

        Regla de negocio: si a tu grupo no le corresponde trabajar el festivo, no tienes
        jornada que ceder, por lo que puede_ceder debe ser False (el frontend bloquea
        compañero/fecha de pago/envío) y se entrega el mensaje explicativo.
        """
        # Misma rotación que el test anterior: idx 0 (01-ene) -> PM, idx 1 (03-abr) -> AM.
        # El 3 de abril dobla el grupo AM, así que un usuario PM descansa.
        DiaEspecial.objects.create(
            fecha=date(2026, 1, 1), tipo='festivo', descripcion='Año Nuevo', activo=True
        )
        DiaEspecial.objects.create(
            fecha=date(2026, 4, 3), tipo='festivo', descripcion='Día festivo', activo=True
        )
        # Jeison es PM (grupo que descansa el 03-abr)
        AsignarJornadaExplorador.objects.create(
            explorador=self.jeison,
            jornada=self.jornada_pm,
            fecha_inicio=date(2025, 1, 1)
        )
        self.client.login(username='jeison.mora', password='test123')
        url = reverse('solicitudes:verificar_doblada_existente')
        response = self.client.get(url, {'fecha': '2026-04-03'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data.get('success', False), f"Response: {data}")
        self.assertFalse(
            data.get('puede_ceder', True),
            f"Usuario PM NO debe poder ceder el 3-abr-2026 (festivo del grupo AM). Response: {data}"
        )
        self.assertFalse(data.get('tiene_doblada', True))
        self.assertIn('descansas', data.get('mensaje', '').lower())