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
  var host = qs(document, '[data-execution-evidence]');
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
    html += '<p class="se-failure__basis" data-execution-failure-evidence>' + escapeRoundHtml(firstFailureExplanation(diag))
      + (tool ? ' 执行归属：' + executionContextMarkup(tool, page.contextLabels) + '。' : '') + '</p>';
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
        return '<div><strong>' + escapeRoundHtml(work.name) + ' · ' + executionWorkDuration(work.measuredWorkNanos)
          + '</strong> · ' + executionContextMarkup(work, page.contextLabels)
          + ' · ' + escapeRoundHtml(work.kind) + ' · ' + work.measuredTools + ' / ' + work.totalTools + ' 已测 '
          + candidates.map(function (candidate, i) {
            return executionLocateButton(candidate.toolCallId, (i ? '#' + (i + 1) : '最长') + ' · ' + observedToolTime(candidate));
          }).join(' ') + executionTaskContextLink(work) + executionSameInputMaximum(work.sameInputMaximum) + '</div>';
      }).join('') + '</div></details>';
  }
  html += executionLongOperations(diag, page.contextLabels);
  setMarkup(host, html);
  syncExecutionEvidenceVisibility();
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
    subagent: item.group.subagentId || '',
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

function firstFailureExplanation(diag) {
  var fallback = '首个工具已记录信号，具体依据请定位查看；不等同整个任务失败。';
  var evidence = diag.firstFailureEvidence;
  if (!diag.firstFailureTool || !evidence || typeof evidence !== 'object') return fallback;
  var basis;
  if (evidence.kind === 'nonzero_exit' && Number.isInteger(evidence.exitCode)
      && evidence.exitCode !== 0 && evidence.exitCode >= -2147483648 && evidence.exitCode <= 2147483647) {
    basis = '退出码 ' + evidence.exitCode;
  } else if (evidence.kind === 'executor_status') {
    var states = { failed: '失败', error: '错误', cancelled: '取消' };
    if (typeof evidence.executorStatus === 'string'
        && Object.prototype.hasOwnProperty.call(states, evidence.executorStatus)) {
      basis = '执行器状态 ' + evidence.executorStatus + '（' + states[evidence.executorStatus] + '）';
    }
  } else if (evidence.kind === 'result_signal') basis = '工具结果记录含失败线索';
  return basis ? '首个依据：' + basis + '；不等同整个任务失败。' : fallback;
}

function syncExecutionEvidenceVisibility() {
  var host = qs(document, '[data-execution-judgment]');
  if (host) host.hidden = qs(host, '[data-collaboration-attention]').hidden
    && !qs(host, '[data-execution-evidence]').childElementCount;
}

function executionWorkDuration(value) {
  if (!/^\d+$/.test(value)) return '未记录';
  var nanos = BigInt(value);
  if (nanos === 0n) return '0ms';
  if (nanos < 1000000n) return '&lt;1ms';
  var unit = nanos < 1000000000n ? 1000000n : 1000000000n;
  var fraction = (nanos % unit).toString().padStart(unit === 1000000n ? 6 : 9, '0').replace(/0+$/, '');
  return (nanos / unit).toString() + (fraction ? '.' + fraction : '') + (unit === 1000000n ? 'ms' : 's');
}


function executionContextMarkup(record, labels) {
  if (record.scope === 'main') return '主会话';
  var id = record.subagentId;
  if (record.scope !== 'subagent' || !id || /^unknown-sidechain:/.test(id)) return '归属未确认';
  return escapeRoundHtml(labels?.['subagent:' + id] || id) + ' · 独立子上下文';
}

function executionTaskContextLink(record) {
  if (record.scope !== 'subagent' || !record.subagentId || /^unknown-sidechain:/.test(record.subagentId)) return '';
  return ' <button type="button" class="sd-btn sd-btn--secondary sd-btn--sm" data-execution-task-context data-collaboration-exchanges="'
    + escapeRoundHtml('subagent:' + record.subagentId) + '">查看任务与往来</button>';
}

