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
    var title = qs(document, '[data-session-hero] h1');
    if (title && meta.title) {
      title.textContent = meta.title;
      title.title = meta.title;
    }
    document.body.setAttribute('data-session-api-session-key', meta.sessionKey || '');
    document.body.setAttribute('data-session-api-artifact', meta.hasArtifact ? 'available' : 'missing');
    var agent = qs(document, '[data-session-agent]');
    if (agent) agent.textContent = (meta.filters && meta.filters.agent) || agent.textContent || '';
    var idText = qs(document, '[data-session-id-text]');
    if (idText && meta.filters && meta.filters.sessionId) {
      idText.textContent = meta.filters.sessionId;
      idText.title = meta.filters.sessionId;
    }
    var fileRow = qs(document, '[data-session-file-path]');
    var fileText = qs(document, '[data-session-file-text]');
    if (fileRow && fileText && meta.cwd) {
      fileRow.hidden = false;
      fileText.textContent = meta.cwd;
      fileText.title = meta.cwd;
      var copy = fileRow.querySelector('[data-action="copy"]');
      if (copy) copy.setAttribute('data-copy-text', meta.cwd);
    }
    var chips = qs(document, '[data-session-meta-chips]');
    if (chips) {
      chips.replaceChildren(
        chip(meta.model || 'Unknown model', true),
        chip(meta.projectName || meta.projectKey || 'Unknown project'),
        chip(meta.updatedAt ? 'Updated ' + meta.updatedAt : 'Updated —'),
        meta.gitBranch ? chip(meta.gitBranch, true) : chip('Branch —', true)
      );
    }
    setText('[data-session-updated]', meta.updatedAt || '—');
    setText('[data-session-artifact]', meta.hasArtifact ? ('Schema ' + (meta.artifactSchemaVersion || 'available')) : 'No artifact');
  }

  function applySessionMetrics(metrics) {
    if (!metrics || !metrics.tokens) return;
    setKpi('Total Tokens', formatSessionCompact(metrics.tokens.total), [
      'Fresh ' + formatSessionCompact(metrics.tokens.fresh),
      'Cache Read ' + formatSessionCompact(metrics.tokens.cacheRead),
      'Cache Write ' + formatSessionCompact(metrics.tokens.cacheWrite),
      'Output ' + formatSessionCompact(metrics.tokens.output)
    ]);
    var inputSide = Number(metrics.tokens.fresh || 0) + Number(metrics.tokens.cacheRead || 0) + Number(metrics.tokens.cacheWrite || 0);
    var cacheRatio = inputSide > 0 ? ((Number(metrics.tokens.cacheRead || 0) / inputSide) * 100).toFixed(1) + '%' : 'N/A';
    setKpi('Cache Health', cacheRatio, [
      'Input-side Tokens ' + formatSessionCompact(inputSide),
      'Cache ratio source API'
    ]);
    setKpi('Workload', formatSessionCompact(Number(metrics.userMessages || 0) + Number(metrics.assistantMessages || 0)), [
      'User Messages ' + formatNumber(metrics.userMessages),
      'Assistant Messages ' + formatNumber(metrics.assistantMessages),
      'Tool Calls ' + formatNumber(metrics.toolCalls),
      'Subagent Runs ' + formatNumber(metrics.subagents)
    ]);
    var activeSeconds = Number(metrics.modelExecutionSeconds || 0) + Number(metrics.toolExecutionSeconds || 0);
    setKpi('Active Time', formatDuration(activeSeconds), [
      'Duration ' + formatDuration(metrics.durationSeconds),
      'Model Time ' + formatDuration(metrics.modelExecutionSeconds),
      'Tool Time ' + formatDuration(metrics.toolExecutionSeconds)
    ]);
    document.body.setAttribute('data-session-api-total-tokens', String(metrics.tokens.total || 0));
    document.body.setAttribute('data-session-api-failed-tools', String(metrics.failedTools || 0));
  }

  function applySessionDiagnostics(diagnostics) {
    if (!diagnostics) return;
    var count = Number(diagnostics.anomalyCount || 0);
    setKpi('Run Health', count > 0 ? 'Needs Review' : 'OK', [
      'Issue Rounds ' + formatNumber(count),
      'Failed Tools ' + (count > 0 ? 'See diagnostics' : '0'),
      'Payload Gaps loaded from API',
      'Attribution Gaps loaded from API'
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
      (diagnostics.anomalies || []).forEach(function (anomaly) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'sd-issue-link sd-issue-link--' + severityTone(anomaly.severity);
        button.setAttribute('data-action', 'jump-round');
        button.setAttribute('data-round', '1');
        button.textContent = anomaly.type || 'anomaly';
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
    if (countEl) countEl.textContent = formatNumber(count) + ' detected';
    var list = qs(document, '.sd-anomalies__list');
    if (list) {
      var anomalies = diagnostics.anomalies || [];
      if (!anomalies.length) {
        var empty = document.createElement('div');
        empty.className = 'sd-card-empty';
        empty.textContent = diagnostics.state && diagnostics.state.message ? diagnostics.state.message : 'No anomaly was detected for this session.';
        list.replaceChildren(empty);
      } else {
        list.replaceChildren.apply(list, anomalies.map(function (anomaly) {
          var row = document.createElement('div');
          row.className = 'sd-anomaly sd-anomaly--' + severityTone(anomaly.severity);
          setMarkup(row, '<span class="sd-anomaly__type">' + escapeHtml(anomaly.type || '') + '</span>'
            + '<span class="sd-anomaly__severity sd-badge sd-badge--' + severityTone(anomaly.severity) + '">' + escapeHtml(anomaly.severity || '') + '</span>'
            + '<span class="sd-anomaly__reason">' + escapeHtml(anomaly.reason || '') + '</span>');
          return row;
        }));
      }
    }
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
    var inputSide = Number(tokens.fresh || 0) + Number(tokens.cacheRead || 0) + Number(tokens.cacheWrite || 0);
    var isLowCache = inputSide > 0 && (Number(tokens.cacheRead || 0) / inputSide) < 0.2;
    var hasIssues = (round.status || '') === 'failed' || Number(round.failedToolCount || 0) > 0;
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
      '<td><span class="sd-round-summary">', formatNumber(round.callCount), ' calls, ', formatNumber(round.toolCallCount), ' tools</span></td>',
      '<td class="metrics-col mono"><span class="sd-round-metrics">', formatNumber(round.callCount), ' LLM</span>', tokenbarHtml(tokens), '</td>',
      '<td class="attribution-col"><span class="sd-round-attribution">lazy</span></td>',
      '<td class="status-col">', statusBadges(round, hasIssues, isLowCache), '</td>',
      '<td class="time-col"><span class="sd-round-time">API</span></td>'
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
        var idx = String(line).lastIndexOf(' ');
        if (idx > 0) {
          span.appendChild(document.createTextNode(line.slice(0, idx) + ' '));
          var b = document.createElement('b');
          b.textContent = line.slice(idx + 1);
          span.appendChild(b);
        } else {
          span.textContent = line;
        }
        return span;
      }));
    }
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
    var html = hasIssues
      ? '<span class="sd-signal-badge sd-signal-badge--failed">failed</span>'
      : '<span class="sd-signal-badge sd-signal-badge--ok">ok</span>';
    if (isLowCache) html += '<span class="sd-signal-badge sd-signal-badge--low-cache">low-cache</span>';
    (round.signals || []).forEach(function (signal) {
      if (signal !== 'Failed') html += '<span class="sd-signal-badge">' + escapeHtml(signal) + '</span>';
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
    var parsed = new DOMParser().parseFromString(markup || '', 'text/html');
    target.replaceChildren.apply(target, Array.prototype.slice.call(parsed.body.childNodes));
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
