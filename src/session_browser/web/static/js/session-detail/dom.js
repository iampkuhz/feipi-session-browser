  function isRoundVisible(round) {
    return !round.hidden && !round.classList.contains('is-filtered-out');
  }

  function syncToggleAllButton(page) {
    var btn = qs(page, '[data-action="toggle-all"]');
    if (!btn) return;
    var rounds = qsa(page, '[data-trace-round-row]');
    var anyOpen = false;
    for (var i = 0; i < rounds.length; i++) {
      if (isRoundVisible(rounds[i]) && rounds[i].classList.contains('is-open')) {
        anyOpen = true;
        break;
      }
    }
    if (anyOpen) {
      btn.textContent = 'Collapse all';
      btn.setAttribute('data-state', 'expand');
    } else {
      btn.textContent = 'Expand all';
      btn.setAttribute('data-state', 'collapse');
    }
  }

  function setRoundOpen(round, open) {
    if (!round) return;
    var btn = qs(round, '[data-action="toggle-round"]');
    var detail = qs(round, '[data-trace-detail]');
    round.classList.toggle('is-open', open);
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (detail) detail.hidden = !open;
    var page = closest(round, '[data-trace-page]') || document;
    syncToggleAllButton(page);
  }

  function toggleRound(button) {
    var round = closest(button, '[data-trace-round-row]');
    if (!round) return;
    var next = !round.classList.contains('is-open');
    setRoundOpen(round, next);
  }

  function toggleRoundByRow(row) {
    if (!row) return;
    var isOpen = row.classList.contains('is-open');
    if (isOpen) {
      setRoundOpen(row, false);
      return;
    }
    var roundId = row.getAttribute('data-round');
    var detailEl = roundId ? document.getElementById('round-' + roundId + '-detail') : null;
    // Check if detail is already loaded (via lazy load) or pre-rendered in DOM
    if (row.getAttribute('data-detail-loaded') === 'true' || detailEl) {
      setRoundOpen(row, true);
      return;
    }
    // Lazy load round detail from API
    lazyLoadRoundDetail(row);
  }