// 服务端提供有界候选；浏览器不按参数预览分组，也不混合单次和累计口径。
function executionLongOperations(diag, labels) {
  var html = [[diag.workloadSignals, true], [diag.longOperations, false]].map(function (entry) {
    var signals = entry[0], cumulative = entry[1];
    if (!signals?.candidates?.length) return '';
    return '<details class="se-evidence" data-execution-signal-metric="' + (cumulative ? 'cumulative' : 'single') + '"><summary>'
      + (cumulative ? '已测累计' : '单次耗时') + '</summary><div class="se-evidence__body"><p>exec_command · 已测 '
      + signals.measuredTools + '/' + signals.totalTools + ' 次'
      + (cumulative ? ' · ' + Math.min(3, signals.candidates.length) + '/' + signals.eligibleGroups + ' 个上下文' : '')
      + (signals.unknownTools ? ' · 缺可信执行器时长 ' + signals.unknownTools + ' 次' : '')
      + (signals.otherKindTools ? ' · 其他计时口径 ' + signals.otherKindTools + ' 次' : '')
      + (signals.excludedIdentityTools || signals.unconfirmedIdentityTools
        ? ' · 归属未确认 ' + (signals.excludedIdentityTools || signals.unconfirmedIdentityTools) + ' 次' : '')
      + '；仅已测，非完整瓶颈。慢不等于异常；不代表任务用时、墙钟、效率或关键路径。</p>'
      + signals.candidates.slice(0, 3).map(function (candidate) {
        var tool = cumulative ? candidate.longest?.tool : candidate.tool;
        if (!tool?.toolCallId) return '';
        var scope = cumulative ? candidate : tool;
        return '<article class="se-long-operation" data-execution-long-operation><p>'
          + executionContextMarkup(scope, labels) + ' · <strong>'
          + executionWorkDuration(cumulative ? candidate.measuredWorkNanos : candidate.durationNanos)
          + '</strong>' + (cumulative ? ' · 已测 ' + candidate.measuredTools + '/' + candidate.totalTools
            + ' 次 · 代表调用 ' + executionWorkDuration(candidate.longest.durationNanos) : '')
          + '</p><p>' + (cumulative ? '本组单次最长（累计不归于此命令）' : '命令摘要')
          + '：<code>' + escapeRoundHtml(tool.inputPreview || '参数预览未记录') + '</code> '
          + executionLocateButton(tool.toolCallId, cumulative ? '定位代表调用' : '定位此动作')
          + executionTaskContextLink(scope) + '</p>'
          + (cumulative ? executionSameInputMaximum(candidate.sameInputMaximum) : '') + '</article>';
      }).join('') + '</div></details>';
  }).join('');
  return html ? '<details class="se-evidence" data-execution-long-operations><summary>耗时线索</summary>'
    + '<div class="se-evidence__body">' + html + '</div></details>' : '';
}

function executionSameInputMaximum(maximum) {
  if (!maximum?.tool?.toolCallId) return '';
  return '<p class="se-basis" data-execution-same-input><strong>其中已测 ' + executionWorkDuration(maximum.measuredWorkNanos)
    + '</strong> · 已测 ' + maximum.measuredTools + '/' + maximum.totalTools + ' 次'
    + (maximum.unknownTools ? ' · 缺测 ' + maximum.unknownTools + ' 次' : '')
    + (maximum.otherKindTools ? ' · 其他计时口径 ' + maximum.otherKindTools + ' 次' : '')
    + ' · 已识别完整参数 ' + maximum.identifiedInputs + '/' + maximum.totalInputs
    + '；同参数记录已测累计最多（本组 ' + maximum.distinctInputs + ' 种参数记录）：<code class="se-diagnosis-command">'
    + escapeRoundHtml(maximum.tool.inputPreview || '参数预览未记录') + '</code> <button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-execution-locate="'
    + escapeRoundHtml(maximum.tool.toolCallId) + '">定位此参数的一次调用</button></p>';
}
