/* 只消费冻结范围的事实窗口；不爬 execution 或原文拼关系。 */
var collaborationView = { epoch: 0, selection: '', view: 'delegations', page: null, returnFocus: null, hotspotReturn: null, labels: new Map(), sourceStatus: 'loading', attention: null, evidence: null, attentionReturn: null, intent: 0 };
var collaborationReasons = {
  explicit_parent_tool: '由 child 的明确父工具字段确认关系',
  child_candidate_available: '存在明确 child 候选；是否已采集以冻结上下文为准',
  child_not_found: '未找到唯一 child 来源', single_file_not_included: '单文件导入未包含 child，不表示未运行',
  child_link_conflict: 'child 关联冲突', target_unknown: '目标身份未确认', actor_unknown: '发起者身份未确认',
  conflicting_tool_identity: '工具身份冲突，未选择任一目标', explicit_target: '明确操作目标',
  queued: '工具报告已排队接受', explicit_error: '工具报告提交错误',
  invalid_target: '追加输入目标格式未确认', invalid_input: '追加输入参数未确认',
  explicit_report: '明确的本次结果报告', report_status_unknown: '报告状态未确认', conflicting_report: '本次报告冲突',
  anonymous_sidechain: '匿名独立上下文，不是可确认的 provider 实例', main_context: '主上下文', explicit_instance: '明确实例',
  targets_truncated: '目标事实已触及资源边界', facts_truncated: '事实已触及资源边界',
  identity_resource_limit: '身份字段超过资源边界', protocol_payload_resource_limit: '协议摘要超过解析预算；原载荷仍可按需查看',
  SUBAGENT_DISCOVERY_TRUNCATED: 'child 候选发现截断', SUBAGENT_COLLECTION_TRUNCATED: 'child 采集截断',
  SUBAGENT_CYCLE: 'child 来源循环', SUBAGENT_IDENTITY_CONFLICT: 'child 身份冲突',
  SUBAGENT_SPAWN_AMBIGUOUS: '委派关联不唯一', SUBAGENT_SPAWN_UNMATCHED: '委派没有匹配来源'
};

function isCollaborationInputError(row) {
  return row?.kind === 'input' && row.phase === 'result_report' && row.reason === 'explicit_error';
}

function invalidateCollaborationAttention() {
  collaborationView.attention = null;
  collaborationView.evidence = null;
  collaborationView.attentionReturn = null;
  collaborationView.intent++;
  var slot = document.querySelector('[data-collaboration-attention]');
  if (slot) { slot.replaceChildren(); slot.hidden = true; }
}

function acceptCollaborationAttention(page) {
  var count = page.inputSubmissionErrorReportTotal, ref = page.firstInputSubmissionError;
  // Missing/invalid authority is not zero, nor evidence against a known same-generation summary.
  if (!Number.isSafeInteger(count) || count < 0 || count === 0 && ref !== null || count > 0 && (!ref || typeof ref.cursor !== 'string'
      || !ref.cursor || !Number.isSafeInteger(ref.exchangeOffset) || ref.exchangeOffset < 0)) return;
  var previous = collaborationView.attention;
  var summary = { count: count, ref: ref, generation: document.body.getAttribute('data-index-generation'), api: getApiBase(),
    limited: Object.keys(page.reasons || {}).some(function (key) { return /truncat|limit|TRUNCATED|CONFLICT|CYCLE/.test(key); }) };
  collaborationView.attention = summary;
  var slot = document.querySelector('[data-collaboration-attention]');
  if (!slot) return;
  if (!count) { slot.replaceChildren(); slot.hidden = true; return; }
  // Keep the actual entry node, including an active return source, across same-scope publications.
  if (previous && previous.count === count && previous.ref?.cursor === ref.cursor && previous.limited === summary.limited
      && !slot.hidden) return;
  slot.hidden = false; slot.classList.add('sc-attention');
  setMarkup(slot, '<p>全冻结范围已记录' + count + '条明确追加输入提交错误。不是工具执行失败、排队接受或整个任务结论。'
    + (summary.limited ? '范围存在截断/解析或身份限制，仅表示已记录事实。' : '') + '</p>'
    + collaborationButton('data-collaboration-attention-open', '', '查看首条提交错误'));
}

function validCollaborationAttentionReturn() {
  var saved = collaborationView.attentionReturn;
  if (!saved?.source?.isConnected || saved.generation !== document.body.getAttribute('data-index-generation')
      || saved.api !== getApiBase()) { collaborationView.attentionReturn = null; return null; }
  return saved.source;
}

// This intent is separate from execution's source tuple and hotspot history.
['click', 'focusin', 'wheel', 'touchstart', 'keydown'].forEach(function (type) {
  document.addEventListener(type, function () { collaborationView.intent++; }, true);
});

function showCollaborationAttention(source, retrying) {
  var summary = collaborationView.attention;
  if (!summary?.count || summary.api !== getApiBase() || summary.generation !== document.body.getAttribute('data-index-generation')) return;
  if (!retrying) collaborationView.attentionReturn = { source: source, generation: summary.generation, api: summary.api };
  collaborationView.view = 'exchanges'; collaborationView.selection = '';
  var host = document.querySelector('[data-collaboration]'), status = document.querySelector('[data-collaboration-status]');
  host.textContent = '正在读取首条明确追加输入提交错误…';
  status.textContent = '';
  var intent = collaborationView.intent;
  var pending = loadCollaborationPage(summary.ref.cursor, false, { start: summary.ref.exchangeOffset });
  var epoch = collaborationView.epoch;
  return pending.then(function () {
    if (epoch !== collaborationView.epoch) return;
    status.textContent = '';
    if (intent === collaborationView.intent) focusCollaborationTarget(host.querySelector('[data-collaboration-relation]'));
  }).catch(function (error) {
    if (epoch !== collaborationView.epoch) return;
    host.textContent = '无法确认提交错误证据；未打开其他记录或原文。';
    showCollaborationError(error, function () {
      if (epoch === collaborationView.epoch && validCollaborationAttentionReturn()) showCollaborationAttention(source, true);
    });
  });
}

