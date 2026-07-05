  /* ── Token tooltip dynamic positioning ── */

  var TOOLTIP_FLIP_THRESHOLD = 180; // px from bottom of viewport to trigger flip

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
      document.body.setAttribute('data-session-api-hydrated', 'true');
      document.body.setAttribute('data-session-round-count', String(parts[3].roundCount || 0));
      document.body.setAttribute('data-session-payload-count', String(parts[4].payloadCount || 0));
      document.body.setAttribute('data-session-anomaly-count', String(parts[2].anomalyCount || 0));
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
  }

  function applySessionMetrics(metrics) {
    if (!metrics || !metrics.tokens) return;
    var tokenKpi = qs(document, '.sd-kpi[aria-label="Total Tokens"] .sd-kpi__value');
    if (tokenKpi) {
      tokenKpi.textContent = formatSessionCompact(metrics.tokens.total);
      tokenKpi.title = 'Loaded from /metrics API';
    }
    document.body.setAttribute('data-session-api-total-tokens', String(metrics.tokens.total || 0));
    document.body.setAttribute('data-session-api-failed-tools', String(metrics.failedTools || 0));
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
