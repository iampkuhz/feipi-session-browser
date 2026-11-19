// Replace diagnostic children only: the collaboration attention entry owns a stable sibling slot.
function setExecutionDiagnosis(content, plain) {
  var summary = document.querySelector('[data-execution-judgment]');
  if (!summary) return;
  var slot = summary.querySelector('[data-collaboration-attention]');
  var block = document.createElement('div');
  if (plain) block.textContent = content; else setMarkup(block, content);
  Array.from(summary.childNodes).forEach(function (node) { if (node !== slot) node.remove(); });
  while (block.firstChild) summary.appendChild(block.firstChild);
}

/* 执行阅读仅请求有界摘要；原文、归因与子上下文继续使用原有惰性入口。 */
var executionView = { page: null, status: 'all', agent: '', epoch: 0 };

function executionDuration(tool) {
  if (tool.durationMs == null) return '<span aria-label="耗时未测量">—</span>';
  if (tool.durationMs === 0 && tool.observation && tool.observation.durationNanos > 0) return '&lt;1ms';
  return escapeRoundHtml(tool.durationMs < 1000 ? tool.durationMs + 'ms' : Number((tool.durationMs / 1000).toFixed(3)) + 's');
}

// Only published same-generation MAIN metrics qualify; rendering never discloses or focuses the card.
function syncMainSourceTimingEntry() {
  var host = document.querySelector('[data-main-source-timing-entry]');
  if (!host) return false;
  var published = typeof sessionDetailState !== 'undefined' && sessionDetailState.mainTiming;
  var timing = published?.metrics?.timing;
  var valid = !!published && published.metrics === sessionDetailState.metrics
    && published.generation === document.body.getAttribute('data-index-generation')
    && document.body.getAttribute('data-session-api-metrics-state') === 'true'
    && document.body.getAttribute('data-session-api-hydrated') === 'true'
    && !document.querySelector('[data-snapshot-batch-error]')
    && (!executionView.agent || executionView.agent === 'main')
    && (SessionTiming.seconds(timing, 'activeTaskSeconds') !== null || SessionTiming.seconds(timing, 'agentTurnSeconds') !== null);
  host.hidden = !valid;
  return valid;
}

function executionWorkDuration(value) {
  var nanos = BigInt(value);
  if (nanos === 0n) return '0ms';
  if (nanos < 1000000n) return '&lt;1ms';
  var unit = nanos < 1000000000n ? 1000000n : 1000000000n;
  var fraction = (nanos % unit).toString().padStart(unit === 1000000n ? 6 : 9, '0').replace(/0+$/, '');
  return (nanos / unit).toString() + (fraction ? '.' + fraction : '') + (unit === 1000000n ? 'ms' : 's');
}

function executionWorkIdentityConfirmed(work) {
  return (work.scope === 'main' && !work.subagentId) || (work.scope === 'subagent' && !!work.subagentId && !/^unknown-sidechain:/.test(work.subagentId));
}

// The untruncated exception uses actual complete context keys, never group counts or labels.
function executionMultiContextSignals(diag, workloads) {
  if (executionView.agent || diag.failures || workloads.length < 2 || !workloads.every(executionWorkIdentityConfirmed)) return false;
  var contextKey = function (work) { return work.scope === 'main' ? 'main' : 'subagent:' + work.subagentId; };
  if (new Set(workloads.map(contextKey)).size < 2) return false;
  var candidates = (diag.workloadSignals?.candidates || []).concat((diag.longOperations?.candidates || []).map(function (candidate) { return candidate.tool; }));
  return new Set(candidates.filter(executionWorkIdentityConfirmed).map(contextKey)).size >= 2;
}

// 线索只消费当前冻结范围的服务端候选；单次与累计独立，不在浏览器重排。
function executionLongOperations(diag, workloads, sharedBasis) {
  var cumulative = diag.workloadSignals;
  var single = diag.longOperations;
  var hasCumulative = !!(cumulative && cumulative.candidates.length);
  var hasSingle = !!(single && single.candidates.length);
  var key = JSON.stringify([executionView.agent, document.body.getAttribute('data-index-generation') || '']);
  if (executionView.signalKey !== key) {
    executionView.signalKey = key;
    executionView.signalMetric = hasCumulative ? 'cumulative' : 'single';
  }
  if ((executionView.signalMetric === 'cumulative' && !hasCumulative) || (executionView.signalMetric === 'single' && !hasSingle)) {
    executionView.signalMetric = hasCumulative ? 'cumulative' : 'single';
  }
  if ((!hasCumulative && !hasSingle) || (diag.workloadGroups <= workloads.length && !executionMultiContextSignals(diag, workloads))) return '';
  return '<section class="se-long-operations" data-execution-long-operations><h3>耗时线索</h3>'
    + (hasCumulative && hasSingle ? '<div class="se-workload-line" data-execution-signal-controls>'
      + ['cumulative', 'single'].map(function (metric) {
        return '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-execution-signal-metric="' + metric
          + '" aria-pressed="' + (executionView.signalMetric === metric) + '">' + (metric === 'cumulative' ? '已测累计' : '单次耗时') + '</button>';
      }).join('') + '</div>' : '')
    + '<div data-execution-signal-content>' + executionSignalContent(diag, sharedBasis) + '</div></section>';
}

