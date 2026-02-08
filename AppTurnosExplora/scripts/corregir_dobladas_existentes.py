"""
Script para corregir datos históricos de dobladas existentes.

Este script realiza las siguientes correcciones:
1. Actualizar jornada_cedida NULL en DobladaDetalle existentes
2. Crear registros faltantes en PDH para DeudaCorporativa existentes

Uso:
    python manage.py shell < scripts/corregir_dobladas_existentes.py
    
    O desde Django shell:
    >>> exec(open('scripts/corregir_dobladas_existentes.py').read())
"""
import os
import sys
import django
from datetime import datetime

# Setup Django
if __name__ == '__main__':
    # Agregar el directorio raíz al path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()

from solicitudes.models import DobladaDetalle, DeudaCorporativa
from permisos.models import PDH
from turnos.services.jornada_service import JornadaService
from django.db import transaction


def corregir_jornada_cedida():
    """
    Corrige registros de DobladaDetalle donde jornada_cedida es NULL.
    Infiere la jornada basándose en la jornada del solicitante en fecha_cesion.
    """
    print("\n" + "="*80)
    print("CORRECCIÓN 1: Actualizar jornada_cedida NULL")
    print("="*80)
    
    detalles_sin_jornada = DobladaDetalle.objects.filter(jornada_cedida__isnull=True)
    total = detalles_sin_jornada.count()
    
    if total == 0:
        print("✅ No hay registros con jornada_cedida NULL. Todo está correcto.")
        return 0
    
    print(f"📋 Encontrados {total} registros con jornada_cedida NULL")
    print("-" * 80)
    
    corregidos = 0
    errores = 0
    
    for detalle in detalles_sin_jornada:
        try:
            solicitud = detalle.solicitud
            fecha_cesion = solicitud.fecha_cambio_turno
            solicitante = solicitud.explorador_solicitante
            
            # Inferir jornada del solicitante en fecha de cesión
            jornada_solicitante = JornadaService.get_jornada_explorador_fecha(
                solicitante.id,
                fecha_cesion.strftime('%Y-%m-%d')
            )
            
            jornada_cedida = jornada_solicitante.nombre.upper()
            
            # Actualizar el registro
            detalle.jornada_cedida = jornada_cedida
            detalle.save()
            
            print(f"✅ Solicitud {solicitud.id}: {solicitante.nombre} -> jornada_cedida = {jornada_cedida}")
            corregidos += 1
            
        except Exception as e:
            print(f"❌ Error en solicitud {detalle.solicitud.id}: {str(e)}")
            errores += 1
    
    print("-" * 80)
    print(f"✅ Corregidos: {corregidos}")
    print(f"❌ Errores: {errores}")
    print(f"📊 Total procesados: {corregidos + errores}/{total}")
    
    return corregidos


def crear_registros_pdh_faltantes():
    """
    Crea registros en PDH para todas las DeudaCorporativa existentes
    que no tengan su correspondiente registro en PDH.
    """
    print("\n" + "="*80)
    print("CORRECCIÓN 2: Crear registros faltantes en PDH")
    print("="*80)
    
    deudas_corporativas = DeudaCorporativa.objects.all().select_related(
        'explorador', 'solicitud_origen'
    )
    total = deudas_corporativas.count()
    
    if total == 0:
        print("ℹ️  No hay deudas corporativas registradas.")
        return 0
    
    print(f"📋 Encontradas {total} deudas corporativas")
    print("-" * 80)
    
    creados = 0
    ya_existentes = 0
    errores = 0
    
    for deuda in deudas_corporativas:
        try:
            # Verificar si ya existe un registro en PDH para esta deuda
            existe_pdh = PDH.objects.filter(
                explorador=deuda.explorador,
                fecha=deuda.fecha_doblada,
                tipo_registro='deuda_corporativa',
                horas=round(deuda.minutos / 60, 2)
            ).exists()
            
            if existe_pdh:
                print(f"⏭️  Solicitud {deuda.solicitud_origen.id if deuda.solicitud_origen else 'N/A'}: "
                      f"{deuda.explorador.nombre} - Ya existe en PDH")
                ya_existentes += 1
                continue
            
            # Determinar supervisor
            supervisor = None
            if deuda.solicitud_origen:
                if hasattr(deuda.solicitud_origen, 'aprobado_supervisor'):
                    supervisor = deuda.solicitud_origen.aprobado_supervisor
                elif deuda.solicitud_origen.explorador_solicitante:
                    supervisor = getattr(deuda.solicitud_origen.explorador_solicitante, 'supervisor', None)
            
            if not supervisor:
                supervisor = getattr(deuda.explorador, 'supervisor', None)
            
            # Crear registro en PDH
            PDH.objects.create(
                explorador=deuda.explorador,
                solicitud=deuda.solicitud_origen,
                fecha=deuda.fecha_doblada,
                horas=round(deuda.minutos / 60, 2),
                supervisor=supervisor,
                tipo_registro='deuda_corporativa',
                comentario=deuda.comentario or f'Deuda corporativa acumulada: {deuda.minutos} minutos por doblada (corrección histórica)'
            )
            
            print(f"✅ Solicitud {deuda.solicitud_origen.id if deuda.solicitud_origen else 'N/A'}: "
                  f"{deuda.explorador.nombre} - {deuda.minutos} min - PDH creado")
            creados += 1
            
        except Exception as e:
            print(f"❌ Error procesando deuda {deuda.id}: {str(e)}")
            errores += 1
    
    print("-" * 80)
    print(f"✅ Creados: {creados}")
    print(f"⏭️  Ya existentes: {ya_existentes}")
    print(f"❌ Errores: {errores}")
    print(f"📊 Total procesados: {creados + ya_existentes + errores}/{total}")
    
    return creados


