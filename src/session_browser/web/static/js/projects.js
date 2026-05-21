/**
 * projects.js — Projects page search, sort, and filter persistence.
 *
 * Loaded via script_extra in projects.html.
 * Uses shared UI primitive classes and data-action attributes (T102).
 *
 * T103: Migrated from select-based sorting to sortable header buttons.
 */
(function() {
    'use strict';

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
            row.style.display = show ? '' : 'none';
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
                empty.style.display = '';
            } else {
                empty.classList.add('is-hidden');
                empty.style.display = 'none';
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

    /* ── Event binding ──────────────────────────────────────── */
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

    // Sortable header buttons
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

    // Copy project path
    var copyBtns = document.querySelectorAll('[data-action="copy-project-path"]');
    copyBtns.forEach(function(btn) {
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

    // Row click: navigate to project detail
    var rows = document.querySelectorAll('#projects-table tbody tr[data-action="open-project"]');
    rows.forEach(function(row) {
        row.addEventListener('click', function(e) {
            // Don't navigate if clicking a link or button inside the row
            if (e.target.closest('a') || e.target.closest('button')) return;
            var link = row.querySelector('[data-action="open-project-link"]');
            if (link) {
                window.location.href = link.href;
            }
        });
    });

    function showToast(msg) {
        var toast = document.querySelector('.toast, .toast-container');
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

    if (savedSearch) {
        filterProjects();
    }
})();