function collaborationButton(attr, value, text) {
  return '<button type="button" class="sd-btn sd-btn--secondary sd-btn--md" ' + attr + '="'
    + escapeRoundHtml(value) + '">' + escapeRoundHtml(text) + '</button>';
}

// 记录类型显式分支；未认识的协议不能借用等待语义。
function collaborationFactLabel(row) {
  if (row.kind === 'delegate') return row.phase === 'result_report' ? '委派工具返回目标 ID' : '委派给';
  if (row.kind === 'input') return row.phase === 'result_report' ? '追加输入提交回执' : '追加输入';
  if (row.kind === 'wait') return row.phase === 'result_report' ? '等待工具本次目标报告' : '等待';
  return row.phase === 'result_report' ? '协作工具本次报告' : '协作操作';
}

// 新保护窗只使用后端唯一工具资格；Result 是工具级全部结果，不是单次回执。
function collaborationProtected() { return collaborationView.page?.evidenceWindow === 'input_submission_error'; }

function collaborationToolEvidence(row, result) {
  if (row.toolPayloadState !== 'unique') return '<span class="se-basis">'
    + (row.toolPayloadState === 'ambiguous' ? '原文无法唯一定位' : '发起记录未确认，原文资格尚未确认') + '</span>';
  return contentPayloadButton('tool:input:' + row.toolId, 'tool_input', '工具 Input 原文', '工具 Input', '')
    + (result ? contentPayloadButton('tool:result:' + row.toolId, 'tool_result', '该工具全部已记录结果；非单一回执或 child 回答', '工具全部已记录 Result', '') : '');
}

function collaborationReport(report) {
  return '<span class="sc-report">#' + report.callIndex + ' · ' + escapeRoundHtml(report.kind === 'delegate' ? '委派工具返回（目标 ID 证据）'
      : report.kind === 'wait' ? (report.phase === 'result_report' ? '等待工具本次报告' + (report.reportedStatus ? '：' + report.reportedStatus : '（状态未知）') : '等待操作')
        : collaborationFactLabel(report)) + ' '
    + (collaborationProtected() ? collaborationToolEvidence(report, report.phase === 'result_report')
      : collaborationButton('data-collaboration-locate', report.toolId, '定位记录')
        + (report.phase === 'result_report' ? contentPayloadButton('tool:result:' + report.toolId, 'tool_result', report.kind === 'delegate' ? '委派工具返回 Result' : '本次报告 Result', report.kind === 'delegate' ? '委派返回 Result' : '报告 Result', '') : '')) + '</span>';
}

