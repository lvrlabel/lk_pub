(function () {
    document.querySelectorAll('.js-auth-submit').forEach(function (form) {
        var btn = form.querySelector('.js-auth-btn');
        if (!btn) return;
        form.addEventListener('submit', function () {
            if (form.dataset.submitting === '1') return;
            form.dataset.submitting = '1';
            btn.disabled = true;
            btn.classList.add('is-busy');
            btn.setAttribute('aria-busy', 'true');
        });
    });
})();
