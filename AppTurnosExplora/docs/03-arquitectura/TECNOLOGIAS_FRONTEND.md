# Tecnologías de Frontend - AppTurnosExplora

## Resumen Ejecutivo

El proyecto utiliza un stack de frontend basado en **AdminLTE 3** (template administrativo) con **Bootstrap 4**, **jQuery**, y múltiples plugins para funcionalidades específicas. El diseño es principalmente server-side rendering con Django Templates, complementado con JavaScript vanilla y librerías modernas para interacciones dinámicas.

---

## 🎨 Framework de Diseño Principal

### **AdminLTE 3**
- **Descripción**: Template administrativo basado en Bootstrap
- **Versión**: 3.x
- **Ubicación**: `static/css/adminlte.min.css`, `static/js/adminlte.min.js`
- **Uso**: Framework base para toda la interfaz de usuario
- **Características**:
  - Sidebar colapsable
  - Navbar responsive
  - Sistema de cards y layouts
  - Tema oscuro/claro

### **Bootstrap 4**
- **Descripción**: Framework CSS responsive
- **Ubicación**: `static/plugins/bootstrap/`
- **Uso**: Sistema de grid, componentes UI, utilidades CSS
- **Características**:
  - Grid system responsive
  - Componentes (cards, modals, dropdowns, etc.)
  - Utilidades de espaciado y tipografía

---

## 📜 Librerías JavaScript Core

### **jQuery**
- **Versión**: 3.x (slim y full)
- **Ubicación**: `static/plugins/jquery/`
- **Uso**: Manipulación DOM, AJAX, eventos
- **Nota**: Base para la mayoría de plugins

### **jQuery UI**
- **Ubicación**: `static/plugins/jquery-ui/`
- **Uso**: Widgets y efectos adicionales

---

## 📅 Calendarios y Datepickers

### **Flatpickr** (local)
- **Versión**: 4.6.13 (congelada en el repo)
- **Ubicación**: `static/plugins/flatpickr/` — servido con `{% static_v %}`
- **Ubicación en código**: Templates de solicitudes
- *Migrado desde `cdn.jsdelivr.net` el 2026-07-28; ver `docs/04-guias/manual-cdn-a-estaticos-locales.md`*
- **Uso**: 
  - Selección de fechas en formularios
  - Bloqueo de domingos, festivos, mantenimiento
  - Marcado visual de días especiales
- **Archivos relacionados**:
  - `static/js/cambio-turno/datepicker_festivos.js`
  - `static/js/cambio-turno/solicitar_doblada.js`
  - `static/js/cambio-turno/solicitar_cambio_turno.js`
  - `static/js/cambio-turno/solicitar_ct_permanente.js`

### **FullCalendar** (local)
- **Versión**: 6.1.11
- **Ubicación**: `static/plugins/fullcalendar/` — servido con `{% static_v %}`
- *Migrado desde CDN el 2026-07-28; la copia local se verificó idéntica por sha256*
- **Uso**: Calendario mensual en "Mis Turnos"
- **Archivo relacionado**: `templates/turnos/mis_turnos.html`

### **Tempus Dominus Bootstrap 4**
- **Ubicación**: `static/plugins/tempusdominus-bootstrap-4/`
- **Uso**: Datepicker alternativo con integración Bootstrap

---

## 🎯 Componentes UI y Plugins

### **SweetAlert2**
- **Ubicación**: `static/plugins/sweetalert2/`
- **Uso**: 
  - Alertas personalizadas
  - Confirmaciones
  - Modales de éxito/error
- **Tema**: Bootstrap 4 (`sweetalert2-theme-bootstrap-4`)

### **Select2**
- **Ubicación**: `static/plugins/select2/`
- **Uso**: Selects mejorados con búsqueda
- **Tema**: Bootstrap 4 (`select2-bootstrap4-theme`)

### **DataTables**
- **Ubicación**: `static/plugins/datatables/`
- **Uso**: Tablas interactivas con:
  - Búsqueda
  - Ordenamiento
  - Paginación
  - Exportación
- **Extensiones disponibles**:
  - Buttons (exportar)
  - Responsive
  - FixedHeader
  - RowReorder
  - Y más...

### **Summernote**
- **Ubicación**: `static/plugins/summernote/`
- **Uso**: Editor de texto enriquecido (WYSIWYG)
- **Versiones**: BS4 y BS5 disponibles

### **Toastr**
- **Ubicación**: `static/plugins/toastr/`
- **Uso**: Notificaciones toast (no bloqueantes)

---

## 📊 Gráficos y Visualización

