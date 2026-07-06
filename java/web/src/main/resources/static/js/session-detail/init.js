  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Token tooltip dynamic positioning ──` */

  var TOOLTIP_FLIP_THRESHOLD = 180; // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`px from bottom of viewport to trigger flip`

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
        chip(parity.updatedLocal ? 'Updated ' + parity.updatedLocal : (meta.updatedAt ? 'Updated ' + meta.updatedAt : 'Updated —')),
        meta.gitBranch ? chip(meta.gitBranch, true) : chip('Branch —', true)
      );
    }
    setText('[data-session-updated]', parity.updatedLocal || meta.updatedAt || '—');
    setText('[data-session-artifact]', meta.hasArtifact ? ('Schema ' + (meta.artifactSchemaVersion || 'available')) : 'No artifact');
  }

  function applySessionMetrics(metrics) {
    if (!metrics || !metrics.tokens) return;
    var parity = metrics.parity || {};
    setKpi('Total Tokens', formatSessionCompact(metrics.tokens.total), [
      subline('Fresh', formatSessionCompact(metrics.tokens.fresh) + ' · ' + (parity.freshShare || pctLabel(metrics.tokens.fresh, metrics.tokens.total))),
      subline('Cache Read', formatSessionCompact(metrics.tokens.cacheRead) + ' · ' + (parity.cacheReadShare || pctLabel(metrics.tokens.cacheRead, metrics.tokens.total))),
      subline('Cache Write', formatSessionCompact(metrics.tokens.cacheWrite) + ' · ' + (parity.cacheWriteShare || pctLabel(metrics.tokens.cacheWrite, metrics.tokens.total))),
      subline('Output', formatSessionCompact(metrics.tokens.output) + ' · ' + (parity.outputShare || pctLabel(metrics.tokens.output, metrics.tokens.total)))
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
      subline('Failed Tools', formatNumber(parity.failedTools || 0) + (parity.failedToolsRate ? ' · ' + parity.failedToolsRate : '')),
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
    var countEl = qs(document, '.sd-anomalies__count');
    if (countEl) countEl.textContent = formatNumber(count) + ' issue rounds';
    var list = qs(document, '.sd-anomalies__list');
    if (list) {
      var empty = document.createElement('div');
      empty.className = 'sd-card-empty';
      empty.textContent = count > 0 ? 'Actionable issues are listed in Diagnostics.' : 'No actionable issues detected.';
      list.replaceChildren(empty);
    }
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
    tbody.replaceChildren.apply(tbody, rows.map(roundRow));
    setupTokenTooltips();
    syncToggleAllButton(document);
  }

  function roundRow(round) {
    var tr = document.createElement('tr');
    var tokens = round.tokens || {};
    var parity = round.parity || {};
    var inputSide = Number(tokens.fresh || 0) + Number(tokens.cacheRead || 0) + Number(tokens.cacheWrite || 0);
    var isLowCache = Boolean(parity.isLowCache) || (inputSide > 0 && (Number(tokens.cacheRead || 0) / inputSide) < 0.2);
    var hasIssues = Boolean(parity.hasIssues) || (round.status || '') === 'failed' || Number(round.failedToolCount || 0) > 0;
    tr.className = 'round-row sd-trace-round-row';
    tr.setAttribute('data-trace-round-row', '');
    tr.setAttribute('data-round', String(round.roundIndex));
    tr.setAttribute('data-status', round.status || (hasIssues ? 'failed' : 'ok'));
    tr.setAttribute('data-has-issues', hasIssues ? 'true' : 'false');
    tr.setAttribute('data-is-low-cache', isLowCache ? 'true' : 'false');
    tr.setAttribute('data-detail-loaded', 'false');
    tr.id = 'round-' + round.roundIndex;
    setMarkup(tr, [
      '<td class="round-col"><span role="button" tabindex="0" class="sd-round-toggle" data-action="toggle-round" aria-controls="round-', round.roundIndex, '-detail" aria-expanded="false" aria-label="Toggle round ', round.roundIndex, '">',
      '<span class="sd-round-toggle__icon" aria-hidden="true">▶</span><span class="sd-round-id">R', round.roundIndex, '</span></span></td>',
      '<td><span class="sd-round-summary">', escapeHtml(parity.summary || ('Round ' + round.roundIndex)), '</span></td>',
      '<td class="metrics-col mono"><span class="sd-round-metrics">', formatNumber(round.toolCallCount), ' tools</span>', tokenbarHtml(tokens), '</td>',
      '<td class="attribution-col"><span class="sd-round-attribution"><button type="button" class="sd-link-btn sd-link-btn--inline" data-action="retry-attribution" data-round="', round.roundIndex, '">request</button> <button type="button" class="sd-link-btn sd-link-btn--inline" data-action="retry-attribution" data-round="', round.roundIndex, '">response</button></span></td>',
      '<td class="status-col">', statusBadges(round, hasIssues, isLowCache), '</td>',
      '<td class="time-col"><span class="sd-round-time">', escapeHtml(parity.time || ''), '</span></td>'
    ].join(''));
    return tr;
  }

  function applySessionPayloads(payloadsResponse) {
    if (!payloadsResponse) return;
    setText('[data-session-payload-policy]', 'Payload hidden by default · ' + formatNumber(payloadsResponse.payloadCount || 0) + ' payload sources loaded from API');
    var container = qs(document, '[data-payload-sources-container]');
    if (!container) return;
    var payloads = payloadsResponse.payloads || [];
    container.replaceChildren.apply(container, payloads.map(function (payload) {
      var tpl = document.createElement('template');
      tpl.setAttribute('data-payload-source', payload.payloadId || '');
      tpl.setAttribute('data-payload-kind', payload.kind || '');
      tpl.setAttribute('data-payload-status', payload.status || '');
      tpl.setAttribute('data-payload-token-estimate', '');
      var section = document.createElement('section');
      section.className = 'sd-payload-section payload-section';
      setMarkup(section, '<h3>' + escapeHtml(payload.title || payload.payloadId || 'Payload') + '</h3>'
        + '<pre>Payload source ' + escapeHtml(payload.payloadId || '') + ' is loaded through ' + escapeHtml(payload.apiUrl || '') + '.</pre>');
      tpl.content.appendChild(section);
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
      + '<article class="sd-diagnostic-card sd-diagnostic-card--wide sd-diagnostic-card--agents">'
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
  }

  function agentsTableHtml(agents) {
    if (!agents.length) return '<div class="sd-card-empty">No agent runs indexed</div>';
    var rows = agents.map(function (row, idx) {
      var active = idx === 0 ? ' is-active' : '';
      return '<tr class="sd-subagent-row' + active + '" data-subagent-row>'
        + '<td class="sd-subagent-table__agent"><span class="sd-subagent-select' + active + '"><span class="sd-subagent-select__main"><b>'
        + escapeHtml(row.agent || 'agent') + '</b><span class="sd-subagent-instance sd-subagent-instance--main">'
        + escapeHtml(row.shortId || '') + '</span></span></span></td>'
        + '<td class="sd-subagent-table__copy-cell"><span class="sd-subagent-copy-value" title="' + escapeHtml(row.sessionFile || '') + '">'
        + escapeHtml(row.sessionFileDisplay || '—') + '</span> <button type="button" class="sd-subagent-copy-btn" data-action="copy" data-copy-text="'
        + escapeHtml(row.sessionFile || '') + '">Copy</button></td>'
        + '<td class="sd-subagent-table__copy-cell"><span class="sd-subagent-copy-value" title="' + escapeHtml(row.sessionId || '') + '">'
        + escapeHtml(row.sessionIdDisplay || '—') + '</span> <button type="button" class="sd-subagent-copy-btn" data-action="copy" data-copy-text="'
        + escapeHtml(row.sessionId || '') + '">Copy</button></td>'
        + '<td>' + formatNumber(row.llmCalls) + ' LLM</td>'
        + '<td>' + escapeHtml(row.tokens || '0') + ' · ' + escapeHtml(row.tokenShare || 'N/A') + '</td>'
        + '<td>' + formatNumber(row.tools) + ' tools</td>'
        + '<td><b class="sd-rate">' + escapeHtml(row.failureLabel || (formatNumber(row.failures) + ' failed · ' + (row.failureRate || 'N/A'))) + '</b></td>'
        + '</tr>';
    }).join('');
    return '<div class="sd-subagent-workbench"><div class="sd-subagent-table-scroll"><table class="sd-subagent-table">'
      + '<thead><tr><th>Agent</th><th>Session file</th><th>Session id</th><th>LLM</th><th>Tokens</th><th>Tools</th><th>Failures</th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table></div></div>';
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
    if (!rows.length) return '<div class="sd-card-empty">No tool calls indexed</div>';
    var body = rows.map(function (row) {
      return '<tr title="' + escapeHtml(row.splitNote || '') + '"><td>' + escapeHtml(row.tool || 'tool') + '</td><td>'
        + formatNumber(row.calls) + '</td><td>' + escapeHtml(row.tokens || '0') + '</td><td><span class="sd-rate">'
        + formatNumber(row.failures) + ' · ' + escapeHtml(row.failureRate || 'N/A') + '</span></td></tr>';
    }).join('');
    return '<table class="sd-compact-table"><thead><tr><th>Tool</th><th>Calls</th><th>Result Tokens</th><th>Failures</th></tr></thead><tbody>'
      + body + '<tr class="sd-table-summary-row"><td>Summary</td><td>' + formatNumber(toolImpact.allToolCalls || 0)
      + '</td><td>' + formatNumber(toolImpact.distinctTools || 0) + ' tools</td><td><span class="sd-rate">'
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

  function tokenbarHtml(tokens) {
    var total = Number(tokens && tokens.total || 0);
    if (total <= 0) return '';
    var fresh = pct(tokens.fresh, total);
    var read = pct(tokens.cacheRead, total);
    var write = pct(tokens.cacheWrite, total);
    var out = pct(tokens.output, total);
    return '<div class="token-group"><span class="metric-token">' + formatSessionCompact(total) + '</span>'
      + '<span class="tokenbar-wrap" tabindex="0" title="Loaded from rounds API" aria-label="Token breakdown loaded from rounds API" style="--token-total-width:100%;">'
      + '<span class="tokenbar"><span class="tokenbar-seg fresh" style="--segment-width:' + fresh + '%"></span>'
      + '<span class="tokenbar-seg read" style="--segment-width:' + read + '%"></span>'
      + '<span class="tokenbar-seg write" style="--segment-width:' + write + '%"></span>'
      + '<span class="tokenbar-seg out" style="--segment-width:' + out + '%"></span></span>'
      + '<div class="token-tooltip" aria-hidden="true"><div class="token-tooltip__title">Token Breakdown</div>'
      + '<div class="token-tooltip__row"><span>Fresh</span><span class="token-tooltip__value">' + formatSessionCompact(tokens.fresh) + '</span></div>'
      + '<div class="token-tooltip__row"><span>Cache Read</span><span class="token-tooltip__value">' + formatSessionCompact(tokens.cacheRead) + '</span></div>'
      + '<div class="token-tooltip__row"><span>Cache Write</span><span class="token-tooltip__value">' + formatSessionCompact(tokens.cacheWrite) + '</span></div>'
      + '<div class="token-tooltip__row"><span>Output</span><span class="token-tooltip__value">' + formatSessionCompact(tokens.output) + '</span></div>'
      + '</div></span></div>';
  }

  function statusBadges(round, hasIssues, isLowCache) {
    var html = '';
    (round.signals || []).forEach(function (signal) {
      var tone = signal === 'Failed' ? ' sd-signal-badge--failed' : '';
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
