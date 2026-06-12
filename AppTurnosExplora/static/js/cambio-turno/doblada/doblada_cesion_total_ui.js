/**
 * Cesión total: compañero en descanso puede cubrir doblada completa (checkbox + selects AM/PM).
 * Debe cargarse antes de solicitar_doblada.js. Expone window.DobladaCesionTotalUI.attach(refs).
 */
(function (global) {
    'use strict';

    function esEmpleadoEnDescanso(selectEl) {
        if (!selectEl || !selectEl.value) return false;
        const opt = selectEl.options[selectEl.selectedIndex];
        return opt && opt.textContent.includes('(Descanso)');
    }

    /**
     * @param {object} refs
     * @param {HTMLSelectElement|null} refs.empleadoReceptorAM
     * @param {HTMLSelectElement|null} refs.empleadoReceptorPM
     * @param {HTMLElement|null} refs.fechasPagoTotal
     * @param {HTMLElement|null} refs.fechaPagoParcial
     * @param {function} refs.actualizarVistaPrevia
     * @returns {{ resetCubreCompletaState: function }}
     */
    function attach(refs) {
        const {
            empleadoReceptorAM,
            empleadoReceptorPM,
            fechasPagoTotal,
            fechaPagoParcial,
            actualizarVistaPrevia,
        } = refs;

        function resetCubreCompletaState() {
            const chkAm = document.getElementById('checkbox_cubre_completa_am');
            const chkPm = document.getElementById('checkbox_cubre_completa_pm');
            const inputAm = document.getElementById('cubre_completa_am');
            const inputPm = document.getElementById('cubre_completa_pm');
            const colPm = document.getElementById('col_receptor_pm');
            const aviso = document.getElementById('aviso_receptor_unico_total');
            if (chkAm) chkAm.style.display = 'none';
            if (chkPm) chkPm.style.display = 'none';
            if (inputAm) inputAm.checked = false;
            if (inputPm) inputPm.checked = false;
            if (colPm) colPm.style.display = '';
            if (aviso) aviso.style.display = 'none';
            if (empleadoReceptorPM) empleadoReceptorPM.disabled = false;
            if (empleadoReceptorAM) empleadoReceptorAM.disabled = false;
            if (fechasPagoTotal) fechasPagoTotal.style.display = 'block';
            if (fechaPagoParcial) fechaPagoParcial.style.display = 'none';
        }

        function handleCubreCompleta(lado) {
            const esAM = lado === 'am';
            const selectActivo = esAM ? empleadoReceptorAM : empleadoReceptorPM;
            const selectOtro = esAM ? empleadoReceptorPM : empleadoReceptorAM;
            const inputCheck = document.getElementById(esAM ? 'cubre_completa_am' : 'cubre_completa_pm');
            const colPm = document.getElementById('col_receptor_pm');
            const aviso = document.getElementById('aviso_receptor_unico_total');

            if (inputCheck && inputCheck.checked) {
                if (selectOtro) {
                    selectOtro.value = selectActivo.value;
                    selectOtro.disabled = true;
                }
                if (!esAM && colPm) colPm.style.opacity = '0.5';
                if (esAM && colPm) colPm.style.opacity = '0.5';
                if (aviso) aviso.style.display = 'block';
                if (fechasPagoTotal) fechasPagoTotal.style.display = 'none';
                if (fechaPagoParcial) fechaPagoParcial.style.display = 'block';
            } else {
                if (selectOtro) {
                    selectOtro.value = '';
                    selectOtro.disabled = false;
                }
                if (colPm) colPm.style.opacity = '1';
                if (aviso) aviso.style.display = 'none';
                if (fechasPagoTotal) fechasPagoTotal.style.display = 'block';
                if (fechaPagoParcial) fechaPagoParcial.style.display = 'none';
            }
            actualizarVistaPrevia();
        }

        function onSelectReceptorTotalChange(lado) {
            const esAM = lado === 'am';
            const selectEl = esAM ? empleadoReceptorAM : empleadoReceptorPM;
            const chkDiv = document.getElementById(esAM ? 'checkbox_cubre_completa_am' : 'checkbox_cubre_completa_pm');
            const inputChk = document.getElementById(esAM ? 'cubre_completa_am' : 'cubre_completa_pm');
            const otroInputChk = document.getElementById(esAM ? 'cubre_completa_pm' : 'cubre_completa_am');

            if (otroInputChk && otroInputChk.checked) {
                return;
            }

            if (esEmpleadoEnDescanso(selectEl)) {
                if (chkDiv) chkDiv.style.display = 'block';
            } else {
                if (chkDiv) chkDiv.style.display = 'none';
                if (inputChk) inputChk.checked = false;
            }
            actualizarVistaPrevia();
        }

        if (empleadoReceptorAM) {
            empleadoReceptorAM.addEventListener('change', () => onSelectReceptorTotalChange('am'));
        }
        if (empleadoReceptorPM) {
            empleadoReceptorPM.addEventListener('change', () => onSelectReceptorTotalChange('pm'));
        }
        const chkAmInput = document.getElementById('cubre_completa_am');
        const chkPmInput = document.getElementById('cubre_completa_pm');
        if (chkAmInput) chkAmInput.addEventListener('change', () => handleCubreCompleta('am'));
        if (chkPmInput) chkPmInput.addEventListener('change', () => handleCubreCompleta('pm'));

        return { resetCubreCompletaState };
    }

    global.DobladaCesionTotalUI = { attach };
})(typeof window !== 'undefined' ? window : this);
