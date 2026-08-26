"""
"A 25 de agosto, ¿quién debe?" — la deuda del mes en curso hasta un día concreto.

Es la pregunta del día a día del supervisor, distinta de la que responde `auditar_morosos`:
aquélla mira el mes YA VENCIDO para decidir sanciones, ésta mira el mes que aún corre, cuando
avisar todavía sirve para algo. Estos tests fijan las dos cosas que se pueden torcer: el corte
por día (nada de lo que aún no ha pasado) y qué deuda cuenta como pendiente.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from empleados.models import Empleado
from permisos.deuda_permiso_service import sincronizar
from permisos.models import PermisoEspecial
from solicitudes.models import DeudaCorporativa
from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService

CORTE = date(2026, 8, 25)


class DeudaACorteTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sup = Empleado.objects.create(
            user=User.objects.create_user(username='sup-corte', password='x'),
            nombre='Supervisora', apellido='C', cedula='sup-corte', activo=True)
        cls.exp = Empleado.objects.create(
            user=User.objects.create_user(username='exp-corte', password='x'),
            nombre='Explorador', apellido='C', cedula='exp-corte', activo=True,
            supervisor=cls.sup)

    def _doblada(self, dia, estado='activa', empleado=None):
        return DeudaCorporativa.objects.create(
            explorador=empleado or self.exp, minutos=30, fecha_doblada=dia, estado=estado)

    def _fila(self, filas, empleado=None):
        empleado = empleado or self.exp
        return next((f for f in filas if f['explorador'].id == empleado.id), None)

    # --- Corte por día -------------------------------------------------------------------

    def test_una_doblada_dentro_del_rango_aparece(self):
        self._doblada(date(2026, 8, 10))

        fila = self._fila(DeudaCorporativaService.deuda_a_corte(CORTE))

        self.assertEqual(fila['minutos'], 30)
        self.assertEqual(fila['minutos_dobladas'], 30)
        self.assertEqual(fila['dias'], 1)

    def test_una_doblada_posterior_al_corte_no_aparece(self):
        """El 26 todavía no ha pasado: no se debe."""
        self._doblada(date(2026, 8, 26))

        self.assertEqual(DeudaCorporativaService.deuda_a_corte(CORTE), [])

    def test_no_se_arrastra_la_deuda_de_meses_anteriores(self):
        """
        A estas alturas ya no existe: o se pagó o la consumió la sanción del mes vencido.
        Mezclarla aquí haría creer que el mes en curso va peor de lo que va.
        """
        self._doblada(date(2026, 7, 28))

        self.assertEqual(DeudaCorporativaService.deuda_a_corte(CORTE), [])

    # --- Qué cuenta como pendiente -------------------------------------------------------

    def test_la_deuda_pagada_no_aparece(self):
        self._doblada(date(2026, 8, 10), estado='pagada')

        self.assertEqual(DeudaCorporativaService.deuda_a_corte(CORTE), [])

    def test_la_deuda_consumida_por_una_sancion_no_aparece(self):
        self._doblada(date(2026, 8, 10), estado='consumida_por_sancion')

        self.assertEqual(DeudaCorporativaService.deuda_a_corte(CORTE), [])

    def test_la_consulta_no_escribe_nada(self):
        self._doblada(date(2026, 8, 10))

        DeudaCorporativaService.deuda_a_corte(CORTE)

        self.assertEqual(DeudaCorporativa.objects.filter(estado='activa').count(), 1)

    # --- Permisos permanentes: prorrateo -------------------------------------------------

    def _permiso_agosto(self, tiempo='0.5'):
        """Permanente los martes de agosto de 2026: días 4, 11, 18 y 25."""
        permiso = PermisoEspecial.objects.create(
            empleado=self.exp, tipo='PERSONAL', es_permanente=True,
            fecha_inicio=date(2026, 8, 1), fecha_fin=date(2026, 8, 31), dias_semana='1',
            tiempo=Decimal(tiempo), motivo='Prueba', estado='APROBADO', supervisor=self.sup)
        sincronizar(permiso)
        return permiso

    def test_del_permiso_solo_cuentan_las_ocurrencias_ya_pasadas(self):
        """Al día 20 han pasado tres martes (4, 11 y 18): 90 min, no los 120 del mes."""
        self._permiso_agosto()

        fila = self._fila(DeudaCorporativaService.deuda_a_corte(date(2026, 8, 20)))

        self.assertEqual(fila['minutos_permisos'], 90)
        self.assertEqual(fila['minutos'], 90)
        self.assertEqual(fila['dias'], 3)

    def test_al_ultimo_dia_cuenta_el_mes_entero(self):
        self._permiso_agosto()

        fila = self._fila(DeudaCorporativaService.deuda_a_corte(date(2026, 8, 31)))

        self.assertEqual(fila['minutos_permisos'], 120)

    def test_un_pago_parcial_que_cubre_lo_devengado_lo_saca_de_la_lista(self):
        """
        El pago se imputa a lo más antiguo, así que 90 min pagados cubren los tres martes
        que han pasado al día 20 aunque el mes entero deba 120.
        """
        permiso = self._permiso_agosto()
        deuda = permiso.deudas_mes.get(anio=2026, mes=8)
        deuda.minutos_pagados = 90
        deuda.save(update_fields=['minutos_pagados'])

        self.assertEqual(DeudaCorporativaService.deuda_a_corte(date(2026, 8, 20)), [])

    def test_un_pago_parcial_menor_deja_el_resto_visible(self):
        permiso = self._permiso_agosto()
        deuda = permiso.deudas_mes.get(anio=2026, mes=8)
        deuda.minutos_pagados = 60
        deuda.save(update_fields=['minutos_pagados'])

        fila = self._fila(DeudaCorporativaService.deuda_a_corte(date(2026, 8, 20)))

        self.assertEqual(fila['minutos_permisos'], 30)

    # --- Las dos fuentes juntas ----------------------------------------------------------

    def test_dobladas_y_permisos_suman_en_la_misma_fila(self):
        self._doblada(date(2026, 8, 10))
        self._permiso_agosto()

        fila = self._fila(DeudaCorporativaService.deuda_a_corte(date(2026, 8, 20)))

        self.assertEqual(fila['minutos_dobladas'], 30)
        self.assertEqual(fila['minutos_permisos'], 90)
        self.assertEqual(fila['minutos'], 120)

    def test_ordena_por_deuda_descendente(self):
        otro = Empleado.objects.create(
            user=User.objects.create_user(username='otro-corte', password='x'),
            nombre='Otro', apellido='C', cedula='otro-corte', activo=True, supervisor=self.sup)
        self._doblada(date(2026, 8, 5))
        self._doblada(date(2026, 8, 6))
        self._doblada(date(2026, 8, 7), empleado=otro)

        filas = DeudaCorporativaService.deuda_a_corte(CORTE)

        self.assertEqual([f['explorador'].id for f in filas], [self.exp.id, otro.id])
