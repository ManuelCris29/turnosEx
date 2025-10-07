document.addEventListener('DOMContentLoaded', function() {

        const table = document.getElementById('empleados-table');
        if (!table) return;

        $('#empleados-table').DataTable({
            "paging": true,
            "lengthChange": true,
            "searching": true,
            "ordering": true,
            "info": true,
            "autoWidth": false,
            "responsive": true,
            "language": {
                "url": "//cdn.datatables.net/plug-ins/1.10.21/i18n/Spanish.json"
            }
        });

});

