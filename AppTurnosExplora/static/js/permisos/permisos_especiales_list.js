(function () {
    const container = document.getElementById('permisos-page');
    const MSG = container ? container.dataset.sancionMsg : '';
    document.querySelectorAll('.js-permiso-btn[data-sancion]').forEach(function (b) {
        b.classList.add('disabled');
        b.style.opacity = '0.65';
        b.addEventListener('click', function (ev) {
            ev.preventDefault();
            if (window.Swal) {
                Swal.fire({ icon: 'warning', title: 'Estás sancionado', text: MSG, confirmButtonText: 'Entendido' });
            } else {
                alert(MSG);
            }
        });
    });
})();
