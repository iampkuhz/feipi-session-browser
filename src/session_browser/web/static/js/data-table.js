/**
 * data-table.js — 可选的表格增强 helper
 *
 * 功能：列排序、行选中、分页、行过滤
 * 不侵入业务页面已有的筛选/排序逻辑（如 sessions.html / projects.html 的内联 JS）。
 * 通过 data 属性或显式调用启用。
 *
 * 启用方式：
 *   <script src="/static/js/data-table.js"></script>
 *   <table id="my-table" data-table-enhanced> ... </table>
 *
 * 或在页面中直接调用：
 *   DataTable.init('#my-table', { sortable: true, selectable: true, pageSize: 20 });
 */
(function () {
  'use strict';

  var DataTable = {};

  /* ──────────────────────────────────────────────
     排序
     ────────────────────────────────────────────── */
  DataTable.sort = function (table, colIndex, direction) {
    var tbody = table.querySelector('tbody');
    if (!tbody) return;
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    var type = _getColumnType(table, colIndex);

    rows.sort(function (a, b) {
      var va = _getCellText(a, colIndex, type);
      var vb = _getCellText(b, colIndex, type);
      if (va === vb) return 0;
      var cmp = (va < vb) ? -1 : 1;
      return direction === 'ascending' ? cmp : -cmp;
    });

    for (var i = 0; i < rows.length; i++) {
      tbody.appendChild(rows[i]);
    }
  };

  DataTable.bindSortHeaders = function (table) {
    var headers = table.querySelectorAll('th.sortable');
    for (var i = 0; i < headers.length; i++) {
      (function (th) {
        th.addEventListener('click', function () {
          var current = th.getAttribute('aria-sort') || 'none';
          var next = current === 'ascending' ? 'descending' : 'ascending';
          // 重置所有 header
          for (var j = 0; j < headers.length; j++) {
            headers[j].removeAttribute('aria-sort');
          }
          th.setAttribute('aria-sort', next);
          DataTable.sort(table, _getColIndex(th), next);
        });
        th.setAttribute('tabindex', '0');
        th.setAttribute('role', 'columnheader');
        th.setAttribute('aria-sort', 'none');
        th.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            th.click();
          }
        });
      })(headers[i]);
    }
  };

  /* ──────────────────────────────────────────────
     选中
     ────────────────────────────────────────────── */
  DataTable.getSelectedRows = function (table) {
    return Array.prototype.slice.call(table.querySelectorAll('tbody tr.selected'));
  };

  DataTable.clearSelection = function (table) {
    var selected = table.querySelectorAll('tbody tr.selected');
    for (var i = 0; i < selected.length; i++) {
      selected[i].classList.remove('selected');
    }
    var allCb = table.querySelectorAll('.row-select-cell input[type="checkbox"]');
    for (var i = 0; i < allCb.length; i++) {
      allCb[i].checked = false;
    }
  };

  DataTable.bindSelection = function (table) {
    // 点击行切换选中
    var tbody = table.querySelector('tbody');
    if (!tbody) return;
    tbody.addEventListener('click', function (e) {
      var row = e.target.closest('tr');
      if (!row || row.parentElement !== tbody) return;
      row.classList.toggle('selected');
    });
  };

  /* ──────────────────────────────────────────────
     分页（纯前端，不改变服务端逻辑）
     ────────────────────────────────────────────── */
  DataTable.paginate = function (table, page, pageSize) {
    var tbody = table.querySelector('tbody');
    if (!tbody) return;
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    var start = (page - 1) * pageSize;
    var end = start + pageSize;
    for (var i = 0; i < rows.length; i++) {
      rows[i].style.display = (i >= start && i < end) ? '' : 'none';
    }
  };

  DataTable.renderPagination = function (container, totalRows, currentPage, pageSize, onPageChange) {
    var totalPages = Math.ceil(totalRows / pageSize) || 1;
    if (currentPage < 1) currentPage = 1;
    if (currentPage > totalPages) currentPage = totalPages;

    container.innerHTML = '';
    container.className = 'data-table__pagination';

    // info
    var info = document.createElement('span');
    info.className = 'data-table__pagination-info';
    var start = (currentPage - 1) * pageSize + 1;
    var end = Math.min(currentPage * pageSize, totalRows);
    info.textContent = start + '-' + end + ' / ' + totalRows;
    container.appendChild(info);

    // controls
    var controls = document.createElement('div');
    controls.className = 'data-table__pagination-controls';

    // prev
    var prev = document.createElement('button');
    prev.className = 'data-table__page-btn';
    prev.textContent = '‹';
    prev.disabled = currentPage <= 1;
    prev.addEventListener('click', function () { onPageChange(currentPage - 1); });
    controls.appendChild(prev);

    // page buttons (show max 7)
    var pages = _getPageRange(currentPage, totalPages);
    for (var i = 0; i < pages.length; i++) {
      (function (p) {
        if (p === '...') {
          var ell = document.createElement('span');
          ell.className = 'data-table__page-ellipsis';
          ell.textContent = '…';
          controls.appendChild(ell);
        } else {
          var btn = document.createElement('button');
          btn.className = 'data-table__page-btn' + (p === currentPage ? ' active' : '');
          btn.textContent = p;
          btn.addEventListener('click', function () { onPageChange(p); });
          controls.appendChild(btn);
        }
      })(pages[i]);
    }

    // next
    var next = document.createElement('button');
    next.className = 'data-table__page-btn';
    next.textContent = '›';
    next.disabled = currentPage >= totalPages;
    next.addEventListener('click', function () { onPageChange(currentPage + 1); });
    controls.appendChild(next);

    container.appendChild(controls);
  };

  /* ──────────────────────────────────────────────
     行内过滤
     ────────────────────────────────────────────── */
  DataTable.filterRows = function (table, query) {
    var tbody = table.querySelector('tbody');
    if (!tbody) return;
    var q = (query || '').toLowerCase();
    var rows = tbody.querySelectorAll('tr');
    var visibleCount = 0;
    for (var i = 0; i < rows.length; i++) {
      var text = rows[i].textContent.toLowerCase();
      var match = !q || text.indexOf(q) !== -1;
      rows[i].style.display = match ? '' : 'none';
      if (match) visibleCount++;
    }
    return visibleCount;
  };

  /* ──────────────────────────────────────────────
     初始化
     ────────────────────────────────────────────── */
  DataTable.init = function (selector, opts) {
    opts = opts || {};
    var tables;
    if (typeof selector === 'string') {
      tables = document.querySelectorAll(selector);
    } else if (selector instanceof HTMLElement) {
      tables = [selector];
    } else {
      tables = [selector];
    }

    for (var i = 0; i < tables.length; i++) {
      (function (table) {
        if (opts.sortable !== false) {
          DataTable.bindSortHeaders(table);
        }
        if (opts.selectable) {
          DataTable.bindSelection(table);
        }
        if (opts.pageSize) {
          table._dtPageSize = opts.pageSize;
          DataTable.paginate(table, 1, opts.pageSize);
        }
      })(tables[i]);
    }
    return DataTable;
  };

  /* ──────────────────────────────────────────────
     自动扫描
     ────────────────────────────────────────────── */
  function autoInit() {
    var tables = document.querySelectorAll('table[data-table-enhanced]');
    for (var i = 0; i < tables.length; i++) {
      DataTable.init(tables[i], { sortable: true });
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

  /* ──────────────────────────────────────────────
     内部工具函数
     ────────────────────────────────────────────── */
  function _getColIndex(th) {
    // th.cellIndex gives column index
    return th.cellIndex;
  }

  function _getColumnType(table, colIndex) {
    var th = table.querySelector('thead tr th:nth-child(' + (colIndex + 1) + ')');
    if (th && th.classList.contains('numeric')) return 'numeric';
    return 'text';
  }

  function _getCellText(row, colIndex, type) {
    var cell = row.querySelector('td:nth-child(' + (colIndex + 1) + ')');
    if (!cell) return '';
    // Prefer data-sort-value if present (avoids parsing formatted display text)
    var sortValue = cell.getAttribute('data-sort-value');
    if (sortValue !== null) {
      var num = parseFloat(sortValue);
      return type === 'numeric' ? (isNaN(num) ? Number.NEGATIVE_INFINITY : num) : sortValue.toLowerCase();
    }
    var raw = (cell.textContent || '').trim();
    if (type === 'numeric') {
      // Handle K/M/B suffixes: "1.2M" → 1200000
      var suffixMatch = raw.match(/^([+-]?\d+\.?\d*)\s*([kKmMbB])?$/);
      if (suffixMatch) {
        var val = parseFloat(suffixMatch[1]);
        var suffix = (suffixMatch[2] || '').toLowerCase();
        if (suffix === 'k') val *= 1000;
        else if (suffix === 'm') val *= 1000000;
        else if (suffix === 'b') val *= 1000000000;
        return val;
      }
      var num = parseFloat(raw.replace(/[^0-9.\-]/g, ''));
      return isNaN(num) ? Number.NEGATIVE_INFINITY : num;
    }
    return raw.toLowerCase();
  }

  function _getPageRange(current, total) {
    if (total <= 7) {
      var all = [];
      for (var i = 1; i <= total; i++) all.push(i);
      return all;
    }
    var pages = [];
    var start = Math.max(2, current - 1);
    var end = Math.min(total - 1, current + 1);
    pages.push(1);
    if (start > 2) pages.push('...');
    for (var i = start; i <= end; i++) pages.push(i);
    if (end < total - 1) pages.push('...');
    pages.push(total);
    return pages;
  }

  // 暴露全局
  window.DataTable = DataTable;
})();
