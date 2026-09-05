  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Token tooltip dynamic positioning ──` */

  var TOOLTIP_FLIP_THRESHOLD = 180; // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`px from bottom of viewport to trigger flip`
  var sessionDetailState = {
    diagnosticsParity: null,
    rounds: [],
    maxRoundTokens: 0
  };

  function positionTokenTooltip(tokenbar) {
    var tooltip = qs(tokenbar, '.token-tooltip');
    if (!tooltip) return;
    var rect = tokenbar.getBoundingClientRect();
    var vpBottom = window.innerHeight || document.documentElement.clientHeight;
    var spaceBelow = vpBottom - rect.bottom;
    var shouldFlip = spaceBelow < TOOLTIP_FLIP_THRESHOLD;
    tooltip.classList.toggle('token-tooltip--flip', shouldFlip);
  }

  function setupTokenTooltips() {
    qsa(document, '.tokenbar-wrap, .sd-sub-tokenbar').forEach(function (bar) {
      bar.addEventListener('mouseenter', function () {
        positionTokenTooltip(bar);
      });
      bar.addEventListener('focusin', function () {
        positionTokenTooltip(bar);
      });
    });
  }

  function positionTokenRoundTooltip(round, event) {
    var tooltip = qs(round, '.sd-token-round-tooltip');
    if (!tooltip) return;

    if (tooltip.getAttribute('data-positioned') !== 'true') {
      tooltip.removeAttribute('data-positioned');
      tooltip.style.removeProperty('--token-round-tooltip-left');
      tooltip.style.removeProperty('--token-round-tooltip-top');
    }
    window.requestAnimationFrame(function () {
      var roundRect = round.getBoundingClientRect();
      var viewportWidth = window.innerWidth || document.documentElement.clientWidth;
      var viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      var viewportMargin = 8;
      var pointerGap = 12;
      var tooltipWidth = tooltip.offsetWidth || 260;
      var tooltipHeight = tooltip.offsetHeight || tooltip.getBoundingClientRect().height;
      var pointerX = event && typeof event.clientX === 'number'
        ? event.clientX
        : roundRect.left + (roundRect.width / 2);
      var pointerY = event && typeof event.clientY === 'number'
        ? event.clientY
        : roundRect.top;
      var spaceLeft = pointerX - viewportMargin;
      var spaceRight = viewportWidth - viewportMargin - pointerX;
      var shouldOpenRight = spaceRight >= spaceLeft;
      var targetLeft = shouldOpenRight
        ? pointerX + pointerGap
        : pointerX - tooltipWidth - pointerGap;
      var minLeft = viewportMargin;
      var maxLeft = viewportWidth - viewportMargin - tooltipWidth;
      if (maxLeft >= minLeft) {
        targetLeft = Math.min(Math.max(targetLeft, minLeft), maxLeft);
      }
      var targetTop = pointerY - tooltipHeight - pointerGap;
      var minTop = viewportMargin;
      var maxTop = viewportHeight - viewportMargin - tooltipHeight;
      if (maxTop >= minTop) targetTop = Math.min(Math.max(targetTop, minTop), maxTop);
      else targetTop = minTop;
      tooltip.style.setProperty(
        '--token-round-tooltip-left',
        Math.round(targetLeft) + 'px'
      );
      tooltip.style.setProperty('--token-round-tooltip-top', Math.round(targetTop) + 'px');
      tooltip.setAttribute('data-positioned', 'true');
    });
  }

  function resetTokenRoundTooltip(round) {
    var tooltip = qs(round, '.sd-token-round-tooltip');
    if (!tooltip) return;
    tooltip.removeAttribute('data-positioned');
    tooltip.style.removeProperty('--token-round-tooltip-left');
    tooltip.style.removeProperty('--token-round-tooltip-top');
  }

  function setupTokenRoundTooltips() {
    qsa(document, '.sd-token-round').forEach(function (round) {
      round.addEventListener('mouseenter', function (event) {
        positionTokenRoundTooltip(round, event);
      });
      round.addEventListener('mousemove', function (event) {
        positionTokenRoundTooltip(round, event);
      });
      round.addEventListener('focusin', function () {
        positionTokenRoundTooltip(round);
      });
      round.addEventListener('mouseleave', function () {
        resetTokenRoundTooltip(round);
      });
      round.addEventListener('focusout', function () {
        resetTokenRoundTooltip(round);
      });
    });
  }

  function hydrateSessionDetailApis() {
    if (!window.fetch || typeof getApiBase !== 'function') return;
    var apiBase = getApiBase();
    if (!apiBase) return;
    var base = apiBase.replace(/\/$/, '');
    Promise.all([
      fetch(base + '/meta', { headers: { 'Accept': 'application/json' } }).then(readSessionJson),
      fetch(base + '/metrics', { headers: { 'Accept': 'application/json' } }).then(readSessionJson),
      fetch(base + '/diagnostics', { headers: { 'Accept': 'application/json' } }).then(readSessionJson),
      fetch(base + '/rounds', { headers: { 'Accept': 'application/json' } }).then(readSessionJson),
      fetch(base + '/payloads', { headers: { 'Accept': 'application/json' } }).then(readSessionJson)
    ]).then(function(parts) {
      applySessionMeta(parts[0]);
      applySessionMetrics(parts[1]);
      applySessionDiagnostics(parts[2]);
      applySessionRounds(parts[3]);
      applySessionPayloads(parts[4]);
      document.body.setAttribute('data-session-api-hydrated', 'true');
      document.body.setAttribute('data-session-round-count', String(parts[3].roundCount || 0));
      document.body.setAttribute('data-session-payload-count', String(parts[4].payloadCount || 0));
      document.body.setAttribute('data-session-anomaly-count', String(parts[2].anomalyCount || 0));
      var params = new URLSearchParams(window.location.search || "");
      var traceStatus = params.get("trace_status") || "all";
      if (traceStatus === "failed" || traceStatus === "low-cache") {
        setFilter(document.querySelector('[data-trace-page]') || document, traceStatus);
      }
      var initialRound = params.get("round") || "";
      if (initialRound && typeof jumpRound === 'function') {
        jumpRound(document.querySelector('[data-trace-page]') || document, initialRound, {
          subagent: params.get("subagent") || "",
          subagentRound: params.get("subagentround") || params.get("subagent_round") || "",
          smooth: false
        });
      }
    }).catch(function(err) {
      console.error('Session Detail API hydration failed:', err.message || err);
      document.body.setAttribute('data-session-api-hydrated', 'false');
    });
  }

  function readSessionJson(response) {
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.json();
  }

  function applySessionMeta(meta) {
    if (!meta) return;
    var parity = meta.parity || {};
    var title = qs(document, '[data-session-hero] h1');
    if (title && meta.title) {
      title.textContent = meta.title;
      title.title = meta.title;
    }
    document.body.setAttribute('data-session-api-session-key', meta.sessionKey || '');
    document.body.setAttribute('data-session-api-artifact', meta.hasArtifact ? 'available' : 'missing');
    var agent = qs(document, '[data-session-agent]');
    if (agent) agent.textContent = parity.agentLabel || (meta.filters && meta.filters.agent) || agent.textContent || '';
    var idText = qs(document, '[data-session-id-text]');
    if (idText && meta.filters && meta.filters.sessionId) {
      idText.textContent = meta.filters.sessionId;
      idText.title = meta.filters.sessionId;
    }
    var fileRow = qs(document, '[data-session-file-path]');
    var fileText = qs(document, '[data-session-file-text]');
    var sessionFilePath = parity.sessionFilePath || meta.sessionFilePath || '';
    if (fileRow && fileText && sessionFilePath) {
      fileRow.hidden = false;
      fileText.textContent = sessionFilePath;
      fileText.title = sessionFilePath;
      var copy = fileRow.querySelector('[data-action="copy"]');
      if (copy) copy.setAttribute('data-copy-text', sessionFilePath);
    }
    var chips = qs(document, '[data-session-meta-chips]');
    if (chips) {
      chips.replaceChildren(
        chip(meta.model || 'Unknown model', true),
        chip(meta.projectName || meta.projectKey || 'Unknown project'),
        chip(parity.date || '—'),
        chip(parity.updatedLocal ? 'Updated ' + parity.updatedLocal : (meta.updatedAt ? 'Updated ' + meta.updatedAt : 'Updated —'))
      );
    }
    setText('[data-session-updated]', parity.updatedLocal || meta.updatedAt || '—');
  }

  function applySessionMetrics(metrics) {
    if (!metrics || !metrics.tokens) return;
    var parity = metrics.parity || {};
    setKpi('Total Tokens', formatSessionCompact(metrics.tokens.total), [
      tokenShareSubline('Fresh', metrics.tokens.fresh, metrics.tokens.total, parity.freshShare),
      tokenShareSubline('Cache Read', metrics.tokens.cacheRead, metrics.tokens.total, parity.cacheReadShare),
      tokenShareSubline('Cache Write', metrics.tokens.cacheWrite, metrics.tokens.total, parity.cacheWriteShare),
      tokenShareSubline('Output', metrics.tokens.output, metrics.tokens.total, parity.outputShare)
    ]);
    var inputSide = Number(metrics.tokens.fresh || 0) + Number(metrics.tokens.cacheRead || 0) + Number(metrics.tokens.cacheWrite || 0);
    setKpi('Cache Health', parity.cacheReuse || pctLabel(metrics.tokens.cacheRead, inputSide), [
      subline('Input-side Tokens', formatSessionCompact(parity.inputSideTokens || inputSide)),
      subline('Low-cache Rounds', formatNumber(parity.lowCacheRounds || 0)),
      subline('Fresh Spike Rounds', formatNumber(parity.freshSpikeRounds || 0))
    ]);
    setKpi('Workload', formatNumber(parity.workloadCalls || (Number(metrics.userMessages || 0) + Number(metrics.assistantMessages || 0))), [
      subline('Main Calls', formatNumber(parity.mainCalls || metrics.assistantMessages)),
      subline('Subagent Calls', formatNumber(parity.subagentCalls || 0)),
      subline('Tool Calls', formatNumber(parity.toolCalls || metrics.toolCalls)),
      subline('Subagent Runs', formatNumber(parity.subagentRuns || metrics.subagents))
    ]);
    var activeSeconds = Number(parity.activeSeconds || 0);
    setKpi('Active Time', formatDuration(activeSeconds), [
      subline('Duration', formatDuration(metrics.durationSeconds)),
      subline('Waiting Time', formatDuration(parity.waitingSeconds || Math.max(Number(metrics.durationSeconds || 0) - activeSeconds, 0))),
      subline('Model Time', parity.modelTimeAvailable ? formatDuration(metrics.modelExecutionSeconds) : 'N/A'),
      subline('Tool Time', parity.toolTimeAvailable ? formatDuration(metrics.toolExecutionSeconds) : 'N/A')
    ]);
    document.body.setAttribute('data-session-api-total-tokens', String(metrics.tokens.total || 0));
    document.body.setAttribute('data-session-api-failed-tools', String(metrics.failedTools || 0));
  }

  function applySessionDiagnostics(diagnostics) {
    if (!diagnostics) return;
    var parity = diagnostics.parity || {};
    var count = Number(parity.issueRounds || diagnostics.anomalyCount || 0);
    setKpi('Run Health', parity.runHealth || (count > 0 ? 'Completed with issue signals' : 'Completed'), [
      subline('Issue Rounds', formatNumber(count)),
      rateSubline('Failed Tools', parity.failedTools || 0, parity.failedToolsTotal || parity.toolCalls || (parity.toolImpact && parity.toolImpact.allToolCalls) || 0, parity.failedToolsRate),
      subline('Payload Gaps', formatNumber(parity.payloadGaps || 0)),
      subline('Attribution Gaps', formatNumber(parity.attributionGaps || 0))
    ]);
    var strip = qs(document, '[data-issue-strip]');
    if (strip) {
      strip.classList.toggle('sd-issue-strip--ok', count === 0);
      strip.classList.remove('sd-issue-strip--loading');
      strip.replaceChildren();
      var title = document.createElement('span');
      title.className = 'sd-issue-title';
      title.textContent = count > 0 ? 'Issue Signals' : 'No issue signals';
      strip.appendChild(title);
      (parity.issueStrip || []).forEach(function (issue) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'sd-issue-link sd-issue-link--' + (issue.tone || 'warn');
        button.setAttribute('data-action', 'jump-round');
        button.setAttribute('data-round', String(issue.roundId || 1));
        button.textContent = issue.label || 'Issue';
        strip.appendChild(button);
      });
      if (count === 0) {
        var ok = document.createElement('span');
        ok.className = 'sd-issue-ok-badge';
        ok.textContent = 'All rounds completed successfully';
        strip.appendChild(ok);
      }
    }
    sessionDetailState.diagnosticsParity = parity;
    renderDiagnosticsCards(parity);
  }

  function applySessionRounds(roundsResponse) {
    var tbody = qs(document, '.trace-table[data-trace-list] tbody');
    if (!tbody || !roundsResponse) return;
    var rows = roundsResponse.rounds || [];
    if (!rows.length) {
      var tr = document.createElement('tr');
      var td = document.createElement('td');
      td.colSpan = 6;
      setMarkup(td, '<div class="empty-state"><div class="empty-state__icon" aria-hidden="true">📭</div><h2 class="empty-state__title">'
        + escapeHtml((roundsResponse.state && roundsResponse.state.title) || 'No rounds indexed')
        + '</h2><p class="empty-state__text">'
        + escapeHtml((roundsResponse.state && roundsResponse.state.message) || 'No normalized round data is available.')
        + '</p></div>');
      tr.appendChild(td);
      tbody.replaceChildren(tr);
      return;
    }
    sessionDetailState.rounds = rows;
    sessionDetailState.maxRoundTokens = rows.reduce(function (max, round) {
      return Math.max(max, Number(round && round.tokens && round.tokens.total || 0));
    }, 0);
    var globalCallIndex = 1;
    tbody.replaceChildren.apply(tbody, rows.map(function (round) {
      var row = roundRow(round, globalCallIndex, sessionDetailState.maxRoundTokens);
      globalCallIndex += Math.max(1, Number(round.callCount || 1));
      return row;
    }));
    setupTokenTooltips();
    if (sessionDetailState.diagnosticsParity) renderDiagnosticsCards(sessionDetailState.diagnosticsParity);
    syncToggleAllButton(document);
  }

  function roundRow(round, globalCallIndex, maxRoundTokens) {
    var tr = document.createElement('tr');
    var tokens = round.tokens || {};
    var parity = round.parity || {};
    var inputSide = Number(tokens.fresh || 0) + Number(tokens.cacheRead || 0) + Number(tokens.cacheWrite || 0);
    var isLowCache = Boolean(parity.isLowCache) || (inputSide > 0 && (Number(tokens.cacheRead || 0) / inputSide) < 0.2);
    var hasIssues = Boolean(parity.hasIssues) || (round.status || '') === 'failed' || Number(round.failedToolCount || 0) > 0;
    var isUserInput = Boolean(parity.isUserInput);
    var visualStatus = hasIssues ? 'failed' : (isUserInput ? 'user' : (round.status || 'ok'));
    var firstCallIndex = 1;
    var globalLabel = 'LLM Call #' + formatNumber(globalCallIndex || round.roundIndex || 1);
    var requestPayloadId = 'llm-R' + round.roundIndex + '-IX' + firstCallIndex + '-request-attribution';
    var responsePayloadId = 'llm-R' + round.roundIndex + '-IX' + firstCallIndex + '-response-attribution';
    tr.className = 'round-row sd-trace-round-row' + (isUserInput ? ' sd-user-round' : '') + (hasIssues ? ' sd-failed-round' : '');
    tr.setAttribute('data-trace-round-row', '');
    tr.setAttribute('data-round', String(round.roundIndex));
    tr.setAttribute('data-status', visualStatus);
    tr.setAttribute('data-round-status', round.status || '');
    tr.setAttribute('data-has-issues', hasIssues ? 'true' : 'false');
    tr.setAttribute('data-is-user-input', isUserInput ? 'true' : 'false');
    tr.setAttribute('data-is-low-cache', isLowCache ? 'true' : 'false');
    tr.setAttribute('data-is-fresh-spike', parity.isFreshSpike ? 'true' : 'false');
    tr.setAttribute('data-detail-loaded', 'false');
    tr.id = 'round-' + round.roundIndex;
    setMarkup(tr, [
      '<td class="round-col"><button type="button" class="sd-round-toggle round-id', hasIssues ? ' failed' : '', '" data-action="toggle-round" aria-controls="round-', round.roundIndex, '-detail" aria-expanded="false" aria-label="Toggle round ', round.roundIndex, '">',
      'R', round.roundIndex, '</button></td>',
      '<td><span class="summary-title">', escapeHtml(parity.summary || ('Round ' + round.roundIndex)), '</span></td>',
      '<td class="metrics-col mono"><div class="metric-cell"><span class="metric-tools">', formatNumber(round.toolCallCount), ' tools</span>', tokenbarHtml(tokens, maxRoundTokens), '</div></td>',
      '<td class="attribution-col"><span class="sd-attribution-actions sd-attribution-actions--row" aria-label="', escapeHtml(globalLabel), ' attribution">',
      '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm sd-attr-btn sd-attr-btn--ok" data-action="open-payload" data-payload-id="', escapeHtml(requestPayloadId), '" data-payload-kind="llm.request_attribution" data-payload-title="Request attribution · ', escapeHtml(globalLabel), '">request</button> ',
      '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm sd-attr-btn sd-attr-btn--ok" data-action="open-payload" data-payload-id="', escapeHtml(responsePayloadId), '" data-payload-kind="llm.response_attribution" data-payload-title="Response attribution · ', escapeHtml(globalLabel), '">response</button></span></td>',
      '<td class="status-col">', statusBadges(round, hasIssues, isLowCache), '</td>',
      '<td class="time-col"><span class="round-time">', escapeHtml(parity.time || ''), '</span></td>'
    ].join(''));
    return tr;
  }

  function applySessionPayloads(payloadsResponse) {
    if (!payloadsResponse) return;
    var container = qs(document, '[data-payload-sources-container]');
    if (!container) return;
    var payloads = payloadsResponse.payloads || [];
    container.replaceChildren.apply(container, payloads.map(function (payload) {
      var tpl = document.createElement('template');
      tpl.setAttribute('data-payload-source', payload.payloadId || '');
      tpl.setAttribute('data-payload-kind', payload.kind || '');
      tpl.setAttribute('data-payload-status', payload.status || '');
      tpl.setAttribute('data-payload-token-estimate', '');
      tpl.setAttribute('data-payload-index-only', 'true');
      tpl.setAttribute('data-payload-api-url', payload.apiUrl || '');
      tpl.setAttribute('data-payload-title', payload.title || payload.payloadId || 'Payload');
      return tpl;
    }));
  }

  function renderDiagnosticsCards(parity) {
    var root = qs(document, '[data-session-diagnostics]');
    if (!root || !parity) return;
    var agents = parity.agents || [];
    var toolImpact = parity.toolImpact || {};
    var contextSegments = parity.contextSegments || [];
    var issues = parity.issues || [];
    var issuePreview = issues.slice(0, 5);
    var html = ''
      + '<article class="sd-diagnostic-card sd-diagnostic-card--wide sd-diagnostic-card--subagents sd-diagnostic-card--agents">'
      + '<header class="sd-diagnostic-card__head"><h2>Agents Breakdown</h2><span>' + formatNumber(agents.length) + ' agents</span></header>'
      + '<div class="sd-diagnostic-card__body">' + agentsTableHtml(agents) + '</div></article>'
      + '<article class="sd-diagnostic-card sd-diagnostic-card--context">'
      + '<header class="sd-diagnostic-card__head"><h2>Context Budget</h2><span>Session-level</span></header>'
      + '<div class="sd-diagnostic-card__body">' + contextBudgetHtml(contextSegments) + '</div></article>'
      + '<article class="sd-diagnostic-card">'
      + '<header class="sd-diagnostic-card__head"><h2>Tool Impact</h2><span>' + formatNumber(toolImpact.allToolCalls || 0) + ' calls</span></header>'
      + '<div class="sd-diagnostic-card__body">' + toolImpactHtml(toolImpact) + '</div></article>'
      + '<article class="sd-diagnostic-card">'
      + '<header class="sd-diagnostic-card__head"><h2>Issues &amp; Repro Seeds</h2><span>' + formatNumber(parity.issueCount || issues.length || 0) + ' issues</span></header>'
      + '<div class="sd-diagnostic-card__body">' + issuesHtml(issuePreview) + '</div></article>';
    setMarkup(root, html);
    setupTokenRoundTooltips();
  }

  function agentsTableHtml(agents) {
    if (!agents.length) return '<div class="sd-card-empty">No agent runs indexed</div>';
    var rows = agents.map(function (row, idx) {
      var active = idx === 0 ? ' is-active' : '';
      var scope = row.scope || (idx === 0 ? 'main' : 'subagent');
      var subagentId = row.subagentId || '';
      var instanceClass = scope === 'main' ? 'sd-subagent-instance--main' : ('sd-subagent-instance--subagent-' + ((idx - 1) % 5));
      var failures = Number(row.failures || 0);
      var rateClass = failures > 0 ? ' sd-rate--warn' : ' sd-rate--ok';
      var failureLabel = row.failureLabel || (formatNumber(row.failures) + ' failed · ' + (row.failureRate || 'N/A'));
      if (scope !== 'main' && failures === 0) {
        failureLabel = 'Success · 0 failed';
      }
      return '<tr class="sd-subagent-row' + active + '" data-subagent-row>'
        + '<td class="sd-subagent-table__agent"><button type="button" class="sd-subagent-select' + active + '" data-action="select-subagent" data-subagent="'
        + escapeHtml(subagentId) + '" data-agent-scope="' + escapeHtml(scope) + '" aria-pressed="' + (idx === 0 ? 'true' : 'false') + '"><span class="sd-subagent-select__main"><b>'
        + escapeHtml(row.agent || 'agent') + '</b><span class="sd-subagent-instance ' + instanceClass + '">'
        + escapeHtml(row.shortId || '') + '</span></span></button></td>'
        + '<td class="sd-subagent-table__copy-cell"><span class="sd-subagent-copy-value" title="' + escapeHtml(row.sessionFile || '') + '">'
        + escapeHtml(row.sessionFileDisplay || '—') + '</span> <button type="button" class="sd-subagent-copy-btn" data-action="copy" data-copy-text="'
        + escapeHtml(row.sessionFile || '') + '" aria-label="Copy session file" title="Copy full session file">Copy</button></td>'
        + '<td class="sd-subagent-table__copy-cell"><span class="sd-subagent-copy-value" title="' + escapeHtml(row.sessionId || '') + '">'
        + escapeHtml(row.sessionIdDisplay || '—') + '</span> <button type="button" class="sd-subagent-copy-btn" data-action="copy" data-copy-text="'
        + escapeHtml(row.sessionId || '') + '" aria-label="Copy session id" title="Copy full session id">Copy</button></td>'
        + '<td title="' + (scope === 'main' ? 'Main agent LLM calls' : 'Subagent internal LLM calls') + '">' + formatNumber(row.llmCalls) + ' LLM</td>'
        + '<td title="' + escapeHtml(row.tokens || '0') + ' · ' + escapeHtml(row.tokenShare || 'N/A') + '">' + escapeHtml(row.tokens || '0') + ' · ' + escapeHtml(row.tokenShare || 'N/A') + '</td>'
        + '<td>' + formatNumber(row.tools) + ' tools</td>'
        + '<td><b class="sd-rate' + rateClass + '">' + escapeHtml(failureLabel) + '</b></td>'
        + '</tr>';
    }).join('');
    var panels = agents.map(function (row, idx) {
      return agentTimelinePanelHtml(row, idx);
    }).join('');
    return '<div class="sd-subagent-workbench" data-subagent-workbench><div class="sd-subagent-table-scroll" aria-label="Agent candidates"><table class="sd-subagent-table">'
      + '<thead><tr><th>Agent</th><th>Session file</th><th>Session id</th><th>LLM</th><th>Tokens</th><th>Tools</th><th>Failures</th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table></div><div class="sd-subagent-timeline-area">' + panels + '</div></div>';
  }

  function agentTimelinePanelHtml(agent, idx) {
    var scope = agent.scope || (idx === 0 ? 'main' : 'subagent');
    var subagentId = agent.subagentId || '';
    var active = idx === 0;
    var timeline = scope === 'main'
      ? tokenRoundChartHtml(sessionDetailState.rounds, agent.agent || 'main agent')
      : '<div class="sd-card-empty">Subagent round timeline is loaded through Trace subagent details.</div>';
    return '<section class="sd-subagent-timeline' + (active ? ' is-active' : '') + '" data-subagent-timeline-panel data-subagent="'
      + escapeHtml(subagentId) + '" data-agent-scope="' + escapeHtml(scope) + '"' + (active ? '' : ' hidden') + '>'
      + '<div class="sd-subagent-timeline__head"><div><b>' + escapeHtml(agent.agent || 'agent') + '</b><span>'
      + escapeHtml((agent.shortId || scope) + (scope === 'main' ? ' · session rounds' : ' · subagent rounds')) + '</span></div><small>'
      + formatNumber(agent.llmCalls) + ' LLM · ' + escapeHtml(agent.tokens || '0') + ' tokens · '
      + formatNumber(agent.tools) + ' tools · ' + formatNumber(agent.failures) + ' failures</small></div>'
      + timeline + '</section>';
  }

  // 折线与 tooltip 共用输入侧口径，不包含输出 token。
  function roundCacheReadRatio(tokens) {
    var inputSide = Number(tokens.fresh || 0) + Number(tokens.cacheRead || 0) + Number(tokens.cacheWrite || 0);
    return inputSide > 0 ? Math.max(0, Math.min(100, Number(tokens.cacheRead || 0) / inputSide * 100)) : 0;
  }

  function tokenRoundChartHtml(rounds, label) {
    if (!rounds || !rounds.length) {
      return '<div class="sd-card-empty">Round timeline is loading from /rounds API.</div>';
    }
    var maxTotal = Math.max(1, sessionDetailState.maxRoundTokens || 1);
    var plotWidth = Math.max(320, rounds.length * 32 + 44);
    var points = rounds.map(function (round, idx) {
      var tokens = round.tokens || {};
      var ratio = roundCacheReadRatio(tokens);
      return (idx * 32) + ',' + (100 - Math.max(0, Math.min(100, ratio))).toFixed(1);
    }).join(' ');
    var buttons = rounds.map(function (round) {
      var tokens = round.tokens || {};
      var total = Number(tokens.total || 0);
      var height = Math.max(6, Math.min(118, (total / maxTotal) * 118));
      var fresh = pct(tokens.fresh, total);
      var read = pct(tokens.cacheRead, total);
      var write = pct(tokens.cacheWrite, total);
      var out = pct(tokens.output, total);
      var parity = round.parity || {};
      var tags = [];
      if (round.status === 'failed' || parity.hasIssues) tags.push('issue');
      if (parity.isLowCache) tags.push('low cache');
      if (parity.isFreshSpike) tags.push('fresh spike');
      return '<button type="button" class="sd-token-round" data-action="jump-round" data-round="' + escapeHtml(round.roundIndex) + '" aria-label="R' + escapeHtml(round.roundIndex) + ' token timeline">'
        + '<span class="sd-token-round__bar" aria-label="R' + escapeHtml(round.roundIndex) + '" style="--bar-height-px:' + height.toFixed(1) + 'px">'
        + '<span class="sd-token-round__seg sd-token-round__seg--fresh" style="--seg-height:' + fresh + '%"></span>'
        + '<span class="sd-token-round__seg sd-token-round__seg--read" style="--seg-height:' + read + '%"></span>'
        + '<span class="sd-token-round__seg sd-token-round__seg--write" style="--seg-height:' + write + '%"></span>'
        + '<span class="sd-token-round__seg sd-token-round__seg--out" style="--seg-height:' + out + '%"></span></span>'
        + '<span class="sd-token-round-tooltip" role="tooltip"><b>R' + escapeHtml(round.roundIndex) + ' · ' + escapeHtml(parity.time || '') + '</b>'
        + '<div>Token shares below use Total, including Output.</div>'
        + '<span><i class="sd-tooltip-mark sd-tooltip-mark--fresh"></i><small>Fresh</small><em>' + formatSessionCompact(tokens.fresh) + '</em><strong>' + fresh + '%</strong></span>'
        + '<span><i class="sd-tooltip-mark sd-tooltip-mark--read"></i><small>Cache Read</small><em>' + formatSessionCompact(tokens.cacheRead) + '</em><strong>' + read + '%</strong></span>'
        + '<span><i class="sd-tooltip-mark sd-tooltip-mark--write"></i><small>Cache Write</small><em>' + formatSessionCompact(tokens.cacheWrite) + '</em><strong>' + write + '%</strong></span>'
        + '<span><i class="sd-tooltip-mark sd-tooltip-mark--out"></i><small>Output</small><em>' + formatSessionCompact(tokens.output) + '</em><strong>' + out + '%</strong></span>'
        + '<span class="sd-token-round-tooltip__total"><i></i><small>Total</small><em>' + formatSessionCompact(total) + '</em><strong>100.0%</strong></span>'
        + '<span class="sd-token-round-tooltip__tags"><i class="sd-tooltip-mark sd-tooltip-mark--line"></i><small>Cache Read / Input</small><em>' + roundCacheReadRatio(tokens).toFixed(1) + '%</em></span>'
        + '<div>Line = Cache Read / (Fresh + Cache Read + Cache Write). Excludes Output; no input = 0%.</div>'
        + (tags.length ? '<span class="sd-token-round-tooltip__tags"><i class="sd-tooltip-mark sd-tooltip-mark--spike"></i><small>Badge Text</small><em>' + escapeHtml(tags.join(', ')) + '</em></span>' : '')
        + '</span><span class="sd-token-round__signal-slot" aria-hidden="true">' + (tags.length ? '<span class="sd-token-round__spike"></span>' : '') + '</span>'
        + '<span class="sd-token-round__label">R' + escapeHtml(round.roundIndex) + '</span></button>';
    }).join('');
    return '<div><small><i class="sd-tooltip-mark sd-tooltip-mark--line" aria-hidden="true"></i> Black line: Cache Read / Input (0–100%, excludes Output). Bars: token totals.</small></div>'
      + '<div class="sd-token-round-chart" aria-label="' + escapeHtml(label || 'agent') + ' token composition">'
      + '<div class="sd-token-round-plot" style="--plot-width:' + plotWidth + 'px; --ratio-line-left:22px; --ratio-line-width:' + Math.max(0, plotWidth - 44) + 'px">'
      + '<svg class="sd-token-ratio-line" viewBox="0 0 ' + Math.max(1, plotWidth - 44) + ' 100" preserveAspectRatio="none" aria-label="Agent cache read ratio line">'
      + '<polyline points="' + escapeHtml(points) + '"></polyline></svg>' + buttons + '</div></div>';
  }

  function contextBudgetHtml(segments) {
    if (!segments.length) return '<div class="sd-card-empty">No context budget available</div>';
    var bars = segments.map(function (segment, idx) {
      return '<span class="sd-context-segment sd-context-segment--' + (idx + 1) + ' sd-context-segment--' + escapeHtml(segment.status || 'available')
        + '" style="--seg-width:' + escapeHtml(segment.shareValue || 0) + '%"><span class="sd-context-segment__label">'
        + escapeHtml(segment.label || '') + '</span><span class="sd-context-segment__pct">' + escapeHtml(segment.share || 'N/A') + '</span></span>';
    }).join('');
    var legend = segments.map(function (segment, idx) {
      return '<div class="sd-context-budget__item sd-context-budget__item--' + escapeHtml(segment.status || 'available') + '"><i class="sd-context-budget__dot sd-context-budget__dot--'
        + (idx + 1) + '" aria-hidden="true"></i><span>' + escapeHtml(segment.label || '') + '</span><b>'
        + escapeHtml(segment.tokensLabel || 'N/A') + ' · ' + escapeHtml(segment.share || 'N/A') + '</b></div>';
    }).join('');
    return '<div class="sd-context-segmented" aria-label="Context budget segmented bar">' + bars + '</div>'
      + '<div class="sd-context-budget">' + legend + '</div>'
      + '<div class="sd-context-note">Unavailable segments are not treated as 0%; tool result tokens are local estimates from transcript result length.</div>';
  }

  function toolImpactHtml(toolImpact) {
    var rows = toolImpact.rows || [];
    if (!rows.length && !Number(toolImpact.allToolCalls || 0)) return '<div class="sd-card-empty">No tool calls indexed</div>';
    var body = rows.map(function (row) {
      var rowTone = rateTone(row.failures, row.calls);
      return '<tr title="' + escapeHtml(row.splitNote || '') + '"><td>' + escapeHtml(row.tool || 'tool') + '</td><td>'
        + formatNumber(row.calls) + '</td><td>' + escapeHtml(row.tokens || '0') + '</td><td><span class="sd-rate sd-rate--' + rowTone + '">'
        + formatNumber(row.failures) + ' · ' + escapeHtml(row.failureRate || 'N/A') + '</span></td></tr>';
    }).join('');
    var summaryTone = rateTone(toolImpact.failedTools, toolImpact.allToolCalls);
    return '<table class="sd-compact-table"><thead><tr><th>Tool</th><th>Calls</th><th>Result Tokens</th><th>Failures</th></tr></thead><tbody>'
      + body + '<tr class="sd-table-summary-row"><td>Summary</td><td>' + formatNumber(toolImpact.allToolCalls || 0)
      + '</td><td>' + formatNumber(toolImpact.distinctTools || 0) + ' tools</td><td><span class="sd-rate sd-rate--' + summaryTone + '">'
      + formatNumber(toolImpact.failedTools || 0) + ' · ' + escapeHtml(toolImpact.failedToolsRate || 'N/A') + '</span></td></tr></tbody></table>';
  }

  function issuesHtml(issues) {
    if (!issues.length) return '<div class="sd-card-empty">No actionable issues detected</div>';
    var rows = issues.map(function (issue) {
      return '<tr><td><span class="sd-signal-badge sd-signal-badge--' + escapeHtml(issue.tone || 'warning') + '">'
        + escapeHtml(issue.issue || 'Issue') + '</span></td><td>' + escapeHtml(issue.evidence || '') + '</td><td>'
        + '<button type="button" class="sd-link-btn sd-link-btn--inline" data-action="jump-round" data-round="' + escapeHtml(issue.roundId || '') + '">'
        + escapeHtml(issue.roundLabel || ('R' + issue.roundId)) + '</button></td><td>'
        + '<button type="button" class="sd-seed-btn" data-action="copy" data-copy-text="' + escapeHtml(issue.seed || '') + '" title="' + escapeHtml(issue.seed || '') + '">Copy locator</button>'
        + '</td></tr>';
    }).join('');
    return '<div class="sd-chart-note">Rows are the actionable issue locators used to jump back to Trace or copy a stable repro locator.</div>'
      + '<table class="sd-compact-table"><thead><tr><th>Issue</th><th>Evidence</th><th>Round</th><th>Locator</th></tr></thead><tbody>'
      + rows + '</tbody></table>';
  }

  function setKpi(label, value, sublines) {
    var card = qs(document, '.sd-kpi[aria-label="' + label + '"]');
    if (!card) return;
    var valueEl = qs(card, '.sd-kpi__value');
    if (valueEl) {
      valueEl.textContent = value;
      valueEl.title = 'Loaded from Session Detail APIs';
    }
    var subgrid = qs(card, '.sd-kpi__subgrid');
    if (subgrid && Array.isArray(sublines)) {
      subgrid.replaceChildren.apply(subgrid, sublines.map(function (line) {
        var span = document.createElement('span');
        if (line && typeof line === 'object') {
          span.appendChild(document.createTextNode((line.label || '') + ' '));
          var b = document.createElement('b');
          if (line.valueClass) b.className = line.valueClass;
          if (line.title) b.title = line.title;
          b.textContent = line.value == null ? '' : String(line.value);
          span.appendChild(b);
        } else {
          var idx = String(line).lastIndexOf(' ');
          if (idx > 0) {
            span.appendChild(document.createTextNode(line.slice(0, idx) + ' '));
            var fallback = document.createElement('b');
            fallback.textContent = line.slice(idx + 1);
            span.appendChild(fallback);
          } else {
            span.textContent = line;
          }
        }
        return span;
      }));
    }
  }

  function subline(label, value) {
    return { label: label, value: value };
  }

  function tokenShareSubline(label, value, total, shareLabel) {
    var ratio = ratioValue(value, total);
    var tone = tokenShareTone(ratio);
    return {
      label: label,
      value: formatSessionCompact(value) + ' · ' + (shareLabel || pctLabel(value, total)),
      valueClass: 'sd-kpi-token-share sd-kpi-token-share--' + tone,
      title: label + ' share: ' + ratio.toFixed(1) + '%'
    };
  }

  function rateSubline(label, failures, total, rateLabel) {
    var tone = rateTone(failures, total);
    return {
      label: label,
      value: formatNumber(failures) + ' · ' + (rateLabel || pctLabel(failures, total)),
      valueClass: 'sd-kpi-tone sd-kpi-tone--' + tone
    };
  }

  function tokenShareTone(ratio) {
    if (ratio >= 50) return 'major';
    if (ratio >= 20) return 'mid';
    return 'minor';
  }

  function rateTone(failures, total) {
    var ratio = ratioValue(failures, total);
    if (ratio >= 10) return 'bad';
    if (Number(failures || 0) > 0) return 'warn';
    return 'ok';
  }

  function ratioValue(value, total) {
    var denominator = Number(total || 0);
    if (denominator <= 0) return 0;
    return Math.max(0, Math.min(100, (Number(value || 0) / denominator) * 100));
  }

  function tokenbarHtml(tokens, maxRoundTokens) {
    var total = Number(tokens && tokens.total || 0);
    if (total <= 0) return '';
    var fresh = pct(tokens.fresh, total);
    var read = pct(tokens.cacheRead, total);
    var write = pct(tokens.cacheWrite, total);
    var out = pct(tokens.output, total);
    var scale = maxRoundTokens > 0 ? Math.max(2, Math.min(100, Math.round((total / maxRoundTokens) * 1000) / 10)) : 100;
    var scaleLabel = scale + '% of max round tokens';
    return '<div class="token-group"><span class="metric-token">' + formatSessionCompact(total) + '</span>'
      + '<span class="tokenbar-wrap" tabindex="0" title="' + escapeHtml(scaleLabel) + '" aria-label="' + escapeHtml(scaleLabel) + '" style="--token-total-width:' + scale + '%;">'
      + '<span class="tokenbar"><span class="tokenbar-seg fresh" style="--segment-width:' + fresh + '%"></span>'
      + '<span class="tokenbar-seg read" style="--segment-width:' + read + '%"></span>'
      + '<span class="tokenbar-seg write" style="--segment-width:' + write + '%"></span>'
      + '<span class="tokenbar-seg out" style="--segment-width:' + out + '%"></span></span>'
      + '<div class="token-tooltip" aria-hidden="true"><div class="token-tooltip__title">Token Breakdown</div>'
      + '<div class="token-tooltip__row"><span>Fresh</span><span class="token-tooltip__value">' + formatSessionCompact(tokens.fresh) + '</span></div>'
      + '<div class="token-tooltip__row"><span>Cache Read</span><span class="token-tooltip__value">' + formatSessionCompact(tokens.cacheRead) + '</span></div>'
      + '<div class="token-tooltip__row"><span>Cache Write</span><span class="token-tooltip__value">' + formatSessionCompact(tokens.cacheWrite) + '</span></div>'
      + '<div class="token-tooltip__row"><span>Output</span><span class="token-tooltip__value">' + formatSessionCompact(tokens.output) + '</span></div>'
      + '<div class="token-tooltip__sep"></div><div class="token-tooltip__row token-tooltip__total"><span>Total</span><span class="token-tooltip__value">' + formatSessionCompact(total) + '</span></div>'
      + '<div class="token-tooltip__row"><span>Scale</span><span class="token-tooltip__value">' + escapeHtml(scaleLabel) + '</span></div>'
      + '</div></span></div>';
  }

  function statusBadges(round, hasIssues, isLowCache) {
    var html = '';
    var signals = (round.signals || []).slice();
    if (hasIssues && signals.indexOf('Failed') < 0) signals.unshift('Failed');
    signals.forEach(function (signal) {
      var tone = signal === 'Failed' ? ' sd-signal-badge--failed' : (signal === 'Subagent' ? ' sd-signal-badge--subagent' : '');
      html += '<span class="sd-signal-badge' + tone + '">' + escapeHtml(signal) + '</span>';
    });
    return html;
  }

  function chip(text, mono) {
    var span = document.createElement('span');
    span.className = mono ? 'sd-chip sd-chip--mono' : 'sd-chip';
    span.textContent = text;
    return span;
  }

  function setText(selector, value) {
    var el = qs(document, selector);
    if (el) el.textContent = value;
  }

  function pct(value, total) {
    if (!total) return 0;
    return Math.max(0, Math.min(100, Math.round((Number(value || 0) / total) * 1000) / 10));
  }

  function pctLabel(value, total) {
    total = Number(total || 0);
    if (!total) return 'N/A';
    return ((Number(value || 0) / total) * 100).toFixed(1) + '%';
  }

  function formatNumber(value) {
    return String(Math.round(Number(value || 0)));
  }

  function formatDuration(seconds) {
    var n = Math.round(Number(seconds || 0));
    if (n >= 3600) return Math.floor(n / 3600) + 'h ' + Math.floor((n % 3600) / 60) + 'm';
    if (n >= 60) return Math.floor(n / 60) + 'm ' + (n % 60) + 's';
    return n + 's';
  }

  function severityTone(severity) {
    var s = String(severity || '').toLowerCase();
    if (s === 'critical' || s === 'error') return 'critical';
    if (s === 'warning' || s === 'warn') return 'warning';
    return 'info';
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch];
    });
  }

  function setMarkup(target, markup) {
    var parsed;
    var source;
    if (target && target.tagName === 'TR') {
      parsed = new DOMParser().parseFromString(
        '<table><tbody><tr>' + (markup || '') + '</tr></tbody></table>',
        'text/html'
      );
      source = parsed.querySelector('tbody tr');
    } else {
      parsed = new DOMParser().parseFromString(markup || '', 'text/html');
      source = parsed.body;
    }
    if (!source) return;
    target.replaceChildren.apply(target, Array.prototype.slice.call(source.childNodes));
  }

  function formatSessionCompact(value) {
    var n = Number(value || 0);
    if (n >= 1000000000) return (n / 1000000000).toFixed(1) + 'B';
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(Math.round(n));
  }

  function selectSubagent(button) {
    if (!button) return;
    var workbench = button.closest('[data-subagent-workbench]');
    if (!workbench) return;
    var subagent = button.getAttribute('data-subagent') || "";
    var scope = button.getAttribute('data-agent-scope') || "subagent";
    qsa(workbench, '[data-action="select-subagent"]').forEach(function (item) {
      var isActive = item === button;
      item.classList.toggle('is-active', isActive);
      item.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      var row = item.closest('[data-subagent-row]');
      if (row) row.classList.toggle('is-active', isActive);
    });
    qsa(workbench, '[data-subagent-timeline-panel]').forEach(function (panel) {
      var isActive = panel.getAttribute('data-subagent') === subagent
        && (panel.getAttribute('data-agent-scope') || "subagent") === scope;
      panel.classList.toggle('is-active', isActive);
      if (isActive) {
        panel.removeAttribute('hidden');
      } else {
        panel.setAttribute('hidden', '');
      }
    });
  }

  window.selectSubagent = selectSubagent;

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closePayload();
  });

  document.addEventListener('DOMContentLoaded', function () {
    // Initialize the trace panel; legacy payload deep links fall back to Trace.
    var page = document.querySelector('[data-trace-page]') || document;
    var params = new URLSearchParams(window.location.search || "");
    var initialTab = "trace";
    switchTab(page, initialTab, false);
    qsa(document, '[data-trace-round-row]').forEach(function (round) {
      var button = qs(round, '[data-action="toggle-round"]');
      var open = round.classList.contains('is-open') || (button && button.getAttribute('aria-expanded') === 'true');
      setRoundOpen(round, open);
    });
    qsa(document, '[data-sub-round-id]').forEach(function (subRound) {
      syncSubRoundToggle(subRound);
    });
    qsa(document, '[data-subagent-block]').forEach(function (block) {
      syncSubagentToggle(block);
    });
    var initialTraceStatus = params.get("trace_status") || "all";
    if (initialTraceStatus === "failed" || initialTraceStatus === "low-cache") {
      setFilter(page, initialTraceStatus);
    }
    var initialRound = params.get("round") || "";
    if (initialRound) {
      jumpRound(page, initialRound, {
        subagent: params.get("subagent") || "",
        subagentRound: params.get("subagentround") || params.get("subagent_round") || "",
        smooth: false
      });
    }
    // Sync toggle-all button text on load
    syncToggleAllButton(document);
    // Setup dynamic token tooltip positioning
    setupTokenTooltips();
    setupTokenRoundTooltips();
    hydrateSessionDetailApis();
  });
