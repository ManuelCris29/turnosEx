from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View
from django.http import JsonResponse
from datetime import datetime


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
