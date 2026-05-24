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

    /* ── Copy project path (works on both list & detail) ─────── */
    var copyPathBtns = document.querySelectorAll('[data-action="copy-project-path"]');
    copyPathBtns.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var text = btn.dataset.clipboardText;
            if (text && navigator.clipboard) {
                navigator.clipboard.writeText(text).then(function() {
                    showToast('Path copied');
                });
            }
        });
    });

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
            case 'last_active':
                return row.dataset.lastSeen || '';
            default:
                return 0;
        }
    }

    function updateSortIndicators() {
        var buttons = document.querySelectorAll('#projects-table th .sortable-header');
        buttons.forEach(function(btn) {
            var caret = btn.querySelector('.sort-caret');
            if (!caret) return;
            if (btn.dataset.sort === currentSort.key) {
                caret.textContent = currentSort.ascending ? '↑' : '↓';
            } else {
                caret.textContent = '↕';
            }
        });
    }

    function updateFilterChip(query) {
        var chip = document.querySelector('.active-filters .filter-chip');
        if (!chip) return;
        if (query) {
            chip.textContent = 'Search: ' + query;
        } else {
            chip.textContent = 'Search: none';
        }
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
        arpStorage.remove('projects_search');
        updateFilterChip('');
    };

    /* ── List page event binding ────────────────────────────── */
    var searchEl = document.getElementById('project-search');

    var savedSearch = arpStorage.get('projects_search');
    if (savedSearch && searchEl) { searchEl.value = savedSearch; }

    // Real-time search on input (preserved behavior)
    if (searchEl) {
        searchEl.addEventListener('input', function() {
            arpStorage.set('projects_search', searchEl.value);
            filterProjects();
        });
    }

    // Sortable header buttons (list page)
    var sortButtons = document.querySelectorAll('#projects-table th .sortable-header');
    sortButtons.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var key = btn.dataset.sort;
            if (currentSort.key === key) {
                currentSort.ascending = !currentSort.ascending;
            } else {
                currentSort.key = key;
                currentSort.ascending = false; // default: descending
            }
            sortProjects();
        });
    });

    // Apply button: re-apply current filters
    var applyBtn = document.querySelector('[data-action="apply-search"]');
    if (applyBtn) {
        applyBtn.addEventListener('click', function() {
            filterProjects();
        });
    }

    // Clear button: reset all filters
    var clearBtns = document.querySelectorAll('[data-action="clear-search"]');
    clearBtns.forEach(function(btn) {
        btn.addEventListener('click', function() {
            resetProjectFilters();
        });
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

    if (savedSearch) {
        filterProjects();
    }

    /* ===========================================================
     * PROJECT DETAIL PAGE behaviors (scoped to #project-sessions-table)
     * All handlers check that #project-sessions-table exists first.
     * =========================================================== */

    var detailTable = document.getElementById('project-sessions-table');

    if (detailTable) {
        /* ── Detail: search in table toolbar ──────────────────── */
        var detailSearch = document.querySelector('#project-sessions-table [data-action="search"]')
            || document.querySelector('.table-toolbar [data-action="search"]')
            || document.getElementById('project-session-search');

        if (detailSearch) {
            detailSearch.addEventListener('input', function() {
                var q = detailSearch.value.toLowerCase().trim();
                var rows = detailTable.querySelectorAll('tbody tr');
                var visibleCount = 0;
                rows.forEach(function(row) {
                    var title = (row.dataset.title || row.textContent || '').toLowerCase();
                    var show = !q || title.indexOf(q) >= 0;
                    row.hidden = !show;
                    if (show) visibleCount++;
                });
                // Update count if element exists
                var countLabel = document.getElementById('project-sessions-count');
                if (countLabel) countLabel.textContent = visibleCount + ' sessions';
            });
        }

        /* ── Detail: copy session ID ─────────────────────────── */
        var copySessionBtns = detailTable.querySelectorAll('[data-action="copy-session"]');
        copySessionBtns.forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                var text = btn.dataset.clipboardText || btn.getAttribute('data-clipboard-text');
                if (text && navigator.clipboard) {
                    navigator.clipboard.writeText(text).then(function() {
                        showToast('Session ID copied');
                    });
                }
            });
        });

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
        var detailSortBtns = detailTable.querySelectorAll('th .sortable-header');
        var detailSortableThs = detailTable.querySelectorAll('th.sortable');
        var detailSortState = { key: null, ascending: false };

        // Button-based sortable headers (legacy pattern)
        detailSortBtns.forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                var key = btn.dataset.sort;
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
                var sortBtn = headers[i].querySelector('.sortable-header');
                if (sortBtn && sortBtn.dataset.sort === key) {
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
                var caret = btn.querySelector('.sort-caret');
                if (!caret) return;
                if (btn.dataset.sort === detailSortState.key) {
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

        /* ── Detail: pagination handlers ─────────────────────── */
        // Listen for page-change events from ui_primitives.js delegation
        document.addEventListener('page-change', function (event) {
            var detail = event.detail || {};
            if (detail.page) {
                navigateToPage(detail.page);
            }
        });

        // Listen for page-size-change events
        document.addEventListener('page-size-change', function (event) {
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
        // Update the URL with the page parameter
        var params = new URLSearchParams(window.location.search);
        params.set('page', pageNum.toString());
        window.location.search = params.toString();
    }

})();
