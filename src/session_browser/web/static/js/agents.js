/**
 * agents.js — Agents page behaviors: row click navigation, sortable headers,
 * copy agent name, and pagination.
 *
 * Loaded via script_extra in agents.html.
 * Uses shared UI primitive classes and data-action attributes (T102).
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

    /* ===========================================================
     * AGENTS LIST TABLE behaviors (scoped to #agents-table)
     * =========================================================== */

    var agentsTable = document.getElementById('agents-table');

    if (agentsTable) {
        /* ── Sort state ─────────────────────────────────────── */
        var currentSort = { key: null, ascending: false };

        /* ── Sortable header clicks (on <th>) ───────────── */
        // Contract: th.sortable[data-action="sort"][data-sort-key]
        // Buttons inside <th> have data-sort for agents.js;
        // stopPropagation on buttons prevents double-handling with ui_primitives.js.
        var sortHeaders = agentsTable.querySelectorAll('th.sortable[data-sort-key]');
        sortHeaders.forEach(function(th) {
            th.addEventListener('click', function(e) {
                var key = th.dataset.sortKey || th.dataset.sort;
                if (!key) return;
                if (currentSort.key === key) {
                    currentSort.ascending = !currentSort.ascending;
                } else {
                    currentSort.key = key;
                    currentSort.ascending = false;
                }
                sortAgents();
            });
        });

        /* ── Sortable header buttons: stop bubbling to prevent
              ui_primitives.js from also handling the same click ── */
        var sortButtons = agentsTable.querySelectorAll('th.sortable .sortable-header');
        sortButtons.forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
            });
        });

        function sortAgents() {
            var tbody = agentsTable.querySelector('tbody');
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
                case 'name':
                    return row.dataset.agentName || '';
                case 'provider': {
                    var badge = row.querySelector('td:nth-child(2) .badge');
                    if (badge && badge.textContent.includes('Anthropic')) return 'Anthropic';
                    if (badge && badge.textContent.includes('OpenAI')) return 'OpenAI';
                    if (badge && badge.textContent.includes('Qoder')) return 'Qoder';
                    return '';
                }
                case 'sessions':
                    return parseInt(row.dataset.sessionCount) || 0;
                case 'projects':
                    return parseInt(row.dataset.projectCount) || 0;
                case 'tokens':
                    return parseInt(row.dataset.totalTokens) || 0;
                case 'tool_calls':
                    return parseInt(row.dataset.totalToolCalls) || 0;
                case 'failed':
                    return parseInt(row.dataset.totalFailed) || 0;
                case 'last_active':
                    return row.dataset.lastActive || '';
                default:
                    return 0;
            }
        }

        function updateSortIndicators() {
            var buttons = agentsTable.querySelectorAll('th .sortable-header');
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

        /* ── Row click: navigate to agent detail ────────────── */
        var listRows = agentsTable.querySelectorAll('tbody tr[data-action="open-agent"]');
        listRows.forEach(function(row) {
            row.addEventListener('click', function(e) {
                if (e.target.closest('a') || e.target.closest('button')) return;
                var href = row.dataset.href;
                if (href) {
                    window.location.href = href;
                }
            });
        });

        /* ── Copy agent name ────────────────────────────────── */
        var copyBtns = agentsTable.querySelectorAll('[data-action="copy-agent-name"]');
        copyBtns.forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                var text = btn.dataset.clipboardText;
                if (text && navigator.clipboard) {
                    navigator.clipboard.writeText(text).then(function() {
                        showToast('Agent name copied');
                    });
                }
            });
        });
    }

    /* ===========================================================
     * EFFICIENCY TABLE behaviors (scoped to #efficiency-table)
     * =========================================================== */

    var efficiencyTable = document.getElementById('efficiency-table');

    if (efficiencyTable) {
        /* ── Sort state ─────────────────────────────────────── */
        var effSortState = { key: null, ascending: false };

        /* ── Sortable header clicks (on <th>) ───────────── */
        var effSortHeaders = efficiencyTable.querySelectorAll('th.sortable[data-sort-key]');
        effSortHeaders.forEach(function(th) {
            th.addEventListener('click', function(e) {
                var key = th.dataset.sortKey || th.dataset.sort;
                if (!key) return;
                if (effSortState.key === key) {
                    effSortState.ascending = !effSortState.ascending;
                } else {
                    effSortState.key = key;
                    effSortState.ascending = false;
                }
                sortEfficiencyTable();
            });
        });

        /* ── Sortable header buttons: stop bubbling ──────── */
        var effSortButtons = efficiencyTable.querySelectorAll('th.sortable .sortable-header');
        effSortButtons.forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
            });
        });

        function sortEfficiencyTable() {
            var tbody = efficiencyTable.querySelector('tbody');
            if (!tbody) return;

            var rows = Array.from(tbody.querySelectorAll('tr'));
            var key = effSortState.key;
            var asc = effSortState.ascending;

            rows.sort(function(a, b) {
                var va = getEffSortValue(a, key);
                var vb = getEffSortValue(b, key);
                if (va === vb) return 0;
                var cmp = (va < vb) ? -1 : 1;
                return asc ? cmp : -cmp;
            });

            rows.forEach(function(r) { tbody.appendChild(r); });
            updateEffSortIndicators();
        }

        function getEffSortValue(row, key) {
            switch (key) {
                case 'sessions':
                    return parseInt(row.dataset.sessionCount) || 0;
                case 'avg_duration':
                    return parseFloat(row.dataset.avgDuration) || 0;
                case 'p95_duration':
                    return parseFloat(row.dataset.p95Duration) || 0;
                case 'avg_input_side':
                    return parseInt(row.dataset.avgInputSide) || 0;
                case 'avg_tools':
                    return parseInt(row.dataset.avgTools) || 0;
                case 'tools_per_round':
                    return parseFloat(row.dataset.toolsPerRound) || 0;
                case 'cache_reuse':
                    return parseFloat(row.dataset.cacheReuse) || 0;
                case 'failed_per_session':
                    return parseFloat(row.dataset.failedPerSession) || 0;
                default:
                    return (row.textContent || '').toLowerCase();
            }
        }

        function updateEffSortIndicators() {
            effSortButtons.forEach(function(btn) {
                var caret = btn.querySelector('.sort-caret');
                if (!caret) return;
                if (btn.dataset.sort === effSortState.key) {
                    caret.textContent = effSortState.ascending ? '↑' : '↓';
                } else {
                    caret.textContent = '↕';
                }
            });
        }
    }

    /* ===========================================================
     * Info-icon tooltip for metric cards
     * =========================================================== */

    // Contract: button.info-icon[data-action="info"] — click shows metric definition tooltip.
    // Native title attribute provides hover fallback.
    var infoIcons = document.querySelectorAll('[data-action="info"]');
    var activeInfoTooltip = null;

    infoIcons.forEach(function(icon) {
        icon.addEventListener('click', function(e) {
            e.stopPropagation();

            // Close any existing tooltip
            if (activeInfoTooltip) {
                activeInfoTooltip.remove();
                activeInfoTooltip = null;
                return;
            }

            var labelText = icon.parentElement.textContent.trim().replace(/\s+/g, ' ');
            var tipText = icon.getAttribute('title') || '';

            var tooltip = document.createElement('div');
            tooltip.className = 'info-tooltip';
            tooltip.setAttribute('role', 'tooltip');
            tooltip.innerHTML = '<strong>' + labelText + '</strong><br>' + tipText;
            tooltip.style.position = 'absolute';
            tooltip.style.zIndex = '9999';
            tooltip.style.background = 'var(--bg-surface, #1e1e2e)';
            tooltip.style.color = 'var(--text-primary, #cdd6f4)';
            tooltip.style.border = '1px solid var(--border-muted, #45475a)';
            tooltip.style.borderRadius = '6px';
            tooltip.style.padding = '8px 12px';
            tooltip.style.fontSize = '12px';
            tooltip.style.lineHeight = '1.4';
            tooltip.style.maxWidth = '280px';
            tooltip.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
            tooltip.style.pointerEvents = 'none';

            document.body.appendChild(tooltip);

            // Position near the icon
            var rect = icon.getBoundingClientRect();
            var top = rect.bottom + 6;
            var left = rect.left;
            // Keep tooltip in viewport
            if (left + 280 > window.innerWidth) {
                left = window.innerWidth - 290;
            }
            if (left < 8) left = 8;
            tooltip.style.top = top + 'px';
            tooltip.style.left = left + 'px';

            activeInfoTooltip = tooltip;

            // Auto-dismiss after 4 seconds
            setTimeout(function() {
                if (activeInfoTooltip === tooltip) {
                    tooltip.remove();
                    activeInfoTooltip = null;
                }
            }, 4000);
        });
    });

    // Click outside closes info tooltip
    document.addEventListener('click', function() {
        if (activeInfoTooltip) {
            activeInfoTooltip.remove();
            activeInfoTooltip = null;
        }
    });

    /* ===========================================================
     * Pagination handlers (shared across both tables)
     * =========================================================== */

    // Page input: enter key to jump to page
    var pageInputs = document.querySelectorAll('[data-action="page-input"]');
    pageInputs.forEach(function(input) {
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                var pageNum = parseInt(input.value, 10);
                if (pageNum > 0) {
                    navigateToPage(pageNum);
                }
            }
        });
    });

    // Next page button
    var nextPageBtns = document.querySelectorAll('[data-action="next-page"]');
    nextPageBtns.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            var href = btn.getAttribute('href');
            if (href) {
                window.location.href = href;
            }
        });
    });

    // Previous page button
    var prevPageBtns = document.querySelectorAll('[data-action="prev-page"]');
    prevPageBtns.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            var href = btn.getAttribute('href');
            if (href) {
                window.location.href = href;
            }
        });
    });

    function navigateToPage(pageNum) {
        var params = new URLSearchParams(window.location.search);
        params.set('page', pageNum.toString());
        window.location.search = params.toString();
    }

})();
