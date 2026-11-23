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
    override = override || {back: button.payloadBack};
    var modal = ensurePayloadModal();
    var ticket = {};
    modal.payloadReadTicket = ticket;
    modal.removeAttribute('data-loading-payload-id');
    var payloadId = override.payloadId || button.getAttribute("data-payload-id") || "";
    var title = override.title || button.getAttribute("data-payload-title") || button.textContent.trim() || "Payload";
    var kind = override.kind || button.getAttribute("data-payload-kind") || "";
    if (!override.back && kind === 'tool_result') override.back = declaringResponse(button);

    var source = payloadId
      ? qs(document, 'template[data-payload-source="' + cssEscape(payloadId) + '"], [data-payload-source="' + cssEscape(payloadId) + '"]')
      : null;
    var sourceIsIndexOnly = !!(source && source.getAttribute && source.getAttribute("data-payload-index-only") === "true");
    var titleEl = qs(modal, "[data-payload-title]");
    var subtitleEl = qs(modal, "[data-payload-subtitle]");
    var body = qs(modal, "[data-payload-body]") || qs(modal, ".sd-modal-body");

    if (titleEl) titleEl.textContent = title;
    modal.removeAttribute('data-attribution-state');
    if (subtitleEl) subtitleEl.textContent = "";

    if (body) {
      body.scrollTop = 0;
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
        var intent;
        // A nested Input button is replaced by this same dialog's loading state.
        function isCurrent() { return modal.open && modal.payloadReadTicket === ticket; }
        function canRestore() { return isCurrent() && button.isConnected; }
        if (button.closest('[data-session-first-question]')) {
          intent = { kind: 'first-question', valid: canRestore };
        } else if (kind === 'tool_result') {
          var pair = button.closest('[data-tool-payload-pair]') ||
            toolTracePair(payloadId.slice('tool:result:'.length));
          var detail = pair && pair.closest('[data-trace-detail]');
          var round = detail && (detail.id.match(/^round-(\d+)-detail$/) || [])[1];
          if (round) intent = { kind: 'tool-result', tool: pair.dataset.toolId, round: round, valid: canRestore };
        }
        readSessionContentPage(fetchUrl, intent)
          .then(function (payload) {
            if (!isCurrent()) return;
            if (body) {
              var rendered = payloadNodeFromJson(payload);
              body.replaceChildren(rendered);
              appendPayloadNavigation(rendered, button, override);
              if (kind === 'tool_result' && payload.kind === kind) {
                attachToolResultEvidence(rendered, button, payload, payloadId, subtitleEl, override.back);
              }
              var path = button.getAttribute('data-attribution-path');
              if (path) appendInlineAttribution(rendered, path, payload, button);
              else if (/^round:(?:req|resp):/.test(payloadId)) {
                rendered.prepend(makeEl('p', 'sd-reading-usage-note', '来源用量：展开轮次后按调用查看。'));
              }
            }
          })
          .catch(function (err) {
            if (!isCurrent()) return;
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

  function appendInlineAttribution(parent, path, payload, origin) {
    var request = path.split('?')[0].endsWith('/request');
    var section = makeEl('section', 'sd-payload-reported');
    section.setAttribute('data-payload-attribution', request ? 'request' : 'response');
    var label = request ? '输入用量明细' : '输出用量明细';
    var summary = makeEl('h3', 'sd-reading-usage-heading', label);
    section.append(summary);
    var state = makeEl('div', 'sd-attribution-summary-grid');
    section.append(state);
    parent.querySelector('.sd-reading-panel').append(section);
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
        var tokens = Object.assign({total: data.totalTokens, fresh: data.freshInputTokens,
          cacheRead: data.cacheReadTokens, cacheWrite: data.cacheWriteTokens,
          output: data.outputTokens, provenance: data.provenance}, data.tokens);
        if (!section.isConnected) return;
        renderPayloadMetadata(parent, payload, response.source, data);
        var round = response.roundIndex || attributionRound(path);
        var roundLabel = roundDisplayLabel(round);
        var callLabel = [roundLabel, data.callKey].filter(Boolean).join(' · ');
        var peer = parent.querySelector('[data-payload-peer]');
        if (peer) peer.textContent = callLabel + (request ? ' · Response' : ' · Request');
        var reasoning = request ? null : (payload.tokens?.reasoning ?? data.reasoningTokens ?? tokens.reasoning);
        if (!isMeasuredToken(reasoning)) reasoning = null;
        var recorded = payload.tokens?.[request ? 'input' : 'output'];
        var total = isMeasuredToken(recorded) ? recorded : directionTokenTotal(request, tokens, data);
        if (!request && isMeasuredToken(total)) {
          tokens.output = total;
          tokens.provenance = Object.assign({}, tokens.provenance, {output: 'provider_reported'});
        }
        renderReadingComposition(parent, total, reasoning);
        section.setAttribute('data-attribution-call', data.callId);
        section.setAttribute('data-attribution-scope', data.scope || '');
        state.replaceChildren();
        appendKv(state, '调用', (data.callKey || roundLabel) + (data.scope === 'subagent' ? ' · 子 agent' : ' · 主会话'));
        var parts = request ? [['fresh', '新鲜输入'], ['cacheRead', '缓存读取'], ['cacheWrite', '缓存写入']]
          : [['output', '输出']];
        renderReportedUsage(summary, state, label, tokens, parts, reasoning, total);
        if (request) appendCacheReadSplit(section, tokens, total);
        var count = request ? data.requestToolResultCount : data.responseToolCallCount;
        if (count != null) appendKv(state, request ? '已记录工具结果' : '已记录工具指令', String(count));
        if (!request && Array.isArray(data.responseTools) && data.responseTools.length) {
          var tools = makeEl('section', 'sd-payload-section');
          tools.append(makeEl('h3', '', '工具指令'));
          var target = responseDestination(round, data.callId, data.scope, callLabel) || origin;
          data.responseTools.forEach(function (tool) {
            if (!tool.id) return;
            var block = qs(parent, '[data-reading-category="toolCall"][data-tool-call-id="' + cssEscape(tool.id) + '"]');
            var name = tool.name || '工具名称未记录';
            var actions = makeEl('div', 'sd-payload-tool-actions');
            actions.append(toolPayloadLink(tool.id, 'input', name, target, callLabel));
            var observed = tool.resultObserved ?? (toolTracePair(tool.id)?.dataset.resultObserved === 'true');
            if (observed) {
              actions.append(toolPayloadLink(tool.id, 'result', name, target, callLabel));
            } else {
              actions.append(makeEl('span', 'sd-reading-usage-note', '结果未记录'));
            }
            if (block) {
              block.append(actions);
            } else {
              var item = makeEl('div', 'sd-payload-tool-link');
              item.append(makeEl('strong', '', name), makeEl('code', '', tool.preview || '参数预览未记录'), actions);
              tools.append(item);
            }
          });
          if (tools.childElementCount === 1) return;
          var empty = parent.querySelector('.sd-payload-empty');
          if (empty && !(payload.reading || []).length) empty.replaceWith(tools);
          else parent.querySelector('.sd-reading-panel').after(tools);
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
      });
    }
    load();
  }

  function isMeasuredToken(value) {
    return Number.isSafeInteger(value) && value >= 0;
  }

  function directionTokenTotal(request, tokens, data) {
    function measured(key) {
      return TokenProvenance.state(tokens, key) === 'provider_reported' && isMeasuredToken(tokens[key]);
    }
    if (!request) return measured('output') ? tokens.output : null;
    if (measured('input')) return tokens.input;
    if (TokenProvenance.state(tokens, 'input') === 'provider_reported' && isMeasuredToken(data.inputTokens)) {
      return data.inputTokens;
    }
    if (measured('total') && measured('output') && tokens.total >= tokens.output) {
      return tokens.total - tokens.output;
    }
    var keys = ['fresh', 'cacheRead', 'cacheWrite'];
    if (!keys.every(measured)) return null;
    var sum = keys.reduce(function (total, key) { return total + tokens[key]; }, 0);
    return isMeasuredToken(sum) ? sum : null;
  }

  function renderReportedUsage(summary, state, label, tokens, parts, reasoning, directionTotal) {
    var reported = parts.filter(function (part) {
      return TokenProvenance.state(tokens, part[0]) === 'provider_reported' && isMeasuredToken(tokens[part[0]]);
    });
    var total = reported.reduce(function (sum, part) { return sum + tokens[part[0]]; }, 0);
    var complete = reported.length === parts.length;
    var formatter = new Intl.NumberFormat();
    summary.textContent = label + ' · ' + (complete ? '来源报告 ' + formatter.format(total) + ' tokens'
      : reported.length ? '已报告 ' + formatter.format(total) + ' tokens，另有未知分项'
        : isMeasuredToken(directionTotal) ? '来源报告 ' + formatter.format(directionTotal) + ' tokens，分项未记录'
          : '来源报告总量未知');
    if (parts.length === 1 && reasoning === null) summary.textContent += ' · 推理等非正文用量未单列';
    var list = makeEl('ul', 'sd-reading-usage-parts');
    parts.forEach(function (part) {
      var key = part[0];
      var item = makeEl('li', 'sd-reading-usage-part sd-reading-usage-part--' + key);
      var precision = TokenProvenance.state(tokens, key);
      var value = TokenProvenance.value(tokens, key, formatter.format);
      item.append(makeEl('span', '', part[1]), makeEl('strong', '', value));
      if (precision === 'estimated') item.append(makeEl('span', '', '本地估算'));
      if (precision === 'unknown' && value !== 'N/A') item.append(makeEl('span', '', '计量来源未知'));
      list.append(item);
    });
    state.append(list);
  }

  function appendCacheReadSplit(parent, tokens, input) {
    var read = tokens.cacheRead;
    var meter = makeEl('div', 'sd-reading-cache-ratio');
    meter.append(makeEl('h3', 'sd-reading-usage-heading', '输入缓存 · 独立于正文构成'));
    parent.insertBefore(meter, parent.firstChild);
    if (TokenProvenance.state(tokens, 'cacheRead') !== 'provider_reported' ||
        !isMeasuredToken(read) || !isMeasuredToken(input) || input === 0 || read > input) {
      meter.append(makeEl('p', 'sd-reading-token-note', '没有可比较的来源计量；不计算命中比例。'));
      return;
    }
    var entries = [{key: 'cacheRead', label: '缓存命中', tokens: read},
      {key: 'fresh', label: '未命中', tokens: input - read}];
    meter.append(compositionBand(entries, input, 'sd-reading-cache-band'), compositionLegend(entries, input));
  }

  function appendPayloadNavigation(parent, origin, override) {
    if (!parent.classList.contains('sd-conversation-payload') && !override.back) return;
    var navigation = makeEl('nav', 'sd-payload-navigation');
    navigation.setAttribute('aria-label', '载荷导航');
    function add(label, destination) {
      var button = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm sd-payload-nav-action', label);
      button.type = 'button';
      button.addEventListener('click', function () { openPayloadContent(destination); });
      navigation.append(button);
      return button;
    }
    if (override.back) add('返回 ' + payloadDestinationLabel(override.back), override.back);
    var path = origin.dataset.attributionPath;
    if (path) {
      var peerPath = path.replace(/\/(request|response)(?=\?|$)/, function (_, side) {
        return side === 'request' ? '/response' : '/request';
      });
      var peer = qs(document, '[data-attribution-path="' + cssEscape(peerPath) + '"]');
      if (peer && peer !== origin) add(payloadDestinationLabel(peer), peer).dataset.payloadPeer = '';
    }
    if (navigation.childElementCount) parent.prepend(navigation);
  }

  function renderPayloadMetadata(parent, payload, source, data) {
    var meta = parent.querySelector('.sd-payload-metadata');
    var pageSource = qs(document, 'meta[name="session-source"]');
    meta.replaceChildren();
    [
      ['记录来源', source || (pageSource && pageSource.content) || '未记录'],
      ['记录入口类型', data.source || payload.source || '未记录'],
      ['客户端标识', data.client || data.originator || payload.client || payload.originator || '未记录'],
      ['CLI 版本', data.clientVersion || data.cliVersion || payload.clientVersion || payload.cliVersion || '未记录'],
      ['模型', data.model || payload.model], ['模型提供方', data.modelProvider || payload.modelProvider],
      ['工具', payload.tool_name], ['工具状态', payload.tool_status], ['载荷大小', payload.size],
    ].forEach(function (entry) {
      if (!entry[1]) return;
      var cell = makeEl('div', 'sd-payload-meta-cell');
      cell.append(makeEl('dt', '', entry[0]), makeEl('dd', '', entry[1]));
      meta.append(cell);
    });
  }

  function payloadDestinationLabel(button) {
    return button.dataset.payloadTitle || button.textContent.trim();
  }

  function attributionRound(path) {
    return (path.match(/^\/attribution\/(\d+)\//) || [])[1] || '';
  }

  function responseDestination(round, callId, scope, callLabel) {
    if (!round || !callId || (scope !== 'main' && scope !== 'subagent')) return null;
    var path = memberAttributionPath(round, callId, 'response');
    var known = qs(document, '[data-trace-detail] [data-attribution-path="' + cssEscape(path) + '"]');
    if (known) return known;
    var button = makeEl('button');
    var call = { callId: callId, scope: scope };
    button.dataset.attributionPath = path;
    button.dataset.payloadKind = payloadKindFor(call, 'resp');
    button.dataset.payloadId = payloadIdFor(call, 'resp');
    button.dataset.payloadTitle = callLabel + ' · Response';
    return button;
  }

  function declaringResponse(button) {
    var owner = button.closest('[data-declaring-call-id]') ||
      button.closest('.sd-tool-group')?.querySelector('[data-declaring-call-id]');
    var callId = owner?.dataset.declaringCallId;
    var ownerRound = owner?.closest('[data-trace-detail]');
    var round = (ownerRound?.id.match(/^round-(\d+)-detail$/) || [])[1];
    return responseDestination(round, callId, owner?.dataset.declaringCallScope,
      [roundDisplayLabel(round), owner?.dataset.declaringCallKey].filter(Boolean).join(' · '));
  }

  function toolTracePair(id) {
    return qs(document, '[data-tool-payload-pair][data-tool-id="' + cssEscape(id) + '"]');
  }

  function toolPayloadLink(id, side, name, origin, callLabel) {
    var label = side === 'input' ? 'Input' : 'Result';
    var button = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm sd-payload-nav-action',
      [callLabel, label].filter(Boolean).join(' · '));
    button.type = 'button';
    button.dataset.action = 'open-payload';
    button.dataset.payloadKind = 'tool_' + side;
    button.dataset.payloadId = 'tool:' + side + ':' + id;
    button.dataset.toolVisibleName = name;
    button.dataset.payloadTitle = [callLabel, name, label].filter(Boolean).join(' · ');
    button.payloadBack = origin;
    return button;
  }

  function attachToolResultEvidence(parent, origin, payload, payloadId, subtitle, response) {
    if (!payloadId.startsWith('tool:result:')) return;
    var id = payloadId.slice('tool:result:'.length);
    var evidence = payload.toolResult || {};
    var row = origin.closest('[data-tool-call-id]');
    var name = evidence.name || origin.dataset.toolVisibleName || row?.dataset.toolVisibleName || '工具名称未记录';
    var timestamp = localTime(evidence.declaredAt) || row?.dataset.toolObservedTimestamp || '未记录';
    var duration = observedToolTime({observation: evidence, durationMs: evidence.durationMs});
    if (subtitle) subtitle.textContent = '发起时间（声明记录） ' + timestamp +
      ' · 耗时 ' + (duration === '未记录' ? row?.dataset.toolObservedTime || duration : duration);
    var ui = appendReadingBlock(parent, name + ' · 命令与参数', {text: '正在读取同一调用的参数…'}, 'tool');
    ui.section.dataset.resultCommand = '';
    parent.prepend(ui.section);
    var url = getApiBase().replace(/\/$/, '') + '/payload/' + encodeURIComponent('tool:input:' + id);
    function show(text) {
      if (!ui.section.isConnected) return;
      var command = recordedCommand(text);
      ui.body.firstChild.textContent = command || text || '参数未记录';
      if (text) describeReadingBlock(ui, command || text, null);
      if (command && command !== text) {
        var callLabel = response ? payloadDestinationLabel(response).replace(/ · Response$/, '') : '';
        var actions = makeEl('div', 'sd-payload-tool-actions');
        actions.append(toolPayloadLink(id, 'input', name, origin, callLabel));
        ui.section.append(actions);
      }
    }
    readSessionContentPage(url).then(function (input) {
      show(input.kind === 'tool_input' && (!input.callId || input.callId === id) ? input.text || input.content : '');
    }).catch(function (error) {
      show('');
      if (!ui.section.isConnected) return;
      ui.body.firstChild.textContent = /refresh/i.test(error.message)
        ? '索引已变化；刷新页面后重试。' : '参数暂不可用；重新打开此结果可重试。';
    });
  }

  function recordedCommand(text) {
    try {
      var value = JSON.parse(text);
      return [value?.command, value?.cmd].find(function (item) {
        return typeof item === 'string' && item.trim();
      });
    } catch (ignored) {
      return null; // 非 JSON 参数保持已有脱敏文本，不推断其结构。
    }
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

  function isPageOpeningMarker(text) {
    return /^<external_codex_apps_open_page>\s*\{\s*"page_id"\s*:\s*null\s*\}\s*<\/external_codex_apps_open_page>$/.test((text || '').trim());
  }

  function organizeRequestMarkdown(markdown) {
    var first = markdown.firstElementChild;
    // 只单列已知的完整页面打开标记；普通引用、围栏和混合段落不变。
    if (first && first.matches("p") && !first.childElementCount
        && isPageOpeningMarker(first.textContent)) {
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
    if (block.html || (request && isPageOpeningMarker(block.text))) {
      var markdown = makeEl("article", "sd-reading-markdown");
      if (block.html) appendRenderedMarkdown(markdown, block.html);
      else markdown.append(makeEl('p', '', block.text));
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
    return { section: section, head: head, body: blockBody };
  }

  var readingNumber = new Intl.NumberFormat();

  function describeReadingBlock(ui, text, tokens, source, characters) {
    ui.body.classList.add('sd-reading-preview');
    ui.body.tabIndex = 0;
    ui.body.setAttribute('role', 'region');
    ui.body.setAttribute('aria-label', ui.head.textContent);
    var details = makeEl('div', 'sd-reading-block-meta');
    if (source) details.append(makeEl('span', 'sd-reading-token-note', source));
    var chars = characters ?? (text.length - (text.match(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g) || []).length);
    var amount = readingNumber.format(chars) + ' 字符';
    if (tokens != null) amount += ' · 约 ' + readingNumber.format(tokens) + ' tokens';
    details.append(makeEl('span', 'sd-reading-block-measure', amount));
    ui.head.append(details);
    return chars;
  }

  function estimateVisibleReadingTokens(text) {
    if (!text.trim()) return 0;
    // 与 SessionDetailParityAnalyzer.estimateTokens 的本地估算权重一致。
    var cjk = (text.match(/[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]/g) || []).length;
    var ascii = (text.match(/[\x20-\x7e]/g) || []).length;
    var punct = (text.match(/[{}()\[\]"'\\;:,.<>+=~`/@#$%^&*|]/g) || []).length;
    return Math.max(1, Math.round(cjk / 1.8 + punct / 3 + (ascii - punct) / 4 + (text.length - cjk - ascii) / 2.5));
  }

  var readingCategories = {
    skills: 'Skills 列表', loadedSkill: 'Skill 正文', base: '基础指令', side: 'Side Chat 启动上下文',
    instructions: 'Instructions', agents: 'AGENTS.md', tools: 'Tools',
    history: '历史上下文', current: '本次内容', toolCall: '工具调用', toolResult: '工具结果',
    result: '工具返回正文', other: '其他可见内容',
    fork_instructions: '继承 · 指令', fork_user: '继承 · 用户消息',
    fork_assistant: '继承 · 助手消息', fork_tool_input: '继承 · 工具参数',
    fork_tool_result: '继承 · 工具结果', fork_tool_definitions: '继承 · 工具定义'
  };

  function readingCategory(block, title) {
    if (title === 'Result') return 'result';
    var kind = String(block.kind || block.category || block.label || '').toLowerCase();
    if (kind === 'loaded_skill') return 'loadedSkill';
    if (/skill/.test(kind)) return 'skills';
    if (kind === 'base_instructions') return 'base';
    if (kind === 'side_context') return 'side';
    if (/agents/.test(kind)) return 'agents';
    if (/instruction|system|developer/.test(kind)) return 'instructions';
    if (kind === 'tool_call') return 'toolCall';
    if (kind === 'tool_result') return 'toolResult';
    if (/tool/.test(kind)) return 'tools';
    if (block.source === 'reconstructed' || /histor|context|previous|历史/.test(kind)) return 'history';
    if (/conversation|current|user|assistant|本次/.test(kind)) return 'current';
    return title === 'Response' || !kind ? 'current' : 'other';
  }

  function appendInheritedComposition(panel, composition, tokens) {
    var categories = ['instructions', 'user', 'assistant', 'tool_input', 'tool_result', 'tool_definitions'];
    var inherited = categories.map(function (category) {
      var key = 'fork_' + category;
      return {kind: key, chars: tokens[key + '_chars'], tokens: tokens[key]};
    }).filter(function (entry) {
      return isMeasuredToken(entry.tokens) && entry.tokens > 0 && isMeasuredToken(entry.chars);
    });
    if (!inherited.length) return;
    composition.readingEntries.push.apply(composition.readingEntries, inherited);
    panel.append(makeEl('p', 'sd-reading-token-note',
      '父历史按本次分叉的文件字节偏移和事件序号重建。只估算可读文本，不计加密内容，也不代表实际传输的逐项 Token。'));
  }

  function renderReadingComposition(parent, total, reasoning) {
    var composition = parent.querySelector('.sd-reading-composition');
    var note = makeEl('p', 'sd-reading-token-note');
    var counts = new Map();
    (composition.readingEntries || []).forEach(function (entry) {
      var row = counts.get(entry.kind);
      if (!row) {
        row = {key: entry.kind, label: readingCategories[entry.kind], chars: 0, tokens: 0, estimated: true};
        counts.set(entry.kind, row);
      }
      row.chars += entry.chars;
      row.tokens += entry.tokens;
    });
    var entries = Array.from(counts.values()).filter(function (entry) { return entry.tokens > 0; });
    var visible = entries.reduce(function (sum, entry) { return sum + entry.tokens; }, 0);
    var largest = entries.reduce(function (max, entry) {
      return !max || entry.tokens > max.tokens ? entry : max;
    }, null);
    var result = composition.dataset.direction === 'Result';
    if (result && visible > 0) total = visible;
    if (isMeasuredToken(reasoning) && reasoning > 0) {
      entries.push({key: 'reasoning', label: '推理（来源报告）', tokens: reasoning});
    }
    var compacted = isMeasuredToken(reasoning) ? composition.compactionOutput : null;
    if (isMeasuredToken(compacted) && compacted > 0) {
      entries.push({key: 'compaction', label: '压缩响应输出', tokens: compacted});
    }
    var accounted = visible + (reasoning || 0) + (compacted || 0);
    var valid = isMeasuredToken(total) && accounted <= total;
    var hasDenominator = valid && total > 0;
    if (valid && total > accounted) {
      entries.push({key: 'remainder', label: '未识别', tokens: total - accounted, estimated: visible > 0});
    }
    var format = readingNumber.format;
    var caption = result
      ? (visible ? '可读返回正文总量：约 ' + format(visible) + ' tokens。' : '没有可估算的返回正文；总量未知。') +
        ' 工具结果不计为独立模型调用；命令与参数不计入。' :
      !isMeasuredToken(total) ? '本次' + composition.dataset.direction + '总 Token 未知，比例与余量未计算。' :
        '本次' + composition.dataset.direction + '来源报告总量：' + format(total) + ' tokens。' +
          (valid ? '比例以该方向的总量为分母。' : '可见估算与已报告分项之和超过总量，不计算比例或负余量。');
    if (!result && total === 0) caption += ' 来源显式上报为零。';
    if (reasoning === 0) caption += ' 推理：来源显式上报为 0 tokens。';
    if (!result && hasDenominator) caption += ' 有依据的分项覆盖' +
      (visible > 0 ? '约 ' : ' ') + TokenProvenance.percent(accounted / total * 100) + '。';
    if (valid && total === accounted) caption += ' 未识别 ' + (visible > 0 && !result ? '约 ' : '') + '0 tokens。';
    if (!result && visible) caption += ' 可见文本约 ' + format(visible) +
      ' tokens（本地估算；原始记录与本机参考不计入）。';
    note.textContent = caption;
    composition.replaceChildren(makeEl('h3', 'sd-reading-usage-heading', result ? '返回正文构成' : '正文构成与未识别量'), note);
    if (hasDenominator) composition.append(compositionBand(entries, total));
    if (entries.length) composition.append(compositionLegend(entries, hasDenominator ? total : null));
    if (largest && composition.dataset.direction === 'Request') {
      composition.append(makeEl('p', 'sd-reading-token-note', '最大可见项：' + largest.label + '（约 ' +
        format(largest.tokens) + ' tokens）。可优先检查是否能精简；不代表可省下等量 Token。'));
    }
  }

  function compositionLegend(entries, total) {
    var list = makeEl('ul', 'sd-reading-usage-parts');
    entries.forEach(function (entry) {
      var item = makeEl('li', 'sd-reading-usage-part sd-reading-usage-part--' + entry.key);
      item.dataset.tokenPart = entry.key;
      var value = (entry.estimated ? '约 ' : '') + readingNumber.format(entry.tokens) + ' tokens';
      if (total !== null) value += ' · ' + TokenProvenance.percent(entry.tokens / total * 100);
      item.append(makeEl('span', '', entry.label));
      if (entry.chars != null) item.append(makeEl('small', 'sd-reading-usage-chars', readingNumber.format(entry.chars) + ' 字符'));
      item.append(makeEl('strong', '', value));
      list.append(item);
    });
    return list;
  }

  function compositionBand(entries, total, className) {
    var namespace = 'http://www.w3.org/2000/svg';
    var band = document.createElementNS(namespace, 'svg');
    band.setAttribute('class', className || 'sd-reading-usage-band');
    band.setAttribute('viewBox', '0 0 100 1');
    band.setAttribute('preserveAspectRatio', 'none');
    band.setAttribute('aria-hidden', 'true');
    var offset = 0;
    entries.forEach(function (entry) {
      if (!entry.tokens) return;
      var width = entry.tokens / total * 100;
      var segment = document.createElementNS(namespace, 'rect');
      segment.setAttribute('class', 'sd-reading-usage-part--' + entry.key);
      segment.dataset.tokenPart = entry.key;
      segment.setAttribute('x', String(offset));
      segment.setAttribute('width', String(width));
      segment.setAttribute('height', '1');
      band.append(segment);
      offset += width;
    });
    return band;
  }

  function formatPayloadTokenEstimate(value) {
    var numeric = Number(value || 0);
    if (!Number.isFinite(numeric) || numeric <= 0) return "";
    var compact;
    if (typeof formatCompactToken === "function") {
      compact = formatCompactToken(numeric);
    } else if (numeric >= 1000000) {
      compact = Number((numeric / 1000000).toFixed(1)) + "M";
    } else if (numeric >= 1000) {
      compact = Number((numeric / 1000).toFixed(1)) + "K";
    } else {
      compact = String(Math.round(numeric));
    }
    return "~" + compact + " tokens";
  }

  function conversationPayloadTitle(kind) {
    return {
      llm_request: "Request", subagent_request: "Request",
      llm_response: "Response", subagent_response: "Response", tool_result: "Result"
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

  function appendToolsEvidence(parent, blocks) {
    var declarations = blocks.some(function (block) { return block.kind === 'tools'; });
    var observed = Array.from(new Set(blocks.filter(function (block) {
      return block.kind === 'tool_call' && block.source === 'reconstructed' && block.toolCallId && block.label;
    }).map(function (block) { return block.label; })));
    var note = declarations ? 'Tools：已记录部分工具声明，可能不含全部内置或 MCP 工具。'
      : 'Tools：完整工具清单及参数定义未记录。';
    if (observed.length) note += ' 此前调用过：' + observed.join('、') + '（不是工具注册表）。';
    parent.append(makeEl('p', 'sd-reading-usage-note', note));
  }

  function conversationPayload(payload, title, raw) {
    var main = makeEl("div", "sd-payload-main sd-conversation-payload");
    var meta = makeEl('dl', 'sd-payload-metadata');
    main.append(meta);
    renderPayloadMetadata(main, payload, null, {});
    if (title !== 'Result') {
      main.appendChild(makeEl("p", "sd-payload-warning", "仅展示本地记录，不等同于完整发送载荷；未公开推理范围未知。"));
    }
    if (payload.truncated) main.appendChild(makeEl("p", "sd-payload-warning", "内容已截断。"));
    var composition = makeEl('section', 'sd-reading-composition');
    composition.setAttribute('aria-label', 'Token 构成');
    composition.dataset.direction = title;
    composition.readingEntries = [];
    var panel = makeEl('div', 'sd-reading-panel');
    panel.append(composition);
    main.append(panel);
    var reading = Array.isArray(payload.reading) ? payload.reading : null;
    if (title === 'Result' || !reading) reading = raw ? [{text: raw}] : [];
    var configuration = reading.filter(function (block) { return block.kind === 'configuration'; });
    var snapshot = reading.find(function (block) { return block.kind === 'context_snapshot'; });
    var responseEvidence = reading.filter(function (block) {
      return ['response_evidence', 'response_compaction'].includes(block.kind);
    });
    reading = reading.filter(function (block) {
      return !['configuration', 'context_snapshot', 'response_evidence', 'response_compaction'].includes(block.kind);
    });
    if (responseEvidence.length) {
      var evidence = makeEl('aside', 'sd-reading-compression');
      evidence.dataset.responseEvidence = '';
      evidence.append(makeEl('strong', '', '本次模型响应证据'));
      responseEvidence.forEach(function (block) {
        evidence.append(makeEl('p', 'sd-reading-token-note', block.text || ''));
      });
      main.append(evidence);
    }
    if (snapshot) {
      var compression = makeEl('aside', 'sd-reading-compression');
      compression.append(makeEl('strong', '', '本次调用前已压缩上下文'),
        makeEl('p', 'sd-reading-token-note', snapshot.text || '压缩正文未列入 Token 构成。'));
      main.append(compression);
    } else if (reading.some(function (block) { return block.kind === 'side_context' && block.source === 'current'; }) &&
        !reading.some(function (block) { return block.kind === 'conversation' && block.label === 'User' && block.source === 'current'; })) {
      main.append(makeEl('p', 'sd-reading-usage-note', '本次未记录用户原话；Side Chat 启动上下文不是用户提问。'));
    }

    if (raw && title !== 'Result' && (payload.unconfirmedContext || reading.length !== 1 || reading[0].text !== raw)) {
      var details = makeEl("details", "sd-payload-original sd-payload-evidence-action");
      details.setAttribute("data-payload-raw", "");
      var summary = payload.unconfirmedContext ? "原始记录（含项目说明或上下文，归属无法确认）"
        : "原始记录（可能包含工具和上下文）";
      details.appendChild(makeEl("summary", "", summary));
      details.appendChild(makeEl("pre", "", raw));
      main.appendChild(details);
    }
    if (!reading.length && !responseEvidence.length) {
      var empty = payload.unconfirmedContext ? "未确认可单列的正文，请查看原始记录。"
        : title === "Request" && raw ? "未单列输入正文；仍有本地记录，请展开“原始记录”查证。" : title + " 正文未记录";
      main.appendChild(makeEl("p", "sd-payload-empty", empty));
    }
    reading.forEach(function (block) {
      var kind = readingCategory(block, title);
      var named = {skills: 'Skills 列表及使用说明', base: '基础指令', side: 'Side Chat 启动上下文'};
      var user = title === 'Request' && block.label === 'User' && block.kind === 'conversation';
      var label = named[kind] || (user ? (block.source === 'current' ? '用户原话' : '此前用户消息') :
        block.label && (reading.length > 1 || block.kind && kind !== "current") ? title + " · " + block.label : title);
      var ui = appendReadingBlock(main, label, block, "text", title === "Request");
      ui.section.dataset.readingCategory = kind;
      if (title === 'Response' && block.kind === 'tool_call' && block.toolCallId &&
          (block.text?.trim() || ui.body.textContent.trim())) ui.section.dataset.toolCallId = block.toolCallId;
      var source = block.source === 'reconstructed' ? '根据早期本地记录重建' :
        block.source === 'current' ? '本次记录' : title === 'Result' ? '该调用的本地返回记录' : '';
      if (source) ui.section.dataset.readingSource = block.source;
      var text = block.text || ui.body.textContent;
      var tokens = block.tokenEstimate ??
        (Array.isArray(payload.reading) || title === 'Result' ? estimateVisibleReadingTokens(text) : null);
      var chars = describeReadingBlock(ui, text, tokens, source, block.characters);
      if (tokens != null) composition.readingEntries.push({kind: kind, chars: chars, tokens: tokens});
      if (kind === 'skills' && Array.isArray(payload.skillNames) && payload.skillNames.length) {
        window.feipiSkillLookup?.(ui.section, {kind: 'skills', names: payload.skillNames});
      }
    });
    if (title === 'Request') appendToolsEvidence(main, reading);
    if (configuration.length) {
      var reference = makeEl('details', 'sd-payload-original');
      reference.append(makeEl('summary', '', '历史会话配置参考（未计入 Token）'),
        makeEl('p', 'sd-reading-usage-note', '配置记录，未计入 Token。不代表已发送到模型，也不是本机当前配置。'));
      configuration.forEach(function (block) {
        var label = (block.label || '配置') + (block.source === 'reconstructed' ? ' · 较早记录' : ' · 本次记录');
        var ui = appendReadingBlock(reference, label, block, 'text', false);
        describeReadingBlock(ui, block.text || ui.body.textContent, null);
      });
      main.append(reference);
    }
    if (title === 'Result' && raw && navigator.clipboard) {
      var copy = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm sd-payload-evidence-action', 'Copy');
      copy.type = 'button';
      copy.addEventListener('click', function () {
        navigator.clipboard.writeText(raw).then(function () { copy.textContent = 'Copied'; })
          .catch(function () { copy.textContent = 'Copy unavailable'; });
      });
      main.append(copy);
    }
    var callTokens = payload.tokens || {};
    if (title === 'Request') appendInheritedComposition(panel, composition, callTokens);
    if (title === 'Response') composition.compactionOutput = callTokens.compactionOutput;
    if (title !== 'Result' && isMeasuredToken(callTokens.turnTotal)) {
      var comparison = [['本次输入', callTokens.input], ['本次输出', callTokens.output],
        ['本次合计', callTokens.total], ['任务累计', callTokens.turnTotal]];
      var summary = makeEl('dl', 'sd-payload-metadata sd-reading-turn');
      comparison.forEach(function (item) {
        if (!isMeasuredToken(item[1])) return;
        var cell = makeEl('div', 'sd-payload-meta-cell');
        cell.append(makeEl('dt', '', item[0]), makeEl('dd', '', readingNumber.format(item[1]) + ' tokens'));
        summary.append(cell);
      });
      panel.prepend(summary);
    }
    renderReadingComposition(main, title === 'Request' ? callTokens.input : title === 'Response' ? callTokens.output : null,
      title === 'Response' ? callTokens.reasoning : null);
    return main;
  }
