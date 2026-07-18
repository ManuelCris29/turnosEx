from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View
from django.http import JsonResponse
from django.db.models import Q
# Cache ahora se usa a través de CacheService (importado donde se necesita)
from turnos.models import Turno, AsignarJornadaExplorador, DiaEspecial
from turnos.services.turno_service import TurnoService
from turnos.services.temporada_service import TemporadaService
from datetime import datetime, timedelta, date


class ReporteDiaView(LoginRequiredMixin, View):
    """Reporte operacional del día para supervisores. Solo accesible con rol supervisor/staff."""

    def get(self, request):
        from core.mixins import AdminRequiredMixin as _AM
        # Verificar permiso de supervisor
        if not request.user.is_staff:
            try:
                tiene = request.user.empleado.empleadorole_set.filter(
                    role__nombre__icontains='supervisor').exists()
            except Exception:
                tiene = False
            if not tiene:
                return JsonResponse({'error': 'Sin permisos'}, status=403)

        fecha_str = request.GET.get('fecha')
        if not fecha_str:
            return JsonResponse({'error': 'Debe enviar fecha (YYYY-MM-DD)'}, status=400)
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Formato de fecha inválido'}, status=400)

        try:
            from turnos.services.reporte_dia_service import ReporteDiaService
            data = ReporteDiaService.reporte(fecha)
            return JsonResponse(data)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f'ReporteDiaView: {e}', exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)