function collaborationRelation(row, grouped, creationReceipt, selectedExchange) {
  var delegate = row.kind === 'delegate' && row.phase === 'declaration';
  var delegateReturn = row.kind === 'delegate' && row.phase === 'result_report';
  var input = row.kind === 'input';
  var heading = grouped === true ? 'h4' : 'h3';
  var confirmedSource = delegate && /^subagent:/.test(row.target) && !/^subagent:unknown-sidechain:/.test(row.target)
    && (row.actor === 'main' && row.actorIdentityReason === 'main_context'
      || /^subagent:/.test(row.actor) && !/^subagent:unknown-sidechain:/.test(row.actor) && row.actorIdentityReason === 'explicit_instance')
    && typeof row.callId === 'string' && row.callId.trim() !== '' && !/^(unknown:|observed-input:)/.test(row.callId)
    && !!row.toolId && row.reason !== 'conflicting_tool_identity';
  var html = '<article class="sc-relation" data-collaboration-relation data-collaboration-source="' + escapeRoundHtml(JSON.stringify([row.target, row.actor, row.callId, row.toolId])) + '" data-collaboration-source-label="' + escapeRoundHtml(row.actorLabel + ' · 发起记录 #' + row.callIndex) + '" data-collaboration-source-confirmed="' + String(confirmedSource) + '" tabindex="-1"><' + heading + '>'
    + escapeRoundHtml(row.actorLabel) + (' → ' + escapeRoundHtml(collaborationFactLabel(row)) + ' → ')
    + escapeRoundHtml(row.targetLabel) + '</' + heading + '>';
  if (delegate) html += '<p class="sc-task">任务：' + escapeRoundHtml(row.task) + '</p>';
  else if (delegateReturn) html += selectedExchange ? '<p>创建/目标 ID 归属回执（当前页未配对）；不等同 child 自身回答或任务完成。</p>' : '<p>委派工具返回（创建/目标 ID 证据）；不等同 child 自身回答或任务完成。</p>';
  else if (input && row.phase === 'declaration') html += '<p class="sc-task">追加内容：' + escapeRoundHtml(row.task || '追加内容摘要未安全解析；按需查看追加输入 Input 原文') + '</p>';
  else if (input && row.phase === 'result_report') html += '<p>' + (row.reportedStatus === 'queued' ? '工具报告已排队接受' : row.reason === 'explicit_error' ? '工具报告提交错误' : '提交状态未确认') + '；不证明目标已收到、已采用或任务完成，也不是 child 自身回答。</p>';
  else if (row.phase === 'result_report') html += '<p>' + escapeRoundHtml(collaborationFactLabel(row)) + '：' + escapeRoundHtml(row.reportedStatus || '状态未确认') + '；不是整个任务的永久状态，也不是 child 自身回答或接收确认。</p>';
  var descendants = (collaborationView.page.items || []).some(function (item) { return item.actor === row.target && item.kind === 'delegate'; });
  html += '<p class="sc-origin">' + (grouped === true ? '' : '#' + row.callIndex + ' / ') + escapeRoundHtml(row.toolName) + ' 发起 · '
    + (row.childIncluded ? '已采集该上下文（不代表已完成）' : escapeRoundHtml(input && row.reason === 'explicit_target' ? '明确追加输入目标' : collaborationReasons[row.reason] || row.reason))
    + (row.childIncluded && /unknown|conflict|truncat|limit|CYCLE|AMBIGUOUS|UNMATCHED/.test(row.reason) ? '；' + escapeRoundHtml(input && row.reason === 'explicit_target' ? '明确追加输入目标' : collaborationReasons[row.reason] || row.reason) : '')
    + (row.parentIssue ? '；父关系冲突/循环或未知，不任取树父' : '') + '</p>';
  if (delegate) html += '<p class="se-basis">'
    + (row.reportTotal ? '相关记录 ' + row.reportTotal + ' 条'
      + (row.reportTotal > row.reports.length ? '（仅预览前 ' + row.reports.length + ' / ' + row.reportTotal + ' 条，完整见往来）' : '')
      + '：' + row.reports.map(function (report) {
      return report.kind === 'delegate' && report.phase === 'result_report' ? '创建/目标 ID 返回'
        : report.kind === 'wait' ? (report.phase === 'result_report' ? '等待本次报告：' + (report.reportedStatus || '状态未知') : '等待操作')
          : collaborationFactLabel(report);
    }).join('；') : '未记录可确认的等待/结果报告') + '。'
    + (creationReceipt ? '创建 ID 仅为归属证据，不是 child 回答或任务完成；完整凭证见下方原文与协作证据。' : '') + '</p>';
  if (row.target && (row.childIncluded || !input && descendants)) html += '<div class="sc-actions">'
    + (row.childIncluded ? collaborationButton('data-collaboration-agent', row.target, '查看 ' + row.targetLabel + ' 的过程与耗时') : '')
    + (descendants && (!input || row.childIncluded) ? collaborationButton('data-collaboration-branch', row.target, '查看此 Agent 发起的委派') : '') + '</div>';
  html += '<details class="se-evidence" data-collaboration-evidence><summary>原文、定位与完整协作证据</summary><div class="se-evidence__body"><p>'
    + (collaborationProtected() ? collaborationToolEvidence(row, row.phase === 'result_report') : (
      collaborationButton('data-collaboration-locate', row.toolId, '定位发起工具')
    + collaborationButton('data-collaboration-locate', row.callId, '定位发起记录')
    + contentPayloadButton('tool:input:' + row.toolId, 'tool_input', input ? '追加输入 Input 原文' : '任务 Input 原文', input ? '追加输入 Input' : delegate ? '任务 Input' : '操作 Input', '')
    + (row.phase === 'result_report' ? contentPayloadButton('tool:result:' + row.toolId, 'tool_result', input ? '追加输入提交回执 Result' : delegateReturn ? '委派工具返回 Result' : '本次报告 Result', input ? '提交回执 Result' : delegateReturn ? '委派返回 Result' : '报告 Result', '') : ''))) + '</p>';
  if (collaborationProtected()) html += '<p class="se-basis">Result 为该工具全部已记录结果，不是单一回执独占正文或 child 回答。</p>';
  if (row.target && (!input || row.childIncluded)) html += '<div class="sc-actions">'
    + (!descendants ? collaborationButton('data-collaboration-branch', row.target, '查看此 Agent 发起的委派') : '')
    + collaborationButton('data-collaboration-exchanges', row.target, '查看相关往来') + '</div>';
  if (delegate) html += '<div class="sc-reports">' + row.reports.map(collaborationReport).join('')
    + (row.reportTotal > row.reports.length ? '<p>仅列前 ' + row.reports.length + ' / ' + row.reportTotal + ' 条；完整记录见相关往来。</p>' : '') + '</div>';
  if (creationReceipt) html += collaborationCreationEvidence(creationReceipt);
  html += '<p>' + escapeRoundHtml(input && row.reason === 'explicit_target' ? '明确追加输入目标' : collaborationReasons[row.reason] || row.reason) + '</p><p>发起上下文：'
    + escapeRoundHtml(row.actor) + '；目标：' + escapeRoundHtml(row.target || '未知') + '</p><p>来源：' + escapeRoundHtml(row.sourceLocator)
    + '</p><p>发起者依据：' + escapeRoundHtml(collaborationReasons[row.actorIdentityReason] || row.actorIdentityReason)
    + '。结果后续输入关联：' + escapeRoundHtml(row.consumer || '未记录')
    + '；不是已接收/已采用确认。工具返回 ID、等待报告和 child 回答是不同证据；回传接收方未确认。</p></div></details></article>';
  return html;
}

