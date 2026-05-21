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

    /* ===========================================================
     * AGENT DETAIL page behaviors (T141)
     * =========================================================== */

    // Contract: [data-action="back"] — back link/button navigates to /agents.
    // Works with both <a> and <button> elements.
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-action="back"]');
        if (!btn) return;
        e.preventDefault();
        var href = btn.getAttribute('href');
        if (!href || href === '#') href = '/agents';
        window.location.href = href;
    });

    // Contract: tr[data-action="open-session"] or [data-action="open-session"] —
    // click navigates to /sessions/{agent}/{session_id}.
    // Skips if click target is already a link or button.
    document.addEventListener('click', function(e) {
        var row = e.target.closest('[data-action="open-session"]');
        if (!row) return;
        if (e.target.closest('a') || e.target.closest('button')) return;
        var href = row.dataset.href;
        if (href) {
            window.location.href = href;
        }
    });

    // Contract: th.sortable[data-action="sort"][data-sort-key] within
    // agent-detail context — click to sort model breakdown table.
    // Toggles ascending/descending and updates .sort-mark indicator.
    var modelSortState = { key: null, ascending: false };

    document.addEventListener('click', function(e) {
        var th = e.target.closest('th.sortable[data-action="sort"][data-sort-key]');
        if (!th) return;
        // Only handle tables within agent detail context (not agents list).
        var table = th.closest('table');
        if (!table || !table.querySelector('[data-action="open-session"]')) return;

        var key = th.dataset.sortKey;
        if (modelSortState.key === key) {
            modelSortState.ascending = !modelSortState.ascending;
        } else {
            modelSortState.key = key;
            modelSortState.ascending = false;
        }

        sortModelTable(table, modelSortState.key, modelSortState.ascending);
        updateModelSortIndicators(table, modelSortState);
    });

    function sortModelTable(table, key, ascending) {
        var tbody = table.querySelector('tbody');
        if (!tbody) return;
        var rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort(function(a, b) {
            var va = getModelCellValue(a, key);
            var vb = getModelCellValue(b, key);
            if (va === vb) return 0;
            var cmp = (va < vb) ? -1 : 1;
            return ascending ? cmp : -cmp;
        });
        rows.forEach(function(r) { tbody.appendChild(r); });
    }

    function getModelCellValue(row, key) {
        var cells = row.querySelectorAll('td');
        switch (key) {
            case 'model_name':
                return (cells[0]?.textContent || '').trim();
            case 'model_sessions':
                return parseInt(cells[1]?.textContent) || 0;
            case 'model_input':
                return parseCompactToken(cells[2]?.textContent || '0');
            case 'model_cache_reuse':
                return parseFloat(cells[3]?.textContent) || 0;
            case 'model_cache_w':
                return parseCompactToken(cells[4]?.textContent || '0');
            case 'model_output':
                return parseCompactToken(cells[5]?.textContent || '0');
            case 'model_tools':
                return parseCompactToken(cells[6]?.textContent || '0');
            case 'model_failed':
                return parseInt(cells[7]?.textContent) || 0;
            case 'avg_duration':
                return parseDuration(cells[8]?.textContent || '0');
            default:
                return 0;
        }
    }

    function updateModelSortIndicators(table, state) {
        var headers = table.querySelectorAll('th.sortable');
        headers.forEach(function(th) {
            var mark = th.querySelector('.sort-mark, .sort-caret');
            if (!mark) return;
            if (th.dataset.sortKey === state.key) {
                mark.textContent = state.ascending ? '↑' : '↓';
            } else {
                mark.textContent = '↕';
            }
        });
    }

    // Helper: parse compact token strings like "723.3M", "48.2K", "1,234".
    function parseCompactToken(str) {
        str = str.replace(/,/g, '').trim();
        var m = str.match(/^([\d.]+)\s*([KMkm])?$/);
        if (!m) return parseFloat(str) || 0;
        var val = parseFloat(m[1]);
        if (m[2] && m[2].toUpperCase() === 'K') val *= 1000;
        if (m[2] && m[2].toUpperCase() === 'M') val *= 1000000;
        return val;
    }

    // Helper: parse duration strings like "8.2s", "12m 47s", "1h 23m".
    function parseDuration(str) {
        var total = 0;
        var hm = str.match(/(\d+(?:\.\d+)?)\s*h/);
        if (hm) total += parseFloat(hm[1]) * 3600;
        var mm = str.match(/(\d+(?:\.\d+)?)\s*m(?!s)/);
        if (mm) total += parseFloat(mm[1]) * 60;
        var sm = str.match(/([\d.]+)\s*s/);
        if (sm) total += parseFloat(sm[1]);
        return total;
    }

    /* ── Session search (T144) ─────────────────────────────────── */
    // Contract: .section-head .input within agent sessions section —
    // instant filtering by session ID, title text, or project name.

    var agentSection = getAgentSection();
    var searchInput = agentSection ? agentSection.querySelector('.section-head .input') : null;
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            var query = searchInput.value.toLowerCase().trim();
            var sessionTable = document.getElementById('agent-sessions-table');
            if (!sessionTable) return;
            var rows = sessionTable.querySelectorAll('tbody tr');
            rows.forEach(function(row) {
                if (!query) {
                    row.style.display = '';
                    return;
                }
                var text = row.textContent.toLowerCase();
                row.style.display = text.indexOf(query) === -1 ? 'none' : '';
            });
            // Re-apply pagination after search filter changes
            setTimeout(function() { applyPagination(); }, 10);
        });
    }

    /* ── Sessions pagination (T146) ────────────────────────────── */
    // Contract: .unified-pagination within the same .card.section as
    // #agent-sessions-table — client-side pagination of tbody rows.
    // Respects active search filter.

    var PAGE_SIZE = 20;
    var currentPage = 1;
    var totalPages = 1;
    var visibleRows = [];

    function getAgentSection() {
        var table = document.getElementById('agent-sessions-table');
        return table ? table.closest('.card.section') : null;
    }

    function updatePaginationDisplay() {
        var section = getAgentSection();
        if (!section) return;
        var pagination = section.querySelector('.unified-pagination');
        var input = pagination ? pagination.querySelector('[data-action="page-input"]') : null;
        var statusText = document.getElementById('agent-page-status-text');
        var prevBtn = pagination ? pagination.querySelector('[data-action="prev-page"]') : null;
        var nextBtn = pagination ? pagination.querySelector('[data-action="next-page"]') : null;
        if (!input || !statusText) return;

        input.value = currentPage;
        var startIdx = (currentPage - 1) * PAGE_SIZE + 1;
        var endIdx = Math.min(currentPage * PAGE_SIZE, visibleRows.length);
        statusText.textContent = 'Page ' + currentPage + ' of ' + totalPages + ' · ' + startIdx + '–' + endIdx + ' of ' + visibleRows.length + ' sessions';

        // Show/hide prev/next buttons
        if (prevBtn) prevBtn.style.display = currentPage <= 1 ? 'none' : '';
        if (nextBtn) nextBtn.style.display = currentPage >= totalPages ? 'none' : '';

        // Show/hide rows
        visibleRows.forEach(function(row, i) {
            row.style.display = (i >= (currentPage - 1) * PAGE_SIZE && i < currentPage * PAGE_SIZE) ? '' : 'none';
        });
    }

    function applyPagination() {
        var table = document.getElementById('agent-sessions-table');
        if (!table) return;
        var tbody = table.querySelector('tbody');
        if (!tbody) return;
        var allRows = Array.from(tbody.querySelectorAll('tr'));
        visibleRows = allRows.filter(function(row) {
            return row.style.display !== 'none';
        });
        if (visibleRows.length === 0) {
            visibleRows = allRows;
        }
        totalPages = Math.ceil(visibleRows.length / PAGE_SIZE) || 1;
        if (currentPage > totalPages) currentPage = totalPages;
        updatePaginationDisplay();
    }

    // Wire up page input Enter key — scoped to agent detail pagination only.
    var agentPageInput = agentSection ? agentSection.querySelector('.unified-pagination [data-action="page-input"]') : null;
    if (agentPageInput) {
        agentPageInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                e.stopImmediatePropagation();
                var pageNum = parseInt(agentPageInput.value, 10);
                if (pageNum >= 1 && pageNum <= totalPages) {
                    currentPage = pageNum;
                    updatePaginationDisplay();
                }
            }
        });
    }

    // Wire up prev-page button
    var agentPrevBtn = agentSection ? agentSection.querySelector('.unified-pagination [data-action="prev-page"]') : null;
    if (agentPrevBtn) {
        agentPrevBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopImmediatePropagation();
            if (currentPage > 1) {
                currentPage--;
                updatePaginationDisplay();
            }
        });
    }

    // Wire up next-page button
    var agentNextBtn = agentSection ? agentSection.querySelector('.unified-pagination [data-action="next-page"]') : null;
    if (agentNextBtn) {
        agentNextBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopImmediatePropagation();
            if (currentPage < totalPages) {
                currentPage++;
                updatePaginationDisplay();
            }
        });
    }

    // Initialize on page load
    applyPagination();

    /* ── Topbar buttons: settings, help, shell (T141) ──────────── */
    // Contract: [data-action="settings"], [data-action="help"], [data-action="shell"]
    // in topbar/sidebar — show toast feedback (full implementation in base.html/common.js).

    document.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-action="settings"]');
        if (btn) { e.preventDefault(); showToast('Open Settings panel'); return; }
    });
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-action="help"]');
        if (btn) { e.preventDefault(); showToast('Open help panel'); return; }
    });
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-action="shell"]');
        if (btn) { e.preventDefault(); showToast('Open local shell / CLI hint'); return; }
    });

})();