class ReporteDiaExcelView(LoginRequiredMixin, View):
    """Exporta el reporte operacional del día como archivo Excel (.xlsx)."""

    def _check_permiso(self, request):
        if request.user.is_staff:
            return True
        try:
            return request.user.empleado.empleadorole_set.filter(
                role__nombre__icontains='supervisor').exists()
        except Exception:
            return False

    def get(self, request):
        if not self._check_permiso(request):
            return JsonResponse({'error': 'Sin permisos'}, status=403)

        fecha_str = request.GET.get('fecha')
        if not fecha_str:
            return JsonResponse({'error': 'Debe enviar fecha (YYYY-MM-DD)'}, status=400)
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'error': 'Formato de fecha inválido'}, status=400)

        try:
            from turnos.services.reporte_dia_service import ReporteDiaService
            data = ReporteDiaService.reporte(fecha)
            return self._generar_excel(fecha, data)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f'ReporteDiaExcelView: {e}', exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)

    def _generar_excel(self, fecha, data):
        import io
        from django.http import HttpResponse
        from openpyxl import Workbook
        from openpyxl.styles import (PatternFill, Font, Alignment,
                                     Border, Side, GradientFill)
        from openpyxl.utils import get_column_letter

        MESES = ['', 'enero','febrero','marzo','abril','mayo','junio',
                 'julio','agosto','septiembre','octubre','noviembre','diciembre']
        DIAS  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
        fecha_legible = f'{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month]} de {fecha.year}'

        trabajando  = data.get('trabajando', [])
        descansando = data.get('descansando', [])
        dia_info    = data.get('dia_info', {})

        am   = [e for e in trabajando if e.get('jornada_dia') in ('AM', 'DOBLADA')]
        pm   = [e for e in trabajando if e.get('jornada_dia') in ('PM', 'DOBLADA')]
        desc = descansando

        # ── Estilos ──────────────────────────────────────────────────────────
        def fill(hex_color):
            return PatternFill('solid', fgColor=hex_color)

        AZUL_OSCURO  = '1E3A5F'
        AZUL_MEDIO   = '2563EB'
        AZUL_CLARO   = 'DBEAFE'
        NARANJA_OSC  = '92400E'
        NARANJA_MED  = 'D97706'
        NARANJA_CL   = 'FEF3C7'
        GRIS_OSC     = '334155'
        GRIS_MED     = '64748B'
        GRIS_CLARO   = 'F1F5F9'
        VERDE_CL     = 'DCFCE7'
        MORADO_CL    = 'EDE9FE'
        BLANCO       = 'FFFFFF'

        def fuente(bold=False, color='000000', size=10, italic=False):
            return Font(bold=bold, color=color, size=size, italic=italic)

        def borde_fino():
            s = Side(style='thin', color='CBD5E1')
            return Border(left=s, right=s, top=s, bottom=s)

        def centrado(wrap=False):
            return Alignment(horizontal='center', vertical='center', wrap_text=wrap)

        def izquierda(wrap=False):
            return Alignment(horizontal='left', vertical='center', wrap_text=wrap)

        wb = Workbook()
        wb.remove(wb.active)  # quitar hoja vacía por defecto

        # ════════════════════════════════════════════════════════════════════
        # HOJA 1 — RESUMEN
        # ════════════════════════════════════════════════════════════════════
        ws = wb.create_sheet('Resumen')
        ws.sheet_view.showGridLines = False
        ws.column_dimensions['A'].width = 32
        ws.column_dimensions['B'].width = 20
        ws.column_dimensions['C'].width = 20
        ws.column_dimensions['D'].width = 20

        # Título principal
        ws.merge_cells('A1:D1')
        c = ws['A1']
        c.value = '📋  REPORTE OPERACIONAL'
        c.font = fuente(bold=True, color=BLANCO, size=14)
        c.fill = fill(AZUL_OSCURO)
        c.alignment = centrado()
        ws.row_dimensions[1].height = 32

        # Fecha
        ws.merge_cells('A2:D2')
        c = ws['A2']
        c.value = fecha_legible.capitalize()
        c.font = fuente(bold=False, color=BLANCO, size=11, italic=True)
        c.fill = fill(AZUL_MEDIO)
        c.alignment = centrado()
        ws.row_dimensions[2].height = 22

        # Tipo de día
        tipo_dia = ('🎉 Festivo' if dia_info.get('es_festivo')
                    else '🏖️ Fin de semana' if dia_info.get('es_finde')
                    else '🔧 Mantenimiento' if dia_info.get('es_mantenimiento')
                    else '💼 Día laboral')
        ws.merge_cells('A3:D3')
        c = ws['A3']
        c.value = tipo_dia
        c.font = fuente(bold=True, size=10)
        c.fill = fill('EFF6FF')
        c.alignment = centrado()
        ws.row_dimensions[3].height = 18

        ws.row_dimensions[4].height = 8  # separador

        # Contadores
        headers_res = ['', 'Trabajan AM', 'Trabajan PM', 'Descansan']
        colores_res = [BLANCO, AZUL_CLARO, NARANJA_CL, GRIS_CLARO]
        fuentes_res = [BLANCO, AZUL_MEDIO, NARANJA_OSC, GRIS_OSC]
        valores_res = ['', len(am), len(pm), len(desc)]

        for col, (h, bg, fg, v) in enumerate(
                zip(headers_res, colores_res, fuentes_res, valores_res), 1):
            # Etiqueta
            lbl = ws.cell(row=5, column=col, value=h)
            lbl.font = fuente(bold=True, color=fg, size=10)
            lbl.fill = fill(bg)
            lbl.alignment = centrado()
            lbl.border = borde_fino()
            ws.row_dimensions[5].height = 20
            # Número
            num = ws.cell(row=6, column=col, value=v if col > 1 else 'Total empleados')
            num.font = fuente(bold=True, color=fg, size=16 if col > 1 else 10)
            num.fill = fill(bg)
            num.alignment = centrado()
            num.border = borde_fino()
            ws.row_dimensions[6].height = 36

        ws.cell(row=6, column=1).value = len(trabajando) + len(descansando)
        ws.cell(row=6, column=1).font = fuente(bold=True, size=16)
        ws.cell(row=6, column=1).fill = fill('F8FAFC')

        # Separador
        ws.row_dimensions[7].height = 8

        # Mini-lista resumen
        fila = 8
        for seccion, empleados_sec, bg_h, fg_h in [
            ('👔  TRABAJAN AM', am,   AZUL_CLARO,  AZUL_MEDIO),
            ('🌙  TRABAJAN PM', pm,   NARANJA_CL,  NARANJA_MED),
            ('🛌  DESCANSAN',   desc, GRIS_CLARO,  GRIS_MED),
        ]:
            ws.merge_cells(f'A{fila}:D{fila}')
            c = ws.cell(row=fila, column=1, value=seccion)
            c.font = fuente(bold=True, color=fg_h, size=10)
            c.fill = fill(bg_h)
            c.alignment = izquierda()
            c.border = borde_fino()
            ws.row_dimensions[fila].height = 18
            fila += 1
            for emp in empleados_sec:
                nombre = f'{emp["nombre"]} {emp["apellido"]}'
                extras = []
                if emp.get('tipo') == 'doblada':
                    cubre = emp.get('cubre_a', {}) or {}
                    extras.append(f'Dobló · cubre a {cubre.get("nombre","")}')
                elif emp.get('tipo') == 'cambio':
                    extras.append('Cambio')
                if emp.get('motivo'):
                    extras.append(emp['motivo'].capitalize())
                if emp.get('companero'):
                    extras.append(f'con {emp["companero"]["nombre"]}')
                if emp.get('permiso'):
                    extras.append(f'{emp["permiso"]["horas"]}h permiso')
                ws.merge_cells(f'A{fila}:B{fila}')
                c = ws.cell(row=fila, column=1, value=nombre)
                c.font = fuente(bold=True, size=10)
                c.alignment = izquierda()
                c.border = borde_fino()
                c2 = ws.merge_cells(f'C{fila}:D{fila}')
                c2 = ws.cell(row=fila, column=3, value=' · '.join(extras))
                c2.font = fuente(italic=True, color='475569', size=9)
                c2.alignment = izquierda()
                c2.border = borde_fino()
                ws.row_dimensions[fila].height = 16
                fila += 1
            fila += 1  # separador entre secciones

        # ════════════════════════════════════════════════════════════════════
        # HOJA 2 — TRABAJAN AM
        # ════════════════════════════════════════════════════════════════════
        ws_am = wb.create_sheet('Trabajan AM')
        self._hoja_trabajan(ws_am, 'TRABAJAN AM ☀️', am, fecha_legible,
                            AZUL_MEDIO, AZUL_CLARO, AZUL_OSC=AZUL_OSCURO,
                            fill=fill, fuente=fuente, borde=borde_fino,
                            centrado=centrado, izquierda=izquierda)

        # ════════════════════════════════════════════════════════════════════
        # HOJA 3 — TRABAJAN PM
        # ════════════════════════════════════════════════════════════════════
        ws_pm = wb.create_sheet('Trabajan PM')
        self._hoja_trabajan(ws_pm, 'TRABAJAN PM 🌙', pm, fecha_legible,
                            NARANJA_MED, NARANJA_CL, AZUL_OSC=NARANJA_OSC,
                            fill=fill, fuente=fuente, borde=borde_fino,
                            centrado=centrado, izquierda=izquierda)

        # ════════════════════════════════════════════════════════════════════
        # HOJA 4 — DESCANSAN
        # ════════════════════════════════════════════════════════════════════
        ws_desc = wb.create_sheet('Descansan')
        self._hoja_descansan(ws_desc, desc, fecha_legible,
                             fill=fill, fuente=fuente, borde=borde_fino,
                             centrado=centrado, izquierda=izquierda,
                             GRIS_OSC=GRIS_OSC, GRIS_MED=GRIS_MED,
                             GRIS_CLARO=GRIS_CLARO, VERDE_CL=VERDE_CL,
                             MORADO_CL=MORADO_CL)

        # ── Respuesta HTTP ───────────────────────────────────────────────────
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        nombre_archivo = f'reporte_operacion_{fecha}.xlsx'
        response = HttpResponse(
            buf.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
        return response

    def _encabezado_hoja(self, ws, titulo, fecha_legible, color_fondo, color_texto,
                          fill, fuente, centrado, cols):
        ws.sheet_view.showGridLines = False
        n = len(cols)
        ws.merge_cells(f'A1:{chr(64+n)}1')
        c = ws['A1']
        c.value = titulo
        c.font = fuente(bold=True, color='FFFFFF', size=13)
        c.fill = fill(color_fondo)
        c.alignment = centrado()
        ws.row_dimensions[1].height = 28
        ws.merge_cells(f'A2:{chr(64+n)}2')
        c = ws['A2']
        c.value = fecha_legible.capitalize()
        c.font = fuente(italic=True, color='FFFFFF', size=10)
        c.fill = fill(color_texto)
        c.alignment = centrado()
        ws.row_dimensions[2].height = 18
        ws.row_dimensions[3].height = 6

    def _fila_header(self, ws, fila, cols, color_fondo, color_texto,
                     fill, fuente, centrado, borde):
        from openpyxl.styles import PatternFill
        for col, (ancho, label) in enumerate(cols, 1):
            c = ws.cell(row=fila, column=col, value=label)
            c.font = fuente(bold=True, color='FFFFFF', size=10)
            c.fill = fill(color_fondo)
            c.alignment = centrado()
            c.border = borde()
            ws.row_dimensions[fila].height = 20
            ws.column_dimensions[chr(64+col)].width = ancho

    def _hoja_trabajan(self, ws, titulo, empleados, fecha_legible,
                       color_enc, color_sub, AZUL_OSC,
                       fill, fuente, borde, centrado, izquierda):
        COLS = [(5,'#'), (22,'Nombre'), (18,'Apellido'), (14,'Jornada día'),
                (12,'Tipo'), (26,'Cubre a'), (14,'Permiso (h)'), (22,'Detalle permiso')]
        self._encabezado_hoja(ws, titulo, fecha_legible, AZUL_OSC, color_enc,
                               fill, fuente, centrado, COLS)
        self._fila_header(ws, 4, COLS, color_enc, 'FFFFFF',
                          fill, fuente, centrado, borde)
        TIPO_BG = {'oficial': 'DBEAFE', 'cambio': 'FEF9C3', 'doblada': 'EDE9FE'}
        TIPO_FG = {'oficial': '1D4ED8', 'cambio': '92400E', 'doblada': '5B21B6'}
        for i, emp in enumerate(empleados, 5):
            bg = 'FFFFFF' if i % 2 == 1 else 'F8FAFC'
            tipo = emp.get('tipo', 'oficial')
            cubre = (emp.get('cubre_a') or {}).get('nombre', '')
            perm = emp.get('permiso') or {}
            vals = [i - 4,
                    emp['nombre'], emp['apellido'],
                    emp.get('jornada_dia', ''),
                    tipo.capitalize(),
                    cubre,
                    perm.get('horas', ''),
                    f'{perm.get("tipo","")} — {perm.get("especificacion","")}' if perm else '']
            for col, v in enumerate(vals, 1):
                c = ws.cell(row=i, column=col, value=v)
                c.border = borde()
                c.alignment = izquierda() if col > 1 else centrado()
                ws.row_dimensions[i].height = 16
                if col == 5 and tipo in TIPO_BG:
                    c.fill = fill(TIPO_BG[tipo])
                    c.font = fuente(bold=True, color=TIPO_FG[tipo], size=9)
                elif col == 6 and cubre:
                    c.font = fuente(italic=True, color='5B21B6', size=10)
                else:
                    c.fill = fill(bg)
                    c.font = fuente(size=10)
        if not empleados:
            ws.merge_cells(f'A5:{chr(64+len(COLS))}5')
            c = ws['A5']
            c.value = 'No hay exploradores en esta jornada'
            c.font = fuente(italic=True, color='94A3B8', size=10)
            c.alignment = centrado()

    def _hoja_descansan(self, ws, empleados, fecha_legible,
                        fill, fuente, borde, centrado, izquierda,
                        GRIS_OSC, GRIS_MED, GRIS_CLARO, VERDE_CL, MORADO_CL):
        COLS = [(5,'#'), (22,'Nombre'), (18,'Apellido'), (12,'Jornada base'),
                (28,'Motivo'), (26,'Compañero'), (14,'Permiso (h)'), (22,'Detalle permiso')]
        self._encabezado_hoja(ws, 'DESCANSAN 🛌', fecha_legible, GRIS_OSC, GRIS_MED,
                               fill, fuente, centrado, COLS)
        self._fila_header(ws, 4, COLS, GRIS_MED, 'FFFFFF',
                          fill, fuente, centrado, borde)
        MOTIVO_BG = {
            'cedió su jornada':          MORADO_CL,
            'paga doblada':              MORADO_CL,
            'doblada permanente':        MORADO_CL,
            'cambio de día de descanso': VERDE_CL,
            'descanso de temporada':     'FEF9C3',
            'lunes de mantenimiento':    GRIS_CLARO,
            'descanso de fin de semana': 'F0FDF4',
            'festivo':                   'FEF2F2',
        }
        for i, emp in enumerate(empleados, 5):
            bg = 'FFFFFF' if i % 2 == 1 else 'F8FAFC'
            motivo = (emp.get('motivo') or '').lower()
            comp = (emp.get('companero') or {}).get('nombre', '')
            perm = emp.get('permiso') or {}
            vals = [i - 4,
                    emp['nombre'], emp['apellido'],
                    emp.get('jornada_base', ''),
                    (emp.get('motivo') or '').capitalize(),
                    comp,
                    perm.get('horas', ''),
                    f'{perm.get("tipo","")} — {perm.get("especificacion","")}' if perm else '']
            motivo_bg = MOTIVO_BG.get(motivo, bg)
            for col, v in enumerate(vals, 1):
                c = ws.cell(row=i, column=col, value=v)
                c.border = borde()
                c.alignment = izquierda() if col > 1 else centrado()
                ws.row_dimensions[i].height = 16
                if col == 5:
                    c.fill = fill(motivo_bg)
                    c.font = fuente(bold=True, color=GRIS_OSC, size=9)
                elif col == 6 and comp:
                    c.font = fuente(italic=True, color='5B21B6', size=10)
                    c.fill = fill(bg)
                else:
                    c.fill = fill(bg)
                    c.font = fuente(size=10)
        if not empleados:
            ws.merge_cells(f'A5:{chr(64+len(COLS))}5')
            c = ws['A5']
            c.value = 'Todos los exploradores trabajan este día'
            c.font = fuente(italic=True, color='94A3B8', size=10)
            c.alignment = centrado()


class TurnosPorDiaView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            fecha = request.GET.get('fecha')
            if not fecha:
                return JsonResponse({'error': 'Debe seleccionar una fecha'}, status=400)
            data = TurnoService.get_exploradores_por_jornada(fecha)
            # Los datos ya vienen como diccionarios desde el servicio
            # Solo necesitamos retornarlos directamente
            return JsonResponse({'am': data.get('am', []), 'pm': data.get('pm', [])})
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Error en TurnosPorDiaView: {str(e)}', exc_info=True)
            return JsonResponse({'error': f'Error al obtener turnos: {str(e)}'}, status=500)


class TurnosPorMesView(LoginRequiredMixin, View):
    def get(self, request):
        fecha_inicio = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')
        if not fecha_inicio or not fecha_fin:
            return JsonResponse({'error': 'Debe enviar fecha_inicio y fecha_fin'}, status=400)
        data = TurnoService.get_exploradores_por_jornada_rango(fecha_inicio, fecha_fin)
        # Serializar empleados (ya son dicts)
        serializado = {}
        for dia, grupos in data.items():
            serializado[dia] = {
                'am': grupos['am'],
                'pm': grupos['pm'],
            }
        return JsonResponse(serializado)


class MisTurnosPorMesView(LoginRequiredMixin, View):
    """Vista para obtener jornadas de un mes específico (cálculo dinámico)
    FASE 3.5: Optimizada con caché para mejorar rendimiento
    """
    
    def get(self, request):
        if not hasattr(request.user, 'empleado'):
            return JsonResponse({'error': 'Usuario no es empleado'}, status=400)
        
        empleado = request.user.empleado
        mes = request.GET.get('mes')  # formato: '08' o '8'
        anio = request.GET.get('anio')  # formato: '2025'
        
        if not mes or not anio:
            return JsonResponse({'error': 'Debe enviar mes y anio'}, status=400)
        
        # Validación y normalización de mes/año
        try:
            mes_int = int(mes)
            anio_int = int(anio)
            if not (1 <= mes_int <= 12):
                return JsonResponse({'error': 'Mes invalido'}, status=400)
            # Normalizar representaciones
            mes = f"{mes_int:02d}"
            anio = str(anio_int)
        except ValueError:
            return JsonResponse({'error': 'anio/mes deben ser numéricos'}, status=400)
        
        # FASE 3.5: Generar clave de caché única para este empleado y mes (normalizados)
        from core.services.cache_service import CacheService
        
        cache_key = f'turnos_mes_{empleado.id}_{anio}_{mes}'
        
        # FASE 3.5: Intentar obtener datos del caché
        cached_data = CacheService.get(cache_key)
        if cached_data is not None:
            return JsonResponse(cached_data)
        
        try:
            # Calcular inicio y fin del mes solicitado
            fecha_inicio = datetime.strptime(f"{anio}-{mes}-01", "%Y-%m-%d").date()
            if int(mes) == 12:
                fecha_fin = datetime.strptime(f"{int(anio)+1}-01-01", "%Y-%m-%d").date() - timedelta(days=1)
            else:
                fecha_fin = datetime.strptime(f"{anio}-{int(mes)+1:02d}-01", "%Y-%m-%d").date() - timedelta(days=1)
            
            # Obtener turnos del mes solicitado (optimizado, evitando N+1)
            turnos_mes = (
                Turno.objects
                .filter(explorador=empleado, fecha__gte=fecha_inicio, fecha__lte=fecha_fin)
                .select_related('jornada', 'sala')
                .order_by('fecha', 'jornada__nombre')
            )
            
            # CORRECCIÓN: Agrupar turnos por fecha para manejar dobladas (AM+PM)
            # En lugar de sobrescribir, crear listas de turnos por fecha
            turnos_por_fecha = {}
            for t in turnos_mes:
                if t.fecha not in turnos_por_fecha:
                    turnos_por_fecha[t.fecha] = []
                turnos_por_fecha[t.fecha].append(t)
            
            # FASE 3.2: Obtener jornada predeterminada (usar first() en lugar de get() para evitar errores)
            # Obtener la jornada más reciente por fecha_inicio
            jornada_predeterminada = (
                AsignarJornadaExplorador.objects
                .filter(explorador=empleado)
                .select_related('jornada')
                .order_by('-fecha_inicio')
                .first()
            )
            jornada_base = (jornada_predeterminada.jornada.nombre if jornada_predeterminada else None)
            
            # Validar que el empleado tenga jornada asignada
            if not jornada_base:
                return JsonResponse({
                    'error': f'El empleado {empleado.nombre} {empleado.apellido} no tiene jornada asignada. '
                             'Todos los exploradores deben tener una jornada (AM o PM) asignada.'
                }, status=400)

            from core.utils.jornada_utils import JornadaUtils
            def calcular_jornada_dia(j_base, fecha):
                return JornadaUtils.calcular_jornada_dia(j_base, fecha)

            from turnos.services.descanso_semana_service import DescansoSemanaService as _DSS
            def calcular_predeterminado(fecha):
                """
                Jornada PREDETERMINADA del día (lo que sería SIN ningún cambio), considerando la
                TEMPORADA además de base+alternancia. En un día de temporada donde el grupo del
                empleado descansa, lo predeterminado es DESCANSO (no su jornada base); si el grupo
                CONTRARIO descansa, este cubre el día completo (DOBLADA). Sin esto, el detalle de
                Mis Turnos decía "tu jornada predeterminada era PM" cuando en realidad ese día
                descansaba. Devuelve 'AM'/'PM'/'DOBLADA'/'DESCANSO'.
                """
                if fecha.weekday() < 5:
                    if _DSS.es_descanso_semana_manual(jornada_base, fecha):
                        return 'DESCANSO'
                    contraria = 'PM' if jornada_base == 'AM' else 'AM'
                    if _DSS.es_descanso_semana_manual(contraria, fecha):
                        return 'DOBLADA'
                    from turnos.models import DiaEspecial as _DE
                    if _DE.es_mantenimiento_efectivo(fecha):
                        return 'DESCANSO'
                return calcular_jornada_dia(jornada_base, fecha)

            # FUENTE DE VERDAD ÚNICA (batch): estado predeterminado/calculado por día
            # (alternancia de finde, temporada, mantenimiento, base). Reemplaza la lógica
            # de capas duplicada que antes vivía en este bucle. Ver
            # docs/AUDITORIA_FUENTE_VERDAD_TURNOS.md
            from turnos.services.turno_service import TurnoService as _TSestado
            estados_mes = _TSestado.estado_mes(empleado, int(anio), int(mes))
            
            # La sala es informativa (especialidad del explorador vía CompetenciaEmpleado);
            # ya no existe asignación de sala por período.
            asignaciones_activas = None

            # DESCANSOS por solicitud aprobada (DOBLADA, D FDS, CAMBIO DESCANSO y DOBLADA
            # PERMANENTE): FUENTE UNICA compartida con estado_dia/estado_mes. Un solo batch,
            # SIEMPRE por FECHA especifica (no por patron de weekday), con la info que consume
            # el detalle del dia. Reemplaza los antiguos dicts inline (que reimplementaban esta
            # regla y divergian, causando atribuciones al companero equivocado).
            from solicitudes.services.descanso_solicitud_service import DescansoPorSolicitudService
            descansos_sol = DescansoPorSolicitudService.en_rango(empleado, fecha_inicio, fecha_fin)

            # PERMISOS ESPECIALES del explorador que caen en el mes (puntual o permanente).
            # No cambian la jornada; se muestran como indicador en el día.
            from permisos.models import PermisoEspecial
            permisos_por_fecha = {}
            pe_qs = (
                PermisoEspecial.objects
                .filter(empleado=empleado, estado__in=['APROBADO', 'PENDIENTE'],
                        fecha_inicio__lte=fecha_fin, fecha_fin__gte=fecha_inicio)
                .select_related('cubre')
            )
            for p in pe_qs:
                p_info = {
                    'horas': float(p.tiempo or 0),
                    'especificacion': p.especificacion or '',
                    'tipo': p.get_tipo_display(),
                    'cubre': f"{p.cubre.nombre} {p.cubre.apellido}" if p.cubre else None,
                    'estado': p.estado,
                    'es_permanente': p.es_permanente,
                }
                if p.es_permanente:
                    dias_set = {int(x) for x in p.dias_semana.split(',') if x.strip().isdigit()}
                    di = max(p.fecha_inicio, fecha_inicio)
                    dfin = min(p.fecha_fin, fecha_fin)
                    while di <= dfin:
                        if di.weekday() in dias_set:
                            permisos_por_fecha[di.strftime('%Y-%m-%d')] = p_info
                        di += timedelta(days=1)
                else:
                    if fecha_inicio <= p.fecha_inicio <= fecha_fin:
                        permisos_por_fecha[p.fecha_inicio.strftime('%Y-%m-%d')] = p_info
                    # Media jornada de temporada: el permiso también toca el día de COMPENSACIÓN
                    # (trabajas la otra media ahí), así que se marca también ese día.
                    fcomp = getattr(p, 'fecha_compensacion', None)
                    if fcomp and fecha_inicio <= fcomp <= fecha_fin:
                        permisos_por_fecha[fcomp.strftime('%Y-%m-%d')] = p_info

            # RESTRICCIONES del empleado vigentes en el mes (aplican TODOS los días del rango;
            # fecha_fin nula = indefinida/en curso).
            from empleados.models import RestriccionEmpleado
            restricciones_por_fecha = {}
            rest_qs = RestriccionEmpleado.objects.filter(
                empleado=empleado, fecha_inicio__lte=fecha_fin
            ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio))
            for r in rest_qs:
                r_info = {
                    'tipo': r.tipo_restriccion or 'Restricción',
                    'recomendacion': r.recomendacion or '',
                    'indefinida': r.fecha_fin is None,
                }
                ini = max(r.fecha_inicio, fecha_inicio)
                fin = min(r.fecha_fin, fecha_fin) if r.fecha_fin else fecha_fin
                di = ini
                while di <= fin:
                    restricciones_por_fecha[di.strftime('%Y-%m-%d')] = r_info
                    di += timedelta(days=1)

            # SANCIONES del empleado vigentes en el mes (no puede solicitar nada esos días)
            from empleados.models import SancionEmpleado
            sanciones_por_fecha = {}
            sanc_qs = SancionEmpleado.objects.filter(
                explorador=empleado, fecha_inicio__lte=fecha_fin
            ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio))
            for s in sanc_qs:
                s_info = {
                    'motivo': s.motivo or '',
                    'desde': s.fecha_inicio.strftime('%d/%m/%Y'),
                    'hasta': s.fecha_fin.strftime('%d/%m/%Y') if s.fecha_fin else None,
                }
                ini = max(s.fecha_inicio, fecha_inicio)
                fin = min(s.fecha_fin, fecha_fin) if s.fecha_fin else fecha_fin
                di = ini
                while di <= fin:
                    sanciones_por_fecha[di.strftime('%Y-%m-%d')] = s_info
                    di += timedelta(days=1)

            # Crear estructura de datos para el mes
            turnos_mes_dict = {}
            dias_mes = (fecha_fin - fecha_inicio).days + 1
            for i in range(dias_mes):
                fecha = fecha_inicio + timedelta(days=i)
                turnos_dia = turnos_por_fecha.get(fecha, [])

                # FESTIVO entre semana: la fuente de verdad manda sobre el horario
                # predeterminado (la jornada que dobla por rotación trabaja AM+PM, la otra
                # descansa). Solo un cambio EXPLÍCITO se respeta: en ese caso estado_mes
                # devuelve fuente='turno' y caemos al flujo normal de abajo.
                _est_fv = estados_mes.get(fecha)
                if _est_fv and _est_fv.get('fuente') == 'festivo':
                    if _est_fv['trabaja']:
                        turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                            'jornada': 'DOBLADA',
                            'sala': 'Por asignar',
                            'tipo': 'predeterminado',
                            'es_cambio': False,
                            'es_doblada': True,
                            'jornada_predeterminada': 'DOBLADA',
                            'coincide_con_predeterminada': True,
                            'turno_id': None,
                            'es_festivo': True,
                        }
                    else:
                        turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                            'jornada': None,
                            'sala': None,
                            'tipo': 'descanso',
                            'es_cambio': False,
                            'es_descanso': True,
                            'jornada_predeterminada': None,
                            'coincide_con_predeterminada': False,
                            'turno_id': None,
                            'es_festivo': True,
                            'descanso_info': {'tipo': 'festivo'},
                        }
                    continue

                # Una cesión COMPLETA aprobada tiene prioridad sobre cualquier Turno residual
                # (el empleado cedió TODO el día aunque queden registros huérfanos). Una cesión
                # PARCIAL, en cambio, deja la otra jornada como Turno real válido: NO se borra,
                # para que Mis Turnos muestre la jornada restante (no "día libre"). La fuente única
                # solo incluye la fecha cuando el día quedó libre COMPLETO (cesión completa o ambas
                # medias jornadas), así que su presencia como 'cedió su jornada' equivale a completa.
                _desc_ced = descansos_sol.get(fecha)
                if _desc_ced and _desc_ced.get('motivo') == 'cedió su jornada' and turnos_dia:
                    turnos_dia = []

                if turnos_dia:
                    # Hay turno(s) asignado(s) (puede ser cambio aprobado o doblada)
                    # OPTIMIZACIÓN: Calcular jornada_display desde turnos_dia sin consultas extra
                    jornadas_turnos = [t.jornada.nombre.upper() for t in turnos_dia if t.jornada]
                    if 'AM' in jornadas_turnos and 'PM' in jornadas_turnos:
                        jornada_display = 'DOBLADA'
                    elif 'AM' in jornadas_turnos:
                        jornada_display = 'AM'
                    elif 'PM' in jornadas_turnos:
                        jornada_display = 'PM'
                    else:
                        jornada_display = calcular_jornada_dia(jornada_base, fecha) or ''

                    jornada_predeterminada = calcular_predeterminado(fecha)
                    
                    # Detectar si es doblada
                    es_doblada = jornada_display == 'DOBLADA'

                    # Determinar tipo de cambio (si todos los turnos tienen el mismo tipo_cambio)
                    tipos_cambio = [t.tipo_cambio for t in turnos_dia if t.tipo_cambio]
                    es_cambio = len(tipos_cambio) > 0
                    tipo_cambio_principal = tipos_cambio[0] if tipos_cambio else None
                    
                    # Determinar sala(s)
                    salas = [t.sala.nombre for t in turnos_dia if t.sala]
                    if len(set(salas)) == 1:
                        # Todas las salas son iguales
                        sala_display = salas[0]
                    else:
                        # Salas diferentes (raro, pero posible)
                        sala_display = ', '.join(set(salas)) if salas else 'Por asignar'
                    
                    coincide_con_predeterminada = jornada_display == jornada_predeterminada if jornada_display else False
                    
                    # Usar el primer turno como referencia (para compatibilidad con código existente)
                    turno_principal = turnos_dia[0]
                    
                    turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                        'jornada': jornada_display,  # Usar jornada_display (puede ser 'DOBLADA')
                        'sala': sala_display,
                        # 'asignado' solo cuando fue creado por CT/DOBLADA (tipo_cambio != null).
                        # 'predeterminado' cuando el turno existe en BD pero sin tipo_cambio (horario importado).
                        'tipo': 'asignado' if es_cambio else 'predeterminado',
                        'es_cambio': es_cambio,
                        'es_doblada': es_doblada,  # Flag para frontend
                        'tipo_cambio': tipo_cambio_principal,  # p. ej. 'PAGO REPROGRAMADO' (detalle en Mis Turnos)
                        'jornada_predeterminada': jornada_predeterminada,
                        'coincide_con_predeterminada': coincide_con_predeterminada,
                        'turno_id': turno_principal.id
                    }
                else:
                    # No hay turno asignado: descansa por una solicitud aprobada?
                    # FUENTE UNICA (descansos_sol): DOBLADA, D FDS, CAMBIO DESCANSO y DOBLADA PERM.
                    desc = descansos_sol.get(fecha)
                    esta_descansando = desc is not None

                    if esta_descansando:
                        _cmp = desc.get("companero") or {}
                        _tipo = desc.get("tipo")
                        turnos_mes_dict[fecha.strftime("%Y-%m-%d")] = {
                            "jornada": None,
                            "sala": None,
                            "tipo": "descanso",
                            "es_cambio": False,
                            "es_descanso": True,
                            "jornada_predeterminada": calcular_jornada_dia(jornada_base, fecha),
                            "coincide_con_predeterminada": False,
                            "turno_id": None,
                            "descanso_info": {
                                "tipo": _tipo,
                                "origen": desc.get("origen"),
                                "companero_nombre": _cmp.get("nombre"),
                                "companero_id": _cmp.get("id"),
                                "solicitud_id": desc.get("solicitud_id"),
                                "fecha_relacionada": (desc.get("fecha_pago") if _tipo == "cedio" else desc.get("fecha_cesion")),
                                "fecha_cesion": desc.get("fecha_cesion"),
                                "fecha_pago": desc.get("fecha_pago"),
                                "fecha_solicitud": desc.get("fecha_solicitud"),
                                "fecha_aprobacion": desc.get("fecha_aprobacion"),
                                "tipo_cesion": desc.get("tipo_cesion"),
                                "jornada_cedida": desc.get("jornada_cedida"),
                            }
                        }
                    else:
                        # No hay turno asignado: el estado lo resuelve la FUENTE DE VERDAD
                        # única (estado_mes), que ya aplica alternancia de finde, temporada y
                        # mantenimiento en el orden correcto. Antes esta lógica estaba duplicada
                        # aquí; ahora solo se mapea su resultado al formato de la respuesta.
                        est = estados_mes.get(fecha) or {}

                        if est.get('trabaja') and est.get('jornada') == 'DOBLADA':
                            # Fin de semana que le corresponde trabajar → jornada predeterminada DOBLADA
                            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                                'jornada': 'DOBLADA',
                                'sala': 'Por asignar',
                                'tipo': 'predeterminado',
                                'es_cambio': False,
                                'es_doblada': True,  # Flag para frontend
                                'jornada_predeterminada': 'DOBLADA',
                                'coincide_con_predeterminada': True,
                                'turno_id': None
                            }
                        elif (not est.get('trabaja')) and est.get('fuente') in ('temporada', 'mantenimiento'):
                            # Descanso de ENTRE SEMANA (temporada/mantenimiento)
                            motivo_descanso_semana = 'temporada' if est.get('fuente') == 'temporada' else 'mantenimiento'
                            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                                'jornada': None,
                                'sala': None,
                                'tipo': 'descanso',
                                'es_cambio': False,
                                'es_descanso': True,
                                'jornada_predeterminada': calcular_jornada_dia(jornada_base, fecha),
                                'coincide_con_predeterminada': False,
                                'turno_id': None,
                                'descanso_info': {
                                    'tipo': 'descanso_semana',
                                    'motivo': motivo_descanso_semana,  # 'manual' o 'mantenimiento'
                                },
                            }
                        else:
                            # Día normal (jornada base entre semana) o descanso de fin de semana
                            # (que conserva el comportamiento histórico: jornada = "Descanso").
                            jornada_nombre = calcular_jornada_dia(jornada_base, fecha)

                            sala_nombre = 'Por asignar'
                            if asignaciones_activas:
                                sala_nombre = asignaciones_activas.sala.nombre

                            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                                'jornada': jornada_nombre,
                                'sala': sala_nombre,
                                'tipo': 'predeterminado',
                                'es_cambio': False,
                                'es_descanso': False,
                                'jornada_predeterminada': jornada_nombre,
                                'coincide_con_predeterminada': True,
                                'turno_id': None
                            }
            
            # FASE 3.3: Obtener información de solicitudes para turnos con cambios (optimizado)
            # Limitar a las solicitudes más recientes para mejorar rendimiento
            from solicitudes.models import SolicitudCambio
            # CORRECCIÓN: turnos_por_fecha ahora contiene listas de turnos, no turnos individuales
            turno_ids_con_cambio = []
            for turnos_lista in turnos_por_fecha.values():
                for turno in turnos_lista:
                    if turno.tipo_cambio is not None:
                        turno_ids_con_cambio.append(turno.id)
            solicitudes_info = {}
            
            if turno_ids_con_cambio:
                # FASE 3.3: Limitar a las 50 solicitudes más recientes para evitar consultas lentas
                # Obtener todas las solicitudes que afectaron estos turnos
                solicitudes = SolicitudCambio.objects.filter(
                    Q(turno_origen_id__in=turno_ids_con_cambio) | Q(turno_destino_id__in=turno_ids_con_cambio),
                    estado='aprobada'
                ).select_related('explorador_solicitante', 'explorador_receptor').order_by('-fecha_resolucion', '-id')[:50]
                
                # Procesar solicitudes en orden descendente (más reciente primero)
                # Para cada turno, solo guardar la primera solicitud encontrada (más reciente)
                for solicitud in solicitudes:
                    # Para turno_origen (solicitante)
                    if solicitud.turno_origen_id and solicitud.turno_origen_id in turno_ids_con_cambio:
                        if solicitud.turno_origen_id not in solicitudes_info:
                            solicitudes_info[solicitud.turno_origen_id] = {
                                'solicitud_id': solicitud.id,
                                'companero_nombre': solicitud.explorador_receptor.nombre,
                                'rol': 'solicitante',
                                'fecha_resolucion': solicitud.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_resolucion else None
                            }
                    
                    # Para turno_destino (receptor)
                    if solicitud.turno_destino_id and solicitud.turno_destino_id in turno_ids_con_cambio:
                        if solicitud.turno_destino_id not in solicitudes_info:
                            solicitudes_info[solicitud.turno_destino_id] = {
                                'solicitud_id': solicitud.id,
                                'companero_nombre': solicitud.explorador_solicitante.nombre,
                                'rol': 'receptor',
                                'fecha_resolucion': solicitud.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_resolucion else None
                            }
            
            # Agregar información de solicitudes a los turnos
            # Para dobladas, buscar en todos los turnos de esa fecha
            for fecha_str, info in turnos_mes_dict.items():
                turno_id = info.get('turno_id')
                solicitud_encontrada = None
                
                # Si hay turno_id, buscar directamente
                if turno_id and turno_id in solicitudes_info:
                    solicitud_encontrada = solicitudes_info[turno_id]
                else:
                    # Si no se encontró, puede ser una doblada con múltiples turnos
                    # Buscar en todos los turnos de esa fecha
                    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                    turnos_fecha = turnos_por_fecha.get(fecha_obj, [])
                    for turno in turnos_fecha:
                        if turno.id in solicitudes_info:
                            solicitud_encontrada = solicitudes_info[turno.id]
                            break  # Usar la primera encontrada
                
                info['solicitud_info'] = solicitud_encontrada
            
            # BÚSQUEDA ADICIONAL PARA DOBLADAS
            # Las dobladas no tienen turno_origen/turno_destino asignados, así que buscamos por fecha y empleado
            # Solo buscar para fechas que aún no tienen solicitud_info y tienen cambios (es_cambio o es_doblada)
            fechas_sin_solicitud = [
                fecha_str for fecha_str, info in turnos_mes_dict.items()
                if not info.get('solicitud_info') and (info.get('es_cambio', False) or info.get('es_doblada', False))
            ]
            
            if fechas_sin_solicitud:
                # Convertir fechas string a objetos date
                fechas_obj = [datetime.strptime(f, '%Y-%m-%d').date() for f in fechas_sin_solicitud]
                
                # IMPORTANTE: Para dobladas, necesitamos buscar en ambos escenarios:
                # 1. Empleado como SOLICITANTE en fecha de cesión (empleado cedió, receptor trabaja)
                # 2. Empleado como RECEPTOR en fecha de cesión (empleado trabaja/dobla, solicitante descansa)
                # 3. Empleado como RECEPTOR en fecha de pago (empleado descansa, solicitante trabaja/dobla)
                # 4. Empleado como SOLICITANTE en fecha de pago (empleado trabaja/dobla, receptor descansa)
                
                # Buscar donde el empleado es SOLICITANTE y la fecha es de CESIÓN (empleado descansa, receptor trabaja)
                solicitudes_solicitante_cesion = SolicitudCambio.objects.filter(
                    explorador_solicitante=empleado,
                    tipo_cambio__nombre='DOBLADA',
                    fecha_cambio_turno__in=fechas_obj,
                    estado='aprobada'
                ).select_related('explorador_receptor', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')
                
                # Buscar donde el empleado es RECEPTOR y la fecha es de CESIÓN (empleado trabaja/dobla, solicitante descansa)
                solicitudes_receptor_cesion = SolicitudCambio.objects.filter(
                    explorador_receptor=empleado,
                    tipo_cambio__nombre='DOBLADA',
                    fecha_cambio_turno__in=fechas_obj,
                    estado='aprobada'
                ).select_related('explorador_solicitante', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')
                
                # Buscar donde el empleado es RECEPTOR y la fecha es de PAGO (empleado descansa, solicitante trabaja/dobla)
                solicitudes_receptor_pago = SolicitudCambio.objects.filter(
                    explorador_receptor=empleado,
                    tipo_cambio__nombre='DOBLADA',
                    doblada__fecha_pago__in=fechas_obj,
                    estado='aprobada'
                ).select_related('explorador_solicitante', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')
                
                # Buscar donde el empleado es SOLICITANTE y la fecha es de PAGO (empleado trabaja/dobla, receptor descansa)
                solicitudes_solicitante_pago = SolicitudCambio.objects.filter(
                    explorador_solicitante=empleado,
                    tipo_cambio__nombre='DOBLADA',
                    doblada__fecha_pago__in=fechas_obj,
                    estado='aprobada'
                ).select_related('explorador_receptor', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')
                
                # Crear diccionarios para búsqueda rápida (solo la más reciente por fecha)
                dobladas_dict = {}
                
                # Solicitudes donde empleado es solicitante en fecha de cesión
                for sol in solicitudes_solicitante_cesion:
                    fecha_str = sol.fecha_cambio_turno.strftime('%Y-%m-%d')
                    if fecha_str not in dobladas_dict:
                        dobladas_dict[fecha_str] = {
                            'solicitud': sol,
                            'companero': sol.explorador_receptor.nombre,
                            'rol': 'solicitante'
                        }
                
                # Solicitudes donde empleado es receptor en fecha de cesión
                for sol in solicitudes_receptor_cesion:
                    fecha_str = sol.fecha_cambio_turno.strftime('%Y-%m-%d')
                    if fecha_str not in dobladas_dict:
                        dobladas_dict[fecha_str] = {
                            'solicitud': sol,
                            'companero': sol.explorador_solicitante.nombre,
                            'rol': 'receptor'
                        }
                
                # Solicitudes donde empleado es receptor en fecha de pago
                for sol in solicitudes_receptor_pago:
                    if sol.doblada and sol.doblada.fecha_pago:
                        fecha_str = sol.doblada.fecha_pago.strftime('%Y-%m-%d')
                        if fecha_str not in dobladas_dict:
                            dobladas_dict[fecha_str] = {
                                'solicitud': sol,
                                'companero': sol.explorador_solicitante.nombre,
                                'rol': 'receptor'
                            }
                
                # Solicitudes donde empleado es solicitante en fecha de pago
                for sol in solicitudes_solicitante_pago:
                    if sol.doblada and sol.doblada.fecha_pago:
                        fecha_str = sol.doblada.fecha_pago.strftime('%Y-%m-%d')
                        if fecha_str not in dobladas_dict:
                            dobladas_dict[fecha_str] = {
                                'solicitud': sol,
                                'companero': sol.explorador_receptor.nombre,
                                'rol': 'solicitante'
                            }
                
                # CAMBIO DESCANSO (intercambio de día de descanso de temporada): el solicitante
                # trabaja su día completo en fecha_cambio_turno y el receptor en doblada.fecha_pago.
                # Adjuntamos el compañero (mismo dict que las dobladas) para que Mis Turnos muestre
                # "con X" en el día doblado por el intercambio.
                cd_sol = SolicitudCambio.objects.filter(
                    explorador_solicitante=empleado, tipo_cambio__nombre='CAMBIO DESCANSO',
                    fecha_cambio_turno__in=fechas_obj, estado='aprobada'
                ).select_related('explorador_receptor', 'doblada').order_by('-fecha_resolucion', '-id')
                for sol in cd_sol:
                    fecha_str = sol.fecha_cambio_turno.strftime('%Y-%m-%d')
                    dobladas_dict.setdefault(fecha_str, {
                        'solicitud': sol, 'companero': sol.explorador_receptor.nombre, 'rol': 'solicitante'})

                cd_rec = SolicitudCambio.objects.filter(
                    explorador_receptor=empleado, tipo_cambio__nombre='CAMBIO DESCANSO',
                    doblada__fecha_pago__in=fechas_obj, estado='aprobada'
                ).select_related('explorador_solicitante', 'doblada').order_by('-fecha_resolucion', '-id')
                for sol in cd_rec:
                    if sol.doblada and sol.doblada.fecha_pago:
                        fecha_str = sol.doblada.fecha_pago.strftime('%Y-%m-%d')
                        dobladas_dict.setdefault(fecha_str, {
                            'solicitud': sol, 'companero': sol.explorador_solicitante.nombre, 'rol': 'receptor'})

                # Asociar información de dobladas a los turnos
                for fecha_str in fechas_sin_solicitud:
                    if fecha_str not in turnos_mes_dict:
                        continue
                    
                    info = turnos_mes_dict[fecha_str]
                    if info.get('solicitud_info'):
                        continue  # Ya tiene información
                    
                    doblada_info = dobladas_dict.get(fecha_str)
                    if doblada_info:
                        sol = doblada_info['solicitud']
                        info['solicitud_info'] = {
                            'solicitud_id': sol.id,
                            'companero_nombre': doblada_info['companero'],
                            'rol': doblada_info['rol'],
                            'fecha_resolucion': sol.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if sol.fecha_resolucion else None
                        }
            
            # Adjuntar el permiso especial (si lo hay) a cada día — antes de cachear
            for _fstr, _pinfo in permisos_por_fecha.items():
                if _fstr in turnos_mes_dict:
                    turnos_mes_dict[_fstr]['permiso'] = _pinfo

            # Adjuntar la restricción (si la hay) a cada día
            for _fstr, _rinfo in restricciones_por_fecha.items():
                if _fstr in turnos_mes_dict:
                    turnos_mes_dict[_fstr]['restriccion'] = _rinfo

            # Adjuntar la sanción (si la hay) a cada día
            for _fstr, _sinfo in sanciones_por_fecha.items():
                if _fstr in turnos_mes_dict:
                    turnos_mes_dict[_fstr]['sancion'] = _sinfo

            # FASE 3.5: Guardar en caché usando CacheService
            # Los datos de turnos no cambian frecuentemente, así que 1 hora es seguro
            from core.services.cache_service import CACHE_TTL_LONG
            CacheService.set(cache_key, turnos_mes_dict, ttl=CACHE_TTL_LONG)

            return JsonResponse(turnos_mes_dict)
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"ERROR en MisTurnosPorMesView: {str(e)}")
            print(f"Traceback: {error_trace}")
            return JsonResponse({
                'error': f'Error al procesar fechas: {str(e)}',
                'traceback': error_trace if request.user.is_staff else None  # Solo mostrar traceback a staff
            }, status=400)


class DiasFestivosView(LoginRequiredMixin, View):
    """
    Vista para obtener días festivos.
    Útil para mostrar en calendarios y validaciones.
    
    ESTRATEGIA HÍBRIDA:
    1. Intenta usar biblioteca calendario-colombiano (más precisa)
    2. Si no está disponible, usa festivos de BD
    3. Combina ambos para máxima precisión
    
    OPTIMIZACIÓN: Usa caché para evitar consultas repetidas a la BD.
    Los festivos no cambian frecuentemente, así que se cachean por 1 hora.
    """
    
    def _obtener_festivos_calculados(self, año_inicio, año_fin):
        """
        Obtiene festivos calculados usando biblioteca externa si está disponible.
        Retorna dict con fecha (YYYY-MM-DD) como clave y descripción como valor.
        """
        festivos_calculados = {}
        
        try:
            # Intentar usar biblioteca calendario-colombiano
            from calendario_colombiano import CalendarioColombiano
            from datetime import date, timedelta
            
            calendario = CalendarioColombiano()
            
            # Obtener festivos para el rango de años
            fecha_inicio = date(año_inicio, 1, 1)
            fecha_fin = date(año_fin, 12, 31)
            fecha_actual = fecha_inicio
            
            while fecha_actual <= fecha_fin:
                if calendario.es_festivo(fecha_actual):
                    fecha_str = fecha_actual.strftime('%Y-%m-%d')
                    # Obtener nombre del festivo si es posible
                    nombre = getattr(calendario, 'nombre_festivo', lambda d: 'Día festivo')(fecha_actual)
                    festivos_calculados[fecha_str] = nombre
                fecha_actual += timedelta(days=1)
                
        except ImportError:
            # Si no está instalada la biblioteca, retornar vacío
            # El frontend usará su cálculo JavaScript como respaldo
            pass
        except Exception as e:
            # En caso de error, continuar sin festivos calculados
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f'Error al calcular festivos con biblioteca externa: {e}')
        
        return festivos_calculados
    
    def get(self, request):
        """
        Obtener días festivos.
        
        Parámetros opcionales:
        - fecha_inicio: Fecha de inicio (formato: YYYY-MM-DD)
        - fecha_fin: Fecha de fin (formato: YYYY-MM-DD)
        - anio: Año específico (formato: YYYY)
        - mes: Mes específico (formato: MM)
        - sin_cache: Si es 'true', omite el caché (útil para testing)
        
        Si no se proporcionan parámetros, devuelve todos los festivos activos.
        """
        try:
            fecha_inicio = request.GET.get('fecha_inicio')
            fecha_fin = request.GET.get('fecha_fin')
            anio = request.GET.get('anio')
            mes = request.GET.get('mes')
            sin_cache = request.GET.get('sin_cache', 'false').lower() == 'true'
            
            # Generar clave de caché basada en los filtros
            cache_key = 'dias_festivos'
            if fecha_inicio:
                cache_key += f'_desde_{fecha_inicio}'
            if fecha_fin:
                cache_key += f'_hasta_{fecha_fin}'
            if anio:
                cache_key += f'_anio_{anio}'
            if mes:
                cache_key += f'_mes_{mes}'
            
            # Intentar obtener del caché usando CacheService (solo si no se solicita sin caché)
            if not sin_cache:
                from core.services.cache_service import CacheService
                cached_data = CacheService.get(cache_key)
                if cached_data is not None:
                    return JsonResponse(cached_data)
            
            # Construir query base
            festivos = DiaEspecial.objects.filter(
                tipo='festivo',
                activo=True
            )
            
            # Filtrar por rango de fechas si se proporciona
            if fecha_inicio and fecha_fin:
                fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
                fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
                festivos = festivos.filter(fecha__gte=fecha_inicio_obj, fecha__lte=fecha_fin_obj)
            elif fecha_inicio:
                fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
                festivos = festivos.filter(fecha__gte=fecha_inicio_obj)
            elif fecha_fin:
                fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
                festivos = festivos.filter(fecha__lte=fecha_fin_obj)
            
            # Filtrar por año si se proporciona
            if anio:
                festivos = festivos.filter(fecha__year=int(anio))
            
            # Filtrar por mes si se proporciona
            if mes:
                festivos = festivos.filter(fecha__month=int(mes))
            
            # Serializar resultados de BD
            festivos_list = []
            festivos_bd = {}  # Dict para fácil combinación
            
            for festivo in festivos.order_by('fecha'):
                fecha_str = festivo.fecha.strftime('%Y-%m-%d')
                festivos_bd[fecha_str] = festivo.descripcion or 'Día festivo'
                festivos_list.append({
                    'fecha': fecha_str,
                    'descripcion': festivo.descripcion or '',
                    'recurrente': festivo.recurrente
                })
            
            # Obtener festivos calculados
            # Si no se especifica año, calcular para un rango amplio (año actual - 1 a + 10)
            año_actual = datetime.now().year
            
            if anio:
                # Si se especifica un año, calcular solo para ese año
                año_inicio = int(anio)
                año_fin = int(anio)
            else:
                # Si no se especifica, calcular para un rango amplio
                año_inicio = año_actual - 1
                año_fin = año_actual + 10
            
            # Combinar festivos calculados con los de BD
            festivos_calculados = self._obtener_festivos_calculados(año_inicio, año_fin)
            
            # Los festivos de BD tienen prioridad, pero agregamos los calculados que no estén en BD
            for fecha_calc, descripcion_calc in festivos_calculados.items():
                if fecha_calc not in festivos_bd:
                    festivos_list.append({
                        'fecha': fecha_calc,
                        'descripcion': descripcion_calc,
                        'recurrente': False
                    })
            
            # Ordenar por fecha
            festivos_list.sort(key=lambda x: x['fecha'])
            
            response_data = {
                'festivos': festivos_list,
                'total': len(festivos_list),
                'fuente': 'bd_y_calculado' if festivos_calculados else 'bd'
            }
            
            # Guardar en caché usando CacheService
            # Los festivos no cambian frecuentemente
            if not sin_cache:
                from core.services.cache_service import CacheService
                from core.services.cache_service import CACHE_TTL_LONG
                CacheService.set(cache_key, response_data, ttl=CACHE_TTL_LONG)
            
            return JsonResponse(response_data)
            
        except ValueError as e:
            return JsonResponse({'error': f'Formato de fecha inválido: {str(e)}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Error al obtener festivos: {str(e)}'}, status=500)


class DiasTemporadaView(LoginRequiredMixin, View):
    """
    Endpoint API para obtener días de temporada por año y mes.
    
    Parámetros:
    - anio: Año (requerido)
    - mes: Mes opcional (1-12)
    
    Retorna JSON con días de temporada agrupados por mes.
    """
    
    def get(self, request):
        try:
            anio = request.GET.get('anio')
            mes = request.GET.get('mes')
            
            if not anio:
                return JsonResponse({'error': 'El parámetro "anio" es requerido'}, status=400)
            
            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)
            
            if mes:
                try:
                    mes = int(mes)
                    if mes < 1 or mes > 12:
                        return JsonResponse({'error': 'El mes debe estar entre 1 y 12'}, status=400)
                    
                    # Obtener días de temporada del mes específico
                    dias_temporada = TemporadaService.obtener_dias_temporada_mes(anio, mes)
                    temporadas = [
                        {
                            'fecha': dia.fecha.strftime('%Y-%m-%d'),
                            'mes': dia.mes or dia.fecha.month,
                            'dia': dia.fecha.day,
                            'descripcion': dia.descripcion or 'Día de temporada'
                        }
                        for dia in dias_temporada
                    ]
                    
                    return JsonResponse({
                        'temporadas': temporadas,
                        'total': len(temporadas),
                        'anio': anio,
                        'mes': mes
                    })
                except ValueError:
                    return JsonResponse({'error': 'El mes debe ser un número válido'}, status=400)
            else:
                # Obtener todos los días de temporada del año, agrupados por mes
                dias_por_mes = TemporadaService.obtener_dias_temporada_por_mes(anio)
                dias_temporada = TemporadaService.obtener_dias_temporada_anio(anio)
                
                temporadas = [
                    {
                        'fecha': dia.fecha.strftime('%Y-%m-%d'),
                        'mes': dia.mes or dia.fecha.month,
                        'dia': dia.fecha.day,
                        'descripcion': dia.descripcion or 'Día de temporada'
                    }
                    for dia in dias_temporada
                ]
                
                return JsonResponse({
                    'temporadas': temporadas,
                    'por_mes': dias_por_mes,
                    'total': len(temporadas),
                    'anio': anio
                })
                
        except Exception as e:
            return JsonResponse({'error': f'Error al obtener temporadas: {str(e)}'}, status=500)


class DiasEspecialesPorTipoView(LoginRequiredMixin, View):
    """
    Endpoint API para obtener días especiales (festivos o mantenimiento) por tipo, año y mes.
    
    Parámetros:
    - tipo: Tipo de día especial ('festivo' o 'mantenimiento') (requerido)
    - anio: Año (requerido)
    - mes: Mes opcional (1-12)
    
    Retorna JSON con días especiales agrupados por mes.
    """
    
    def get(self, request):
        try:
            tipo = request.GET.get('tipo')
            anio = request.GET.get('anio')
            mes = request.GET.get('mes')
            
            if not tipo:
                return JsonResponse({'error': 'El parámetro "tipo" es requerido'}, status=400)
            
            if tipo not in ['festivo', 'mantenimiento']:
                return JsonResponse({'error': 'El tipo debe ser "festivo" o "mantenimiento"'}, status=400)
            
            if not anio:
                return JsonResponse({'error': 'El parámetro "anio" es requerido'}, status=400)
            
            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)
            
            from turnos.services.dia_especial_service import DiaEspecialService
            
            if mes:
                try:
                    mes = int(mes)
                    if mes < 1 or mes > 12:
                        return JsonResponse({'error': 'El mes debe estar entre 1 y 12'}, status=400)
                    
                    # Obtener días del tipo del mes específico
                    dias_especiales = DiaEspecialService.obtener_dias_por_tipo_mes(tipo, anio, mes)
                    dias_list = [
                        {
                            'fecha': dia.fecha.strftime('%Y-%m-%d'),
                            'mes': dia.mes or dia.fecha.month,
                            'dia': dia.fecha.day,
                            'descripcion': dia.descripcion or f'Día de {tipo}'
                        }
                        for dia in dias_especiales
                    ]
                    
                    return JsonResponse({
                        'dias': dias_list,
                        'total': len(dias_list),
                        'tipo': tipo,
                        'anio': anio,
                        'mes': mes
                    })
                except ValueError:
                    return JsonResponse({'error': 'El mes debe ser un número válido'}, status=400)
            else:
                # Obtener todos los días del tipo del año, agrupados por mes
                dias_por_mes = DiaEspecialService.obtener_dias_por_tipo_por_mes(tipo, anio)
                dias_especiales = DiaEspecialService.obtener_dias_por_tipo_anio(tipo, anio)
                
                dias_list = [
                    {
                        'fecha': dia.fecha.strftime('%Y-%m-%d'),
                        'mes': dia.mes or dia.fecha.month,
                        'dia': dia.fecha.day,
                        'descripcion': dia.descripcion or f'Día de {tipo}'
                    }
                    for dia in dias_especiales
                ]
                
                return JsonResponse({
                    'dias': dias_list,
                    'por_mes': dias_por_mes,
                    'total': len(dias_list),
                    'tipo': tipo,
                    'anio': anio
                })
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al obtener días especiales por tipo: {e}")
            return JsonResponse({'error': f'Error al obtener días especiales: {str(e)}'}, status=500)


