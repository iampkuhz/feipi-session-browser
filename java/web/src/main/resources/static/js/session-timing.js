/** Source timing is independent of transcript span and legacy execution counters. */
(function () {
  'use strict';
  var precisionKeys = {
    wallSeconds: 'wallPrecision', activeTaskSeconds: 'activeTaskPrecision', agentTurnSeconds: 'agentTurnPrecision',
    modelExecutionSeconds: 'modelExecutionPrecision', toolExecutionSeconds: 'toolExecutionPrecision'
  };
  function seconds(timing, key) {
    var number = timing && timing[key];
    var precision = timing && timing[precisionKeys[key]];
    return typeof number === 'number' && Number.isFinite(number) && number >= 0
      && (precision === 'measured' || precision === 'partial') ? number : null;
  }
  function duration(number) {
    var n = Math.round(number);
    if (n >= 3600) return Math.floor(n / 3600) + 'h ' + Math.floor(n % 3600 / 60) + 'm';
    if (n >= 60) return Math.floor(n / 60) + 'm ' + n % 60 + 's';
    return n + 's';
  }
  function value(timing, key) {
    var number = seconds(timing, key);
    return number == null ? 'N/A' : duration(number) + (timing[precisionKeys[key]] === 'partial' ? ' · Partial' : '');
  }
  function nonTaskWall(timing) {
    if (!timing || timing.wallPrecision !== 'measured' || timing.activeTaskPrecision !== 'measured') return 'N/A';
    var wall = seconds(timing, 'wallSeconds');
    var active = seconds(timing, 'activeTaskSeconds');
    return wall == null || active == null || active > wall ? 'N/A' : duration(wall - active);
  }
  function description(timing) {
    timing = timing || {};
    var counts = ['completedTaskCount', 'incompleteTaskCount', 'abortedTaskCount'].map(function (key, index) {
      var count = timing[key];
      return ['Completed', 'Incomplete', 'Aborted'][index] + ': '
        + (typeof count === 'number' && count >= 0 ? count : 'Not reported');
    }).join(' · ');
    return 'MAIN task windows (union), including tools/wait; not model inference. '
      + 'Agent Turn is cumulative MAIN-agent workload, not Task Active. '
      + 'Non-task Wall Time: ' + nonTaskWall(timing) + ' (not user waiting). ' + counts
      + (timing.activeTaskBasis ? ' · Task basis: ' + timing.activeTaskBasis : '')
      + (timing.agentTurnBasis ? ' · Agent-turn basis: ' + timing.agentTurnBasis : '');
  }
  function prepareTable(table) {
    if (!table) return;
    table.querySelectorAll('[data-sort-key="process-time"], [data-sort-key="duration"], [data-sort="process-time"], [data-sort="duration"]').forEach(function (header) {
      var label = (header.getAttribute('data-sort-key') || header.getAttribute('data-sort')) === 'process-time' ? 'Task Active' : 'Wall Duration';
      Array.from(header.childNodes).forEach(function (node) {
        if (node.nodeType === 3 && node.textContent.trim()) node.textContent = label + ' ';
      });
      header.title = label === 'Task Active' ? 'MAIN source task-window union; includes tools/wait, not model execution. Unknown = N/A.' : 'Source wall-clock duration, not execution time.';
    });
    var parent = table.parentElement;
    if (!parent.querySelector('[data-session-timing-description]')) {
      var note = document.createElement('p');
      note.className = 'session-timing-note';
      note.setAttribute('data-session-timing-description', '');
      note.textContent = 'Task Active: MAIN task windows (union), including tools/wait; not model execution. Agent Turn workload is separate. Missing source timing = N/A.';
      parent.insertBefore(note, table);
    }
  }
  function applyDetail(card, timing) {
    if (!card) return;
    card.setAttribute('data-session-timing', '');
    card.setAttribute('aria-label', 'Source Task Active');
    var label = card.querySelector('.sd-kpi__label');
    if (label) label.textContent = 'Source Task Active';
    var primary = card.querySelector('.sd-kpi__value');
    if (primary) {
      primary.classList.add('session-timing-value');
      primary.setAttribute('data-session-timing-value', '');
    }
    var note = card.querySelector('[data-session-timing-note]') || document.createElement('p');
    note.setAttribute('data-session-timing-note', '');
    note.className = 'session-timing-note';
    note.textContent = description(timing);
    if (!note.parentElement) card.appendChild(note);
  }
  window.SessionTiming = { seconds: seconds, value: value, nonTaskWall: nonTaskWall,
    description: description, prepareTable: prepareTable, applyDetail: applyDetail };
}());
