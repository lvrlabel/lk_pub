/**
 * Чат с менеджером — мобильный shell: visualViewport, scroll, auto-resize.
 */
(function () {
    'use strict';

    function qs(sel, root) {
        return (root || document).querySelector(sel);
    }

    function isMobile() {
        return window.matchMedia('(max-width: 900px)').matches;
    }

    function syncViewport() {
        if (!document.body.classList.contains('manager-chat-page')) return;
        if (!isMobile()) {
            document.documentElement.style.removeProperty('--mc-vvh');
            return;
        }
        var vv = window.visualViewport;
        var h = vv && vv.height ? vv.height : window.innerHeight;
        document.documentElement.style.setProperty('--mc-vvh', Math.round(h) + 'px');
        if (window.scrollY || document.documentElement.scrollTop) {
            window.scrollTo(0, 0);
        }
    }

    function scrollToBottom(box) {
        if (!box) return;
        box.scrollTop = box.scrollHeight;
    }

    function autoResize(ta) {
        if (!ta) return;
        var maxH = isMobile() ? 110 : 160;
        var minH = isMobile() ? 40 : 48;
        ta.style.height = 'auto';
        var next = Math.min(Math.max(ta.scrollHeight, minH), maxH);
        ta.style.height = next + 'px';
        ta.style.overflowY = ta.scrollHeight > maxH ? 'auto' : 'hidden';
    }

    function boot() {
        var box = qs('[data-manager-chat-messages]') || qs('.manager-chat-messages');
        var ta = qs('#managerReplyMessage');

        syncViewport();
        scrollToBottom(box);

        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(function () {
                scrollToBottom(box);
            });
        }
        window.setTimeout(function () {
            scrollToBottom(box);
        }, 120);
        window.setTimeout(function () {
            scrollToBottom(box);
        }, 320);

        if (ta) {
            autoResize(ta);
            ta.addEventListener('input', function () {
                autoResize(ta);
            });
            ta.addEventListener('focus', function () {
                window.setTimeout(function () {
                    syncViewport();
                    scrollToBottom(box);
                }, 180);
            });
        }

        function onViewportChange() {
            syncViewport();
            if (document.activeElement === ta) {
                scrollToBottom(box);
            }
        }

        window.addEventListener('resize', onViewportChange);
        window.addEventListener('orientationchange', function () {
            window.setTimeout(onViewportChange, 200);
        });
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', onViewportChange);
            window.visualViewport.addEventListener('scroll', onViewportChange);
        }

        // Закрытие оверлея админ-панели тапом по затемнению
        var layout = qs('.manager-chat-layout');
        if (layout) {
            layout.addEventListener('click', function (e) {
                if (!layout.classList.contains('is-tools-open')) return;
                if (e.target === layout || e.target.classList.contains('manager-chat-main')) {
                    layout.classList.remove('is-tools-open');
                }
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
