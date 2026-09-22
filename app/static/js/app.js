/**
 * Toolls Music Distribution - Личный кабинет
 * JavaScript приложения
 */

document.addEventListener('DOMContentLoaded', function() {
    initSidebar();
    initSidebarNavGroups();
    initFlashMessages();
    initModals();
    initUserPopups();
    initForms();
    initHeaderNotifications();
    initThemeToggle();
});

var CABINET_THEME_KEY = 'toolls-cabinet-theme';
var CABINET_THEME_KEY_LEGACY = 'lvr-cabinet-theme';

function getCabinetTheme() {
    try {
        var t = localStorage.getItem(CABINET_THEME_KEY);
        if (t !== 'light' && t !== 'dark') {
            t = localStorage.getItem(CABINET_THEME_KEY_LEGACY);
        }
        if (t === 'light' || t === 'dark') return t;
    } catch (e) {}
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

function applyCabinetTheme(theme) {
    var t = theme === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', t);
    document.documentElement.classList.toggle('dark-theme', t === 'dark');
    if (document.body) {
        document.body.classList.toggle('dark-theme', t === 'dark');
    }
    var meta = document.getElementById('metaThemeColor');
    if (meta) meta.setAttribute('content', t === 'light' ? '#e7edf7' : '#0b0f14');
    try {
        localStorage.setItem(CABINET_THEME_KEY, t);
    } catch (e) {}
    syncThemeToggleUi(t);
}

function syncThemeToggleUi(theme) {
    var btn = document.getElementById('themeToggle');
    var icon = document.getElementById('themeToggleIcon');
    if (!btn || !icon) return;
    var isLight = theme === 'light';
    icon.textContent = isLight ? 'dark_mode' : 'light_mode';
    btn.title = isLight ? 'Тёмная тема' : 'Светлая тема';
    btn.setAttribute('aria-label', isLight ? 'Включить тёмную тему' : 'Включить светлую тему');
}

function initThemeToggle() {
    syncThemeToggleUi(getCabinetTheme());
    var btn = document.getElementById('themeToggle');
    if (!btn) return;
    btn.addEventListener('click', function() {
        var next = getCabinetTheme() === 'light' ? 'dark' : 'light';
        applyCabinetTheme(next);
    });
}

/**
 * Мобильное меню
 */
function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mobileToggle = document.getElementById('mobileMenuToggle');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const overlay = document.getElementById('sidebarOverlay');
    
    function setDrawerOpen(open) {
        document.body.classList.toggle('nav-drawer-open', open);
        if (mobileToggle) mobileToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (overlay) overlay.setAttribute('aria-hidden', open ? 'false' : 'true');
    }

    function closeSidebar() {
        if (sidebar) sidebar.classList.remove('open');
        setDrawerOpen(false);
    }
    
    function openSidebar() {
        closeHeaderNotificationsDropdown();
        if (sidebar) sidebar.classList.add('open');
        setDrawerOpen(true);
    }
    
    function toggleSidebar() {
        if (!sidebar) return;
        var willOpen = !sidebar.classList.contains('open');
        if (willOpen) closeHeaderNotificationsDropdown();
        sidebar.classList.toggle('open');
        setDrawerOpen(sidebar.classList.contains('open'));
    }
    
    if (mobileToggle && sidebar) {
        mobileToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleSidebar();
        });
    }
    
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            closeSidebar();
        });
    }
    
    if (overlay && sidebar) {
        overlay.addEventListener('click', closeSidebar);
    }
    
    // Закрытие при клике вне меню (десктоп, если меню открыто)
    document.addEventListener('click', function(e) {
        if (sidebar && sidebar.classList.contains('open')) {
            if (!sidebar.contains(e.target) && mobileToggle && !mobileToggle.contains(e.target)) {
                closeSidebar();
            }
        }
    });
    
    // Закрытие при переходе по пункту меню (мобилка)
    if (sidebar) {
        sidebar.querySelectorAll('.nav-item[href], .sidebar-btn[href]').forEach(function (link) {
            link.addEventListener('click', function () {
                if (window.innerWidth <= 768) closeSidebar();
            });
        });
    }

    // Закрытие при переходе на широкий экран
    window.addEventListener('resize', function() {
        if (window.innerWidth > 768) closeSidebar();
    });
}

