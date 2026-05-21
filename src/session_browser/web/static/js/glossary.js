/**
 * glossary.js — Glossary page search/filter.
 *
 * Loaded via script_extra in glossary.html.
 */
(function() {
    'use strict';

    var searchInput = document.getElementById('glossary-search');
    var matchCount = document.getElementById('glossary-match-count');
    var emptyState = document.getElementById('glossary-empty');
    var sections = document.querySelectorAll('.glossary-table-section');

    if (!searchInput) return;

    function filterGlossary(query) {
        var q = (query || '').trim().toLowerCase();
        var totalVisible = 0;
        var sectionsWithRows = 0;

        sections.forEach(function(section) {
            var tables = section.querySelectorAll('table[data-table-enhanced]');
            var sectionVisible = 0;

            tables.forEach(function(table) {
                var rows = table.querySelectorAll('tbody tr');
                var tableVisible = 0;

                rows.forEach(function(row) {
                    var text = row.textContent.toLowerCase();
                    var match = !q || text.indexOf(q) !== -1;
                    row.style.display = match ? '' : 'none';
                    if (match) { tableVisible++; sectionVisible++; totalVisible++; }
                });

                var tableWrap = table.closest('.table-scroll');
                if (tableWrap) {
                    tableWrap.style.display = tableVisible > 0 ? '' : 'none';
                } else {
                    table.style.display = tableVisible > 0 ? '' : 'none';
                }
            });

            if (q && sectionVisible === 0) {
                section.style.display = 'none';
            } else {
                section.style.display = '';
                if (sectionVisible > 0) sectionsWithRows++;
            }
        });

        if (q) {
            matchCount.textContent = totalVisible + ' 条匹配';
        } else {
            matchCount.textContent = '';
        }

        if (q && totalVisible === 0) {
            emptyState.style.display = '';
        } else {
            emptyState.style.display = 'none';
        }
    }

    var debounceTimer;
    searchInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        var val = this.value;
        debounceTimer = setTimeout(function() { filterGlossary(val); }, 150);
    });

    searchInput.focus();
})();
