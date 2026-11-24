  var sessionDetailState = { diagnosticsParity: null, rounds: [], maxRoundTokens: 0, filterTicket: 0 };

  function setupTokenTooltips() { TokenProvenance.bindTooltips(document); }
  function setupTokenRoundTooltips() { TokenProvenance.bindTooltips(document); }

  function hydrateSessionDetailApis() {
    if (!window.fetch || typeof getApiBase !== 'function') return;
    var apiBase = getApiBase();
    if (!apiBase) return;
    var base = apiBase.replace(/\/$/, '');
    var recovery = history.state && history.state.sessionSnapshotRecovery;
    if (recovery) {
      hydrateSessionDetailApis.recovering = true;
      history.replaceState({ ...history.state, sessionSnapshotRecovery: null }, '');
    }
    var resources = {
      meta: applySessionMeta,
      metrics: applySessionMetrics,
      diagnostics: applySessionDiagnostics,
      rounds: applySessionRounds,
      execution: applyExecutionSummary
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
    // "legacy" can also be a real stamp on a personal index before its first publication.
    hydrateSessionDetailApis.documentStamped = document.body.hasAttribute('data-index-generation');
    var snapshot = window.IndexSnapshot.create();
    var pendingDeepLink = null;
    function applyPublishedDeepLink() {
      var pending = pendingDeepLink;
      pendingDeepLink = null;
      if (!pending || pending.rounds !== sessionDetailState.rounds
          || document.body.getAttribute('data-session-api-rounds-state') !== 'true'
          || !document.body.hasAttribute('data-index-generation')
          || document.querySelector('[data-snapshot-batch-error]')) return;
      return runReadingNavigation(function (current) {
        if (recovery?.kind === 'tool-result') {
          return locateExecution(recovery.tool, current);
        }
        if (pending.params.get('execution')) return locateExecution(pending.params.get('execution'), current);
        return jumpRound(pending.root, pending.params.get('round'), {
          current: current,
          subagent: pending.params.get('subagent') || '',
          subagentRound: pending.params.get('subagentround') || pending.params.get('subagent_round') || ''
        });
      });
    }
    window.addEventListener('index-snapshot-restored', applyPublishedDeepLink);
    hydrateSessionDetailApis.ready = snapshot.load(Object.keys(resources).map(function (name) {
      return {
        key: name,
        url: base + '/' + name + (name === 'execution' ? '?summary=1' : ''),
        apply: function (part) {
          var error = document.querySelector('[data-resource-error="' + name + '"]');
          if (error) error.remove();
          resources[name](part);
          if (name === 'rounds') {
            document.body.setAttribute('data-session-round-count', String(part.roundCount || 0));
            var params = new URLSearchParams(window.location.search || '');
            var root = document.querySelector('[data-trace-page]') || document;
            var status = params.get('trace_status') || 'all';
            if (status === 'failed' || status === 'low-cache') {
              setFilter(root, status);
              if (!params.get('round') && !params.get('execution')) reloadPagedRoundsFilter(status);
            }
            if (params.get('round') || params.get('execution')) {
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
    }));
    hydrateSessionDetailApis.ready.then(function () {
      if (document.querySelector('[data-snapshot-batch-error]')) return;
      openReadingDetails(new URLSearchParams(location.search));
      applyPublishedDeepLink();
      if (recovery?.kind === 'first-question') {
        var first = qs(document, '[data-session-first-question] [data-action="open-payload"]');
        if (first && first.getClientRects().length) first.click();
        else runReadingNavigation(function () { throw new Error('索引已更新，当前会话已无首问可用'); });
      }
    });
  }

  // Continuations are bound to the already rendered IndexSnapshot, never a new snapshot.
  function readSessionContentPage(url, intent) {
    var trigger = document.activeElement;
    var roundRow = trigger && trigger.closest('[data-trace-round-row], [data-trace-detail]');
    var round = roundRow && (roundRow.dataset.round || (roundRow.id.match(/^round-(\d+)-detail$/) || [])[1]);
    function changed(published) {
      var target = new URL(window.location.href);
      var focusedRound = round && roundRow.contains(document.activeElement);
      var recovery = published && intent?.valid() ? intent : null;
      if (published && !intent && focusedRound && url === getApiBase() + '/round/' + round) {
        recovery = { kind: 'round', round: round };
      }
      var targetRound = recovery?.round || (focusedRound ? round : '');
      if (targetRound) {
        target.searchParams.set('round', targetRound);
        target.searchParams.delete('subagent');
        target.searchParams.delete('subagentround');
        target.searchParams.delete('subagent_round');
        target.searchParams.delete('execution');
        window.history.replaceState(window.history.state, '', target);
      }
      if (recovery && !hydrateSessionDetailApis.recovering) {
        hydrateSessionDetailApis.recovering = true;
        var state = { kind: recovery.kind, round: recovery.round, tool: recovery.tool };
        window.history.replaceState({ ...window.history.state, sessionSnapshotRecovery: state }, '', target);
        window.location.reload();
      }
      return new Error('Index changed; refresh the page before continuing');
    }
    function generation() { return document.body.getAttribute('data-index-generation'); }
    // A first click (or an initial deep link) can happen before the coordinator is started.
    return Promise.resolve().then(function () { return hydrateSessionDetailApis.ready; }).then(function () {
      if (document.querySelector('[data-snapshot-batch-error]')) throw changed();
      var expected = generation();
      var headers = { Accept: 'application/json' };
      var stamped = expected && (expected !== 'legacy' || hydrateSessionDetailApis.documentStamped);
      if (stamped) headers['X-Session-Index-Generation'] = expected;
      return fetch(url, { headers: headers, cache: 'no-store' }).then(function (response) {
        var actual = response.headers.get('X-Session-Index-Generation');
        if (generation() !== expected) throw changed();
        if (response.status === 409) {
          throw changed(stamped && actual && actual !== expected && url.startsWith('/api/sessions/') ? actual : null);
        }
        if (actual && actual !== expected) throw changed();
        // An unheaded HTTP error is not evidence of a new index.
        if (!response.ok) {
          return response.json().catch(function () { return {}; }).then(function (data) {
            throw new Error('HTTP ' + response.status + (data.message ? ': ' + data.message : ''));
          });
        }
        if (stamped && !actual) throw new Error('索引校验信息缺失，请重试；持续失败时刷新页面');
        return response.json();
      }).then(function (data) {
        if (generation() !== expected || document.querySelector('[data-snapshot-batch-error]')) throw changed();
        return data;
      });
    });
  }

  function contentPager(target, section, loaded, total, cursor, load, existing) {
    var pager = existing || document.createElement('div');
    pager.setAttribute('data-content-pagination', section);
    pager.dataset.loaded = String(loaded);
    pager.dataset.total = String(total);
    pager.dataset.hasMore = String(Boolean(cursor));
    pager.replaceChildren();
    var label = document.createElement('span');
    var sectionLabel = { rounds: '轮次', 'round-members': '调用记录', 'round-tools': '当前页工具' }[section] || section;
    label.textContent = sectionLabel + ' · 已显示 ' + loaded + ' / ' + total + ' ';
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
    var start = sessionDetailState.roundsOffset || 0;
    if (!table || (!response.nextCursor && !previous && !start)) return;
    var target = table.parentNode;
    var pager = contentPager(target, 'rounds', loaded, response.total ?? response.roundCount, response.nextCursor, function (cursor) {
      var url = getApiBase().replace(/\/$/, '') + '/rounds?cursor=' + encodeURIComponent(cursor);
      if (sessionDetailState.roundFilter) url += '&trace_status=' + encodeURIComponent(sessionDetailState.roundFilter);
      var ticket = sessionDetailState.filterTicket;
      var epoch = sessionDetailState.roundsEpoch;
      return readSessionContentPage(url).then(function (part) {
        if (ticket !== sessionDetailState.filterTicket || epoch !== sessionDetailState.roundsEpoch || !target.isConnected) return;
        appendSessionRounds(part);
      });
    }, previous);
    if (start) {
      pager.firstElementChild.textContent = '轮次 · 第 ' + (start + 1) + '–' + (start + loaded)
        + ' 条 / ' + (response.total ?? response.roundCount) + ' ';
      var first = document.createElement('button');
      first.type = 'button';
      first.className = 'sd-btn sd-btn--secondary sd-btn--sm';
      first.textContent = '返回首段';
      first.onclick = function () {
        runReadingNavigation(function () { return reloadPagedRoundsFilter('all'); });
      };
      pager.prepend(first);
    }
  }

  function reloadPagedRoundsFilter(status) {
    if (!sessionDetailState.roundsPaged) return;
    var ticket = (sessionDetailState.filterTicket || 0) + 1;
    sessionDetailState.filterTicket = ticket;
    var url = getApiBase().replace(/\/$/, '') + '/rounds?trace_status=' + encodeURIComponent(status);
    return readSessionContentPage(url).then(function (part) {
      if (sessionDetailState.filterTicket !== ticket) return;
      sessionDetailState.roundFilter = status;
      applySessionRounds(part);
      setFilter(document, status);
      var url = new URL(location.href);
      ['round', 'subagent', 'subagentround', 'subagent_round', 'execution'].forEach(function (key) { url.searchParams.delete(key); });
      history.replaceState(history.state, '', url);
    }).catch(function (error) {
      if (sessionDetailState.filterTicket !== ticket) return;
      showSessionResourceError('rounds', error, function () { return reloadPagedRoundsFilter(status); });
    });
  }

  function appendSessionRounds(response) {
    var tbody = qs(document, '.trace-table[data-trace-list] tbody');
    if (!tbody) return;
    (response.rounds || []).forEach(function (round) {
      tbody.appendChild(roundRow(round, sessionDetailState.maxRoundTokens));
      sessionDetailState.rounds.push(round);
    });
    updateRoundsPager(response, sessionDetailState.rounds.length);
    if (sessionDetailState.diagnostics) applySessionDiagnostics(sessionDetailState.diagnostics);
    var active = qs(document, '[data-action^="status-"].is-active');
    if (active) setFilter(document, active.getAttribute('data-action').replace('status-', ''));
    setupTokenTooltips();
    syncToggleAllButton(document);
  }

  function showSessionResourceError(name, err, retry) {
    if (name === 'execution') {
      var judgment = qs(document, '[data-execution-judgment]');
      if (judgment) judgment.hidden = false;
    }
    if (name === 'meta') {
      setText('[data-session-file-text]', '会话文件信息加载失败；请重试');
      var copyFile = qs(document, '[data-session-file-path] [data-action="copy"]');
      if (copyFile) copyFile.hidden = true;
    }
    var selectors = {
      meta: '[data-session-hero] h1, [data-session-meta-chips], [data-session-started], [data-session-updated]',
      metrics: '.sd-kpi__value, .sd-kpi__subgrid',
      diagnostics: '[data-token-composition]'
    };
    if (selectors[name]) qsa(document, selectors[name]).forEach(function (node) { node.textContent = 'Unavailable'; });
    var target = name === 'rounds' ? qs(document, '.trace-table[data-trace-list] tbody')
      : name === 'diagnostics' ? qs(document, '[data-session-diagnostics]')
      : name === 'execution' ? qs(document, '[data-execution-judgment]')
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
      var prompt = meta.firstUserPrompt || '';
      var titlePrefix = String(display.text || '').replace(/…$/, '');
      var restoredTitle = prompt.startsWith(titlePrefix) && prompt.length > titlePrefix.length ? prompt : '';
      title.textContent = restoredTitle || display.text || (meta.filters && meta.filters.sessionId) || 'Untitled session';
      title.removeAttribute('title');
      if (display.html && !restoredTitle) appendRenderedMarkdown(title, display.html);
      var firstQuestion = qs(document, '[data-session-first-question]');
      if (firstQuestion) setMarkup(firstQuestion, meta.firstUserPromptPayloadId
        ? contentPayloadButton(meta.firstUserPromptPayloadId, 'llm_request', '首问 · 本地输入记录', '查看首问', '') : '');
      var original = qs(document, '[data-session-original-title]');
      if (original) {
        original.hidden = !meta.title || meta.title === title.textContent;
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
    if (fileRow && fileText) {
      fileRow.hidden = false;
      fileText.textContent = sessionFilePath || '来源未提供可展示的会话文件路径';
      fileText.title = sessionFilePath;
      var copy = fileRow.querySelector('[data-action="copy"]');
      if (copy) {
        copy.hidden = !sessionFilePath;
        copy.setAttribute('data-copy-text', sessionFilePath);
      }
    }
    var modelBrief = qs(document, '[data-session-model-brief]');
    if (modelBrief && meta.model && String(meta.model).toLowerCase() !== 'unknown') {
      modelBrief.textContent = meta.model;
      modelBrief.title = '会话模型元数据；分 Agent 模型见归因统计';
      modelBrief.hidden = false;
    }
    var chips = qs(document, '[data-session-meta-chips]');
    if (chips) {
      chips.replaceChildren(...[meta.projectName || meta.projectKey, parity.date].filter(Boolean).map(chip));
    }
    setTimestamp('[data-session-started]', meta.createdAt);
    setTimestamp('[data-session-updated]', meta.updatedAt);
  }

  function setTimestamp(selector, source) {
    var host = qs(document, selector);
    if (!host) return;
    var timestamp = source ? new Date(source) : null;
    if (!timestamp || !Number.isFinite(timestamp.getTime())) {
      host.removeAttribute('datetime');
      host.textContent = '未记录';
      return;
    }
    host.dateTime = timestamp.toISOString();
    host.textContent = new Intl.DateTimeFormat('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
    }).format(timestamp);
  }

  function applySessionMetrics(metrics) {
    if (!metrics || !metrics.tokens) return;
    sessionDetailState.metrics = metrics;
    var parity = metrics.parity || {};
    var hasContent = hasSessionContent();
    function observed(value) { return hasContent && typeof value === 'number' ? formatNumber(value) : 'N/A'; }
    setKpi('Total Tokens', TokenProvenance.total(metrics.tokens, formatSessionCompact), [
      measuredTokenSubline('新输入', metrics.tokens, 'fresh'),
      measuredTokenSubline('缓存读取', metrics.tokens, 'cacheRead'),
      measuredTokenSubline('缓存写入', metrics.tokens, 'cacheWrite'),
      measuredTokenSubline('输出', metrics.tokens, 'output')
    ]);
    var inputSide = TokenProvenance.inputTotal(metrics.tokens);
    var measuredInput = inputSide != null;
    setKpi('Cache Health', TokenProvenance.ratio(metrics.tokens, metrics.cacheReadRatio), [
      subline('输入端 Token', measuredInput ? formatSessionCompact(inputSide) : 'N/A'),
      subline('低缓存记录', measuredInput && parity.lowCacheRoundsAvailable === true && typeof parity.lowCacheRounds === 'number' ? formatNumber(parity.lowCacheRounds) : 'N/A'),
      subline('新输入突增记录', observed(parity.freshSpikeRounds))
    ]);
    setKpi('Workload', observed(parity.workloadCalls), [
      subline('主 Agent 记录', observed(parity.mainCalls)),
      subline('子 Agent 记录', observed(parity.subagentCalls)),
      subline('工具调用', observed(parity.toolCalls ?? metrics.toolCalls)),
      subline('子 Agent 运行', observed(parity.subagentRuns ?? metrics.subagents)),
      subline('工具失败', observed(parity.failedToolsAvailable === false ? null : parity.failedTools ?? metrics.failedTools))
    ]);
    setKpi('Source Task Active', detailDuration(metrics.timing, 'activeTaskSeconds'), [
      subline('会话总历时', detailDuration(metrics.timing, 'wallSeconds')),
      subline('Agent 累计耗时', detailDuration(metrics.timing, 'agentTurnSeconds')),
      subline('模型执行', detailDuration(metrics.timing, 'modelExecutionSeconds')),
      subline('工具执行', detailDuration(metrics.timing, 'toolExecutionSeconds'))
    ]);
    document.body.setAttribute('data-session-api-total-tokens', String(metrics.tokens.total || 0));
    document.body.setAttribute('data-session-api-failed-tools', String(metrics.failedTools || 0));
    if (sessionDetailState.diagnostics) applySessionDiagnostics(sessionDetailState.diagnostics);
  }

  function hasSessionContent() {
    return (sessionDetailState.unfilteredRoundCount ?? Number(sessionDetailState.metrics?.roundCount || 0)) > 0;
  }

  function roundEvidenceLabel(round) {
    return 'R' + round.roundIndex;
  }

  function detailDuration(timing, key) {
    var seconds = SessionTiming.seconds(timing, key);
    return durationLabel(seconds) + (seconds != null && timing[key.replace('Seconds', 'Precision')] === 'partial' ? ' · 部分' : '');
  }

  function applySessionDiagnostics(diagnostics) {
    if (!diagnostics) return;
    sessionDetailState.diagnostics = diagnostics;
    sessionDetailState.diagnosticsParity = diagnostics.parity || {};
    renderDiagnosticsCards(sessionDetailState.diagnosticsParity);
  }

  function applySessionRounds(roundsResponse) {
    var tbody = qs(document, '.trace-table[data-trace-list] tbody');
    if (!tbody || !roundsResponse) return;
    var boundaries = qs(document, '[data-trace-boundaries]');
    if (boundaries && roundsResponse.modelCallCount != null) {
      boundaries.textContent = roundsResponse.modelCallCount > 0
        ? '模型调用（已确认）：' + formatNumber(roundsResponse.modelCallCount)
        : '模型调用：未确认';
    }
    sessionDetailState.roundsEpoch = (sessionDetailState.roundsEpoch || 0) + 1;
    var previousPager = document.querySelector('[data-content-pagination="rounds"]');
    if (previousPager) previousPager.remove();
    sessionDetailState.roundsPaged = Boolean(roundsResponse.nextCursor || roundsResponse.total != null);
    var rows = roundsResponse.rounds || [];
    sessionDetailState.roundsOffset = Number(roundsResponse.offset || 0);
    sessionDetailState.roundsLoaded = true;
    sessionDetailState.rounds = rows;
    if ((!sessionDetailState.roundFilter || sessionDetailState.roundFilter === 'all') && !sessionDetailState.roundsOffset) {
      sessionDetailState.unfilteredRoundCount = roundsResponse.roundCount ?? roundsResponse.total ?? rows.length;
      sessionDetailState.analysisRounds = rows;
    }
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
    sessionDetailState.maxRoundTokens = rows.reduce(function (max, round) {
      return Math.max(max, Number(round && round.tokens && round.tokens.total || 0));
    }, 0);
    tbody.replaceChildren.apply(tbody, rows.map(function (round) {
      return roundRow(round, sessionDetailState.maxRoundTokens);
    }));
    updateRoundsPager(roundsResponse, rows.length);
    setupTokenTooltips();
    if (sessionDetailState.diagnosticsParity) renderDiagnosticsCards(sessionDetailState.diagnosticsParity);
    syncToggleAllButton(document);
  }

  function roundRow(round, maxRoundTokens) {
    var tr = document.createElement('tr');
    var tokens = round.tokens || {};
    var parity = round.parity || {};
    var cacheRatio = roundCacheReadRatio(tokens);
    var isLowCache = cacheRatio != null && (Boolean(parity.isLowCache) || cacheRatio < 20);
    var hasIssues = Boolean(parity.hasIssues) || (round.status || '') === 'failed' || Number(round.failedToolCount || 0) > 0;
    var isUserInput = Boolean(parity.isUserInput);
    var visualStatus = hasIssues ? 'failed' : (isUserInput ? 'user' : (round.callCount > 0 ? 'recorded' : 'unknown'));
    var summary = String(parity.summary || '').trim();
    if (summary === 'Round ' + round.roundIndex || summary === '内容未记录') summary = '';
    var summaryRole = { user: '用户', assistant: '助手', tool: '工具' }[parity.summaryRole] || '';
    var label = roundEvidenceLabel(round);
    var counts = [round.callCount > 1 ? formatNumber(round.callCount) + ' 条记录' : '',
      round.toolCallCount > 0 ? formatNumber(round.toolCallCount) + ' 工具' : ''].filter(Boolean).join(' · ');
    var target = '/attribution/' + round.roundIndex + '/1/';
    // Paged round listings do not carry call identity. Keep the round alias when it cannot be proven.
    var owners = Array.isArray(parity.agentUsage) ? parity.agentUsage : [];
    var member = round.callCount === 1 && Array.isArray(round.calls) && round.calls.length === 1 &&
      typeof round.calls[0] === 'string' && round.calls[0].trim() && owners.length === 1
      ? round.calls[0] : '';
    var owner = member && owners[0]?.owner;
    var scopedCall = owner === 'main' || (typeof owner === 'string' && /^subagent(?::.+|_unknown)$/.test(owner))
      ? {callId: member, scope: owner === 'main' ? 'main' : 'subagent'} : null;
    function roundSide(side, kind, name) {
      if (scopedCall) {
        return contentPayloadButton(payloadIdFor(scopedCall, side), payloadKindFor(scopedCall, side),
          label + ' · ' + name, name, memberAttributionPath(round.roundIndex, member, kind));
      }
      return contentPayloadButton('round:' + side + ':' + round.roundIndex, 'llm_' + kind,
        label + ' · ' + name, name, target + kind);
    }
    var actions = round.callCount === 1 ? [
      '<span class="sd-attribution-actions sd-attribution-actions--row" role="group" aria-label="本轮原文">',
      parity.requestAvailable === false ? '<span class="se-missing">输入未记录</span>'
        : roundSide('req', 'request', 'Request'),
      parity.responseAvailable === false ? '<span class="se-missing">输出未记录</span>'
        : roundSide('resp', 'response', 'Response'),
      '</span>'
    ].join('') : round.callCount > 1 ? '<span class="se-missing">见调用明细</span>'
      : isUserInput && parity.observedInputAvailable
      ? contentPayloadButton('round:req:' + round.roundIndex, 'llm_request', label + ' · 用户输入', 'Input', '')
      : '<span class="muted">未记录调用</span>';
    tr.className = 'round-row sd-trace-round-row' + (isUserInput ? ' sd-user-round' : '') + (hasIssues ? ' sd-failed-round' : '');
    tr.setAttribute('data-trace-round-row', '');
    tr.setAttribute('data-round', String(round.roundIndex));
    tr.setAttribute('data-round-label', label);
    tr.dataset.roundCallCount = String(round.callCount || 0);
    tr.setAttribute('data-status', visualStatus);
    tr.setAttribute('data-round-status', round.status || '');
    tr.setAttribute('data-has-issues', hasIssues ? 'true' : 'false');
    tr.setAttribute('data-is-user-input', isUserInput ? 'true' : 'false');
    tr.setAttribute('data-observed-input-available', parity.observedInputAvailable ? 'true' : 'false');
    tr.setAttribute('data-is-low-cache', isLowCache ? 'true' : 'false');
    tr.setAttribute('data-is-fresh-spike', parity.isFreshSpike ? 'true' : 'false');
    tr.setAttribute('data-detail-loaded', 'false');
    tr.id = 'round-' + round.roundIndex;
    setMarkup(tr, [
      '<td class="round-col" title="', parity.confirmedCallCount > 0 || parity.modelCallEvidence ? '模型调用已确认' : '模型调用未确认', '"><button type="button" class="sd-round-toggle round-id', hasIssues ? ' failed' : '', '" data-action="toggle-round" aria-controls="round-', round.roundIndex, '-detail" aria-expanded="false" aria-label="Toggle round ', round.roundIndex, '">',
      '<span class="round-chevron" aria-hidden="true">›</span>', label, '</button></td>',
      '<td class="summary-col"><div class="summary-content"><span class="summary-line">', summaryRole ? '<span class="summary-role' + (parity.summaryRole === 'tool' ? ' summary-role--tool' : '') + '">' + summaryRole + '</span>' : '',
      '<span class="summary-title', summary ? '' : ' summary-title--missing', '"', summary ? ' title="' + escapeHtml(summary) + '"' : '',
      '>', escapeHtml(summary || '摘要未记录'), '</span></span>', statusBadges(round, hasIssues), '</div></td>',
      '<td class="metrics-col mono"><div class="metric-cell">', tokenbarHtml(tokens, maxRoundTokens),
      counts ? '<span class="metric-calls-tools" title="' + counts + '">' + counts + '</span>' : '', '</div></td>',
      '<td class="attribution-col">', actions, '</td>',
      '<td class="time-col">', timeEvidence(localTime(parity.taskStartedAt) || parity.time, '时间', 'sd-time-point round-time'), '</td>',
      '<td class="duration-col">', timeEvidence(durationFromMillis(parity.taskDurationMs), '耗时', 'sd-time-duration round-time'), '</td>'
    ].join(''));
    return tr;
  }

  function renderDiagnosticsCards(parity) {
    var root = qs(document, '[data-session-diagnostics]');
    if (!root || !parity) return;
    var composition = qs(document, '[data-token-composition]');
    if (composition) setMarkup(composition, parity.contextSegmentsAvailable === false
      ? diagnosticUnavailable('当前来源未提供可验证的 Token 构成') : contextBudgetHtml(parity.contextSegments || []));
    if (!hasSessionContent()) {
      setMarkup(root, '<article class="sd-diagnostic-card sd-diagnostic-card--wide"><header class="sd-diagnostic-card__head"><h2>内容证据不可用</h2><span>未知</span></header><div class="sd-diagnostic-card__body"><div class="sd-card-empty">无可用轮次内容。Agent、工具及失败次数均为 N/A，不代表实测为零。</div></div></article>');
      return;
    }
    var agents = parity.agents || [];
    var identifiedAgents = agents.filter(function (agent) { return agent.scope !== 'subagent_unknown'; }).length;
    var agentCountLabel = formatNumber(identifiedAgents) + ' 个 Agent' + (identifiedAgents < agents.length ? ' · 另有未识别子 Agent' : '');
    var html = '<article class="sd-diagnostic-card sd-diagnostic-card--wide sd-diagnostic-card--subagents sd-diagnostic-card--agents">'
      + '<header class="sd-diagnostic-card__head"><h2>Agent 用量明细</h2><span>' + agentCountLabel + '</span></header>'
      + '<div class="sd-diagnostic-card__body">' + agentsTableHtml(agents) + '</div></article>';
    setMarkup(root, html);
    var selected = sessionDetailState.selectedAgent;
    if (selected) {
      var button = qsa(root, '[data-action="select-subagent"]').find(function (item) {
        return item.dataset.agentScope === selected.scope && item.dataset.subagent === selected.id;
      });
      if (button) selectSubagent(button);
    }
    qsa(root, '[data-agent-token-summary]').forEach(function (host) {
      host.append(TokenProvenance.breakdown(JSON.parse(host.dataset.agentTokenSummary), { title: '全会话 Token 构成' }));
    });
    setupTokenRoundTooltips();
  }

  function diagnosticUnavailable(message) {
    return '<div class="sd-card-empty" data-evidence-state="unavailable">' + escapeHtml(message) + '</div>';
  }

  function agentsTableHtml(agents) {
    if (!agents.length) return '<div class="sd-card-empty">未记录 Agent 运行</div>';
    var rows = agents.map(function (row, idx) {
      var active = idx === 0 ? ' is-active' : '';
      var scope = row.scope || (idx === 0 ? 'main' : 'subagent');
      var subagentId = row.subagentId || '';
      var instanceClass = scope === 'main' ? 'sd-subagent-instance--main' : ('sd-subagent-instance--subagent-' + ((idx - 1) % 5));
      var model = (row.models || []).join('、');
      var usage = agentTokenSegments(row);
      var identity = [row.agent || 'Agent', row.shortId, model].filter(Boolean).join(' · ');
      return '<tr class="sd-subagent-row' + active + '" data-subagent-row>'
        + '<td class="sd-subagent-table__agent"><button type="button" class="sd-subagent-select' + active + '" data-action="select-subagent" data-subagent="'
        + escapeHtml(subagentId) + '" data-agent-scope="' + escapeHtml(scope) + '" title="' + escapeHtml(identity) + '" aria-pressed="' + (idx === 0 ? 'true' : 'false') + '"><span class="sd-subagent-select__main"><b>'
        + escapeHtml(row.agent || 'Agent') + '</b><span class="sd-subagent-instance ' + instanceClass + '">'
        + escapeHtml(row.shortId || '') + '</span></span>'
        + (model ? '<small class="sd-subagent-select__model">' + escapeHtml(model) + '</small>' : '') + '</button></td>'
        + '<td>' + agentCallCounts(row) + '</td>'
        + '<td>' + (usage ? '<span tabindex="0" data-token-breakdown="' + escapeHtml(JSON.stringify({ tokens: usage })) + '">' : '')
        + escapeHtml(diagnosticAgentTokens(row)) + (usage ? '</span>' : '') + '</td>'
        + '<td>' + agentToolCounts(row) + '</td>'
        + '</tr>';
    }).join('');
    var panels = agents.map(function (row, idx) {
      return agentTimelinePanelHtml(row, idx);
    }).join('');
    return '<div class="sd-subagent-workbench" data-subagent-workbench><div class="sd-subagent-table-scroll" aria-label="Agent candidates"><table class="sd-subagent-table">'
      + '<thead><tr><th>Agent</th><th>模型调用</th><th>Token</th><th>工具调用</th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table></div><div class="sd-subagent-timeline-area">' + panels + '</div></div>';
  }

  function agentCount(value) {
    return Number.isFinite(value) ? formatNumber(value) : 'N/A';
  }

  function agentCallCounts(agent) {
    var calls = agent.confirmedModelCalls;
    if (!Number.isFinite(calls) || (calls === 0 && agent.localRecords !== 0)) {
      return '<span class="sd-agent-count">未确认</span>';
    }
    return '<b title="仅统计已确认的模型调用">' + agentCount(calls) + ' 次</b>';
  }

  function agentToolCounts(agent) {
    return '<span class="sd-agent-count">' + (Number.isFinite(agent.tools) ? agentCount(agent.tools) + ' 次' : '未记录') + '</span><b class="sd-rate' + (agent.failures > 0 ? ' sd-rate--warn' : '')
      + '" title="' + (agent.failures === 0 ? '未观察到工具失败' : Number.isFinite(agent.failures) ? '已记录工具失败' : '未记录工具失败数量')
      + '">失败 ' + (Number.isFinite(agent.failures) ? agentCount(agent.failures) + ' 次' : '未记录') + '</b>';
  }

  function agentSourceHtml(agent) {
    var fields = [['Session ID', agent.sessionId], ['Session file', agent.sessionFile]].filter(function (field) { return field[1]; });
    if (!fields.length) return '';
    return '<details class="se-evidence sd-agent-source"><summary>来源 ID 与文件</summary><div class="se-evidence__body">'
      + fields.map(function (field) {
        return '<p>' + field[0] + ' <code>' + escapeHtml(field[1]) + '</code>'
          + '<button type="button" class="sd-subagent-copy-btn" data-action="copy" data-copy-text="'
          + escapeHtml(field[1]) + '" aria-label="Copy ' + field[0] + '">Copy</button></p>';
      }).join('') + '</div></details>';
  }

  function agentTimelinePanelHtml(agent, idx) {
    var scope = agent.scope || (idx === 0 ? 'main' : 'subagent');
    var subagentId = agent.subagentId || '';
    var active = idx === 0;
    var owner = scope === 'main' || scope === 'subagent_unknown' ? scope : subagentId ? 'subagent:' + subagentId : '';
    var scoped = (sessionDetailState.analysisRounds || []).flatMap(function (round) {
      var usage = (round.parity?.agentUsage || []).find(function (part) { return part.owner === owner; });
      if (!usage) return [];
      var ratio = roundCacheReadRatio(usage.tokens);
      return [Object.assign({}, round, { tokens: usage.tokens, status: usage.failed ? 'failed' : 'ok',
        parity: Object.assign({}, round.parity, { hasIssues: usage.failed,
          isLowCache: ratio != null && ratio < 20,
          isFreshSpike: false }) })];
    });
    var usage = agentTokenSegments(agent);
    return '<section class="sd-subagent-timeline' + (active ? ' is-active' : '') + '" data-subagent-timeline-panel data-subagent="'
      + escapeHtml(subagentId) + '" data-agent-scope="' + escapeHtml(scope) + '"' + (active ? '' : ' hidden') + '>'
      + '<div class="sd-subagent-timeline__head"><b>' + escapeHtml(agent.agent || 'Agent') + (scoped.length ? ' · Token 走势' : ' · 全会话统计') + '</b>'
      + agentSourceHtml(agent) + '</div>'
      + (scoped.length ? tokenRoundChartHtml(scoped, agent.agent || 'Agent')
        : '<p>' + agentCallCounts(agent) + '；工具：' + agentToolCounts(agent) + '</p>'
          + (usage ? '<div data-agent-token-summary="' + escapeHtml(JSON.stringify(usage)) + '"></div>'
            : diagnosticUnavailable('全会话 Token：N/A（该 Agent 无可归属的分段用量）'))) + '</section>';
  }

  function agentTokenSegments(agent) {
    return agent.tokenSegments || (typeof agent.tokens === 'object' ? agent.tokens : null);
  }

  function diagnosticAgentTokens(agent) {
    var usage = agentTokenSegments(agent);
    return usage ? TokenProvenance.total(usage, formatSessionCompact) : 'N/A';
  }

  function roundCacheReadRatio(tokens) {
    var inputSide = TokenProvenance.inputTotal(tokens);
    return inputSide > 0 ? tokens.cacheRead / inputSide * 100 : null;
  }

  function tokenRoundChartHtml(rounds, label) {
    if (!rounds || !rounds.length) {
      return '<div class="sd-card-empty">' + (sessionDetailState.roundsLoaded
        ? '没有可用的归一化轮次，来源日志可能缺失。'
        : '正在加载轮次时间线。') + '</div>';
    }
    var maxTotal = rounds.reduce(function (max, round) { return Math.max(max, Number(round.tokens?.total || 0)); }, 1);
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
      var fresh = TokenProvenance.share(tokens, 'fresh') || 0;
      var read = TokenProvenance.share(tokens, 'cacheRead') || 0;
      var write = TokenProvenance.share(tokens, 'cacheWrite') || 0;
      var out = TokenProvenance.share(tokens, 'output') || 0;
      var parity = round.parity || {};
      var roundLabel = roundEvidenceLabel(round);
      var tags = [];
      if (round.status === 'failed' || parity.hasIssues) tags.push('issue');
      if (roundCacheReadRatio(tokens) != null && parity.isLowCache) tags.push('low cache');
      if (parity.isFreshSpike) tags.push('fresh spike');
      return '<button type="button" class="sd-token-round" data-action="jump-round" data-round="' + escapeHtml(round.roundIndex) + '" aria-label="' + escapeHtml(roundLabel) + ' token timeline" data-token-breakdown="' + escapeHtml(JSON.stringify({ tokens: tokens, title: roundLabel + ' · ' + (parity.time || '未记录'), ratio: true, navigate: true, scale: tags.length ? '诊断信号：' + tags.join(', ') : '' })) + '">'
        + '<span class="sd-token-round__bar" aria-label="' + escapeHtml(roundLabel) + '" style="--bar-height-px:' + height.toFixed(1) + 'px">'
        + '<span class="sd-token-round__seg sd-token-round__seg--fresh" style="--seg-height:' + fresh + '%"></span>'
        + '<span class="sd-token-round__seg sd-token-round__seg--read" style="--seg-height:' + read + '%"></span>'
        + '<span class="sd-token-round__seg sd-token-round__seg--write" style="--seg-height:' + write + '%"></span>'
        + '<span class="sd-token-round__seg sd-token-round__seg--out" style="--seg-height:' + out + '%"></span></span>'
        + '<span class="sd-token-round__signal-slot" aria-hidden="true">' + (tags.length ? '<span class="sd-token-round__spike"></span>' : '') + '</span>'
        + '<span class="sd-token-round__label">' + escapeHtml(roundLabel) + '</span></button>';
    }).join('');
    return '<div><small><i class="sd-tooltip-mark sd-tooltip-mark--line" aria-hidden="true"></i> 柱：Token 总量　线：输入缓存命中率</small></div>'
      + '<div class="sd-token-round-chart" aria-label="' + escapeHtml(label || 'agent') + ' token composition">'
      + '<div class="sd-token-round-plot" style="--plot-width:' + plotWidth + 'px; --ratio-line-left:22px; --ratio-line-width:' + Math.max(0, plotWidth - 44) + 'px">'
      + '<svg class="sd-token-ratio-line" viewBox="0 0 ' + Math.max(1, plotWidth - 44) + ' 100" preserveAspectRatio="none" aria-label="Agent cache read ratio line">'
      + pointGroups.map(function (points) { return '<polyline points="' + escapeHtml(points) + '"></polyline>'; }).join('') + '</svg>' + buttons + '</div></div>';
  }

  function contextBudgetHtml(segments) {
    var labels = { 'Provider Cached Input': '缓存输入', 'Fresh Input': '新输入', 'Cache Write': '缓存写入', Output: '输出' };
    var colors = { 'Provider Cached Input': 2, 'Fresh Input': 3, 'Cache Write': 4, Output: 5 };
    var measured = segments.flatMap(function (segment) {
      var partial = segment.precision === 'estimated' || segment.precision === 'mixed' || segment.shareStatus === 'partial';
      if (segment.includedInUsage !== true || !labels[segment.label]
        || !['provider_reported', 'estimated', 'mixed'].includes(segment.precision)
        || !['available', 'partial'].includes(segment.shareStatus)
        || !Number.isFinite(segment.tokens) || segment.tokens < 0
        || !Number.isFinite(segment.shareValue) || segment.shareValue <= 0 || segment.shareValue > 100) return [];
      return [{
        color: colors[segment.label],
        label: labels[segment.label],
        amount: (segment.precision === 'provider_reported' ? '' : '≈') + formatSessionCompact(segment.tokens),
        share: (partial ? '≈' : '') + TokenProvenance.percent(segment.shareValue),
        width: segment.shareValue
      }];
    });
    if (!measured.length) return diagnosticUnavailable('当前来源未提供可验证的 Token 构成');
    var bars = measured.map(function (segment) {
      return '<span title="' + escapeHtml(segment.label + ' · ' + segment.amount + ' · ' + segment.share)
        + '" class="sd-context-segment sd-context-segment--' + segment.color
        + '" style="--seg-width:' + segment.width + '%"></span>';
    }).join('');
    var legend = measured.map(function (segment) {
      return '<div class="sd-context-budget__item"><i class="sd-context-budget__dot sd-context-budget__dot--'
        + segment.color + '" aria-hidden="true"></i><span>' + escapeHtml(segment.label) + '</span><b>'
        + escapeHtml(segment.amount + ' · ' + segment.share) + '</b></div>';
    }).join('');
    return '<div class="sd-context-segmented" aria-hidden="true">' + bars + '</div>'
      + '<div class="sd-context-budget" aria-label="Token 构成用量">' + legend + '</div>';
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

  function measuredTokenSubline(label, tokens, key) {
    var value = TokenProvenance.value(tokens, key, formatSessionCompact);
    var ratio = TokenProvenance.state(tokens) === 'provider_reported' ? TokenProvenance.share(tokens, key) : null;
    var share = ratio == null ? '' : TokenProvenance.percent(ratio);
    // 保留已有分类配色；配色不把无法验证的占比写成 0.0%。
    var amount = tokens[key];
    var toneRatio = value !== 'N/A' && Number.isFinite(amount) && Number.isFinite(tokens.total)
      && tokens.total > 0 ? amount / tokens.total * 100 : null;
    return {
      label: label,
      value: share ? value + ' · ' + share : value,
      valueClass: 'sd-kpi-token-share sd-kpi-token-share--' + tokenShareTone(toneRatio),
      title: share ? label + ' share: ' + share : TokenProvenance.note(tokens)
    };
  }

  function tokenShareTone(ratio) {
    if (ratio >= 50) return 'major';
    if (ratio >= 20) return 'mid';
    return 'minor';
  }

  function tokenbarHtml(tokens, maxRoundTokens) {
    var total = Number(tokens && tokens.total || 0);
    var fresh = TokenProvenance.share(tokens, 'fresh') || 0;
    var read = TokenProvenance.share(tokens, 'cacheRead') || 0;
    var write = TokenProvenance.share(tokens, 'cacheWrite') || 0;
    var out = TokenProvenance.share(tokens, 'output') || 0;
    var scale = maxRoundTokens > 0 ? Math.max(2, Math.min(100, Math.round((total / maxRoundTokens) * 1000) / 10)) : 100;
    var scaleLabel = '条宽为最大 Round 的 ' + TokenProvenance.percent(scale) + '；各分段占比仍以本轮总量为分母';
    return '<div class="token-group"><span class="metric-token">' + escapeHtml(TokenProvenance.total(tokens, formatSessionCompact)) + '</span>'
      + '<span class="tokenbar-wrap" tabindex="0" data-token-breakdown="' + escapeHtml(JSON.stringify({ tokens: tokens, scale: scaleLabel })) + '" aria-label="' + escapeHtml(scaleLabel) + '" style="--token-total-width:' + scale + '%;">'
      + '<span class="tokenbar"><span class="tokenbar-seg fresh" style="--segment-width:' + fresh + '%"></span>'
      + '<span class="tokenbar-seg read" style="--segment-width:' + read + '%"></span>'
      + '<span class="tokenbar-seg write" style="--segment-width:' + write + '%"></span>'
      + '<span class="tokenbar-seg out" style="--segment-width:' + out + '%"></span></span>'
      + '</span></div>';
  }

  function statusBadges(round, hasIssues) {
    var html = '';
    var signals = (round.signals || []).slice();
    var failedTools = Number(round.failedToolCount || 0);
    if (failedTools && !signals.includes('Failed')) signals.unshift('Failed');
    if (hasIssues && !failedTools && !signals.length) signals.push('异常');
    if (!signals.length) return '';
    var labels = signals.map(function (signal) {
      return signal === 'Failed' ? (failedTools ? formatNumber(failedTools) + ' 次工具失败' : (round.status === 'failed' ? '失败' : '异常')) : signal;
    });
    var tone = signals[0] === 'Failed' ? ' sd-signal-badge--failed' : (signals[0] === 'Subagent' ? ' sd-signal-badge--subagent' : '');
    html = '<span class="sd-round-signals"><span class="sd-signal-badge' + tone + '" title="' + escapeHtml(labels[0]) + '">' + escapeHtml(labels[0]) + '</span>';
    if (labels.length > 1) {
      var id = 'round-signals-' + round.roundIndex;
      html += '<button type="button" class="sd-btn sd-more-signals" popovertarget="' + id + '" aria-label="查看全部信号">+' + (labels.length - 1) + '</button>'
        + '<span popover class="sd-signal-list" id="' + id + '">' + labels.map(escapeHtml).join(' · ') + '</span>';
    }
    html += '</span>';
    return html;
  }

  function chip(text) {
    var span = document.createElement('span');
    span.className = 'sd-chip';
    span.textContent = text;
    return span;
  }

  function setText(selector, value) {
    var el = qs(document, selector);
    if (el) el.textContent = value;
  }

  function formatNumber(value) {
    return String(Math.round(Number(value || 0)));
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
    if (n >= 1000000000) return Number((n / 1000000000).toFixed(1)) + 'B';
    if (n >= 1000000) return Number((n / 1000000).toFixed(1)) + 'M';
    if (n >= 1000) return Number((n / 1000).toFixed(1)) + 'K';
    return String(Math.round(n));
  }

  function selectSubagent(button) {
    if (!button) return;
    var workbench = button.closest('[data-subagent-workbench]');
    if (!workbench) return;
    var subagent = button.getAttribute('data-subagent') || "";
    var scope = button.getAttribute('data-agent-scope') || "subagent";
    sessionDetailState.selectedAgent = { scope: scope, id: subagent };
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
    // Sync toggle-all button text on load
    syncToggleAllButton(document);
    // Setup dynamic token tooltip positioning
    setupTokenTooltips();
    setupTokenRoundTooltips();
    hydrateSessionDetailApis();
  });
