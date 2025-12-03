"""
Script para verificar cambios permanentes existentes entre dos empleados
"""
import os
import django

# Configurar el entorno de Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio, CambioPermanenteDetalle, CambioPermanenteDia
from empleados.models import Empleado
from django.db import models
from datetime import date

def verificar_cambios_permanentes():
    print("=" * 80)
    print("VERIFICACIÓN DE CAMBIOS PERMANENTES")
    print("=" * 80)
    
    # Buscar los empleados
    try:
        # Buscar por email o nombre
        manuel = Empleado.objects.filter(
            models.Q(email__icontains='manuel.moreno') | 
            models.Q(nombre__icontains='manuel') & models.Q(apellido__icontains='moreno')
        ).first()
        
        jeison = Empleado.objects.filter(
            models.Q(email__icontains='jeison.mora') | 
            models.Q(nombre__icontains='jeison') & models.Q(apellido__icontains='mora')
        ).first()
        
        if not manuel:
            print("[ERROR] No se encontro el empleado manuel.moreno")
            print("   Empleados disponibles con 'manuel':")
            for emp in Empleado.objects.filter(nombre__icontains='manuel')[:5]:
                print(f"      - {emp.nombre} {emp.apellido} ({emp.email})")
            return
        if not jeison:
            print("[ERROR] No se encontro el empleado jeison.mora")
            print("   Empleados disponibles con 'jeison':")
            for emp in Empleado.objects.filter(nombre__icontains='jeison')[:5]:
                print(f"      - {emp.nombre} {emp.apellido} ({emp.email})")
            return
        
        print(f"\n[INFO] Empleados encontrados:")
        print(f"   Solicitante: {manuel.nombre} {manuel.apellido} (ID: {manuel.id})")
        print(f"   Receptor: {jeison.nombre} {jeison.apellido} (ID: {jeison.id})")
        
        # Buscar cambios permanentes en ambas direcciones
        print(f"\n[INFO] Buscando cambios permanentes...")
        
        # Dirección 1: manuel -> jeison
        cambios_1 = SolicitudCambio.objects.filter(
            explorador_solicitante=manuel,
            explorador_receptor=jeison,
            tipo_cambio__nombre='CT PERMANENTE',
            estado__in=['pendiente', 'aprobada']
        ).select_related('cambio_permanente', 'tipo_cambio')
        
        # Dirección 2: jeison -> manuel
        cambios_2 = SolicitudCambio.objects.filter(
            explorador_solicitante=jeison,
            explorador_receptor=manuel,
            tipo_cambio__nombre='CT PERMANENTE',
            estado__in=['pendiente', 'aprobada']
        ).select_related('cambio_permanente', 'tipo_cambio')
        
        total_cambios = cambios_1.count() + cambios_2.count()
        
        if total_cambios == 0:
            print(f"\n[OK] No se encontraron cambios permanentes activos entre estos empleados.")
            print(f"   El error puede ser causado por la logica de validacion incorrecta.")
        else:
            print(f"\n[ADVERTENCIA] Se encontraron {total_cambios} cambio(s) permanente(s) activo(s):")
            print("-" * 80)
            
            # Mostrar cambios dirección 1
            for cambio in cambios_1:
                mostrar_detalle_cambio(cambio, manuel, jeison)
            
            # Mostrar cambios dirección 2
            for cambio in cambios_2:
                mostrar_detalle_cambio(cambio, jeison, manuel)
        
        # Verificar superposición con el nuevo rango
        print(f"\n[INFO] Verificando superposicion con nuevo rango:")
        print(f"   Fecha inicio: 2025-11-28")
        print(f"   Fecha fin: 2025-11-30")
        print(f"   Día seleccionado: Viernes")
        print("-" * 80)
        
        fecha_inicio_nueva = date(2025, 11, 28)
        fecha_fin_nueva = date(2025, 11, 30)
        
        todos_cambios = list(cambios_1) + list(cambios_2)
        hay_superposicion = False
        
        for cambio in todos_cambios:
            detalle = cambio.cambio_permanente
            if detalle:
                fecha_inicio_existente = detalle.fecha_inicio
                fecha_fin_existente = detalle.fecha_fin
                
                # Verificar superposición
                if fecha_fin_existente is None:
                    # Cambio existente es indefinido
                    se_superpone = fecha_inicio_nueva >= fecha_inicio_existente
                elif fecha_fin_nueva is None:
                    # Cambio nuevo es indefinido
                    se_superpone = fecha_inicio_nueva <= fecha_fin_existente and fecha_inicio_nueva >= fecha_inicio_existente
                else:
                    # Ambos tienen fecha fin
                    se_superpone = fecha_inicio_nueva <= fecha_fin_existente and fecha_fin_nueva >= fecha_inicio_existente
                
                if se_superpone:
                    hay_superposicion = True
                    print(f"\n[ERROR] SUPERPOSICION DETECTADA:")
                    print(f"   Cambio existente ID: {cambio.id}")
                    print(f"   Estado: {cambio.estado}")
                    print(f"   Rango existente: {fecha_inicio_existente} a {fecha_fin_existente or 'Sin fecha fin'}")
                    print(f"   Rango nuevo: {fecha_inicio_nueva} a {fecha_fin_nueva}")
                    
                    # Mostrar días seleccionados del cambio existente
                    dias_existentes = detalle.dias.all()
                    if dias_existentes.exists():
                        dias_nombres = []
                        for dia in dias_existentes:
                            if dia.tipo == 'dia_semana' and dia.dia_semana is not None:
                                dias_nombres.append(dia.get_dia_semana_display())
                        if dias_nombres:
                            print(f"   Días seleccionados existentes: {', '.join(dias_nombres)}")
        
        if not hay_superposicion and total_cambios > 0:
            print(f"\n[OK] No hay superposicion con los cambios existentes.")
            print(f"   El error puede ser causado por la logica de validacion incorrecta.")
        elif not hay_superposicion:
            print(f"\n[OK] No hay cambios existentes que se superpongan.")
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()

def mostrar_detalle_cambio(cambio, solicitante, receptor):
    """Muestra los detalles de un cambio permanente"""
    detalle = cambio.cambio_permanente
    print(f"\n[INFO] Cambio Permanente ID: {cambio.id}")
    print(f"   Estado: {cambio.estado}")
    print(f"   Fecha solicitud: {cambio.fecha_solicitud}")
    print(f"   Solicitante: {solicitante.nombre} {solicitante.apellido}")
    print(f"   Receptor: {receptor.nombre} {receptor.apellido}")
    
    if detalle:
        print(f"   Fecha inicio: {detalle.fecha_inicio}")
        print(f"   Fecha fin: {detalle.fecha_fin or 'Sin fecha fin (indefinido)'}")
        
        # Mostrar días seleccionados
        dias_seleccionados = detalle.dias.all()
        if dias_seleccionados.exists():
            dias_nombres = []
            for dia in dias_seleccionados:
                if dia.tipo == 'dia_semana' and dia.dia_semana is not None:
                    dias_nombres.append(dia.get_dia_semana_display())
            if dias_nombres:
                print(f"   Dias seleccionados: {', '.join(dias_nombres)}")
            else:
                print(f"   Dias seleccionados: Todos los dias habiles")
        else:
            print(f"   Dias seleccionados: Todos los dias habiles (retrocompatibilidad)")
    else:
        print(f"   [ADVERTENCIA] No se encontro detalle del cambio permanente")

if __name__ == "__main__":
    verificar_cambios_permanentes()

