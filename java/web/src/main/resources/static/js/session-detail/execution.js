/* 执行阅读仅请求有界摘要；原文、归因与子上下文继续使用原有惰性入口。 */
var executionView = { page: null, status: 'all', epoch: 0, subagents: new Map() };

function executionDuration(tool) {
  if (tool.durationMs == null) return '<span aria-label="耗时未测量">—</span>';
  if (tool.durationMs === 0 && tool.observation && tool.observation.durationNanos > 0) return '&lt;1ms';
  return escapeRoundHtml(tool.durationMs < 1000 ? tool.durationMs + 'ms' : Number((tool.durationMs / 1000).toFixed(3)) + 's');
}

function executionWorkDuration(value) {
  var nanos = BigInt(value);
  if (nanos === 0n) return '0ms';
  if (nanos < 1000000n) return '&lt;1ms';
  var unit = nanos < 1000000000n ? 1000000n : 1000000000n;
  var fraction = (nanos % unit).toString().padStart(unit === 1000000n ? 6 : 9, '0').replace(/0+$/, '');
  return (nanos / unit).toString() + (fraction ? '.' + fraction : '') + (unit === 1000000n ? 'ms' : 's');
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
  // 本页展示编号按完整 ID 区分，筛选/定位/续页间复用；不截前缀，不推断父链。
  if (!executionView.subagents.has(group.subagentId)) {
    executionView.subagents.set(group.subagentId, executionView.subagents.size + 1);
  }
  return '子 Agent ' + executionView.subagents.get(group.subagentId) + ' · 独立上下文';
}

function executionEvidence(group, tool) {
  var html = '<details class="se-evidence ' + (tool ? 'se-tool-evidence' : 'se-group-evidence') + '"><summary>'
    + (tool ? '证据' : '记录来源') + '</summary><div class="se-evidence__body">';
  if (!tool) {
    html += '<p>本地记录 ' + escapeRoundHtml(group.id) + ' · '
      + escapeRoundHtml(group.scope === 'subagent' ? (group.subagentId || '子 Agent 身份未记录') : '主会话')
      + (group.parentCallId ? ' · 父调用 ' + escapeRoundHtml(group.parentCallId) : '')
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
      current.className = 'se-group';
      current.dataset.executionGroup = group.id;
      current.tabIndex = -1;
      setMarkup(current, '<header><h3>' + escapeRoundHtml(group.label) + (group.index ? ' ' + group.index : '')
        + (item.toolOrdinal > 1 ? '（续 · 工具 ' + item.toolOrdinal + ' 起）' : '')
        + '</h3><span>' + escapeRoundHtml(executionGroupContext(group))
        + (group.response ? ' · 下发 ' + group.toolCount + ' 个工具' : ' · 未观察到模型输出') + '</span>'
        + executionGroupActions(group) + executionEvidence(group, null) + '</header>'
        + (group.preview ? '<p class="se-response-text">' + escapeRoundHtml(group.preview) + '</p>' : ''));
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
    current.appendChild(row);
  });
  if (!items.length && !append) host.textContent = executionView.status === 'failed' ? '此范围没有观察到工具失败。' : '此来源没有可用的执行摘要；可按需检查下方记录证据。';
}

