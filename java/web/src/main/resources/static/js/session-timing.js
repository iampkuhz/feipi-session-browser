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
    if (number === 0) return '0s';
    if (number < 0.001) return '<1ms';
    if (number < 1) return Number((number * 1000).toFixed(3)) + 'ms';
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
      return ['已结束', '未闭合', '中止'][index] + '：'
        + (typeof count === 'number' && count >= 0 ? count : '未报告');
    }).join(' · ');
    var taskBasis = timing.activeTaskBasis === 'main_task_windows' ? '任务汇总方法：按主任务时间窗口计时，重叠窗口只计一次。' : '';
    var turnBasis = timing.agentTurnBasis === 'main_agent_turn_duration' ? '轮次依据：记录中的主会话轮次时长累计。'
      : timing.agentTurnBasis === 'main_task_duration_sum' ? '轮次栏依据：无可用时间窗口时的主任务时长累计，不冒称实测轮次。' : '';
    return [
      '计时口径：主会话任务活动时间包含任务期间的工具和等待，不是模型推理耗时。'
        + '主会话轮次累计与任务活动时间口径不同，不是 LLM 调用延迟或模型推理耗时。'
        + '来源记录时间跨度不代表持续执行。'
        + '来源模型计时、来源工具计时仅使用明确记录，与逐工具执行器观测累计分开；不得相减推算模型耗时或混口径相加。',
      '来源依据：' + taskBasis + turnBasis
        + '任务外记录跨度：' + nonTaskWall(timing) + '（不等于用户等待）。',
      '缺测与记录：N/A 表示未知而非 0；Partial 表示部分测量。任务计时记录：' + counts + '；仅说明计时记录状态，不表示业务成功。'
    ].join('\n\n');
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
    var primary = card.querySelector('.sd-kpi__value');
    if (primary) {
      primary.classList.add('session-timing-value');
      primary.setAttribute('data-session-timing-value', '');
    }
    var explanation = card.ownerDocument.querySelector('[data-session-timing-explanation]');
    if (!explanation) return;
    var note = explanation.querySelector('[data-session-timing-note]');
    if (!note) {
      note = document.createElement('details');
      note.setAttribute('data-session-timing-note', '');
      note.className = 'session-timing-note';
      var summary = document.createElement('summary');
      summary.textContent = '计时口径与来源';
      note.append(summary, document.createElement('p'));
      explanation.appendChild(note);
    }
    var paragraphs = note.querySelectorAll(':scope > p');
    description(timing).split('\n\n').forEach(function (text, index) {
      var paragraph = paragraphs[index];
      if (!paragraph) { paragraph = document.createElement('p'); note.appendChild(paragraph); }
      paragraph.textContent = text;
    });
  }
  window.SessionTiming = { seconds: seconds, value: value, nonTaskWall: nonTaskWall,
    description: description, prepareTable: prepareTable, applyDetail: applyDetail };
}());