### **Chart.js**
- **Ubicación**: `static/plugins/chart.js/`
- **Uso**: Gráficos interactivos
- **Templates relacionados**: `pages/charts/chartjs.html`

### **uPlot**
- **Ubicación**: `static/plugins/uplot/`
- **Uso**: Gráficos de alto rendimiento
- **Templates relacionados**: `pages/charts/uplot.html`

### **Flot Charts**
- **Ubicación**: `static/plugins/flot/`
- **Uso**: Gráficos jQuery-based
- **Templates relacionados**: `pages/charts/flot.html`

---

## 🎨 Iconos y Fuentes

### **Font Awesome**
- **Versión**: Free (latest)
- **Ubicación**: `static/plugins/fontawesome-free/`
- **Uso**: Iconos en toda la aplicación
- **CDN alternativo**: También usado desde CDN en algunos templates

### **Google Fonts - Source Sans Pro**
- **CDN**: `https://fonts.googleapis.com/css?family=Source+Sans+Pro`
- **Uso**: Tipografía principal del proyecto

---

## 📝 Formularios y Validación

### **jQuery Validation**
- **Ubicación**: `static/plugins/jquery-validation/`
- **Uso**: Validación de formularios en cliente
- **Localización**: Múltiples idiomas disponibles

### **Inputmask**
- **Ubicación**: `static/plugins/inputmask/`
- **Uso**: Máscaras de entrada (teléfonos, fechas, etc.)

### **iCheck Bootstrap**
- **Ubicación**: `static/plugins/icheck-bootstrap/`
- **Uso**: Checkboxes y radios personalizados

### **Bootstrap Switch**
- **Ubicación**: `static/plugins/bootstrap-switch/`
- **Uso**: Toggles/Switches personalizados

---

## 🗂️ Otros Componentes

### **Bootstrap Duallistbox**
- **Ubicación**: `static/plugins/bootstrap4-duallistbox/`
- **Uso**: Selectores duales (lista origen/destino)

### **Bootstrap Color Picker**
- **Ubicación**: `static/plugins/bootstrap-colorpicker/`
- **Uso**: Selector de colores

### **Pace Progress**
- **Ubicación**: `static/plugins/pace-progress/`
- **Uso**: Indicadores de carga de página
- **Temas**: Múltiples temas disponibles

### **Overlay Scrollbars**
- **Ubicación**: `static/plugins/overlayScrollbars/`
- **Uso**: Scrollbars personalizados

### **Moment.js**
- **Ubicación**: `static/plugins/moment/`
- **Uso**: Manipulación de fechas y tiempos

---

## 📁 Estructura de Archivos Frontend

```
AppTurnosExplora/
├── static/
│   ├── css/
│   │   ├── adminlte.min.css          # AdminLTE principal
│   │   ├── base_custom.css           # Estilos personalizados
│   │   └── mis_turnos.css            # Estilos específicos
│   ├── js/
│   │   ├── adminlte.min.js          # AdminLTE JS
│   │   ├── cambio-turno/
│   │   │   ├── datepicker_festivos.js
│   │   │   ├── solicitar_doblada.js
│   │   │   ├── solicitar_cambio_turno.js
│   │   │   ├── solicitar_ct_permanente.js
│   │   │   └── validadores_solicitudes.js
│   │   └── mis_turnos.js
│   └── plugins/                      # Todas las librerías
│       ├── bootstrap/
│       ├── jquery/
│       ├── fontawesome-free/
│       ├── sweetalert2/
│       ├── select2/
│       ├── datatables/
│       ├── flatpickr/ (si está local)
│       └── ...
└── templates/
    ├── base.html                     # Template base
    ├── header.html
    ├── footer.html
    └── [app]/                         # Templates por app
```

---

## 🔧 Configuración en Templates

### Template Base (`base.html`)

```html
<!-- CSS -->
<link rel="stylesheet" href="/static/css/adminlte.min.css">
<link rel="stylesheet" href="/static/plugins/fontawesome-free/css/all.min.css">
<link rel="stylesheet" href="/static/plugins/sweetalert2/sweetalert2.min.css">
<link rel="stylesheet" href="/static/css/base_custom.css">

<!-- JavaScript -->
<script src="/static/plugins/jquery/jquery.min.js"></script>
<script src="/static/plugins/bootstrap/js/bootstrap.bundle.min.js"></script>
<script src="/static/plugins/sweetalert2/sweetalert2.min.js"></script>
<script src="/static/js/adminlte.min.js"></script>
```

### Templates de Solicitudes

