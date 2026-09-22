/**
 * Чат сообщества: автообновление новых сообщений, автопрокрутка.
 */
(function () {
    'use strict';

    var box = document.getElementById('cmChatMessages');
    var form = document.getElementById('cmChatForm');
    var input = document.getElementById('cmChatInput');
    var typing = document.getElementById('cmChatTyping');
    var mediaForm = document.getElementById('cmMediaForm');
    var mediaInput = document.getElementById('cmMediaInput');
    var mediaType = document.getElementById('cmMediaType');
    var replying = document.getElementById('cmChatReplying');
    var replyId = document.getElementById('cmChatReplyId');
    var mediaReplyId = document.getElementById('cmMediaReplyId');
    var replyAuthor = document.getElementById('cmChatReplyAuthor');
    var replyText = document.getElementById('cmChatReplyText');
    var replyCancel = document.getElementById('cmChatReplyCancel');
    if (!box || !form || !input) return;

    function isNearBottom() {
        return box.scrollHeight - box.scrollTop - box.clientHeight < 120;
    }

    function scrollToBottom(force) {
        if (force || isNearBottom()) {
            box.scrollTop = box.scrollHeight;
        }
    }

    function lastMessageId() {
        var items = box.querySelectorAll('.cm-msg');
        if (!items.length) return 0;
        return parseInt(items[items.length - 1].getAttribute('data-id'), 10) || 0;
    }

    function hideEmpty() {
        var empty = document.getElementById('cmChatEmpty');
        if (empty) empty.remove();
    }

    function escapeHtml(s) {
        var div = document.createElement('div');
        div.textContent = String(s);
        return div.innerHTML;
    }

    function appendMessage(m, own) {
        hideEmpty();
        var el = document.createElement('div');
        el.className = 'cm-msg' + (own ? ' cm-msg--own' : '');
        el.setAttribute('data-id', m.id);
        el.innerHTML =
            '<div class="cm-msg__avatar-wrap">' +
            '<a href="/community/user/' + m.user_id + '">' +
            '<img src="' + escapeHtml(m.avatar) + '" alt="" class="cm-msg__avatar"></a></div>' +
            '<div class="cm-msg__body"><div class="cm-msg__meta">' +
            '<a href="/community/user/' + m.user_id + '" class="cm-msg__author">' + escapeHtml(m.author) + '</a>' +
            (m.is_admin ? '<span class="cm-badge cm-badge--admin">Менеджер Toolls</span>' : '') +
            '<span class="cm-msg__time">' + escapeHtml(m.time) + '</span></div>' +
            (m.reply_to ? '<div class="cm-msg__reply"><strong>' + escapeHtml(m.reply_to.author) + '</strong><span>' + escapeHtml(m.reply_to.text) + '</span></div>' : '') +
            (m.media_url ? (m.media_type === 'video' ? '<video class="cm-msg__media cm-video-message" src="' + escapeHtml(m.media_url) + '" controls playsinline preload="metadata"></video>' : '<audio class="cm-msg__media" src="' + escapeHtml(m.media_url) + '" controls preload="metadata"></audio>') : '') +
            (m.text ? '<div class="cm-msg__text">' + escapeHtml(m.text) + '</div>' : '') +
            '<button type="button" class="cm-msg__reply-btn" data-reply-id="' + m.id + '" data-reply-author="' + escapeHtml(m.author) + '" data-reply-text="' + escapeHtml(m.text || (m.media_type === 'audio' ? 'Голосовое сообщение' : 'Видео-сообщение')) + '"><span class="material-icons">reply</span> Ответить</button></div>';
        box.appendChild(el);
    }

    var apiUrl = box.getAttribute('data-api-url') || '/community/api/messages';
    var pending = false;
    var recorder = null;
    var recordedChunks = [];

    function setReply(id, author, text) {
        replyId.value = id;
        mediaReplyId.value = id;
        replyAuthor.textContent = author;
        replyText.textContent = text;
        replying.hidden = false;
        input.focus();
    }

    function clearReply() {
        replyId.value = '';
        mediaReplyId.value = '';
        replying.hidden = true;
    }

    function postTyping(active) {
        fetch('/community/api/typing', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('#cmChatForm input[name="csrf_token"]').value},
            body: JSON.stringify({typing: active})
        }).catch(function () {});
    }

    function pollTyping() {
        fetch('/community/api/typing').then(function (r) { return r.json(); }).then(function (data) {
            if (!typing) return;
            typing.textContent = data.users && data.users.length ? data.users.join(', ') + ' печатает...' : '';
        }).catch(function () {});
    }

    function startRecording(kind) {
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            alert('Запись медиа не поддерживается этим браузером');
            return;
        }
        navigator.mediaDevices.getUserMedia(kind === 'video' ? {audio: true, video: true} : {audio: true}).then(function (stream) {
            recordedChunks = [];
            recorder = new MediaRecorder(stream);
            recorder.ondataavailable = function (e) { if (e.data.size) recordedChunks.push(e.data); };
            recorder.onstop = function () {
                stream.getTracks().forEach(function (track) { track.stop(); });
                var blob = new Blob(recordedChunks, {type: recorder.mimeType || (kind === 'video' ? 'video/webm' : 'audio/webm')});
                var file = new File([blob], kind + '-' + Date.now() + '.webm', {type: blob.type});
                var transfer = new DataTransfer();
                transfer.items.add(file);
                mediaInput.files = transfer.files;
                mediaType.value = kind;
                mediaForm.submit();
            };
            recorder.start();
            var button = document.getElementById(kind === 'video' ? 'cmVideoBtn' : 'cmVoiceBtn');
            button.classList.add('is-recording');
            button.title = 'Остановить и отправить запись';
            button.querySelector('.material-icons').textContent = 'stop';
            button.onclick = function () {
                recorder.stop();
                button.classList.remove('is-recording');
                button.title = kind === 'video' ? 'Записать видео-кружок' : 'Записать голосовое';
                button.querySelector('.material-icons').textContent = kind === 'video' ? 'videocam' : 'mic';
                button.onclick = function () { startRecording(kind); };
            };
        }).catch(function () { alert('Нет доступа к микрофону или камере'); });
    }

    function poll() {
        if (pending) return;
        if (document.hidden) return;
        pending = true;
        var url = apiUrl + '?after_id=' + lastMessageId();
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var near = isNearBottom();
                data.messages.forEach(function (m) {
                    appendMessage(m, false);
                });
                if (near) scrollToBottom(false);
            })
            .catch(function () { /* сеть недоступна — повторим позже */ })
            .then(function () { pending = false; });
    }

    // Enter — отправка (Shift+Enter — перевод строки)
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (input.value.trim()) form.requestSubmit();
        }
    });
    input.addEventListener('input', function () { postTyping(Boolean(input.value.trim())); });
    input.addEventListener('blur', function () { postTyping(false); });
    box.addEventListener('click', function (e) {
        var button = e.target.closest('.cm-msg__reply-btn');
        if (!button) return;
        setReply(button.dataset.replyId, button.dataset.replyAuthor, button.dataset.replyText);
    });
    replyCancel.addEventListener('click', clearReply);
    document.getElementById('cmVoiceBtn').addEventListener('click', function () { startRecording('audio'); });
    document.getElementById('cmVideoBtn').addEventListener('click', function () { startRecording('video'); });

    // Автообновление
    setInterval(poll, 5000);
    setInterval(pollTyping, 2000);

    // Первичная прокрутка
    scrollToBottom(true);
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function () { scrollToBottom(true); });
    }
    setTimeout(function () { scrollToBottom(true); }, 250);
})();