class CalcularMantenimientoAutomaticoView(LoginRequiredMixin, View):
    """
    Endpoint API para calcular automáticamente los días de mantenimiento para un año.
    
    Parámetros:
    - anio: Año (requerido)
    
    Retorna JSON con días de mantenimiento calculados automáticamente, agrupados por mes.
    """
    
    def get(self, request):
        try:
            anio = request.GET.get('anio')
            
            if not anio:
                return JsonResponse({'error': 'El parámetro "anio" es requerido'}, status=400)
            
            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)
            
            from turnos.services.dia_especial_service import DiaEspecialService
            
            # Calcular días de mantenimiento automático
            dias_por_mes = DiaEspecialService.calcular_dias_mantenimiento_automatico(anio)
            
            # Convertir a formato de lista para compatibilidad
            dias_list = []
            for mes, dias in dias_por_mes.items():
                for dia in dias:
                    fecha = date(anio, mes, dia)
                    dias_list.append({
                        'fecha': fecha.strftime('%Y-%m-%d'),
                        'mes': mes,
                        'dia': dia,
                        'descripcion': 'Día de mantenimiento'
                    })
            
            return JsonResponse({
                'dias': dias_list,
                'por_mes': dias_por_mes,
                'total': len(dias_list),
                'tipo': 'mantenimiento',
                'anio': anio
            })
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al calcular días de mantenimiento automático: {e}")
            return JsonResponse({'error': f'Error al calcular días de mantenimiento: {str(e)}'}, status=500)