function executionSignalContent(diag, sharedBasis) {
  var isCumulative = executionView.signalMetric === 'cumulative';
  var signals = isCumulative ? diag.workloadSignals : diag.longOperations;
  var other = isCumulative ? diag.longOperations : diag.workloadSignals;
  var html = '<p class="se-basis">exec_command · 可信已测 ' + signals.measuredTools + '/' + signals.totalTools + ' 次'
    + (isCumulative ? '；累计线索 ' + Math.min(3, signals.candidates.length) + '/' + signals.eligibleGroups + ' 组（按执行上下文分组）' : '')
    + (signals.unknownTools ? '；缺少本口径的执行器原始时长 ' + signals.unknownTools + ' 次（毫秒摘要不能代替原始值）' : '')
    + (signals.otherKindTools ? '；其他计时口径 ' + signals.otherKindTools + ' 次' : '')
    + (isCumulative && signals.excludedIdentityTools ? '；归属边界未确认而排除 ' + signals.excludedIdentityTools + ' 次（含同组受影响的已知记录）' : '')
    + (!isCumulative && signals.unconfirmedIdentityTools ? '；身份依据不足 ' + signals.unconfirmedIdentityTools + ' 次（不代表 Agent 不存在）' : '')
    + (isCumulative ? (sharedBasis ? '。仅比较已测部分，非完整瓶颈；未测记录可能改变累计高低。' : '。仅比较已测部分，未测记录可能改变累计高低；')
      : '。按同类执行器记录的单次时长选取；' + (sharedBasis ? '仅已测，非完整瓶颈。' : '') + '非累计、')
    + '非任务用时、效率、墙钟或关键路径，慢不等于异常。至多 3 条。</p>';
  if (other && other.candidates.length) {
    var maximum = other.candidates[0];
    html += '<p class="se-basis" data-execution-signal-other>' + (isCumulative ? '单次最大值 ' + executionWorkDuration(maximum.durationNanos) : '已测累计最大值 ' + executionWorkDuration(maximum.measuredWorkNanos))
      + ' · ' + executionContextMarkup(isCumulative ? maximum.tool : maximum)
      + (!isCumulative ? ' · 已测 ' + maximum.measuredTools + '/' + maximum.totalTools + ' 次' : '') + '；切换指标查看对应线索。</p>';
  }
  return html + signals.candidates.slice(0, 3).map(function (candidate) {
    var tool = isCumulative ? candidate.longest.tool : candidate.tool;
    var context = isCumulative ? candidate : tool;
    var contextKey = context.scope === 'main' ? 'main' : 'subagent:' + context.subagentId;
    return '<article class="se-long-operation" data-execution-long-operation><p class="se-basis">执行归属：' + executionContextMarkup(context)
      + '</p><div class="se-workload-line"><strong>' + escapeRoundHtml(tool.name) + (isCumulative ? ' · 已测累计 ' + executionWorkDuration(candidate.measuredWorkNanos) : ' · 单次 ' + executionWorkDuration(candidate.durationNanos))
      + '</strong>' + (isCumulative ? '<span>已测 ' + candidate.measuredTools + '/' + candidate.totalTools + ' 次 · 最长单次 ' + executionWorkDuration(candidate.longest.durationNanos)
        + (candidate.unknownTools ? ' · 缺测 ' + candidate.unknownTools + ' 次' : '') + (candidate.otherKindTools ? ' · 其他计时口径 ' + candidate.otherKindTools + ' 次' : '') + '</span>' : '')
      + (isCumulative ? '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-collaboration-agent="' + escapeRoundHtml(contextKey) + '">查看上下文过程</button>' : '')
      + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-execution-locate="' + escapeRoundHtml(tool.toolCallId)
      + '">' + (isCumulative ? '定位代表调用' : '定位此动作') + '</button>'
      + (context.scope === 'subagent' && context.subagentId && !/^unknown-sidechain:/.test(context.subagentId) ? '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-execution-task-context data-collaboration-exchanges="' + escapeRoundHtml(contextKey) + '">查看任务与往来</button>' : '')
      + '</div><p class="se-representative">' + (isCumulative ? '本组单次最长（累计不归于此命令）' : '命令摘要') + '：<code class="se-diagnosis-command">'
      + escapeRoundHtml(tool.inputPreview || '参数未记录 · 定位后检查来源') + '</code></p>'
      + (isCumulative ? executionSameInputMaximum(candidate.sameInputMaximum) : '') + '</article>';
  }).join('');
}

