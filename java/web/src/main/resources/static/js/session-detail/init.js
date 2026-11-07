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
    var resources = {
      meta: applySessionMeta,
      metrics: applySessionMetrics,
      diagnostics: applySessionDiagnostics,
      rounds: applySessionRounds
    };
    Object.keys(resources).forEach(function (name) {
      document.body.setAttribute('data-session-api-' + name + '-state', 'loading');
    });
    function updateHydrated() {
      var complete = Object.keys(resources).every(function (name) {
        return document.body.getAttribute('data-session-api-' + name + '-state') === 'true';
      });
      document.body.setAttribute('data-session-api-hydrated', String(complete));
    }
    var snapshot = window.IndexSnapshot.create();
    var pendingDeepLink = null;
    function applyPublishedDeepLink() {
      var pending = pendingDeepLink;
      pendingDeepLink = null;
      if (!pending || pending.rounds !== sessionDetailState.rounds
          || document.body.getAttribute('data-session-api-rounds-state') !== 'true'
          || !document.body.hasAttribute('data-index-generation')
          || document.querySelector('[data-snapshot-batch-error]')) return;
      // The coordinator Promise resolves only after it publishes the checked generation.
      jumpRound(pending.root, pending.params.get('round'), {
        subagent: pending.params.get('subagent') || '',
        subagentRound: pending.params.get('subagentround') || pending.params.get('subagent_round') || '',
        smooth: false
      });
    }
    window.addEventListener('index-snapshot-restored', applyPublishedDeepLink);
    snapshot.load(Object.keys(resources).map(function (name) {
      return {
        key: name,
        url: base + '/' + name,
        apply: function (part) {
          var error = document.querySelector('[data-resource-error="' + name + '"]');
          if (error) error.remove();
          resources[name](part);
          if (name === 'rounds') {
            document.body.setAttribute('data-session-round-count', String(part.roundCount || 0));
            var params = new URLSearchParams(window.location.search || '');
            var root = document.querySelector('[data-trace-page]') || document;
            var status = params.get('trace_status') || 'all';
            if (status === 'failed' || status === 'low-cache') setFilter(root, status);
            if (params.get('round') && typeof jumpRound === 'function') {
              pendingDeepLink = { root: root, params: params, rounds: sessionDetailState.rounds };
            }
          }
          if (name === 'diagnostics') document.body.setAttribute('data-session-anomaly-count', String(part.anomalyCount || 0));
          document.body.setAttribute('data-session-api-' + name + '-state', 'true');
          updateHydrated();
        },
        error: function (err, retry) {
          document.body.setAttribute('data-session-api-' + name + '-state', 'false');
          updateHydrated();
          showSessionResourceError(name, err, function () {
            return Promise.resolve(retry()).then(applyPublishedDeepLink);
          });
        }
      };
    })).then(applyPublishedDeepLink);
  }

  // Continuations are bound to the already rendered IndexSnapshot, never a new snapshot.
  function readSessionContentPage(url) {
    var expected = document.body.getAttribute('data-index-generation') || '';
    var headers = { Accept: 'application/json' };
    if (expected && expected !== 'legacy') headers['X-Session-Index-Generation'] = expected;
    return fetch(url, { headers: headers, cache: 'no-store' }).then(function (response) {
      var current = document.body.getAttribute('data-index-generation') || '';
      var actual = response.headers.get('X-Session-Index-Generation') || '';
      if (current !== expected || response.status === 409 || (expected && expected !== 'legacy' && actual !== expected)) {
        throw new Error('Index changed; refresh the page before continuing');
      }
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    }).then(function (data) {
      if ((document.body.getAttribute('data-index-generation') || '') !== expected) throw new Error('Index changed; refresh the page before continuing');
      return data;
    });
  }

  function contentPager(target, section, loaded, total, cursor, load, existing) {
    var pager = existing || document.createElement('div');
    pager.setAttribute('data-content-pagination', section);
    pager.replaceChildren();
    var label = document.createElement('span');
    var sectionLabel = { rounds: 'Rounds', 'round-members': 'Round records', 'round-tools': 'Tools in this member page' }[section] || section;
    label.textContent = sectionLabel + ': ' + loaded + ' / ' + total + ' loaded. ';
    pager.appendChild(label);
    if (cursor) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'sd-btn sd-btn--secondary sd-btn--sm';
      button.setAttribute('data-action', 'load-content-page');
      button.textContent = 'Load more';
      button.loadContentPage = function () {
        if (button.disabled) return;
        button.disabled = true;
        button.textContent = 'Loading…';
        var error = pager.querySelector('[role="alert"]');
        if (error) error.remove();
        Promise.resolve().then(function () { return load(cursor); }).catch(function (err) {
          if (!pager.isConnected) return;
          var message = document.createElement('span');
          message.setAttribute('role', 'alert');
          message.textContent = ' Unable to load: ' + err.message + '. ';
          pager.appendChild(message);
          button.textContent = /refresh/i.test(err.message) ? 'Refresh page' : 'Retry';
          if (/refresh/i.test(err.message)) button.loadContentPage = function () { window.location.reload(); };
        }).finally(function () { button.disabled = false; });
      };
      pager.appendChild(button);
    }
    if (!existing) target.appendChild(pager);
    return pager;
  }

  function updateRoundsPager(response, loaded) {
    var previous = qs(document, '[data-content-pagination="rounds"]');
    var table = qs(document, '.trace-table[data-trace-list]');
    if (!table || (!response.nextCursor && !previous)) return;
    var target = table.parentNode;
    contentPager(target, 'rounds', loaded, response.total ?? response.roundCount, response.nextCursor, function (cursor) {
      var url = getApiBase().replace(/\/$/, '') + '/rounds?cursor=' + encodeURIComponent(cursor);
      if (sessionDetailState.roundFilter) url += '&trace_status=' + encodeURIComponent(sessionDetailState.roundFilter);
      var ticket = sessionDetailState.filterTicket;
      var epoch = sessionDetailState.roundsEpoch;
      return readSessionContentPage(url).then(function (part) {
        if (ticket !== sessionDetailState.filterTicket || epoch !== sessionDetailState.roundsEpoch || !target.isConnected) return;
        appendSessionRounds(part);
      });
    }, previous);
  }

  function reloadPagedRoundsFilter(status) {
    if (!sessionDetailState.roundsPaged) return;
    var ticket = (sessionDetailState.filterTicket || 0) + 1;
    sessionDetailState.filterTicket = ticket;
    sessionDetailState.roundFilter = status;
    var previous = qs(document, '[data-content-pagination="rounds"]');
    if (previous) previous.remove();
    var url = getApiBase().replace(/\/$/, '') + '/rounds?trace_status=' + encodeURIComponent(status);
    return readSessionContentPage(url).then(function (part) {
      if (sessionDetailState.filterTicket !== ticket) return;
      applySessionRounds(part);
      setFilter(document, status);
    }).catch(function (error) {
      if (sessionDetailState.filterTicket !== ticket) return;
      showSessionResourceError('rounds', error, function () { return reloadPagedRoundsFilter(status); });
    });
  }

  function appendSessionRounds(response) {
    var tbody = qs(document, '.trace-table[data-trace-list] tbody');
    if (!tbody) return;
    var globalIndex = sessionDetailState.rounds.reduce(function (sum, round) { return sum + Math.max(1, Number(round.callCount || 1)); }, 1);
    (response.rounds || []).forEach(function (round) {
      tbody.appendChild(roundRow(round, globalIndex, sessionDetailState.maxRoundTokens));
      globalIndex += Math.max(1, Number(round.callCount || 1));
      sessionDetailState.rounds.push(round);
    });
    updateRoundsPager(response, sessionDetailState.rounds.length);
    var active = qs(document, '[data-action^="status-"].is-active');
    if (active) setFilter(document, active.getAttribute('data-action').replace('status-', ''));
    setupTokenTooltips();
    syncToggleAllButton(document);
  }

  function showSessionResourceError(name, err, retry) {
    var selectors = {
      meta: '[data-session-hero] h1, [data-session-meta-chips], [data-session-updated]',
      metrics: '[data-session-metrics-shell] .sd-kpi:not([aria-label="Run Health"]) .sd-kpi__value, [data-session-metrics-shell] .sd-kpi:not([aria-label="Run Health"]) .sd-kpi__subgrid',
      diagnostics: '[data-issue-strip], .sd-kpi[aria-label="Run Health"] .sd-kpi__value, .sd-kpi[aria-label="Run Health"] .sd-kpi__subgrid'
    };
    if (selectors[name]) qsa(document, selectors[name]).forEach(function (node) { node.textContent = 'Unavailable'; });
    if (name === 'diagnostics') {
      var strip = qs(document, '[data-issue-strip]');
      if (strip) strip.classList.remove('sd-issue-strip--loading');
    }
    var target = name === 'rounds' ? qs(document, '.trace-table[data-trace-list] tbody')
      : name === 'diagnostics' ? qs(document, '[data-session-diagnostics]')
      : qs(document, '[data-session-hero]') || document.body;
    if (!target) return;
    var previous = document.querySelector('[data-resource-error="' + name + '"]');
    if (previous) previous.remove();
    var error = document.createElement(name === 'rounds' ? 'tr' : 'div');
    error.setAttribute('data-resource-error', name);
    var content = error;
    if (name === 'rounds') {
      content = document.createElement('td');
      content.colSpan = 6;
      error.appendChild(content);
    }
    content.setAttribute('role', 'alert');
    content.appendChild(document.createTextNode('Unable to load ' + name + ' (' + (err.message || 'Request failed') + '). '));
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn';
    button.textContent = 'Retry';
    button.addEventListener('click', function () {
      button.disabled = true;
      retry().then(function () { button.disabled = false; });
    });
    content.appendChild(button);
    if (name === 'rounds' || name === 'diagnostics') target.replaceChildren(error);
    else target.appendChild(error);
  }

  function applySessionMeta(meta) {
    if (!meta) return;
    var parity = meta.parity || {};
    var title = qs(document, '[data-session-hero] h1');
    if (title) {
      var display = meta.displayTitle || { text: meta.title };
      title.textContent = display.text || (meta.filters && meta.filters.sessionId) || 'Untitled session';
      title.removeAttribute('title');
      if (display.html) appendRenderedMarkdown(title, display.html);
      var original = qs(document, '[data-session-original-title]');
      if (original) {
        original.hidden = !meta.title || meta.title === display.text;
        original.querySelector('pre').textContent = original.hidden ? '' : meta.title;
      }
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
        chip(parity.date || '—')
      );
    }
    setText('[data-session-updated]', parity.updatedLocal || meta.updatedAt || '—');
  }

  function applySessionMetrics(metrics) {
    if (!metrics || !metrics.tokens) return;
    sessionDetailState.metrics = metrics;
    var parity = metrics.parity || {};
    var hasContent = hasSessionContent();
    function observed(value) { return hasContent && typeof value === 'number' ? formatNumber(value) : 'N/A'; }
    setKpi('Total Tokens', TokenProvenance.total(metrics.tokens, formatSessionCompact), [
      measuredTokenSubline('Fresh', metrics.tokens, 'fresh', parity.freshShare),
      measuredTokenSubline('Cache Read', metrics.tokens, 'cacheRead', parity.cacheReadShare),
      measuredTokenSubline('Cache Write', metrics.tokens, 'cacheWrite', parity.cacheWriteShare),
      measuredTokenSubline('Output', metrics.tokens, 'output', parity.outputShare)
    ]);
    TokenProvenance.attach(qs(document, '.sd-kpi[aria-label="Total Tokens"]'), metrics.tokens);
    var inputSide = Number(metrics.tokens.fresh || 0) + Number(metrics.tokens.cacheRead || 0) + Number(metrics.tokens.cacheWrite || 0);
    var measuredInput = TokenProvenance.measuredInput(metrics.tokens);
    setKpi('Cache Health', TokenProvenance.ratio(metrics.tokens, metrics.cacheReadRatio), [
      subline('Input-side Tokens', measuredInput ? formatSessionCompact(inputSide) : 'N/A · Partial'),
      subline('Low-cache rows', measuredInput && parity.lowCacheRoundsAvailable === true && typeof parity.lowCacheRounds === 'number' ? formatNumber(parity.lowCacheRounds) : 'N/A'),
      subline('Fresh-spike rows', observed(parity.freshSpikeRounds))
    ]);
    TokenProvenance.attach(qs(document, '.sd-kpi[aria-label="Cache Health"]'), metrics.tokens);
    setKpi('Workload', observed(parity.workloadCalls), [
      subline('Main records', observed(parity.mainCalls)),
      subline('Subagent records', observed(parity.subagentCalls)),
      subline('Tool Calls', observed(parity.toolCalls ?? metrics.toolCalls)),
      subline('Subagent Runs', observed(parity.subagentRuns ?? metrics.subagents))
    ]);
    var timingCard = qs(document, '[data-session-timing], .sd-kpi[aria-label="Source Task Active"], .sd-kpi[aria-label="Active Time"]');
    setKpi(timingCard ? timingCard.getAttribute('aria-label') : 'Active Time', SessionTiming.value(metrics.timing, 'activeTaskSeconds'), [
      subline('Wall Duration', SessionTiming.value(metrics.timing, 'wallSeconds')),
      subline('Agent Turn', SessionTiming.value(metrics.timing, 'agentTurnSeconds')),
      subline('Model Execution', SessionTiming.value(metrics.timing, 'modelExecutionSeconds')),
      subline('Tool Execution', SessionTiming.value(metrics.timing, 'toolExecutionSeconds'))
    ]);
    SessionTiming.applyDetail(timingCard, metrics.timing);
    document.body.setAttribute('data-session-api-total-tokens', String(metrics.tokens.total || 0));
    document.body.setAttribute('data-session-api-failed-tools', String(metrics.failedTools || 0));
    if (sessionDetailState.diagnostics) applySessionDiagnostics(sessionDetailState.diagnostics);
  }

  function hasSessionContent() {
    return sessionDetailState.roundsLoaded ? sessionDetailState.rounds.length > 0
      : Number((sessionDetailState.metrics || {}).roundCount || 0) > 0;
  }

  function applySessionDiagnostics(diagnostics) {
    if (!diagnostics) return;
    sessionDetailState.diagnostics = diagnostics;
    var parity = diagnostics.parity || {};
    var hasContent = hasSessionContent();
    var count = Number(parity.issueRounds || diagnostics.anomalyCount || 0);
    setKpi('Run Health', !hasContent ? 'Unknown' : (count > 0 ? 'Issue signals detected' : 'No issue signals detected'), [
      subline('Issue rows', hasContent ? formatNumber(count) : 'N/A'),
      hasContent ? rateSubline('Failed Tools', parity.failedTools || 0, parity.failedToolsTotal || parity.toolCalls || (parity.toolImpact && parity.toolImpact.allToolCalls) || 0, parity.failedToolsRate) : subline('Failed Tools', 'N/A'),
      subline('Payload Gaps', hasContent && typeof parity.payloadGaps === 'number' ? formatNumber(parity.payloadGaps) : 'N/A'),
      subline('Attribution Gaps', hasContent && (parity.attributionGapsAvailable === true || parity.attributionGaps > 0) ? formatNumber(parity.attributionGaps) : 'N/A')
    ]);
    var strip = qs(document, '[data-issue-strip]');
    if (strip) {
      strip.classList.toggle('sd-issue-strip--ok', hasContent && count === 0);
      strip.classList.remove('sd-issue-strip--loading');
      strip.replaceChildren();
      var title = document.createElement('span');
      title.className = 'sd-issue-title';
      title.textContent = !hasContent ? 'Unknown · No round content available' : (count > 0 ? 'Issue Signals' : 'No issue signals detected');
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
        ok.textContent = hasContent ? 'Issue checks do not establish completion or content completeness' : 'Session completion and failures are not established';
        strip.appendChild(ok);
      }
    }
    sessionDetailState.diagnosticsParity = parity;
    renderDiagnosticsCards(parity);
  }

  function applySessionRounds(roundsResponse) {
    var tbody = qs(document, '.trace-table[data-trace-list] tbody');
    if (!tbody || !roundsResponse) return;
    var boundaries = qs(document, '[data-trace-boundaries]');
    if (boundaries && roundsResponse.modelCallCount != null) {
      boundaries.textContent = (roundsResponse.modelCallCount
        ? formatNumber(roundsResponse.modelCallCount) + ' 次有证据的调用'
        : '未确认独立模型调用边界')
        + (roundsResponse.recordGroupCount ? ' · ' + formatNumber(roundsResponse.recordGroupCount) + ' 个未确认记录组。' : '。');
    }
    sessionDetailState.roundsEpoch = (sessionDetailState.roundsEpoch || 0) + 1;
    var previousPager = document.querySelector('[data-content-pagination="rounds"]');
    if (previousPager) previousPager.remove();
    sessionDetailState.roundsPaged = Boolean(roundsResponse.nextCursor || roundsResponse.total != null);
    var rows = roundsResponse.rounds || [];
    sessionDetailState.roundsLoaded = true;
    sessionDetailState.rounds = rows;
    if (sessionDetailState.metrics) applySessionMetrics(sessionDetailState.metrics);
    else if (sessionDetailState.diagnostics) applySessionDiagnostics(sessionDetailState.diagnostics);
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
      if (sessionDetailState.diagnosticsParity) renderDiagnosticsCards(sessionDetailState.diagnosticsParity);
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
    updateRoundsPager(roundsResponse, rows.length);
    setupTokenTooltips();
    if (sessionDetailState.diagnosticsParity) renderDiagnosticsCards(sessionDetailState.diagnosticsParity);
    syncToggleAllButton(document);
  }

  function roundRow(round, globalCallIndex, maxRoundTokens) {
    var tr = document.createElement('tr');
    var tokens = round.tokens || {};
    var parity = round.parity || {};
    var inputSide = Number(tokens.fresh || 0) + Number(tokens.cacheRead || 0) + Number(tokens.cacheWrite || 0);
    var isLowCache = TokenProvenance.measuredInput(tokens) && (Boolean(parity.isLowCache) || (inputSide > 0 && (Number(tokens.cacheRead || 0) / inputSide) < 0.2));
    var hasIssues = Boolean(parity.hasIssues) || (round.status || '') === 'failed' || Number(round.failedToolCount || 0) > 0;
    var isUserInput = Boolean(parity.isUserInput);
    var visualStatus = hasIssues ? 'failed' : (isUserInput ? 'user' : (round.status || 'ok'));
    var summary = String(parity.summary || '').trim();
    if (summary === 'Round ' + round.roundIndex || summary === '内容未记录') summary = '';
    var summaryRole = { user: '用户', assistant: '助手' }[parity.summaryRole] || '';
    var label = (parity.modelCallEvidence ? 'R' : 'G') + round.roundIndex;
    var target = round.callCount === 1 ? '/attribution/' + round.roundIndex + '/1/' : '';
    var actions = round.callCount > 0 ? [
      '<span class="sd-attribution-actions sd-attribution-actions--row" aria-label="内容与 Token 归因">',
      contentPayloadButton('round:req:' + round.roundIndex, 'llm_request', label + ' · Request', 'Request', target && target + 'request'),
      contentPayloadButton('round:resp:' + round.roundIndex, 'llm_response', label + ' · Response', 'Response', target && target + 'response'),
      '</span>'
    ].join('') : '<span class="muted">未记录调用</span>';
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
      '<span class="round-chevron" aria-hidden="true">›</span>', label, '</button></td>',
      '<td class="summary-col">', summaryRole ? '<span class="summary-role">' + summaryRole + '</span>' : '',
      '<span class="summary-title', summary ? '' : ' summary-title--missing', '"', summary ? ' title="' + escapeHtml(summary) + '"' : '',
      '>', escapeHtml(summary || '摘要未记录'), '</span></td>',
      '<td class="metrics-col mono"><div class="metric-cell"><span class="metric-calls-tools"><span>', formatNumber(round.callCount), ' records</span><span>', formatNumber(round.toolCallCount), ' tools</span></span>', tokenbarHtml(tokens, maxRoundTokens), '</div></td>',
      '<td class="attribution-col">', actions, '</td>',
      '<td class="status-col">', statusBadges(round, hasIssues, isLowCache), '</td>',
      '<td class="time-col"><span class="round-time">', escapeHtml(parity.time || '未记录'), '</span></td>'
    ].join(''));
    TokenProvenance.attach(tr.querySelector('.metric-cell'), tokens);
    return tr;
  }

  function renderDiagnosticsCards(parity) {
    var root = qs(document, '[data-session-diagnostics]');
    if (!root || !parity) return;
    if (!hasSessionContent()) {
      setMarkup(root, '<article class="sd-diagnostic-card sd-diagnostic-card--wide"><header class="sd-diagnostic-card__head"><h2>Content evidence unavailable</h2><span>Unknown</span></header><div class="sd-diagnostic-card__body"><div class="sd-card-empty">No round content is available. Agent, tool and failure counts are N/A, not measured zero.</div></div></article>');
      return;
    }
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
        failureLabel = 'No failure signals · 0 failed';
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
        + '<td>' + escapeHtml(diagnosticAgentTokens(row)) + '</td>'
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
      + formatNumber(agent.llmCalls) + ' LLM · ' + escapeHtml(diagnosticAgentTokens(agent)) + ' tokens · '
      + formatNumber(agent.tools) + ' tools · ' + formatNumber(agent.failures) + ' failures</small></div>'
      + timeline + '</section>';
  }

  // 折线与 tooltip 共用输入侧口径，不包含输出 token。
  function diagnosticAgentTokens(agent) {
    if (agent.tokenSegments && typeof agent.tokenSegments === 'object') return TokenProvenance.total(agent.tokenSegments, formatSessionCompact);
    if (agent.tokens && typeof agent.tokens === 'object') return TokenProvenance.total(agent.tokens, formatSessionCompact);
    return (agent.tokens || 'N/A') + ' · Unknown source';
  }

  function roundCacheReadRatio(tokens) {
    if (!TokenProvenance.measuredInput(tokens)) return null;
    var inputSide = Number(tokens.fresh || 0) + Number(tokens.cacheRead || 0) + Number(tokens.cacheWrite || 0);
    return inputSide > 0 ? Math.max(0, Math.min(100, Number(tokens.cacheRead || 0) / inputSide * 100)) : null;
  }

  function tokenRoundChartHtml(rounds, label) {
    if (!rounds || !rounds.length) {
      return '<div class="sd-card-empty">' + (sessionDetailState.roundsLoaded
        ? 'No normalized rounds available. The source log may be missing.'
        : 'Round timeline is loading from /rounds API.') + '</div>';
    }
    var maxTotal = Math.max(1, sessionDetailState.maxRoundTokens || 1);
    var plotWidth = Math.max(320, rounds.length * 32 + 44);
    var pointGroups = [];
    var currentPoints = [];
    rounds.forEach(function (round, idx) {
      var tokens = round.tokens || {};
      var ratio = roundCacheReadRatio(tokens);
      if (ratio == null) {
        if (currentPoints.length) pointGroups.push(currentPoints.join(' '));
        currentPoints = [];
      } else currentPoints.push((idx * 32) + ',' + (100 - Math.max(0, Math.min(100, ratio))).toFixed(1));
    });
    if (currentPoints.length) pointGroups.push(currentPoints.join(' '));
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
      if (TokenProvenance.measuredInput(tokens) && parity.isLowCache) tags.push('low cache');
      if (parity.isFreshSpike) tags.push('fresh spike');
      return '<button type="button" class="sd-token-round" data-action="jump-round" data-round="' + escapeHtml(round.roundIndex) + '" aria-label="R' + escapeHtml(round.roundIndex) + ' token timeline">'
        + '<span class="sd-token-round__bar" aria-label="R' + escapeHtml(round.roundIndex) + '" style="--bar-height-px:' + height.toFixed(1) + 'px">'
        + '<span class="sd-token-round__seg sd-token-round__seg--fresh" style="--seg-height:' + fresh + '%"></span>'
        + '<span class="sd-token-round__seg sd-token-round__seg--read" style="--seg-height:' + read + '%"></span>'
        + '<span class="sd-token-round__seg sd-token-round__seg--write" style="--seg-height:' + write + '%"></span>'
        + '<span class="sd-token-round__seg sd-token-round__seg--out" style="--seg-height:' + out + '%"></span></span>'
        + '<span class="sd-token-round-tooltip" role="tooltip"><b>R' + escapeHtml(round.roundIndex) + ' · ' + escapeHtml(parity.time || '未记录') + '</b>'
        + '<div>Token shares below use Total, including Output.</div>'
        + '<span><i class="sd-tooltip-mark sd-tooltip-mark--fresh"></i><small>Fresh</small><em>' + escapeHtml(TokenProvenance.value(tokens, 'fresh', formatSessionCompact)) + '</em><strong>' + measuredShare(tokens, fresh) + '</strong></span>'
        + '<span><i class="sd-tooltip-mark sd-tooltip-mark--read"></i><small>Cache Read</small><em>' + escapeHtml(TokenProvenance.value(tokens, 'cacheRead', formatSessionCompact)) + '</em><strong>' + measuredShare(tokens, read) + '</strong></span>'
        + '<span><i class="sd-tooltip-mark sd-tooltip-mark--write"></i><small>Cache Write</small><em>' + escapeHtml(TokenProvenance.value(tokens, 'cacheWrite', formatSessionCompact)) + '</em><strong>' + measuredShare(tokens, write) + '</strong></span>'
        + '<span><i class="sd-tooltip-mark sd-tooltip-mark--out"></i><small>Output</small><em>' + escapeHtml(TokenProvenance.value(tokens, 'output', formatSessionCompact)) + '</em><strong>' + measuredShare(tokens, out) + '</strong></span>'
        + '<span class="sd-token-round-tooltip__total"><i></i><small>Total</small><em>' + escapeHtml(TokenProvenance.total(tokens, formatSessionCompact)) + '</em><strong>' + measuredShare(tokens, total > 0 ? 100 : 0) + '</strong></span>'
        + '<span class="sd-token-round-tooltip__tags"><i class="sd-tooltip-mark sd-tooltip-mark--line"></i><small>Cache Read / Input</small><em>' + escapeHtml(TokenProvenance.ratio(tokens)) + '</em></span>'
        + '<div>' + escapeHtml(TokenProvenance.note(tokens)) + '</div>'
        + (tags.length ? '<span class="sd-token-round-tooltip__tags"><i class="sd-tooltip-mark sd-tooltip-mark--spike"></i><small>Badge Text</small><em>' + escapeHtml(tags.join(', ')) + '</em></span>' : '')
        + '</span><span class="sd-token-round__signal-slot" aria-hidden="true">' + (tags.length ? '<span class="sd-token-round__spike"></span>' : '') + '</span>'
        + '<span class="sd-token-round__label">R' + escapeHtml(round.roundIndex) + '</span></button>';
    }).join('');
    return '<div><small><i class="sd-tooltip-mark sd-tooltip-mark--line" aria-hidden="true"></i> Black line: Cache Read / Input (0–100%, excludes Output). Bars: token totals.</small></div>'
      + '<div><small>Only provider-reported input forms the ratio. Not reported / Unknown / Estimated: N/A, not 0%.</small></div>'
      + '<div class="sd-token-round-chart" aria-label="' + escapeHtml(label || 'agent') + ' token composition">'
      + '<div class="sd-token-round-plot" style="--plot-width:' + plotWidth + 'px; --ratio-line-left:22px; --ratio-line-width:' + Math.max(0, plotWidth - 44) + 'px">'
      + '<svg class="sd-token-ratio-line" viewBox="0 0 ' + Math.max(1, plotWidth - 44) + ' 100" preserveAspectRatio="none" aria-label="Agent cache read ratio line">'
      + pointGroups.map(function (points) { return '<polyline points="' + escapeHtml(points) + '"></polyline>'; }).join('') + '</svg>' + buttons + '</div></div>';
  }

  function contextBudgetHtml(segments) {
    if (!segments.length) return '<div class="sd-card-empty">No context budget available</div>';
    function measurement(segment) {
      var precision = segment.precision || 'unknown';
      var numeric = typeof segment.tokens === 'number' && Number.isFinite(segment.tokens) && segment.tokens >= 0;
      var observed = numeric ? formatSessionCompact(segment.tokens) : (segment.tokensLabel || 'N/A');
      var tokens = 'N/A · Unknown';
      if (precision === 'provider_reported') tokens = observed + ' · Provider reported';
      else if (precision === 'estimated') tokens = '≈' + observed.replace(/^[~≈]/, '') + ' · Estimated';
      else if (precision === 'unavailable') tokens = 'Not reported';
      else if (precision === 'mixed') tokens = (numeric && segment.tokens > 0 ? observed : 'N/A') + ' · Partial';
      else if ((numeric && segment.tokens > 0) || (!numeric && observed !== '0' && observed !== 'N/A')) tokens = observed + ' · Unknown';
      var known = ['provider_reported', 'estimated', 'mixed'].indexOf(precision) !== -1;
      var available = segment.includedInUsage === true && known
        && ['available', 'partial'].indexOf(segment.shareStatus) !== -1
        && typeof segment.shareValue === 'number' && Number.isFinite(segment.shareValue)
        && segment.shareValue >= 0 && segment.shareValue <= 100;
      var share = 'N/A';
      if (available) {
        var partial = segment.shareStatus === 'partial' || precision !== 'provider_reported';
        share = (partial ? '≈' : '') + String(Math.round(segment.shareValue * 10) / 10) + '%' + (partial ? ' · Partial' : '');
      }
      if (segment.includedInUsage === false) share = 'N/A · Not in usage';
      else if (segment.includedInUsage !== true) share = 'N/A · Usage inclusion unknown';
      return { tokens: tokens, share: share, available: available };
    }
    var bars = segments.map(function (segment, idx) {
      var measured = measurement(segment);
      if (!measured.available) return '';
      return '<span class="sd-context-segment sd-context-segment--' + (idx + 1) + ' sd-context-segment--' + escapeHtml(segment.status || 'available')
        + '" style="--seg-width:' + escapeHtml(segment.shareValue) + '%"><span class="sd-context-segment__label">'
        + escapeHtml(segment.label || '') + '</span><span class="sd-context-segment__pct">' + escapeHtml(measured.share) + '</span></span>';
    }).join('');
    var legend = segments.map(function (segment, idx) {
      var measured = measurement(segment);
      return '<div class="sd-context-budget__item sd-context-budget__item--' + escapeHtml(segment.status || 'available') + '"><i class="sd-context-budget__dot sd-context-budget__dot--'
        + (idx + 1) + '" aria-hidden="true"></i><span>' + escapeHtml(segment.label || '') + '</span><b>'
        + escapeHtml(measured.tokens) + '<br>' + escapeHtml(measured.share) + '</b></div>';
    }).join('');
    return '<div class="sd-context-segmented" aria-label="Context budget segmented bar">' + bars + '</div>'
      + '<div class="sd-context-note" aria-label="Context budget measurements">' + legend + '</div>'
      + '<div class="sd-context-note">Usage composition includes only explicitly included segments with available shares. Partial shares are approximate, not provider-exact. Unknown or unavailable measurements are not 0%; tool results are local estimates outside usage composition.</div>';
  }

  function measuredShare(tokens, share) {
    return TokenProvenance.state(tokens) === 'provider_reported' ? share + '%' : 'N/A';
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

  function measuredTokenSubline(label, tokens, key, shareLabel) {
    var line = tokenShareSubline(label, tokens[key], tokens.total, shareLabel);
    if (TokenProvenance.state(tokens) !== 'provider_reported') {
      line.value = TokenProvenance.value(tokens, key, formatSessionCompact);
      line.title = TokenProvenance.note(tokens);
    }
    return line;
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
    if (total <= 0) return '<span class="metric-token">' + escapeHtml(TokenProvenance.total(tokens, formatSessionCompact)) + '</span>';
    var fresh = pct(tokens.fresh, total);
    var read = pct(tokens.cacheRead, total);
    var write = pct(tokens.cacheWrite, total);
    var out = pct(tokens.output, total);
    var scale = maxRoundTokens > 0 ? Math.max(2, Math.min(100, Math.round((total / maxRoundTokens) * 1000) / 10)) : 100;
    var scaleLabel = scale + '% of max round tokens';
    return '<div class="token-group"><span class="metric-token">' + escapeHtml(TokenProvenance.total(tokens, formatSessionCompact)) + '</span>'
      + '<span class="tokenbar-wrap" tabindex="0" title="' + escapeHtml(scaleLabel) + '" aria-label="' + escapeHtml(scaleLabel) + '" style="--token-total-width:' + scale + '%;">'
      + '<span class="tokenbar"><span class="tokenbar-seg fresh" style="--segment-width:' + fresh + '%"></span>'
      + '<span class="tokenbar-seg read" style="--segment-width:' + read + '%"></span>'
      + '<span class="tokenbar-seg write" style="--segment-width:' + write + '%"></span>'
      + '<span class="tokenbar-seg out" style="--segment-width:' + out + '%"></span></span>'
      + '<div class="token-tooltip" aria-hidden="true"><div class="token-tooltip__title">Token Breakdown</div>'
      + '<div class="token-tooltip__row"><span>Fresh</span><span class="token-tooltip__value">' + escapeHtml(TokenProvenance.value(tokens, 'fresh', formatSessionCompact)) + '</span></div>'
      + '<div class="token-tooltip__row"><span>Cache Read</span><span class="token-tooltip__value">' + escapeHtml(TokenProvenance.value(tokens, 'cacheRead', formatSessionCompact)) + '</span></div>'
      + '<div class="token-tooltip__row"><span>Cache Write</span><span class="token-tooltip__value">' + escapeHtml(TokenProvenance.value(tokens, 'cacheWrite', formatSessionCompact)) + '</span></div>'
      + '<div class="token-tooltip__row"><span>Output</span><span class="token-tooltip__value">' + escapeHtml(TokenProvenance.value(tokens, 'output', formatSessionCompact)) + '</span></div>'
      + '<div class="token-tooltip__sep"></div><div class="token-tooltip__row token-tooltip__total"><span>Total</span><span class="token-tooltip__value">' + escapeHtml(TokenProvenance.total(tokens, formatSessionCompact)) + '</span></div>'
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