def generar_reporte_final():
    """
    Genera un reporte final del estado de las tablas.
    """
    print("\n" + "="*80)
    print("REPORTE FINAL")
    print("="*80)
    
    # DobladaDetalle
    total_dobladas = DobladaDetalle.objects.count()
    dobladas_sin_jornada = DobladaDetalle.objects.filter(jornada_cedida__isnull=True).count()
    
    print(f"📋 DobladaDetalle:")
    print(f"   Total: {total_dobladas}")
    print(f"   Con jornada_cedida: {total_dobladas - dobladas_sin_jornada}")
    print(f"   Sin jornada_cedida (NULL): {dobladas_sin_jornada}")
    
    # DeudaCorporativa
    total_deudas = DeudaCorporativa.objects.count()
    deudas_activas = DeudaCorporativa.objects.filter(estado='activa').count()
    
    print(f"\n💰 DeudaCorporativa:")
    print(f"   Total: {total_deudas}")
    print(f"   Activas: {deudas_activas}")
    print(f"   Canceladas: {total_deudas - deudas_activas}")
    
    # PDH (deuda_corporativa)
    total_pdh = PDH.objects.filter(tipo_registro='deuda_corporativa').count()
    
    print(f"\n📊 PDH (tipo=deuda_corporativa):")
    print(f"   Total: {total_pdh}")
    
    print("\n" + "="*80)
    
    # Verificación de consistencia
    if dobladas_sin_jornada == 0:
        print("✅ CONSISTENCIA: Todas las dobladas tienen jornada_cedida")
    else:
        print(f"⚠️  ADVERTENCIA: {dobladas_sin_jornada} dobladas sin jornada_cedida")
    
    if total_deudas == total_pdh:
        print("✅ CONSISTENCIA: Todas las deudas corporativas tienen registro en PDH")
    else:
        diferencia = abs(total_deudas - total_pdh)
        print(f"⚠️  NOTA: Diferencia de {diferencia} registros entre DeudaCorporativa y PDH")
        print(f"   (Esto puede ser normal si hay deudas sin supervisor asignado)")
    
    print("="*80 + "\n")


@transaction.atomic
def main():
    """
    Función principal que ejecuta todas las correcciones.
    """
    print("\n" + "🔧 " + "="*76)
    print("🔧  SCRIPT DE CORRECCIÓN: Datos Históricos de Dobladas")
    print("🔧 " + "="*76)
    print(f"📅 Fecha de ejecución: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Corrección 1: jornada_cedida NULL
        corregidos_jornada = corregir_jornada_cedida()
        
        # Corrección 2: Registros PDH faltantes
        creados_pdh = crear_registros_pdh_faltantes()
        
        # Reporte final
        generar_reporte_final()
        
        print("\n✅ SCRIPT COMPLETADO EXITOSAMENTE")
        print(f"   - jornada_cedida corregidas: {corregidos_jornada}")
        print(f"   - Registros PDH creados: {creados_pdh}")
        print()
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)