function applyExecutionPage(page, append) {
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
  var summary = document.querySelector('[data-execution-judgment]');
  var diag = page.diagnostics;
  if (!summary || !diag) return;
  var compact = diag.totalTools > 0 && diag.failures === 0 && (diag.workloads || []).length > 0;
  var html = '<h2>执行判断</h2>';
  if (compact) {
    html += '<p class="se-basis">未观察到工具失败；不证明任务成功或记录完整。</p>';
  } else {
    html += '<div class="se-judgments">';
    if (diag.totalTools === 0) {
      html += '<article><h3>此范围未观察到工具调用</h3><p>这不代表没有工作，也不证明任务成功。'
        + '请核对下方可用的模型输出与模型输入；未记录内容以页面标注为准。</p></article>';
    } else html += '<article><h3>' + diag.failures + ' 个工具有失败信号</h3><p>'
      + (diag.failures ? '可用日志中观察到非零退出或错误结果；不等同整个任务失败。' : '可用日志中未观察到工具失败；不证明任务成功或记录完整。') + '</p>'
      + (diag.firstFailureTool ? '<code class="se-diagnosis-command">' + escapeRoundHtml(diag.firstFailureTool.inputPreview || '参数未记录 · 定位后检查结果') + '</code>' : '')
      + (diag.firstFailure ? '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-execution-locate="' + escapeRoundHtml(diag.firstFailure) + '">定位首个失败</button>' : '') + '</article>';
    html += '</div>';
  }
  var block = '';
  (diag.workloads || []).forEach(function (work) {
    var key = JSON.stringify([work.scope, work.subagentId, work.kind]);
    if (key !== block) {
      if (block) html += '</div></section>';
      block = key;
      html += '<section data-execution-workloads><p class="se-basis">' + escapeRoundHtml(executionGroupContext(work))
        + ' · 执行器观测 · 仅本上下文、同口径比较；仅已测，非完整瓶颈，慢不等于异常。</p><div class="se-judgments">';
    }
    var tool = work.longest;
    html += '<article data-execution-workload><h3>' + escapeRoundHtml(work.name) + ' · 已测累计 '
      + executionWorkDuration(work.measuredWorkNanos) + '</h3><p>单次已测最长 ' + executionDuration(tool)
      + ' · 已测 ' + work.measuredTools + '/' + work.totalTools + ' 次'
      + (work.unknownTools ? ' · 未知 ' + work.unknownTools + ' 次' : '')
      + (work.otherKindTools ? ' · 其他/未确认口径 ' + work.otherKindTools + ' 次' : '') + '</p>'
      + '<p>代表动作（不代表同一命令）：</p><code class="se-diagnosis-command">'
      + escapeRoundHtml(tool.inputPreview || '参数未记录 · 定位后检查来源')
      + '</code><button type="button" class="sd-btn sd-btn--secondary sd-btn--md" data-execution-locate="'
      + escapeRoundHtml(tool.toolCallId) + '">定位此动作</button>';
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
  var coverage = '已测工具 ' + diag.measuredTools + ' / ' + diag.totalTools
    + (diag.workloadGroups > 8 ? '；仅展示 ' + diag.workloadGroups + ' 组中的前 8 组（上下文分块，非全局榜）' : '')
    + '；未参与可信累计比较 ' + (diag.unrankedTools || 0) + ' 次（缺测或上下文/口径未确认）';
  var measurement = coverage
    + '；已测工作量之和 ' + (diag.measuredTools ? escapeRoundHtml(durationLabel(diag.measuredWorkMs)) : '无可用时长')
    + '，全范围可含不同上下文/口径，不据此混榜；不是墙钟时间或关键路径。模型耗时未测量；— 表示来源未知，不是零。'
    + '工具结果、wait/poll 返回或子任务完成均不证明整个任务完成。日志未明确记录时，异步任务状态未知；'
    + '不能据工具或轮询结果判断其仍在运行或已结束。';
  var basis = compact ? '模型耗时未测量；累计非墙钟或关键路径；— 未知，不是零。' : measurement;
  if (compact && (diag.unrankedTools > 0 || diag.workloadGroups > 8 || diag.measuredTools < diag.totalTools)) {
    basis = coverage + '；' + basis;
  }
  html += '<p class="se-basis">' + (diag.totalTools === 0 ? '模型耗时未测量。' : basis) + '</p>'
    + '<details class="se-measurement"><summary>计量说明</summary>'
    + (diag.totalTools === 0 || compact ? '<p>' + measurement + '</p>' : '')
    + '<p>卡片已测次数仅计本口径，分母为本上下文同名全部调用；代表动作取本类单次最长。'
    + '仅时长不证明区间重叠或并行，不据此推断根因；来源/kind 详见动作证据。'
    + '模型输入仅限来源记录或本地关联结果，不代表完整 provider context。</p>'
    + (diag.longestByName || []).map(function (tool) { return '<p>' + escapeRoundHtml(tool.name) + ' · '
      + escapeRoundHtml(tool.observation ? tool.observation.kind : '口径未记录') + '</p>'; }).join('') + '</details>';
  setMarkup(summary, html);
}

function loadExecutionPage(params, append) {
  var epoch = append ? executionView.epoch : ++executionView.epoch;
  // 新范围不再拥有旧游标。移除旧 pager，使其外层错误/loading 回调仅触及离线节点。
  if (!append) {
    var pagerHost = document.querySelector('[data-execution-pagination]');
    if (pagerHost) pagerHost.replaceChildren();
  }
  var query = new URLSearchParams(Object.assign({ status: executionView.status }, params));
  return readSessionContentPage(getApiBase() + '/execution?' + query).then(function (page) {
    if (epoch !== executionView.epoch) return;
    applyExecutionPage(page, append);
    if (params.target) {
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