// 完整回执留在任务原有 evidence 内；不是第二张任务卡，也不借目标聚合预览代替它。
function collaborationCreationEvidence(row) {
  return '<section data-collaboration-creation-evidence><h4>创建/目标 ID 归属回执</h4><p>记录类型：'
    + escapeRoundHtml(row.kind) + ' / ' + escapeRoundHtml(row.phase) + '；不是 child 回答、任务完成或接收确认。</p><p>发起上下文：'
    + escapeRoundHtml(row.actor) + '；目标：' + escapeRoundHtml(row.target) + '</p><p>发起记录：'
    + escapeRoundHtml(row.callId) + '；工具：' + escapeRoundHtml(row.toolId) + '</p><p>来源：'
    + escapeRoundHtml(row.sourceLocator) + '</p><p>发起者依据：'
    + escapeRoundHtml(collaborationReasons[row.actorIdentityReason] || row.actorIdentityReason) + '；关联依据：'
    + escapeRoundHtml(collaborationReasons[row.reason] || row.reason) + '</p><p>结果后续输入关联：'
    + escapeRoundHtml(row.consumer || '未记录') + '；不是已接收/已采用确认。回传接收方未确认。</p><p>'
    + (collaborationProtected() ? collaborationToolEvidence(row, true) : (
      collaborationButton('data-collaboration-locate', row.toolId, '定位回执工具')
    + collaborationButton('data-collaboration-locate', row.callId, '定位回执发起记录')
    + contentPayloadButton('tool:result:' + row.toolId, 'tool_result', '创建归属回执 Result', '创建回执 Result', '')))
    + '</p></section>';
}

// 只配所选往来当前页相邻且唯一的完整四元组；不拼页、不重排，不用 childIncluded 证明身份。
function collaborationSelectedExchanges(rows) {
  function key(row) { return JSON.stringify([row.actor, row.callId, row.toolId, row.target]); }
  function confirmed(row) {
    var identity = row.actor === 'main' && row.actorIdentityReason === 'main_context'
      || /^subagent:.+/.test(row.actor) && !/^subagent:unknown-sidechain:/.test(row.actor) && row.actorIdentityReason === 'explicit_instance';
    return identity && /^subagent:.+/.test(row.target) && !/^subagent:unknown-sidechain:/.test(row.target)
      && [row.actor, row.callId, row.toolId, row.target].every(function (value) { return typeof value === 'string' && value.trim() !== ''; })
      && !/^(unknown:|observed-input:)/.test(row.callId) && !row.parentIssue
      && (row.reason === 'explicit_parent_tool' || row.reason === 'child_candidate_available');
  }
  var counts = new Map();
  rows.forEach(function (row) {
    if (row.kind !== 'delegate' || row.phase !== 'declaration' && row.phase !== 'result_report') return;
    var count = counts.get(key(row)) || { declaration: 0, result_report: 0 }; count[row.phase]++; counts.set(key(row), count);
  });
  var html = '';
  for (var i = 0; i < rows.length; i++) {
    var row = rows[i], next = rows[i + 1], count = counts.get(key(row));
    if (row.kind === 'delegate' && row.phase === 'declaration' && confirmed(row)
        && next && next.kind === 'delegate' && next.phase === 'result_report' && confirmed(next)
        && key(row) === key(next) && count.declaration === 1 && count.result_report === 1) {
      html += collaborationRelation(row, false, next); i++;
    } else html += collaborationRelation(row, false, null, true);
  }
  return html;
}

// 仅当前页的连续明确声明；不排序，也不和先前页尾拼组。
function collaborationDelegations(rows) {
  function confirmed(row) {
    var actor = row.actorIdentityReason === 'main_context' && row.actor === 'main'
      || row.actorIdentityReason === 'explicit_instance' && /^subagent:/.test(row.actor)
        && !/^subagent:unknown-sidechain:/.test(row.actor);
    return row.kind === 'delegate' && row.phase === 'declaration' && actor
      && typeof row.callId === 'string' && row.callId.trim() !== ''
      && !/^(unknown:|observed-input:)/.test(row.callId);
  }
  var html = '';
  for (var start = 0; start < rows.length;) {
    var row = rows[start];
    if (!confirmed(row)) { html += collaborationRelation(row, false); start++; continue; }
    var end = start + 1;
    while (end < rows.length && confirmed(rows[end])
        && rows[end].actor === row.actor && rows[end].callId === row.callId) end++;
    var title = row.actorLabel + ' · 发起记录 #' + row.callIndex + ' · 此处显示 ' + (end - start) + ' 项委派';
    html += '<section class="sc-response-group" data-collaboration-response-group aria-label="'
      + escapeRoundHtml(title) + '"><h3>' + escapeRoundHtml(title) + '</h3>'
      + rows.slice(start, end).map(function (member) { return collaborationRelation(member, true); }).join('') + '</section>';
    start = end;
  }
  return html;
}

// Only explicit navigation reveals native disclosure ancestors; background sync never opens them.
function focusCollaborationTarget(target) {
  if (!target || !target.isConnected) return;
  for (var parent = target.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === 'DETAILS') parent.open = true;
  }
  target.focus();
  target.scrollIntoView({ block: 'center' });
}

