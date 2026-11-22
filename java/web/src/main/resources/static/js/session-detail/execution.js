function executionLine(text, label) {
  if (!text) return '';
  return '<span class="se-log-line" title="' + escapeRoundHtml(text) + '">'
    + (label ? '<b>' + label + '</b>' : '') + escapeRoundHtml(text) + '</span>';
}

function executionLocateButton(id, label) {
  return '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm" data-execution-locate="'
    + escapeRoundHtml(id) + '">' + escapeRoundHtml(label) + '</button>';
}

function applyExecutionSummary(page) {
  var host = qs(document, '[data-execution-judgment]');
  var diag = page?.diagnostics;
  if (!host || !diag) return;
  var html = '';
  var tool = diag.firstFailureTool;
  if (diag.failures > 0) {
    html += '<div class="se-failure"><strong>' + formatNumber(diag.failures) + ' 次工具失败信号'
      + (tool ? ' · ' + escapeRoundHtml(tool.name + ' · ' + toolStatusLabel(tool)) : '') + '</strong>';
    if (diag.firstFailureResultPreview) html += executionLine(diag.firstFailureResultPreview, '');
    if (diag.firstFailure) {
      html += '<div class="se-failure__actions">' + executionLocateButton(diag.firstFailure, '定位首个失败')
        + (tool?.resultObserved ? contentPayloadButton('tool:result:' + diag.firstFailure, 'tool_result', '首个失败 · 执行结果', '查看失败结果', '') : '')
        + '</div>';
    }
    html += '</div>';
  }
  var workloads = (diag.workloads || []).filter(function (work) {
    return work.longest && work.measuredTools > 0 && /^\d+$/.test(work.measuredWorkNanos);
  });
  if (workloads.length) {
    html += '<details class="se-evidence"><summary>工具耗时证据</summary><div class="se-evidence__body">'
      + '<p>按上下文与计时口径分别累计，不是会话用时。' + (diag.workloadGroups > workloads.length
        ? '显示 ' + workloads.length + ' / ' + diag.workloadGroups + ' 组。' : '') + '</p>'
      + workloads.map(function (work) {
        var candidates = work.slowest?.length ? work.slowest.slice(0, 3) : [work.longest];
        return '<div><strong>' + escapeRoundHtml(work.name) + ' · ' + escapeRoundHtml(durationLabel(Number(work.measuredWorkNanos) / 1e9))
          + '</strong> · ' + (work.scope === 'subagent' ? '子 Agent' : '主会话')
          + ' · ' + escapeRoundHtml(work.kind) + ' · ' + work.measuredTools + ' / ' + work.totalTools + ' 已测 '
          + candidates.map(function (candidate, i) {
            return executionLocateButton(candidate.toolCallId, (i ? '#' + (i + 1) : '最长') + ' · ' + observedToolTime(candidate));
          }).join(' ') + '</div>';
      }).join('') + '</div></details>';
  }
  setMarkup(host, html);
  host.hidden = !html;
}

async function locateExecution(id, current) {
  var query = new URLSearchParams({ target: id });
  var slice = await readSessionContentPage(getApiBase() + '/execution?' + query);
  if (!current()) return;
  var item = slice.items?.find(function (item) { return item.tool?.toolCallId === id; })
    || slice.items?.find(function (item) { return item.group?.id === id; });
  if (!item?.group?.round) throw new Error('该动作没有可定位的轮次');
  return jumpRound(document, item.group.round, {
    execution: id,
    target: id,
    targetKind: item.tool?.toolCallId === id ? 'tool' : 'call',
    current: current
  });
}

function openReadingDetails(params) {
  if (params.get('tab') === 'analysis' || location.hash === '#session-analysis') {
    var analysis = qs(document, '#session-analysis');
    if (analysis) scrollTraceTarget(analysis, false);
  }
  if (params.get('tab') === 'payload') {
    var trace = qs(document, '[data-trace-panel]');
    if (trace) scrollTraceTarget(trace, false);
  }
}
