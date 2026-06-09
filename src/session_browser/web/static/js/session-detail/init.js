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

  function positionTokenRoundTooltip(round) {
    var tooltip = qs(round, '.sd-token-round-tooltip');
    var chart = round.closest('.sd-token-round-chart');
    if (!tooltip || !chart) return;

    tooltip.style.setProperty('--token-round-tooltip-y', '0px');
    window.requestAnimationFrame(function () {
      var tooltipRect = tooltip.getBoundingClientRect();
      var chartRect = chart.getBoundingClientRect();
      var minTop = chartRect.top + 8;
      var maxBottom = chartRect.bottom - 8;
      var maxTop = maxBottom - tooltipRect.height;
      var targetTop = Math.min(tooltipRect.top, maxTop);
      targetTop = Math.max(targetTop, minTop);
      tooltip.style.setProperty(
        '--token-round-tooltip-y',
        Math.round(targetTop - tooltipRect.top) + 'px'
      );
    });
  }

  function resetTokenRoundTooltip(round) {
    var tooltip = qs(round, '.sd-token-round-tooltip');
    if (!tooltip) return;
    tooltip.style.removeProperty('--token-round-tooltip-y');
  }

  function setupTokenRoundTooltips() {
    qsa(document, '.sd-token-round').forEach(function (round) {
      round.addEventListener('mouseenter', function () {
        positionTokenRoundTooltip(round);
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

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closePayload();
  });

  document.addEventListener('DOMContentLoaded', function () {
    // Initialize tab panels and Payload selector state.
    var page = document.querySelector('[data-trace-page]') || document;
    if (typeof initPayloadTab === 'function') initPayloadTab(page);
    var params = new URLSearchParams(window.location.search || "");
    var initialTab = (params.get("tab") === "payload" || params.get("payload_call_id")) ? "payload" : "trace";
    switchTab(page, initialTab, false);
    qsa(document, '[data-trace-round-row]').forEach(function (round) {
      var button = qs(round, '[data-action="toggle-round"]');
      var open = round.classList.contains('is-open') || (button && button.getAttribute('aria-expanded') === 'true');
      setRoundOpen(round, open);
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
  });
