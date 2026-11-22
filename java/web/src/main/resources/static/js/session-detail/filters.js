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

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Toggle round-row visibility`
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
      var roundId = round.getAttribute('data-round');
      var detail = roundId ? document.getElementById('round-' + roundId + '-detail') : null;
      if (detail && !shouldShow) detail.hidden = true;
      else if (detail && round.classList.contains('is-open')) detail.hidden = false;
    });
    if (window.history && window.URLSearchParams) {
      var url = new URL(window.location.href);
      if (status === 'all') url.searchParams.delete('trace_status');
      else url.searchParams.set('trace_status', status);
      window.history.replaceState(window.history.state, '', url);
    }
  }

  var roundExpansionEpoch = 0;

  function collapseAll(page) {
    roundExpansionEpoch++;
    qsa(page, '[data-trace-round-row]').forEach(function (round) {
      setRoundOpen(round, false);
    });
  }

  function expandAll(page) {
    var epoch = ++roundExpansionEpoch;
    var rounds = Array.from(qsa(page, '[data-trace-round-row]')).filter(isRoundVisible);
    var index = 0;
    async function next() {
      while (epoch === roundExpansionEpoch && index < rounds.length) {
        var round = rounds[index++];
        if (!round.isConnected || !isRoundVisible(round)) continue;
        if (round.getAttribute('data-detail-loaded') === 'true') {
          setRoundOpen(round, true);
        } else {
          try { await lazyLoadRoundDetail(round); }
          catch (error) { /* 保留该行的重试入口，继续下一条记录。 */ }
        }
      }
    }
    for (var worker = 0; worker < Math.min(5, rounds.length); worker++) next();
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

  function ensureTraceScrollRoom(target, marginTop) {
    var doc = target.ownerDocument || document;
    var win = doc.defaultView || window;
    var scrollEl = doc.scrollingElement || doc.documentElement;
    if (!scrollEl) return;
    var viewportHeight = win.innerHeight || doc.documentElement.clientHeight || 0;
    if (!viewportHeight) return;

    var currentTop = win.pageYOffset || scrollEl.scrollTop || 0;
    var targetTop = target.getBoundingClientRect().top + currentTop;
    var requiredHeight = targetTop + viewportHeight - marginTop + 16;
    if (requiredHeight <= scrollEl.scrollHeight) return;

    var spacer = qs(doc, '[data-trace-scroll-spacer]');
    if (!spacer) {
      spacer = doc.createElement('div');
      spacer.setAttribute('data-trace-scroll-spacer', 'true');
      spacer.setAttribute('aria-hidden', 'true');
      spacer.className = 'sd-trace-scroll-spacer';
      (qs(doc, '.main') || doc.body).appendChild(spacer);
    }
  }

  function scrollTraceTarget(target, smooth) {
    if (!target) return;
    var head = qs(target.ownerDocument, '.sd-workspace-head');
    var marginTop = 12 + (head ? head.getBoundingClientRect().height : 0);
    ensureTraceScrollRoom(target, marginTop);

    var scrollToTarget = function () {
      var doc = target.ownerDocument || document;
      var win = doc.defaultView || window;
      var scrollEl = doc.scrollingElement || doc.documentElement;
      var currentTop = win.pageYOffset || (scrollEl && scrollEl.scrollTop) || 0;
      var targetTop = target.getBoundingClientRect().top + currentTop - marginTop;
      if (scrollEl && scrollEl.scrollTo) {
        scrollEl.scrollTo({
          top: Math.max(0, targetTop),
          behavior: smooth ? 'smooth' : 'auto'
        });
      } else if (win && win.scrollTo) {
        win.scrollTo(0, Math.max(0, targetTop));
      }
    };

    var runScroll = function () {
      if (target.scrollIntoView) {
        target.scrollIntoView({
          block: 'start',
          inline: 'nearest',
          behavior: smooth ? 'smooth' : 'auto'
        });
      }
      scrollToTarget();
      if (window.requestAnimationFrame) {
        window.requestAnimationFrame(function () {
          scrollToTarget();
          clearJumpTarget();
          target.classList.add('is-jump-target');
        });
      } else {
        clearJumpTarget();
        target.classList.add('is-jump-target');
      }
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
    url.searchParams.delete('tab');
    if (options.execution) url.searchParams.set('execution', options.execution);
    else url.searchParams.delete('execution');
    url.searchParams.set('round', roundId);
    if (options.subagent) url.searchParams.set('subagent', options.subagent);
    else url.searchParams.delete('subagent');
    if (options.subagentRound) url.searchParams.set('subagentround', options.subagentRound);
    else url.searchParams.delete('subagentround');
    url.searchParams.delete('subagent_round');
    window.history.replaceState(window.history.state, '', url);
  }

  var readingNavigationTicket = 0;

  async function runReadingNavigation(navigate) {
    var ticket = ++readingNavigationTicket;
    var prior = qs(document, '[data-reading-navigation-error]');
    if (prior) prior.remove();
    try {
      await navigate(function () { return ticket === readingNavigationTicket; });
    } catch (error) {
      if (ticket !== readingNavigationTicket) return;
      var host = document.getElementById('session-records') || qs(document, '[data-trace-page]');
      if (!host) return;
      var callout = document.createElement('div');
      callout.dataset.readingNavigationError = '';
      callout.setAttribute('role', 'alert');
      callout.textContent = '无法定位执行记录：' + error.message + ' ';
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'sd-btn sd-btn--secondary sd-btn--sm';
      var refresh = /refresh/i.test(error.message);
      button.textContent = refresh ? 'Refresh page' : 'Retry';
      button.onclick = function () {
        if (refresh) window.location.reload();
        else runReadingNavigation(navigate);
      };
      callout.appendChild(button);
      host.prepend(callout);
      scrollTraceTarget(callout, false);
    }
  }

  function roundEvidenceTarget(detail, options) {
    if (!detail || !options.target) return null;
    var key = cssEscape(options.target);
    return qs(detail, options.targetKind === 'tool'
      ? '[data-tool-payload-pair][data-tool-id="' + key + '"]'
      : '[data-execution-call="' + key + '"]');
  }

  async function jumpRound(page, roundId, options) {
    options = options || {};
    if (!/^\d+$/.test(String(roundId)) || Number(roundId) < 1) throw new Error('无效的轮次');
    var current = options.current || function () { return true; };
    var findRow = function () { return qs(page, '[data-trace-round-row][data-round="' + cssEscape(roundId) + '"]'); };
    var round = findRow();
    if (!round || round.classList.contains('is-filtered-out')) {
      var ticket = ++sessionDetailState.filterTicket;
      var response = await readSessionContentPage(getApiBase() + '/rounds?target=' + encodeURIComponent(roundId));
      if (!current() || ticket !== sessionDetailState.filterTicket) return;
      sessionDetailState.roundFilter = '';
      setFilter(page, 'all');
      applySessionRounds(response);
      round = findRow();
    }
    if (!round) throw new Error('当前索引中没有此轮次');
    var getDetail = function () { return document.getElementById('round-' + roundId + '-detail'); };
    var detail = getDetail();
    var target = roundEvidenceTarget(detail, options);
    if (!target && round.pendingRoundDetail) {
      await round.pendingRoundDetail;
      detail = getDetail();
      target = roundEvidenceTarget(detail, options);
    }
    if (!current() || !round.isConnected) return;
    if (!target && (options.target || !detail)) {
      await lazyLoadRoundDetail(round, options, detail);
      detail = getDetail();
      target = roundEvidenceTarget(detail, options);
    }
    if (!current() || !round.isConnected) return;
    if (options.target && !target) throw new Error('当前轮次未找到指定证据');
    setRoundOpen(round, true);
    updateTraceJumpUrl(roundId, options);
    if (target) {
      var subround = target.closest('[data-sub-round-id]');
      if (subround) expandSubagentRound(subround);
      var filter = qs(detail, '[data-tool-kind-filter]');
      if (filter?.value) {
        filter.value = '';
        applyToolKindFilter(detail);
      }
      if (target.matches('[data-tool-payload-pair]')) {
        target.open = true;
        target.querySelector('summary').focus({ preventScroll: true });
      } else {
        target.tabIndex = -1;
        target.focus({ preventScroll: true });
      }
    }
    scrollTraceTarget(target || findSubagentTraceTarget(round, options), options.smooth === true);
  }
