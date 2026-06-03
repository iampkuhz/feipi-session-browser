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
    return new URLSearchParams(new FormData(form));
  }

  /**
   * Navigate to /sessions with the given params object.
   */
  function navigate(params) {
    var qs = new URLSearchParams();
    for (var k in params) {
      if (params[k] !== '' && params[k] != null) {
        qs.set(k, params[k]);
      }
    }
    var url = '/sessions' + (qs.toString() ? '?' + qs.toString() : '');
    window.location.href = url;
  }

  /**
   * Submit the filter form (server-side navigation).
   */
  function submitFilter() {
    var form = document.getElementById('session-filter-form');
    if (form) form.submit();
  }

  /**
   * Handle browser back/forward: full reload since state is server-side.
   */
  window.addEventListener('popstate', function () {
    window.location.reload();
  });

  // ── Real-time client-side search ──────────────────────────────────────

  /**
   * Filter visible table rows based on search input value.
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
    var countEl = document.querySelector('[data-session-match-count]');
    if (countEl) countEl.textContent = visibleCount + ' matching sessions';
  }

  function bindRealtimeSearch() {
    var searchInput = document.getElementById('session-search');
    if (!searchInput) return;

    searchInput.addEventListener('input', function () {
      filterVisibleRows(searchInput.value);
    });

    // Prevent form submit on Enter — just filter client-side
    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        filterVisibleRows(searchInput.value);
      }
    });

    // Apply saved search on load
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
      // Submit form for server-side filter
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
    bindPagination();
    bindRealtimeSearch();
    bindSelectAutoSubmit();
    setupTokenTooltips();

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
    var sortBtns = document.querySelectorAll('.sessions-th__sort-btn');
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

  /**
   * Bind filter form submit handler.
   * Resets to page 1 on submit.
   */
  function bindFormSubmit() {
    var form = document.getElementById('session-filter-form');
    if (!form) return;

    form.addEventListener('submit', function (e) {
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
      // Let form submit naturally (GET /sessions?...)
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
   * Fetch a page via AJAX and replace table body + pagination.
   * Uses X-Requested-With header to trigger partial response from server.
   * pushState only happens AFTER successful response — never before.
   * On failure, does full reload to target URL — never leaves a loading/empty table.
   * After replacing pagination, re-augments sortable headers so new DOM has data-action.
   */
  function fetchPage(params) {
    var qs = new URLSearchParams();
    for (var k in params) {
      if (params[k] !== '' && params[k] != null) {
        qs.set(k, params[k]);
      }
    }
    var url = '/sessions' + (qs.toString() ? '?' + qs.toString() : '');

    // Locate tbody using selector matching ui.table_card macro output:
    // <section class="card table-card"> > .table-wrap > table.data-table > tbody
    var tbody = document.querySelector('.table-card .data-table tbody');
    if (!tbody) {
      // Fallback: full navigation if target not found
      window.location.href = url;
      return;
    }

    // Show loading state
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:24px;color:var(--text-subtle);">Loading...</td></tr>';

    fetch(url, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(function (response) {
      if (!response.ok) {
        throw new Error('HTTP ' + response.status);
      }
      return response.text();
    })
    .then(function (html) {
      // Parse response: #sessions-ajax-response contains tbody + pagination
      var parser = new DOMParser();
      var doc = parser.parseFromString(html, 'text/html');
      var ajaxResponse = doc.getElementById('sessions-ajax-response');
      if (!ajaxResponse) {
        throw new Error('Missing #sessions-ajax-response in AJAX response');
      }

      // Extract tbody content from AJAX response
      var newTbody = ajaxResponse.querySelector('tbody');
      if (!newTbody) {
        console.error('AJAX pagination fallback: missing tbody in response');
        window.location.href = url;
        return;
      }

      // Validate: response must contain at least one data row
      var rows = newTbody.querySelectorAll('tr');
      if (rows.length === 0) {
        console.error('AJAX pagination fallback: no rows in response tbody');
        window.location.href = url;
        return;
      }

      // Validate: response must contain pagination element
      var newPagination = ajaxResponse.querySelector('#ajax-pagination');
      if (!newPagination) {
        console.error('AJAX pagination fallback: missing #ajax-pagination in response');
        window.location.href = url;
        return;
      }

      tbody.innerHTML = newTbody.innerHTML;

      // Replace pagination — page input value comes from server response
      var oldPagination = document.getElementById('ajax-pagination');
      if (oldPagination) {
        oldPagination.innerHTML = newPagination.innerHTML;
      } else if (tbody) {
        // Create pagination container if it doesn't exist
        var tableCard = tbody.closest('.table-card') || tbody.closest('.card');
        if (tableCard) {
          var paginationDiv = document.createElement('div');
          paginationDiv.id = 'ajax-pagination';
          paginationDiv.innerHTML = newPagination.innerHTML;
          tableCard.appendChild(paginationDiv);
        }
      }

      // pushState ONLY after successful response and DOM update
      window.history.pushState({ ajax: true }, '', url);

      // Re-augment sortable headers on new DOM so data-action is present
      augmentSortableHeaders();

      // Sync hidden page_size with the new select from AJAX response
      syncPageSizeHidden();

      // Re-bind token tooltip positioning for new rows
      setupTokenTooltips();
    })
    .catch(function (err) {
      console.error('AJAX pagination fallback:', err.message || err);
      // Safe fallback: direct full-page navigation without restore attempt.
      // Restoring originalTbodyHTML can fail silently and leave the page
      // stuck in "Loading..." state when the DOM is in an unexpected state.
      window.location.href = url;
    });
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

  document.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || target.nodeType !== 1) return;
    var row = target.closest('.sessions-row');
    if (!row) return;

    // Don't navigate if clicking a link inside the row
    if (target.closest('a')) return;

    // Dispatch custom event for external handlers
    row.dispatchEvent(new CustomEvent('session-row-click', {
      bubbles: true,
      detail: {
        agent: row.dataset.agent,
        sessionId: row.dataset.sessionId,
        row: row
      }
    }));

    var agent = row.dataset.agent;
    var sessionId = row.dataset.sessionId;
    if (agent && sessionId) {
      window.location.href = '/sessions/' + agent + '/' + sessionId;
    }
  });

  // ── Auto-init on DOM ready ──────────────────────────────────────────────

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
