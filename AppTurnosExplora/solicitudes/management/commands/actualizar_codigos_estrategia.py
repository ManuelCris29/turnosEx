"""
Comando para actualizar codigo_estrategia en tipos existentes
"""
from django.core.management.base import BaseCommand
from solicitudes.models import TipoSolicitudCambio


class Command(BaseCommand):
    help = 'Actualiza codigo_estrategia en tipos de solicitud existentes'

    def handle(self, *args, **options):
        # Mapeo de nombres a códigos
        mapeo = {
            'CAMBIO TURNO': 'CT',
            'CT PERMANENTE': 'CT PERMANENTE',
            'DOBLADA': 'DOBLADA',
            'D FDS': 'D FDS',
        }

        tipos = TipoSolicitudCambio.objects.filter(activo=True)
        self.stdout.write("Actualizando códigos de estrategia...\n")

        actualizados = 0
        for tipo in tipos:
            codigo = mapeo.get(tipo.nombre.upper())
            if codigo:
                tipo.codigo_estrategia = codigo
                tipo.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[OK] {tipo.nombre} -> codigo_estrategia: {codigo}"
                    )
                )
                actualizados += 1
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"[WARN] {tipo.nombre} -> No se encontro mapeo"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(f"\n[OK] Actualizacion completada: {actualizados} tipos actualizados")
        )

