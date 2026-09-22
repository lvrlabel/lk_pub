/**
 * Живой чат с менеджером:
 * - галочки прочтения;
 * - новые сообщения подставляются в DOM (без reload страницы).
 */
(function () {
    'use strict';

    var root = document.querySelector('[data-manager-chat-sync-url]');
    if (!root) return;

    var syncUrl = root.getAttribute('data-manager-chat-sync-url');
    if (!syncUrl) return;

    var POLL_MS = 3000;
    var timer = null;
    var inFlight = false;

    var lastMessageId = parseInt(root.getAttribute('data-last-message-id') || '0', 10) || 0;
    var messagesCount = parseInt(root.getAttribute('data-messages-count') || '0', 10) || 0;

    function setTick(el, isRead) {
        if (!el) return;
        var icon = el.querySelector('.material-icons');
        var sr = el.querySelector('.visually-hidden');
        el.classList.toggle('is-read', !!isRead);
        el.classList.toggle('is-sent', !isRead);
        el.setAttribute('title', isRead ? 'Прочитано' : 'Доставлено, не прочитано');
        if (icon) icon.textContent = isRead ? 'done_all' : 'done';
        if (sr) sr.textContent = isRead ? 'Прочитано' : 'Не прочитано';
    }

    function applyReads(reads) {
        if (!reads || typeof reads !== 'object') return;
        var ticks = root.querySelectorAll('.manager-chat-ticks[data-msg-id]');
        ticks.forEach(function (el) {
            var id = el.getAttribute('data-msg-id');
            if (!id || !Object.prototype.hasOwnProperty.call(reads, id)) return;
            setTick(el, !!reads[id]);
        });
    }

    function scrollToBottom() {
        root.scrollTop = root.scrollHeight;
    }

    function isUserTyping() {
        var ta = document.getElementById('managerReplyMessage');
        if (!ta) return false;
        // Не блокируем обновление только из‑за фокуса — только если есть текст
        return !!(ta.value || '').trim();
    }

    function applyMessagesHtml(html) {
        if (!html) return;
        var nearBottom = (root.scrollHeight - root.scrollTop - root.clientHeight) < 120;
        root.innerHTML = html;
        if (nearBottom) {
            scrollToBottom();
        }
    }

    function syncOnce() {
        if (inFlight || document.hidden) return;
        inFlight = true;

        var url = syncUrl
            + (syncUrl.indexOf('?') >= 0 ? '&' : '?')
            + 'last_id=' + encodeURIComponent(String(lastMessageId))
            + '&count=' + encodeURIComponent(String(messagesCount));

        fetch(url, {
            method: 'GET',
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            cache: 'no-store'
        })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data || !data.ok) return;

                var nextLastId = parseInt(data.last_message_id || 0, 10) || 0;
                var nextCount = parseInt(data.messages_count || 0, 10) || 0;
                var hasNewer = nextLastId > lastMessageId || nextCount > messagesCount;

                if (hasNewer && data.html) {
                    if (isUserTyping()) {
                        // Не трогаем DOM, пока печатают — на следующем цикле подтянется
                        applyReads(data.reads);
                        return;
                    }
                    applyMessagesHtml(data.html);
                    lastMessageId = nextLastId;
                    messagesCount = nextCount;
                    root.setAttribute('data-last-message-id', String(lastMessageId));
                    root.setAttribute('data-messages-count', String(messagesCount));
                } else {
                    // Синхронизируем курсоры без перерисовки (на случай рассинхрона)
                    if (nextLastId >= lastMessageId) lastMessageId = nextLastId;
                    if (nextCount >= messagesCount) messagesCount = nextCount;
                }

                applyReads(data.reads);
            })
            .catch(function () { /* тихо */ })
            .finally(function () { inFlight = false; });
    }

    function start() {
        syncOnce();
        if (timer) clearInterval(timer);
        timer = setInterval(syncOnce, POLL_MS);
    }

    function stop() {
        if (timer) {
            clearInterval(timer);
            timer = null;
        }
    }

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) stop();
        else start();
    });

    start();
})();