// Consume only the server's qualified complete-input fact; never group previews here.
function executionSameInputMaximum(maximum) {
  if (!maximum) return '';
  return '<p class="se-basis" data-execution-same-input><strong>其中已测 ' + executionWorkDuration(maximum.measuredWorkNanos)
    + '</strong> · 已测 ' + maximum.measuredTools + '/' + maximum.totalTools + ' 次'
    + (maximum.unknownTools ? ' · 缺测 ' + maximum.unknownTools + ' 次' : '')
    + (maximum.otherKindTools ? ' · 其他计时口径 ' + maximum.otherKindTools + ' 次' : '')
    + '；同参数记录已测累计最多（本组 ' + maximum.distinctInputs + ' 种参数记录）：<code class="se-diagnosis-command">'
    + escapeRoundHtml(maximum.tool.inputPreview) + '</code> <button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-execution-locate="'
    + escapeRoundHtml(maximum.tool.toolCallId) + '">定位此参数的一次调用</button></p>';
}

function executionFailed(tool) {
  var observed = tool.observation || {};
  var exit = observed.exitCode == null ? tool.exitCode : observed.exitCode;
  return (exit != null && exit !== 0) || ['failed', 'error', 'cancelled'].includes(observed.status)
    || isFailedTool(tool);
}

function executionStatus(tool) {
  var observation = tool.observation || {};
  var exit = observation.exitCode == null ? tool.exitCode : observation.exitCode;
  var labels = { completed: '完成', success: '完成', ok: '完成', failed: '失败', error: '失败',
    cancelled: '已取消', running: '运行中', pending: '等待中', queued: '排队中' };
  if (exit != null) return '退出码 ' + exit;
  if (observation.status) return '执行器：' + (labels[observation.status] || observation.status);
  if (tool.status) return '结果信号：' + (labels[tool.status] || tool.status);
  return tool.resultObserved ? '已记录结果 · 退出未知' : '结果未记录';
}

function executionGroupActions(group) {
  var call = { callId: group.id, scope: group.scope };
  var html = '<div class="se-group__actions" data-execution-response-actions>';
  ['req', 'resp'].forEach(function (side) {
    var inputOnly = group.id === 'observed-input:1';
    var label = inputOnly && side === 'req' ? '用户输入' : side === 'req' ? '模型输入' : '模型输出';
    var available = group.round > 0 && (side === 'req' ? group.inputAvailable : group.outputAvailable);
    if (available) {
      var kind = side === 'req' ? 'request' : 'response';
      var path = '/attribution/' + group.round + '/1/' + kind + '?call_id=' + encodeURIComponent(group.id);
      html += contentPayloadButton(inputOnly ? 'round:req:1' : payloadIdFor(call, side), payloadKindFor(call, side), label, label, inputOnly ? '' : path);
    } else html += '<span class="se-missing">' + label + '未记录</span>';
  });
  return html + '</div>';
}

function executionGroupContext(group) {
  if (group.scope !== 'subagent') return '主会话';
  if (!group.subagentId) return '子 Agent · 身份未记录 · 独立上下文';
  if (typeof collaborationView !== 'undefined' && collaborationView.labels.has('subagent:' + group.subagentId)) {
    return collaborationView.labels.get('subagent:' + group.subagentId) + ' · 独立上下文';
  }
  // 权威协作窗口尚未提供身份时显示完整key，不按诊断/分页顺序猜编号。
  return '子上下文 ' + group.subagentId + ' · 独立上下文';
}

function executionContextMarkup(group) {
  var text = escapeRoundHtml(executionGroupContext(group));
  if (group.scope !== 'subagent' || !group.subagentId) return text;
  return '<span data-execution-context-key="' + escapeRoundHtml('subagent:' + group.subagentId)
    + '">' + text + '</span>';
}

function executionAgentMarkup(key) {
  return '<span data-execution-context-short data-execution-context-key="' + escapeRoundHtml(key) + '">'
    + escapeRoundHtml(collaborationView.labels.get(key) || key) + '</span>';
}

function syncExecutionContextLabels() {
  document.querySelectorAll('[data-execution-context-key]').forEach(function (node) {
    var key = node.dataset.executionContextKey;
    node.textContent = node.hasAttribute('data-execution-context-short')
      ? collaborationView.labels.get(key) || key
      : executionGroupContext({ scope: 'subagent', subagentId: key.slice('subagent:'.length) });
  });
}

