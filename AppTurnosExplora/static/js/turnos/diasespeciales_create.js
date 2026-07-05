if (typeof django !== 'undefined' && django.jQuery) {
    django.jQuery(function($) {
        $('input, select, textarea').addClass('form-control');
        $('input[type="checkbox"]').removeClass('form-control').addClass('form-check-input');
    });
}
