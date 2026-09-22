/**
 * Чат в «Обращениях»: scroll, auto-resize, file chips, Enter-send, soft-poll.
 * Мобильный режим (iOS/Android): фиксированный viewport + composer внизу.
 */
(function () {
    'use strict';

    function qs(sel, root) {
        return (root || document).querySelector(sel);
    }

    function qsa(sel, root) {
        return Array.prototype.slice.call((root || document).querySelectorAll(sel));
    }

    function isMobileLayout() {
        return window.matchMedia('(max-width: 1100px)').matches;
    }

    function scrollChatToBottom(box) {
        if (!box) return;
        box.scrollTop = box.scrollHeight;
    }

    function isChatShell() {
        return document.body.classList.contains('support-appeals-chat') ||
            document.body.classList.contains('support-chat-open');
    }

    function isChatMobileShell() {
        return isMobileLayout() && isChatShell();
    }

    function lockPageScroll() {
        if (!isChatShell()) return;
        if (window.scrollY || window.pageYOffset) {
            window.scrollTo(0, 0);
        }
        if (document.documentElement.scrollTop) {
            document.documentElement.scrollTop = 0;
        }
    }

    function syncSupportViewport() {
        if (!isChatShell()) {
            document.documentElement.style.removeProperty('--support-vvh');
            return;
        }
        var vv = window.visualViewport;
        var height = vv && vv.height ? vv.height : window.innerHeight;
        document.documentElement.style.setProperty('--support-vvh', Math.round(height) + 'px');
        lockPageScroll();
    }

    function autoResizeTextarea(ta) {
        if (!ta) return;
        var maxH = isMobileLayout() ? 96 : 160;
        var minH = isMobileLayout() ? 40 : 44;
        ta.style.height = 'auto';
        var next = Math.min(Math.max(ta.scrollHeight, minH), maxH);
        ta.style.height = next + 'px';
        ta.style.overflowY = ta.scrollHeight > maxH ? 'auto' : 'hidden';
    }

    function formatFileSize(bytes) {
        if (!bytes && bytes !== 0) return '';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function syncFileChips(form) {
        var input = qs('[data-support-file-input]', form);
        var chips = qs('[data-support-file-chips]', form) || qs('[data-support-file-chips]', form.parentElement);
        if (!input || !chips) return;

        chips.innerHTML = '';
        var files = input.files ? Array.prototype.slice.call(input.files) : [];
        if (!files.length) {
            chips.hidden = true;
            return;
        }

        chips.hidden = false;
        files.forEach(function (file, index) {
            var chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'support-chat-file-chip';
            chip.title = 'Убрать файл';
            chip.setAttribute('data-file-index', String(index));

            var icon = document.createElement('span');
            icon.className = 'material-icons';
            icon.setAttribute('aria-hidden', 'true');
            icon.textContent = file.type && file.type.indexOf('image/') === 0 ? 'image' : 'attach_file';

            var label = document.createElement('span');
            label.className = 'support-chat-file-chip__name';
            label.textContent = file.name;

            var size = document.createElement('span');
            size.className = 'support-chat-file-chip__size';
            size.textContent = formatFileSize(file.size);

            var close = document.createElement('span');
            close.className = 'material-icons support-chat-file-chip__remove';
            close.setAttribute('aria-hidden', 'true');
            close.textContent = 'close';

            chip.appendChild(icon);
            chip.appendChild(label);
            chip.appendChild(size);
            chip.appendChild(close);

            chip.addEventListener('click', function () {
                removeFileAt(input, index, form);
            });

            chips.appendChild(chip);
        });
    }

    function removeFileAt(input, index, form) {
        if (!input || !window.DataTransfer) {
            input.value = '';
            syncFileChips(form);
            return;
        }
        var dt = new DataTransfer();
        Array.prototype.forEach.call(input.files || [], function (file, i) {
            if (i !== index) dt.items.add(file);
        });
        input.files = dt.files;
        syncFileChips(form);
    }

    function bindComposer(root, messagesBox) {
        var form = qs('[data-support-chat-form]', root);
        if (!form || form.dataset.supportChatBound === '1') return;
        form.dataset.supportChatBound = '1';

        var ta = qs('[data-support-chat-input]', form);
        var fileInput = qs('[data-support-file-input]', form);
        var enterHint = qs('.manager-chat-enter-hint', form);

        function keepComposerStable() {
            autoResizeTextarea(ta);
            syncSupportViewport();
            scrollChatToBottom(messagesBox);
            lockPageScroll();
        }

        if (ta) {
            autoResizeTextarea(ta);
            ta.addEventListener('input', function () {
                keepComposerStable();
            });

            ta.addEventListener('focus', function () {
                window.setTimeout(function () {
                    keepComposerStable();
                }, 50);
                window.setTimeout(function () {
                    keepComposerStable();
                }, 320);
            });

            ta.addEventListener('blur', function () {
                window.setTimeout(syncSupportViewport, 80);
            });

            ta.addEventListener('keydown', function (e) {
                if (e.key !== 'Enter' || isMobileLayout() || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) {
                    return;
                }
                e.preventDefault();
                if (typeof form.reportValidity === 'function' && !form.reportValidity()) return;
                if (typeof form.requestSubmit === 'function') form.requestSubmit();
                else form.submit();
            });
        }

        if (fileInput) {
            fileInput.addEventListener('change', function () {
                syncFileChips(form);
                keepComposerStable();
            });
            syncFileChips(form);
        }

        if (enterHint) {
            function syncEnterHint() {
                enterHint.hidden = isMobileLayout();
            }
            syncEnterHint();
            window.addEventListener('resize', syncEnterHint);
        }
    }

    function fetchTicketStatus(ticketId) {
        return fetch('/tickets/' + ticketId + '/status', {
            headers: { Accept: 'application/json' },
            credentials: 'same-origin',
        })
            .then(function (resp) {
                return resp.ok ? resp.json() : null;
            })
            .catch(function () {
                return null;
            });
    }

    function appealsStatusMeta(status) {
        if (status === 'closed') {
            return { label: 'Закрыт', mod: 'is-closed' };
        }
        if (status === 'waiting_for_user') {
            return { label: 'Есть ответ', mod: 'is-answered' };
        }
        return { label: 'На рассмотрении', mod: 'is-pending' };
    }

    function applyStatusToElements(ticketId, data) {
        if (!data || !data.ok) return;
        var meta = appealsStatusMeta(data.status);
        var nextText = meta.label || data.status_display || '';
        var nextClass = data.status_class || '';

        qsa('[data-ticket-status-id="' + ticketId + '"]').forEach(function (el) {
            var isAppealsPill = el.classList.contains('support-appeals-status');

            if (isAppealsPill) {
                ['is-pending', 'is-answered', 'is-closed'].forEach(function (c) {
                    el.classList.remove(c);
                });
                if (meta.mod) el.classList.add(meta.mod);
                // Не мешаем pill-стилям классами status-*
                Array.from(el.classList).forEach(function (c) {
                    if (c.indexOf('status-') === 0) el.classList.remove(c);
                });
            } else {
                Array.from(el.classList).forEach(function (c) {
                    if (c.indexOf('status-') === 0) el.classList.remove(c);
                });
                if (nextClass) el.classList.add(nextClass);
            }

            if (el.textContent !== nextText) {
                el.textContent = nextText;
            }
        });
    }

    function initInboxChat() {
        var panel = qs('.support-chat-panel');
        var messagesBox =
            qs('[data-support-chat-messages]', panel) || qs('.support-chat-panel .manager-chat-messages');
        var selectedData = document.getElementById('support-selected-ticket-data');
        var selectedTicketId = selectedData ? selectedData.getAttribute('data-ticket-id') : '';
        var selectedUpdatedAt = selectedData ? selectedData.getAttribute('data-updated-at') || '' : '';

        syncSupportViewport();

        if (messagesBox) {
            var scrollOnce = function () {
                scrollChatToBottom(messagesBox);
                lockPageScroll();
            };
            scrollOnce();
            if (document.fonts && document.fonts.ready) {
                document.fonts.ready.then(scrollOnce);
            } else {
                window.addEventListener('load', scrollOnce, { once: true });
            }
            window.setTimeout(scrollOnce, 80);
            window.setTimeout(scrollOnce, 280);
        }

        if (panel) bindComposer(panel, messagesBox);

        function onViewportChange() {
            syncSupportViewport();
            if (messagesBox && document.activeElement && document.activeElement.matches('[data-support-chat-input]')) {
                scrollChatToBottom(messagesBox);
            }
        }

        window.addEventListener('resize', onViewportChange);
        window.addEventListener('orientationchange', function () {
            window.setTimeout(onViewportChange, 180);
        });
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', onViewportChange);
            window.visualViewport.addEventListener('scroll', onViewportChange);
        }

        function pollStatuses() {
            var ids = {};
            qsa('[data-ticket-status-id]').forEach(function (el) {
                var id = el.getAttribute('data-ticket-status-id');
                if (id) ids[id] = true;
            });
            Object.keys(ids).forEach(function (id) {
                fetchTicketStatus(id).then(function (data) {
                    applyStatusToElements(id, data);
                });
            });
        }

        function pollSelectedTicketRealtime() {
            if (!selectedTicketId) return;
            fetchTicketStatus(selectedTicketId).then(function (data) {
                if (!data || !data.ok) return;
                applyStatusToElements(selectedTicketId, data);
                if (selectedUpdatedAt && data.updated_at && data.updated_at !== selectedUpdatedAt) {
                    var typing = qs('[data-support-chat-input]', panel);
                    if (typing && (document.activeElement === typing || (typing.value || '').trim())) {
                        selectedUpdatedAt = data.updated_at;
                        return;
                    }
                    var sep = window.location.search ? '&' : '?';
                    window.location.href =
                        window.location.pathname + window.location.search + sep + 'rt=' + Date.now();
                    return;
                }
                if (data.updated_at) selectedUpdatedAt = data.updated_at;
            });
        }

        function startPolling() {
            pollStatuses();
            window.setInterval(pollStatuses, 5000);
            if (selectedTicketId) window.setInterval(pollSelectedTicketRealtime, 8000);
        }

        if (document.readyState === 'complete') {
            window.setTimeout(startPolling, 800);
        } else {
            window.addEventListener(
                'load',
                function () {
                    window.setTimeout(startPolling, 800);
                },
                { once: true }
            );
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initInboxChat);
    } else {
        initInboxChat();
    }

    window.SupportChat = {
        bindComposer: bindComposer,
        scrollToBottom: function (root) {
            scrollChatToBottom(qs('[data-support-chat-messages]', root) || qs('.manager-chat-messages', root));
        },
        initRoot: function (root) {
            if (!root) return;
            var box = qs('[data-support-chat-messages]', root) || qs('.manager-chat-messages', root);
            bindComposer(root, box);
            scrollChatToBottom(box);
            syncSupportViewport();
        },
    };
})();
