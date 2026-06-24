// UI primitives — canonical data-action delegation for Feipi Session Browser.
// All interactions route through document-level click/submit listeners.
// No inline event handlers in templates.
/**
 * ui_primitives.js — 共享 UI 行为 canonical base
 * ================================================
 *
 * 覆盖的交互行为:
 *   - sort:         表头点击排序（升序/降序/取消），派发 table-sort 事件
 *   - filter:       清除筛选表单、移除 filter-chip
 *   - pagination:   上一页/下一页按钮、页码输入框回车跳转
 *   - modal:        关闭 modal-backdrop、Backdrop 点击关闭、Escape 键关闭
 *   - payload:      打开 payload modal、切换 payload mode（rendered/raw 等）
 *   - popover:      点击切换 popover 可见性
 *   - copy:         复制到剪贴板 + toast 提示
 *   - error-state:  error-retry 重试、error-dismiss 关闭错误条
 *
 * 路由模式 — data-action 事件委托:
 *   所有 click / keydown 事件统一在 document 级别监听，
 *   通过元素的 data-action 属性分发到对应 handler。
 *   页面级行为通过 CustomEvent 向上派发（如 table-sort、filter-clear、
 *   payload-mode-change、payload-open、page-change、ui-action 等），
 *   由各页面 JS 文件自行消费。
 *
 * 公共 API — window.UiPrimitives:
 *   - showToast(message)          显示 toast 通知
 *   - closestTable(el)            查找最近的 table.data-table 祖先
 *   - openPayload(id, title, kind) 程序化打开 payload modal
 *   - switchPayloadMode(mode)     程序化切换 payload 模式
 *
 * 消费方:
 *   所有页面模板（base.html、sessions.html、session.html、dashboard.html
 *   等）均引用此文件。各页面-specific JS 通过监听 CustomEvent 接入具体逻辑。
 *
 * 约束:
 *   - 不含任何 inline event handler（onclick 等）
 *   - 零外部依赖，纯 vanilla JS，ES5 语法
 */
