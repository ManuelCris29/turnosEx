// JavaScript para Asignación de Salas por Período
document.addEventListener('DOMContentLoaded', function() {
    
    // Función para desactivar asignación con confirmación
    window.desactivarAsignacion = function(asignacionId, descripcion) {
        if (confirm(`¿Está seguro de desactivar la asignación: ${descripcion}?`)) {
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = `/empleados/desactivar-asignacion-sala/${asignacionId}/`;
            
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = csrfToken;
            
            form.appendChild(csrfInput);
            document.body.appendChild(form);
            form.submit();
        }
    };

    // Auto-completar fecha fin cuando se selecciona fecha inicio
    const fechaInicioInput = document.querySelector('input[name="fecha_inicio"]');
    const fechaFinInput = document.querySelector('input[name="fecha_fin"]');
    
    if (fechaInicioInput && fechaFinInput) {
        fechaInicioInput.addEventListener('change', function() {
            const fechaInicio = this.value;
            
            if (fechaInicio && !fechaFinInput.value) {
                // Establecer fecha fin 7 días después (una semana)
                const fechaInicioObj = new Date(fechaInicio);
                const fechaFinObj = new Date(fechaInicioObj);
                fechaFinObj.setDate(fechaFinObj.getDate() + 6); // 6 días adicionales = 7 días total
                
                const fechaFinStr = fechaFinObj.toISOString().split('T')[0];
                fechaFinInput.value = fechaFinStr;
            }
        });
    }

    // Validación del formulario antes de enviar
    const formulario = document.querySelector('form');
    if (formulario) {
        formulario.addEventListener('submit', function(e) {
            const empleado = document.querySelector('select[name="empleado"]').value;
            const sala = document.querySelector('select[name="sala"]').value;
            const fechaInicio = document.querySelector('input[name="fecha_inicio"]').value;
            const fechaFin = document.querySelector('input[name="fecha_fin"]').value;
            
            // Validaciones básicas
            if (!empleado || !sala || !fechaInicio || !fechaFin) {
                e.preventDefault();
                alert('Por favor, complete todos los campos requeridos.');
                return false;
            }
            
            // Validar que la fecha fin sea posterior a la fecha inicio
            const fechaInicioObj = new Date(fechaInicio);
            const fechaFinObj = new Date(fechaFin);
            
            if (fechaFinObj <= fechaInicioObj) {
                e.preventDefault();
                alert('La fecha de fin debe ser posterior a la fecha de inicio.');
                return false;
            }
            
            // Validar que no sea más de 30 días
            const diferenciaDias = (fechaFinObj - fechaInicioObj) / (1000 * 60 * 60 * 24);
            if (diferenciaDias > 30) {
                e.preventDefault();
                alert('El período no puede ser mayor a 30 días.');
                return false;
            }
        });
    }

    // Función para limpiar formulario
    window.limpiarFormulario = function() {
        document.querySelector('select[name="empleado"]').value = '';
        document.querySelector('select[name="sala"]').value = '';
        document.querySelector('input[name="fecha_inicio"]').value = '';
        document.querySelector('input[name="fecha_fin"]').value = '';
    };

    // Función para establecer período semanal (7 días)
    window.asignarSemana = function() {
        const fechaInicio = document.querySelector('input[name="fecha_inicio"]');
        const fechaFin = document.querySelector('input[name="fecha_fin"]');
        
        if (fechaInicio.value) {
            const fechaInicioObj = new Date(fechaInicio.value);
            const fechaFinObj = new Date(fechaInicioObj);
            fechaFinObj.setDate(fechaFinObj.getDate() + 6);
            
            fechaFin.value = fechaFinObj.toISOString().split('T')[0];
        }
    };

    // Función para establecer período mensual (30 días)
    window.asignarMes = function() {
        const fechaInicio = document.querySelector('input[name="fecha_inicio"]');
        const fechaFin = document.querySelector('input[name="fecha_fin"]');
        
        if (fechaInicio.value) {
            const fechaInicioObj = new Date(fechaInicio.value);
            const fechaFinObj = new Date(fechaInicioObj);
            fechaFinObj.setDate(fechaFinObj.getDate() + 29);
            
            fechaFin.value = fechaFinObj.toISOString().split('T')[0];
        }
    };

    // Mejorar UX con tooltips informativos
    const tooltips = document.querySelectorAll('[data-toggle="tooltip"]');
    if (tooltips.length > 0) {
        // Inicializar tooltips si Bootstrap está disponible
        if (typeof $ !== 'undefined' && $.fn.tooltip) {
            $('[data-toggle="tooltip"]').tooltip();
        }
    }
});