/**
 * Сворачиваемые группы в боковом меню (refine)
 */
function initSidebarNavGroups() {
    var groups = document.querySelectorAll('[data-nav-group]');
    if (!groups.length) return;

    groups.forEach(function(group) {
        var toggle = group.querySelector('.nav-group-toggle');
        if (!toggle) return;

        toggle.addEventListener('click', function() {
            var expanded = group.classList.toggle('is-expanded');
            toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        });
    });
}

/**
 * Автоскрытие flash-сообщений
 */
function initFlashMessages() {
    const flashMessages = document.querySelectorAll('.flash-message');
    
    flashMessages.forEach(function(message) {
        // Автоскрытие через 5 секунд
        setTimeout(function() {
            message.style.opacity = '0';
            message.style.transform = 'translateY(-10px)';
            setTimeout(function() {
                message.remove();
            }, 300);
        }, 5000);
    });
}

/**
 * Закрыть панель уведомлений (шапка) — вызывается из меню-бургера на мобилке.
 */
function closeHeaderNotificationsDropdown() {
    var panel = document.getElementById('headerNotifDropdown');
    var btn = document.getElementById('headerNotifToggle');
    var backdrop = document.getElementById('headerNotifBackdrop');
    if (panel) panel.setAttribute('hidden', '');
    if (btn) btn.setAttribute('aria-expanded', 'false');
    if (backdrop) {
        backdrop.setAttribute('hidden', '');
        backdrop.setAttribute('aria-hidden', 'true');
    }
    document.body.classList.remove('header-notif-open');
}

/**
 * Колокольчик уведомлений в шапке (десктоп: выпадашка; мобилка: fixed + safe-area + затемнение)
 */
function initHeaderNotifications() {
    var wrap = document.getElementById('headerNotificationsWrap');
    var btn = document.getElementById('headerNotifToggle');
    var panel = document.getElementById('headerNotifDropdown');
    var backdrop = document.getElementById('headerNotifBackdrop');
    var closeBtn = document.getElementById('headerNotifClose');
    if (!wrap || !btn || !panel) return;

    function isMobileLayout() {
        return window.matchMedia('(max-width: 768px)').matches;
    }

    function isOpen() {
        return !panel.hasAttribute('hidden');
    }

    function setOpen(open) {
        if (open) {
            panel.removeAttribute('hidden');
            if (backdrop && isMobileLayout()) {
                backdrop.removeAttribute('hidden');
                backdrop.setAttribute('aria-hidden', 'false');
            }
            if (isMobileLayout()) {
                document.body.classList.add('header-notif-open');
            }
        } else {
            closeHeaderNotificationsDropdown();
            return;
        }
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var next = !isOpen();
        if (!next) {
            closeHeaderNotificationsDropdown();
        } else {
            setOpen(true);
        }
    });

    if (backdrop) {
        backdrop.addEventListener('click', function () {
            closeHeaderNotificationsDropdown();
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            closeHeaderNotificationsDropdown();
        });
    }

    document.addEventListener('click', function (e) {
        if (!isOpen()) return;
        if (wrap.contains(e.target)) return;
        if (backdrop && e.target === backdrop) return;
        closeHeaderNotificationsDropdown();
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && isOpen()) {
            closeHeaderNotificationsDropdown();
        }
    });

    window.addEventListener('resize', function () {
        if (!isMobileLayout() && backdrop) {
            backdrop.setAttribute('hidden', '');
            backdrop.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('header-notif-open');
        }
    });

    var markAllForm = document.getElementById('headerNotifMarkAllForm');
    if (markAllForm) {
        markAllForm.addEventListener('submit', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var fd = new FormData(markAllForm);
            fetch(markAllForm.action, {
                method: 'POST',
                body: fd,
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' }
            })
                .then(function (r) {
                    if (!r.ok) throw new Error('mark-all');
                    return r.json();
                })
                .then(function () {
                    wrap.setAttribute('data-unread-count', '0');
                    var total = parseInt(wrap.getAttribute('data-total-count'), 10) || 0;
                    var inner = btn.querySelector('.header-notifications__inner');
                    if (inner) {
                        inner.querySelectorAll('.notification-badge').forEach(function (b) {
                            b.remove();
                        });
                        if (total > 0) {
                            var span = document.createElement('span');
                            span.className = 'notification-badge notification-badge--archive';
                            span.setAttribute('aria-hidden', 'true');
                            span.textContent = total > 99 ? '99+' : String(total);
                            inner.appendChild(span);
                        }
                    }
                    var countsEl = document.getElementById('headerNotifCounts');
                    if (countsEl) {
                        countsEl.textContent = total > 0 ? '(' + total + ')' : '';
                    }
                    panel.querySelectorAll('.header-notif-item.is-unread').forEach(function (el) {
                        el.classList.remove('is-unread');
                    });
                    markAllForm.remove();
                    var unreadLabel = 'Уведомления';
                    if (total > 0) {
                        unreadLabel =
                            'Уведомления, всего ' + total + ', все прочитаны';
                    } else {
                        unreadLabel = 'Уведомлений нет';
                    }
                    btn.setAttribute('aria-label', unreadLabel);
                    btn.setAttribute(
                        'title',
                        total > 0 ? 'Уведомлений в архиве: ' + total : 'Уведомлений нет'
                    );
                })
                .catch(function () {});
        });
    }
}

