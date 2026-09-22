(function () {
    'use strict';

    var MAX_SECONDS = 180;

    function pad2(n) {
        return n < 10 ? '0' + n : String(n);
    }

    function formatDuration(sec) {
        sec = Math.max(0, Math.floor(sec));
        var m = Math.floor(sec / 60);
        var s = sec % 60;
        return m + ':' + pad2(s);
    }

    function pickMimeType() {
        if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) {
            return '';
        }
        var types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/mp4',
            'audio/aac'
        ];
        for (var i = 0; i < types.length; i++) {
            if (MediaRecorder.isTypeSupported(types[i])) {
                return types[i];
            }
        }
        return '';
    }

    function extFromMime(mime) {
        if (!mime) return 'webm';
        if (mime.indexOf('ogg') !== -1) return 'ogg';
        if (mime.indexOf('mp4') !== -1 || mime.indexOf('aac') !== -1) return 'm4a';
        return 'webm';
    }

    function initManagerChatVoice() {
        var btn = document.getElementById('managerChatVoiceBtn');
        if (!btn) return;

        var form = document.querySelector('.manager-chat-composer-form');
        var fileInput = document.getElementById('managerReplyAttachments');
        var textarea = document.getElementById('managerReplyMessage');
        var panel = document.getElementById('managerChatVoicePanel');
        var panelTitle = document.getElementById('managerChatVoicePanelTitle');
        var panelClose = document.getElementById('managerChatVoicePanelClose');
        var stepRecord = document.getElementById('managerChatVoiceStepRecord');
        var stepReview = document.getElementById('managerChatVoiceStepReview');
        var stopBtn = document.getElementById('managerChatVoiceStopBtn');
        var sendBtn = document.getElementById('managerChatVoiceSendBtn');
        var retryBtn = document.getElementById('managerChatVoiceRetryBtn');
        var previewAudio = document.getElementById('managerChatVoicePreviewAudio');
        var recordingTimer = document.getElementById('managerChatVoiceRecordingTimer');
        var voiceFlag = document.getElementById('managerChatVoiceFlag');
        var composerRow = document.querySelector('.manager-chat-composer-row');

        if (!form || !fileInput || !textarea || !panel) return;

        var recorder = null;
        var stream = null;
        var chunks = [];
        var mimeType = pickMimeType();
        var recording = false;
        var startedAt = 0;
        var timerId = null;
        var pendingVoiceFile = null;
        var previewUrl = null;

        if (!mimeType || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            btn.disabled = true;
            btn.title = 'Запись голоса недоступна в этом браузере';
            return;
        }

        function revokePreviewUrl() {
            if (previewUrl) {
                URL.revokeObjectURL(previewUrl);
                previewUrl = null;
            }
        }

        function showStep(name) {
            if (stepRecord) stepRecord.hidden = name !== 'record';
            if (stepReview) stepReview.hidden = name !== 'review';
            if (panelTitle) {
                panelTitle.textContent = name === 'review'
                    ? 'Прослушайте и отправьте'
                    : 'Запись голосового';
            }
        }

        function openPanel(step) {
            panel.hidden = false;
            if (composerRow) composerRow.classList.add('is-voice-muted');
            showStep(step);
        }

        function closePanel() {
            panel.hidden = true;
            if (composerRow) composerRow.classList.remove('is-voice-muted');
            showStep('record');
        }

        function clearVoiceAttachment() {
            pendingVoiceFile = null;
            fileInput.value = '';
            if (voiceFlag) voiceFlag.value = '0';
            if (previewAudio) {
                previewAudio.pause();
                previewAudio.removeAttribute('src');
            }
            revokePreviewUrl();
        }

        function cancelAll() {
            stopRecording(true);
            clearVoiceAttachment();
            closePanel();
            btn.classList.remove('is-recording');
        }

        function setVoiceFile(file, durationSec) {
            pendingVoiceFile = file;
            if (voiceFlag) voiceFlag.value = '1';
            try {
                var dt = new DataTransfer();
                dt.items.add(file);
                fileInput.files = dt.files;
            } catch (err) {
                clearVoiceAttachment();
                alert('Не удалось прикрепить голосовое сообщение. Попробуйте другой браузер.');
                return false;
            }
            if (previewAudio) {
                revokePreviewUrl();
                previewUrl = URL.createObjectURL(file);
                previewAudio.src = previewUrl;
            }
            if (recordingTimer && durationSec) {
                recordingTimer.textContent = formatDuration(durationSec);
            }
            openPanel('review');
            return true;
        }

        function stopTracks() {
            if (stream) {
                stream.getTracks().forEach(function (track) { track.stop(); });
                stream = null;
            }
        }

        function stopRecordingUI() {
            recording = false;
            btn.classList.remove('is-recording');
            if (timerId) {
                clearInterval(timerId);
                timerId = null;
            }
        }

        function stopRecording(silent) {
            if (!recorder || recorder.state === 'inactive') {
                stopRecordingUI();
                return;
            }
            if (silent) {
                recorder.onstop = function () {
                    stopTracks();
                    stopRecordingUI();
                };
            }
            recorder.stop();
        }

        async function beginRecording() {
            clearVoiceAttachment();
            openPanel('record');

            try {
                stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            } catch (err) {
                cancelAll();
                alert('Нет доступа к микрофону. Разрешите запись в настройках браузера.');
                return;
            }

            chunks = [];
            recorder = new MediaRecorder(stream, { mimeType: mimeType });
            recorder.ondataavailable = function (e) {
                if (e.data && e.data.size > 0) chunks.push(e.data);
            };
            recorder.onstop = function () {
                stopTracks();
                stopRecordingUI();

                if (!chunks.length) {
                    if (!panel.hidden) cancelAll();
                    return;
                }

                var blob = new Blob(chunks, { type: mimeType });
                if (blob.size < 800) {
                    alert('Запись слишком короткая. Попробуйте ещё раз и говорите дольше.');
                    beginRecording();
                    return;
                }

                var ext = extFromMime(mimeType);
                var name = 'voice-' + Date.now() + '.' + ext;
                var file = new File([blob], name, { type: mimeType });
                var durationSec = startedAt ? (Date.now() - startedAt) / 1000 : 0;
                setVoiceFile(file, durationSec);
            };

            recording = true;
            startedAt = Date.now();
            btn.classList.add('is-recording');
            if (recordingTimer) recordingTimer.textContent = '0:00';

            timerId = setInterval(function () {
                var elapsed = (Date.now() - startedAt) / 1000;
                if (recordingTimer) recordingTimer.textContent = formatDuration(elapsed);
                if (elapsed >= MAX_SECONDS) stopRecording(false);
            }, 200);

            recorder.start(250);
        }

        btn.addEventListener('click', function () {
            if (recording) return;
            if (!panel.hidden && stepReview && !stepReview.hidden) return;
            beginRecording();
        });

        if (stopBtn) {
            stopBtn.addEventListener('click', function () {
                if (recording) stopRecording(false);
            });
        }

        if (retryBtn) {
            retryBtn.addEventListener('click', function () {
                clearVoiceAttachment();
                beginRecording();
            });
        }

        if (sendBtn) {
            sendBtn.addEventListener('click', function () {
                if (!pendingVoiceFile) {
                    alert('Сначала запишите голосовое сообщение.');
                    return;
                }
                if (recording) {
                    alert('Сначала нажмите «Готово».');
                    return;
                }
                if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
            });
        }

        if (panelClose) {
            panelClose.addEventListener('click', cancelAll);
        }

        form.addEventListener('submit', function (e) {
            if (recording) {
                e.preventDefault();
                alert('Сначала нажмите «Готово» и завершите запись.');
                return;
            }
            var hasText = textarea.value.trim().length > 0;
            var hasFiles = fileInput.files && fileInput.files.length > 0;
            if (!hasText && !hasFiles) {
                e.preventDefault();
                alert('Напишите сообщение или запишите голосовое.');
            }
        });

        fileInput.addEventListener('change', function () {
            if (fileInput.files && fileInput.files.length && !pendingVoiceFile) {
                if (voiceFlag) voiceFlag.value = '0';
                closePanel();
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initManagerChatVoice);
    } else {
        initManagerChatVoice();
    }
})();