function executionEvidence(group, tool) {
  var html = '<details class="se-evidence ' + (tool ? 'se-tool-evidence' : 'se-group-evidence') + '"><summary>'
    + (tool ? '证据' : '记录来源') + '</summary><div class="se-evidence__body">';
  if (!tool) {
    if (group.toolCount > 0 && group.preview) html += '<p class="se-response-text">' + escapeRoundHtml(group.preview) + '</p>';
    html += '<p>本地记录 ' + escapeRoundHtml(group.id) + ' · '
      + escapeRoundHtml(group.scope === 'subagent' ? (group.subagentId || '子 Agent 身份未记录') : '主会话')
      + (group.parentCallId ? ' · 父调用 ' + escapeRoundHtml(group.parentCallId) : '')
      + (group.parentToolCallId ? ' · 明确父工具 ' + escapeRoundHtml(group.parentToolCallId) : '')
      + '。模型输入为来源记录/本地重建，不等同完整原始 HTTP 请求。</p>';
    html += '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-action="copy" data-copy-text="' + escapeRoundHtml(group.id) + '">复制来源 ID</button>';
    html += '<p>来源记录时间：' + escapeRoundHtml(group.timestamp || '未记录') + '（非执行起止区间）</p>';
  }
  if (tool) {
    html += contentPayloadButton('tool:input:' + tool.toolCallId, 'tool_input', '命令或参数', '命令或参数', '');
    html += contentPayloadButton('tool:result:' + tool.toolCallId, 'tool_result', '执行结果', '执行结果', '');
    html += '<p>工具 ID：' + escapeRoundHtml(tool.toolCallId) + ' · ' + escapeRoundHtml(executionStatus(tool)) + '</p>';
    html += '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-action="copy" data-copy-text="' + escapeRoundHtml(tool.toolCallId) + '">复制工具 ID</button>';
    if (tool.observation) {
      html += '<p>来源：' + escapeRoundHtml(tool.observation.source || '未记录')
        + ' · ' + escapeRoundHtml(tool.observation.kind || '未知')
        + (tool.observation.status ? ' · 状态原值 ' + escapeRoundHtml(tool.observation.status) : '')
        + (tool.observation.processId ? ' · 进程标识 ' + escapeRoundHtml(tool.observation.processId) : '')
        + (tool.observation.issue ? ' · ' + escapeRoundHtml(tool.observation.issue) : '') + '</p>';
    }
  }
  return html + '</div></details>';
}

