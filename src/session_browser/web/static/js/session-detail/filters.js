  function setFilter(page, status) {
    status = status || 'all';
    qsa(page, '[data-action="status-all"]').forEach(function (b) {
      b.classList.toggle('is-active', status === 'all');
    });
    qsa(page, '[data-action="status-failed"]').forEach(function (b) {
      b.classList.toggle('is-active', status === 'failed');
    });

    // Toggle round-row visibility
    qsa(page, '[data-trace-round-row]').forEach(function (round) {
      var rowStatus = (round.getAttribute('data-status') || '').toLowerCase();
      var hasIssues = round.getAttribute('data-has-issues') === 'true';
      var shouldShow = status === 'all' || rowStatus === status || (status === 'failed' && hasIssues);
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

  function jumpRound(page, roundId) {
    var round = qs(page, '[data-trace-round-row][data-round="' + roundId + '"]');
    if (!round) return;
    if (typeof switchTab === 'function') switchTab(page, 'trace', true);
    round.classList.remove('is-filtered-out');
    round.hidden = false;
    if (window.history && window.URLSearchParams) {
      var url = new URL(window.location.href);
      url.searchParams.set('tab', 'trace');
      url.searchParams.set('round', roundId);
      window.history.replaceState({}, '', url.toString());
    }
    var detailEl = document.getElementById('round-' + roundId + '-detail');
    // If detail not loaded and not pre-rendered, trigger lazy load then scroll after load
    if (round.getAttribute('data-detail-loaded') !== 'true' && !detailEl) {
      lazyLoadRoundDetail(round);
      // Scroll after a short delay (detail will be injected by fetch)
      setTimeout(function () {
        round.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }, 500);
    } else {
      setRoundOpen(round, true);
      round.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }
