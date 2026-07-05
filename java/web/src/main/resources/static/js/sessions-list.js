// sessions-list.js — canonical page JS for Sessions List.
// Uses data-action event delegation; delegates shared primitives to ui_primitives.js.
// No inline event handlers. Does NOT duplicate logic from ui_primitives.js.
/**
 * sessions-list.js — Sessions List page behavior
 * =================================================
 *
 * Covered interactions:
 *   - sort:         intercept sortable header clicks (link or button),
 *                   update hidden sort/dir fields, dispatch table-sort,
 *                   then submit filter form.
 *   - filter:       form submit handler for #session-filter-form.
 *   - clear:        data-action="clear" (handled by ui_primitives),
 *                   dispatches filter-clear event consumed here.
 *   - pagination:   prev/next links, page-input Enter, page-size select.
 *   - row-click:    click .sessions-row → navigate to session detail.
 *   - nav:          sidebar navigation buttons.
 *
 * Delegation model:
 *   - Click events use document-level delegation via data-action attributes.
 *   - Sortable headers are augmented at init with data-action="sort".
 *   - ui_primitives.js handles the delegation dispatch; this file augments
 *     elements that lack data-action and listens for CustomEvents.
 *
 * Public API — window.SessionsList:
 *   - init()                initialize all behaviors (auto-called on DOMContentLoaded)
 *   - getFilterParams()     return current filter params as URLSearchParams
 *   - navigate(params)      navigate to /sessions with given params
 */
