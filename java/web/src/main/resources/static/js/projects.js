/**
 * projects.js — Projects page search, sort, filter, and project-detail behaviors.
 *
 * Loaded via script_extra in projects.html (list + detail pages).
 * Uses shared UI primitive classes and data-action attributes (T102).
 *
 * T103: Migrated from select-based sorting to sortable header buttons.
 * T113: Added project-detail behaviors scoped to #project-sessions-table.
 */
(function() {
    'use strict';

    /* ── Toast helper (shared across all behaviors) ──────────── */
    function showToast(msg) {
        var toast = document.querySelector('.toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'toast';
            document.body.appendChild(toast);
        }
        toast.textContent = msg;
        toast.classList.add('is-visible');
        clearTimeout(toast._timeout);
        toast._timeout = setTimeout(function() {
            toast.classList.remove('is-visible');
        }, 2000);
    }
    window.showToast = showToast;

    /* ── Copy project path — REMOVED (T044) ───────────────────
     * Copy behavior now handled exclusively by the unified
     * handler in ui_primitives.js via data-copy-text.
     * ─────────────────────────────────────────────────────────── */

    /* ===========================================================
     * LIST PAGE behaviors (scoped to #projects-table)
     * =========================================================== */

    /* ── Sort state ─────────────────────────────────────────── */
    var currentSort = { key: null, ascending: false };

    window.applyProjectFilters = function() { filterProjects(); };

    function filterProjects() {
        var q = document.getElementById('project-search').value.toLowerCase().trim();
        var rows = document.querySelectorAll('#projects-table tbody tr');
        var visibleCount = 0;

        rows.forEach(function(row) {
            var name = (row.dataset.name || '').toLowerCase();
            var path = (row.dataset.path || '').toLowerCase();
            var show = !q || name.indexOf(q) >= 0 || path.indexOf(q) >= 0;
            row.hidden = !show;
            if (show) visibleCount++;
        });

        var countEl = document.getElementById('projects-count');
        if (countEl) countEl.textContent = visibleCount;
        var label = document.getElementById('projects-count-label');
        if (label) label.textContent = visibleCount + ' projects';

        // Update filter footer match count
        var matchEl = document.getElementById('projects-match-count');
        if (matchEl) matchEl.textContent = visibleCount + ' matching projects';

        var empty = document.getElementById('projects-empty');
        if (empty) {
            if (visibleCount === 0 && rows.length > 0) {
                empty.classList.remove('is-hidden');
                empty.hidden = false;
            } else {
                empty.classList.add('is-hidden');
                empty.hidden = true;
            }
        }

        // Update page status
        updatePageStatus(visibleCount, rows.length);

        // Update active-filters chip
        updateFilterChip(q);
    }

    window.applyProjectSort = function() { sortProjects(); };

    function sortProjects() {
        var tbody = document.querySelector('#projects-table tbody');
        if (!tbody) return;

        var rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort(function(a, b) {
            var va = getSortValue(a, currentSort.key);
            var vb = getSortValue(b, currentSort.key);
            if (va === vb) return 0;
            var cmp = (va < vb) ? -1 : 1;
            return currentSort.ascending ? cmp : -cmp;
        });

        rows.forEach(function(r) { tbody.appendChild(r); });
        updateSortIndicators();
    }

    function getSortValue(row, key) {
        switch (key) {
            case 'sessions':
                return parseInt(row.dataset.totalSessions) || 0;
            case 'tokens':
                return parseInt(row.dataset.totalTokens) || 0;
            case 'tools':
                return parseInt(row.dataset.totalTools) || 0;
            case 'failed':
                return parseInt(row.dataset.totalFailed) || 0;
            case 'first_seen':
                return row.dataset.firstSeen || '';
            case 'last_active':
                return row.dataset.lastSeen || '';
            default:
                return 0;
        }
    }

    function updateSortIndicators() {
        var buttons = document.querySelectorAll('#projects-table th .c-data-table__sort');
        buttons.forEach(function(btn) {
            var caret = btn.querySelector('.c-data-table__sort-icon');
            if (!caret) return;
            if (btn.dataset.sortKey === currentSort.key) {
                caret.textContent = currentSort.ascending ? '↑' : '↓';
            } else {
                caret.textContent = '↕';
            }
        });
    }

    function updateFilterChip(query) {
        var container = document.getElementById('projects-active-filters');
        if (!container) return;

        // Clear existing chips using DOM methods
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }

        if (query) {
            var chip = document.createElement('span');
            chip.className = 'filter-chip';

            var label = document.createTextNode('Search: ');
            chip.appendChild(label);

            var queryText = document.createTextNode(escapeHtml(query));
            chip.appendChild(queryText);

            var closeLink = document.createElement('a');
            closeLink.href = '#';
            closeLink.setAttribute('data-action', 'remove-filter');
            closeLink.setAttribute('aria-label', 'Remove search filter');
            closeLink.textContent = '×';
            chip.appendChild(closeLink);

            container.appendChild(chip);
        }
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    function formatNumber(value) {
        return String(Math.round(Number(value || 0))).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    function formatCompact(value) {
        var n = Number(value || 0);
        if (n >= 1000000000) return (n / 1000000000).toFixed(1) + 'B';
        if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
        if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
        return formatNumber(n);
    }

    function formatDuration(seconds) {
        var n = Math.max(0, Math.round(Number(seconds || 0)));
        if (n >= 3600) return Math.floor(n / 3600) + 'h ' + Math.floor((n % 3600) / 60) + 'm';
        if (n >= 60) return Math.floor(n / 60) + 'm ' + (n % 60) + 's';
        return n + 's';
    }

    function formatDate(value) {
        if (!value) return '—';
        var date = new Date(value);
        if (isNaN(date.getTime())) return value;
        return date.toLocaleString([], { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    }

    function segmentPct(tokens, key) {
        var total = Number(tokens && tokens.total || 0);
        if (!total) return 0;
        return Math.round(Number(tokens[key] || 0) * 1000 / total) / 10;
    }

    function normalizeProjectParams(params) {
        var cleaned = new URLSearchParams();
        params.forEach(function(value, key) {
            var v = String(value == null ? '' : value).trim();
            if (!v) return;
            if (key === 'page' && v === '1') return;
            if (key === 'page_size' && v === '25') return;
            cleaned.set(key, v);
        });
        return cleaned;
    }

    function apiFetch(path, params) {
        var qs = normalizeProjectParams(params || new URLSearchParams());
        var url = path + (qs.toString() ? '?' + qs.toString() : '');
        return fetch(url, { headers: { 'Accept': 'application/json' } }).then(function(response) {
            if (!response.ok) throw new Error('HTTP ' + response.status);
            return response.json();
        });
    }

    function updatePageStatus(visible, total) {
        var statusEl = document.getElementById('page-status-text');
        if (statusEl) {
            statusEl.textContent = 'of 1 · ' + visible + ' of ' + total + ' projects';
        }
    }

    function getProjectListParams() {
        var params = new URLSearchParams(window.location.search);
        var searchEl = document.getElementById('project-search');
        if (searchEl && searchEl.value.trim()) params.set('q', searchEl.value.trim());
        else params.delete('q');
        if (currentSort.key) {
            params.set('sort', currentSort.key);
            params.set('dir', currentSort.ascending ? 'asc' : 'desc');
        }
        return params;
    }

    function fetchProjectsList(params, replaceState) {
        if (!document.getElementById('projects-table')) return;
        params = params || getProjectListParams();
        var qs = normalizeProjectParams(params);
        var url = '/projects' + (qs.toString() ? '?' + qs.toString() : '');
        Promise.all([
            apiFetch('/api/projects/summary', qs),
            apiFetch('/api/projects/rows', qs)
        ]).then(function(parts) {
            renderProjectSummary(parts[0]);
            renderProjectRows(parts[1]);
            if (replaceState) window.history.replaceState({ api: true }, '', url);
            else window.history.pushState({ api: true }, '', url);
        }).catch(function(err) {
            console.error('Projects API fallback:', err.message || err);
            window.location.href = url;
        });
    }

    function renderProjectSummary(summary) {
        if (!summary) return;
        var count = document.getElementById('projects-count');
        if (count) count.innerHTML = '<b>' + escapeHtml(summary.projectCount) + '</b> projects';
        var cards = document.querySelectorAll('.metric-grid .metric-card');
        setMetricCardValue(cards[0], summary.projectCount);
        setMetricCardValue(cards[1], summary.sessionCount);
        setMetricCardValue(cards[2], formatCompact(summary.tokens && summary.tokens.total));
        setMetricCardValue(cards[3], summary.failedTools);
        var match = document.getElementById('projects-match-count');
        if (match) match.textContent = summary.projectCount + ' matching projects';
        updateFilterChip((summary.filters && summary.filters.q) || '');
    }

    function setMetricCardValue(card, value) {
        if (!card) return;
        var el = card.querySelector('.metric-card__value');
        if (el) el.textContent = String(value);
    }

    function renderProjectRows(response) {
        var table = document.getElementById('projects-table');
        if (!table || !response) return;
        var tbody = table.querySelector('tbody');
        if (!tbody) return;
        var rows = response.rows || [];
        if (!rows.length) {
            tbody.replaceChildren(projectEmptyRow(response.state));
        } else {
            tbody.replaceChildren.apply(tbody, rows.map(projectRowElement));
        }
        renderProjectPagination(response.pagination);
        bindProjectRowClicks();
    }

    function projectEmptyRow(state) {
        var tr = document.createElement('tr');
        var td = document.createElement('td');
        td.colSpan = 8;
        td.innerHTML = '<div class="empty-state"><div class="empty-state__icon" aria-hidden="true">📁</div><h2 class="empty-state__title">'
            + escapeHtml(state && state.title ? state.title : 'No projects match current filters')
            + '</h2><p class="empty-state__text">'
            + escapeHtml(state && state.message ? state.message : 'Try adjusting the project search.')
            + '</p><button class="btn primary" data-action="clear-search">Clear Search</button></div>';
        tr.appendChild(td);
        return tr;
    }

    function projectRowElement(row) {
        var tr = document.createElement('tr');
        var tokens = row.tokens || {};
        var projectName = row.projectName || row.projectKey;
        tr.setAttribute('data-action', 'open-project');
        tr.dataset.name = projectName || '';
        tr.dataset.path = row.projectKey || '';
        tr.dataset.firstSeen = row.firstSeen || '';
        tr.dataset.lastSeen = row.lastSeen || '';
        tr.dataset.totalSessions = row.totalSessions || 0;
        tr.dataset.totalTokens = tokens.total || 0;
        tr.dataset.totalTools = row.toolCalls || 0;
        tr.dataset.totalFailed = row.failedTools || 0;
        tr.innerHTML = [
            '<td class="project-cell"><a href="', escapeHtml(row.detailUrl || '#'), '" class="project-name-link" data-project="', escapeHtml(projectName), '" data-action="open-project-link">',
            escapeHtml(projectName), '</a><div class="project-path-row"><span class="path-text truncate" data-tooltip="', escapeHtml(row.projectKey), '">',
            escapeHtml(row.projectKey || ''), '</span><button class="path-copy-btn" data-action="copy" data-copy-text="', escapeHtml(row.projectKey), '" title="Copy full path" aria-label="Copy project path">Copy</button></div></td>',
            '<td class="agents-cell"><span class="agents-cell__inner">', agentBadge('cc', 'claude', 'CC', row.claudeSessions), agentBadge('cx', 'codex', 'CX', row.codexSessions), agentBadge('qd', 'qoder', 'QD', row.qoderSessions), '</span></td>',
            '<td class="numeric mono"><strong>', formatNumber(row.totalSessions), '</strong></td>',
            projectTokenCell(tokens),
            '<td class="numeric mono">', formatNumber(row.toolCalls), Number(row.failedTools || 0) > 0 ? '<span class="badge err tools-failed" data-tooltip="' + escapeHtml(row.failedTools) + ' failed tool results">' + escapeHtml(row.failedTools) + ' failed</span>' : '', '</td>',
            '<td class="numeric mono">', formatNumber(row.failedTools), '</td>',
            '<td class="text-xs text-muted" title="', escapeHtml(row.firstSeen), '">', escapeHtml(formatDate(row.firstSeen)), '</td>',
            '<td class="text-xs text-muted">', escapeHtml(formatDate(row.lastSeen)), '</td>'
        ].join('');
        return tr;
    }

    function agentBadge(cls, dot, label, count) {
        if (!Number(count || 0)) return '';
        return '<span class="badge ' + cls + ' badge--has-dot" data-tooltip="' + escapeHtml(count) + ' sessions" role="status"><span class="badge-dot badge-dot--' + dot + '" aria-hidden="true"></span>' + label + '</span>';
    }

    function projectTokenCell(tokens) {
        var freshPct = segmentPct(tokens, 'fresh');
        var readPct = segmentPct(tokens, 'cacheRead');
        var writePct = segmentPct(tokens, 'cacheWrite');
        var outPct = segmentPct(tokens, 'output');
        return '<td class="token-cell"><div class="token-total"><span class="token-total__value">' + formatCompact(tokens && tokens.total)
            + '</span><span class="tokenbar" aria-hidden="true"><span class="tokenbar-seg fresh" style="--segment-width:' + freshPct
            + '%"></span><span class="tokenbar-seg read" style="--segment-width:' + readPct
            + '%"></span><span class="tokenbar-seg write" style="--segment-width:' + writePct
            + '%"></span><span class="tokenbar-seg out" style="--segment-width:' + outPct + '%"></span></span></div></td>';
    }

    function renderProjectPagination(pagination) {
        var nav = document.querySelector('#projects-table').closest('.table-card').querySelector('.pagination');
        if (!nav || !pagination) return;
        var disabled = (pagination.totalPages || 0) <= 1;
        nav.innerHTML = '<button class="btn sm" data-action="prev-page" aria-label="Previous page"'
            + (!pagination.hasPrevious || disabled ? ' disabled' : '') + '>&lsaquo; prev</button><span class="page-status">Page</span>'
            + '<input class="page-input mono" data-action="page-input" value="' + escapeHtml(pagination.page) + '" aria-label="Page number"'
            + (disabled ? ' disabled' : '') + ' data-total-pages="' + escapeHtml(pagination.totalPages || 1) + '"/>'
            + '<span class="page-status" id="page-status-text">of ' + escapeHtml(pagination.totalPages || 0)
            + (pagination.totalItems > 0 ? ' of ' + escapeHtml(pagination.totalItems) : '') + '</span><span class="spacer"></span>'
            + '<label class="page-size-label" aria-label="每页条数"><span class="page-status">每页</span><select class="page-size-select" data-action="page-size">'
            + pageSizeOption(25, pagination.pageSize) + pageSizeOption(50, pagination.pageSize) + pageSizeOption(100, pagination.pageSize)
            + '</select></label><button class="btn sm" data-action="next-page" aria-label="Next page"'
            + (!pagination.hasNext || disabled ? ' disabled' : '') + '>next &rsaquo;</button>';
    }

    function pageSizeOption(value, selected) {
        return '<option value="' + value + '"' + (Number(selected) === value ? ' selected' : '') + '>' + value + '</option>';
    }

    function bindProjectRowClicks() {
        var listRows = document.querySelectorAll('#projects-table tbody tr[data-action="open-project"]');
        listRows.forEach(function(row) {
            if (row.dataset.bound === 'true') return;
            row.dataset.bound = 'true';
            row.addEventListener('click', function(e) {
                if (e.target.closest('a') || e.target.closest('button')) return;
                var link = row.querySelector('[data-action="open-project-link"]');
                if (link) window.location.href = link.href;
            });
        });
    }

    window.resetProjectFilters = function() {
        var searchEl = document.getElementById('project-search');
        if (searchEl) searchEl.value = '';
        currentSort = { key: null, ascending: false };
        updateSortIndicators();
        filterProjects();
        if (typeof arpStorage !== 'undefined') {
            arpStorage.remove('projects_search');
        }
        updateFilterChip('');
        if (window.location.search) {
            fetchProjectsList(new URLSearchParams(), false);
        }
    };

    /* ── List page event binding ────────────────────────────── */
    function initListPage() {
        var searchEl = document.getElementById('project-search');
        var serverSearchTimer = null;

        function scheduleServerSearch() {
            if (!searchEl) return;
            clearTimeout(serverSearchTimer);
            serverSearchTimer = setTimeout(function() {
                var params = new URLSearchParams(window.location.search);
                var q = searchEl.value.trim();
                var currentQ = params.get('q') || '';
                if (q === currentQ) return;
                if (q) {
                    params.set('q', q);
                } else {
                    params.delete('q');
                }
                params.delete('page');
                fetchProjectsList(params);
            }, 250);
        }

        // Real-time search on input (preserved behavior)
        if (searchEl) {
            searchEl.addEventListener('input', function() {
                filterProjects();
                scheduleServerSearch();
            });
            searchEl.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    filterProjects();
                    scheduleServerSearch();
                }
            });
        }

        var filterForm = document.querySelector('.card.filter-card .filter-form, .filter-form');
        if (filterForm) {
            filterForm.addEventListener('submit', function(e) {
                e.preventDefault();
                filterProjects();
                scheduleServerSearch();
            });
        }

        // Sortable header buttons (list page)
        var sortButtons = document.querySelectorAll('#projects-table th .c-data-table__sort');
        sortButtons.forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                var key = btn.dataset.sortKey;
                if (currentSort.key === key) {
                    currentSort.ascending = !currentSort.ascending;
                } else {
                    currentSort.key = key;
                    currentSort.ascending = false; // default: descending
                }
                sortProjects();
                var params = getProjectListParams();
                params.set('sort', key);
                params.set('dir', currentSort.ascending ? 'asc' : 'desc');
                params.delete('page');
                fetchProjectsList(params);
            });
        });

        // Clear button: reset all filters
        var clearBtns = document.querySelectorAll('[data-action="clear-search"]');
        clearBtns.forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                resetProjectFilters();
            });
        });

        // Remove single filter chip (x button) — event delegation
        document.addEventListener('click', function(e) {
            if (e.target.closest('[data-action="remove-filter"]')) {
                e.preventDefault();
                resetProjectFilters();
            }
        });

        // Row click: navigate to project detail (list page)
        bindProjectRowClicks();

        if (searchEl && searchEl.value) {
            filterProjects();
        }
        fetchProjectsList(new URLSearchParams(window.location.search), true);
    }

    /* ===========================================================
     * PROJECT DETAIL PAGE behaviors (scoped to #project-sessions-table)
     * All handlers check that #project-sessions-table exists first.
     * =========================================================== */
    function initDetailPage() {
        var detailTable = document.getElementById('project-sessions-table');

        if (detailTable) {
            hydrateProjectDetailFromApis(detailTable);
            /* ── Detail: search in table toolbar ──────────────────── */
            var detailSection = detailTable.closest('.page-section') || detailTable.closest('.card');
            var detailSearch = detailSection
                ? detailSection.querySelector('.table-toolbar [data-action="search"]')
                : null;
            if (!detailSearch) {
                detailSearch = document.querySelector('.table-toolbar [data-action="search"]');
            }

            if (detailSearch) {
                detailSearch.addEventListener('input', function() {
                    var q = detailSearch.value.toLowerCase().trim();
                    var rows = detailTable.querySelectorAll('tbody tr');
                    var visibleCount = 0;
                    rows.forEach(function(row) {
                        var title = (row.dataset.title || '').toLowerCase();
                        var sessionId = (row.dataset.sessionId || '').toLowerCase();
                        var show = !q || title.indexOf(q) >= 0 || sessionId.indexOf(q) >= 0;
                        row.hidden = !show;
                        if (show) visibleCount++;
                    });
                    // Update count if element exists
                    var countLabel = document.getElementById('project-sessions-count');
                    if (countLabel) countLabel.textContent = visibleCount + ' sessions';
                    clearTimeout(detailSearch._apiTimer);
                    detailSearch._apiTimer = setTimeout(function() {
                        var params = projectDetailParams();
                        params.delete('page');
                        fetchProjectSessions(params);
                    }, 250);
                });
            }

            /* ── Detail: copy session ID — REMOVED (T044) ────────────
             * Copy behavior now handled exclusively by the unified
             * handler in ui_primitives.js.
             * ─────────────────────────────────────────────────────────── */

            /* ── Detail: row click navigation ────────────────────── */
            var detailRows = detailTable.querySelectorAll('tbody tr[data-action="open-session"]');
            detailRows.forEach(function(row) {
                row.addEventListener('click', function(e) {
                    if (e.target.closest('a') || e.target.closest('button')) return;
                    // T117: use data-href on tr when no link inside
                    var href = row.dataset.href;
                    if (href) {
                        window.location.href = href;
                        return;
                    }
                    var link = row.querySelector('a.link, a[data-action="open-session-link"]');
                    if (link && link.href) {
                        window.location.href = link.href;
                    }
                });
            });

            /* ── Detail: sortable headers ────────────────────────── */
            var detailSortBtns = detailTable.querySelectorAll('th .c-data-table__sort');
            var detailSortableThs = detailTable.querySelectorAll('th.sortable');
            var detailSortState = { key: null, ascending: false };

            // Button-based sortable headers
            detailSortBtns.forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    e.stopPropagation();
                    var key = btn.dataset.sortKey;
                    if (!key) return;
                    if (detailSortState.key === key) {
                        detailSortState.ascending = !detailSortState.ascending;
                    } else {
                        detailSortState.key = key;
                        detailSortState.ascending = false;
                    }
                    sortDetailTable();
                    updateDetailSortIndicators();
                });
            });

            // Direct th-based sortable headers (T117 pattern)
            detailSortableThs.forEach(function(th) {
                th.addEventListener('click', function(e) {
                    // Skip if click was on a button inside the th
                    if (e.target.closest('button')) return;
                    var key = th.dataset.sort;
                    if (!key) return;
                    if (detailSortState.key === key) {
                        detailSortState.ascending = !detailSortState.ascending;
                    } else {
                        detailSortState.key = key;
                        detailSortState.ascending = false;
                    }
                    sortDetailTable();
                    updateDetailSortIndicators();
                });
            });

            function sortDetailTable() {
                var tbody = detailTable.querySelector('tbody');
                if (!tbody) return;

                var rows = Array.from(tbody.querySelectorAll('tr'));
                var key = detailSortState.key;
                var asc = detailSortState.ascending;

                rows.sort(function(a, b) {
                    var va = getDetailSortValue(a, key);
                    var vb = getDetailSortValue(b, key);
                    if (va === vb) return 0;
                    var cmp = (va < vb) ? -1 : 1;
                    return asc ? cmp : -cmp;
                });

                rows.forEach(function(r) { tbody.appendChild(r); });
            }

            function getDetailSortValue(row, key) {
                var colIndex = -1;
                var headers = Array.from(detailTable.querySelectorAll('thead th'));
                for (var i = 0; i < headers.length; i++) {
                    var sortBtn = headers[i].querySelector('.c-data-table__sort');
                    if (sortBtn && sortBtn.dataset.sortKey === key) {
                        colIndex = i;
                        break;
                    }
                    // T117: also check data-sort directly on th
                    if (headers[i].dataset.sort === key) {
                        colIndex = i;
                        break;
                    }
                }
                if (colIndex < 0) return '';

                var cells = row.querySelectorAll('td');
                if (colIndex >= cells.length) return '';
                var text = cells[colIndex].textContent.trim();

                // Try numeric for numeric columns
                var num = parseFloat(text.replace(/,/g, ''));
                if (!isNaN(num)) return num;
                return text.toLowerCase();
            }

            function updateDetailSortIndicators() {
                // Update button-based carets
                detailSortBtns.forEach(function(btn) {
                    var caret = btn.querySelector('.c-data-table__sort-icon');
                    if (!caret) return;
                    if (btn.dataset.sortKey === detailSortState.key) {
                        caret.textContent = detailSortState.ascending ? '↑' : '↓';
                    } else {
                        caret.textContent = '↕';
                    }
                });

                // T117: update data-sorted attribute on th for CSS :after indicator
                var allSortableThs = detailTable.querySelectorAll('th.sortable');
                allSortableThs.forEach(function(th) {
                    if (th.dataset.sort === detailSortState.key) {
                        th.setAttribute('data-sorted', detailSortState.ascending ? 'asc' : 'desc');
                    } else {
                        th.removeAttribute('data-sorted');
                    }
                });
            }

        } // end if (detailTable)
    }

    function projectKeyFromLocation() {
        var match = window.location.pathname.match(/^\/projects\/(.+)$/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function projectDetailParams() {
        var params = new URLSearchParams(window.location.search);
        var search = document.querySelector('#project-sessions-table')
            ? document.querySelector('.table-toolbar [data-action="search"]')
            : null;
        if (search && search.value.trim()) params.set('q', search.value.trim());
        else params.delete('q');
        return params;
    }

    function hydrateProjectDetailFromApis(detailTable) {
        var projectKey = projectKeyFromLocation();
        if (!projectKey || !window.fetch) return;
        var encoded = encodeURIComponent(projectKey);
        var params = projectDetailParams();
        Promise.all([
            apiFetch('/api/projects/' + encoded + '/summary', params),
            apiFetch('/api/projects/' + encoded + '/token-trend', params),
            apiFetch('/api/projects/' + encoded + '/agent-mix', params),
            apiFetch('/api/projects/' + encoded + '/tool-hotspots', params),
            apiFetch('/api/projects/' + encoded + '/sessions/rows', params)
        ]).then(function(parts) {
            renderProjectDetailSummary(parts[0]);
            renderProjectTokenTrend(parts[1]);
            renderProjectAgentMix(parts[2]);
            renderToolHotspots(parts[3]);
            renderProjectSessions(parts[4], detailTable);
            window.history.replaceState({ api: true }, '', window.location.pathname + (normalizeProjectParams(params).toString() ? '?' + normalizeProjectParams(params).toString() : ''));
        }).catch(function(err) {
            console.error('Project Detail API hydration failed:', err.message || err);
        });
    }

    function fetchProjectSessions(params, replaceState) {
        var detailTable = document.getElementById('project-sessions-table');
        var projectKey = projectKeyFromLocation();
        if (!detailTable || !projectKey) return;
        var encoded = encodeURIComponent(projectKey);
        var qs = normalizeProjectParams(params || projectDetailParams());
        apiFetch('/api/projects/' + encoded + '/sessions/rows', qs).then(function(response) {
            renderProjectSessions(response, detailTable);
            var url = window.location.pathname + (qs.toString() ? '?' + qs.toString() : '');
            if (replaceState) window.history.replaceState({ api: true }, '', url);
            else window.history.pushState({ api: true }, '', url);
        }).catch(function(err) {
            console.error('Project sessions API fallback:', err.message || err);
            window.location.search = qs.toString();
        });
    }

    function renderProjectDetailSummary(summary) {
        if (!summary) return;
        var headStat = document.querySelector('.page-head-actions .ui-stat-pill');
        if (headStat) headStat.textContent = formatDate(summary.firstSeen) + ' – ' + formatDate(summary.lastSeen);
        var cards = document.querySelectorAll('.project-detail-kpis .metric-card');
        setMetricCardValue(cards[0], summary.totalSessions);
        setMetricCardValue(cards[1], [summary.claudeSessions, summary.qoderSessions, summary.codexSessions].filter(function(v) { return Number(v || 0) > 0; }).length);
        setMetricCardValue(cards[2], formatCompact(summary.tokens && summary.tokens.total));
        var input = (summary.tokens && (summary.tokens.fresh + summary.tokens.cacheRead + summary.tokens.cacheWrite)) || 0;
        setMetricCardValue(cards[3], input > 0 ? (summary.tokens.cacheRead * 100 / input).toFixed(1) + '%' : 'N/A');
        setMetricCardValue(cards[4], formatNumber(summary.failedTools));
    }

    function renderProjectTokenTrend(response) {
        var points = response && response.points ? response.points : [];
        var wrap = document.querySelector('.project-trend-points');
        if (!wrap) return;
        wrap.replaceChildren.apply(wrap, points.map(function(point) {
            var span = document.createElement('span');
            span.className = 'project-trend-point';
            span.setAttribute('data-tooltip', 'Range point: ' + point.label + ' · Total Tokens ' + formatCompact(point.tokens && point.tokens.total));
            span.textContent = point.label + ' · ' + formatCompact(point.tokens && point.tokens.total);
            return span;
        }));
    }

    function renderProjectAgentMix(response) {
        var bar = document.querySelector('.agent-mix-bar');
        if (!bar || !response || !Array.isArray(response.rows)) return;
        bar.replaceChildren.apply(bar, response.rows.filter(function(row) {
            return Number(row.sessions || 0) > 0;
        }).map(function(row) {
            var a = document.createElement('a');
            var scope = row.agent === 'claude_code' ? 'claude-code' : row.agent;
            a.className = 'agent-mix-bar__segment agent-mix-bar__segment--' + scope;
            a.href = '/dashboard?agent=' + encodeURIComponent(scope);
            a.style.setProperty('--segment-width', Math.max(2, row.sessionShare || 0) + '%');
            a.textContent = row.label + ' · ' + formatNumber(row.sessions);
            return a;
        }));
    }

    function renderToolHotspots(response) {
        if (!response || response.available) return;
        var hotspot = document.querySelector('[data-project-tool-hotspots], .tool-hotspots, .project-tool-hotspots');
        if (!hotspot) return;
        hotspot.textContent = 'Tool hotspots unavailable: ' + (response.reason || 'not indexed');
    }

    function renderProjectSessions(response, table) {
        if (!response || !table) return;
        var tbody = table.querySelector('tbody');
        if (!tbody) return;
        var rows = response.rows || [];
        if (!rows.length) {
            var empty = document.createElement('tr');
            var td = document.createElement('td');
            td.colSpan = 12;
            td.innerHTML = '<div class="empty-state"><div class="empty-state__icon" aria-hidden="true">📁</div><h2 class="empty-state__title">'
                + escapeHtml(response.state && response.state.title ? response.state.title : 'No sessions in this project yet')
                + '</h2><a class="btn primary" href="/sessions" data-action="view-all">View all sessions</a></div>';
            empty.appendChild(td);
            tbody.replaceChildren(empty);
        } else {
            tbody.replaceChildren.apply(tbody, rows.map(projectSessionRow));
        }
        renderDetailPagination(response.pagination, table);
    }

    function projectSessionRow(row) {
        var tr = document.createElement('tr');
        var tokens = row.tokens || {};
        var title = row.title || 'Untitled';
        tr.setAttribute('data-action', 'open-session');
        tr.dataset.href = row.detailUrl || '';
        tr.dataset.title = title;
        tr.dataset.sessionId = row.sessionId || '';
        tr.innerHTML = [
            '<td><div class="title-main"><a href="', escapeHtml(row.detailUrl || '#'), '" class="session-link">', escapeHtml(title), '</a></div>',
            '<div class="title-sub mono">', escapeHtml((row.sessionId || '').slice(-8)), '<button class="btn sm session-copy-btn" data-action="copy" data-copy-text="', escapeHtml(row.sessionId || ''), '" aria-label="Copy session ID" title="Copy session ID">Copy</button></div></td>',
            '<td><span class="badge ', row.agent === 'claude_code' ? 'cc' : (row.agent === 'codex' ? 'cx' : 'qd'), '">', row.agent === 'claude_code' ? 'CC' : (row.agent === 'codex' ? 'CX' : 'QD'), '</span></td>',
            '<td class="mono" title="', escapeHtml(row.model || ''), '">', escapeHtml(row.model || 'Unknown model'), '</td>',
            projectTokenCell(tokens),
            '<td class="num mono">', formatNumber(row.rounds), '</td><td class="num mono">', formatNumber(row.tools), '</td><td class="num mono">', formatNumber(row.subagents), '</td>',
            '<td class="num mono" data-tooltip="', escapeHtml(row.durationSeconds), 's">', formatDuration(row.durationSeconds), '</td>',
            '<td class="num mono" data-tooltip="', escapeHtml(row.processSeconds), 's">', formatDuration(row.processSeconds), '</td>',
            '<td class="', Number(row.failedTools || 0) === 0 ? 'muted' : '', '">', Number(row.failedTools || 0) > 0 ? '<span class="badge err">' + escapeHtml(row.failedTools) + ' failed</span>' : 'No failures', '</td>',
            '<td class="mono" title="', escapeHtml(row.createdAt || ''), '">', escapeHtml(formatDate(row.createdAt)), '</td><td class="muted">', escapeHtml(formatDate(row.updatedAt)), '</td>'
        ].join('');
        return tr;
    }

    function renderDetailPagination(pagination, table) {
        var nav = table.closest('.card').querySelector('.pagination');
        if (!nav || !pagination) return;
        var disabled = (pagination.totalPages || 0) <= 1;
        nav.innerHTML = '<button class="btn sm" data-action="prev-page" aria-label="Previous page"'
            + (!pagination.hasPrevious || disabled ? ' disabled' : '') + '>&lsaquo; prev</button><span class="page-status">Page</span>'
            + '<input class="page-input mono" data-action="page-input" value="' + escapeHtml(pagination.page) + '" aria-label="Page number"'
            + (disabled ? ' disabled' : '') + ' data-total-pages="' + escapeHtml(pagination.totalPages || 1) + '"/>'
            + '<span class="page-status">of ' + escapeHtml(pagination.totalPages || 0)
            + (pagination.totalItems > 0 ? ' of ' + escapeHtml(pagination.totalItems) : '') + '</span><span class="spacer"></span>'
            + '<label class="page-size-label" aria-label="每页条数"><span class="page-status">每页</span><select class="page-size-select" data-action="page-size">'
            + pageSizeOption(25, pagination.pageSize) + pageSizeOption(50, pagination.pageSize) + pageSizeOption(100, pagination.pageSize)
            + '</select></label><button class="btn sm" data-action="next-page" aria-label="Next page"'
            + (!pagination.hasNext || disabled ? ' disabled' : '') + '>next &rsaquo;</button>';
    }

    /* ── Server-side pagination (both list and detail pages) ── */
    // Scoped to projects pages only — do NOT activate on sessions-list
    // where sessions-list.js handles pagination via AJAX.
    function _isProjectsPage() {
        return !!(document.getElementById('projects-table')
            || document.getElementById('project-sessions-table'));
    }

    function initPagination() {
        document.addEventListener('page-change', function (event) {
            if (!_isProjectsPage()) return;
            var detail = event.detail || {};
            if (detail.page) {
                var params = document.getElementById('projects-table')
                    ? getProjectListParams()
                    : projectDetailParams();
                params.set('page', String(detail.page));
                if (document.getElementById('projects-table')) fetchProjectsList(params);
                else fetchProjectSessions(params);
            }
        });

        document.addEventListener('page-size-change', function (event) {
            if (!_isProjectsPage()) return;
            var detail = event.detail || {};
            if (detail.pageSize) {
                var params = document.getElementById('projects-table')
                    ? getProjectListParams()
                    : projectDetailParams();
                params.set('page_size', String(detail.pageSize));
                params.set('page', '1');
                if (document.getElementById('projects-table')) fetchProjectsList(params);
                else fetchProjectSessions(params);
            }
        });
    }

    function navigateToPage(pageNum) {
        var params = new URLSearchParams(window.location.search);
        params.set('page', pageNum.toString());
        window.location.search = params.toString();
    }

    /* ── DOM ready: initialize all behaviors ──────────────────── */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initListPage();
            initDetailPage();
            initPagination();
        });
    } else {
        // DOM already ready (e.g. script loaded defer or async)
        initListPage();
        initDetailPage();
        initPagination();
    }

})();