// 只复用当前 DOM 中仍有效的来源；没有历史时保留诚实的概览入口。
// Hotspot → collaboration history is independent of collaboration → execution history.
function validHotspotReturnSource() {
  var saved = collaborationView.hotspotReturn;
  var source = saved?.source;
  if (!source?.isConnected || !source.closest('[data-execution-long-operations]')
      || source.dataset.collaborationExchanges !== saved.key
      || saved.generation !== document.body.getAttribute('data-index-generation')) {
    collaborationView.hotspotReturn = null;
    return null;
  }
  return source;
}

function syncHotspotReturnNavigation() {
  var host = document.querySelector('[data-collaboration]');
  if (!host) return;
  var button = host.querySelector('[data-collaboration-hotspot-return]');
  if (!validHotspotReturnSource()) { if (button) button.remove(); return; }
  if (!button) {
    button = document.createElement('button');
    button.type = 'button'; button.className = 'sd-btn sd-btn--secondary sd-btn--md';
    button.setAttribute('data-collaboration-hotspot-return', '');
    button.textContent = '返回耗时位置';
    (host.querySelector('.sc-actions') || host).appendChild(button);
  }
}

function syncExecutionCollaborationNavigation() {
  syncHotspotReturnNavigation();
  var button = document.querySelector('[data-execution-collaboration-return]');
  if (!button) return;
  var host = document.querySelector('[data-collaboration]');
  var source = collaborationView.returnFocus;
  if (source && (!collaborationView.page || !source.isConnected || !host?.contains(source))) collaborationView.returnFocus = source = null;
  var overview = collaborationView.page?.exchangeTotal ? host?.querySelector('[data-collaboration-context]') : null;
  button.hidden = !source && !overview;
  button.textContent = source ? '返回协作位置' : '查看 Agent 协作';
}

function applyCollaborationPage(page, append) {
  collaborationView.page = page;
  acceptCollaborationAttention(page);
  // 往来窗口也可含明确委派声明；资格仍由当前 DOM 的完整身份保护。
  collaborationView.sourceStatus = page.view === 'delegations' || page.view === 'exchanges' ? 'ready' : 'unavailable';
  (page.participants || []).forEach(function (p) { collaborationView.labels.set(p.key, p.label); });
  (page.items || []).forEach(function (row) {
    if (row.actor) collaborationView.labels.set(row.actor, row.actorLabel);
    if (row.target) collaborationView.labels.set(row.target, row.targetLabel);
    if (row.key) collaborationView.labels.set(row.key, row.label);
  });
  syncExecutionContextLabels();
  var host = document.querySelector('[data-collaboration]');
  if (!host) return;
  if (!page.exchangeTotal) {
    host.classList.remove('sc-panel');
    setMarkup(host, '<p class="se-basis">当前记录未提供可确认的协作关联；不按 Agent 名称、时间或消息正文猜测。Qoder / 裸名 send_input 等未证实协议不生成关联。</p>');
    syncExecutionDelegationSources();
    syncExecutionCollaborationNavigation();
    return;
  }
  host.classList.add('sc-panel');
  if (!append) {
    setMarkup(host, '<h2>Agent 协作</h2><p class="se-collaboration-layout-note">独立展示当前协作范围，不与左侧逐行对应；范围见下方导航。</p><p class="se-basis">' + page.participantTotal + ' 个参与上下文 · '
      + page.delegationTotal + ' 条委派 · ' + page.exchangeTotal + ' 条协作事实。仅委派组成支路；等待/本次报告不是完成或消息接收证明。</p>'
      + Object.keys(page.reasons).filter(function (key) { return /truncat|limit|TRUNCATED|CONFLICT|CYCLE/.test(key); }).map(function (key) { return '<p class="se-basis">' + escapeRoundHtml(collaborationReasons[key] || key) + '：' + page.reasons[key] + '</p>'; }).join('')
      + '<nav class="sc-actions" aria-label="协作支路">'
      + collaborationButton('data-collaboration-root', '', '全部委派（默认两层）')
      + collaborationButton('data-collaboration-all-exchanges', '', '全部协作往来' + (page.inputDeclarationTotal > 0 ? '（含追加输入声明' + page.inputDeclarationTotal + '条）' : ''))
      + collaborationButton('data-collaboration-participants', '', '参与者与深层入口') + '</nav>'
      + (validCollaborationAttentionReturn() ? collaborationButton('data-collaboration-attention-return', '', '返回提交错误关注位置') : '')
      + '<p class="sc-breadcrumb" data-collaboration-context tabindex="-1">'
      + (page.selection ? '全部 → 所选上下文：' + executionAgentMarkup(page.selection) + ' · ' : '')
      + ({ delegations: page.selection ? '该上下文发起的委派' : '全部委派', exchanges: '协作往来', participants: '参与上下文' })[page.view] + '</p>'
      + (page.view === 'delegations' ? '<p class="se-basis">按当前页连续的同一发起记录分组；项数仅当前已载，不代表完整批次，不表示并行。</p>' : '')
      + '<div data-collaboration-items></div><div data-collaboration-pagination></div>'
      + '<details class="se-evidence"><summary>采集与关联原因</summary><div class="se-evidence__body">'
      + (page.selection ? '<p>所选上下文完整身份：' + escapeRoundHtml(page.selection) + '</p>' : '')
      + Object.keys(page.reasons).map(function (key) { return '<p>' + escapeRoundHtml(collaborationReasons[key] || key) + '：' + page.reasons[key] + '</p>'; }).join('')
      + '<p>父等待与 child 执行在各自上下文查看，不相加为墙钟或模型耗时。在线协作筛选不承诺离线交互；静态档案仍保留原文。</p></div></details>');
  }
  var items = host.querySelector('[data-collaboration-items]');
  var block = document.createElement('div');
  setMarkup(block, page.view === 'participants' ? page.items.map(function (participant) {
    return '<div class="sc-participant">' + escapeRoundHtml(participant.label) + ' · '
      + (participant.included ? collaborationButton('data-collaboration-agent', participant.key, '查看过程与耗时') : '冻结内容未包含过程')
      + collaborationButton('data-collaboration-branch', participant.key, '发起的委派')
      + collaborationButton('data-collaboration-exchanges', participant.key, '相关往来')
      + '<details class="se-evidence"><summary>完整身份</summary><p>' + escapeRoundHtml(participant.key) + '</p></details></div>';
  }).join('') : page.view === 'delegations' ? collaborationDelegations(page.items)
    : page.selection ? collaborationSelectedExchanges(page.items)
      : page.items.map(function (row) { return collaborationRelation(row, false); }).join(''));
  if (!page.items.length) block.textContent = page.view === 'delegations' && page.selection
    ? '未记录该上下文发起的明确委派，不代表没有工作。可从全部协作往来核对任务、输入或报告。'
    : page.view === 'delegations' && page.inputDeclarationTotal > 0
    ? '未记录创建委派；已记录的追加输入请从全部协作往来查看。不代表没有工作。'
    : '此支路未记录明确委派/往来；不代表没有工作。可返回全部或查看其他参与者。';
  items.appendChild(block);
  var pager = host.querySelector('[data-collaboration-pagination]');
  pager.replaceChildren();
  var epoch = collaborationView.epoch;
  contentPager(pager, 'collaboration', page.offset + page.items.length, page.total, page.nextCursor, function (cursor) {
    if (epoch !== collaborationView.epoch) return Promise.resolve();
    return loadCollaborationPage(cursor, true);
  });
  var summary = pager.querySelector('span');
  syncExecutionDelegationSources();
  syncExecutionCollaborationNavigation();
  summary.textContent = collaborationProtected() ? '已载事实 ' + (collaborationView.evidence.start + 1) + '–' + (page.offset + page.items.length) + ' / ' + page.total + '；从错误定位处开始，未载前段 ' + collaborationView.evidence.start + ' 条，不是全量。' : '已展示至 ' + (page.offset + page.items.length) + ' / ' + page.total
    + (page.view === 'exchanges' && page.selection ? ' 条事实；当前已载 ' + items.querySelectorAll('[data-collaboration-relation]').length + ' 张主卡' : '')
    + (page.view === 'delegations' && !page.selection ? '（默认两层；完整 ' + page.delegationTotal + ' 条，深层从参与者/支路进入）' : '') + '。';
}

