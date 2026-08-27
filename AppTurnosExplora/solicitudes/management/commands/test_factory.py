"""
Comando para probar el factory
"""
from django.core.management.base import BaseCommand

from solicitudes.models import TipoSolicitudCambio
from solicitudes.services.solicitud_factory import SolicitudFactory


class Command(BaseCommand):
    help = 'Prueba el factory de estrategias'

    def handle(self, *args, **options):
        self.stdout.write("=== ESTRATEGIAS REGISTRADAS ===\n")
        for k, v in SolicitudFactory._strategies.items():
            self.stdout.write(f"  {k} -> {v.__name__}")
        
        self.stdout.write("\n=== PROBANDO TIPOS ===\n")
        tipos = TipoSolicitudCambio.objects.filter(activo=True)
        for tipo in tipos:
            strategy = SolicitudFactory.get_strategy(tipo)
            self.stdout.write(
                f"Tipo: {tipo.nombre}\n"
                f"  Codigo estrategia: {tipo.codigo_estrategia}\n"
                f"  Estrategia encontrada: {strategy.__class__.__name__ if strategy else 'None'}\n"
            )