function renderExecutionItems(items, append) {
  var host = document.querySelector('[data-execution-items]');
  if (!host) return;
  if (!append) host.replaceChildren();
  var current = null;
  items.forEach(function (item) {
    var group = item.group;
    if (!current || current.dataset.executionGroup !== group.id) {
      current = document.createElement('article');
      current.className = 'se-group' + (group.toolCount === 1 && item.tool ? ' se-group--single' : '');
      current.dataset.executionGroup = group.id;
      current.tabIndex = -1;
      var identity = group.label + (group.index ? ' #' + group.index : '');
      setMarkup(current, '<header><h3 aria-label="' + escapeRoundHtml(identity) + '">' + escapeRoundHtml(identity)
        + (item.toolOrdinal > 1 ? '（续 · 工具 ' + item.toolOrdinal + ' 起）' : '')
        + '</h3><span class="se-group-context' + (group.scope === 'subagent' ? '' : ' se-group-context--main') + '">' + executionContextMarkup(group)
        + (group.response === true && group.toolCount === 0 && group.outputAvailable === false
          ? ' · 本地未记录工具声明'
          : group.response ? ' · 下发 ' + group.toolCount + ' 个工具' : ' · 未观察到模型输出') + '</span>'
        + executionGroupActions(group) + executionEvidence(group, null) + '</header>'
        + (group.preview && !group.toolCount ? '<p class="se-response-text">' + escapeRoundHtml(group.preview) + '</p>' : ''));
      host.appendChild(current);
    }
    var tool = item.tool;
    if (!tool) return;
    var row = document.createElement('div');
    row.className = 'se-action' + (executionFailed(tool) ? ' se-action--failed' : '');
    row.dataset.executionTool = tool.toolCallId;
    row.tabIndex = -1;
    setMarkup(row, '<div class="se-action__main"><code>'
      + escapeRoundHtml(tool.inputPreview || '参数未记录 · 可检查证据') + '</code></div>'
      + '<div class="se-context"><span class="se-kind">' + escapeRoundHtml(tool.name) + '</span>'
      + '<span class="se-status">' + escapeRoundHtml(executionStatus(tool)) + '</span></div>'
      + '<strong class="se-duration">' + executionDuration(tool) + '</strong>' + executionEvidence(group, tool));
    if (current.classList.contains('se-group--single')) {
      var header = current.querySelector('header');
      header.insertBefore(row, header.querySelector('.se-group__actions'));
    } else current.appendChild(row);
  });
  if (!items.length && !append) host.textContent = executionView.status === 'failed' ? '此范围没有观察到工具失败。' : '此来源没有可用的执行摘要；可按需检查下方记录证据。';
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

function seedExecutionContextLabels(labels) {
  if (!labels || typeof labels !== 'object' || typeof collaborationView === 'undefined') return;
  Object.keys(labels).forEach(function (key) {
    if (typeof labels[key] === 'string' && labels[key] && !collaborationView.labels.has(key)) {
      collaborationView.labels.set(key, labels[key]);
    }
  });
}

function applyExecutionPage(page, append, deferContextLabels) {
  var timingCard = document.querySelector('[data-session-timing]');
  var timingTop = null;
  if (timingCard && document.activeElement === timingCard && syncMainSourceTimingEntry()) {
    var timingRect = timingCard.getBoundingClientRect();
    if (timingRect.top >= 0 && timingRect.bottom <= innerHeight) timingTop = timingRect.top;
  }
  if (!deferContextLabels) seedExecutionContextLabels(page.contextLabels);
  var activeMetric = document.activeElement.closest('[data-execution-signal-metric]');
  var focusedMetric = activeMetric && activeMetric.dataset.executionSignalMetric;
  var focusedSignalKey = executionView.signalKey;
  // 初始/重刷批次没有追加参数；新的冻结范围不继承旧指标。
  if (append === undefined) executionView.signalKey = null;
  executionView.renderedAgent = executionView.agent || '';
  executionView.page = page;
  if (!append) executionView.start = page.offset;
  renderExecutionItems(page.items || [], append);
  var pagerHost = document.querySelector('[data-execution-pagination]');
  if (pagerHost) {
    pagerHost.replaceChildren();
    var epoch = executionView.epoch;
    contentPager(pagerHost, 'execution', page.offset + page.items.length, page.total, page.nextCursor, function (cursor) {
      if (epoch !== executionView.epoch) return Promise.resolve();
      return loadExecutionPage({ cursor: cursor }, true);
    });
    pagerHost.querySelector('span').textContent = '当前摘要 ' + (page.total ? executionView.start + 1 : 0)
      + '–' + (page.offset + page.items.length) + ' / ' + page.total + '；范围外记录未加载。 ';
  }
  syncExecutionContextLabels();
  var summary = document.querySelector('[data-execution-judgment]');
  var diag = page.diagnostics;
  if (!summary || !diag) return;
  // Frozen diagnostics do not depend on the process page. Keep their actual nodes,
  // native disclosure state and focus when only that page is replaced/appended.
  var diagnosisKey = JSON.stringify([executionView.agent || '', document.body.getAttribute('data-index-generation'), diag]);
  if (append !== undefined && executionView.diagnosisKey === diagnosisKey && summary.querySelector('h2')) {
    syncExecutionDelegationSources();
    return;
  }
  executionView.diagnosisKey = diagnosisKey;
  var workloads = diag.workloads || [];
  var compact = diag.totalTools > 0 && diag.failures === 0 && workloads.length > 0;
  var unmeasured = diag.totalTools > 0 && diag.failures === 0 && diag.measuredTools === 0 && workloads.length === 0;
  var sharedWorkBasis = compact && new Set(workloads.map(function (work) {
    return JSON.stringify([work.scope, work.subagentId, work.kind]);
  })).size > 1;
  var hasSubagentWork = workloads.some(function (work) { return work.scope === 'subagent' && !!work.subagentId; });
  var sharedSignalBasis = !executionView.agent && compact && sharedWorkBasis && workloads.every(executionWorkIdentityConfirmed);
  var signals = executionLongOperations(diag, workloads, sharedSignalBasis);
  var discloseWork = !!signals && sharedSignalBasis;
  var html = '<h2>执行判断' + (executionView.agent ? ' · ' + executionAgentMarkup(executionView.agent) : '') + '</h2>'
    + '<a href="#execution-process-context">直接查看所选过程</a>';
  if (compact) {
    html += '<p class="se-basis">未观察到工具失败；不证明任务成功或记录完整。'
      + (sharedWorkBasis && !discloseWork ? ' <span data-execution-shared-work-basis>仅已测，非完整瓶颈，慢不等于异常。</span>' : '') + '</p>';
  } else {
    html += '<div class="se-judgments">';
    if (diag.totalTools === 0) {
      html += '<article><h3>此范围未观察到工具调用</h3><p>这不代表没有工作，也不证明任务成功。'
        + '请核对下方可用的模型输出与模型输入；未记录内容以页面标注为准。</p></article>';
    } else html += '<article><h3>' + (unmeasured ? '无可用工具时长' : diag.failures + ' 个工具有失败信号') + '</h3><p>'
      + (diag.failures ? escapeRoundHtml(firstFailureExplanation(diag)) : '可用日志中未观察到工具失败；不证明任务成功或记录完整。') + '</p>'
      + (diag.firstFailureTool ? '<p class="se-basis">执行归属：'
        + (['main', 'subagent'].includes(diag.firstFailureTool.scope) ? executionContextMarkup(diag.firstFailureTool) : '归属未记录') + '</p>' : '')
      + (diag.firstFailureTool ? '<code class="se-diagnosis-command">' + escapeRoundHtml(diag.firstFailureTool.inputPreview || '参数未记录 · 定位后检查结果') + '</code>' : '')
      + (diag.firstFailure ? '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-execution-locate="' + escapeRoundHtml(diag.firstFailure) + '">定位首个失败</button>' : '') + '</article>';
    html += '</div>';
  }
  html += signals;
  if (discloseWork) {
    var secondary = workloads.filter(function (work) { return work.name !== 'exec_command' || work.kind !== 'executor_reported'; });
    html += secondary.map(function (work) {
      return '<p class="se-basis" data-execution-secondary-work>' + executionContextMarkup(work) + ' · ' + escapeRoundHtml(work.name)
        + ' · 已测累计 ' + executionWorkDuration(work.measuredWorkNanos) + ' · 已测 ' + work.measuredTools + '/' + work.totalTools + ' 次'
        + (work.kind === 'executor_reported' ? ' · 执行器观测，同口径单独累计' : ' · 其他计时口径，单独累计')
        + (work.unknownTools ? ' · 未知 ' + work.unknownTools + ' 次' : '')
        + (work.otherKindTools ? ' · 其他/未确认口径 ' + work.otherKindTools + ' 次' : '') + '</p>';
    }).join('');
    var gaps = workloads.filter(function (work) { return !secondary.includes(work) && (work.unknownTools || work.otherKindTools); });
    if (gaps.length) html += '<div data-execution-workload-gaps>' + gaps.map(function (work) {
      return '<p class="se-basis">' + executionContextMarkup(work) + ' · ' + escapeRoundHtml(work.name) + ' · 执行器观测'
        + (work.unknownTools ? ' · 未知 ' + work.unknownTools + ' 次' : '')
        + (work.otherKindTools ? ' · 其他/未确认口径 ' + work.otherKindTools + ' 次' : '') + '</p>';
    }).join('') + '</div>';
    html += '<details class="se-workload-details" data-execution-workload-details><summary>上下文计量明细 · 已载 ' + workloads.length + '/' + diag.workloadGroups + ' 组（' + (diag.workloadGroups > workloads.length ? '前缀，' : '') + '非排名）</summary>';
  }
  var block = '';
  workloads.forEach(function (work) {
    var key = JSON.stringify([work.scope, work.subagentId, work.kind]);
    if (key !== block) {
      if (block) html += '</div></section>';
      block = key;
      html += '<section data-execution-workloads><p class="se-basis">' + executionContextMarkup(work)
        + ' · 执行器观测 · 仅本上下文、同口径比较'
        + (sharedWorkBasis ? '。' : '；仅已测，非完整瓶颈，慢不等于异常。') + '</p>'
        + (work.scope === 'subagent' && work.subagentId ? '<div class="se-sources" data-execution-delegation-sources="'
          + escapeRoundHtml('subagent:' + work.subagentId) + '"></div>' : '') + '<div class="se-judgments">';
    }
    var tool = work.longest;
    html += '<article data-execution-workload><div class="se-workload-line"><h3>' + escapeRoundHtml(work.name) + ' · 已测累计 '
      + executionWorkDuration(work.measuredWorkNanos) + '</h3><p>单次已测最长 ' + executionDuration(tool)
      + ' · 已测 ' + work.measuredTools + '/' + work.totalTools + ' 次'
      + (work.unknownTools ? ' · 未知 ' + work.unknownTools + ' 次' : '')
      + (work.otherKindTools ? ' · 其他/未确认口径 ' + work.otherKindTools + ' 次' : '') + '</p>'
      + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-execution-locate="'
      + escapeRoundHtml(tool.toolCallId) + '">定位此动作</button></div>'
      + '<p class="se-representative">代表动作（不代表同一命令）：<code class="se-diagnosis-command">'
      + escapeRoundHtml(tool.inputPreview || '参数未记录 · 定位后检查来源') + '</code></p>'
      + executionSameInputMaximum(work.sameInputMaximum);
    var candidates = work.slowest || [];
    if (candidates.length > 1) {
      html += '<details class="se-evidence" data-execution-slowest><summary>更多耗时调用</summary>'
        + '<div class="se-evidence__body"><p>单次耗时前 ' + candidates.length + ' 项（含上方代表），非全部慢项或根因。</p>'
        + candidates.slice(1).map(function (candidate) {
          return '<div data-execution-slow-call="' + escapeRoundHtml(candidate.toolCallId)
            + '"><code class="se-diagnosis-command">' + escapeRoundHtml(candidate.inputPreview || '参数未记录 · 定位后检查来源')
            + '</code><strong>' + executionDuration(candidate) + '</strong> '
            + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-execution-locate="'
            + escapeRoundHtml(candidate.toolCallId) + '">定位此动作</button></div>';
        }).join('') + '</div></details>';
    }
    html += '</article>';
  });
  if (block) html += '</div></section>';
  if (discloseWork) html += '</details>';
  var coverage = '已测工具 ' + diag.measuredTools + ' / ' + diag.totalTools
    + (diag.workloadGroups > 8 ? '；仅展示 ' + diag.workloadGroups + ' 组中的前 8 组（上下文分块，非全局榜）' : '')
    + '；未参与可信累计比较 ' + (diag.unrankedTools || 0) + ' 次（缺测或上下文/口径未确认）';
  var measurement = coverage
    + '；已测工作量之和 ' + (diag.measuredTools ? escapeRoundHtml(durationLabel(diag.measuredWorkMs)) : '无可用时长')
    + '，全范围可含不同上下文/口径，不据此混榜；不是墙钟时间或关键路径。模型耗时未测量；— 表示来源未知，不是零。'
    + '工具结果、wait/poll 返回或子任务完成均不证明整个任务完成。日志未明确记录时，异步任务状态未知；'
    + '不能据工具或轮询结果判断其仍在运行或已结束。';
  var failureMeasured = diag.failures > 0 && diag.measuredTools > 0 && workloads.length > 0;
  var basis = compact ? '模型耗时未测量；' + (discloseWork ? '' : '累计非墙钟或关键路径；') + '— 未知，不是零。' : measurement;
  if (unmeasured) basis = '无可用工具时长，不能按耗时判断慢项；先查看下方操作与结果证据。'
    + coverage + '。模型耗时未测量；— 表示来源未知，不是零。工具返回不证明整个任务完成。';
  if (compact && (discloseWork || diag.unrankedTools > 0 || diag.workloadGroups > 8 || diag.measuredTools < diag.totalTools)) {
    basis = coverage + '；' + basis;
  }
  if (failureMeasured) basis = coverage + '。模型耗时未测量；累计非墙钟或关键路径；— 表示来源未知，不是零。'
    + '工具返回不证明整个任务完成；日志未明确记录时，异步任务状态未知。';
  html += '<p class="se-basis">' + (diag.totalTools === 0 ? '模型耗时未测量。' : basis)
    + (discloseWork ? '工具返回不证明整个任务完成。' : '') + '</p>'
    + (hasSubagentWork ? '<p class="se-source-note">委派来源仅当前已展示证据，不代表唯一父级；上下文累计不归属于某次任务。</p>' : '')
    + '<details class="se-measurement"><summary>计量说明</summary>'
    + (diag.totalTools === 0 || compact || unmeasured || failureMeasured ? '<p>' + measurement + '</p>' : '')
    + '<p>卡片已测次数仅计本口径，分母为本上下文同名全部调用；代表动作取本类单次最长。'
    + '仅时长不证明区间重叠或并行，不据此推断根因；来源/kind 详见动作证据。'
    + '模型输入仅限来源记录或本地关联结果，不代表完整 provider context。</p>'
    + (signals && diag.workloadSignals && diag.workloadSignals.candidates.length ? diag.workloadSignals.candidates : workloads).filter(function (work) { return !!work.sameInputMaximum; }).map(function (work) {
      return '<p>' + executionContextMarkup(work) + ' · ' + escapeRoundHtml(work.name) + ' · 输入识别 '
        + work.sameInputMaximum.identifiedInputs + '/' + work.sameInputMaximum.totalInputs
        + '；按来源完整参数记录比较，不证明业务操作或环境相同。</p>';
    }).join('')
    + (diag.longestByName || []).map(function (tool) { return '<p>' + escapeRoundHtml(tool.name) + ' · '
      + escapeRoundHtml(tool.observation ? tool.observation.kind : '口径未记录') + '</p>'; }).join('') + '</details>';
  setExecutionDiagnosis(html);
  // 仅延续重建前仍在本范围指标上的焦点，不复活已离开的阅读意图。
  if (focusedMetric && append !== undefined && focusedSignalKey === executionView.signalKey) {
    var replacement = summary.querySelector('[data-execution-signal-metric="' + focusedMetric + '"]');
    if (replacement) replacement.focus({ preventScroll: true });
  }
  syncExecutionDelegationSources();
  syncHotspotReturnNavigation();
  syncMainSourceTimingEntry();
  // Retain only an already visible, still-focused valid card across this synchronous layout change.
  if (timingTop !== null && timingCard.isConnected && document.activeElement === timingCard && syncMainSourceTimingEntry()) {
    var updatedTimingRect = timingCard.getBoundingClientRect();
    if (updatedTimingRect.top < 0 || updatedTimingRect.bottom > innerHeight) window.scrollBy(0, updatedTimingRect.top - timingTop);
  }
}

function loadExecutionPage(params, append) {
  syncMainSourceTimingEntry();
  var signalInteraction = executionView.signalInteraction;
  var epoch = append ? executionView.epoch : ++executionView.epoch;
  // 新范围不再拥有旧游标。移除旧 pager，使其外层错误/loading 回调仅触及离线节点。
  if (!append) {
    if ((executionView.renderedAgent || '') !== executionView.agent) {
      document.querySelector('[data-execution-items]').textContent = '正在读取所选上下文的过程…';
      setExecutionDiagnosis('正在读取所选上下文的诊断，尚不能判断。', true);
    }
    var pagerHost = document.querySelector('[data-execution-pagination]');
    if (pagerHost) pagerHost.replaceChildren();
  }
  var query = new URLSearchParams(Object.assign({ status: executionView.status, agent_context: executionView.agent }, params));
  return readSessionContentPage(getApiBase() + '/execution?' + query).then(function (page) {
    if (epoch !== executionView.epoch) return;
    applyExecutionPage(page, append);
    // 更后的指标操作只撤销旧定位的滚动/聚焦，不丢弃合法返回的数据。
    if (params.target && signalInteraction === executionView.signalInteraction) {
      var target = document.querySelector('[data-execution-tool="' + cssEscape(params.target) + '"]')
        || document.querySelector('[data-execution-group="' + cssEscape(params.target) + '"]');
      if (target) { target.scrollIntoView({ block: 'center' }); target.focus(); }
    }
  }).catch(function (error) {
    // 也保护入口深链和通用 pager 的外层失败回调；当前失败仍原样交给 Retry/Refresh。
    if (epoch !== executionView.epoch) return;
    throw error;
  });
}

document.addEventListener('click', function (event) {
  if (event.target.closest('[data-main-source-timing-open]')) {
    if (!syncMainSourceTimingEntry()) return;
    var card = document.querySelector('[data-session-timing]');
    if (!card) return;
    executionView.signalInteraction = (executionView.signalInteraction || 0) + 1;
    for (var parent = card.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    card.focus(); card.scrollIntoView({ block: 'center' });
    return;
  }
  var metric = event.target.closest('[data-execution-signal-metric]');
  if (metric) {
    executionView.signalInteraction = (executionView.signalInteraction || 0) + 1;
    executionView.signalMetric = metric.dataset.executionSignalMetric;
    executionView.signalKey = JSON.stringify([executionView.agent, document.body.getAttribute('data-index-generation') || '']);
    var section = metric.closest('[data-execution-long-operations]');
    section.querySelectorAll('[data-execution-signal-metric]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(button === metric));
    });
    setMarkup(section.querySelector('[data-execution-signal-content]'), executionSignalContent(executionView.page.diagnostics, !!document.querySelector('[data-execution-workload-details]')));
    syncHotspotReturnNavigation();
    return;
  }
  var locate = event.target.closest('[data-execution-locate]');
  var filter = event.target.closest('[data-execution-filter]');
  if (!locate && !filter) return;
  executionView.status = filter ? filter.dataset.executionFilter : 'all';
  document.querySelectorAll('[data-execution-filter]').forEach(function (button) {
    button.setAttribute('aria-pressed', String(button.dataset.executionFilter === executionView.status));
  });
  var params = locate ? { target: locate.dataset.executionLocate } : {};
  var status = document.querySelector('[data-execution-status]');
  status.textContent = '正在加载摘要…';
  var pending = loadExecutionPage(params, false);
  var epoch = executionView.epoch;
  pending.then(function () {
    if (epoch !== executionView.epoch) return;
    status.textContent = '';
    var url = new URL(location.href);
    if (locate) url.searchParams.set('execution', params.target);
    else url.searchParams.delete('execution');
    history.replaceState({}, '', url);
  }).catch(function (error) {
    if (epoch !== executionView.epoch) return;
    status.textContent = error.message + ' · ';
    var retry = document.createElement('button');
    retry.type = 'button';
    retry.textContent = /refresh/i.test(error.message) ? 'Refresh page' : 'Retry';
    retry.onclick = function () {
      if (epoch !== executionView.epoch) return;
      if (/refresh/i.test(error.message)) location.reload(); else (locate || filter).click();
    };
    status.appendChild(retry);
  });
});

/* Payload 保留独立入口；打开后才请求索引，完整内容仍逐项惰性读取。 */
function loadExecutionPayloadIndex(cursor, append) {
  var host = document.querySelector('[data-payload-index]');
  if (!host) return Promise.resolve();
  if (!cursor && host.dataset.loaded === 'true') return Promise.resolve();
  if (host.loadingPromise) return host.loadingPromise;
  host.loadingPromise = readSessionContentPage(getApiBase() + '/payloads' + (cursor ? '?cursor=' + encodeURIComponent(cursor) : '')).then(function (page) {
    if (!append) host.replaceChildren();
    var block = document.createElement('div');
    setMarkup(block, (page.payloads || []).map(function (entry) {
      return '<p>' + contentPayloadButton(entry.payloadId, entry.kind, entry.title, /request/.test(entry.kind) ? '模型输入' : '模型输出', '')
        + ' <code>' + escapeRoundHtml(entry.callId || '') + '</code></p>';
    }).join('') || '<p>没有可用的载荷索引。</p>');
    host.appendChild(block);
    var previous = host.querySelector('[data-content-pagination="payloads"]');
    if (previous) previous.remove();
    contentPager(host, 'payloads', host.querySelectorAll('[data-payload-id]').length, page.total ?? page.payloadCount, page.nextCursor, function (next) {
      return loadExecutionPayloadIndex(next, true);
    });
    host.dataset.loaded = 'true';
  }).finally(function () { host.loadingPromise = null; });
  return host.loadingPromise;
}

function showPayloadIndexError(error) {
  var host = document.querySelector('[data-payload-index]');
  host.textContent = '原文索引加载失败：' + error.message + ' · ';
  var button = document.createElement('button');
  button.type = 'button';
  button.className = 'sd-btn sd-btn--secondary sd-btn--md';
  button.textContent = /refresh/i.test(error.message) ? 'Refresh page' : 'Retry';
  button.onclick = function () {
    if (/refresh/i.test(error.message)) location.reload();
    else loadExecutionPayloadIndex().catch(showPayloadIndexError);
  };
  host.appendChild(button);
}