(function () {
  'use strict';

  // ── Helpers ──────────────────────────────────────────────────────────────

  function closest(el, selector) {
    while (el && el.nodeType === 1) {
      if (el.matches && el.matches(selector)) return el;
      el = el.parentElement;
    }
    return null;
  }

  /**
   * Extract sort key from element: data-sort-key attribute or href ?sort= param.
   */
  function getSortKey(el) {
    var key = el.getAttribute('data-sort-key');
    if (key) return key;
    var href = el.getAttribute('href') || '';
    var m = href.match(/[?&]sort=([^&]+)/);
    if (m) return decodeURIComponent(m[1]);
    return null;
  }

  /**
   * Extract sort direction from href ?dir= param.
   */
  function getSortDir(el) {
    var href = el.getAttribute('href') || '';
    var m = href.match(/[?&]dir=([^&]+)/);
    if (m) return decodeURIComponent(m[1]);
    return null;
  }

  /**
   * Build URLSearchParams from current filter form.
   */
  function getFilterParams() {
    var form = document.getElementById('session-filter-form');
    if (!form) return new URLSearchParams();
    return cleanParams(new URLSearchParams(new FormData(form)));
  }

  function normalizeAgent(value) {
    var normalized = (value || '').trim().toLowerCase();
    if (!normalized || normalized === 'all') return '';
    if (normalized === 'claude-code') return 'claude_code';
    return normalized;
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
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

  function apiUrl(path, params) {
    var qs = cleanParams(params instanceof URLSearchParams ? params : new URLSearchParams(params || {}));
    return path + (qs.toString() ? '?' + qs.toString() : '');
  }

  function cleanParams(params) {
    var cleaned = new URLSearchParams();
    params.forEach(function (value, key) {
      var v = value == null ? '' : String(value).trim();
      if (key === 'agent') v = normalizeAgent(v);
      if (!v) return;
      if (key === 'page' && v === '1') return;
      if (key === 'page_size' && v === '25') return;
      if ((key === 'sort' && (v === 'ended-at' || v === 'updated')) || (key === 'dir' && v === 'desc' && !params.get('sort'))) return;
      cleaned.set(key, v);
    });
    if (!cleaned.get('sort')) cleaned.delete('dir');
    return cleaned;
  }

  /**
   * Navigate to /sessions with the given params object.
   */
  function navigate(params) {
    var raw = new URLSearchParams();
    for (var k in params) {
      if (params[k] !== '' && params[k] != null) {
        raw.set(k, params[k]);
      }
    }
    var qs = cleanParams(raw);
    var url = '/sessions' + (qs.toString() ? '?' + qs.toString() : '');
    window.location.href = url;
  }

  /**
   * Submit the filter form (server-side navigation).
   */
  function submitFilter() {
    var form = document.getElementById('session-filter-form');
    if (!form) return;
    var params = getFilterParams();
    params.set('page', '1');
    fetchPage(paramsToObject(params));
  }

  /**
   * Handle browser back/forward: refresh from resource APIs.
   */
  window.addEventListener('popstate', function () {
    syncFormFromLocation();
    fetchPage(paramsToObject(getFilterParams()), true);
  });

  // ── Real-time client-side search + debounced server-side search ──────

  var SEARCH_DEBOUNCE_MS = 300;
  var _searchTimer = null;

  /**
   * Filter visible table rows based on search input value (instant feedback).
   * Only affects rows currently in the DOM (current page).
   */
  function filterVisibleRows(query) {
    var q = (query || '').toLowerCase().trim();
    var tbody = document.querySelector('.table-card .data-table tbody');
    if (!tbody) return;
    var rows = tbody.querySelectorAll('tr.sessions-row');
    var visibleCount = 0;
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var sessionId = (row.dataset.sessionId || '').toLowerCase();
      var title = (row.dataset.title || '').toLowerCase();
      var show = !q || sessionId.indexOf(q) >= 0 || title.indexOf(q) >= 0;
      row.classList.toggle('is-hidden', !show);
      if (show) visibleCount++;
    }
    // Update matching count in filter footer
    var countEl = document.querySelector('.active-filters__count');
    if (countEl) {
      countEl.textContent = visibleCount + ' matching sessions';
    }
  }

  /**
   * Trigger a server-side AJAX search to query the full database.
   * Resets to page 1 and replaces tbody + pagination with server results.
   */
  function debouncedServerSearch(query) {
    var params = getFilterParams();
    params.set('q', query || '');
    params.set('page', '1');

    fetchPage(paramsToObject(params));
  }

  function bindRealtimeSearch() {
    var searchInput = document.getElementById('session-search');
    if (!searchInput) return;

    searchInput.addEventListener('input', function () {
      var query = searchInput.value;
      // Instant client-side filter on current page rows
      filterVisibleRows(query);
      // Debounced server-side search across all sessions
      if (_searchTimer) clearTimeout(_searchTimer);
      _searchTimer = setTimeout(function () {
        debouncedServerSearch(query);
      }, SEARCH_DEBOUNCE_MS);
    });

    // Enter: cancel debounce and trigger immediate server search
    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (_searchTimer) {
          clearTimeout(_searchTimer);
          _searchTimer = null;
        }
        debouncedServerSearch(searchInput.value);
      }
    });

    // Apply saved search on load (server already filtered, but sync UI)
    if (searchInput.value) {
      filterVisibleRows(searchInput.value);
    }
  }

  // ── Auto-submit on select change ──────────────────────────────────────

  /**
   * Bind change events on filter selects to auto-submit the form.
   * Since there's no Apply button, selecting a filter immediately
   * triggers a server-side navigation with reset to page 1.
   */
  function bindSelectAutoSubmit() {
    var form = document.getElementById('session-filter-form');
    if (!form) return;

    form.addEventListener('change', function (e) {
      if (e.target.tagName !== 'SELECT') return;
      // Reset to page 1 when filter changes
      var pageInput = form.querySelector('input[name="page"]');
      if (pageInput) {
        pageInput.value = '1';
      }
      // Refresh from JSON APIs.
      submitFilter();
    });
  }

  // ── Token tooltip dynamic positioning ──────────────────────────────

  var TOOLTIP_FLIP_THRESHOLD = 180; // px from bottom of viewport to trigger flip

  function positionTokenTooltip(bar) {
    var tooltip = bar.querySelector('.token-tooltip');
    if (!tooltip) return;
    var rect = bar.getBoundingClientRect();
    var vpBottom = window.innerHeight || document.documentElement.clientHeight;
    var spaceBelow = vpBottom - rect.bottom;
    var shouldFlip = spaceBelow < TOOLTIP_FLIP_THRESHOLD;
    tooltip.classList.toggle('token-tooltip--flip', shouldFlip);
  }

  function setupTokenTooltips() {
    document.querySelectorAll('.data-table .token-total, .tokenbar-wrap').forEach(function (bar) {
      bar.addEventListener('mouseenter', function () {
        positionTokenTooltip(bar);
      });
      bar.addEventListener('focusin', function () {
        positionTokenTooltip(bar);
      });
    });
  }

  // ── Initialization: augment DOM for data-action delegation ──────────────

  function init() {
    augmentSortableHeaders();
    removeInlinePageSizeHandler();
    syncPageSizeHidden();
    bindFormSubmit();
    bindFilterClear();
    bindSortAndPaginationClicks();
    bindPagination();
    bindRealtimeSearch();
    bindSelectAutoSubmit();
    setupTokenTooltips();
    syncFormFromLocation();
    fetchPage(paramsToObject(getFilterParams()), true);

    // Expose public API
    window.SessionsList = {
      init: init,
      getFilterParams: getFilterParams,
      navigate: navigate
    };
  }

  /**
   * Add data-action="sort" to sortable header buttons/links.
   * Removes href from links so navigation goes through our handler
   * instead of default link-follow behavior.
   */
  function augmentSortableHeaders() {
    var sortBtns = document.querySelectorAll('.sessions-th .c-data-table__sort, .data-table th .c-data-table__sort');
    for (var i = 0; i < sortBtns.length; i++) {
      var btn = sortBtns[i];
      // Only augment if not already having data-action
      if (!btn.getAttribute('data-action')) {
        btn.setAttribute('data-action', 'sort');
        var key = getSortKey(btn);
        if (key) btn.setAttribute('data-sort-key', key);
        // Remove href to prevent default navigation;
        // our handler will submit the form instead.
        if (btn.tagName === 'A') {
          btn.removeAttribute('href');
          btn.style.cursor = 'pointer';
        }
      }
    }
  }

  /**
   * Remove inline onchange from page-size select so our delegation takes over.
   */
  function removeInlinePageSizeHandler() {
    var sel = document.querySelector('.sessions-footer-page-size__select');
    if (sel && sel.getAttribute('onchange')) {
      sel.removeAttribute('onchange');
    }
  }

  /**
   * Sync hidden page_size input with visible select value.
   * Ensures FormData(form) always includes the current page_size.
   */
  function syncPageSizeHidden() {
    var sel = document.querySelector('[data-action="page-size"]');
    var form = document.getElementById('session-filter-form');
    if (!sel || !form) return;
    var hidden = form.querySelector('input[name="page_size"]');
    if (hidden) {
      hidden.value = sel.value;
    }
  }

  // ── Event bindings ──────────────────────────────────────────────────────

  function bindSortAndPaginationClicks() {
    document.addEventListener('click', function (e) {
      var sortBtn = closest(e.target, '.c-data-table__sort[data-action="sort"]');
      if (sortBtn) {
        e.preventDefault();
        handleSort(sortBtn);
        return;
      }
    });
  }

  /**
   * Bind filter form submit handler.
   * Resets to page 1 on submit.
   */
  function bindFormSubmit() {
    var form = document.getElementById('session-filter-form');
    if (!form) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      // Remove any existing hidden page param to reset to page 1
      var pageInput = form.querySelector('input[name="page"]');
      if (pageInput) {
        pageInput.value = '1';
      }
      // Dispatch custom event for external handlers
      form.dispatchEvent(new CustomEvent('filter-submit', {
        bubbles: true,
        detail: { form: form }
      }));
      fetchPage(paramsToObject(getFilterParams()));
    });
  }

  /**
   * Listen for filter-clear events from ui_primitives.js.
   * Resets to page 1 and navigates to base /sessions URL.
   */
  function bindFilterClear() {
    document.addEventListener('filter-clear', function () {
      navigate({});
    });
  }

  // ── Sort handler (data-action="sort" delegated by ui_primitives) ────────

  /**
   * handleSort: called by ui_primitives click delegation for data-action="sort".
   * Updates hidden sort/dir fields and submits the filter form.
   */
  function handleSort(btnEl) {
    var sortKey = getSortKey(btnEl);
    if (!sortKey) return;

    var form = document.getElementById('session-filter-form');
    if (!form) return;

    // Determine current direction from hidden input
    var dirInput = form.querySelector('input[name="dir"]');
    var currentDir = dirInput ? dirInput.value : 'desc';

    // Toggle: desc → asc → desc (consistent with th_sort macro default of desc)
    var newDir = (currentDir === 'desc') ? 'asc' : 'desc';

    // Update hidden inputs
    var sortInput = form.querySelector('input[name="sort"]');
    if (sortInput) sortInput.value = sortKey;
    if (dirInput) dirInput.value = newDir;

    // Dispatch custom event for external handlers
    form.dispatchEvent(new CustomEvent('table-sort', {
      bubbles: true,
      detail: { key: sortKey, dir: newDir, header: btnEl }
    }));

    // Submit form for server-side sort
    submitFilter();
  }

  // ── Pagination ──────────────────────────────────────────────────────────

  /**
   * Apply an AJAX HTML response to the table: replace tbody + pagination.
   * Shared by fetchPage (pagination) and debouncedServerSearch (search).
   * Re-augments sortable headers, syncs page size, and re-binds tooltips.
   */
  function applyAjaxTableResponse(html, url) {
    var tbody = document.querySelector('.table-card .data-table tbody');
    if (!tbody) return;

    var parser = new DOMParser();
    var doc = parser.parseFromString(html, 'text/html');
    var ajaxResponse = doc.getElementById('sessions-ajax-response');
    if (!ajaxResponse) {
      throw new Error('Missing #sessions-ajax-response in AJAX response');
    }

    var newTbody = ajaxResponse.querySelector('tbody');
    if (!newTbody) {
      throw new Error('Missing tbody in AJAX response');
    }

    // Rows may be empty when filter matches nothing (empty-state row).
    // Only fall back to full navigation if the tbody element itself is missing.
    replaceChildrenFrom(tbody, newTbody);

    // Replace pagination — page input value comes from server response
    var newPagination = ajaxResponse.querySelector('#ajax-pagination');
    if (newPagination) {
      var oldPagination = document.getElementById('ajax-pagination');
      if (oldPagination) {
        replaceChildrenFrom(oldPagination, newPagination);
      } else {
        var tableCard = tbody.closest('.table-card') || tbody.closest('.card');
        if (tableCard) {
          var paginationDiv = document.createElement('div');
          paginationDiv.id = 'ajax-pagination';
          replaceChildrenFrom(paginationDiv, newPagination);
          tableCard.appendChild(paginationDiv);
        }
      }
    }

    // Update matching count in filter footer
    var countEl = document.querySelector('.active-filters__count');
    if (countEl) {
      var serverCountEl = ajaxResponse.querySelector('.active-filters__count');
      if (serverCountEl) {
        countEl.textContent = serverCountEl.textContent;
      }
    }

    // pushState ONLY after successful response and DOM update
    if (url) {
      window.history.pushState({ ajax: true }, '', url);
    }

    // Re-augment sortable headers on new DOM so data-action is present
    augmentSortableHeaders();

    // Sync hidden page_size with the new select from AJAX response
    syncPageSizeHidden();

    // Re-bind token tooltip positioning for new rows
    setupTokenTooltips();
  }

  function replaceChildrenFrom(target, source) {
    var imported = Array.prototype.map.call(source.childNodes, function (node) {
      return document.importNode(node, true);
    });
    target.replaceChildren.apply(target, imported);
  }

  function showLoadingRow(tbody) {
    var row = document.createElement('tr');
    var cell = document.createElement('td');
    cell.colSpan = 13;
    cell.className = 'sessions-loading-cell';
    cell.textContent = 'Loading...';
    row.appendChild(cell);
    tbody.replaceChildren(row);
  }

  function syncFormFromLocation() {
    var form = document.getElementById('session-filter-form');
    if (!form) return;
    var params = new URLSearchParams(window.location.search);
    ['q', 'agent', 'model', 'project', 'status', 'sort', 'dir', 'page_size', 'page'].forEach(function (key) {
      var field = form.querySelector('[name="' + key + '"]');
      if (!field) return;
      var value = params.get(key) || '';
      if (key === 'agent') value = normalizeAgent(value);
      if (key === 'page' && !value) value = '1';
      if (key === 'page_size' && !value) value = '25';
      if (key === 'dir' && !value) value = 'desc';
      field.value = value;
    });
  }

  function setSelectOptions(select, options, selectedValue, allLabel) {
    if (!select || !Array.isArray(options)) return;
    var current = selectedValue == null ? '' : String(selectedValue);
    var normalized = options.slice();
    if (allLabel && (!normalized.length || (normalized[0].value !== '' && normalized[0].value !== 'all'))) {
      normalized.unshift({ value: '', label: allLabel });
    }
    select.replaceChildren.apply(select, normalized.map(function (option) {
      var value = option.value === 'all' ? '' : String(option.value || '');
      var opt = document.createElement('option');
      opt.value = value;
      opt.textContent = option.label || (value || allLabel || 'All');
      if (value === current || (!value && !current)) opt.selected = true;
      return opt;
    }));
  }

  function renderSummary(summary) {
    if (!summary) return;
    var stats = document.querySelector('.page-head__stats');
    if (stats) {
      stats.replaceChildren(
        statPill(summary.totalCount, 'sessions'),
        statPill(summary.projectCount, 'projects'),
        statPill(formatCompact(summary.tokens && summary.tokens.total), 'total tokens')
      );
    }
    var countEl = document.querySelector('.active-filters__count');
    if (countEl) {
      countEl.textContent = summary.totalCount > 0
        ? summary.totalCount + ' matching sessions'
        : 'No matching sessions';
    }
  }

  function statPill(value, label) {
    var span = document.createElement('span');
    span.className = 'ui-stat-pill';
    span.setAttribute('role', 'status');
    var b = document.createElement('b');
    b.textContent = String(value);
    span.appendChild(b);
    span.appendChild(document.createTextNode(' ' + label));
    return span;
  }

  function renderOptions(options, filters) {
    if (!options) return;
    setSelectOptions(document.getElementById('filter-agent'), options.agents, filters.agent, 'All Agents');
    setSelectOptions(document.getElementById('filter-model'), options.models, filters.model, 'All Models');
    setSelectOptions(document.getElementById('filter-project'), options.projects, filters.project, 'All Projects');
    setSelectOptions(document.getElementById('filter-status'), options.statuses, filters.status, 'All');
  }

  function renderRows(rowsResponse) {
    var tbody = document.querySelector('.table-card .data-table tbody');
    if (!tbody || !rowsResponse) return;
    var rows = rowsResponse.rows || [];
    if (!rows.length) {
      tbody.replaceChildren(emptyRow(rowsResponse.state));
    } else {
      tbody.replaceChildren.apply(tbody, rows.map(sessionRowElement));
    }
    renderPagination(rowsResponse.pagination);
    updateHiddenPaging(rowsResponse.filters, rowsResponse.pagination);
    augmentSortableHeaders();
    setupTokenTooltips();
  }

  function emptyRow(state) {
    var row = document.createElement('tr');
    var cell = document.createElement('td');
    cell.colSpan = 13;
    var title = state && state.title ? state.title : 'No sessions found';
    var message = state && state.message ? state.message : 'No sessions match your current filters.';
    cell.innerHTML = '<div class="empty-state"><div><div class="empty-state__icon">🔎</div><h2 class="empty-state__title">'
      + escapeHtml(title) + '</h2><p class="empty-state__text">' + escapeHtml(message)
      + '</p><a href="/sessions" class="btn primary" data-action="clear">Clear Filters</a></div></div>';
    row.appendChild(cell);
    return row;
  }

  function sessionRowElement(row) {
    var tr = document.createElement('tr');
    var tokens = row.tokens || {};
    var title = row.title || row.sessionId;
    var projectLabel = row.projectName || row.projectKey || '—';
    var agentClass = row.agent === 'claude_code' ? 'cc' : (row.agent === 'codex' ? 'cx' : 'qd');
    var agentText = row.agent === 'claude_code' ? 'CC' : (row.agent === 'codex' ? 'CX' : 'QD');
    tr.className = 'sessions-row';
    tr.setAttribute('data-action', 'row');
    tr.dataset.sessionKey = row.sessionKey || '';
    tr.dataset.agent = row.agent || '';
    tr.dataset.model = row.model || '';
    tr.dataset.project = row.projectKey || '';
    tr.dataset.sessionId = row.sessionId || '';
    tr.dataset.detailUrl = row.detailUrl || '';
    tr.dataset.title = title;
    tr.dataset.endedAt = row.updatedAt || '';
    tr.dataset.totalTokens = tokens.total || 0;
    tr.dataset.rounds = row.rounds || 0;
    tr.dataset.toolCount = row.tools || 0;
    tr.dataset.duration = row.durationSeconds || 0;
    tr.dataset.processTime = row.processSeconds || 0;
    tr.dataset.failedTools = row.failedTools || 0;
    tr.dataset.createdAt = row.createdAt || '';
    tr.innerHTML = [
      '<td class="col-session"><div class="title-main"><a class="session-link" href="', escapeHtml(row.detailUrl), '" data-action="open-session" data-session-link>',
      escapeHtml(title), '</a></div><div class="title-sub mono"><span>', escapeHtml((row.sessionId || '').slice(0, 12)), '</span></div></td>',
      '<td class="col-project"><div class="project-cell"><span class="project-name"><a href="', escapeHtml(row.projectUrl || '#'), '" class="link-muted" data-project="', escapeHtml(row.projectKey || ''), '" title="', escapeHtml(row.cwd || ''), '">',
      escapeHtml(projectLabel), '</a></span></div></td>',
      '<td class="col-agent"><span class="badge ', agentClass, '">', agentText, '</span></td>',
      '<td class="mono col-model" title="', escapeHtml(row.model || ''), '">', escapeHtml(row.model || 'Unknown model'), '</td>',
      tokenCellHtml(tokens, 'col-tokens'),
      '<td class="num mono col-rounds">', formatNumber(row.rounds), '</td>',
      '<td class="num mono col-tools">', formatNumber(row.tools), '</td>',
      '<td class="num mono col-subagents">', formatNumber(row.subagents), '</td>',
      '<td class="mono col-duration" data-tooltip="', escapeHtml(row.durationSeconds), 's">', formatDuration(row.durationSeconds), '</td>',
      '<td class="mono col-process-time" data-tooltip="active processing ', escapeHtml(row.processSeconds), 's">', formatDuration(row.processSeconds), '</td>',
      '<td class="col-failure ', Number(row.failedTools || 0) === 0 ? 'muted' : '', '">',
      Number(row.failedTools || 0) > 0 ? formatNumber(row.failedTools) + ' failed' : 'No failures', '</td>',
      '<td class="mono col-created" title="', escapeHtml(row.createdAt || ''), '">', escapeHtml(formatDate(row.createdAt)), '</td>',
      '<td class="muted col-updated">', escapeHtml(formatDate(row.updatedAt)), '</td>'
    ].join('');
    return tr;
  }

  function tokenCellHtml(tokens, extraClass) {
    var freshPct = segmentPct(tokens, 'fresh');
    var readPct = segmentPct(tokens, 'cacheRead');
    var writePct = segmentPct(tokens, 'cacheWrite');
    var outPct = segmentPct(tokens, 'output');
    return [
      '<td class="mono token-cell ', extraClass || '', '"><span class="token-total"><span class="token-total__value">',
      formatCompact(tokens && tokens.total), '</span><span class="tokenbar tokenbar-in-cell" aria-hidden="true">',
      '<span class="tokenbar-seg fresh t-fresh" style="--segment-width:', freshPct, '%"></span>',
      '<span class="tokenbar-seg read t-read" style="--segment-width:', readPct, '%"></span>',
      '<span class="tokenbar-seg write t-write" style="--segment-width:', writePct, '%"></span>',
      '<span class="tokenbar-seg out t-out" style="--segment-width:', outPct, '%"></span>',
      '<span class="token-tooltip" aria-hidden="true"><span class="token-tooltip__title">Token Breakdown</span>',
      tooltipRowHtml('fresh', 'Fresh input', tokens && tokens.fresh, freshPct),
      tooltipRowHtml('read', 'Cached Rd', tokens && tokens.cacheRead, readPct),
      tooltipRowHtml('write', 'Cached Wr', tokens && tokens.cacheWrite, writePct),
      tooltipRowHtml('out', 'Output', tokens && tokens.output, outPct),
      '<span class="token-tooltip__sep"></span><span class="token-tooltip__row token-tooltip__total"><span>Total</span><span class="token-tooltip__value">',
      formatCompact(tokens && tokens.total), '</span></span></span></span></span></td>'
    ].join('');
  }

  function tooltipRowHtml(cls, label, value, pct) {
    return '<span class="token-tooltip__row"><span class="token-tooltip__label"><span class="dot dot--'
      + cls + '"></span><span class="token-tooltip__type-name">' + escapeHtml(label)
      + '</span></span><span class="token-tooltip__value">' + formatCompact(value)
      + '</span><span class="token-tooltip__pct">' + pct + '%</span></span>';
  }

  function renderPagination(pagination) {
    var wrapper = document.getElementById('ajax-pagination');
    var card = document.querySelector('.sessions-table-card');
    if (!wrapper && card) {
      var paginationShell = document.createElement('div');
      paginationShell.className = 'table-card-pagination';
      wrapper = document.createElement('div');
      wrapper.id = 'ajax-pagination';
      paginationShell.appendChild(wrapper);
      card.appendChild(paginationShell);
    }
    if (!wrapper || !pagination) return;
    var disabled = (pagination.totalPages || 0) <= 1;
    wrapper.innerHTML = '<nav class="pagination unified-pagination" role="navigation" aria-label="Sessions pagination" data-pagination>'
      + '<button class="btn sm" data-action="prev-page" aria-label="Previous page"'
      + (!pagination.hasPrevious || disabled ? ' disabled' : '') + '>&lsaquo; prev</button>'
      + '<span class="page-status">Page</span>'
      + '<input class="page-input mono" data-action="page-input" aria-label="Page number" value="'
      + escapeHtml(pagination.page) + '" data-total-pages="' + escapeHtml(pagination.totalPages || 1) + '"'
      + (disabled ? ' disabled' : '') + ' title="输入页码后按 Enter，跳转到指定页">'
      + '<span class="page-status">of ' + escapeHtml(pagination.totalPages || 0)
      + (pagination.totalItems > 0 ? ' of ' + escapeHtml(pagination.totalItems) : '') + '</span>'
      + '<span class="spacer"></span><label class="page-size-label page-status">每页 '
      + '<select class="page-size-select sessions-footer-page-size__select" data-action="page-size" aria-label="Page size">'
      + pageSizeOption(25, pagination.pageSize) + pageSizeOption(50, pagination.pageSize)
      + pageSizeOption(100, pagination.pageSize) + '</select></label>'
      + '<button class="btn sm" data-action="next-page" aria-label="Next page"'
      + (!pagination.hasNext || disabled ? ' disabled' : '') + '>next &rsaquo;</button></nav>';
  }

  function pageSizeOption(value, selected) {
    return '<option value="' + value + '"' + (Number(selected) === value ? ' selected' : '') + '>' + value + '</option>';
  }

  function updateHiddenPaging(filters, pagination) {
    var form = document.getElementById('session-filter-form');
    if (!form) return;
    var page = form.querySelector('input[name="page"]');
    var pageSize = form.querySelector('input[name="page_size"]');
    var sort = form.querySelector('input[name="sort"]');
    var dir = form.querySelector('input[name="dir"]');
    if (page && pagination) page.value = String(pagination.page || 1);
    if (pageSize && pagination) pageSize.value = String(pagination.pageSize || 25);
    if (sort && filters) sort.value = filters.sort || '';
    if (dir && filters) dir.value = filters.dir || 'desc';
  }

  /**
   * Fetch a page via JSON resource APIs and replace table body + pagination.
   * pushState only happens AFTER successful response — never before.
   * On failure, does full reload to target URL — never leaves a loading/empty table.
   * After replacing pagination, re-augments sortable headers so new DOM has data-action.
   */
  function fetchPage(params, replaceState) {
    var qs = new URLSearchParams();
    for (var k in params) {
      if (params[k] !== '' && params[k] != null) {
        qs.set(k, params[k]);
      }
    }
    qs = cleanParams(qs);
    var url = '/sessions' + (qs.toString() ? '?' + qs.toString() : '');

    var tbody = document.querySelector('.table-card .data-table tbody');
    if (!tbody) {
      // Fallback: full navigation if target not found
      window.location.href = url;
      return;
    }

    // Show loading state
    showLoadingRow(tbody);

    Promise.all([
      fetch(apiUrl('/api/sessions/summary', qs), { headers: { 'Accept': 'application/json' } }).then(readJson),
      fetch(apiUrl('/api/sessions/options', qs), { headers: { 'Accept': 'application/json' } }).then(readJson),
      fetch(apiUrl('/api/sessions/rows', qs), { headers: { 'Accept': 'application/json' } }).then(readJson)
    ])
    .then(function (parts) {
      renderSummary(parts[0]);
      renderOptions(parts[1], parts[2].filters || {});
      renderRows(parts[2]);
      if (replaceState) {
        window.history.replaceState({ api: true }, '', url);
      } else {
        window.history.pushState({ api: true }, '', url);
      }
    })
    .catch(function (err) {
      console.error('Sessions API pagination fallback:', err.message || err);
      // Safe fallback: direct full-page navigation without restore attempt.
      window.location.href = url;
    });
  }

  function readJson(response) {
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.json();
  }

  /**
   * Bind page-change and page-size-change events from ui_primitives.js.
   * Uses AJAX to fetch and replace table content without page reload.
   */
  function bindPagination() {
    // page-change: dispatched when prev/next buttons or page-input Enter
    document.addEventListener('page-change', function (event) {
      var detail = event.detail || {};
      if (detail.page) {
        var params = getFilterParams();
        params.set('page', String(detail.page));
        // Preserve hidden sort/dir fields
        var form = document.getElementById('session-filter-form');
        if (form) {
          var sortInput = form.querySelector('input[name="sort"]');
          var dirInput = form.querySelector('input[name="dir"]');
          if (sortInput && sortInput.value) params.set('sort', sortInput.value);
          if (dirInput && dirInput.value) params.set('dir', dirInput.value);
        }
        // Preserve page_size from pagination select
        var pageSizeSel = document.querySelector('.sessions-footer-page-size__select, [data-action="page-size"]');
        if (pageSizeSel && pageSizeSel.value) params.set('page_size', pageSizeSel.value);
        fetchPage(paramsToObject(params));
      } else if (detail.href) {
        // Legacy: direct URL navigation
        window.location.href = detail.href;
      }
    });

    // page-size-change: dispatched when page-size select changes
    document.addEventListener('page-size-change', function (event) {
      var detail = event.detail || {};
      if (detail.pageSize) {
        var params = getFilterParams();
        params.set('page_size', String(detail.pageSize));
        params.set('page', '1'); // reset to first page on size change
        // Preserve hidden sort/dir fields
        var form = document.getElementById('session-filter-form');
        if (form) {
          var sortInput = form.querySelector('input[name="sort"]');
          var dirInput = form.querySelector('input[name="dir"]');
          if (sortInput && sortInput.value) params.set('sort', sortInput.value);
          if (dirInput && dirInput.value) params.set('dir', dirInput.value);
        }
        fetchPage(paramsToObject(params));
      }
    });
  }

  /**
   * Convert URLSearchParams to a plain object for navigate().
   */
  function paramsToObject(params) {
    var obj = {};
    params.forEach(function (value, key) {
      obj[key] = value;
    });
    return obj;
  }

  // ── Row click navigation ────────────────────────────────────────────────

  function markRowOpening(row) {
    if (!row) return;
    row.classList.add('is-opening');
    row.setAttribute('aria-busy', 'true');
  }

  function getDetailUrl(row) {
    var explicitUrl = row.getAttribute('data-detail-url');
    if (explicitUrl) return explicitUrl;
    var agent = row.dataset.agent;
    var sessionId = row.dataset.sessionId;
    if (!agent || !sessionId) return '';
    return '/sessions/' + encodeURIComponent(agent) + '/' + encodeURIComponent(sessionId);
  }

  document.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || target.nodeType !== 1) return;
    var row = target.closest('.sessions-row');
    if (!row) return;

    // Don't navigate if clicking a link inside the row
    if (target.closest('a')) {
      if (target.closest('[data-session-link]')) {
        markRowOpening(row);
      }
      return;
    }

    // Dispatch custom event for external handlers
    row.dispatchEvent(new CustomEvent('session-row-click', {
      bubbles: true,
      detail: {
        agent: row.dataset.agent,
        sessionId: row.dataset.sessionId,
        row: row
      }
    }));

    var detailUrl = getDetailUrl(row);
    if (detailUrl) {
      markRowOpening(row);
      window.location.assign(detailUrl);
    }
  });

  // ── Auto-init on DOM ready ──────────────────────────────────────────────

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
