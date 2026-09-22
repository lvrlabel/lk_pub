/**
 * Аналитика: артист, даты, период, сортировка таблицы, график, площадки.
 */
(function () {
    'use strict';

    function qs(sel, root) {
        return (root || document).querySelector(sel);
    }

    function qsa(sel, root) {
        return Array.prototype.slice.call((root || document).querySelectorAll(sel));
    }

    function formatInt(n) {
        return Math.round(Number(n) || 0).toLocaleString('ru-RU');
    }

    function formatMoney(n) {
        return (Number(n) || 0).toLocaleString('ru-RU', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }) + ' ₽';
    }

    function periodKeyFromParts(year, month) {
        return (Number(year) || 0) * 100 + (Number(month) || 0);
    }

    function keyFromDateString(value) {
        if (!value) return 0;
        var parts = String(value).split('-');
        if (parts.length < 2) return 0;
        var y = Number(parts[0]) || 0;
        var m = Number(parts[1]) || 0;
        if (!y || !m) return 0;
        return y * 100 + m;
    }

    function minKeyForFilter(filter) {
        var now = new Date();
        var y = now.getFullYear();
        var m = now.getMonth() + 1;
        if (filter === 'all' || filter === 'custom') return 0;
        if (filter === 'year') return y * 100 + 1;
        var monthsBack = filter === '3m' ? 3 : filter === '6m' ? 6 : 12;
        m -= monthsBack;
        while (m <= 0) {
            m += 12;
            y -= 1;
        }
        return y * 100 + m;
    }

    function getToolbar() {
        return qs('#statsToolbar');
    }

    function getStatsBase() {
        var toolbar = getToolbar();
        var sel = qs('#releaseSelect');
        if (toolbar && toolbar.dataset.statsBase) return toolbar.dataset.statsBase;
        if (sel && sel.dataset.statsBase) return sel.dataset.statsBase;
        return '/stats';
    }

    function buildStatsUrl(overrides) {
        overrides = overrides || {};
        var base = getStatsBase();
        var params = new URLSearchParams();

        var artistSel = qs('#artistSelect');
        var releaseSel = qs('#releaseSelect');
        var dateFrom = qs('#dateFrom');
        var dateTo = qs('#dateTo');
        var periodSel = qs('#periodFilter');

        var artistId =
            overrides.artist_id !== undefined
                ? overrides.artist_id
                : artistSel
                  ? artistSel.value
                  : '';
        var releaseId =
            overrides.release_id !== undefined
                ? overrides.release_id
                : releaseSel
                  ? releaseSel.value
                  : '';
        var from =
            overrides.date_from !== undefined
                ? overrides.date_from
                : dateFrom
                  ? dateFrom.value
                  : '';
        var to =
            overrides.date_to !== undefined
                ? overrides.date_to
                : dateTo
                  ? dateTo.value
                  : '';
        var period =
            overrides.period !== undefined
                ? overrides.period
                : periodSel
                  ? periodSel.value
                  : 'all';

        if (artistId) params.set('artist_id', artistId);
        if (releaseId) params.set('release_id', releaseId);
        if (from) params.set('date_from', from);
        if (to) params.set('date_to', to);
        if (period && period !== 'all') params.set('period', period);

        var qsStr = params.toString();
        return qsStr ? base + (base.indexOf('?') >= 0 ? '&' : '?') + qsStr : base;
    }

    function initSelectSearch(inputId, selectId) {
        var input = qs('#' + inputId);
        var select = qs('#' + selectId);
        if (!input || !select) return;

        input.addEventListener('input', function () {
            var q = (input.value || '').toLowerCase().trim();
            var options = qsa('option', select);
            options.forEach(function (opt, idx) {
                if (idx === 0 && !opt.value) {
                    opt.hidden = false;
                    return;
                }
                var hay = (opt.getAttribute('data-search') || opt.textContent || '').toLowerCase();
                opt.hidden = !!q && hay.indexOf(q) < 0;
            });
        });
    }

    function initArtistSelect() {
        var sel = qs('#artistSelect');
        if (!sel) return;
        sel.addEventListener('change', function () {
            window.location.href = buildStatsUrl({
                artist_id: this.value || '',
                release_id: '',
            });
        });
    }

    function initReleaseSelect() {
        var sel = qs('#releaseSelect');
        if (!sel) return;
        sel.addEventListener('change', function () {
            window.location.href = buildStatsUrl({
                release_id: this.value || '',
            });
        });
    }

    function initUpcJump() {
        var statsBase = getStatsBase();
        if (!statsBase) return;

        function jump() {
            var input = qs('#statsUpcJump');
            var btn = qs('#statsUpcJumpBtn');
            if (!input) return;
            var upc = (input.value || '').trim();
            if (!upc) {
                input.focus();
                return;
            }
            if (btn) btn.disabled = true;
            fetch('/stats/search?upc=' + encodeURIComponent(upc), {
                credentials: 'same-origin',
                headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then(function (r) {
                    return r.json().then(function (data) {
                        if (!r.ok) throw new Error((data && data.error) || 'Релиз не найден');
                        return data;
                    });
                })
                .then(function (data) {
                    if (!data || !data.id) return;
                    window.location.href = buildStatsUrl({
                        release_id: String(data.id),
                        artist_id: '',
                    });
                })
                .catch(function (e) {
                    alert(e.message || 'Не удалось найти релиз');
                })
                .finally(function () {
                    if (btn) btn.disabled = false;
                });
        }

        var btn = qs('#statsUpcJumpBtn');
        var input = qs('#statsUpcJump');
        if (btn) btn.addEventListener('click', jump);
        if (input) {
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    jump();
                }
            });
        }
    }

    function initPlatformTabs() {
        var tabs = qs('#statsPlatformTabs');
        var list = qs('#statsPlatformBars');
        if (!tabs || !list) return;
        tabs.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-platform]');
            if (!btn) return;
            qsa('.stats-dash__tab', tabs).forEach(function (t) {
                t.classList.toggle('is-active', t === btn);
            });
            var name = btn.getAttribute('data-platform') || 'all';
            qsa('[data-platform-name]', list).forEach(function (row) {
                if (name === 'all') {
                    row.hidden = false;
                    return;
                }
                var rowName = (row.getAttribute('data-platform-name') || '').toLowerCase();
                row.hidden = rowName !== name.toLowerCase();
            });
        });
    }

    function initTable() {
        var table = qs('#analyticsTable');
        if (!table) return;
        var tbody = qs('tbody', table);
        var search = qs('#statsTableSearch');
        var sortState = { key: 'period', dir: 'desc' };

        function visibleRows() {
            return qsa('tr', tbody).filter(function (row) {
                return row.style.display !== 'none' && !row.hidden;
            });
        }

        function applySearch() {
            var q = ((search && search.value) || '').toLowerCase().trim();
            qsa('tr', tbody).forEach(function (row) {
                if (row.dataset.periodFiltered === '1') {
                    row.style.display = 'none';
                    return;
                }
                if (!q) {
                    row.style.display = '';
                    return;
                }
                row.style.display = row.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
            });
        }

        function sortBy(key) {
            if (sortState.key === key) {
                sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
            } else {
                sortState.key = key;
                sortState.dir = 'desc';
            }
            var rows = qsa('tr', tbody);
            rows.sort(function (a, b) {
                var av;
                var bv;
                if (key === 'period') {
                    av = Number(a.getAttribute('data-period-key') || 0);
                    bv = Number(b.getAttribute('data-period-key') || 0);
                } else if (key === 'revenue') {
                    av = Number(a.getAttribute('data-revenue') || 0);
                    bv = Number(b.getAttribute('data-revenue') || 0);
                } else {
                    av = Number(a.getAttribute('data-' + key) || 0);
                    bv = Number(b.getAttribute('data-' + key) || 0);
                }
                return sortState.dir === 'asc' ? av - bv : bv - av;
            });
            rows.forEach(function (row) {
                tbody.appendChild(row);
            });
        }

        qsa('th[data-sort]', table).forEach(function (th) {
            th.addEventListener('click', function () {
                sortBy(th.getAttribute('data-sort'));
            });
        });

        if (search) search.addEventListener('input', applySearch);

        window.StatsDashTable = {
            applySearch: applySearch,
            markPeriodFilter: function (minKey, maxKey) {
                minKey = Number(minKey) || 0;
                maxKey = Number(maxKey) || 0;
                qsa('tr', tbody).forEach(function (row) {
                    var key = Number(row.getAttribute('data-period-key') || 0);
                    var hide = false;
                    if (minKey > 0 && key < minKey) hide = true;
                    if (maxKey > 0 && key > maxKey) hide = true;
                    row.dataset.periodFiltered = hide ? '1' : '0';
                });
                applySearch();
            },
            visibleRows: visibleRows,
        };
    }

    function updateMetricsFromRows() {
        var rows = window.StatsDashTable ? window.StatsDashTable.visibleRows() : [];
        var streams = 0;
        var downloads = 0;
        var revenue = 0;
        rows.forEach(function (row) {
            streams += Number(row.getAttribute('data-streams') || 0);
            downloads += Number(row.getAttribute('data-downloads') || 0);
            revenue += Number(row.getAttribute('data-revenue') || 0);
        });
        var elStreams = qs('[data-metric="streams"]');
        var elDownloads = qs('[data-metric="downloads"]');
        var elRevenue = qs('[data-metric="revenue"]');
        var elPeriods = qs('[data-metric="periods"]');
        if (elStreams) elStreams.textContent = formatInt(streams);
        if (elDownloads) elDownloads.textContent = formatInt(downloads);
        if (elRevenue) elRevenue.textContent = formatMoney(revenue);
        if (elPeriods) elPeriods.textContent = formatInt(rows.length);
    }

    function resolveFilterKeys() {
        var periodSel = qs('#periodFilter');
        var dateFrom = qs('#dateFrom');
        var dateTo = qs('#dateTo');
        var period = periodSel ? periodSel.value : 'all';
        var fromVal = dateFrom ? dateFrom.value : '';
        var toVal = dateTo ? dateTo.value : '';

        if (period === 'custom' || fromVal || toVal) {
            return {
                minKey: keyFromDateString(fromVal),
                maxKey: keyFromDateString(toVal),
                period: 'custom',
            };
        }
        return {
            minKey: minKeyForFilter(period),
            maxKey: 0,
            period: period || 'all',
        };
    }

    function applyClientFilters(chartApi) {
        var keys = resolveFilterKeys();
        if (window.StatsDashTable) {
            window.StatsDashTable.markPeriodFilter(keys.minKey, keys.maxKey);
        }
        updateMetricsFromRows();
        if (chartApi && chartApi.filterByRange) {
            chartApi.filterByRange(keys.minKey, keys.maxKey);
        }
    }

    function initPeriodAndDates(chartApi) {
        var periodSel = qs('#periodFilter');
        var dateFrom = qs('#dateFrom');
        var dateTo = qs('#dateTo');
        var applyBtn = qs('#statsApplyFilters');

        function syncPeriodToCustom() {
            if (periodSel && periodSel.value !== 'custom') {
                periodSel.value = 'custom';
            }
        }

        if (periodSel) {
            periodSel.addEventListener('change', function () {
                if (this.value !== 'custom') {
                    if (dateFrom) dateFrom.value = '';
                    if (dateTo) dateTo.value = '';
                    applyClientFilters(chartApi);
                    if (history.replaceState) {
                        history.replaceState(null, '', buildStatsUrl({ period: this.value, date_from: '', date_to: '' }));
                    }
                }
            });
        }

        if (dateFrom) {
            dateFrom.addEventListener('change', syncPeriodToCustom);
        }
        if (dateTo) {
            dateTo.addEventListener('change', syncPeriodToCustom);
        }

        if (applyBtn) {
            applyBtn.addEventListener('click', function () {
                var keys = resolveFilterKeys();
                if (keys.period === 'custom' && periodSel) periodSel.value = 'custom';
                // Если есть релиз — фильтруем на клиенте; иначе просто обновляем URL
                var releaseSel = qs('#releaseSelect');
                if (releaseSel && releaseSel.value && qs('#analyticsTable')) {
                    applyClientFilters(chartApi);
                    if (history.replaceState) {
                        history.replaceState(
                            null,
                            '',
                            buildStatsUrl({
                                period: keys.period,
                                date_from: dateFrom ? dateFrom.value : '',
                                date_to: dateTo ? dateTo.value : '',
                            })
                        );
                    }
                } else {
                    window.location.href = buildStatsUrl({
                        period: keys.period,
                        date_from: dateFrom ? dateFrom.value : '',
                        date_to: dateTo ? dateTo.value : '',
                    });
                }
            });
        }

        // стартовое состояние из URL / STATS_DASH_DATA
        var data = window.STATS_DASH_DATA || {};
        if (periodSel && data.period) {
            periodSel.value = data.period;
        }
        if (dateFrom && data.dateFrom) dateFrom.value = data.dateFrom;
        if (dateTo && data.dateTo) dateTo.value = data.dateTo;
        if ((dateFrom && dateFrom.value) || (dateTo && dateTo.value)) {
            if (periodSel) periodSel.value = 'custom';
        }

        applyClientFilters(chartApi);
    }

    function initChart() {
        var data = window.STATS_DASH_DATA;
        var canvas = qs('#timelineChart');
        if (!data || !canvas || typeof Chart === 'undefined') return null;

        var currentMetric = 'all';
        var currentType = 'line';
        var chart = null;
        var activeMinKey = 0;
        var activeMaxKey = 0;

        var defs = {
            streams: {
                label: 'Стримы',
                borderColor: '#14b8a6',
                backgroundColor: 'rgba(20, 184, 166, 0.55)',
                fillColor: 'rgba(20, 184, 166, 0.14)',
                yAxisID: 'y',
            },
            downloads: {
                label: 'Скачивания',
                borderColor: '#64748b',
                backgroundColor: 'rgba(100, 116, 139, 0.55)',
                fillColor: 'rgba(100, 116, 139, 0.12)',
                yAxisID: 'y',
            },
            revenue: {
                label: 'Доход (₽)',
                borderColor: '#059669',
                backgroundColor: 'rgba(5, 150, 105, 0.55)',
                fillColor: 'rgba(5, 150, 105, 0.12)',
                yAxisID: 'y1',
            },
        };

        function filteredIndexes() {
            var out = [];
            (data.keys || []).forEach(function (key, i) {
                var k = Number(key) || 0;
                if (activeMinKey && k < activeMinKey) return;
                if (activeMaxKey && k > activeMaxKey) return;
                out.push(i);
            });
            return out;
        }

        function sliceByIndexes(arr, indexes) {
            return indexes.map(function (i) {
                return arr[i];
            });
        }

        function buildDatasets(metric, chartType, indexes) {
            var keys = metric === 'all' ? ['streams', 'downloads', 'revenue'] : [metric];
            var isBar = chartType === 'bar';
            var isArea = chartType === 'area';
            return keys.map(function (key) {
                var def = defs[key];
                return {
                    label: def.label,
                    data: sliceByIndexes(data[key], indexes),
                    borderColor: def.borderColor,
                    backgroundColor: isBar ? def.backgroundColor : def.fillColor,
                    tension: isBar ? 0 : 0.3,
                    fill: isArea || (!isBar && metric === 'all'),
                    yAxisID: def.yAxisID,
                };
            });
        }

        function render() {
            var indexes = filteredIndexes();
            var labels = sliceByIndexes(data.labels, indexes);
            var chartJsType = currentType === 'bar' ? 'bar' : 'line';
            var showRevenueAxis = currentMetric === 'all' || currentMetric === 'revenue';
            var showMainAxis = currentMetric !== 'revenue';

            if (chart) {
                chart.destroy();
                chart = null;
            }

            chart = new Chart(canvas, {
                type: chartJsType,
                data: {
                    labels: labels,
                    datasets: buildDatasets(currentMetric, currentType, indexes),
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            display: currentMetric === 'all',
                            position: 'top',
                        },
                    },
                    scales: {
                        x: { grid: { display: false } },
                        y: {
                            display: showMainAxis,
                            position: 'left',
                            beginAtZero: true,
                        },
                        y1: {
                            display: showRevenueAxis,
                            position: currentMetric === 'revenue' ? 'left' : 'right',
                            beginAtZero: true,
                            grid: { drawOnChartArea: currentMetric === 'revenue' },
                        },
                    },
                },
            });
        }

        qsa('#statsMetricChips [data-metric]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                qsa('#statsMetricChips [data-metric]').forEach(function (b) {
                    b.classList.toggle('is-active', b === btn);
                });
                currentMetric = btn.getAttribute('data-metric');
                render();
            });
        });

        qsa('#statsChartTypeChips [data-type]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                qsa('#statsChartTypeChips [data-type]').forEach(function (b) {
                    b.classList.toggle('is-active', b === btn);
                });
                currentType = btn.getAttribute('data-type');
                render();
            });
        });

        render();

        return {
            filterByMinKey: function (minKey) {
                activeMinKey = minKey || 0;
                activeMaxKey = 0;
                render();
            },
            filterByRange: function (minKey, maxKey) {
                activeMinKey = minKey || 0;
                activeMaxKey = maxKey || 0;
                render();
            },
        };
    }

    function boot() {
        initSelectSearch('artistSearch', 'artistSelect');
        initSelectSearch('releaseSearch', 'releaseSelect');
        initArtistSelect();
        initReleaseSelect();
        initUpcJump();
        initPlatformTabs();
        initTable();
        var chartApi = initChart();
        initPeriodAndDates(chartApi);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
