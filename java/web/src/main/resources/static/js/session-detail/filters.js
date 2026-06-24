  function setFilter(page, status) {
    status = status || 'all';
    qsa(page, '[data-action="status-all"]').forEach(function (b) {
      b.classList.toggle('is-active', status === 'all');
    });
    qsa(page, '[data-action="status-failed"]').forEach(function (b) {
      b.classList.toggle('is-active', status === 'failed');
    });
    qsa(page, '[data-action="status-low-cache"]').forEach(function (b) {
      b.classList.toggle('is-active', status === 'low-cache');
    });

    // Toggle round-row visibility
    qsa(page, '[data-trace-round-row]').forEach(function (round) {
      var rowStatus = (round.getAttribute('data-status') || '').toLowerCase();
      var hasIssues = round.getAttribute('data-has-issues') === 'true';
      var isLowCache = round.getAttribute('data-is-low-cache') === 'true';
      var shouldShow = (
        status === 'all'
        || rowStatus === status
        || (status === 'failed' && hasIssues)
        || (status === 'low-cache' && isLowCache)
      );
      round.classList.toggle('is-filtered-out', !shouldShow);
    });
    if (window.history && window.URLSearchParams) {
      var url = new URL(window.location.href);
      if (status === 'all') url.searchParams.delete('trace_status');
      else url.searchParams.set('trace_status', status);
      window.history.replaceState({}, '', url.toString());
    }
  }

  function collapseAll(page) {
    qsa(page, '[data-trace-round-row]').forEach(function (round) {
      setRoundOpen(round, false);
    });
  }

  function expandAll(page) {
    var rounds = qsa(page, '[data-trace-round-row]');
    var loadCount = 0;
    var maxConcurrent = 5;
    for (var i = 0; i < rounds.length; i++) {
      var round = rounds[i];
      if (!isRoundVisible(round)) continue;
      if (round.getAttribute('data-detail-loaded') === 'true') {
        setRoundOpen(round, true);
      } else {
        // Batch the first few, skip the rest to avoid flooding
        if (loadCount < maxConcurrent) {
          loadCount++;
          lazyLoadRoundDetail(round);
        } else {
          setRoundOpen(round, true);
        }
      }
    }
  }

  function toggleAll(page) {
    var btn = qs(page, '[data-action="toggle-all"]');
    var rounds = qsa(page, '[data-trace-round-row]');
    var anyOpen = false;
    for (var i = 0; i < rounds.length; i++) {
      if (isRoundVisible(rounds[i]) && rounds[i].classList.contains('is-open')) {
        anyOpen = true;
        break;
      }
    }
    if (anyOpen) {
      collapseAll(page);
      if (btn) {
        btn.setAttribute('data-state', 'collapse');
        btn.textContent = 'Expand all';
      }
    } else {
      expandAll(page);
      if (btn) {
        btn.setAttribute('data-state', 'expand');
        btn.textContent = 'Collapse all';
      }
    }
  }

  function clearJumpTarget() {
    qsa(document, '.is-jump-target').forEach(function (el) {
      el.classList.remove('is-jump-target');
    });
  }

  function subagentBlockMatches(block, subagent) {
    if (!block || !subagent) return false;
    if (block.getAttribute('data-subagent-id') === subagent) return true;
    if (/^\d+$/.test(subagent)) {
      var parent = closest(block, '[data-trace-detail]') || document;
      var blocks = qsa(parent, '[data-subagent-block]');
      return blocks[parseInt(subagent, 10) - 1] === block;
    }
    return false;
  }

  function findSubagentTraceTarget(round, options) {
    options = options || {};
    var subagent = options.subagent || "";
    if (!subagent) return round;

    var roundId = round.getAttribute('data-round') || "";
    var detail = document.getElementById('round-' + roundId + '-detail');
    var scope = detail || round.parentNode || document;
    var blocks = qsa(scope, '[data-subagent-block]');
    var block = null;

    for (var i = 0; i < blocks.length; i++) {
      if (subagentBlockMatches(blocks[i], subagent)) {
        block = blocks[i];
        break;
      }
    }
    if (!block) return round;

    var subRound = options.subagentRound || "";
    if (subRound) {
      var subRoundEl = qs(block, '[data-sub-round-id="' + cssEscape(subRound) + '"]');
      if (subRoundEl) {
        if (typeof expandSubagentRound === 'function') expandSubagentRound(subRoundEl);
        return subRoundEl;
      }
    }
    return block;
  }

  function scrollTraceTarget(target, smooth) {
    if (!target) return;
    var runScroll = function () {
      var doc = target.ownerDocument || document;
      var win = doc.defaultView || window;
      var scrollEl = doc.scrollingElement || doc.documentElement;
      var currentTop = win.pageYOffset || scrollEl.scrollTop || 0;
      var targetTop = target.getBoundingClientRect().top + currentTop - 12;
      if (scrollEl && scrollEl.scrollTo) {
        scrollEl.scrollTo({
          top: Math.max(0, targetTop),
          behavior: smooth ? 'smooth' : 'auto'
        });
      } else if (win && win.scrollTo) {
        win.scrollTo(0, Math.max(0, targetTop));
      }
      clearJumpTarget();
      target.classList.add('is-jump-target');
    };
    if (window.requestAnimationFrame) {
      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(runScroll);
      });
    } else {
      setTimeout(runScroll, 0);
    }
  }

  function updateTraceJumpUrl(roundId, options) {
    if (!window.history || !window.URLSearchParams) return;
    options = options || {};
    var url = new URL(window.location.href);
    url.searchParams.set('tab', 'trace');
    url.searchParams.set('round', roundId);
    if (options.subagent) url.searchParams.set('subagent', options.subagent);
    else url.searchParams.delete('subagent');
    if (options.subagentRound) url.searchParams.set('subagentround', options.subagentRound);
    else url.searchParams.delete('subagentround');
    url.searchParams.delete('subagent_round');
    window.history.replaceState({}, '', url.toString());
  }

  function jumpRound(page, roundId, options) {
    options = options || {};
    var round = qs(page, '[data-trace-round-row][data-round="' + cssEscape(roundId) + '"]');
    if (!round) return;
    if (typeof switchTab === 'function') switchTab(page, 'trace', true);
    round.classList.remove('is-filtered-out');
    round.hidden = false;
    updateTraceJumpUrl(roundId, options);

    var finishJump = function () {
      setRoundOpen(round, true);
      scrollTraceTarget(findSubagentTraceTarget(round, options), options.smooth === true);
    };

    var detailEl = document.getElementById('round-' + roundId + '-detail');
    // If detail not loaded and not pre-rendered, trigger lazy load then scroll after load.
    if (round.getAttribute('data-detail-loaded') !== 'true' && !detailEl) {
      var load = lazyLoadRoundDetail(round);
      if (load && typeof load.then === 'function') {
        load.then(finishJump).catch(finishJump);
      } else {
        finishJump();
      }
    } else {
      finishJump();
    }
  }
