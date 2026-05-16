/**
 * keyboard.js — 键盘快捷键与焦点模型
 *
 * 快捷键映射：
 *   Esc     关闭 inspector / modal / 收起展开项
 *   /       聚焦当前页搜索输入框
 *   j       下移高亮行（表格 / 列表）
 *   k       上移高亮行
 *   Enter   打开当前高亮行详情
 *
 * 约束：
 *   - 在 input / textarea / select 内时，j/k/Esc 不拦截（允许原生行为）。
 *   - / 快捷键仅在未聚焦输入框时触发。
 *   - 与已有 inspector.js 的 Esc 关闭协作，不重复消费。
 */
(function () {
  'use strict';

  var Keyboard = {};

  /* ──────────────────────────────────────────────
     工具函数
     ────────────────────────────────────────────── */

  /** 判断当前焦点是否在可编辑元素内 */
  function isEditableTarget(el) {
    if (!el) return false;
    var tag = el.tagName;
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
  }

  /** 获取当前页面中"活跃"的表格（优先选可见且含多行的） */
  function getActiveTable() {
    // 如果 Profile tab 活跃，优先返回 Profile 表格
    var profileTab = document.querySelector('[data-tab="profile"].active');
    if (profileTab) {
      var profileTable = getProfileTable();
      if (profileTable) return profileTable;
    }
    // 优先使用 data-table-enhanced 标记的表格
    var tables = document.querySelectorAll('table[data-table-enhanced]');
    for (var i = 0; i < tables.length; i++) {
      if (isTableVisible(tables[i])) return tables[i];
    }
    // 退而求其次：任意含 tbody 的可见表格
    var allTables = document.querySelectorAll('table');
    for (var i = 0; i < allTables.length; i++) {
      if (isTableVisible(allTables[i]) && allTables[i].querySelector('tbody tr')) {
        return allTables[i];
      }
    }
    return null;
  }

  /** 获取 Profile 表格（LLM Calls table，lazy-loaded） */
  function getProfileTable() {
    var profileContent = document.getElementById('profile');
    if (!profileContent || !profileContent.dataset.loaded) return null;
    var table = profileContent.querySelector('table.profile-call-index');
    if (table && isTableVisible(table)) return table;
    return null;
  }

  function isTableVisible(table) {
    return !!(table && table.offsetParent !== null);
  }

  /** 获取当前页面中可见的搜索输入框 */
  function getSearchInput() {
    // 按页面上下文优先匹配
    var candidates = [
      // search.html 的搜索表单
      'input[name="q"]',
      // sessions / dashboard
      '#session-search',
      // projects / dashboard
      '#project-search',
      // 通用：带 filter-bar__input--search 的第一个可见 input
      '.filter-bar__input--search'
    ];
    for (var i = 0; i < candidates.length; i++) {
      var els = document.querySelectorAll(candidates[i]);
      for (var j = 0; j < els.length; j++) {
        if (els[j].offsetParent !== null && els[j].type !== 'hidden') {
          return els[j];
        }
      }
    }
    return null;
  }

  /* ──────────────────────────────────────────────
     行高亮 (keyboard-focus)
     ────────────────────────────────────────────── */

  var _highlightedRow = null;

  function clearHighlight() {
    if (_highlightedRow) {
      _highlightedRow.classList.remove('keyboard-focus');
      _highlightedRow = null;
    }
  }

  function highlightRow(row) {
    clearHighlight();
    if (!row) return;
    row.classList.add('keyboard-focus');
    _highlightedRow = row;
    // 确保行在视口内
    row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function getNavigableRows(table) {
    if (!table) return [];
    var tbody = table.querySelector('tbody');
    if (!tbody) return [];
    var rows = [];
    var allRows = tbody.querySelectorAll('tr');
    for (var i = 0; i < allRows.length; i++) {
      // 只纳入可见行
      if (allRows[i].offsetParent !== null) {
        rows.push(allRows[i]);
      }
    }
    return rows;
  }

  /** 下移一行 */
  Keyboard.navigateNext = function () {
    var table = getActiveTable();
    if (!table) return;
    var rows = getNavigableRows(table);
    if (!rows.length) return;

    var idx = _highlightedRow ? rows.indexOf(_highlightedRow) : -1;
    idx = (idx + 1) % rows.length;
    highlightRow(rows[idx]);
  };

  /** 上移一行 */
  Keyboard.navigatePrev = function () {
    var table = getActiveTable();
    if (!table) return;
    var rows = getNavigableRows(table);
    if (!rows.length) return;

    var idx = _highlightedRow ? rows.indexOf(_highlightedRow) : -1;
    idx = idx <= 0 ? rows.length - 1 : idx - 1;
    highlightRow(rows[idx]);
  };

  /** 打开当前高亮行 */
  Keyboard.openSelected = function () {
    if (!_highlightedRow) return;
    // LLM call row → open LLM Call Inspector
    if (_highlightedRow.classList.contains('llm-call-row')) {
      if (typeof window.openLLMInspector === 'function') {
        window.openLLMInspector(_highlightedRow);
        return;
      }
    }
    // 查找行内的第一个 <a> 链接，模拟点击
    var link = _highlightedRow.querySelector('a[href]');
    if (link) {
      link.click();
      return;
    }
    // 没有链接：如果存在 Inspector 且行有 data 属性，尝试打开
    if (typeof window.openInspector === 'function') {
      var title = _highlightedRow.textContent.trim().substring(0, 60);
      window.openInspector({
        title: title,
        metadata: extractRowMetadata(_highlightedRow),
        summary: title
      });
    }
  };

  /** 从行 data 属性提取元数据（供 Inspector 使用） */
  function extractRowMetadata(row) {
    var meta = {};
    var dataset = row.dataset;
    var labelMap = {
      sessionId: 'Session ID',
      agent: 'Agent',
      model: 'Model',
      project: 'Project',
      title: 'Title',
      totalTokens: 'Total Tokens',
      endedAt: 'Ended At',
      callIdx: 'Call #',
      scope: 'Scope',
      round: 'Round'
    };
    for (var key in labelMap) {
      if (dataset[key]) {
        meta[labelMap[key]] = { value: dataset[key], mono: true };
      }
    }
    return meta;
  }

  /* ──────────────────────────────────────────────
     Esc 处理
     ────────────────────────────────────────────── */

  Keyboard.handleEscape = function () {
    // 1. 关闭 Inspector
    if (document.body.classList.contains('inspector-open')) {
      if (typeof window.closeInspector === 'function') {
        window.closeInspector();
        return;
      }
    }
    // 2. 关闭 modal（如有）
    var openModal = document.querySelector('.modal-open, [role="dialog"]:not([hidden])');
    if (openModal) {
      var closeBtn = openModal.querySelector('[aria-label*="关闭"], .modal-close, [data-dismiss="modal"]');
      if (closeBtn) { closeBtn.click(); return; }
      openModal.classList.remove('modal-open');
      return;
    }
    // 3. 收起展开的 round / collapse
    var expanded = document.querySelector('.round.expanded');
    if (expanded) {
      expanded.classList.remove('expanded');
      return;
    }
    // 4. 清除行高亮
    clearHighlight();
  };

  /* ──────────────────────────────────────────────
     聚焦搜索
     ────────────────────────────────────────────── */

  Keyboard.focusSearch = function () {
    var input = getSearchInput();
    if (input) {
      input.focus();
      // 选中全部文本，方便快速替换
      input.select();
    }
  };

  /* ──────────────────────────────────────────────
     全局 keydown 监听
     ────────────────────────────────────────────── */

  document.addEventListener('keydown', function (e) {
    var target = e.target;

    // Esc: 始终处理（即使在不元素内也要尝试关闭面板）
    if (e.key === 'Escape') {
      Keyboard.handleEscape();
      return;
    }

    // 在可编辑元素内，不拦截其他快捷键
    if (isEditableTarget(target)) {
      return;
    }

    // / → 聚焦搜索
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      Keyboard.focusSearch();
      return;
    }

    // j → 下一行
    if (e.key === 'j' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      Keyboard.navigateNext();
      return;
    }

    // k → 上一行
    if (e.key === 'k' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault();
      Keyboard.navigatePrev();
      return;
    }

    // Enter → 打开选中行
    if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (_highlightedRow) {
        e.preventDefault();
        Keyboard.openSelected();
      }
      return;
    }
  });

  /* ──────────────────────────────────────────────
     全局 API
     ────────────────────────────────────────────── */

  window.Keyboard = Keyboard;

})();