// 只桥接当前DOM已展示的明确声明；完整四元身份定位，不读取额外页面或正文。
function syncExecutionDelegationSources() {
  var ready = collaborationView.sourceStatus === 'ready';
  var rows = ready ? Array.from(document.querySelectorAll('[data-collaboration-source-confirmed="true"]')) : [];
  document.querySelectorAll('[data-execution-delegation-sources]').forEach(function (host) {
    var key = host.dataset.executionDelegationSources;
    var matches = rows.filter(function (node) { return JSON.parse(node.dataset.collaborationSource)[0] === key; });
    var unique = new Map();
    matches.forEach(function (node) { unique.set(node.dataset.collaborationSource, node); });
    var items = Array.from(unique.values());
    var status = collaborationView.sourceStatus;
    var text = status === 'loading' ? '已加载委派来源：读取中，旧来源已撤销。'
      : status === 'failed' ? '已加载委派来源：读取失败，请在协作区重试。'
      : status === 'unavailable' ? '已加载委派来源：当前视图不提供委派来源。'
      : !items.length ? '已加载委派来源：当前已载关系无可确认来源，不代表没有委派。'
      : '已加载委派来源 ' + items.length + ' 条';
    var retained = new Map(Array.from(host.querySelectorAll('button')).map(function (button) {
      return [button.dataset.executionDelegationSource, button];
    }));
    var wanted = items.slice(0, 3).map(function (node) { return node.dataset.collaborationSource; });
    var signature = JSON.stringify([text, wanted, items.slice(0, 3).map(function (node) { return node.dataset.collaborationSourceLabel; })]);
    if (host.dataset.sourceSignature === signature) return;
    host.dataset.sourceSignature = signature;
    var label = host.querySelector('p') || document.createElement('p');
    label.textContent = text + (items.length > 3 ? '；仅列前 3 条，另 ' + (items.length - 3) + ' 条见协作区。' : '');
    if (!label.isConnected) host.appendChild(label);
    retained.forEach(function (button, identity) { if (!wanted.includes(identity)) button.remove(); });
    items.slice(0, 3).forEach(function (node, index) {
      var identity = node.dataset.collaborationSource;
      var button = retained.get(identity) || document.createElement('button');
      button.type = 'button'; button.className = 'sd-btn sd-btn--secondary sd-btn--md';
      button.dataset.executionDelegationSource = identity;
      button.textContent = (items.length > 1 ? '来源 ' + (index + 1) + ' · ' : '') + node.dataset.collaborationSourceLabel + ' · 定位任务关系';
      if (!button.isConnected) host.appendChild(button);
    });
  });
}

