  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Payload modal: single shell ──` */

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
    modal.id = "payload-modal";
    modal.className = "sd-payload-modal payload-modal payload-modal--sd";
    modal.setAttribute("aria-labelledby", "sd-payload-title");
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Build modal structure using DOM APIs to avoid innerHTML quality gate`
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

  function openPayloadContent(button, override) {
    override = override || {};
    var modal = ensurePayloadModal();
    var payloadId = override.payloadId || button.getAttribute("data-payload-id") || "";
    var title = override.title || button.getAttribute("data-payload-title") || button.textContent.trim() || "Payload";
    var kind = override.kind || button.getAttribute("data-payload-kind") || "";
    var source = payloadId
      ? qs(document, 'template[data-payload-source="' + cssEscape(payloadId) + '"], [data-payload-source="' + cssEscape(payloadId) + '"]')
      : null;
    var sourceIsIndexOnly = !!(source && source.getAttribute && source.getAttribute("data-payload-index-only") === "true");
    var sourceTokenEstimate = source ? source.getAttribute("data-payload-token-estimate") : "";
    var sourceTokenSummary = formatPayloadTokenEstimate(sourceTokenEstimate);

    var titleEl = qs(modal, "[data-payload-title]");
    var subtitleEl = qs(modal, "[data-payload-subtitle]");
    var body = qs(modal, "[data-payload-body]") || qs(modal, ".sd-modal-body");

    if (titleEl) titleEl.textContent = title;
    modal.removeAttribute('data-bucket-detail-round');
    modal.removeAttribute('data-attribution-state');
    if (subtitleEl) subtitleEl.textContent = conversationPayloadTitle(kind)
      ? "" : [payloadId || "diagnostic", sourceTokenSummary].filter(Boolean).join(" · ");

    if (body) {
      if (source && !sourceIsIndexOnly) {
        var htmlContent = (source.tagName && source.tagName.toLowerCase() === "template")
          ? source.innerHTML
          : source.innerHTML;
        setHtml(body, htmlContent);
      } else if (payloadId && window.fetch) {
        // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`No template found (slim mode) — fetch from payload API`
        setHtml(body, '<div class="sd-payload-loading"><p>Loading payload...</p></div>');
        var apiBase = getApiBase();
        var fetchUrl = apiBase.replace(/\/$/, '') + '/payload/' + encodeURIComponent(payloadId);
        modal.setAttribute('data-loading-payload-id', payloadId);
        readSessionContentPage(fetchUrl)
          .then(function (payload) {
            if (modal.getAttribute('data-loading-payload-id') !== payloadId) return;
            if (subtitleEl && payload) {
              subtitleEl.textContent = payloadSubtitle(payloadId, payload);
            }
            if (body) {
              var rendered = payloadNodeFromJson(payload);
              body.replaceChildren(rendered);
              var path = button.getAttribute('data-attribution-path');
              if (path) appendInlineAttribution(rendered, path, payload);
              else if (/^round:(?:req|resp):/.test(payloadId)) {
                rendered.append(makeEl('p', 'sd-payload-warning', '多条记录的归因请在展开后按调用查看。'));
              }
            }
          })
          .catch(function (err) {
            if (modal.getAttribute('data-loading-payload-id') !== payloadId) return;
            if (body) {
              body.replaceChildren();
              var message = document.createElement('p');
              message.textContent = 'Unable to load payload: ' + err.message;
              body.appendChild(message);
              var retry = document.createElement('button');
              retry.type = 'button';
              retry.className = 'sd-btn sd-btn--secondary sd-btn--sm';
              retry.textContent = /refresh/i.test(err.message) ? 'Refresh page' : 'Retry';
              retry.addEventListener('click', function () {
                if (/refresh/i.test(err.message)) window.location.reload();
                else openPayloadContent(button, override);
              });
              body.appendChild(retry);
            }
          });
      } else {
        setHtml(body, diagnosticPayloadHtml(payloadId, title, kind));
      }
    }

    if (typeof modal.showModal === "function" && !modal.open) modal.showModal();
    else modal.setAttribute("open", "");
  }

  function appendInlineAttribution(parent, path, payload) {
    var request = path.split('?')[0].endsWith('/request');
    var details = makeEl('details', 'sd-payload-original');
    details.setAttribute('data-payload-attribution', request ? 'request' : 'response');
    var label = request ? '输入归因' : '输出归因';
    details.append(makeEl('summary', '', label));
    var state = makeEl('div', 'sd-attribution-summary-grid');
    details.append(state);
    var notice = parent.querySelector(".sd-payload-warning");
    if (notice) notice.after(details);
    else parent.prepend(details);
    var status = makeEl('p', 'sd-payload-warning', '正在读取' + label + '…');
    status.setAttribute('role', 'status');
    state.append(status);
    var url = getApiBase().replace(/\/$/, '') + path;
    function load() {
      status.textContent = '正在读取' + label + '…';
      state.replaceChildren(status);
      return readSessionContentPage(url).then(function (response) {
        var data = response.data || {};
        if (response.kind !== 'llm.' + (request ? 'request' : 'response') + '_attribution' || !data.callId) {
          throw new Error('归因未记录');
        }
        var tokens = {fresh: data.freshInputTokens, cacheRead: data.cacheReadTokens,
          cacheWrite: data.cacheWriteTokens, output: data.outputTokens, provenance: data.provenance};
        if (data.tokens && typeof data.tokens === 'object') tokens = data.tokens;
        details.setAttribute('data-attribution-call', data.callId);
        details.setAttribute('data-attribution-scope', data.scope || '');
        state.replaceChildren();
        appendKv(state, '调用', (data.callKey || data.callId) + (data.scope === 'subagent' ? ' · 子 agent' : ' · 主会话'));
        var parts = request ? [['fresh', '新鲜输入'], ['cacheRead', '缓存读取'], ['cacheWrite', '缓存写入']]
          : [['output', '输出']];
        parts.forEach(function (part) {
          appendKv(state, part[1], TokenProvenance.value(tokens, part[0], function (n) { return Number(n).toLocaleString(); }));
        });
        var measured = parts.every(function (part) { return TokenProvenance.state(tokens, part[0]) === 'provider_reported'; });
        appendKv(state, '计量依据', measured ? '提供方报告' : '含估算、缺测或来源未知，见各分项');
        var count = request ? data.requestToolResultCount : data.responseToolCallCount;
        if (count != null) appendKv(state, request ? '已记录工具结果' : '已记录工具指令', String(count));
        if (!request && Array.isArray(data.responseTools) && data.responseTools.length) {
          var tools = makeEl('section', 'sd-payload-section');
          tools.append(makeEl('h3', '', '工具指令'));
          data.responseTools.forEach(function (tool) {
            var item = makeEl('div', 'sd-payload-tool-link');
            item.append(makeEl('span', '', (tool.name || '工具') + (tool.preview ? ' · ' + tool.preview : '')));
            var button = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm', 'Input');
            button.type = 'button';
            button.setAttribute('data-action', 'open-payload');
            button.setAttribute('data-payload-kind', 'tool_input');
            button.setAttribute('data-payload-id', 'tool:input:' + tool.id);
            button.setAttribute('data-payload-title', (tool.name || '工具') + ' · Input');
            item.append(button);
            tools.append(item);
          });
          var empty = parent.querySelector('.sd-payload-empty');
          if (empty && !(payload.reading || []).length) empty.replaceWith(tools);
          else details.after(tools);
        }
      }).catch(function (error) {
        status.textContent = /refresh/i.test(error.message) ? '索引已变化；刷新页面后重试。' : label + '暂不可用。';
        var retry = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm', 'Retry');
        retry.type = 'button';
        retry.addEventListener('click', function () {
          if (/refresh/i.test(error.message)) window.location.reload();
          else load();
        });
        state.append(retry);
        details.open = true;
      });
    }
    load();
  }

  function openPayload(button) {
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Attribution buttons should open the analysis modal directly; only`
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`ordinary payload buttons fall back to raw request/response/result data.`
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
    appendReadingBlock(parent, title, { text: text }, type);
  }

  function appendRenderedMarkdown(target, html) {
    var rendered = new DOMParser().parseFromString(html, "text/html");
    target.replaceChildren.apply(target, Array.from(rendered.body.childNodes));
  }

  function organizeRequestMarkdown(markdown) {
    var first = markdown.firstElementChild;
    // 只单列已知的完整页面打开标记；普通引用、围栏和混合段落不变。
    if (first && first.matches("p") && !first.childElementCount
        && /^<external_codex_apps_open_page>\s*\{\s*"page_id"\s*:\s*null\s*\}\s*<\/external_codex_apps_open_page>$/.test(first.textContent.trim())) {
      var details = makeEl("details", "sd-reading-page-marker");
      details.appendChild(makeEl("summary", "", "页面打开标记（来源未确认）"));
      details.appendChild(makeEl("pre", "", first.textContent));
      first.replaceWith(details);
    }
    markdown.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach(function (heading) {
      if (heading.childElementCount) return;
      var match = /^([^:\n]{1,160}\.[a-z\d]{1,12}:)([ \t]+)((?:\/|[a-z]:[\\/])[^\n]+)$/i.exec(heading.textContent);
      if (!match) return;
      heading.classList.add("sd-reading-file-heading");
      var filename = makeEl("span", "sd-reading-file-name", match[1]);
      var location = makeEl("code", "sd-reading-file-path", match[2] + match[3]);
      location.tabIndex = 0;
      heading.replaceChildren(filename, location);
    });
  }

  function appendReadingBlock(parent, title, block, type, request) {
    var section = makeEl("section", "sd-content-block content-block");
    if (type === "tool") {
      section.classList.add("content-block--tool", "sd-response-block--tool");
    } else if (type === "text") {
      section.classList.add("content-block--text", "sd-response-block--text");
    }
    var head = makeEl("div", "sd-response-block-head block-head");
    head.appendChild(makeEl("span", "sd-card-title", title));
    var blockBody = makeEl("div", "sd-response-block-body block-body");
    if (block.html) {
      var markdown = makeEl("article", "sd-reading-markdown");
      appendRenderedMarkdown(markdown, block.html);
      if (request) organizeRequestMarkdown(markdown);
      markdown.querySelectorAll("table").forEach(function (table) {
        var scroll = makeEl("div", "sd-reading-table-scroll");
        scroll.tabIndex = 0;
        scroll.setAttribute("role", "region");
        scroll.setAttribute("aria-label", "Scrollable Markdown table");
        table.replaceWith(scroll);
        scroll.appendChild(table);
      });
      blockBody.appendChild(markdown);
    } else {
      blockBody.appendChild(makeEl("pre", "", block.text));
    }
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
    if (payload && conversationPayloadTitle(payload.kind)) return "";
    var parts = [payloadId || "diagnostic"];
    if (payload && payload.size) parts.push(payload.size);
    var tokenSummary = formatPayloadTokenEstimate(payload && payload.token_estimate);
    if (tokenSummary) parts.push(tokenSummary);
    return parts.filter(Boolean).join(" · ");
  }

  function conversationPayloadTitle(kind) {
    return {
      llm_request: "Request", subagent_request: "Request",
      llm_response: "Response", subagent_response: "Response"
    }[kind];
  }

  function payloadNodeFromJson(payload) {
    payload = payload || {};
    var kind = payload.kind || "unknown";
    var status = payload.status || (payload.truncated ? "truncated" : "available");
    var size = payload.size || "";
    var text = payload.text || payload.content || "";
    var toolName = payload.tool_name || "";
    var toolStatus = payload.tool_status || "";
    var toolCommand = payload.tool_command || "";
    var tokenSummary = formatPayloadTokenEstimate(payload.token_estimate);
    var conversationTitle = conversationPayloadTitle(kind);
    if (conversationTitle) return conversationPayload(payload, conversationTitle, text);
    var shell = makeEl("div", "sd-payload-shell payload-shell");
    var meta = makeEl("aside", "sd-payload-meta payload-meta");
    meta.appendChild(makeEl("h3", "", "Metadata"));
    appendKv(meta, "kind", kind);
    appendKv(meta, "status", status);
    if (size) appendKv(meta, "size", size);
    if (tokenSummary) appendKv(meta, "tokens", tokenSummary);
    if (toolName) appendKv(meta, "tool", toolName);
    if (toolStatus) appendKv(meta, "tool status", toolStatus);

    var main = makeEl("main", "sd-payload-main payload-main");
    if (toolCommand) appendPreBlock(main, "Command", toolCommand, "tool");
    var contentTitle = {
      tool_input: "Input", tool_result: "Result"
    }[kind] || "Content";
    if (payload.truncated) main.appendChild(makeEl("p", "sd-payload-warning", "内容已截断。"));
    if (text) {
      appendPreBlock(main, contentTitle, text, "text");
      if (navigator.clipboard && (kind === 'tool_input' || kind === 'tool_result')) {
        var copy = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm', 'Copy');
        copy.type = 'button';
        copy.addEventListener('click', function () {
          navigator.clipboard.writeText(text).then(function () { copy.textContent = 'Copied'; })
            .catch(function () { copy.textContent = 'Copy unavailable'; });
        });
        main.append(copy);
      }
    }
    else main.appendChild(makeEl("div", "sd-payload-empty", contentTitle + " 内容未记录"));

    shell.appendChild(meta);
    shell.appendChild(main);
    return shell;
  }

  function conversationPayload(payload, title, raw) {
    var main = makeEl("div", "sd-payload-main sd-conversation-payload");
    main.appendChild(makeEl("p", "sd-payload-warning", "仅展示本地可见记录，不代表完整 provider context。"));
    if (payload.truncated) main.appendChild(makeEl("p", "sd-payload-warning", "内容已截断。"));
    var reading = Array.isArray(payload.reading) ? payload.reading : (raw ? [{ text: raw }] : []);
    if (raw && (payload.unconfirmedContext || reading.length !== 1 || reading[0].text !== raw)) {
      var details = makeEl("details", "sd-payload-original");
      details.setAttribute("data-payload-raw", "");
      var summary = payload.unconfirmedContext ? "原始记录（含项目说明或上下文，归属无法确认）"
        : "原始记录（可能包含工具和上下文）";
      details.appendChild(makeEl("summary", "", summary));
      details.appendChild(makeEl("pre", "", raw));
      main.appendChild(details);
    }
    if (!reading.length) {
      var empty = payload.unconfirmedContext ? "未确认可单列的正文，请查看原始记录。"
        : title === "Request" && raw ? "未单列输入正文；仍有本地记录，请展开“原始记录”查证。" : title + " 正文未记录";
      main.appendChild(makeEl("p", "sd-payload-empty", empty));
    } else {
      reading.forEach(function (block) {
        var label = reading.length > 1 && block.label ? title + " · " + block.label : title;
        appendReadingBlock(main, label, block, "text", title === "Request");
      });
    }
    return main;
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
    readSessionContentPage(url)
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
