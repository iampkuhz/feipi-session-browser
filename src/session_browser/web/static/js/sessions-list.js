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
 *   - token-tooltip: augment token cells with structured tooltip on hover.
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

  // ── Initialization: augment DOM for data-action delegation ──────────────

  function init() {
    augmentSortableHeaders();
    removeInlinePageSizeHandler();
    bindFormSubmit();
    bindFilterClear();
    bindTokenTooltips();

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
   * Handle prev/next page link clicks.
   * Listens on document for links matching prev/next pagination patterns.
   */
  document.addEventListener('click', function (event) {
    var target = event.target;
    var link = target.closest ? target.closest('a') : null;
    if (!link) return;

    // Check if it's a prev/next pagination link
    if (link.textContent.trim().match(/^(Previous|Next|‹|›)/i) ||
        link.getAttribute('aria-label') === 'Previous page' ||
        link.getAttribute('aria-label') === 'Next page') {
      var container = closest(link, '.sessions-table-footer');
      if (container) {
        event.preventDefault();
        var href = link.getAttribute('href');
        if (href) {
          // Dispatch page-change event before navigating
          document.dispatchEvent(new CustomEvent('page-change', {
            detail: { href: href }
          }));
          window.location.href = href;
        }
      }
    }

    // Row click navigation (only if no data-action is set)
    if (link.closest('.sessions-row') && !link.getAttribute('data-action')) {
      // Let link navigate naturally
      return;
    }
  });

  /**
   * Handle page-size select change.
   * Navigates to the selected page-size URL.
   */
  document.addEventListener('change', function (event) {
    var sel = event.target;
    if (sel.classList.contains('sessions-footer-page-size__select')) {
      var val = sel.value;
      if (val) {
        document.dispatchEvent(new CustomEvent('page-size-change', {
          detail: { pageSize: val }
        }));
        window.location.href = val;
      }
    }
  });

  // ── Row click navigation ────────────────────────────────────────────────

  document.addEventListener('click', function (event) {
    var target = event.target;
    var row = target.closest ? target.closest('.sessions-row') : null;
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

  // ── Token tooltip augmentation ─────────────────────────────────────────

  /**
   * Augment token cells with structured tooltip on hover.
   * The CSS handles show/hide via .sessions-token-total:hover .sessions-token-tooltip.
   * This function ensures the tooltip element exists with structured content.
   */
  function bindTokenTooltips() {
    var tokenTotals = document.querySelectorAll('.sessions-token-total');
    for (var i = 0; i < tokenTotals.length; i++) {
      augmentTokenTooltip(tokenTotals[i]);
    }
  }

  /**
   * Add tooltip to a token-total cell if not already present.
   */
  function augmentTokenTooltip(container) {
    if (container.querySelector('.sessions-token-tooltip')) return;

    var row = closest(container, '.sessions-row');
    if (!row) return;

    var totalTokens = parseInt(row.dataset.totalTokens, 10) || 0;
    var rounds = row.dataset.rounds || '0';
    var tools = row.dataset.toolCount || '0';
    var duration = row.dataset.duration || '0';

    // Calculate breakdown from row data
    // The token bar in the template already shows fresh/cache/output percentages
    // We build the tooltip content from the cell's own data
    var totalEl = container.querySelector('.sessions-token-total__value');
    var totalText = totalEl ? totalEl.textContent.trim() : String(totalTokens);

    // Build tooltip HTML
    var tooltip = document.createElement('div');
    tooltip.className = 'sessions-token-tooltip';
    tooltip.setAttribute('aria-hidden', 'true');
    tooltip.innerHTML =
      '<div class="sessions-token-tooltip__title">Token Breakdown</div>' +
      '<div class="sessions-token-tooltip__row">' +
        '<span class="sessions-token-tooltip__label">' +
          '<span class="sessions-token-tooltip__dot sessions-token-tooltip__dot--fresh"></span> Fresh' +
        '</span>' +
        '<span class="sessions-token-tooltip__value sessions-token-tooltip__fresh-val">—</span>' +
      '</div>' +
      '<div class="sessions-token-tooltip__row">' +
        '<span class="sessions-token-tooltip__label">' +
          '<span class="sessions-token-tooltip__dot sessions-token-tooltip__dot--cache"></span> Cache' +
        '</span>' +
        '<span class="sessions-token-tooltip__value sessions-token-tooltip__cache-val">—</span>' +
      '</div>' +
      '<div class="sessions-token-tooltip__row">' +
        '<span class="sessions-token-tooltip__label">' +
          '<span class="sessions-token-tooltip__dot sessions-token-tooltip__dot--out"></span> Output' +
        '</span>' +
        '<span class="sessions-token-tooltip__value sessions-token-tooltip__out-val">—</span>' +
      '</div>' +
      '<div class="sessions-token-tooltip__sep"></div>' +
      '<div class="sessions-token-tooltip__row sessions-token-tooltip__total">' +
        '<span class="sessions-token-tooltip__label">Total</span>' +
        '<span class="sessions-token-tooltip__value">' + totalText + '</span>' +
      '</div>' +
      '<div class="sessions-token-tooltip__sep"></div>' +
      '<div class="sessions-token-tooltip__row">' +
        '<span class="sessions-token-tooltip__label">Rounds</span>' +
        '<span>' + rounds + '</span>' +
      '</div>' +
      '<div class="sessions-token-tooltip__row">' +
        '<span class="sessions-token-tooltip__label">Tools</span>' +
        '<span>' + tools + '</span>' +
      '</div>' +
      '<div class="sessions-token-tooltip__row">' +
        '<span class="sessions-token-tooltip__label">Duration</span>' +
        '<span>' + duration + 's</span>' +
      '</div>';

    container.appendChild(tooltip);
  }

  // ── Auto-init on DOM ready ──────────────────────────────────────────────

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