function loadCollaborationPage(cursor, append, evidence) {
  if (!append) {
    collaborationView.evidence = evidence || null;
    if (!evidence) collaborationView.attentionReturn = null;
  }
  evidence = collaborationView.evidence;
  var generation = document.body.getAttribute('data-index-generation');
  var epoch = append ? collaborationView.epoch : ++collaborationView.epoch;
  collaborationView.sourceStatus = 'loading';
  syncExecutionDelegationSources();
  if (!append) {
    collaborationView.returnFocus = null;
    syncExecutionCollaborationNavigation();
    var pager = document.querySelector('[data-collaboration-pagination]');
    if (pager) pager.replaceChildren();
  }
  var query = new URLSearchParams({ view: collaborationView.view, selection: collaborationView.selection });
  if (evidence) { query.set('view', 'exchanges'); query.set('selection', ''); query.set('limit', '20'); query.set('evidence_window', 'input_submission_error'); }
  if (cursor) query.set('cursor', cursor);
  return readSessionContentPage(getApiBase() + '/collaboration?' + query).then(function (page) {
    if (epoch !== collaborationView.epoch || generation !== document.body.getAttribute('data-index-generation')) return;
    if (!evidence && page.evidenceWindow) throw new Error('无法确认协作窗口，请重试或刷新页面');
    if (evidence && (page.evidenceWindow !== 'input_submission_error' || page.view !== 'exchanges' || page.selection !== ''
        || (!append && (page.offset !== evidence.start || !isCollaborationInputError(page.items?.[0]))))) {
      throw new Error('无法确认提交错误证据窗口，请重试或刷新页面');
    }
    // 宽屏的迟到事实会改变列宽；只补偿仍在阅读的既有动作，不重建节点或焦点。
    var trace = document.querySelector('[data-trace-panel]');
    var anchor = innerWidth >= 1600 && scrollY > 0 && trace?.checkVisibility()
      ? Array.from(trace.querySelectorAll('[data-execution-tool]')).find(function (node) {
        var rect = node.getBoundingClientRect();
        return rect.bottom > 0 && rect.top < innerHeight;
      }) : null;
    var top = anchor?.getBoundingClientRect().top;
    applyCollaborationPage(page, append);
    if (anchor?.isConnected && trace.checkVisibility()) window.scrollBy(0, anchor.getBoundingClientRect().top - top);
  }).catch(function (error) {
    if (epoch !== collaborationView.epoch) return;
    collaborationView.sourceStatus = 'failed';
    syncExecutionDelegationSources();
    throw error;
  });
}

function showCollaborationError(error, retry) {
  var host = document.querySelector('[data-collaboration-status]');
  host.textContent = error.message + ' · ';
  var button = document.createElement('button');
  button.type = 'button';
  button.textContent = /refresh/i.test(error.message) ? 'Refresh page' : 'Retry';
  button.onclick = function () { if (/refresh/i.test(error.message)) location.reload(); else retry(); };
  host.appendChild(button);
}

// 显式读取一个既有往来窗口；范围身份沿原epoch，不缓存或自动翻页。
function showExecutionTaskContext(key, source, focusSource) {
  focusSource = focusSource || source;
  if (source?.matches('[data-execution-task-context]') && source.closest('[data-execution-long-operations]')) {
    collaborationView.hotspotReturn = { source: source, key: key, generation: document.body.getAttribute('data-index-generation') };
  }
  executionView.signalInteraction = (executionView.signalInteraction || 0) + 1;
  collaborationView.view = 'exchanges';
  collaborationView.selection = key;
  var host = document.querySelector('[data-collaboration]');
  var status = document.querySelector('[data-collaboration-status]');
  var scope = '协作往来 · 所选上下文：' + key;
  host.textContent = '正在读取' + scope + '…';
  status.textContent = '正在读取' + scope + '…';
  var focusRequested = true;
  function retainLaterReading(event) {
    if (event.target !== focusSource && !focusSource.contains(event.target)) focusRequested = false;
  }
  document.addEventListener('focusin', retainLaterReading);
  document.addEventListener('click', retainLaterReading);
  var pending = loadCollaborationPage();
  var epoch = collaborationView.epoch;
  return pending.then(function () {
    if (epoch !== collaborationView.epoch) return;
    status.textContent = '';
    var context = host.querySelector('[data-collaboration-context]');
    if (focusRequested && validHotspotReturnSource() === source && context) { context.focus(); context.scrollIntoView({ block: 'center' }); }
  }).catch(function (error) {
    if (epoch !== collaborationView.epoch) return;
    host.textContent = '读取失败：' + scope + '；当前没有此选择的新结果。';
    syncHotspotReturnNavigation();
    showCollaborationError(error, function () {
      if (epoch !== collaborationView.epoch) return;
      showExecutionTaskContext(key, source, status.querySelector('button'));
    });
    var recovery = status.querySelector('button');
    var recover = recovery.onclick;
    recovery.onclick = function () { if (epoch === collaborationView.epoch) recover(); };
  }).finally(function () {
    document.removeEventListener('focusin', retainLaterReading);
    document.removeEventListener('click', retainLaterReading);
  });
}

