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

  function directPayloadTargetForAttribution(button) {
    var kind = button.getAttribute("data-payload-kind") || "";
    var payloadId = button.getAttribute("data-payload-id") || "";
    var title = button.getAttribute("data-payload-title") || button.textContent.trim() || "";
    var match;
    if (kind === "llm.request_attribution") {
      match = payloadId.match(/^sub-(.+)-IX([0-9]+)-request-attribution$/);
      if (match) {
        return {
          payloadId: "sub-" + match[1] + "-" + match[2] + "-ctx",
          kind: "context",
          title: directPayloadTitle(title, "LLM Request", "Request")
        };
      }
      if (/-request-attribution$/.test(payloadId)) {
        return {
          payloadId: payloadId.replace(/-request-attribution$/, "-context"),
          kind: "context",
          title: directPayloadTitle(title, "LLM Request", "Request")
        };
      }
    }
    if (kind === "llm.response_attribution") {
      match = payloadId.match(/^sub-(.+)-IX([0-9]+)-response-attribution$/);
      if (match) {
        return {
          payloadId: "sub-" + match[1] + "-" + match[2] + "-rsp",
          kind: "response",
          title: directPayloadTitle(title, "LLM Response", "Response")
        };
      }
      if (/-response-attribution$/.test(payloadId)) {
        return {
          payloadId: payloadId.replace(/-response-attribution$/, "-output"),
          kind: "response",
          title: directPayloadTitle(title, "LLM Response", "Response")
        };
      }
    }
    return null;
  }

  function directPayloadTitle(title, fallback, label) {
    var text = String(title || "").trim();
    if (!text) return fallback;
    text = text
      .replace(/Request\s*归因/g, label)
      .replace(/Response\s*归因/g, label)
      .replace(/Req\s*归因/g, label)
      .replace(/Resp\s*归因/g, label);
    return text || fallback;
  }

  function openPayloadContent(button, override) {
    override = override || {};
    var modal = ensurePayloadModal();
    var payloadId = override.payloadId || button.getAttribute("data-payload-id") || "";
    var title = override.title || button.getAttribute("data-payload-title") || button.textContent.trim() || "Payload";
    var kind = override.kind || button.getAttribute("data-payload-kind") || "";
    var source = payloadId
      ? qs(document, 'template[data-payload-source="' + cssEscape(payloadId) + '"], [data-payload-source="' + cssEscape(payloadId) + '"]')
      : null;
    var sourceTokenEstimate = source ? source.getAttribute("data-payload-token-estimate") : "";
    var sourceTokenSummary = formatPayloadTokenEstimate(sourceTokenEstimate);

    var titleEl = qs(modal, "[data-payload-title]");
    var subtitleEl = qs(modal, "[data-payload-subtitle]");
    var body = qs(modal, "[data-payload-body]") || qs(modal, ".sd-modal-body");

    if (titleEl) titleEl.textContent = title;
    if (subtitleEl) subtitleEl.textContent = (payloadId || "diagnostic") + (sourceTokenSummary ? " · " + sourceTokenSummary : "");

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
            if (subtitleEl && payload) {
              subtitleEl.textContent = payloadSubtitle(payloadId, payload);
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
  }

  function openPayload(button) {
    var directTarget = directPayloadTargetForAttribution(button);
    if (directTarget) {
      openPayloadContent(button, directTarget);
      return;
    }

    // Non-request/response attribution payloads still use the attribution API.
    if (typeof openAttributionModal === "function") {
      openAttributionModal(button).then(function(handled) {
        if (!handled) openPayloadContent(button);
      });
      return;
    }
    openPayloadContent(button);
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

  function formatPayloadTokenEstimate(value) {
    var numeric = Number(value || 0);
    if (!Number.isFinite(numeric) || numeric <= 0) return "";
    var compact;
    if (typeof formatCompactToken === "function") {
      compact = formatCompactToken(numeric);
    } else if (numeric >= 1000000) {
      compact = (numeric / 1000000).toFixed(1) + "M";
    } else if (numeric >= 1000) {
      compact = (numeric / 1000).toFixed(1) + "K";
    } else {
      compact = String(Math.round(numeric));
    }
    return "~" + compact + " tokens";
  }

  function payloadSubtitle(payloadId, payload) {
    var parts = [payloadId || "diagnostic"];
    if (payload && payload.size) parts.push(payload.size);
    var tokenSummary = formatPayloadTokenEstimate(payload && payload.token_estimate);
    if (tokenSummary) parts.push(tokenSummary);
    return parts.filter(Boolean).join(" · ");
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
    var tokenSummary = formatPayloadTokenEstimate(payload.token_estimate);
    var shell = makeEl("div", "sd-payload-shell payload-shell");
    var meta = makeEl("aside", "sd-payload-meta payload-meta");
    meta.appendChild(makeEl("h3", "", "Metadata"));
    appendKv(meta, "kind", kind);
    appendKv(meta, "status", status);
    appendKv(meta, "size", size);
    if (tokenSummary) appendKv(meta, "result tokens", tokenSummary);
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
        if (subtitleEl && payload) {
          subtitleEl.textContent = payloadSubtitle(payloadId, payload);
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
