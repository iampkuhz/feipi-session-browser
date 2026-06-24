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
    var roundId = round.getAttribute('data-round');
    var detail = qs(round, '[data-trace-detail]') || (roundId ? document.getElementById('round-' + roundId + '-detail') : null);
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

  function syncSubagentToggle(block) {
    if (!block) return;
    var btn = qs(block, '[data-action="toggle-subagent-rounds"]');
    if (!btn) return;
    var steps = qsa(block, '[data-sub-round-steps]');
    var allOpen = steps.length > 0;
    for (var i = 0; i < steps.length; i++) {
      if (steps[i].hidden) {
        allOpen = false;
        break;
      }
    }
    btn.textContent = allOpen ? 'Collapse all' : 'Expand all';
    btn.setAttribute('aria-expanded', allOpen ? 'true' : 'false');
    btn.setAttribute('data-state', allOpen ? 'expanded' : 'collapsed');
  }

  function syncSubRoundToggle(subRound) {
    if (!subRound) return;
    var steps = qs(subRound, '[data-sub-round-steps]');
    var toggle = qs(subRound, '[data-action="toggle-sub-round"]');
    var open = !!(steps && !steps.hidden);
    subRound.classList.toggle('is-open', open);
    subRound.setAttribute('data-sub-round-open', open ? 'true' : 'false');
    if (toggle) {
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      toggle.setAttribute('data-state', open ? 'expanded' : 'collapsed');
    }
  }

  function setSubRoundOpen(subRound, open, skipBlockSync) {
    if (!subRound) return;
    var steps = qs(subRound, '[data-sub-round-steps]');
    if (steps) steps.hidden = !open;
    syncSubRoundToggle(subRound);
    if (!skipBlockSync) syncSubagentToggle(closest(subRound, '[data-subagent-block]'));
  }

  function setSubagentRoundsOpen(block, open) {
    if (!block) return;
    qsa(block, '[data-sub-round-id]').forEach(function (subRound) {
      setSubRoundOpen(subRound, open, true);
    });
    syncSubagentToggle(block);
  }

  function expandSubagentRound(subRound) {
    if (!subRound) return;
    setSubRoundOpen(subRound, true);
  }

  function toggleSubagentRound(toggle) {
    var subRound = closest(toggle, '[data-sub-round-id]');
    if (!subRound) return;
    var steps = qs(subRound, '[data-sub-round-steps]');
    var next = !(steps && !steps.hidden);
    setSubRoundOpen(subRound, next);
  }

  function toggleSubagentRounds(button) {
    var block = closest(button, '[data-subagent-block]');
    if (!block) return;
    var steps = qsa(block, '[data-sub-round-steps]');
    var shouldOpen = false;
    for (var i = 0; i < steps.length; i++) {
      if (steps[i].hidden) {
        shouldOpen = true;
        break;
      }
    }
    setSubagentRoundsOpen(block, shouldOpen);
  }