function selectExecutionAgent(key, label, source) {
  collaborationView.returnFocus = source || null;
  syncExecutionCollaborationNavigation();
  executionView.agent = key;
  executionView.status = 'all';
  var context = document.querySelector('[data-execution-agent-context]');
  setMarkup(context, key ? '所选过程：' + executionAgentMarkup(key) + '；诊断仅限本上下文。' : '全部上下文；耗时按各自口径分块。');
  document.querySelectorAll('[data-execution-filter]').forEach(function (button) {
    button.setAttribute('aria-pressed', String(button.dataset.executionFilter === 'all'));
  });
  // 数据继续读取，但用户已返回协作位置时，不让迟到的选择完成抢回焦点。
  var focusRequested = true;
  function retainReturnedFocus(event) {
    if (event.target.closest('[data-execution-collaboration-return]')) focusRequested = false;
    if (event.target.closest('[data-main-source-timing-open]') && syncMainSourceTimingEntry()) focusRequested = false;
  }
  document.addEventListener('click', retainReturnedFocus);
  var pending = loadExecutionPage({}, false);
  var epoch = executionView.epoch;
  return pending.then(function () {
    if (epoch !== executionView.epoch) return;
    document.querySelector('[data-execution-status]').textContent = '';
    if (!focusRequested) return;
    var diagnosis = document.querySelector('[data-execution-judgment]');
    diagnosis.focus();
    diagnosis.scrollIntoView({ block: 'start' });
  }).catch(function (error) {
    if (epoch !== executionView.epoch) return;
    var status = document.querySelector('[data-execution-status]');
    status.textContent = error.message + ' · ';
    var retry = document.createElement('button');
    retry.textContent = /refresh/i.test(error.message) ? 'Refresh page' : 'Retry';
    retry.onclick = function () {
      if (epoch !== executionView.epoch) return;
      if (/refresh/i.test(error.message)) location.reload(); else selectExecutionAgent(key, label, source);
    };
    status.appendChild(retry);
  }).finally(function () { document.removeEventListener('click', retainReturnedFocus); });
}

document.addEventListener('click', function (event) {
  var button = event.target.closest('button');
  if (!button) return;
  if (button.hasAttribute('data-collaboration-attention-open')) { showCollaborationAttention(button); return; }
  if (button.hasAttribute('data-collaboration-attention-return')) {
    var attentionSource = validCollaborationAttentionReturn();
    if (attentionSource) focusCollaborationTarget(attentionSource);
    return;
  }
  if (button.hasAttribute('data-collaboration-hotspot-return')) {
    var hotspot = validHotspotReturnSource();
    syncHotspotReturnNavigation();
    if (hotspot) focusCollaborationTarget(hotspot);
    return;
  }
  if (button.hasAttribute('data-execution-task-context')) {
    showExecutionTaskContext(button.dataset.collaborationExchanges, button);
    return;
  }
  if (button.hasAttribute('data-execution-delegation-source')) {
    if (collaborationView.sourceStatus !== 'ready') return;
    var relation = Array.from(document.querySelectorAll('[data-collaboration-source-confirmed="true"]')).find(function (node) {
      return node.dataset.collaborationSource === button.dataset.executionDelegationSource;
    });
    if (relation) focusCollaborationTarget(relation);
    return;
  }
  if (button.hasAttribute('data-collaboration-locate')) {
    if (collaborationProtected() && button.closest('[data-collaboration]')) return;
    executionView.agent = '';
    document.querySelector('[data-execution-agent-context]').textContent = '全部上下文 · 已定位协作证据；协作位置可由下方导航查看。';
    var proxy = document.createElement('button');
    proxy.dataset.executionLocate = button.dataset.collaborationLocate;
    document.body.appendChild(proxy);
    proxy.click();
    proxy.remove();
    return;
  }
  if (button.hasAttribute('data-collaboration-agent')) {
    selectExecutionAgent(button.dataset.collaborationAgent, button.closest('article')?.querySelector('h3')?.textContent, button);
    return;
  }
  if (button.hasAttribute('data-execution-agent-reset')) { selectExecutionAgent('', '', null); return; }
  if (button.hasAttribute('data-execution-collaboration-return')) {
    syncExecutionCollaborationNavigation();
    var target = collaborationView.returnFocus || document.querySelector('[data-collaboration-context]');
    if (target) focusCollaborationTarget(target);
    return;
  }
  var root = button.hasAttribute('data-collaboration-root');
  var branch = button.hasAttribute('data-collaboration-branch');
  var exchanges = button.hasAttribute('data-collaboration-exchanges');
  var all = button.hasAttribute('data-collaboration-all-exchanges');
  var participants = button.hasAttribute('data-collaboration-participants');
  if (!root && !branch && !exchanges && !all && !participants) return;
  collaborationView.view = participants ? 'participants' : exchanges || all ? 'exchanges' : 'delegations';
  collaborationView.selection = branch ? button.dataset.collaborationBranch : exchanges ? button.dataset.collaborationExchanges : '';
  var status = document.querySelector('[data-collaboration-status]');
  status.textContent = '正在读取协作事实…';
  var pending = loadCollaborationPage();
  var epoch = collaborationView.epoch;
  function retry() {
    if (epoch !== collaborationView.epoch) return;
    var retried = loadCollaborationPage();
    epoch = collaborationView.epoch;
    retried.then(function () { if (epoch === collaborationView.epoch) status.textContent = ''; })
      .catch(function (error) { if (epoch === collaborationView.epoch) showCollaborationError(error, retry); });
  }
  pending.then(function () {
    if (epoch !== collaborationView.epoch) return;
    status.textContent = '';
    document.querySelector('[data-collaboration-context]')?.focus();
  }).catch(function (error) { if (epoch === collaborationView.epoch) showCollaborationError(error, retry); });
});
