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

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closePayload();
  });

  document.addEventListener('DOMContentLoaded', function () {
    // Initialize tab panels: trace visible, others hidden
    var page = document.querySelector('[data-trace-page]') || document;
    switchTab(page, 'trace');
    qsa(document, '[data-trace-round-row]').forEach(function (round) {
      var button = qs(round, '[data-action="toggle-round"]');
      var open = round.classList.contains('is-open') || (button && button.getAttribute('aria-expanded') === 'true');
      setRoundOpen(round, open);
    });
    // Sync toggle-all button text on load
    syncToggleAllButton(document);
    // Setup dynamic token tooltip positioning
    setupTokenTooltips();
  });
