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

    function updatePageStatus(visible, total) {
        var statusEl = document.getElementById('page-status-text');
        if (statusEl) {
            statusEl.textContent = 'of 1 · ' + visible + ' of ' + total + ' projects';
        }
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
            window.location.href = '/projects';
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
                var query = params.toString();
                window.location.href = '/projects' + (query ? '?' + query : '');
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
        var listRows = document.querySelectorAll('#projects-table tbody tr[data-action="open-project"]');
        listRows.forEach(function(row) {
            row.addEventListener('click', function(e) {
                // Don't navigate if clicking a link or button inside the row
                if (e.target.closest('a') || e.target.closest('button')) return;
                var link = row.querySelector('[data-action="open-project-link"]');
                if (link) {
                    window.location.href = link.href;
                }
            });
        });

        if (searchEl && searchEl.value) {
            filterProjects();
        }
    }

    /* ===========================================================
     * PROJECT DETAIL PAGE behaviors (scoped to #project-sessions-table)
     * All handlers check that #project-sessions-table exists first.
     * =========================================================== */
    function initDetailPage() {
        var detailTable = document.getElementById('project-sessions-table');

        if (detailTable) {
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
                navigateToPage(detail.page);
            }
        });

        document.addEventListener('page-size-change', function (event) {
            if (!_isProjectsPage()) return;
            var detail = event.detail || {};
            if (detail.pageSize) {
                var params = new URLSearchParams(window.location.search);
                params.set('page_size', String(detail.pageSize));
                params.set('page', '1');
                window.location.search = params.toString();
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