/**
 * Модальные окна
 */
function initModals() {
    // Закрытие по Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const activeModal = document.querySelector('.modal.active');
            if (activeModal) {
                activeModal.classList.remove('active');
            }
        }
    });
}

/**
 * Открытие модального окна
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

/**
 * Закрытие модального окна
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

/**
 * Всплывающие уведомления администратора (на каждой загрузке страницы)
 */
function initUserPopups() {
    var modal = document.getElementById('userPopupModal');
    if (!modal) return;

    var raw = modal.getAttribute('data-popups');
    var popups = [];
    try {
        popups = raw ? JSON.parse(raw) : [];
    } catch (e) {
        return;
    }
    if (!Array.isArray(popups) || !popups.length) return;

    var overlay = modal.querySelector('.user-popup-modal__overlay');
    var closeBtn = modal.querySelector('.user-popup-modal__close');
    var okBtn = modal.querySelector('.user-popup-modal__ok');
    var badgeEl = document.getElementById('userPopupBadge');
    var titleEl = document.getElementById('userPopupTitle');
    var leadEl = document.getElementById('userPopupLead');
    var pointsEl = document.getElementById('userPopupPoints');
    var calloutEl = document.getElementById('userPopupCallout');
    var calloutTextEl = calloutEl ? calloutEl.querySelector('p') : null;

    function pickPopup() {
        for (var i = 0; i < popups.length; i++) {
            if (popups[i] && popups[i].id) {
                return popups[i];
            }
        }
        return null;
    }

    function applyTone(tone) {
        modal.classList.remove('user-popup-modal--tone-red', 'user-popup-modal--tone-orange');
        modal.classList.add(tone === 'orange' ? 'user-popup-modal--tone-orange' : 'user-popup-modal--tone-red');
    }

    function fillPopup(item) {
        applyTone(item.tone || 'red');
        if (badgeEl) badgeEl.textContent = item.badge || '';
        if (titleEl) titleEl.textContent = item.title || '';
        if (leadEl) {
            var lead = (item.lead || '').trim();
            leadEl.textContent = lead;
            leadEl.hidden = !lead;
        }
        if (pointsEl) {
            pointsEl.innerHTML = '';
            var points = Array.isArray(item.points) ? item.points : [];
            points.forEach(function (line) {
                if (!String(line).trim()) return;
                var li = document.createElement('li');
                li.textContent = line;
                pointsEl.appendChild(li);
            });
            pointsEl.hidden = pointsEl.children.length === 0;
        }
        if (calloutEl && calloutTextEl) {
            var callout = (item.callout || '').trim();
            calloutTextEl.textContent = callout;
            calloutEl.hidden = !callout;
        }
    }

    function openUserPopup() {
        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('user-popup-open');
        if (okBtn) okBtn.focus();
    }

    function closeUserPopup() {
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('user-popup-open');
    }

    var popup = pickPopup();
    if (!popup) return;

    fillPopup(popup);
    window.requestAnimationFrame(function () {
        openUserPopup();
    });

    if (overlay) {
        overlay.addEventListener('click', closeUserPopup);
    }
    if (closeBtn) {
        closeBtn.addEventListener('click', closeUserPopup);
    }
    if (okBtn) {
        okBtn.addEventListener('click', closeUserPopup);
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            closeUserPopup();
        }
    });
}

