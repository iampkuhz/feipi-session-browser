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

  var payloadIntent = 0;
  var payloadViewIntent = 0;
  var payloadNavigation = null;

  function invalidatePayloadNavigation() {
    payloadIntent += 1;
    payloadViewIntent += 1;
    payloadNavigation = null;
    var modal = document.getElementById('sd-payload-modal') || document.getElementById('payload-modal');
    if (modal) {
      modal.removeAttribute('data-loading-payload-id');
      modal.querySelectorAll('[data-local-target], [data-local-result-return], [data-local-results-more], [data-local-relations-more]').forEach(function (node) { node.remove(); });
    }
  }

  function localPayloadKind(kind, payloadId) {
    return /^(?:llm_request|subagent_request)$/.test(kind) && /^(?:main|sa):req:.+/.test(payloadId)
      || /^(?:tool_result|tool\.result)$/.test(kind) && /^tool:result:.+/.test(payloadId);
  }

  function payloadUrl(url, parameters) {
    var parsed = new URL(url, location.href);
    Object.keys(parameters).forEach(function (key) {
      if (parameters[key] == null) parsed.searchParams.delete(key);
      else parsed.searchParams.set(key, parameters[key]);
    });
    return parsed.pathname + parsed.search;
  }

  function payloadContext() {
    return getApiBase() + '|' + (document.body.getAttribute('data-index-generation') || '');
  }

  function openPayloadContent(button, override) {
    override = override || {};
    invalidatePayloadNavigation();
    var intent = payloadIntent;
    var context = payloadContext();
    var modal = ensurePayloadModal();
    if (!modal.hasAttribute('data-payload-lifecycle')) {
      modal.setAttribute('data-payload-lifecycle', '');
      modal.addEventListener('cancel', invalidatePayloadNavigation);
      modal.addEventListener('close', function () { if (!modal.open) invalidatePayloadNavigation(); });
    }
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
        var loading = body.firstElementChild;
        var apiBase = getApiBase();
        var fetchUrl = apiBase.replace(/\/$/, '') + '/payload/' + encodeURIComponent(payloadId);
        var local = localPayloadKind(kind, payloadId);
        if (local) fetchUrl = payloadUrl(fetchUrl, { view: 'local_results' });
        modal.setAttribute('data-loading-payload-id', payloadId);
        readSessionContentPage(fetchUrl)
          .then(function (payload) {
            if (intent !== payloadIntent || context !== payloadContext() || !modal.open || loading.parentNode !== body) return;
            var response = payload;
            if (local) payload = response.payload;
            if (subtitleEl && payload) subtitleEl.textContent = local ? '' : payloadSubtitle(payloadId, payload);
            if (body) {
              var rendered = local ? localPayloadNode(response, fetchUrl, button, modal) : payloadNodeFromJson(payload);
              body.replaceChildren(rendered);
              var path = button.getAttribute('data-attribution-path');
              if (path) appendInlineAttribution(rendered, path, payload);
              else if (/^round:(?:req|resp):/.test(payloadId)) {
                rendered.append(makeEl('p', 'sd-payload-warning', '多条记录的归因请在展开后按调用查看。'));
              }
            }
          })
          .catch(function (err) {
            if (intent !== payloadIntent || context !== payloadContext() || !modal.open || loading.parentNode !== body) return;
            if (body) {
              if (local) {
                var reload = function () { openPayloadContent(button, override); };
                localPayloadFailure(body, err, reload, reload);
                return;
              }
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


  function localRelationNotice(page) {
    if (!page) return '目标预览未载入。';
    if (page.identity === 'ambiguous') return '来源记录有冲突，无法确认准确输入。';
    if (page.coverage === 'unknown' || page.identity === 'unconfirmed') return '本地记录不足，尚不能确认包含关系。';
    if (page.coverage === 'partial') return '仅展示当前已确认的输入，记录可能不完整。';
    if (!(page.targets || []).length && !page.nextCursor) return '本地未记录包含此结果的输入。';
    return page.nextCursor ? '当前仅展示已载入的引用；还有其他已确认输入。' : '已确认本地包含；不代表模型实际采用。';
  }

  function localPayloadFailure(host, error, retry, reopen) {
    host.replaceChildren();
    var expired = error.httpStatus === 400 || error.httpStatus === 404;
    var changed = error.httpStatus === 409 || /refresh/i.test(error.message);
    if (changed) invalidatePayloadNavigation();
    host.append(makeEl('p', 'sd-payload-warning', changed ? '索引已变化，请刷新页面后重新读取结果。'
      : expired ? '此引用已失效或不属于当前范围，请重新读取原结果。' : '读取暂时失败，可以重试。'));
    var action = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm', changed ? 'Refresh page' : expired ? '重新读取原结果' : 'Retry');
    action.type = 'button';
    var context = payloadContext();
    var modal = host.closest('dialog');
    var recover = changed ? function () { location.reload(); } : expired ? reopen : retry;
    action.addEventListener('click', function () {
      if (!host.isConnected || !action.isConnected || !modal || !modal.open) return;
      if (context !== payloadContext()) {
        action.disabled = true;
        host.append(makeEl('p', 'sd-payload-warning', '当前范围已变化，请关闭并重新打开原文。'));
        return;
      }
      recover();
    });
    host.append(action);
  }

  // 保留一个返回视图的 DOM，而不是缓存正文或建立无限导航历史。
  function navigateLocalTarget(target, sourceButton, url, origin, modal) {
    var targetUrl = new URL(target.apiUrl, location.href);
    var base = new URL(getApiBase().replace(/\/$/, '') + '/', location.href);
    if (targetUrl.origin !== base.origin || !targetUrl.pathname.startsWith(base.pathname + 'payload/')) {
      sourceButton.disabled = true;
      sourceButton.after(makeEl('p', 'sd-payload-warning', '此入口不属于当前范围，请重新打开原结果。'));
      return;
    }
    var sourceUrl = new URL(url, location.href);
    var fetchUrl = payloadUrl(targetUrl.href, { view: 'local_results', target: target.target,
      limit: sourceUrl.searchParams.get('limit'), visibility: sourceUrl.searchParams.get('visibility'), cursor: null, occurrence: null });
    var body = qs(modal, '[data-payload-body]') || qs(modal, '.sd-modal-body');
    var title = qs(modal, '[data-payload-title]');
    var saved = { nodes: Array.from(body.childNodes), scroll: body.scrollTop, focus: sourceButton, title: title.textContent };
    var context = payloadContext();
    var intent = ++payloadIntent;
    payloadViewIntent += 1;
    payloadNavigation = saved;
    var touched = false;
    function touchedByUser(event) { if (event.isTrusted) touched = true; }
    modal.addEventListener('focusin', touchedByUser);
    var startingScroll = 0;
    function scrolledByUser() { if (body.scrollTop !== startingScroll) touched = true; }
    body.addEventListener('scroll', scrolledByUser);
    function active() { return intent === payloadIntent && context === payloadContext() && modal.open && payloadNavigation === saved && view.isConnected; }
    var view = makeEl('div', 'sd-conversation-payload');
    var back = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm', '返回结果');
    back.type = 'button';
    back.setAttribute('data-local-result-return', '');
    back.addEventListener('click', function () {
      if (context !== payloadContext() || !modal.open || payloadNavigation !== saved || !view.isConnected) return;
      ++payloadIntent;
      payloadViewIntent += 1;
      payloadNavigation = null;
      body.replaceChildren.apply(body, saved.nodes);
      title.textContent = saved.title;
      body.scrollTop = saved.scroll;
      if (saved.focus.isConnected) saved.focus.focus({ preventScroll: true });
    });
    var content = makeEl('div', '');
    content.append(makeEl('p', 'sd-payload-loading', '正在读取准确引用…'));
    view.append(back, content);
    body.replaceChildren(view);
    startingScroll = body.scrollTop;
    title.textContent = '包含此结果的本地输入';
    function load() {
      intent = ++payloadIntent;
      readSessionContentPage(fetchUrl).then(function (response) {
        if (!active()) return;
        var rendered = localPayloadNode(response, fetchUrl, origin, modal);
        content.replaceChildren(rendered);
        var targetNode = Array.from(rendered.querySelectorAll('[data-local-reference]')).find(function (node) {
          return node.getAttribute('data-local-reference') === response.localResults.targetReferenceId;
        });
        if (targetNode) {
          targetNode.classList.add('sd-local-result--target');
          if (!touched) { targetNode.scrollIntoView({ block: 'nearest' }); targetNode.focus({ preventScroll: true }); }
        }
        if (target.attributionPath) appendInlineAttribution(rendered, target.attributionPath, response.payload);
      }).catch(function (error) {
        if (active()) localPayloadFailure(content, error, load, function () { openPayloadContent(origin); });
      }).finally(function () {
        modal.removeEventListener('focusin', touchedByUser);
        body.removeEventListener('scroll', scrolledByUser);
      });
    }
    load();
  }

  function appendLocalRelations(host, item, page, url, origin, modal) {
    var targets = [];
    function render(next, append) {
      if (!append) targets = [];
      targets = targets.concat(next ? next.targets || [] : []);
      host.replaceChildren(makeEl('h4', '', '包含此结果的本地输入'));
      var groups = new Map();
      targets.forEach(function (target) {
        var key = target.requestPayloadId;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(target);
      });
      groups.forEach(function (references) {
        var first = references[0];
        var group = makeEl('div', 'sd-local-target');
        var label = '本地记录' + (first.recordIndex == null ? '（编号未记录）' : '#' + first.recordIndex)
          + (first.scope === 'main' ? ' · 主会话' : first.scope === 'subagent' ? ' · 子上下文' : ' · 上下文未确认');
        group.append(makeEl('p', '', label));
        references.forEach(function (target, index) {
          var button = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm', references.length === 1 ? '查看准确引用' : '查看已载入引用 ' + (index + 1));
          button.type = 'button';
          button.setAttribute('data-local-target', '');
          button.addEventListener('click', function () { navigateLocalTarget(target, button, url, origin, modal); });
          group.append(button);
        });
        host.append(group);
      });
      host.append(makeEl('p', 'sd-payload-warning', localRelationNotice(next)));
      if (item.occurrence && (!next || next.nextCursor)) {
        var more = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm', next ? '其他已确认输入' : '读取目标预览');
        more.type = 'button';
        more.setAttribute('data-local-relations-more', '');
        more.addEventListener('click', function () {
          var intent = payloadIntent, context = payloadContext();
          var relationUrl = payloadUrl(url, { target: null, occurrence: item.occurrence, cursor: next && next.nextCursor });
          function load() {
            intent = ++payloadIntent;
            more.disabled = true;
            readSessionContentPage(relationUrl).then(function (response) {
              if (intent !== payloadIntent || context !== payloadContext() || !host.isConnected || !modal.open) return;
              render(response.relations, !!next);
            }).catch(function (error) {
              if (intent !== payloadIntent || !host.isConnected || !modal.open) return;
              localPayloadFailure(host, error, load, function () { openPayloadContent(origin); });
            }).finally(function () { more.disabled = false; });
          }
          load();
        });
        host.append(more);
      }
    }
    render(page, false);
  }

  function localPayloadNode(response, url, origin, modal) {
    var payload = response.payload;
    var page = response.localResults;
    var request = /request$/.test(payload.kind);
    var root;
    if (request) {
      root = conversationPayload(payload, 'Request', payload.text || payload.content || '');
      root.querySelectorAll('.sd-content-block .sd-card-title').forEach(function (heading) { heading.textContent = '输入正文'; });
      if ((page.items || []).length) {
        var empty = root.querySelector('.sd-payload-empty');
        if (empty) empty.textContent = '未单列输入正文；本条包含以下本地工具结果。';
      }
    } else {
      root = makeEl('div', 'sd-payload-main sd-conversation-payload');
      root.append(makeEl('p', 'sd-payload-warning', '按本地记录中的结果分别展示；本地记录编号不是 provider 调用次数。'));
      if (payload.truncated) root.append(makeEl('p', 'sd-payload-warning', '工具级全文已截断；各结果正文状态见下方分项。'));
    }
    var section = makeEl('section', 'sd-local-results');
    section.append(makeEl('h3', '', request ? '本地记录中的工具结果' : '本次工具的结果记录'));
    var items = makeEl('div', 'sd-local-results-items');
    section.append(items);
    function appendPage(current) {
      (current.items || []).forEach(function (item) {
        var article = makeEl('section', 'sd-local-result');
        article.tabIndex = -1;
        if (item.referenceId) article.setAttribute('data-local-reference', item.referenceId);
        article.setAttribute('data-local-result', '');
        article.append(makeEl('h4', '', (item.toolName || '工具') + ' · 结果记录'));
        var content = item.content || {};
        if (content.state === 'missing') article.append(makeEl('p', 'sd-payload-empty', '此结果正文未记录。'));
        else if (!content.text) article.append(makeEl('p', 'sd-payload-empty', '已记录空结果（不是缺失）。'));
        else {
          var output = recordedToolOutput(content.text);
          if (output && !output.text) article.append(makeEl('p', 'sd-payload-empty', '已记录空输出（不是缺失）。'));
          else appendPreBlock(article, output ? '工具输出' : '结果正文', output ? output.text : content.text, 'text');
          payloadCopyButton(article, content.text, '复制此结果原文');
          if (output) {
            var raw = makeEl('details', 'sd-payload-original');
            raw.append(makeEl('summary', '', '包装说明与原始结果'));
            raw.append(makeEl('pre', '', content.text));
            article.append(raw);
          }
        }
        if (content.truncated) article.append(makeEl('p', 'sd-payload-warning', '此结果正文已截断。'));
        if (!request) {
          var relations = makeEl('div', 'sd-local-relations');
          appendLocalRelations(relations, item, item.targetPreview, url, origin, modal);
          article.append(relations);
        } else if (item.identity !== 'confirmed') article.append(makeEl('p', 'sd-payload-warning', '此本地结果的来源尚未确认。'));
        items.append(article);
      });
      var previous = section.querySelector('[data-local-results-more]');
      if (previous) previous.remove();
      if (current.nextCursor) {
        var more = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm', '继续读取结果记录');
        more.type = 'button';
        more.setAttribute('data-local-results-more', '');
        var pageError = makeEl('div', '');
        more.addEventListener('click', function () {
          var intent = payloadIntent, context = payloadContext();
          var nextUrl = payloadUrl(url, { target: null, occurrence: null, cursor: current.nextCursor });
          function load() {
            pageError.replaceChildren();
            intent = ++payloadIntent;
            more.disabled = true;
            readSessionContentPage(nextUrl).then(function (next) {
              if (intent === payloadIntent && context === payloadContext() && section.isConnected && modal.open) { pageError.remove(); appendPage(next.localResults); }
            }).catch(function (error) {
              if (intent === payloadIntent && section.isConnected && modal.open) localPayloadFailure(pageError, error, load, function () { openPayloadContent(origin); });
            }).finally(function () { more.disabled = false; });
          }
          load();
        });
        section.append(more, pageError);
      }
    }
    appendPage(page);
    if (!(page.items || []).length) {
      var unitemizedText = payload.text || payload.content || '';
      if (!request && payload.status === 'available' && unitemizedText) {
        var unitemized = makeEl('section', 'sd-content-block');
        unitemized.setAttribute('data-unitemized-tool-output', '');
        var unitemizedOutput = payload.truncated ? null : recordedToolOutput(unitemizedText);
        unitemized.append(makeEl('h4', '', payload.truncated ? '未分项工具记录（已截断；包含关系未确认）' : '未分项的工具输出（包含关系未确认）'));
        if (unitemizedOutput && !unitemizedOutput.text) unitemized.append(makeEl('p', 'sd-payload-empty', '已记录空输出（不是缺失）。'));
        else appendPreBlock(unitemized, payload.truncated ? '已记录正文（已截断）' : unitemizedOutput ? '工具输出' : '工具级全文', unitemizedOutput ? unitemizedOutput.text : unitemizedText, 'text');
        section.append(unitemized);
      } else section.append(makeEl('p', 'sd-payload-empty', request ? '本页未单列工具结果。' : '此处未能单列结果，可查看工具级全文。'));
    }
    if (page.coverage !== 'complete') section.append(makeEl('p', 'sd-payload-warning', '当前结果记录可能不完整，不能据此判断全部输入。'));
    root.append(section);
    var requestRaw = request && root.querySelector('[data-payload-raw]');
    if (requestRaw) root.append(requestRaw);
    if (!request) {
      var original = makeEl('details', 'sd-payload-original');
      original.setAttribute('data-tool-result-original', '');
      original.append(makeEl('summary', '', payload.truncated ? '工具级全文、包装说明与原始载荷（已截断）' : '工具级全文、包装说明与原始载荷（完整记录）'));
      original.append(payloadNodeFromJson(payload));
      root.append(original);
    }
    return root;
  }

  function appendInlineAttribution(parent, path, payload) {
    var viewIntent = payloadViewIntent;
    var attributionIntent = 0;
    var context = payloadContext();
    var scrollBody = parent.closest('.sd-modal-body');
    var modal = parent.closest('dialog');
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
    function current(intent) {
      return intent === attributionIntent && viewIntent === payloadViewIntent && context === payloadContext() && parent.isConnected && modal && modal.open;
    }
    function load() {
      if (!current(attributionIntent)) return;
      var intent = ++attributionIntent;
      var initialFocus = document.activeElement;
      var initialScroll = scrollBody ? scrollBody.scrollTop : 0;
      status.textContent = '正在读取' + label + '…';
      state.replaceChildren(status);
      return readSessionContentPage(url).then(function (response) {
        if (!current(intent)) return;
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
        if (!current(intent)) return;
        if (error.httpStatus === 409 || /refresh/i.test(error.message)) invalidatePayloadNavigation();
        status.textContent = /refresh/i.test(error.message) ? '索引已变化；刷新页面后重试。' : label + '暂不可用。';
        var retry = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm', 'Retry');
        retry.type = 'button';
        retry.addEventListener('click', function () {
          if (/refresh/i.test(error.message)) window.location.reload();
          else load();
        });
        state.append(retry);
        if (document.activeElement === initialFocus && (!scrollBody || scrollBody.scrollTop === initialScroll)) details.open = true;
      });
    }
    load();
  }

  function openPayload(button) {
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Attribution buttons should open the analysis modal directly; only`
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`ordinary payload buttons fall back to raw request/response/result data.`
    if (typeof openAttributionModal === "function") {
      invalidatePayloadNavigation();
      var intent = payloadIntent;
      openAttributionModal(button).then(function(handled) {
        if (!handled && intent === payloadIntent) openPayloadContent(button);
      });
      return;
    }
    openPayloadContent(button);
  }

  function closePayload() {
    invalidatePayloadNavigation();
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

  // 有界、只读地解开明确的 output/result 包装；不执行脚本，不从说明文字猜输出。
  function recordedToolOutput(raw) {
    if (raw.length > 1024 * 1024) return null;
    var current = raw;
    var envelope = /^Script completed\r?\nWall time [\d.]+ seconds\r?\nOutput:\r?\n([\s\S]*)$/.exec(current);
    if (envelope) current = envelope[1];
    var fields = envelope ? ['Output'] : [];
    for (var depth = 0; depth < 4; depth += 1) {
      var value;
      try { value = JSON.parse(current); } catch (ignored) { break; }
      if (!value || Array.isArray(value) || typeof value !== 'object') break;
      var keys = ['output', 'result'].filter(function (key) { return Object.prototype.hasOwnProperty.call(value, key); });
      if (keys.length !== 1 || typeof value[keys[0]] !== 'string') break;
      current = value[keys[0]];
      fields.push(keys[0]);
    }
    if (!fields.length) return null;
    return { text: current, field: fields.join(' → ') };
  }

  // Only a complete, bounded, single literal field; matching the entire object rejects duplicate/escaped keys and wrappers.
  function recordedMultilineToolInput(text) {
    if (text.length > 65536) return null;
    var match = /^[ \t\r\n]*\{[ \t\r\n]*"(?:cmd|command|script)"[ \t\r\n]*:[ \t\r\n]*("(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*")[ \t\r\n]*\}[ \t\r\n]*$/.exec(text);
    if (!match) return null;
    var command;
    try { command = JSON.parse(match[1]); } catch (ignored) { return null; }
    return /[\r\n]/.test(command) ? command : null;
  }

  function payloadCopyButton(parent, text, label) {
    if (!navigator.clipboard) return;
    var copy = makeEl('button', 'sd-btn sd-btn--secondary sd-btn--sm', label);
    copy.type = 'button';
    copy.addEventListener('click', function () {
      navigator.clipboard.writeText(text).then(function () { copy.textContent = 'Copied'; })
        .catch(function () { copy.textContent = 'Copy unavailable'; });
    });
    parent.append(copy);
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
    if (kind === 'tool_result') shell.classList.add('sd-payload-shell--tool-result');
    var meta = makeEl("aside", "sd-payload-meta payload-meta");
    meta.appendChild(makeEl("h3", "", "Metadata"));
    appendKv(meta, "kind", kind);
    appendKv(meta, "内容状态", status);
    if (size) appendKv(meta, "size", size);
    if (tokenSummary) appendKv(meta, "tokens", tokenSummary);
    if (toolName) appendKv(meta, "tool", toolName);
    if (toolStatus) appendKv(meta, "tool status", toolStatus);

    var main = makeEl("main", "sd-payload-main payload-main");
    if (toolCommand && kind === 'tool_result') {
      var declaration = makeEl('details', 'sd-payload-original');
      declaration.append(makeEl('summary', '', '声明命令与参数（非执行结果）'));
      appendPreBlock(declaration, 'Command', toolCommand, 'tool');
      main.append(declaration);
    } else if (toolCommand) appendPreBlock(main, 'Command', toolCommand, 'tool');
    var contentTitle = {
      tool_input: "Input", tool_result: "Result"
    }[kind] || "Content";
    if (payload.truncated) main.appendChild(makeEl("p", "sd-payload-warning", "内容已截断。"));
    if (text) {
      var command = kind === 'tool_input' && status === 'available' && !payload.truncated ? recordedMultilineToolInput(text) : null;
      var output = kind === 'tool_result' ? recordedToolOutput(text) : null;
      if (command !== null) {
        var input = makeEl('div', '');
        input.setAttribute('data-tool-input-command', '');
        appendPreBlock(input, '命令文本（本次工具参数，不拆分调用）', command, 'text');
        payloadCopyButton(input, command, '复制命令文本');
        main.append(input);
        var parameters = makeEl('details', 'sd-payload-original');
        parameters.setAttribute('data-tool-input-original', '');
        parameters.append(makeEl('summary', '', '完整原始参数（JSON）'));
        parameters.append(makeEl('pre', '', text));
        payloadCopyButton(parameters, text, '复制原始参数');
        main.append(parameters);
      } else if (output) {
        appendKv(meta, '展示', '提取 ' + output.field + ' 正文；其余字段见原始载荷');
        var result = makeEl('div', 'sd-tool-output');
        result.setAttribute('data-tool-output', '');
        if (output.text) appendPreBlock(result, '工具输出', output.text, 'text');
        else result.append(makeEl('p', 'sd-payload-empty', '已记录空输出（不是缺失）'));
        payloadCopyButton(result, output.text, '复制输出');
        main.append(result);
        var original = makeEl('details', 'sd-payload-original');
        original.setAttribute('data-tool-result-original', '');
        original.append(makeEl('summary', '', '包装说明与原始载荷（完整记录）'));
        original.append(makeEl('pre', '', text));
        payloadCopyButton(original, text, '复制原始载荷');
        main.append(original);
      } else {
        if (kind === 'tool_result') appendKv(meta, '展示', '按记录原文展示；未拆分 output/result 字段');
        appendPreBlock(main, contentTitle, text, "text");
        if (kind === 'tool_input' || kind === 'tool_result') payloadCopyButton(main, text, 'Copy');
      }
    }
    else main.appendChild(makeEl("div", "sd-payload-empty", kind === "tool_result" && status === "available" ? "已记录工具返回，暂无可展示的非空正文" : contentTitle + " 内容未记录"));

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
