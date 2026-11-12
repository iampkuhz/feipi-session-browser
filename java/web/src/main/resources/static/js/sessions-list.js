// 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`sessions-list.js — canonical page JS for Sessions List.`
// 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Uses data-action event delegation; delegates shared primitives to ui_primitives.js.`
// 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`No inline event handlers. Does NOT duplicate logic from ui_primitives.js.`
/* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`* * sessions-list.js — Sessions List page behavior * ================================================= * * Covered interactions: * - sort: intercept sortable header clicks (link or button), * update hidden sort/dir fields, dispatch table-sort, * then submit filter form. * - filter: form submit handl` */
(function () {
  'use strict';

  var sessionsRequestGeneration = 0;

  // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`── Helpers ──────────────────────────────────────────────────────────────`

  function closest(el, selector) {
    while (el && el.nodeType === 1) {
      if (el.matches && el.matches(selector)) return el;
      el = el.parentElement;
    }
    return null;
  }

  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`* * Extract sort key from element: data-sort-key attribute or href ?sort= param.` */
  function getSortKey(el) {
    var key = el.getAttribute('data-sort-key');
    if (key) return key;
    var href = el.getAttribute('href') || '';
    var m = href.match(/[?&]sort=([^&]+)/);
    if (m) return decodeURIComponent(m[1]);
    return null;
  }

  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`* * Extract sort direction from href ?dir= param.` */
  function getSortDir(el) {
    var href = el.getAttribute('href') || '';
    var m = href.match(/[?&]dir=([^&]+)/);
    if (m) return decodeURIComponent(m[1]);
    return null;
  }

  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`* * Build URLSearchParams from current filter form.` */
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

  function setMarkup(target, markup) {
    var parsed;
    var source;
    if (target && target.tagName === 'TR') {
      // 中文说明：DOMParser 解析孤立 <td> 时会按 HTML 规则剥离 table cell。
      // 这里补齐 table 上下文，确保 API 渲染出的 session row 仍然是合法 <tr><td>...</td></tr>。
      parsed = new DOMParser().parseFromString(
        '<table><tbody><tr>' + (markup || '') + '</tr></tbody></table>',
        'text/html'
      );
      source = parsed.querySelector('tbody tr');
    } else {
      parsed = new DOMParser().parseFromString(markup || '', 'text/html');
      source = parsed.body;
    }
    if (!source) return;
    target.replaceChildren.apply(target, Array.prototype.slice.call(source.childNodes));
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
    if (n >= 3600) return Math.floor(n / 3600) + 'h ' + Math.floor((n % 3600) / 60) + 'min';
    if (n >= 60) return Math.floor(n / 60) + 'min ' + (n % 60) + 's';
    return n + 's';
  }

  function pad2(value) {
    return String(value).padStart(2, '0');
  }

  function formatDateTime(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (isNaN(date.getTime())) return value;
    return date.getFullYear() + '-' + pad2(date.getMonth() + 1) + '-' + pad2(date.getDate())
      + ' ' + pad2(date.getHours()) + ':' + pad2(date.getMinutes()) + ':' + pad2(date.getSeconds());
  }

  function formatRelativeTime(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (isNaN(date.getTime())) return value;
    var seconds = Math.max(0, (Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return seconds.toFixed(1) + 's ago';
    if (seconds < 3600) return (seconds / 60).toFixed(1) + 'm ago';
    if (seconds < 86400) return (seconds / 3600).toFixed(1) + 'h ago';
    return (seconds / 86400).toFixed(1) + 'd ago';
  }

  function apiUrl(path, params) {
    var qs = cleanParams(params instanceof URLSearchParams ? params : new URLSearchParams(params || {}));
    return path + (qs.toString() ? '?' + qs.toString() : '');
  }

  function cleanParams(params) {
    if (['failure', 'duration'].indexOf((params.get('sort') || '').trim().toLowerCase()) >= 0) {
      params.delete('sort');
      params.delete('dir');
    }
    var cleaned = new URLSearchParams();
    params.forEach(function (value, key) {
      var v = value == null ? '' : String(value).trim();
      if (key === 'agent') v = normalizeAgent(v);
      if (!v) return;
      if (key === 'page' && v === '1') return;
      if (key === 'page_size' && v === '25') return;
      if ((key === 'sort' && (v === 'ended-at' || v === 'updated') && params.get('dir') !== 'asc')
          || (key === 'dir' && v === 'desc' && !params.get('sort'))) return;
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
   * 标记搜索 pending 状态；数据过滤只由 /api/sessions/* 响应决定。
   */
  function filterVisibleRows(query) {
    var q = (query || '').trim();
    var countEl = document.querySelector('.active-filters__count');
    if (countEl) {
      countEl.textContent = q ? 'Searching sessions…' : 'Loading sessions…';
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
      // 仅显示 pending；最终结果必须来自 API。
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

    // Apply saved search on load (server/API response remains the data source).
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

  // ── Initialization: augment DOM for data-action delegation ──────────────

  function init() {
    augmentSortableHeaders();
    removeInlinePageSizeHandler();
    bindFormSubmit();
    bindFilterClear();
    bindSortAndPaginationClicks();
    bindPagination();
    bindRealtimeSearch();
    bindSelectAutoSubmit();
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
    SessionTiming.prepareTable(tbody.closest('table'));
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
    cell.colSpan = 11;
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
        statPill(TokenProvenance.amount(summary.tokens, 'total', formatCompact), 'total tokens')
      );
      TokenProvenance.attach(stats, summary.tokens);
    }
    var countEl = document.querySelector('.active-filters__count');
    if (countEl) {
      countEl.textContent = summary.totalCount > 0
        ? formatNumber(summary.totalCount) + ' matching sessions'
        : 'No matching sessions';
    }
  }

  function renderActiveFilters(activeFilters) {
    var container = document.querySelector('.active-filters');
    if (!container || !activeFilters) return;
    var chips = Array.isArray(activeFilters.chips) ? activeFilters.chips : [];
    if (!chips.length) {
      container.replaceChildren();
      return;
    }
    container.replaceChildren.apply(container, chips.map(function (chip) {
      var span = document.createElement('span');
      span.className = 'ui-filter-chip';
      span.appendChild(document.createTextNode((chip.label || chip.key || 'Filter') + ': ' + (chip.value || '')));
      span.appendChild(document.createTextNode(' '));
      var a = document.createElement('a');
      a.href = chip.removeUrl || activeFilters.clearAllUrl || '/sessions';
      a.setAttribute('aria-label', 'Remove ' + (chip.key || 'filter') + ' filter');
      a.textContent = '×';
      span.appendChild(a);
      return span;
    }));
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
    SessionTiming.prepareTable(tbody.closest('table'));
  }

  function emptyRow(state) {
    var row = document.createElement('tr');
    var cell = document.createElement('td');
    cell.colSpan = 11;
    var title = state && state.title ? state.title : 'No sessions found';
    var message = state && state.message ? state.message : 'No sessions match your current filters.';
    setMarkup(cell, '<div class="empty-state"><div><div class="empty-state__icon">🔎</div><h2 class="empty-state__title">'
      + escapeHtml(title) + '</h2><p class="empty-state__text">' + escapeHtml(message)
      + '</p><a href="/sessions" class="btn primary" data-action="clear">Clear Filters</a></div></div>');
    row.appendChild(cell);
    return row;
  }

  function sessionTitle(row) {
    var title = String(row.displayTitle == null ? row.title || '' : row.displayTitle).replace(/\s+/g, ' ').trim();
    var id = row.sessionId || '';
    return !title || title === id || title === row.sessionKey || title === id.slice(0, 12)
      || /^[a-f\d]{8}-[a-f\d-]{27,}$/i.test(title) ? 'Untitled session' : title;
  }

  function toolsMarkup(row) {
    var total = row.tools == null ? '—' : formatNumber(row.tools);
    var known = row.failedTools != null;
    var label = (row.tools == null ? 'Tool calls unknown' : formatNumber(row.tools) + ' tool calls') + '; '
      + (known ? formatNumber(row.failedTools) + ' failed' : 'failures unknown');
    return '<td class="num mono col-tools" title="' + escapeHtml(label) + '" aria-label="' + escapeHtml(label) + '">'
      + total + (known && row.failedTools > 0 ? '<span class="sessions-tool-failures">(' + formatNumber(row.failedTools) + ')</span>'
        : !known ? '<span class="sessions-tools-unknown">(?)</span>' : '') + '</td>';
  }

  function taskActiveMarkup(timing) {
    var value = SessionTiming.value(timing, 'activeTaskSeconds');
    if (SessionTiming.seconds(timing, 'activeTaskSeconds') != null && timing.activeTaskPrecision === 'partial') {
      return escapeHtml(value.replace(' · Partial', ''))
        + ' <button type="button" class="sessions-partial" popovertarget="sessions-task-active-help" aria-describedby="sessions-task-active-help">Partial</button>';
    }
    return escapeHtml(value);
  }

  function sessionRowElement(row) {
    var tr = document.createElement('tr');
    var tokens = row.tokens || {};
    var title = sessionTitle(row);
    var projectLabel = row.projectName || row.projectKey || '—';
    var agentClass = row.agent === 'claude_code' ? 'cc' : (row.agent === 'codex' ? 'cx' : 'qd');
    var agentDotClass = row.agent === 'claude_code' ? 'claude' : (row.agent === 'codex' ? 'codex' : 'qoder');
    var agentText = row.agent === 'claude_code' ? 'CC' : (row.agent === 'codex' ? 'CX' : 'QD');
    var agentLabel = row.agent === 'claude_code' ? 'Claude Code' : (row.agent === 'codex' ? 'Codex' : 'Qoder');
    var branch = row.gitBranch || '';
    var rounds = DataTable.sessionRounds(row);
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
    tr.dataset.toolCount = row.tools == null ? '' : row.tools;
    tr.dataset.duration = SessionTiming.seconds(row.timing, 'wallSeconds');
    tr.dataset.processTime = SessionTiming.seconds(row.timing, 'activeTaskSeconds');
    tr.dataset.failedTools = row.failedTools == null ? '' : row.failedTools;
    tr.dataset.createdAt = row.createdAt || '';
    setMarkup(tr, [
      '<td class="col-session"><div class="title-main"><a class="session-link" href="', escapeHtml(row.detailUrl), '" title="', escapeHtml(title), '" data-action="open-session" data-session-link>',
      escapeHtml(title), '</a></div><div class="title-sub mono"><span class="mono" title="', escapeHtml(row.sessionId || ''), '">', escapeHtml((row.sessionId || '').slice(0, 12)), '</span>',
      branch ? '<span class="session-branch" title="' + escapeHtml(branch) + '">· ' + escapeHtml(branch) + '</span>' : '',
      '</div></td>',
      '<td class="col-project"><div class="project-cell"><span class="project-name"><a href="', escapeHtml(row.projectUrl || '#'), '" class="link-muted" data-project="', escapeHtml(row.projectKey || ''), '" title="', escapeHtml(row.cwd || ''), '">',
      escapeHtml(projectLabel), '</a></span></div></td>',
      '<td class="col-agent"><span class="badge ', agentClass, ' badge--has-dot" data-tooltip="', escapeHtml(agentLabel), '" role="status"><span class="badge-dot badge-dot--', agentDotClass, '" aria-hidden="true"></span>', agentText, '</span></td>',
      '<td class="mono col-model" title="', escapeHtml(row.model || ''), '">', escapeHtml(row.model || 'Unknown model'), '</td>',
      '<td class="token-cell col-tokens"></td>',
      '<td class="num mono col-rounds" title="', escapeHtml(rounds.note), '">', escapeHtml(rounds.value), '</td>',
      toolsMarkup(row),
      '<td class="num mono col-subagents">', (row.subagents == null ? "—" : formatNumber(row.subagents)), '</td>',
      '<td class="mono col-process-time" data-task-active>', taskActiveMarkup(row.timing), '</td>',
      '<td class="mono col-created" title="', escapeHtml(row.createdAt || ''), '">', escapeHtml(formatDateTime(row.createdAt)), '</td>',
      '<td class="muted col-updated" title="', escapeHtml(row.updatedAt || ''), '">', escapeHtml(formatRelativeTime(row.updatedAt)), '</td>'
    ].join(''));
    var partialBadge = tr.querySelector('.sessions-partial');
    if (partialBadge) partialBadge.title = document.getElementById('sessions-task-active-help').textContent.trim();
    TokenProvenance.renderCell(tr.querySelector('.token-cell'), tokens, formatCompact, true, 'compact');
    return tr;
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
    setMarkup(wrapper, '<nav class="pagination unified-pagination" role="navigation" aria-label="Sessions pagination" data-pagination>'
      + '<button class="btn sm" data-action="prev-page" aria-label="Previous page"'
      + (!pagination.hasPrevious || disabled ? ' disabled' : '') + '>&lsaquo; prev</button>'
      + '<span class="page-status">Page</span>'
      + '<input class="page-input mono" data-action="page-input" aria-label="Page number" value="'
      + escapeHtml(pagination.page) + '" data-total-pages="' + escapeHtml(pagination.totalPages || 1) + '"'
      + (disabled ? ' disabled' : '') + ' title="输入页码后按 Enter，跳转到指定页">'
      + '<span class="page-status">of ' + formatNumber(pagination.totalPages)
      + (pagination.totalItems > 0 ? ' · ' + formatNumber(pagination.totalItems) + ' sessions' : '') + '</span>'
      + '<span class="spacer"></span><label class="page-size-label page-status">每页 '
      + '<select class="page-size-select sessions-footer-page-size__select" data-action="page-size" aria-label="Page size">'
      + pageSizeOptions(pagination.pageSize) + '</select></label>'
      + '<button class="btn sm" data-action="next-page" aria-label="Next page"'
      + (!pagination.hasNext || disabled ? ' disabled' : '') + '>next &rsaquo;</button></nav>');
  }

  function pageSizeOption(value, selected) {
    return '<option value="' + value + '"' + (Number(selected) === value ? ' selected' : '') + '>' + value + '</option>';
  }

  function pageSizeOptions(selected) {
    var sizes = [25, 50, 100];
    if (Number.isInteger(selected) && selected > 0 && !sizes.includes(selected)) sizes.push(selected);
    return sizes.sort(function (a, b) { return a - b; }).map(function (size) {
      return pageSizeOption(size, selected);
    }).join('');
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
   * Resources render only after their index generation agrees; ordinary failures retain local retry.
   * After replacing pagination, re-augments sortable headers so new DOM has data-action.
   */
  var sessionsSnapshot = null;
  function fetchPage(params, replaceState) {
    var generation = ++sessionsRequestGeneration;
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

    // A new query owns the page; errors and retries from older queries are obsolete.
    document.querySelectorAll('[data-resource-error]').forEach(function (error) { error.remove(); });
    // Show loading state
    showLoadingRow(tbody);

    var filters = params;
    var resources = {
      summary: renderSummary,
      options: function (part) { renderOptions(part, filters); },
      rows: function (part) {
        filters = part.filters || params;
        renderRows(part);
        if (replaceState) window.history.replaceState({ api: true }, '', url);
        else window.history.pushState({ api: true }, '', url);
      },
      'active-filters': renderActiveFilters
    };
    if (!sessionsSnapshot) sessionsSnapshot = window.IndexSnapshot.create();
    sessionsSnapshot.load(Object.keys(resources).map(function (name) {
      return {
        key: name,
        url: apiUrl('/api/sessions/' + name, qs),
        apply: function (part) {
          if (generation !== sessionsRequestGeneration) return;
          var error = document.querySelector('[data-resource-error="' + name + '"]');
          if (error) error.remove();
          resources[name](part);
        },
        error: function (err, retry) {
          if (generation === sessionsRequestGeneration) showListResourceError(name, err, retry);
        }
      };
    }));
  }

  function showListResourceError(name, err, retry) {
    var previous = document.querySelector('[data-resource-error="' + name + '"]');
    if (previous) previous.remove();
    var target = name === 'rows' ? document.querySelector('.table-card .data-table tbody')
      : name === 'summary' ? document.querySelector('.page-head__stats')
      : name === 'active-filters' ? document.querySelector('.active-filters')
      : document.getElementById('session-filter-form');
    if (!target) return;
    var error = document.createElement(name === 'rows' ? 'tr' : 'div');
    error.setAttribute('data-resource-error', name);
    var content = error;
    if (name === 'rows') {
      content = document.createElement('td');
      content.colSpan = 13;
      error.appendChild(content);
      var count = document.querySelector('.active-filters__count');
      if (count && /Loading|Searching/.test(count.textContent)) count.textContent = 'Sessions unavailable';
    }
    content.setAttribute('role', 'alert');
    content.appendChild(document.createTextNode('Unable to load ' + name + ' (' + (err.message || 'Request failed') + '). '));
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn';
    button.textContent = 'Retry';
    button.addEventListener('click', function () {
      button.disabled = true;
      retry().then(function () { button.disabled = false; });
    });
    content.appendChild(button);
    if (name === 'options') target.appendChild(error);
    else target.replaceChildren(error);
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
        // 中文说明：沿用表单中 API 确认的实际页大小，不能用常用下拉选项覆盖合法的非选项值。
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
    if (target.closest('button, input, select, textarea, summary')) return;

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