/**
 * Инициализация форм
 */
function initForms() {
    // Превью изображений
    const fileInputs = document.querySelectorAll('input[type="file"][data-preview]');
    
    fileInputs.forEach(function(input) {
        input.addEventListener('change', function(e) {
            const previewId = this.getAttribute('data-preview');
            const preview = document.getElementById(previewId);
            const file = e.target.files[0];
            
            if (file && preview) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    preview.innerHTML = `<img src="${e.target.result}" alt="Preview">`;
                };
                reader.readAsDataURL(file);
            }
        });
    });
    
    // Подтверждение опасных действий
    const dangerForms = document.querySelectorAll('form[data-confirm]');
    
    dangerForms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            const message = this.getAttribute('data-confirm') || 'Вы уверены?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });

    // Мягкая прогрузка на submit: защищает от повторного клика
    const loadingForms = document.querySelectorAll('form.js-submit-loading');
    loadingForms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            if (form.dataset.submitting === '1') return;
            form.dataset.submitting = '1';

            // disabled submit-кнопки не попадают в POST — сохраняем нажатую action
            var submitter = e.submitter;
            if (submitter && submitter.name) {
                form.querySelectorAll('input[data-submitter-mirror="1"]').forEach(function(el) {
                    el.remove();
                });
                var mirror = document.createElement('input');
                mirror.type = 'hidden';
                mirror.name = submitter.name;
                mirror.value = submitter.value || '';
                mirror.setAttribute('data-submitter-mirror', '1');
                form.appendChild(mirror);
            }

            var submitButtons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
            submitButtons.forEach(function(btn) {
                if (btn.tagName === 'BUTTON') {
                    if (!btn.dataset.originalHtml) btn.dataset.originalHtml = btn.innerHTML;
                    var text = btn.getAttribute('data-loading-text') || 'Отправка...';
                    btn.innerHTML = '<span class="material-icons">hourglass_top</span> ' + text;
                } else {
                    if (!btn.dataset.originalValue) btn.dataset.originalValue = btn.value;
                    btn.value = btn.getAttribute('data-loading-text') || 'Отправка...';
                }
                btn.disabled = true;
                btn.classList.add('is-loading');
            });
        });
    });
}

/**
 * AJAX запрос
 */
function ajax(url, options = {}) {
    const defaults = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        }
    };
    
    const config = { ...defaults, ...options };
    
    // Добавление CSRF токена
    const csrfToken = document.querySelector('meta[name="csrf-token"]');
    if (csrfToken) {
        config.headers['X-CSRFToken'] = csrfToken.getAttribute('content');
    }
    
    return fetch(url, config)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        });
}

/**
 * Показать уведомление
 */
function showNotification(message, type = 'info') {
    const container = document.querySelector('.flash-messages') || createFlashContainer();
    
    const notification = document.createElement('div');
    notification.className = `flash-message flash-${type}`;
    notification.innerHTML = `
        <span class="material-icons">
            ${type === 'success' ? 'check_circle' : 
              type === 'error' ? 'error' : 
              type === 'warning' ? 'warning' : 'info'}
        </span>
        <span>${message}</span>
        <button class="flash-close" onclick="this.parentElement.remove()">
            <span class="material-icons">close</span>
        </button>
    `;
    
    container.appendChild(notification);
    
    // Автоскрытие
    setTimeout(function() {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

function createFlashContainer() {
    const container = document.createElement('div');
    container.className = 'flash-messages';
    const content = document.querySelector('.content');
    if (content) {
        content.parentNode.insertBefore(container, content);
    }
    return container;
}

/**
 * Форматирование чисел
 */
function formatNumber(num) {
    return new Intl.NumberFormat('ru-RU').format(num);
}

/**
 * Форматирование валюты
 */
function formatCurrency(amount) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        minimumFractionDigits: 2
    }).format(amount);
}

/**
 * Форматирование даты
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
    }).format(date);
}

/**
 * Debounce функция
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Копирование в буфер обмена
 */
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        showNotification('Скопировано в буфер обмена', 'success');
    }).catch(function() {
        showNotification('Не удалось скопировать', 'error');
    });
}

