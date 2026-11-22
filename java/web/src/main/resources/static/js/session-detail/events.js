  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Event delegation (single listener) ──` */

  document.addEventListener('click', function (event) {
    var locate = closest(event.target, '[data-execution-locate]');
    if (locate) {
      runReadingNavigation(function (current) { return locateExecution(locate.dataset.executionLocate, current); });
      return;
    }
    var actionEl = closest(event.target, '[data-action]');
    var page = closest(actionEl, '[data-trace-page]') || document;

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`── KV value click-to-copy handler (non-blocking, text still selectable) ──`
    var kvValueEl = closest(event.target, '.sd-attribution-topcard .sd-kv > span:last-child');
    if (kvValueEl && kvValueEl.textContent && kvValueEl.textContent !== "—" && kvValueEl.textContent !== "" && navigator.clipboard && navigator.clipboard.writeText) {
      var fullText = kvValueEl.getAttribute('title') || kvValueEl.textContent;
      navigator.clipboard.writeText(fullText).then(function() {
        var orig = kvValueEl.style.color;
        kvValueEl.style.color = '#059669';
        setTimeout(function() { kvValueEl.style.color = orig; }, 600);
      }).catch(function() {});
    }

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Subround summary row click toggles the single subround unless a child action handles it.`
    var subRoundToggleEl = closest(event.target, '[data-sub-round-toggle]');
    if (subRoundToggleEl && !actionEl) {
      event.preventDefault();
      event.stopPropagation();
      toggleSubagentRound(subRoundToggleEl);
      return;
    }

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Handle data-action elements`
    if (actionEl) {
      var action = actionEl.getAttribute('data-action');

      if (action === 'load-content-page') {
        event.preventDefault();
        if (actionEl.loadContentPage) actionEl.loadContentPage();
        return;
      } else if (action === 'toggle-round') {
        event.preventDefault();
        event.stopPropagation();
        toggleRound(actionEl);
        return;
      } else if (action.indexOf('status-') === 0) {
        event.preventDefault();
        event.stopPropagation();
        var status = action.replace('status-', '').toLowerCase();
        setFilter(page, status);
        reloadPagedRoundsFilter(status);
      } else if (action === 'toggle-all') {
        event.preventDefault();
        event.stopPropagation();
        toggleAll(page);
      } else if (action === 'toggle-subagent-rounds') {
        event.preventDefault();
        event.stopPropagation();
        toggleSubagentRounds(actionEl);
      } else if (action === 'toggle-sub-round') {
        event.preventDefault();
        event.stopPropagation();
        toggleSubagentRound(actionEl);
      } else if (action === 'jump-round') {
        event.preventDefault();
        event.stopPropagation();
        runReadingNavigation(function (current) { return jumpRound(page, actionEl.getAttribute('data-round'), {
          current: current,
          subagent: actionEl.getAttribute('data-subagent') || '',
          subagentRound: actionEl.getAttribute('data-subagent-round') || ''
        }); });
      } else if (action === 'select-subagent') {
        event.preventDefault();
        event.stopPropagation();
        if (typeof selectSubagent === 'function') selectSubagent(actionEl);
      } else if (action === 'open-payload') {
        event.preventDefault();
        event.stopPropagation();
        openPayload(actionEl);
      } else if (action === 'open-attribution') {
        event.preventDefault();
        event.stopPropagation();
        if (typeof openAttributionModal === 'function') {
          openAttributionModal(actionEl);
        }
      } else if (action === 'close-payload') {
        event.preventDefault();
        event.stopPropagation();
        closePayload();
      } else if (action === 'copy') {
        event.preventDefault();
        event.stopPropagation();
        var copyText = actionEl.getAttribute('data-copy-text') || '';
        if (copyText && window.arpCopy) {
          window.arpCopy(actionEl, copyText, {
            original: actionEl.textContent || 'Copy',
            feedback: 'Copied!'
          });
        } else if (copyText && navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(copyText);
        }
      } else if (action === 'retry-attribution') {
        event.preventDefault();
        event.stopPropagation();
        var modal = document.getElementById("sd-payload-modal") || document.getElementById("payload-modal");
        if (modal) {
          var url = modal.getAttribute("data-attribution-url");
          if (url) {
            _attributionCache.delete(url);
            var body = qs(modal, "[data-payload-body]") || qs(modal, ".sd-modal-body");
            if (body) retryAttributionFetch(url, body);
          }
        }
      } else if (action === 'retry-round') {
        event.preventDefault();
        event.stopPropagation();
        var retryRoundId = actionEl.getAttribute('data-round');
        if (retryRoundId) {
          var retryRow = qs(document, '[data-trace-round-row][data-round="' + retryRoundId + '"]');
          if (retryRow) {
            retryRow.removeAttribute('data-detail-loaded');
            // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Remove any existing loading/error rows for this round`
            var loadingRows = qsa(document, '[data-loading-for="' + retryRoundId + '"]');
            loadingRows.forEach(function (lr) { if (lr.parentNode) lr.parentNode.removeChild(lr); });
            var detailRow = document.getElementById('round-' + retryRoundId + '-detail');
            if (detailRow && detailRow.parentNode) detailRow.parentNode.removeChild(detailRow);
            lazyLoadRoundDetail(retryRow)?.catch(function () { /* 行内已显示失败与重试。 */ });
          }
        }
      }
      return;
    }

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Row click: toggle round detail when clicking anywhere on the row`
    var roundRow = closest(event.target, '[data-trace-round-row]');
    if (roundRow && !closest(event.target, '[popovertarget], [popover]')) {
      event.preventDefault();
      toggleRoundByRow(roundRow);
    }
  }, true);
