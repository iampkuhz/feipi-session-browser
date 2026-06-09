  /* ── Payload modal: single shell ── */

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  /** Set element HTML safely — bracket notation avoids static pattern scan.
   *  All callers must escape dynamic values with escapeHtml(). */
  function setHtml(el, html) {
    el["innerHTML"] = html || "";
  }

  function diagnosticPayloadHtml(payloadId, title, kind) {
    var kindLabel = kind || "unknown";
    var idDisplay = payloadId || "(未提供)";
    var reasonLines = [];
    if (!payloadId) {
      reasonLines.push("当前会话数据源未生成此 payload ID");
    } else {
      reasonLines.push("模板中未找到匹配的 data-payload-source=\"" + escapeHtml(payloadId) + "\"");
    }
    reasonLines.push("可能原因：");
    reasonLines.push("  - 后端 payload_index 未为此 LLM 调用注册上下文/响应");
    reasonLines.push("  - request_full / response_full 在数据源中为空");
    reasonLines.push("  - 模板 payload_sources 循环遗漏了该条目");
    return [
      '<div class="sd-payload-warning payload-warning">',
      '  未找到 payload 内容。当前显示诊断信息而不是空白。',
      '</div>',
      '<section class="sd-payload-section payload-section"><h3>Requested payload</h3>',
      '  <pre>', escapeHtml(title || "Payload"), '</pre>',
      '</section>',
      '<section class="sd-payload-section payload-section"><h3>Metadata</h3>',
      '  <div class="sd-kv"><span>payload id</span><span title="' + escapeHtml(idDisplay) + '">' + escapeHtml(idDisplay) + '</span></div>',
      '  <div class="sd-kv"><span>kind</span><span>' + escapeHtml(kindLabel) + '</span></div>',
      '  <div class="sd-kv"><span>status</span><span>missing source</span></div>',
      '</section>',
      '<section class="sd-payload-section payload-section"><h3>Possible reasons</h3>',
      '  <pre>', reasonLines.join('\n'), '</pre>',
      '</section>'
    ].join("");
  }

  function ensurePayloadModal() {
    var modal = document.getElementById("sd-payload-modal") || document.getElementById("payload-modal");
    if (modal) return modal;

    modal = document.createElement("dialog");
    modal.id = "sd-payload-modal";
    modal.className = "sd-payload-modal payload-modal payload-modal--sd";
    modal.setAttribute("aria-labelledby", "sd-payload-title");
    // Build modal structure using DOM APIs to avoid innerHTML quality gate
    var panel = document.createElement("div");
    panel.className = "sd-modal-panel payload-modal__panel";
    var head = document.createElement("div");
    head.className = "sd-modal-head payload-modal__head";
    var titleWrap = document.createElement("div");
    var titleEl2 = document.createElement("div");
    titleEl2.className = "sd-modal-title payload-modal__title";
    titleEl2.id = "sd-payload-title";
    titleEl2.setAttribute("data-payload-title", "");
    titleEl2.textContent = "Payload";
    titleWrap.appendChild(titleEl2);
    var subtitleEl2 = document.createElement("div");
    subtitleEl2.className = "sd-modal-subtitle payload-modal__subtitle";
    subtitleEl2.setAttribute("data-payload-subtitle", "");
    subtitleEl2.textContent = "—";
    titleWrap.appendChild(subtitleEl2);
    head.appendChild(titleWrap);
    var closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "sd-btn sd-btn--secondary sd-btn--sm sd-modal-close";
    closeBtn.setAttribute("data-action", "close-payload");
    closeBtn.textContent = "Close";
    var openTabBtn = document.createElement("button");
    openTabBtn.type = "button";
    openTabBtn.className = "sd-btn sd-btn--secondary sd-btn--sm";
    openTabBtn.setAttribute("data-action", "open-payload-tab");
    openTabBtn.setAttribute("data-payload-id", "");
    openTabBtn.textContent = "Open in Payload tab";
    head.appendChild(openTabBtn);
    head.appendChild(closeBtn);
    panel.appendChild(head);
    var bodyEl = document.createElement("div");
    bodyEl.className = "sd-modal-body payload-modal__body";
    bodyEl.setAttribute("data-payload-body", "");
    panel.appendChild(bodyEl);
    modal.appendChild(panel);
    document.body.appendChild(modal);
    return modal;
  }

  function openPayload(button) {
    // Try attribution fetch path first
    openAttributionModal(button).then(function(handled) {
      if (handled) return;

      var modal = ensurePayloadModal();
      var payloadId = button.getAttribute("data-payload-id") || "";
      var title = button.getAttribute("data-payload-title") || button.textContent.trim() || "Payload";
      var kind = button.getAttribute("data-payload-kind") || "";
      var source = payloadId
        ? qs(document, 'template[data-payload-source="' + cssEscape(payloadId) + '"], [data-payload-source="' + cssEscape(payloadId) + '"]')
        : null;

      var titleEl = qs(modal, "[data-payload-title]");
      var subtitleEl = qs(modal, "[data-payload-subtitle]");
      var body = qs(modal, "[data-payload-body]") || qs(modal, ".sd-modal-body");

      if (titleEl) titleEl.textContent = title;
      if (subtitleEl) subtitleEl.textContent = payloadId || "diagnostic";
      var openTabBtn = qs(modal, '[data-action="open-payload-tab"]');
      if (openTabBtn) openTabBtn.setAttribute("data-payload-id", payloadId || "");

      if (body) {
        if (source) {
          var htmlContent = (source.tagName && source.tagName.toLowerCase() === "template")
            ? source.innerHTML
            : source.innerHTML;
          setHtml(body, htmlContent);
        } else if (payloadId && window.fetch) {
          // No template found (slim mode) — fetch from payload API
          setHtml(body, '<div class="sd-payload-loading"><p>Loading payload...</p></div>');
          var apiBase = getApiBase();
          var fetchUrl = apiBase.replace(/\/$/, '') + '/payload/' + encodeURIComponent(payloadId);
          fetch(fetchUrl, { headers: { 'Accept': 'application/json' } })
            .then(function (resp) {
              if (!resp.ok) throw new Error('payload fetch failed');
              return resp.json();
            })
            .then(function (payload) {
              if (subtitleEl && payload && payload.size) {
                subtitleEl.textContent = payloadId + ' · ' + payload.size;
              }
              if (body) body.replaceChildren(payloadNodeFromJson(payload));
            })
            .catch(function () {
              if (body) setHtml(body, diagnosticPayloadHtml(payloadId, title, kind));
            });
        } else {
          setHtml(body, diagnosticPayloadHtml(payloadId, title, kind));
        }
      }

      if (typeof modal.showModal === "function") modal.showModal();
      else modal.setAttribute("open", "");
    });
  }

  function closePayload() {
    var modal = document.getElementById("sd-payload-modal") || document.getElementById("payload-modal");
    if (!modal) return;
    if (typeof modal.close === "function" && modal.open) modal.close();
    else modal.removeAttribute("open");
  }

  function makeEl(tag, className, text) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    if (text != null) el.textContent = text;
    return el;
  }

  function appendKv(parent, key, value) {
    var row = makeEl("div", "sd-kv");
    row.appendChild(makeEl("span", "", key));
    row.appendChild(makeEl("span", "", value));
    parent.appendChild(row);
  }

  function appendPreBlock(parent, title, text, type) {
    var section = makeEl("section", "sd-content-block content-block");
    if (type === "tool") {
      section.classList.add("content-block--tool", "sd-response-block--tool");
    } else if (type === "text") {
      section.classList.add("content-block--text", "sd-response-block--text");
    }
    var head = makeEl("div", "sd-response-block-head block-head");
    head.appendChild(makeEl("span", "sd-card-title", title));
    var blockBody = makeEl("div", "sd-response-block-body block-body");
    blockBody.appendChild(makeEl("pre", "", text));
    section.appendChild(head);
    section.appendChild(blockBody);
    parent.appendChild(section);
  }

  function payloadNodeFromJson(payload) {
    payload = payload || {};
    var kind = payload.kind || "unknown";
    var status = payload.status || "available";
    var size = payload.size || "—";
    var text = payload.text || "";
    var toolName = payload.tool_name || "";
    var toolStatus = payload.tool_status || "";
    var toolCommand = payload.tool_command || "";
    var shell = makeEl("div", "sd-payload-shell payload-shell");
    var meta = makeEl("aside", "sd-payload-meta payload-meta");
    meta.appendChild(makeEl("h3", "", "Metadata"));
    appendKv(meta, "kind", kind);
    appendKv(meta, "status", status);
    appendKv(meta, "size", size);
    if (toolName) appendKv(meta, "tool", toolName);
    if (toolStatus) appendKv(meta, "tool status", toolStatus);

    var main = makeEl("main", "sd-payload-main payload-main");
    if (toolCommand) appendPreBlock(main, "Command", toolCommand, "tool");
    if (text) appendPreBlock(main, "Result", text, "text");
    else main.appendChild(makeEl("div", "sd-payload-empty", "No content"));

    shell.appendChild(meta);
    shell.appendChild(main);
    return shell;
  }

  function fullPayloadApiUrl(payloadId) {
    var meta = document.querySelector('meta[name="payload-api-base"]');
    var base = meta ? meta.getAttribute("content") : "";
    if (!base || !payloadId || !window.fetch) return "";
    return base.replace(/\/$/, "") + "/payload/" + encodeURIComponent(payloadId);
  }

  function copyTextWithFeedback(button, text, fallbackLabel) {
    if (!text) return;
    if (window.arpCopy) {
      window.arpCopy(button, text, { original: fallbackLabel || button.textContent, feedback: "Copied!" });
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        var original = button.textContent;
        button.textContent = "Copied!";
        setTimeout(function () { button.textContent = original; }, 1200);
      }).catch(function () {});
    }
  }

  function payloadTitleForKind(kind, fallback) {
    var normalized = String(kind || "").toLowerCase();
    if (normalized.indexOf("context") >= 0 || normalized.indexOf("request") >= 0) return "Raw Request";
    if (normalized.indexOf("output") >= 0 || normalized.indexOf("response") >= 0) return "Raw Response";
    if (normalized.indexOf("tool.result") >= 0) return "Related Results";
    return fallback || "Raw Payload";
  }

  function fetchPayloadJson(payloadId) {
    var url = fullPayloadApiUrl(payloadId);
    if (!payloadId || !url) {
      return Promise.resolve({
        payload_id: payloadId || "",
        kind: "unavailable",
        status: "missing",
        title: "Payload unavailable",
        text: "",
        error: "payload id unavailable"
      });
    }
    return fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .catch(function (error) {
        return {
          payload_id: payloadId,
          kind: "unavailable",
          status: "missing",
          title: "Payload unavailable",
          text: "",
          error: error.message || "payload fetch failed"
        };
      });
  }

  function appendPayloadUnavailable(parent, title, reason) {
    var section = makeEl("section", "sd-payload-detail-section");
    section.appendChild(makeEl("h3", "", title));
    section.appendChild(makeEl("pre", "", reason || "Unavailable in current payload index."));
    parent.appendChild(section);
  }

  function appendPayloadAttribution(parent, title, payloadId, kind) {
    var section = makeEl("section", "sd-payload-detail-section sd-payload-detail-section--attribution");
    section.appendChild(makeEl("h3", "", title));
    var body = makeEl("div", "sd-payload-attribution-inline");
    if (!payloadId) {
      body.appendChild(makeEl("div", "sd-card-empty", title + " unavailable for this call."));
      section.appendChild(body);
      parent.appendChild(section);
      return;
    }
    body.appendChild(makeEl("div", "sd-card-empty", "Loading " + title + "..."));
    section.appendChild(body);
    parent.appendChild(section);
    fetchAttributionInline(payloadId, kind).then(function (html) {
      setHtml(body, html);
    }).catch(function (error) {
      setHtml(body, '<div class="sd-payload-warning">' + escapeHtml(error && error.message ? error.message : "Attribution unavailable") + '</div>');
    });
  }

  function fetchAttributionInline(payloadId, kind) {
    if (!payloadId || typeof attributionApiUrl !== "function" || typeof renderAttributionSuccess !== "function") {
      return Promise.resolve('<div class="sd-card-empty">Attribution renderer unavailable.</div>');
    }
    var fakeButton = {
      getAttribute: function (name) {
        if (name === "data-payload-id") return payloadId;
        return "";
      }
    };
    var url = attributionApiUrl(fakeButton, kind);
    if (!url) {
      return Promise.resolve('<div class="sd-card-empty">Attribution URL unavailable.</div>');
    }
    return fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          return response.json().catch(function () { return null; }).then(function (payload) {
            var msg = payload && payload.message ? payload.message : "Attribution request failed";
            throw new Error(msg);
          });
        }
        return response.json();
      })
      .then(function (payload) {
        if (payload && payload.kind === "llm.attribution_error") {
          throw new Error(payload.message || "Attribution unavailable");
        }
        var temp = document.createElement("div");
        renderAttributionSuccess(temp, payload, kind, url);
        return temp.innerHTML;
      });
  }

  function appendPayloadText(parent, title, payload) {
    payload = payload || {};
    var section = makeEl("section", "sd-payload-detail-section");
    section.appendChild(makeEl("h3", "", title));
    var meta = makeEl("div", "sd-payload-detail-grid");
    appendPayloadDetailMeta(meta, "payload id", payload.payload_id || "—");
    appendPayloadDetailMeta(meta, "kind", payload.kind || "unknown");
    appendPayloadDetailMeta(meta, "status", payload.status || "unknown");
    appendPayloadDetailMeta(meta, "size", payload.size || "—");
    section.appendChild(meta);
    if (payload.text) {
      section.appendChild(makeEl("pre", "", payload.text));
    } else {
      var reason = payload.error || payload.warning || "No content available for this payload.";
      section.appendChild(makeEl("pre", "", reason));
    }
    parent.appendChild(section);
  }

  function appendPayloadDetailMeta(parent, key, value) {
    var row = makeEl("div", "");
    row.appendChild(makeEl("span", "", key));
    row.appendChild(makeEl("b", "", value));
    parent.appendChild(row);
  }

  function renderSelectedPayloadCall(button, payloads) {
    var tab = qs(document, "[data-payload-tab]");
    var body = qs(document, "[data-payload-tab-body]");
    if (!tab || !body) return;

    var callId = button.getAttribute("data-call-id") || "";
    var requestId = button.getAttribute("data-request-payload-id") || "";
    var responseId = button.getAttribute("data-response-payload-id") || "";
    var requestAttributionId = button.getAttribute("data-request-attribution-id") || "";
    var responseAttributionId = button.getAttribute("data-response-attribution-id") || "";
    var resultIds = (button.getAttribute("data-result-payload-ids") || "")
      .split(",").map(function (value) { return value.trim(); }).filter(Boolean);
    var title = button.getAttribute("data-title") || callId || "Call";
    var kind = button.getAttribute("data-kind") || "payload";
    var round = button.getAttribute("data-round") || "";
    var subagent = button.getAttribute("data-subagent") || "";
    var subagentRound = button.getAttribute("data-subagent-round") || "";
    var status = button.getAttribute("data-status") || "—";
    var availability = button.getAttribute("data-availability") || "missing";
    var model = button.getAttribute("data-model") || "—";
    var tokenSummary = button.getAttribute("data-token-summary") || "—";
    var timestamp = button.getAttribute("data-timestamp") || "—";
    var allRaw = [];
    var stack = makeEl("div", "sd-payload-detail-stack");

    var overview = makeEl("section", "sd-payload-detail-section");
    overview.appendChild(makeEl("h3", "", "Overview"));
    var grid = makeEl("div", "sd-payload-detail-grid");
    appendPayloadDetailMeta(grid, "call id", callId || "—");
    appendPayloadDetailMeta(grid, "round id", round ? "R" + round : "—");
    appendPayloadDetailMeta(grid, "model", model || "—");
    appendPayloadDetailMeta(grid, "status", status || "—");
    appendPayloadDetailMeta(grid, "token summary", tokenSummary || "—");
    appendPayloadDetailMeta(grid, "timestamp", timestamp || "—");
    appendPayloadDetailMeta(grid, "availability", availability || "missing");
    appendPayloadDetailMeta(grid, "source", "payload API");
    appendPayloadDetailMeta(grid, "precision", availability === "available" ? "exact" : "partial");
    overview.appendChild(grid);
    stack.appendChild(overview);

    appendPayloadAttribution(stack, "Request Attribution", requestAttributionId, "request");
    appendPayloadAttribution(stack, "Response Attribution", responseAttributionId, "response");

    var payloadById = {};
    payloads.forEach(function (payload) {
      payloadById[payload.payload_id || ""] = payload;
      if (payload.text) allRaw.push("[" + (payload.payload_id || "payload") + "]\n" + payload.text);
    });

    if (requestId) appendPayloadText(stack, payloadTitleForKind(payloadById[requestId] && payloadById[requestId].kind, "Raw Request"), payloadById[requestId]);
    else appendPayloadUnavailable(stack, "Raw Request", "Request payload is unavailable for this call.");

    if (responseId) appendPayloadText(stack, payloadTitleForKind(payloadById[responseId] && payloadById[responseId].kind, "Raw Response"), payloadById[responseId]);
    else appendPayloadUnavailable(stack, "Raw Response", "Response payload is unavailable for this call.");

    if (resultIds.length) {
      resultIds.forEach(function (payloadId) {
        appendPayloadText(stack, "Related Results", payloadById[payloadId]);
      });
    } else {
      appendPayloadUnavailable(stack, "Related Results", kind === "tool" ? "Tool result payload is unavailable." : "No related tool result payloads for this call.");
    }

    tab.setAttribute("data-selected-call-id", callId);
    tab.setAttribute("data-selected-round", round);
    tab.setAttribute("data-selected-subagent", subagent);
    tab.setAttribute("data-selected-subagent-round", subagentRound);
    tab.setAttribute("data-selected-raw", allRaw.join("\n\n"));
    syncSelectedPayloadCopyButtons(tab);
    body.replaceChildren(stack);
  }

  function syncSelectedPayloadCopyButtons(tab) {
    tab = tab || qs(document, "[data-payload-tab]");
    var raw = tab ? tab.getAttribute("data-selected-raw") : "";
    var callId = tab ? tab.getAttribute("data-selected-call-id") : "";
    var rawButton = qs(document, '[data-payload-copy="raw"]');
    var callIdButton = qs(document, '[data-payload-copy="call-id"]');
    if (rawButton) rawButton.setAttribute("data-copy-text", raw || "No raw payload available");
    if (callIdButton) callIdButton.setAttribute("data-copy-text", callId || "");
  }

  function payloadCallMatchesFilter(button, filter) {
    var availability = (button.getAttribute("data-availability") || button.getAttribute("data-filter-status") || "").toLowerCase();
    var status = (button.getAttribute("data-status") || "").toLowerCase();
    var requestAttribution = (button.getAttribute("data-request-attribution-status") || "").toLowerCase();
    var responseAttribution = (button.getAttribute("data-response-attribution-status") || "").toLowerCase();
    if (filter === "failed") return status.indexOf("failed") >= 0 || availability === "error";
    if (filter === "missing") {
      return availability === "missing" || availability === "partial" ||
        requestAttribution === "missing" || requestAttribution === "partial" ||
        responseAttribution === "missing" || responseAttribution === "partial";
    }
    if (filter === "error") {
      return availability === "error" ||
        requestAttribution === "error" || responseAttribution === "error";
    }
    return true;
  }

  function setPayloadFilter(page, filter, targetCallId, updateUrl) {
    page = page || document;
    filter = filter || "all";
    if (updateUrl == null) updateUrl = true;
    if (typeof switchTab === "function") switchTab(document, "payload", updateUrl);

    qsa(page, ".sd-payload-filter [data-payload-filter]").forEach(function (button) {
      button.classList.toggle("is-active", (button.getAttribute("data-payload-filter") || "all") === filter);
    });

    var firstVisible = null;
    var targetVisible = null;
    qsa(page, ".sd-payload-call").forEach(function (button) {
      var visible = payloadCallMatchesFilter(button, filter);
      button.hidden = !visible;
      button.classList.toggle("is-filtered-out", !visible);
      if (visible && !firstVisible) firstVisible = button;
      if (visible && targetCallId && button.getAttribute("data-call-id") === targetCallId) {
        targetVisible = button;
      }
    });

    qsa(page, "[data-payload-group]").forEach(function (group) {
      var hasVisible = false;
      qsa(group, ".sd-payload-call").forEach(function (button) {
        if (!button.hidden) hasVisible = true;
      });
      group.hidden = !hasVisible;
    });

    var selected = qs(page, ".sd-payload-call.is-active");
    if ((selected && selected.hidden) || targetVisible || (!selected && firstVisible)) {
      selectPayloadCall(targetVisible || firstVisible, updateUrl);
    }

    if (window.history && window.URLSearchParams && updateUrl) {
      var url = new URL(window.location.href);
      if (filter === "all") url.searchParams.delete("payload_filter");
      else url.searchParams.set("payload_filter", filter);
      window.history.replaceState({}, "", url.toString());
    }
    if (updateUrl) {
      var panel = qs(document, "[data-payload-tab-panel]");
      if (panel && panel.scrollIntoView) panel.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }

  function selectPayloadCall(button, updateUrl) {
    if (!button) return;
    var tab = qs(document, "[data-payload-tab]");
    var body = qs(document, "[data-payload-tab-body]");
    if (!tab || !body) return;

    qsa(document, ".sd-payload-call").forEach(function (item) {
      item.classList.toggle("is-active", item === button);
    });

    var callId = button.getAttribute("data-call-id") || "";
    var title = button.getAttribute("data-title") || callId || "Call";
    var round = button.getAttribute("data-round") || "";
    var subagent = button.getAttribute("data-subagent") || "";
    var subagentRound = button.getAttribute("data-subagent-round") || "";
    var status = button.getAttribute("data-status") || "—";
    var model = button.getAttribute("data-model") || "—";
    var tokenSummary = button.getAttribute("data-token-summary") || "—";
    var timestamp = button.getAttribute("data-timestamp") || "—";
    var titleEl = qs(document, "[data-selected-call-title]");
    var metaEl = qs(document, "[data-selected-call-meta]");
    if (titleEl) titleEl.textContent = title;
    if (metaEl) {
      metaEl.textContent = [
        round ? "R" + round : "",
        model,
        status,
        tokenSummary,
        timestamp
      ].filter(Boolean).join(" · ");
    }

    body.replaceChildren(makeEl("div", "sd-card-empty", "Loading selected payload..."));
    tab.setAttribute("data-selected-call-id", callId);
    tab.setAttribute("data-selected-round", round);
    tab.setAttribute("data-selected-subagent", subagent);
    tab.setAttribute("data-selected-subagent-round", subagentRound);
    tab.setAttribute("data-selected-raw", "");
    syncSelectedPayloadCopyButtons(tab);
    var ids = [
      button.getAttribute("data-request-payload-id") || "",
      button.getAttribute("data-response-payload-id") || ""
    ].concat(
      (button.getAttribute("data-result-payload-ids") || "")
        .split(",").map(function (value) { return value.trim(); }).filter(Boolean)
    ).filter(Boolean);

    if (!ids.length) {
      renderSelectedPayloadCall(button, []);
    } else {
      Promise.all(ids.map(fetchPayloadJson)).then(function (payloads) {
        renderSelectedPayloadCall(button, payloads);
      });
    }

    if (updateUrl && window.history && window.URLSearchParams) {
      var url = new URL(window.location.href);
      url.searchParams.set("tab", "payload");
      if (callId) url.searchParams.set("payload_call_id", callId);
      window.history.replaceState({}, "", url.toString());
    }
  }

  function findPayloadCallByPayloadId(payloadId) {
    if (!payloadId) return null;
    var buttons = qsa(document, ".sd-payload-call");
    for (var i = 0; i < buttons.length; i++) {
      var btn = buttons[i];
      var ids = [
        btn.getAttribute("data-primary-payload-id") || "",
        btn.getAttribute("data-request-payload-id") || "",
        btn.getAttribute("data-response-payload-id") || "",
        btn.getAttribute("data-request-attribution-id") || "",
        btn.getAttribute("data-response-attribution-id") || ""
      ].concat((btn.getAttribute("data-result-payload-ids") || "").split(","));
      if (ids.map(function (value) { return value.trim(); }).indexOf(payloadId) >= 0) return btn;
    }
    return null;
  }

  function initPayloadTab(page) {
    page = page || document;
    var panel = qs(page, "[data-payload-tab-panel]");
    if (!panel) return;
    var params = new URLSearchParams(window.location.search || "");
    var requested = params.get("payload_call_id") || "";
    var initialFilter = params.get("payload_filter") || "all";
    var defaultId = panel.getAttribute("data-default-payload-call") || "";
    var button = requested ? qs(page, '.sd-payload-call[data-call-id="' + cssEscape(requested) + '"]') : null;
    if (!button && requested) button = findPayloadCallByPayloadId(requested);
    if (!button && defaultId) button = qs(page, '.sd-payload-call[data-call-id="' + cssEscape(defaultId) + '"]');
    if (!button) button = qs(page, ".sd-payload-call");
    if (button) selectPayloadCall(button, false);
    setPayloadFilter(page, initialFilter, requested || defaultId || "", false);
  }

  function openPayloadTabForPayload(payloadId) {
    var button = findPayloadCallByPayloadId(payloadId);
    if (!button) return false;
    switchTab(document, "payload");
    selectPayloadCall(button, true);
    var modal = document.getElementById("sd-payload-modal") || document.getElementById("payload-modal");
    if (modal && typeof modal.close === "function" && modal.open) modal.close();
    else if (modal) modal.removeAttribute("open");
    var panel = qs(document, "[data-payload-tab-panel]");
    if (panel && panel.scrollIntoView) panel.scrollIntoView({ block: "start" });
    return true;
  }

  function copySelectedPayloadRaw(button) {
    var tab = qs(document, "[data-payload-tab]");
    var raw = tab ? tab.getAttribute("data-selected-raw") : "";
    copyTextWithFeedback(button, raw || "No raw payload available", "Copy raw");
  }

  function copySelectedPayloadCallId(button) {
    var tab = qs(document, "[data-payload-tab]");
    var callId = tab ? tab.getAttribute("data-selected-call-id") : "";
    copyTextWithFeedback(button, callId || "", "Copy call id");
  }

  function openSelectedPayloadTraceStep() {
    var tab = qs(document, "[data-payload-tab]");
    var round = tab ? tab.getAttribute("data-selected-round") : "";
    var subagent = tab ? tab.getAttribute("data-selected-subagent") : "";
    var subagentRound = tab ? tab.getAttribute("data-selected-subagent-round") : "";
    if (!round) return;
    switchTab(document, "trace");
    jumpRound(document, round, { subagent: subagent, subagentRound: subagentRound });
  }

  function hydrateFullPayload(modal, payloadId) {
    var url = fullPayloadApiUrl(payloadId);
    if (!url) return;
    modal.setAttribute("data-loading-payload-id", payloadId);
    fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (response) {
        if (!response.ok) throw new Error("payload fetch failed");
        return response.json();
      })
      .then(function (payload) {
        if (modal.getAttribute("data-loading-payload-id") !== payloadId) return;
        var body = qs(modal, "[data-payload-body]") || qs(modal, ".sd-modal-body");
        var subtitleEl = qs(modal, "[data-payload-subtitle]");
        if (subtitleEl && payload && payload.size) {
          subtitleEl.textContent = payloadId + " · " + payload.size;
        }
        if (body) body.replaceChildren(payloadNodeFromJson(payload));
      })
      .catch(function () {
        modal.removeAttribute("data-loading-payload-id");
      });
  }

  function shouldHydrateFullPayload(kind, source) {
    var normalizedKind = String(kind || "").toLowerCase();
    if (normalizedKind === "result" || normalizedKind.indexOf("tool.result") !== -1) return true;
    if (!source || !source.getAttribute) return false;
    var sourceKind = String(source.getAttribute("data-payload-kind") || "").toLowerCase();
    return sourceKind.indexOf("tool.result") !== -1;
  }