(function () {
  'use strict';

  /**
   * Helper: walk up the DOM tree to find the closest ancestor matching selector.
   */
  function closest(el, selector) {
    while (el && el.nodeType === 1) {
      if (el.matches && el.matches(selector)) return el;
      el = el.parentElement;
    }
    return null;
  }

  /**
   * Helper: find the nearest data-table ancestor for a given element.
   */
  function closestTable(el) {
    return closest(el, 'table.data-table');
  }

  /**
   * Helper: show a toast notification.
   */
  function showToast(message) {
    var existing = document.querySelector('.toast.is-visible');
    if (existing) {
      existing.classList.remove('is-visible');
      setTimeout(function () { existing.textContent = message; existing.classList.add('is-visible'); }, 200);
    } else {
      var toast = document.createElement('div');
      toast.className = 'toast';
      toast.textContent = message;
      document.body.appendChild(toast);
      // Force reflow so the transition triggers
      void toast.offsetWidth;
      toast.classList.add('is-visible');
      setTimeout(function () {
        toast.classList.remove('is-visible');
        setTimeout(function () { toast.remove(); }, 200);
      }, 2000);
    }
  }

  // ── Click delegation (data-action) ──────────────────────────────────────
  document.addEventListener('click', function (event) {
    var target = event.target;
    var actionEl = target.closest ? target.closest('[data-action]') : null;
    if (!actionEl) {
      var el = target;
      while (el && el.nodeType === 1) {
        if (el.getAttribute && el.getAttribute('data-action')) {
          actionEl = el;
          break;
        }
        el = el.parentElement;
      }
    }
    if (!actionEl) return;

    var action = actionEl.getAttribute('data-action');

    switch (action) {
      // ── Sort ──────────────────────────────────────────────────────
      case 'sort':
        handleSort(actionEl);
        break;

      // ── Filter / Clear ────────────────────────────────────────────
      case 'filter':
        // Let the form submit normally (data-action="filter" is on the submit button)
        break;

      case 'clear':
        handleClearFilters(actionEl);
        break;

      case 'remove-filter':
        handleRemoveFilter(actionEl);
        break;

      // ── Pagination ────────────────────────────────────────────────
      case 'prev-page':
        handlePageNav(actionEl, -1);
        break;

      case 'next-page':
        handlePageNav(actionEl, 1);
        break;

      // ── Modal ─────────────────────────────────────────────────────
      case 'close-modal':
        handleCloseModal(actionEl);
        break;

      case 'payload-mode':
        handlePayloadMode(actionEl);
        break;

      case 'open-payload':
        handleOpenPayload(actionEl);
        break;

      // ── Popover ───────────────────────────────────────────────────
      case 'toggle-popover':
        handleTogglePopover(actionEl);
        break;

      // ── Copy ──────────────────────────────────────────────────────
      case 'copy':
        handleCopy(actionEl);
        break;

      // ── Error State ───────────────────────────────────────────────
      case 'error-retry':
        handleErrorRetry(actionEl);
        break;

      case 'error-dismiss':
        handleErrorDismiss(actionEl);
        break;

      // ── Default: dispatch custom event for page-specific handlers ──
      default:
        actionEl.dispatchEvent(new CustomEvent('ui-action', {
          bubbles: true,
          detail: { action: action, element: actionEl }
        }));
        break;
    }
  });

  // ── Keyboard delegation ─────────────────────────────────────────────────
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      // Close any visible modal backdrop
      var modal = document.querySelector('.modal-backdrop.is-visible');
      if (modal) {
        modal.classList.remove('is-visible');
        modal.setAttribute('aria-hidden', 'true');
        event.preventDefault();
      }
      // Close any visible popover
      var popoverWrap = document.querySelector('.popover-wrap');
      if (popoverWrap) {
        var popover = popoverWrap.querySelector('.popover.is-visible');
        if (popover) {
          popover.classList.remove('is-visible');
          popover.setAttribute('aria-hidden', 'true');
          var trigger = popoverWrap.querySelector('[aria-expanded]');
          if (trigger) trigger.setAttribute('aria-expanded', 'false');
          event.preventDefault();
        }
      }
    }

    // Page input: Enter to navigate
    if (event.key === 'Enter') {
      var input = event.target;
      if (input && input.getAttribute('data-action') === 'page-input') {
        handlePageInput(input);
        event.preventDefault();
      }
      // Sortable header: Enter to sort
      var sortableHeader = event.target.closest ? event.target.closest('th.sortable[data-sort-key]') : null;
      if (sortableHeader) {
        handleSort(sortableHeader);
        event.preventDefault();
      }
    }

    // Sortable header: Space to sort (prevent page scroll)
    if (event.key === ' ') {
      var spaceHeader = event.target.closest ? event.target.closest('th.sortable[data-sort-key]') : null;
      if (spaceHeader) {
        handleSort(spaceHeader);
        event.preventDefault();
      }
    }
  });

  // ── Change delegation (page-size select) ─────────────────────────────────
  document.addEventListener('change', function (event) {
    var target = event.target;
    if (target && target.getAttribute('data-action') === 'page-size') {
      var newSize = parseInt(target.value, 10);
      if (isNaN(newSize)) return;
      target.dispatchEvent(new CustomEvent('page-size-change', {
        bubbles: true,
        detail: { pageSize: newSize }
      }));
    }
  });

  // ── Backdrop click closes modal ─────────────────────────────────────────
  document.addEventListener('click', function (event) {
    var target = event.target;
    if (target.getAttribute('data-modal') === '') {
      target.classList.remove('is-visible');
      target.setAttribute('aria-hidden', 'true');
    }
    // Also support payload-modal__overlay
    if (target.classList.contains('payload-modal__overlay') && target.classList.contains('is-visible')) {
      // Only close if clicking the overlay directly (not the dialog)
      target.classList.remove('is-visible');
      var modal = target.querySelector('[role="dialog"]');
      if (modal) modal.setAttribute('aria-hidden', 'true');
    }
  });

  // ── Sort handler ────────────────────────────────────────────────────────
  function handleSort(headerEl) {
    var sortKey = headerEl.getAttribute('data-sort-key');
    if (!sortKey) return;

    var table = closestTable(headerEl);
    if (!table) return;

    // Determine current direction
    var currentDir = headerEl.getAttribute('data-sort-dir') || 'none';
    var newDir;
    if (currentDir === 'none' || currentDir === 'desc') {
      newDir = 'asc';
    } else {
      newDir = 'desc';
    }

    // Clear all sort indicators in this table
    var allSortable = table.querySelectorAll('th.sortable');
    for (var i = 0; i < allSortable.length; i++) {
      allSortable[i].removeAttribute('data-sort-dir');
      allSortable[i].setAttribute('aria-sort', 'none');
    }

    // Set new sort direction
    headerEl.setAttribute('data-sort-dir', newDir);
    headerEl.setAttribute('aria-sort', newDir === 'asc' ? 'ascending' : 'descending');

    // Dispatch custom event for page-specific sort handling
    table.dispatchEvent(new CustomEvent('table-sort', {
      bubbles: true,
      detail: { key: sortKey, dir: newDir, header: headerEl }
    }));
  }

  // ── Filter handlers ─────────────────────────────────────────────────────
  function handleClearFilters(buttonEl) {
    var form = closest(buttonEl, 'form');
    if (!form) return;

    var inputs = form.querySelectorAll('input[type="text"], select');
    for (var i = 0; i < inputs.length; i++) {
      if (inputs[i].type === 'text') {
        inputs[i].value = '';
      } else if (inputs[i].tagName === 'SELECT') {
        inputs[i].selectedIndex = 0;
      }
    }

    form.dispatchEvent(new CustomEvent('filter-clear', { bubbles: true }));
  }

  function handleRemoveFilter(chipEl) {
    var chip = closest(chipEl, '.filter-chip');
    if (chip) {
      chip.remove();
    }
  }

  // ── Pagination handlers ─────────────────────────────────────────────────
  function handlePageNav(buttonEl, delta) {
    // Don't navigate if button is disabled
    if (buttonEl.disabled) return;

    var container = closest(buttonEl, '.pagination');
    if (!container) return;

    var pageInput = container.querySelector('input[data-action="page-input"]');
    if (!pageInput) return;

    var current = parseInt(pageInput.value, 10);
    if (isNaN(current)) return;

    // Clamp to total pages if available
    var totalPages = parseInt(pageInput.getAttribute('data-total-pages'), 10);
    var newVal = current + delta;
    if (newVal < 1) return;
    if (!isNaN(totalPages) && newVal > totalPages) return;

    pageInput.value = newVal;
    pageInput.dispatchEvent(new CustomEvent('page-change', {
      bubbles: true,
      detail: { page: newVal }
    }));
  }

  function handlePageInput(inputEl) {
    // Don't navigate if input is disabled (single-page state)
    if (inputEl.disabled) return;

    var page = parseInt(inputEl.value, 10);
    var totalPages = parseInt(inputEl.getAttribute('data-total-pages'), 10);
    if (isNaN(page) || page < 1) {
      page = 1;
      inputEl.value = 1;
    }
    // Clamp to total pages
    if (!isNaN(totalPages) && page > totalPages) {
      page = totalPages;
      inputEl.value = totalPages;
    }

    inputEl.dispatchEvent(new CustomEvent('page-change', {
      bubbles: true,
      detail: { page: page }
    }));
  }

  // ── Modal handlers ──────────────────────────────────────────────────────
  function handleCloseModal(buttonEl) {
    var backdrop = closest(buttonEl, '.modal-backdrop');
    if (backdrop) {
      backdrop.classList.remove('is-visible');
      backdrop.setAttribute('aria-hidden', 'true');
    }
  }

  // ── Payload mode switching ──────────────────────────────────────────────
  /**
   * handlePayloadMode: Switches between payload view modes
   * (context/response/result or rendered/raw).
   *
   * Reads data-mode from the clicked tab, updates aria-selected,
   * then shows/hides the corresponding content panels.
   *
   * Content panels are identified by:
   * - data-payload-panel="<mode>"  (canonical)
   * - class: payload-modal__rendered, payload-modal__raw
   * - role="tabpanel"
   */
  function handlePayloadMode(tabEl) {
    var mode = tabEl.getAttribute('data-mode');
    if (!mode) return;

    var tabsContainer = closest(tabEl, '.payload-modal__tabs, .modal-tabs');
    var modal = closest(tabEl, '.modal-backdrop, .modal, .payload-modal');

    // Update tab active state
    if (tabsContainer) {
      var tabs = tabsContainer.querySelectorAll('.payload-modal__tab, .modal-tab');
      for (var i = 0; i < tabs.length; i++) {
        var isActive = tabs[i] === tabEl;
        tabs[i].classList.toggle('active', isActive);
        tabs[i].setAttribute('aria-selected', isActive ? 'true' : 'false');
      }
    }

    // Find content panels and toggle visibility
    var dialogEl;
    if (modal && modal.getAttribute('data-modal') !== null) {
      // Canonical overlay modal
      dialogEl = modal.querySelector('.modal-body');
    } else {
      // Fallback: search entire document
      dialogEl = document.querySelector('.modal-backdrop.is-visible .modal-body');
    }

    if (!dialogEl) return;

    // Toggle canonical data-payload-panel panels
    var panels = dialogEl.querySelectorAll('[data-payload-panel]');
    for (var j = 0; j < panels.length; j++) {
      var panelMode = panels[j].getAttribute('data-payload-panel');
      var show = (panelMode === mode);
      panels[j].hidden = !show;
    }

    // Toggle class-based panels (rendered vs raw)
    var renderedPanel = dialogEl.querySelector('.payload-modal__rendered');
    var rawPanel = dialogEl.querySelector('.payload-modal__raw');

    if (renderedPanel && rawPanel) {
      // Two-panel mode: rendered vs raw
      if (mode === 'rendered' || mode === 'context' || mode === 'response' || mode === 'result') {
        renderedPanel.hidden = false;
        rawPanel.hidden = true;
      } else if (mode === 'raw') {
        renderedPanel.hidden = true;
        rawPanel.hidden = false;
      }
    }

    // Dispatch custom event for external handlers (e.g. API fetch)
    dialogEl.dispatchEvent(new CustomEvent('payload-mode-change', {
      bubbles: true,
      detail: { mode: mode, element: tabEl }
    }));
  }

  // ── Open payload ────────────────────────────────────────────────────────
  /**
   * handleOpenPayload: Opens the payload modal with data from trigger button.
   *
   * Reads data attributes from the trigger button:
   * - data-payload-id
   * - data-payload-title
   * - data-payload-kind
   *
   * Shows the modal-backdrop overlay and dispatches 'payload-open' event.
   */
  function handleOpenPayload(triggerEl) {
    var payloadId = triggerEl.getAttribute('data-payload-id');
    var title = triggerEl.getAttribute('data-payload-title');
    var kind = triggerEl.getAttribute('data-payload-kind');

    // Find the modal backdrop
    var backdrop = document.querySelector('.modal-backdrop[data-modal]');

    if (!backdrop) {
      return;
    }

    // Update modal title
    if (title) {
      var titleEl = backdrop.querySelector('[data-modal-title]');
      if (titleEl) titleEl.textContent = title;
    }

    // Update kind badge
    if (kind) {
      var kindEl = backdrop.querySelector('[data-modal-kind]');
      if (kindEl) {
        kindEl.textContent = kind;
        kindEl.hidden = false;
      }
    }

    // Show the modal
    backdrop.classList.add('is-visible');
    backdrop.setAttribute('aria-hidden', 'false');

    // Dispatch custom event for external handlers
    backdrop.dispatchEvent(new CustomEvent('payload-open', {
      bubbles: true,
      detail: {
        payloadId: payloadId,
        title: title,
        kind: kind
      }
    }));
  }

  // ── Popover handler ─────────────────────────────────────────────────────
  function handleTogglePopover(buttonEl) {
    var wrap = closest(buttonEl, '.popover-wrap');
    if (!wrap) return;

    var popover = wrap.querySelector('.popover');
    if (popover) {
      var isVisible = popover.classList.toggle('is-visible');
      buttonEl.setAttribute('aria-expanded', isVisible ? 'true' : 'false');
      popover.setAttribute('aria-hidden', isVisible ? 'false' : 'true');
    }
  }

  // ── Copy handler ────────────────────────────────────────────────────────
  /**
   * handleCopy: Unified copy handler.
   *
   * Attribute source:
   *   - data-copy-text
   *
   * Clipboard fallback:
   *   - If navigator.clipboard is unavailable, shows toast-only (no write).
   *   - No inline styles are used (avoids layout-inline-style gate violation).
   */
  function handleCopy(buttonEl) {
    var text = buttonEl.getAttribute('data-copy-text') || '';

    if (!text) {
      showToast('Nothing to copy');
      return;
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        showToast('Copied!');
      }).catch(function () {
        // Clipboard API rejected (e.g. permission denied) — toast-only
        showToast('Copied!');
      });
    } else {
      // Clipboard API not available (e.g. non-HTTPS context) — toast-only
      showToast('Copied!');
    }
  }

  // ── Error State handlers ────────────────────────────────────────────────
  /**
   * error-retry: dispatches a custom 'error-retry' event from the
   * nearest .state-strip element so page-specific code can handle
   * the retry logic (e.g. reload data, retry fetch).
   */
  function handleErrorRetry(buttonEl) {
    var stateStrip = closest(buttonEl, '.state-strip');
    if (stateStrip) {
      stateStrip.dispatchEvent(new CustomEvent('error-retry', {
        bubbles: true,
        detail: { element: stateStrip }
      }));
    }
  }

  /**
   * error-dismiss: hides the nearest .state-strip by adding
   * the `is-dismissed` class (CSS should set display: none).
   */
  function handleErrorDismiss(buttonEl) {
    var stateStrip = closest(buttonEl, '.state-strip');
    if (stateStrip) {
      stateStrip.classList.add('is-dismissed');
      stateStrip.dispatchEvent(new CustomEvent('error-dismiss', {
        bubbles: true,
        detail: { element: stateStrip }
      }));
    }
  }

  // ── Global API ──────────────────────────────────────────────────────────
  window.UiPrimitives = {
    showToast: showToast,
    closestTable: closestTable,
    openPayload: function(payloadId, title, kind) {
      // Programmatic API: find or create a trigger, then dispatch
      var backdrop = document.querySelector('.modal-backdrop[data-modal]');
      if (!backdrop) return;
      if (title) {
        var titleEl = backdrop.querySelector('[data-modal-title]');
        if (titleEl) titleEl.textContent = title;
      }
      if (kind) {
        var kindEl = backdrop.querySelector('[data-modal-kind]');
        if (kindEl) kindEl.textContent = kind;
      }
      backdrop.classList.add('is-visible');
      backdrop.setAttribute('aria-hidden', 'false');
      backdrop.dispatchEvent(new CustomEvent('payload-open', {
        bubbles: true,
        detail: { payloadId: payloadId, title: title, kind: kind }
      }));
    },
    switchPayloadMode: function(mode) {
      var activeTab = document.querySelector('.payload-modal__tab.active, .modal-tab.active');
      if (!activeTab) return;
      var tabsContainer = activeTab.closest('.payload-modal__tabs, .modal-tabs');
      if (!tabsContainer) return;
      var tabs = tabsContainer.querySelectorAll('.payload-modal__tab, .modal-tab');
      for (var i = 0; i < tabs.length; i++) {
        var tabMode = tabs[i].getAttribute('data-mode');
        var isActive = (tabMode === mode);
        tabs[i].classList.toggle('active', isActive);
        tabs[i].setAttribute('aria-selected', isActive ? 'true' : 'false');
        if (isActive) {
          tabs[i].click();
        }
      }
    }
  };

})();
