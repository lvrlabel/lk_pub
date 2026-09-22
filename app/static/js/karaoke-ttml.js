/**
 * Генератор караоке TTML — ручной line-level sync в браузере.
 */
(function () {
    'use strict';

    var audio = document.getElementById('karaokeAudio');
    var fileInput = document.getElementById('karaokeAudioFile');
    var trackSelect = document.getElementById('karaokeTrackSelect');
    var lyricsInput = document.getElementById('karaokeLyrics');
    var titleInput = document.getElementById('karaokeTitle');
    var applyBtn = document.getElementById('karaokeApplyLyrics');
    var playBtn = document.getElementById('karaokePlayBtn');
    var markBtn = document.getElementById('karaokeMarkBtn');
    var undoBtn = document.getElementById('karaokeUndoBtn');
    var resetBtn = document.getElementById('karaokeResetBtn');
    var downloadBtn = document.getElementById('karaokeDownloadBtn');
    var linesBox = document.getElementById('karaokeLines');
    var timeLabel = document.getElementById('karaokeTimeLabel');
    var syncStatus = document.getElementById('karaokeSyncStatus');
    var tipEl = document.getElementById('karaokeTip');
    var sessionEl = document.getElementById('karaokeSession');
    var sessionLabel = document.getElementById('karaokeSessionLabel');
    var durationLabel = document.getElementById('karaokeDurationLabel');
    var playhead = document.getElementById('karaokePlayhead');
    var waveformEmpty = document.querySelector('.karaoke-waveform__empty');
    var playLabel = playBtn ? playBtn.querySelector('[data-play-label]') : null;

    if (!audio || !lyricsInput || !linesBox) return;

    var objectUrl = null;
    var lines = []; /* { text, begin: number|null } */
    var nextIndex = 0;
    var rafId = 0;

    function formatTime(sec) {
        if (!isFinite(sec) || sec < 0) sec = 0;
        var m = Math.floor(sec / 60);
        var s = sec - m * 60;
        var whole = Math.floor(s);
        var ms = Math.round((s - whole) * 1000);
        if (ms === 1000) {
            whole += 1;
            ms = 0;
        }
        return m + ':' + String(whole).padStart(2, '0') + '.' + String(ms).padStart(3, '0');
    }

    function formatTtmlTime(sec) {
        if (!isFinite(sec) || sec < 0) sec = 0;
        var h = Math.floor(sec / 3600);
        var m = Math.floor((sec % 3600) / 60);
        var s = sec - h * 3600 - m * 60;
        var whole = Math.floor(s);
        var ms = Math.round((s - whole) * 1000);
        if (ms === 1000) {
            whole += 1;
            ms = 0;
        }
        var mm = String(m).padStart(2, '0');
        var ss = String(whole).padStart(2, '0');
        var mmm = String(ms).padStart(3, '0');
        if (h > 0) {
            return String(h).padStart(2, '0') + ':' + mm + ':' + ss + '.' + mmm;
        }
        return mm + ':' + ss + '.' + mmm;
    }

    function escapeXml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&apos;');
    }

    function parseLyrics(text) {
        return String(text || '')
            .replace(/\r\n/g, '\n')
            .replace(/\r/g, '\n')
            .split('\n')
            .map(function (l) {
                return l.trim();
            })
            .filter(function (l) {
                return l.length > 0;
            });
    }

    function markedCount() {
        var n = 0;
        for (var i = 0; i < lines.length; i++) {
            if (lines[i].begin != null) n += 1;
        }
        return n;
    }

    function updateStatus() {
        if (syncStatus) {
            syncStatus.textContent = markedCount() + ' из ' + lines.length + ' строк';
        }
        var hasAudio = !!(audio.src && !audio.error);
        var hasLines = lines.length > 0;
        if (playBtn) playBtn.disabled = !hasAudio;
        if (markBtn) markBtn.disabled = !hasAudio || !hasLines || nextIndex >= lines.length;
        if (undoBtn) undoBtn.disabled = markedCount() === 0;
        if (resetBtn) resetBtn.disabled = !hasLines;
        var complete = hasLines && markedCount() === lines.length;
        if (downloadBtn) {
            downloadBtn.disabled = !complete;
            downloadBtn.classList.toggle('is-complete', complete);
        }
        if (sessionEl) sessionEl.classList.toggle('is-ready', hasAudio);
        if (sessionLabel) sessionLabel.textContent = hasAudio ? 'Аудио загружено' : 'Нет аудио';
    }

    function setTip(text) {
        if (tipEl) tipEl.textContent = text;
    }

    function renderLines() {
        if (!lines.length) {
            linesBox.innerHTML = '<div class="karaoke-lines-empty">Строки появятся после подготовки текста</div>';
            updateStatus();
            return;
        }

        var html = '';
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            var cls = 'karaoke-line';
            if (line.begin != null) cls += ' is-synced';
            if (i === nextIndex) cls += ' is-next';
            var time = line.begin != null ? formatTime(line.begin) : '—:—.—';
            html +=
                '<div class="' +
                cls +
                '" data-index="' +
                i +
                '">' +
                '<span class="karaoke-line__idx">' +
                (i + 1) +
                '</span>' +
                '<span class="karaoke-line__text"></span>' +
                '<span class="karaoke-line__time">' +
                time +
                '</span>' +
                '</div>';
        }
        linesBox.innerHTML = html;

        var textNodes = linesBox.querySelectorAll('.karaoke-line__text');
        for (var j = 0; j < textNodes.length; j++) {
            textNodes[j].textContent = lines[j].text;
        }

        var nextEl = linesBox.querySelector('.karaoke-line.is-next');
        if (nextEl && typeof nextEl.scrollIntoView === 'function') {
            nextEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
        updateStatus();
    }

    function highlightByTime(t) {
        var active = -1;
        for (var i = 0; i < lines.length; i++) {
            if (lines[i].begin != null && lines[i].begin <= t) {
                active = i;
            }
        }
        var nodes = linesBox.querySelectorAll('.karaoke-line');
        for (var n = 0; n < nodes.length; n++) {
            nodes[n].classList.toggle('is-active', n === active);
        }
    }

    function tick() {
        if (timeLabel) timeLabel.textContent = formatTime(audio.currentTime || 0);
        updatePlayhead();
        highlightByTime(audio.currentTime || 0);
        if (!audio.paused && !audio.ended) {
            rafId = window.requestAnimationFrame(tick);
        }
    }

    function updatePlayhead() {
        var duration = audio.duration;
        var ratio = isFinite(duration) && duration > 0 ? (audio.currentTime || 0) / duration : 0;
        if (playhead) playhead.style.left = Math.max(0, Math.min(100, ratio * 100)) + '%';
    }

    function startTick() {
        if (rafId) window.cancelAnimationFrame(rafId);
        rafId = window.requestAnimationFrame(tick);
    }

    function revokeObjectUrl() {
        if (objectUrl) {
            URL.revokeObjectURL(objectUrl);
            objectUrl = null;
        }
    }

    function loadAudioFromUrl(url, fromFile) {
        if (!url) return;
        if (!fromFile) revokeObjectUrl();
        audio.src = url;
        audio.load();
        playBtn.disabled = false;
        setTip('Аудио готово. Нажмите Play и отмечайте начало каждой строки пробелом или кнопкой «Отметить строку».');
        updateStatus();
        if (waveformEmpty) waveformEmpty.hidden = true;
    }

    function applyLyrics() {
        var parsed = parseLyrics(lyricsInput.value);
        if (!parsed.length) {
            setTip('Вставьте текст песни — по одной строке на строку.');
            return;
        }
        lines = parsed.map(function (text) {
            return { text: text, begin: null };
        });
        nextIndex = 0;
        renderLines();
        setTip('Строки готовы. Включите трек и отмечайте строки в такт. Пробел = отметить.');
    }

    function markLine() {
        if (!audio.src || nextIndex >= lines.length) return;
        var t = audio.currentTime || 0;
        lines[nextIndex].begin = t;
        nextIndex += 1;
        renderLines();
        if (nextIndex >= lines.length) {
            setTip('Все строки отмечены. Можно скачать TTML или Undo, если ошиблись.');
            if (!audio.paused) {
                audio.pause();
                syncPlayUi();
            }
        }
    }

    function undoMark() {
        if (!lines.length) return;
        var last = -1;
        for (var i = lines.length - 1; i >= 0; i--) {
            if (lines[i].begin != null) {
                last = i;
                break;
            }
        }
        if (last < 0) return;
        lines[last].begin = null;
        nextIndex = last;
        renderLines();
        setTip('Последняя отметка снята. Продолжайте с этой строки.');
    }

    function resetMarks() {
        for (var i = 0; i < lines.length; i++) {
            lines[i].begin = null;
        }
        nextIndex = 0;
        renderLines();
        setTip('Таймкоды сброшены. Можно синхронизировать заново.');
    }

    function lineEnds() {
        var duration = isFinite(audio.duration) ? audio.duration : null;
        var ends = [];
        for (var i = 0; i < lines.length; i++) {
            var begin = lines[i].begin;
            if (begin == null) {
                ends.push(null);
                continue;
            }
            var end = null;
            for (var j = i + 1; j < lines.length; j++) {
                if (lines[j].begin != null) {
                    end = lines[j].begin;
                    break;
                }
            }
            if (end == null) {
                end = duration != null && duration > begin ? duration : begin + 3;
            }
            if (end <= begin) end = begin + 0.2;
            ends.push(end);
        }
        return ends;
    }

    function buildTtml() {
        var ends = lineEnds();
        var title = (titleInput && titleInput.value.trim()) || 'Lyrics';
        var parts = [];
        parts.push('<?xml version="1.0" encoding="UTF-8"?>');
        parts.push(
            '<tt xmlns="http://www.w3.org/ns/ttml" xmlns:tts="http://www.w3.org/ns/ttml#styling" xmlns:itunes="http://music.apple.com/lyric-ttml-internal" xml:lang="ru" itunes:timing="line">'
        );
        parts.push('  <head>');
        parts.push('    <metadata>');
        parts.push('      <ttm:title xmlns:ttm="http://www.w3.org/ns/ttml#metadata">' + escapeXml(title) + '</ttm:title>');
        parts.push('    </metadata>');
        parts.push('  </head>');
        parts.push('  <body>');
        parts.push('    <div>');

        for (var i = 0; i < lines.length; i++) {
            if (lines[i].begin == null || ends[i] == null) continue;
            parts.push(
                '      <p begin="' +
                    formatTtmlTime(lines[i].begin) +
                    '" end="' +
                    formatTtmlTime(ends[i]) +
                    '">' +
                    escapeXml(lines[i].text) +
                    '</p>'
            );
        }

        parts.push('    </div>');
        parts.push('  </body>');
        parts.push('</tt>');
        return parts.join('\n') + '\n';
    }

    function downloadTtml() {
        if (!lines.length || markedCount() !== lines.length) {
            setTip('Сначала отметьте начало каждой строки. Только полная разметка попадёт в TTML.');
            return;
        }
        var xml = buildTtml();
        var blob = new Blob([xml], { type: 'application/ttml+xml;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        var safeTitle = ((titleInput && titleInput.value.trim()) || 'lyrics')
            .replace(/[\\/:*?"<>|]+/g, '_')
            .slice(0, 80);
        a.href = url;
        a.download = safeTitle + '.ttml';
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.setTimeout(function () {
            URL.revokeObjectURL(url);
        }, 1000);
    }

    function syncPlayUi() {
        var playing = !audio.paused && !audio.ended;
        if (playLabel) playLabel.textContent = playing ? 'Pause' : 'Play';
        var icon = playBtn.querySelector('.material-icons');
        if (icon) icon.textContent = playing ? 'pause' : 'play_arrow';
    }

    function togglePlay() {
        if (!audio.src) return;
        if (audio.paused) {
            var p = audio.play();
            if (p && typeof p.catch === 'function') {
                p.catch(function () {
                    setTip('Не удалось запустить аудио. Проверьте файл или выберите другой трек.');
                });
            }
        } else {
            audio.pause();
        }
    }

    if (fileInput) {
        fileInput.addEventListener('change', function () {
            var file = fileInput.files && fileInput.files[0];
            if (!file) return;
            if (trackSelect) trackSelect.value = '';
            revokeObjectUrl();
            objectUrl = URL.createObjectURL(file);
            loadAudioFromUrl(objectUrl, true);
            if (titleInput && !titleInput.value.trim()) {
                titleInput.value = file.name.replace(/\.[^.]+$/, '');
            }
        });
    }

    if (trackSelect) {
        trackSelect.addEventListener('change', function () {
            var url = trackSelect.value;
            if (!url) return;
            if (fileInput) fileInput.value = '';
            revokeObjectUrl();
            loadAudioFromUrl(url, false);
            var opt = trackSelect.options[trackSelect.selectedIndex];
            var label = (opt && opt.text) || '';
            if (titleInput && label) {
                var parts = label.split(' — ');
                titleInput.value = (parts.length > 1 ? parts.slice(1).join(' — ') : label).trim();
            }
            var trackId = opt ? opt.getAttribute('data-track-id') : '';
            var mapEl = document.getElementById('karaokeTrackLyricsMap');
            var lyricsMap = {};
            if (mapEl) {
                try {
                    lyricsMap = JSON.parse(mapEl.textContent || '{}') || {};
                } catch (err) {
                    lyricsMap = {};
                }
            }
            var lyrics = trackId && lyricsMap[String(trackId)] ? lyricsMap[String(trackId)] : '';
            if (lyrics && lyricsInput && !lyricsInput.value.trim()) {
                lyricsInput.value = lyrics;
            }
        });
    }

    if (applyBtn) applyBtn.addEventListener('click', applyLyrics);
    if (playBtn) playBtn.addEventListener('click', togglePlay);
    if (markBtn) markBtn.addEventListener('click', markLine);
    if (undoBtn) undoBtn.addEventListener('click', undoMark);
    if (resetBtn) resetBtn.addEventListener('click', resetMarks);
    if (downloadBtn) downloadBtn.addEventListener('click', downloadTtml);

    lyricsInput.addEventListener('input', function () {
        if (!lines.length) return;
        /* мягко предупреждаем: после apply таймкоды живут отдельно */
    });

    audio.addEventListener('play', function () {
        syncPlayUi();
        startTick();
    });
    audio.addEventListener('pause', function () {
        syncPlayUi();
        tick();
    });
    audio.addEventListener('ended', function () {
        syncPlayUi();
        tick();
    });
    audio.addEventListener('timeupdate', function () {
        if (timeLabel) timeLabel.textContent = formatTime(audio.currentTime || 0);
        updatePlayhead();
        highlightByTime(audio.currentTime || 0);
    });
    audio.addEventListener('loadedmetadata', updateStatus);
    audio.addEventListener('loadedmetadata', function () {
        if (durationLabel) durationLabel.textContent = '/ ' + formatTime(audio.duration || 0).replace('.000', '');
        updatePlayhead();
    });
    audio.addEventListener('error', function () {
        setTip('Ошибка загрузки аудио. Попробуйте другой файл.');
        updateStatus();
    });

    document.addEventListener('keydown', function (e) {
        if (e.code !== 'Space' && e.key !== ' ') return;
        var tag = (e.target && e.target.tagName) || '';
        if (tag === 'TEXTAREA' || tag === 'INPUT' || tag === 'SELECT' || (e.target && e.target.isContentEditable)) {
            return;
        }
        e.preventDefault();
        if (markBtn && !markBtn.disabled) {
            markLine();
        }
    });

    updateStatus();
})();
