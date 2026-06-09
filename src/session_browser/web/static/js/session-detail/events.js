  /* ── Event delegation (single listener) ── */

  document.addEventListener('click', function (event) {
    var actionEl = closest(event.target, '[data-action]');
    var page = closest(actionEl, '[data-trace-page]') || document;

    // ── Bucket toggle handler ──
    var toggleEl = closest(event.target, '[data-bucket-toggle]');
    if (toggleEl) {
      event.preventDefault();
      event.stopPropagation();
      var card = closest(toggleEl, '.sd-attribution-bucket-card');
      if (card) {
        var body = qs(card, '.sd-attribution-bucket-body');
        if (body) {
          var isExpanded = body.hasAttribute('hidden');
          if (isExpanded) {
            // Check if this bucket needs dynamic loading
            var modal = document.getElementById("sd-payload-modal") || document.getElementById("payload-modal");
            var roundIdx = modal ? modal.getAttribute("data-bucket-detail-round") : "";
            var bucketLabel = card.getAttribute("data-bucket-label") || "";
            var bucketKey = card.getAttribute("data-bucket-key") || "";
            var detailKind = body.getAttribute("data-bucket-detail-kind") || "";

            if (roundIdx && (detailKind === "current_user_message" || bucketKey === "current_user_message")) {
              loadBucketDetailDynamic(modal, body, roundIdx, "current_user_message");
            } else if (roundIdx && (detailKind === "system_sources" && bucketKey === "local_instruction_context")) {
              loadBucketDetailDynamic(modal, body, roundIdx, "local_instruction_context");
            }
          }
          body.hidden = !isExpanded;
          card.classList.toggle('is-expanded', isExpanded);
        }
      }
      return;
    }

    // ── Bucket dynamic content fetch trigger (template-rendered) ──
    var fetchTrigger = closest(event.target, '[data-bucket-dynamic-load]');
    if (fetchTrigger && fetchTrigger.getAttribute("data-loaded") !== "1") {
      event.preventDefault();
      event.stopPropagation();
      var card = closest(fetchTrigger, '.sd-attribution-bucket-card');
      var bucketKey = card ? (card.getAttribute("data-bucket-key") || "") : "";
      // Fallback to bucket label if key not available
      if (!bucketKey) {
        var bucketLabel = card ? (card.getAttribute("data-bucket-label") || "") : "";
        if (bucketLabel.indexOf("当前用户输入") >= 0) bucketKey = "current_user_message";
        else if (bucketLabel.indexOf("本地指令") >= 0) bucketKey = "local_instruction_context";
      }
      var modal = document.getElementById("sd-payload-modal") || document.getElementById("payload-modal");
      var roundIdx = modal ? modal.getAttribute("data-bucket-detail-round") : "";
      var pageSource = modal ? modal.getAttribute("data-bucket-detail-source") : "";

      if (!pageSource) {
        // Fallback: try to extract from page meta
        var metaSource = document.querySelector('meta[name="session-source"]');
        pageSource = metaSource ? metaSource.getAttribute("content") : "";
      }

      if (roundIdx && bucketKey && pageSource) {
        // Show loading on the trigger itself
        fetchTrigger.textContent = '';
        var loadingSpan = document.createElement('span');
        loadingSpan.className = 'sd-bucket-detail-loading';
        loadingSpan.textContent = '加载中…';
        fetchTrigger.appendChild(loadingSpan);
        fetchTrigger.setAttribute("data-loading", "1");

        var apiUrl = "/api/sessions/" + encodeURIComponent(pageSource) + "/" +
          encodeURIComponent(_getPageSourceAndSessionId().sessionId || "") + "/bucket-detail/" + roundIdx + "/" + bucketKey;

        // If sessionId not from modal, try to get from page
        var sid = _getPageSourceAndSessionId().sessionId;
        if (!sid) {
          var metaSid = document.querySelector('meta[name="session-id"]');
          sid = metaSid ? metaSid.getAttribute("content") : "";
        }
        apiUrl = "/api/sessions/" + encodeURIComponent(pageSource) + "/" + encodeURIComponent(sid) + "/bucket-detail/" + roundIdx + "/" + bucketKey;

        fetch(apiUrl, { headers: { "Accept": "application/json" } })
          .then(function (resp) {
            if (!resp.ok) throw new Error("HTTP " + resp.status);
            return resp.json();
          })
          .then(function (data) {
            if (data.kind === "bucket_detail" && data.text) {
              var html = '<pre class="sd-bucket-detail-preview sd-bucket-detail-preview--full">' +
                escapeHtml(data.text) + '</pre>' +
                '<div class="sd-bucket-detail-meta">~' + formatCompactToken(data.tokens) + ' tokens</div>';
              setHtml(fetchTrigger, html);
              fetchTrigger.setAttribute("data-loaded", "1");
              fetchTrigger.removeAttribute("data-bucket-dynamic-load");
            } else if (data.note) {
              setHtml(fetchTrigger, '<div class="sd-bucket-detail-empty">' + escapeHtml(data.note) + '</div>');
            } else {
              setHtml(fetchTrigger, '<div class="sd-bucket-detail-empty">无详细内容</div>');
            }
          })
          .catch(function (err) {
            setHtml(fetchTrigger, '<div class="sd-bucket-detail-empty">加载失败: ' + escapeHtml(err.message) + '</div>');
          });
      }
      return;
    }

    // ── Tool detail toggle handler ──
    var toolToggleEl = closest(event.target, '[data-tool-detail-toggle]');
    if (toolToggleEl) {
      event.preventDefault();
      event.stopPropagation();
      var item = closest(toolToggleEl, '.sd-bucket-detail-item--expandable');
      if (item) {
        var expanded = qs(item, '.sd-bucket-detail-expanded');
        if (expanded) {
          var isOpen = !expanded.hasAttribute('hidden');
          if (isOpen) {
            expanded.hidden = true;
            item.classList.remove('is-expanded');
          } else {
            if (typeof hydrateToolDetailItem === "function") hydrateToolDetailItem(item);
            expanded.hidden = false;
            item.classList.add('is-expanded');
          }
        }
      }
      return;
    }

    // ── KV value click-to-copy handler (non-blocking, text still selectable) ──
    var kvValueEl = closest(event.target, '.sd-attribution-rail__card .sd-kv > span:last-child');
    if (kvValueEl && kvValueEl.textContent && kvValueEl.textContent !== "—" && kvValueEl.textContent !== "" && navigator.clipboard && navigator.clipboard.writeText) {
      var fullText = kvValueEl.getAttribute('title') || kvValueEl.textContent;
      navigator.clipboard.writeText(fullText).then(function() {
        var orig = kvValueEl.style.color;
        kvValueEl.style.color = '#059669';
        setTimeout(function() { kvValueEl.style.color = orig; }, 600);
      }).catch(function() {});
    }

    // Handle data-action elements
    if (actionEl) {
      var action = actionEl.getAttribute('data-action');

      if (action === 'toggle-round') {
        event.preventDefault();
        event.stopPropagation();
        toggleRound(actionEl);
        return;
      } else if (action.indexOf('tab-') === 0) {
        event.preventDefault();
        event.stopPropagation();
        var tabName = actionEl.getAttribute('data-tab');
        if (tabName) switchTab(document, tabName);
        return;
      } else if (action.indexOf('status-') === 0) {
        event.preventDefault();
        event.stopPropagation();
        setFilter(page, action.replace('status-', '').toLowerCase());
      } else if (action === 'toggle-all') {
        event.preventDefault();
        event.stopPropagation();
        toggleAll(page);
      } else if (action === 'jump-round') {
        event.preventDefault();
        event.stopPropagation();
        jumpRound(page, actionEl.getAttribute('data-round'), {
          subagent: actionEl.getAttribute('data-subagent') || '',
          subagentRound: actionEl.getAttribute('data-subagent-round') || ''
        });
      } else if (action === 'open-payload') {
        event.preventDefault();
        event.stopPropagation();
        openPayload(actionEl);
      } else if (action === 'select-payload-call') {
        event.preventDefault();
        event.stopPropagation();
        selectPayloadCall(actionEl, true);
      } else if (action === 'payload-filter') {
        event.preventDefault();
        event.stopPropagation();
        var payloadFilter = actionEl.getAttribute('data-payload-filter') || 'all';
        var payloadCall = actionEl.getAttribute('data-payload-call') || '';
        setPayloadFilter(document, payloadFilter, payloadCall, true);
      } else if (action === 'open-payload-tab') {
        event.preventDefault();
        event.stopPropagation();
        openPayloadTabForPayload(actionEl.getAttribute('data-payload-id') || '');
      } else if (action === 'copy-selected-raw') {
        event.preventDefault();
        event.stopPropagation();
        copySelectedPayloadRaw(actionEl);
      } else if (action === 'open-trace-step') {
        event.preventDefault();
        event.stopPropagation();
        openSelectedPayloadTraceStep();
      } else if (action === 'copy-call-id') {
        event.preventDefault();
        event.stopPropagation();
        copySelectedPayloadCallId(actionEl);
      } else if (action === 'close-payload') {
        event.preventDefault();
        event.stopPropagation();
        closePayload();
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
            // Remove any existing loading/error rows for this round
            var loadingRows = qsa(document, '[data-loading-for="' + retryRoundId + '"]');
            loadingRows.forEach(function (lr) { if (lr.parentNode) lr.parentNode.removeChild(lr); });
            var detailRow = document.getElementById('round-' + retryRoundId + '-detail');
            if (detailRow && detailRow.parentNode) detailRow.parentNode.removeChild(detailRow);
            lazyLoadRoundDetail(retryRow);
          }
        }
      }
      return;
    }

    // Tab click fallback: delegate on [data-tab] even without [data-action].
    // This ensures tab switching works regardless of how tabs are authored.
    var tabEl = closest(event.target, '[data-tab]');
    if (tabEl) {
      var tabName = tabEl.getAttribute('data-tab');
      if (tabName) {
        event.preventDefault();
        event.stopPropagation();
        switchTab(document, tabName);
        return;
      }
    }

    // Row click: toggle round detail when clicking anywhere on the row
    var roundRow = closest(event.target, '[data-trace-round-row]');
    if (roundRow) {
      event.preventDefault();
      toggleRoundByRow(roundRow);
    }
  }, true);