class CalcularFestivosAutomaticoView(LoginRequiredMixin, View):
    """
    Endpoint API para generar y obtener automáticamente los días festivos para un año.

    Parámetros:
    - anio: Año (requerido)

    Retorna JSON con días festivos calculados y/o generados en BD, agrupados por mes.
    """

    def get(self, request):
        try:
            anio = request.GET.get('anio')

            if not anio:
                return JsonResponse({'error': 'El parámetro \"anio\" es requerido'}, status=400)

            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)

            # Validar año mínimo (solo para evitar años históricos muy antiguos)
            if anio < 2000:
                return JsonResponse({
                    'error': f'El año debe ser mayor o igual a 2000. Año proporcionado: {anio}'
                }, status=400)

            from turnos.services.dia_especial_service import DiaEspecialService

            # Generar (si faltan) y obtener festivos automáticos
            dias_por_mes = DiaEspecialService.generar_festivos_automaticos(anio)

            # Convertir a formato de lista para compatibilidad
            dias_list = []
            for mes, dias in dias_por_mes.items():
                for dia in dias:
                    fecha = date(anio, mes, dia)
                    dias_list.append({
                        'fecha': fecha.strftime('%Y-%m-%d'),
                        'mes': mes,
                        'dia': dia,
                        'descripcion': 'Día festivo'
                    })

            return JsonResponse({
                'dias': dias_list,
                'por_mes': dias_por_mes,
                'total': len(dias_list),
                'tipo': 'festivo',
                'anio': anio
            })

        except ValueError as e:
            # Capturar errores de validación de rango de años
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Intento de generar festivos con año inválido: {e}")
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al calcular festivos automáticos: {e}")
            return JsonResponse({'error': f'Error al calcular festivos automáticos: {str(e)}'}, status=500)
