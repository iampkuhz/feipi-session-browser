/**
 * projects.js — Projects page search, sort, and filter persistence.
 *
 * Loaded via script_extra in projects.html.
 */
(function() {
    'use strict';

    window.applyProjectFilters = function() { filterProjects(); };

    function filterProjects() {
        var q = document.getElementById('project-search').value.toLowerCase().trim();
        var rows = document.querySelectorAll('#projects-table tbody tr');
        var visibleCount = 0;

        rows.forEach(function(row) {
            var name = (row.dataset.name || '').toLowerCase();
            var path = (row.dataset.path || '').toLowerCase();
            var show = !q || name.indexOf(q) >= 0 || path.indexOf(q) >= 0;
            row.style.display = show ? '' : 'none';
            if (show) visibleCount++;
        });

        document.getElementById('project-count').textContent = visibleCount;
        var label = document.getElementById('projects-count-label');
        if (label) label.textContent = visibleCount + ' projects';
        var empty = document.getElementById('projects-empty');
        if (empty) empty.style.display = visibleCount === 0 ? 'block' : 'none';
    }

    window.applyProjectSort = function() { sortProjects(); };

    function sortProjects() {
        var sortBy = document.getElementById('project-sort').value;
        var tbody = document.querySelector('#projects-table tbody');
        if (!tbody) return;

        var rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort(function(a, b) {
            var keyMap = {
                'last_seen': function(r) { return r.dataset.lastSeen; },
                'total_sessions': function(r) { return parseInt(r.dataset.totalSessions) || 0; },
                'total_tokens': function(r) { return parseInt(r.dataset.totalTokens) || 0; },
                'total_tool_calls': function(r) { return parseInt(r.dataset.totalTools) || 0; },
                'total_failed_tools': function(r) { return parseInt(r.dataset.totalFailed) || 0; }
            };
            var getter = keyMap[sortBy] || keyMap['last_seen'];
            var va = getter(a), vb = getter(b);
            if (sortBy === 'last_seen') {
                return vb > va ? 1 : (va > vb ? -1 : 0);
            }
            return vb - va;
        });

        rows.forEach(function(r) { tbody.appendChild(r); });
    }

    window.resetProjectFilters = function() {
        document.getElementById('project-search').value = '';
        document.getElementById('project-sort').selectedIndex = 0;
        filterProjects();
        arpStorage.remove('projects_search');
        arpStorage.remove('projects_sort');
    };

    var searchEl = document.getElementById('project-search');
    var sortEl = document.getElementById('project-sort');

    var savedSearch = arpStorage.get('projects_search');
    if (savedSearch && searchEl) { searchEl.value = savedSearch; }
    var savedSort = arpStorage.get('projects_sort');
    if (savedSort && sortEl) { sortEl.value = savedSort; }

    if (searchEl) {
        searchEl.addEventListener('input', function() {
            arpStorage.set('projects_search', searchEl.value);
        });
    }
    if (sortEl) {
        sortEl.addEventListener('change', function() {
            arpStorage.set('projects_sort', sortEl.value);
        });
    }

    if (savedSearch || savedSort) {
        filterProjects();
        if (savedSort) sortProjects();
    }
})();