```html
<!-- Flatpickr autohospedado -->
<link rel="stylesheet" href="{% static_v 'plugins/flatpickr/flatpickr.min.css' %}">
<script src="{% static_v 'plugins/flatpickr/flatpickr.min.js' %}"></script>
<script src="{% static_v 'plugins/flatpickr/l10n/es.js' %}"></script>
```

### Template Mis Turnos

```html
<!-- FullCalendar autohospedado -->
<script src="{% static_v 'plugins/fullcalendar/index.global.min.js' %}"></script>
```

---

## 📦 Dependencias Principales

### Desde CDN (Externas)
- **Google Fonts**: Tipografía (`base.html` y login; con `display=fallback`)
- **Font Awesome 6.4.0**: solo en `templates/turnos/mis_turnos.html`, vía `cdnjs` con SRI.
  Sigue en CDN porque la copia local es la 5.15.4 (major distinto).

### Desde Static (Locales)
- **AdminLTE 3**: Framework base
- **Bootstrap 4**: CSS framework
- **jQuery**: JavaScript base
- **Font Awesome 5.15.4**: Iconos (global, desde `base.html`)
- **SweetAlert2** (v11.4.0): Alertas — cargado una sola vez en `base.html`
- **Flatpickr** (4.6.13): Datepicker de los formularios
- **FullCalendar** (6.1.11): Calendario interactivo
- **Select2**: Selects mejorados
- **DataTables**: Tablas
- **Chart.js** (4.5.1, `chart.umd.min.js`) **/uPlot**: Gráficos
- **Summernote**: Editor WYSIWYG
- **Toastr**: Notificaciones

> ⚠️ En `static/plugins/chart.js/` conviven dos versiones: usa **`chart.umd.min.js`** (v4).
> El `Chart.min.js` es la v2.9.4 de AdminLTE y su API es incompatible.

---

## 🎯 Uso por Funcionalidad

### Formularios de Solicitudes
- **Flatpickr**: Selección de fechas
- **Select2**: Selección de empleados
- **SweetAlert2**: Confirmaciones y alertas
- **jQuery Validation**: Validación de formularios

### Calendario de Turnos
- **FullCalendar**: Visualización mensual
- **CSS personalizado**: Estilos de tarjetas y badges

### Tablas de Datos
- **DataTables**: Tablas interactivas con búsqueda y ordenamiento
- **Bootstrap Tables**: Tablas simples con clases Bootstrap

### Notificaciones
- **SweetAlert2**: Alertas modales
- **Toastr**: Notificaciones toast (no bloqueantes)

### Gráficos y Reportes
- **Chart.js**: Gráficos interactivos
- **uPlot**: Gráficos de alto rendimiento
- **Flot**: Gráficos jQuery-based

---

## 🚀 Mejores Prácticas Aplicadas

1. **CDN para librerías grandes**: Flatpickr y FullCalendar desde CDN para mejor caché
2. **Librerías locales**: AdminLTE, Bootstrap, jQuery locales para control total
3. **CSS personalizado**: `base_custom.css` para estilos específicos del proyecto
4. **JavaScript modular**: Archivos JS organizados por funcionalidad
5. **Templates Django**: Uso de `{% block extra_css %}` y `{% block extra_js %}` para extensibilidad

---

## 📝 Notas Técnicas

- **No hay build process**: El proyecto no usa Webpack, Vite, o similar
- **Vanilla JavaScript**: Código JS personalizado sin frameworks modernos (React, Vue, etc.)
- **Server-side rendering**: Django Templates para renderizado
- **AJAX**: Comunicación con backend vía jQuery AJAX
- **Responsive**: Bootstrap 4 garantiza diseño responsive

---

## 🔄 Posibles Mejoras Futuras

1. **Migrar a Bootstrap 5**: AdminLTE 3 soporta Bootstrap 5
2. **Webpack/Vite**: Para bundling y optimización de assets
3. **TypeScript**: Para mejor tipado en JavaScript
4. **Framework moderno**: Considerar React/Vue para componentes complejos
5. **PWA**: Convertir en Progressive Web App
6. **Optimización de assets**: Minificación y compresión automática

---

## 📚 Referencias

- **AdminLTE 3**: https://adminlte.io/
- **Bootstrap 4**: https://getbootstrap.com/docs/4.6/
- **Flatpickr**: https://flatpickr.js.org/
- **FullCalendar**: https://fullcalendar.io/
- **SweetAlert2**: https://sweetalert2.github.io/
- **Select2**: https://select2.org/
- **DataTables**: https://datatables.net/



