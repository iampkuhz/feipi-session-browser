/**
 * glossary.js — Glossary page canonical JavaScript.
 *
 * Loaded via script_extra in glossary.html.
 *
 * Features:
 * - Search filtering with 150ms debounce
 * - Match count display
 * - Empty state toggle (class-based, no inline styles)
 * - Info-icon hover tooltips for metric labels
 */
(function () {
  'use strict';

  // ── Search filtering ──────────────────────────────────────

  var searchInput = document.getElementById('glossary-search');
  var matchCount = document.getElementById('glossary-match-count');
  var emptyState = document.getElementById('glossary-empty');
  var sections = document.querySelectorAll('.glossary-table-section');

  if (!searchInput) return;

  /**
   * Filter glossary tables based on search query.
   * Uses class toggling (.is-hidden) — never sets inline style.display.
   */
  function filterGlossary(query) {
    var q = (query || '').trim().toLowerCase();
    var totalVisible = 0;
    var sectionsWithRows = 0;

    sections.forEach(function (section) {
      var tables = section.querySelectorAll('table[data-table-enhanced]');
      var sectionVisible = 0;

      tables.forEach(function (table) {
        var rows = table.querySelectorAll('tbody tr');
        var tableVisible = 0;

        rows.forEach(function (row) {
          var text = row.textContent.toLowerCase();
          var match = !q || text.indexOf(q) !== -1;
          if (match) {
            row.classList.remove('is-hidden');
            tableVisible++;
            sectionVisible++;
            totalVisible++;
          } else {
            row.classList.add('is-hidden');
          }
        });

        var tableWrap = table.closest('.table-wrap');
        if (tableWrap) {
          tableWrap.classList.toggle('is-hidden', tableVisible === 0);
        } else {
          table.classList.toggle('is-hidden', tableVisible === 0);
        }
      });

      if (q && sectionVisible === 0) {
        section.classList.add('is-hidden');
      } else {
        section.classList.remove('is-hidden');
        if (sectionVisible > 0) sectionsWithRows++;
      }
    });

    // Match count display
    if (q) {
      matchCount.textContent = totalVisible + ' 条匹配';
    } else {
      matchCount.textContent = '';
    }

    // Empty state toggle
    if (q && totalVisible === 0) {
      emptyState.classList.remove('is-hidden');
    } else {
      emptyState.classList.add('is-hidden');
    }
  }

  // Debounced input listener (150ms)
  var debounceTimer;
  searchInput.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    var val = this.value;
    debounceTimer = setTimeout(function () {
      filterGlossary(val);
    }, 150);
  });

  // Auto-focus search on page load
  searchInput.focus();

  // ── Info-icon tooltips for metric labels ──────────────────

  var infoIcons = document.querySelectorAll('.metric-label .info-icon');
  infoIcons.forEach(function (icon) {
    icon.addEventListener('click', function (e) {
      e.preventDefault();
    });
    // Native title attribute handles tooltip; this listener
    // ensures no default action and provides a hook for future
    // custom tooltip implementation.
  });
})();
