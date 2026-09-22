/**
 * Новый релиз — DMB shell (фаза 2: медиакаталог + вкладки трека).
 */
(function () {
    'use strict';

    var root = document.getElementById('rdmbCreate');
    if (!root) return;

    var SECTIONS = [
        { id: 'data', title: 'Новый релиз — Данные релиза' },
        { id: 'media', title: 'Новый релиз — Медиафайлы' },
        { id: 'tracks', title: 'Новый релиз — Треки' },
        { id: 'extra', title: 'Новый релиз — Дополнительно' },
        { id: 'countries', title: 'Новый релиз — Страны' },
        { id: 'distribution', title: 'Новый релиз — Дистрибуция' },
        { id: 'dates', title: 'Новый релиз — Даты и цены' },
        { id: 'events', title: 'Новый релиз — События по релизу' },
        { id: 'apply', title: 'Новый релиз — Применить' },
    ];

    var ROLE_LABELS = {
        featuring: 'Featuring',
        lyricist: 'Автор слов',
        composer: 'Композитор',
        arranger: 'Аранжировщик',
        producer: 'Продюсер',
        mixer: 'Сведение',
        mastering: 'Мастеринг',
        remixer: 'Ремиксер',
    };

    var form = document.getElementById('releaseCreateForm');
    var tracksList = document.getElementById('tracksList');
    var template = document.getElementById('trackCardTemplate');
    var addBtn = document.getElementById('addTrackBtn');
    var artistsHidden = document.getElementById('artists');
    var displayArtist = document.getElementById('displayArtist');
    var titleInput = document.getElementById('title');
    var genreInput = document.getElementById('genre');
    var dateInput = document.getElementById('release_date');
    var coverInput = document.getElementById('coverInput');
    var coverPreview = document.getElementById('coverPreview');
    var coverPreviewMedia = document.getElementById('coverPreviewMedia');
    var mediaBulkInput = document.getElementById('mediaBulkInput');
    var mediaBody = document.getElementById('mediaCatalogBody');
    var mediaEmpty = document.getElementById('mediaCatalogEmpty');
    var confirmBox = document.getElementById('confirmNoDrugs');
    var submitBtn = document.getElementById('submitModerationBtn');
    var sectionTitle = document.getElementById('rdmbSectionTitle');
    var prevBtn = document.getElementById('rdmbPrevBtn');
    var nextBtn = document.getElementById('rdmbNextBtn');
    var statTracks = document.getElementById('statTracks');
    var mainChips = document.getElementById('mainArtistsChips');
    var contribModal = document.getElementById('contribModal');
    var contribName = document.getElementById('contribName');
    var contribSaveBtn = document.getElementById('contribSaveBtn');

    var nextIndex = 0;
    var currentSection = 'data';
    var mainArtists = [];
    var contribTargetCard = null;

    function defaultArtists() {
        return root.getAttribute('data-default-artists') || '';
    }

    function qs(sel, el) {
        return (el || document).querySelector(sel);
    }

    function qsa(sel, el) {
        return Array.prototype.slice.call((el || document).querySelectorAll(sel));
    }

    function formatBytes(n) {
        n = Number(n) || 0;
        if (n < 1024) return n + ' B';
        if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
        return (n / (1024 * 1024)).toFixed(2) + ' MB';
    }

    function extOf(name) {
        var m = String(name || '').toLowerCase().match(/\.([a-z0-9]+)$/);
        return m ? m[1].toUpperCase() : '—';
    }

    function syncArtistsHidden() {
        var display = (displayArtist && displayArtist.value.trim()) || '';
        var joined = mainArtists.length ? mainArtists.join(', ') : display;
        if (artistsHidden) artistsHidden.value = joined || display;
    }

    function renderChips(container, list, onRemove) {
        if (!container) return;
        container.innerHTML = '';
        list.forEach(function (item, idx) {
            var name = typeof item === 'string' ? item : item.name;
            var chip = document.createElement('span');
            chip.className = 'rdmb__chip';
            var label = name;
            if (item && item.roles && item.roles.length) {
                label +=
                    ' · ' +
                    item.roles
                        .map(function (r) {
                            return ROLE_LABELS[r] || r;
                        })
                        .join(', ');
            }
            chip.appendChild(document.createTextNode(label));
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.setAttribute('aria-label', 'Удалить');
            btn.innerHTML = '<span class="material-icons" style="font-size:1rem">close</span>';
            btn.addEventListener('click', function () {
                onRemove(idx);
            });
            chip.appendChild(btn);
            container.appendChild(chip);
        });
    }

    function refreshArtistChips() {
        renderChips(mainChips, mainArtists, function (idx) {
            mainArtists.splice(idx, 1);
            refreshArtistChips();
            syncArtistsHidden();
            updateReady();
        });
        syncArtistsHidden();
    }

    function setReady(key, ok) {
        var item = qs('[data-ready="' + key + '"]');
        if (!item) return;
        item.classList.toggle('is-ok', !!ok);
        item.classList.toggle('is-missing', !ok);
        var icon = qs('.material-icons', item);
        if (icon) icon.textContent = ok ? 'check_circle' : 'error_outline';
    }

    function countCompleteTracks() {
        var n = 0;
        if (!tracksList) return 0;
        qsa('[data-track-card]', tracksList).forEach(function (card) {
            var title = qs('[data-field="title"]', card);
            var artists = qs('[data-field="artists"]', card);
            var wav = qs('[data-wav-input]', card);
            if (
                title &&
                title.value.trim() &&
                artists &&
                artists.value.trim() &&
                wav &&
                wav.files &&
                wav.files.length
            ) {
                n += 1;
            }
        });
        return n;
    }

    function countSelectedPlatforms() {
        return qsa('.js-platform:checked').length;
    }

    function updateNavWarn() {
        var hasCover = !!(coverInput && coverInput.files && coverInput.files.length);
        var hasMeta = !!(
            titleInput &&
            titleInput.value.trim() &&
            artistsHidden &&
            artistsHidden.value.trim() &&
            genreInput &&
            genreInput.value
        );
        var hasDate = !!(dateInput && dateInput.value);
        var tracksOk = countCompleteTracks() > 0;
        var platformsOk = countSelectedPlatforms() > 0;

        qsa('[data-rdmb-section]').forEach(function (btn) {
            var id = btn.getAttribute('data-rdmb-section');
            var warn = false;
            if (id === 'data') warn = !hasMeta;
            if (id === 'media') warn = !hasCover;
            if (id === 'tracks') warn = !tracksOk;
            if (id === 'dates') warn = !hasDate;
            if (id === 'distribution') warn = !platformsOk;
            btn.classList.toggle('is-warn', warn);
        });
    }

    function refreshMediaCatalog() {
        if (!mediaBody) return;
        mediaBody.innerHTML = '';
        var rows = 0;

        function addRow(assigned, trackLabel, file, onClear) {
            if (!file) return;
            rows += 1;
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' +
                assigned +
                '</td>' +
                '<td>' +
                (trackLabel || '—') +
                '</td>' +
                '<td>' +
                (file.name || '—') +
                '</td>' +
                '<td>' +
                extOf(file.name) +
                '</td>' +
                '<td>' +
                formatBytes(file.size) +
                '</td>' +
                '<td></td>';
            if (onClear) {
                var td = tr.lastElementChild;
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'rdmb__icon-btn';
                btn.title = 'Убрать файл';
                btn.innerHTML = '<span class="material-icons" style="font-size:1.05rem">close</span>';
                btn.addEventListener('click', onClear);
                td.appendChild(btn);
            }
            mediaBody.appendChild(tr);
        }

        if (coverInput && coverInput.files && coverInput.files[0]) {
            addRow('Обложка', '—', coverInput.files[0], function () {
                coverInput.value = '';
                setCoverPreview(
                    '<div class="rdmb__cover-ph"><span class="material-icons" aria-hidden="true">add</span><span>Добавить обложку</span></div>',
                    false
                );
                refreshMediaCatalog();
                updateReady();
            });
        }

        if (tracksList) {
            qsa('[data-track-card]', tracksList).forEach(function (card, i) {
                var wav = qs('[data-wav-input]', card);
                var titleEl = qs('[data-field="title"]', card);
                var file = wav && wav.files && wav.files[0];
                if (!file) return;
                var tname = (titleEl && titleEl.value.trim()) || 'Трек ' + (i + 1);
                addRow('Стерео трек', tname, file, function () {
                    wav.value = '';
                    var zone = qs('[data-wav-zone]', card);
                    var label = qs('[data-wav-label]', card);
                    var props = qs('[data-wav-props]', card);
                    if (label) label.textContent = 'Файл не загружен — нажмите или перетащите';
                    if (zone) zone.classList.remove('has-file');
                    if (props) props.textContent = 'ФОРМАТ · РАЗМЕР · ИМЯ ФАЙЛА';
                    refreshMediaCatalog();
                    updateReady();
                });
            });
        }

        if (rows === 0) {
            var empty = document.createElement('tr');
            empty.className = 'rdmb__table-empty';
            empty.innerHTML = '<td colspan="6">Медиафайлов в каталоге релиза нет</td>';
            mediaBody.appendChild(empty);
        }
    }

    function updateReady() {
        var hasCover = !!(coverInput && coverInput.files && coverInput.files.length);
        var hasMeta = !!(
            titleInput &&
            titleInput.value.trim() &&
            artistsHidden &&
            artistsHidden.value.trim() &&
            genreInput &&
            genreInput.value
        );
        var hasDate = !!(dateInput && dateInput.value);
        var tracksOk = countCompleteTracks() > 0;
        var platformsOk = countSelectedPlatforms() > 0;
        var confirmed = !!(confirmBox && confirmBox.checked);

        setReady('cover', hasCover);
        setReady('meta', hasMeta);
        setReady('date', hasDate);
        setReady('tracks', tracksOk);
        setReady('platforms', platformsOk);
        setReady('confirm', confirmed);

        if (statTracks) {
            var total = tracksList ? qsa('[data-track-card]', tracksList).length : 0;
            statTracks.textContent = String(total);
        }
        if (submitBtn) {
            submitBtn.disabled = !(
                hasCover &&
                hasMeta &&
                hasDate &&
                tracksOk &&
                platformsOk &&
                confirmed
            );
        }
        updateNavWarn();
        refreshMediaCatalog();
        syncTrackDateHints();
        refreshApplyErrors({
            hasCover: hasCover,
            hasMeta: hasMeta,
            hasDate: hasDate,
            tracksOk: tracksOk,
            platformsOk: platformsOk,
            confirmed: confirmed,
        });
    }

    function refreshApplyErrors(state) {
        var list = document.getElementById('applyErrorsList');
        var box = document.getElementById('applyIssuesBox');
        var sub = document.getElementById('applyIssuesSub');
        var ok = document.getElementById('applyReadyMsg');
        if (!list || !box) return;

        var issues = [];
        if (!state.hasCover) {
            issues.push({ section: 'media', text: 'Обложка релиза обязательна' });
        }
        if (!state.hasMeta) {
            issues.push({
                section: 'data',
                text: 'Заполните название, артиста и жанр в «Данные релиза»',
            });
        }
        if (!state.hasDate) {
            issues.push({ section: 'dates', text: 'Укажите дату релиза в «Даты и цены»' });
        }
        if (!state.tracksOk) {
            issues.push({
                section: 'tracks',
                text: 'Добавьте хотя бы один трек с WAV, названием и артистами',
            });
        }
        if (!state.platformsOk) {
            issues.push({
                section: 'distribution',
                text: 'Выберите хотя бы одну площадку в «Дистрибуция»',
            });
        }
        if (!state.confirmed) {
            issues.push({
                section: 'apply',
                text: 'Подтвердите отсутствие пропаганды наркотических средств',
            });
        }

        list.innerHTML = '';
        issues.forEach(function (issue, idx) {
            var li = document.createElement('li');
            var a = document.createElement('a');
            a.href = '#';
            a.textContent = idx + 1 + '. ' + issue.text;
            a.addEventListener('click', function (e) {
                e.preventDefault();
                activateSection(issue.section);
            });
            li.appendChild(a);
            list.appendChild(li);
        });

        var ready = issues.length === 0;
        box.classList.toggle('is-ready', ready);
        if (sub) sub.textContent = ready ? 'Готово' : 'Критические ошибки';
        if (ok) ok.hidden = !ready;
        list.hidden = ready;
    }

    function syncTrackDateHints() {
        var dateVal = dateInput && dateInput.value ? dateInput.value : 'не указана';
        qsa('[data-track-date-hint]').forEach(function (el) {
            el.textContent = 'Будет использована дата релиза: ' + dateVal + '.';
        });
    }

    function activateSection(id) {
        currentSection = id;
        qsa('[data-rdmb-section]').forEach(function (btn) {
            btn.classList.toggle('is-active', btn.getAttribute('data-rdmb-section') === id);
        });
        qsa('[data-rdmb-panel]').forEach(function (panel) {
            panel.hidden = panel.getAttribute('data-rdmb-panel') !== id;
        });
        var meta = SECTIONS.find(function (s) {
            return s.id === id;
        });
        if (sectionTitle && meta) sectionTitle.textContent = meta.title;
        var idx = SECTIONS.findIndex(function (s) {
            return s.id === id;
        });
        if (prevBtn) prevBtn.disabled = idx <= 0;
        if (nextBtn) nextBtn.textContent = idx >= SECTIONS.length - 1 ? 'К проверке' : 'Далее';
    }

    function initNav() {
        qsa('[data-rdmb-section]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                activateSection(btn.getAttribute('data-rdmb-section'));
            });
        });
        if (prevBtn) {
            prevBtn.addEventListener('click', function () {
                var idx = SECTIONS.findIndex(function (s) {
                    return s.id === currentSection;
                });
                if (idx > 0) activateSection(SECTIONS[idx - 1].id);
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', function () {
                var idx = SECTIONS.findIndex(function (s) {
                    return s.id === currentSection;
                });
                if (idx < SECTIONS.length - 1) activateSection(SECTIONS[idx + 1].id);
                else activateSection('apply');
            });
        }
    }

    function setCoverPreview(html, hasImage) {
        [coverPreview, coverPreviewMedia].forEach(function (el) {
            if (!el) return;
            el.innerHTML = html;
            el.classList.toggle('has-image', !!hasImage);
        });
    }

    function applyCoverFile(file) {
        if (!file || !coverInput) return;
        var dt = new DataTransfer();
        dt.items.add(file);
        coverInput.files = dt.files;
        var reader = new FileReader();
        reader.onload = function (ev) {
            setCoverPreview('<img src="' + ev.target.result + '" alt="Обложка">', true);
        };
        reader.readAsDataURL(file);
        updateReady();
    }

    function findEmptyWavCard() {
        var cards = qsa('[data-track-card]', tracksList);
        for (var i = 0; i < cards.length; i++) {
            var wav = qs('[data-wav-input]', cards[i]);
            if (wav && !(wav.files && wav.files.length)) return cards[i];
        }
        return null;
    }

    function assignWavToCard(card, file) {
        if (!card || !file) return;
        var input = qs('[data-wav-input]', card);
        var zone = qs('[data-wav-zone]', card);
        var label = qs('[data-wav-label]', card);
        var props = qs('[data-wav-props]', card);
        var dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        if (label) label.textContent = file.name;
        if (zone) zone.classList.add('has-file');
        if (props) {
            props.textContent =
                extOf(file.name) + ' · ' + formatBytes(file.size) + ' · ' + file.name;
        }
        var titleEl = qs('[data-field="title"]', card);
        if (titleEl && !titleEl.value.trim()) {
            titleEl.value = file.name.replace(/\.wav$/i, '');
        }
        renumberTracks();
    }

    function initCover() {
        if (!coverInput) return;
        [coverPreview, coverPreviewMedia].forEach(function (el) {
            if (!el) return;
            el.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    coverInput.click();
                }
            });
        });
        coverInput.addEventListener('change', function () {
            var file = coverInput.files && coverInput.files[0];
            if (!file) {
                updateReady();
                return;
            }
            applyCoverFile(file);
        });

        var mediaUploadBtn = document.getElementById('mediaUploadBtn');
        var mediaCoverBtn = document.getElementById('mediaCoverBtn');
        if (mediaCoverBtn) {
            mediaCoverBtn.addEventListener('click', function () {
                coverInput.click();
            });
        }
        if (mediaUploadBtn && mediaBulkInput) {
            mediaUploadBtn.addEventListener('click', function () {
                mediaBulkInput.click();
            });
            mediaBulkInput.addEventListener('change', function () {
                var files = Array.prototype.slice.call(mediaBulkInput.files || []);
                files.forEach(function (file) {
                    var name = (file.name || '').toLowerCase();
                    if (/\.(jpe?g|png)$/.test(name)) {
                        applyCoverFile(file);
                        return;
                    }
                    if (name.endsWith('.wav')) {
                        var card = findEmptyWavCard();
                        if (!card) {
                            addTrack();
                            card = findEmptyWavCard();
                        }
                        assignWavToCard(card, file);
                    }
                });
                mediaBulkInput.value = '';
                updateReady();
            });
        }
    }

    function renumberTracks() {
        if (!tracksList) return;
        var cards = qsa('[data-track-card]', tracksList);
        cards.forEach(function (card, i) {
            var num = qs('[data-track-num]', card);
            if (num) num.textContent = String(i + 1);
            var heading = qs('[data-track-heading]', card);
            var titleEl = qs('[data-field="title"]', card);
            if (heading) heading.textContent = (titleEl && titleEl.value.trim()) || 'Без названия';
            var remove = qs('[data-remove-track]', card);
            if (remove) remove.hidden = cards.length <= 1;
        });
        updateReady();
    }

    function activateTrackTab(card, tab) {
        qsa('[data-track-tab]', card).forEach(function (btn) {
            btn.classList.toggle('is-active', btn.getAttribute('data-track-tab') === tab);
        });
        qsa('[data-track-pane]', card).forEach(function (pane) {
            pane.hidden = pane.getAttribute('data-track-pane') !== tab;
            pane.classList.toggle('is-active', pane.getAttribute('data-track-pane') === tab);
        });
    }

    function bindTrackTabs(card) {
        qsa('[data-track-tab]', card).forEach(function (btn) {
            btn.addEventListener('click', function () {
                activateTrackTab(card, btn.getAttribute('data-track-tab'));
            });
        });
    }

    function bindWav(card) {
        var input = qs('[data-wav-input]', card);
        var zone = qs('[data-wav-zone]', card);
        var label = qs('[data-wav-label]', card);
        var props = qs('[data-wav-props]', card);
        if (!input || !zone) return;

        function apply(file) {
            if (!file) return;
            if (!(file.name || '').toLowerCase().endsWith('.wav')) {
                alert('Нужен файл WAV');
                return;
            }
            assignWavToCard(card, file);
        }

        zone.addEventListener('click', function () {
            input.click();
        });
        zone.addEventListener('dragover', function (e) {
            e.preventDefault();
            zone.classList.add('is-drag');
        });
        zone.addEventListener('dragleave', function () {
            zone.classList.remove('is-drag');
        });
        zone.addEventListener('drop', function (e) {
            e.preventDefault();
            zone.classList.remove('is-drag');
            apply(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]);
        });
        input.addEventListener('change', function () {
            apply(input.files && input.files[0]);
            if (!(input.files && input.files[0])) {
                if (label) label.textContent = 'Файл не загружен — нажмите или перетащите';
                zone.classList.remove('has-file');
                if (props) props.textContent = 'ФОРМАТ · РАЗМЕР · ИМЯ ФАЙЛА';
                updateReady();
            }
        });
    }

    function bindLyrics(card) {
        var fileInput = qs('[data-lyrics-file]', card);
        var btn = qs('[data-lyrics-upload]', card);
        var nameEl = qs('[data-lyrics-name]', card);
        var textarea = qs('[data-field="lyrics"]', card);
        if (!fileInput || !btn || !textarea) return;
        btn.addEventListener('click', function () {
            fileInput.click();
        });
        fileInput.addEventListener('change', function () {
            var file = fileInput.files && fileInput.files[0];
            if (!file) return;
            var reader = new FileReader();
            reader.onload = function (ev) {
                textarea.value = ev.target.result || '';
                if (nameEl) nameEl.textContent = file.name;
            };
            reader.readAsText(file, 'UTF-8');
        });
    }

    function appendUnique(fieldEl, name) {
        if (!fieldEl || !name) return;
        var cur = fieldEl.value
            .split(',')
            .map(function (s) {
                return s.trim();
            })
            .filter(Boolean);
        if (cur.indexOf(name) === -1) cur.push(name);
        fieldEl.value = cur.join(', ');
    }

    function renderTrackContribChips(card) {
        var box = qs('[data-track-contrib-chips]', card);
        var list = card._contribs || [];
        renderChips(box, list, function (idx) {
            card._contribs.splice(idx, 1);
            renderTrackContribChips(card);
        });
    }

    function openContribModal(card) {
        contribTargetCard = card;
        if (contribName) contribName.value = '';
        qsa('#contribModal input[type="checkbox"]').forEach(function (cb) {
            cb.checked = false;
        });
        if (contribModal) contribModal.hidden = false;
        if (contribName) contribName.focus();
    }

    function closeContribModal() {
        contribTargetCard = null;
        if (contribModal) contribModal.hidden = true;
    }

    function saveContribModal() {
        if (!contribTargetCard) return;
        var name = (contribName && contribName.value.trim()) || '';
        if (!name) {
            alert('Укажите имя контрибьютора');
            return;
        }
        var roles = qsa('#contribModal input[type="checkbox"]:checked').map(function (cb) {
            return cb.value;
        });
        if (!roles.length) {
            alert('Выберите хотя бы одну роль');
            return;
        }

        contribTargetCard._contribs = contribTargetCard._contribs || [];
        contribTargetCard._contribs.push({ name: name, roles: roles });
        renderTrackContribChips(contribTargetCard);

        var artistsEl = qs('[data-field="artists"]', contribTargetCard);
        var composersEl = qs('[data-field="composers"]', contribTargetCard);
        var authorsEl = qs('[data-field="authors"]', contribTargetCard);
        if (roles.indexOf('featuring') >= 0) appendUnique(artistsEl, name);
        if (roles.indexOf('composer') >= 0 || roles.indexOf('arranger') >= 0) {
            appendUnique(composersEl, name);
        }
        if (roles.indexOf('lyricist') >= 0) appendUnique(authorsEl, name);

        closeContribModal();
        updateReady();
    }

    function initContribModal() {
        qsa('[data-contrib-close]').forEach(function (el) {
            el.addEventListener('click', closeContribModal);
        });
        if (contribSaveBtn) contribSaveBtn.addEventListener('click', saveContribModal);
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && contribModal && !contribModal.hidden) closeContribModal();
        });
    }

    function wireNames(card, index) {
        var prefix = 'tracks-' + index;
        var wav = qs('[data-wav-input]', card);
        if (wav) {
            wav.name = prefix + '-wav';
            wav.id = prefix + '-wav';
        }
        qsa('[data-field]', card).forEach(function (el) {
            var field = el.getAttribute('data-field');
            el.name = prefix + '-' + field;
            el.id = prefix + '-' + field;
        });
        [
            ['data-label-title', 'title'],
            ['data-label-artists', 'artists'],
            ['data-label-lyrics', 'lyrics'],
        ].forEach(function (pair) {
            var label = qs('[' + pair[0] + ']', card);
            if (label) label.setAttribute('for', prefix + '-' + pair[1]);
        });
    }

    function addTrack() {
        if (!template || !tracksList) return null;
        var node = template.content.cloneNode(true);
        var card = qs('[data-track-card]', node);
        var index = nextIndex++;
        card._contribs = [];
        wireNames(card, index);
        bindTrackTabs(card);
        bindWav(card);
        bindLyrics(card);
        activateTrackTab(card, 'info');

        var artistsEl = qs('[data-field="artists"]', card);
        if (artistsEl) {
            artistsEl.value =
                (artistsHidden && artistsHidden.value.trim()) ||
                (displayArtist && displayArtist.value.trim()) ||
                defaultArtists();
        }

        var titleEl = qs('[data-field="title"]', card);
        if (titleEl) titleEl.addEventListener('input', renumberTracks);
        qsa('[data-field="title"], [data-field="artists"]', card).forEach(function (el) {
            el.addEventListener('input', updateReady);
        });

        var instrumental = qs('[data-instrumental]', card);
        if (instrumental) {
            instrumental.addEventListener('change', function () {
                var authors = qs('[data-field="authors"]', card);
                if (instrumental.checked && authors) authors.value = '';
            });
        }

        var openContrib = qs('[data-open-contrib]', card);
        if (openContrib) {
            openContrib.addEventListener('click', function () {
                openContribModal(card);
            });
        }

        qs('[data-remove-track]', card).addEventListener('click', function () {
            if (qsa('[data-track-card]', tracksList).length <= 1) return;
            card.remove();
            renumberTracks();
        });

        tracksList.appendChild(card);
        renumberTracks();
        return card;
    }

    function initArtistsUi() {
        var seed = (displayArtist && displayArtist.value.trim()) || defaultArtists();
        if (seed) {
            mainArtists = seed
                .split(',')
                .map(function (s) {
                    return s.trim();
                })
                .filter(Boolean);
        }
        refreshArtistChips();

        var addMain = document.getElementById('addMainArtistBtn');
        if (addMain) {
            addMain.addEventListener('click', function () {
                var name = window.prompt('Имя основного артиста');
                if (!name) return;
                name = name.trim();
                if (!name) return;
                mainArtists.push(name);
                if (displayArtist && !displayArtist.value.trim()) displayArtist.value = name;
                refreshArtistChips();
                updateReady();
            });
        }
        if (displayArtist) {
            displayArtist.addEventListener('input', function () {
                syncArtistsHidden();
                updateReady();
            });
        }
    }

    function initWatchers() {
        [titleInput, genreInput, dateInput].forEach(function (el) {
            if (!el) return;
            el.addEventListener('input', updateReady);
            el.addEventListener('change', updateReady);
        });
        if (confirmBox) confirmBox.addEventListener('change', updateReady);
    }

    function initFormGuards() {
        if (!form) return;
        form.setAttribute('novalidate', 'novalidate');
        var formAction = document.getElementById('formAction');

        qsa('button[type="submit"][data-form-action]', form).forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (formAction) formAction.value = btn.getAttribute('data-form-action') || 'draft';
            });
        });

        form.addEventListener('submit', function (e) {
            syncArtistsHidden();
            var submitter = e.submitter;
            var action =
                (submitter && submitter.getAttribute('data-form-action')) ||
                (formAction && formAction.value) ||
                'draft';
            if (formAction) formAction.value = action;

            var titleOk = !!(titleInput && titleInput.value.trim());
            var artistsOk = !!(artistsHidden && artistsHidden.value.trim());
            var genreOk = !!(genreInput && genreInput.value);
            if (!titleOk || !artistsOk || !genreOk) {
                e.preventDefault();
                form.dataset.submitting = '';
                activateSection('data');
                alert('Заполните название, артиста и жанр в «Данные релиза»');
                return;
            }

            if (action === 'draft') {
                return;
            }

            if (!dateInput || !dateInput.value) {
                e.preventDefault();
                form.dataset.submitting = '';
                activateSection('dates');
                alert('Укажите дату релиза в «Даты и цены»');
                return;
            }
            if (!confirmBox || !confirmBox.checked) {
                e.preventDefault();
                form.dataset.submitting = '';
                activateSection('apply');
                alert('Подтвердите отсутствие пропаганды наркотических средств');
                return;
            }
            if (!coverInput || !coverInput.files || !coverInput.files.length) {
                e.preventDefault();
                form.dataset.submitting = '';
                activateSection('media');
                alert('Загрузите обложку');
                return;
            }
            if (!countCompleteTracks()) {
                e.preventDefault();
                form.dataset.submitting = '';
                activateSection('tracks');
                alert('Добавьте хотя бы один трек с WAV, названием и артистами');
                return;
            }
            if (!countSelectedPlatforms()) {
                e.preventDefault();
                form.dataset.submitting = '';
                activateSection('distribution');
                alert('Выберите хотя бы одну площадку в разделе «Дистрибуция»');
            }
        });
    }

    function setChecked(selector, on) {
        qsa(selector).forEach(function (el) {
            el.checked = !!on;
        });
        updateReady();
    }

    function initPhase3Controls() {
        var ww = document.getElementById('territoryWorldwide');
        var tAll = document.getElementById('territoriesSelectAll');
        var tClear = document.getElementById('territoriesClearAll');
        var pAll = document.getElementById('platformsSelectAll');
        var pClear = document.getElementById('platformsClearAll');

        if (ww) {
            ww.addEventListener('change', function () {
                if (ww.checked) setChecked('.js-territory', true);
                updateReady();
            });
        }
        if (tAll) {
            tAll.addEventListener('click', function () {
                if (ww) ww.checked = false;
                setChecked('.js-territory', true);
            });
        }
        if (tClear) {
            tClear.addEventListener('click', function () {
                if (ww) ww.checked = false;
                setChecked('.js-territory', false);
            });
        }
        qsa('.js-territory').forEach(function (el) {
            el.addEventListener('change', function () {
                if (ww && !el.checked) ww.checked = false;
                updateReady();
            });
        });
        if (pAll) pAll.addEventListener('click', function () {
            setChecked('.js-platform', true);
        });
        if (pClear) pClear.addEventListener('click', function () {
            setChecked('.js-platform', false);
        });
        qsa('.js-platform').forEach(function (el) {
            el.addEventListener('change', updateReady);
        });
    }

    if (addBtn) {
        addBtn.addEventListener('click', function () {
            var card = addTrack();
            if (card) {
                activateSection('tracks');
                card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        });
    }

    initNav();
    initCover();
    initContribModal();
    initArtistsUi();
    initWatchers();
    initFormGuards();
    initPhase3Controls();
    addTrack();
    activateSection('data');
    updateReady();
})();