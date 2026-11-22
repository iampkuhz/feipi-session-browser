  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Attribution API fetch support ──` */

  var _attributionCache = new Map();

  function _getPageSourceAndSessionId() {
    var path = window.location.pathname;
    var m = path.match(/^\/sessions\/([^\/]+)\/([^\/]+)/);
    if (!m) return { source: "", sessionId: "" };
    return { source: m[1], sessionId: m[2] };
  }

  // 导入和个人详情共用投影，URL 必须保留页面注入的分析范围。
  function _getSessionScopedApiBase() {
    var pageMeta = document.querySelector('meta[name="session-page-api-base"]');
    var payloadMeta = document.querySelector('meta[name="payload-api-base"]');
    var injected = (pageMeta && pageMeta.getAttribute("content")) ||
      (payloadMeta && payloadMeta.getAttribute("content")) || "";
    if (injected) return injected.replace(/\/+$/, "");
    var pageInfo = _getPageSourceAndSessionId();
    if (!pageInfo.source || !pageInfo.sessionId) return "";
    return "/api/sessions/" + encodeURIComponent(pageInfo.source) + "/" +
      encodeURIComponent(pageInfo.sessionId);
  }

  function attributionApiUrl(button, kind) {
    var payloadId = button.getAttribute("data-payload-id") || "";
    var callId = button.getAttribute("data-attribution-call-id") || "";
    var identityQuery = callId ? "?call_id=" + encodeURIComponent(callId) : "";

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Try main LLM call pattern: llm-R{round}-IX{call}-...`
    var m = payloadId.match(/^llm-R(\d+)-IX(\d+)-/);
    if (m) {
      var apiBase = _getSessionScopedApiBase();
      if (!apiBase) return "";
      return apiBase + "/attribution/" + m[1] + "/" + m[2] + "/" + kind + identityQuery;
    }

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Try subagent pattern: sub-{sa_id}-IX{n}-request-attribution / sub-{sa_id}-IX{n}-response-attribution`
    var sa_m = payloadId.match(/^sub-([^-]+(?:-[^-]+)*)-IX(\d+)-(request|response)-attribution$/);
    if (sa_m) {
      var saId = sa_m[1];
      var saCallIdx = sa_m[2];
      var subagentApiBase = _getSessionScopedApiBase();
      if (!subagentApiBase) return "";
      return subagentApiBase + "/attribution/subagent/" + encodeURIComponent(saId) + "/" + saCallIdx + "/" + kind + identityQuery;
    }

    return "";
  }

  function renderAttributionLoading(kind) {
    var label = kind === "request" ? "Request" : "Response";
    return '<div class="sd-payload-loading">' +
      '<p>Loading ' + label + ' attribution...</p>' +
      '</div>';
  }

  function renderAttributionError(body, errorPayload, url) {
    setHtml(body, '<div class="sd-payload-error">' +
      '<h3>Attribution Load Failed</h3>' +
      '<div class="sd-error-meta">' +
      '<div class="sd-kv"><span>error_type</span><span>' + escapeHtml(errorPayload.error_type || "Unknown") + '</span></div>' +
      '<div class="sd-kv"><span>message</span><span>' + escapeHtml(errorPayload.message || "") + '</span></div>' +
      '</div>' +
      '<p>' + escapeHtml(errorPayload.fallback || "") + '</p>' +
      '<button type="button" class="sd-btn sd-btn--primary" data-action="retry-attribution">Retry</button>' +
      '</div>');
    var retryBtn = body.querySelector('[data-action="retry-attribution"]');
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        _attributionCache.delete(url);
        retryAttributionFetch(url, body);
      });
    }
  }

  function retryAttributionFetch(url, body) {
    setHtml(body, renderAttributionLoading(url.indexOf("/request") !== -1 ? "request" : "response"));
    fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (resp) {
        if (!resp.ok) {
          return resp.json().then(function (d) {
            // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Structured attribution error from server — render directly.`
            if (d && d.kind === "llm.attribution_error") {
              renderAttributionError(body, d, url);
              return;
            }
            throw { status: resp.status, data: d };
          });
        }
        return resp.json();
      })
      .then(function (payload) {
        if (payload && payload.kind === "llm.attribution_error") {
          renderAttributionError(body, payload, url);
        } else if (payload) {
          renderAttributionSuccess(body, payload);
        }
      })
      .catch(function (err) {
        var message = err.data && err.data.message ? err.data.message : "Failed to load attribution data";
        var fallback = err.data && err.data.fallback ? err.data.fallback : "Attribution unavailable; base LLM call metadata is still available.";
        renderAttributionError(body, {
          error_type: err.status ? "HTTP_" + err.status : "NetworkError",
          message: message,
          fallback: fallback,
        }, url);
      });
  }

  function renderAttributionSuccess(body, payload) {
    var data = payload.data || payload;
    var measuredTokens = data.tokens && typeof data.tokens === 'object' ? data.tokens : {
      total: data.totalTokens, fresh: data.freshInputTokens, cacheRead: data.cacheReadTokens,
      cacheWrite: data.cacheWriteTokens, output: data.outputTokens, provenance: data.provenance
    };
    var html = "";

    // 本地重建免责声明。
    html += '<div class="sd-attribution-disclaimer">基于本地日志重建，不等同于真实提供方请求/响应体。</div>';

    // ── 调用身份卡片 ──
    html += '<div class="sd-attribution-topgrid" data-attribution-section="identity-tokens">';
    html += '<section class="sd-attribution-topcard" data-attribution-card="identity">';
    html += '<h3>调用身份</h3>';
    html += '<div class="sd-attribution-identity-grid">';
    html += '<div class="sd-kv"><span>Call ID</span><span title="' + escapeHtml(data.callId || "—") + '">' + escapeHtml(data.callId || "—") + '</span></div>';
    html += '<div class="sd-kv"><span>Call Key</span><span>' + escapeHtml(data.callKey || "—") + '</span></div>';
    html += '<div class="sd-kv"><span>Model</span><span title="' + escapeHtml(data.model || "—") + '">' + escapeHtml(data.model || "—") + '</span></div>';
    html += '<div class="sd-kv"><span>Scope</span><span>' + escapeHtml(scopeLabel(data.scope)) + '</span></div>';
    html += '<div class="sd-kv"><span>Timestamp</span><span title="' + escapeHtml(data.timestamp || "—") + '">' + escapeHtml(data.timestamp ? formatAttributionTime(data.timestamp) : "未记录") + '</span></div>';
    html += '</div>';
    html += '</section>';

    // ── Token 分段卡片 ──
    html += '<section class="sd-attribution-topcard" data-attribution-card="tokens">';
    html += '<h3>调用 Token（输入与输出）</h3>';
    html += '<div class="sd-attribution-summary-grid">';
    html += '<div class="sd-kv"><span>Total</span><span>' + escapeHtml(TokenProvenance.total(measuredTokens, formatCompactToken)) + '</span></div>';
    html += '<div class="sd-kv"><span>Fresh Input</span><span>' + escapeHtml(TokenProvenance.value(measuredTokens, 'fresh', formatCompactToken)) + '</span></div>';
    html += '<div class="sd-kv"><span>Cache Read</span><span>' + escapeHtml(TokenProvenance.value(measuredTokens, 'cacheRead', formatCompactToken)) + '</span></div>';
    html += '<div class="sd-kv"><span>Cache Write</span><span>' + escapeHtml(TokenProvenance.value(measuredTokens, 'cacheWrite', formatCompactToken)) + '</span></div>';
    html += '<div class="sd-kv"><span>Output</span><span>' + escapeHtml(TokenProvenance.value(measuredTokens, 'output', formatCompactToken)) + '</span></div>';
    html += '<div class="sd-kv"><span>Measurement</span><span>' + escapeHtml(TokenProvenance.note(measuredTokens) || 'Provider reported') + '</span></div>';
    html += '</div>';
    html += '</section>';
    html += '</div>';

    // ── 工具计数 + 高级归因 ──
    html += '<div class="sd-attribution-topgrid sd-attribution-topgrid--spaced" data-attribution-section="tools-advanced">';
    html += '<section class="sd-attribution-topcard" data-attribution-card="tool-counts">';
    html += '<h3>工具计数</h3>';
    html += '<div class="sd-attribution-summary-grid">';
    html += '<div class="sd-kv" data-attribution-kv="request-tool-results"><span>Request Tool Results</span><span>' + escapeHtml(String(data.requestToolResultCount != null ? data.requestToolResultCount : "—")) + '</span></div>';
    html += '<div class="sd-kv" data-attribution-kv="response-tool-calls"><span>Response Tool Calls</span><span>' + escapeHtml(String(data.responseToolCallCount != null ? data.responseToolCallCount : "—")) + '</span></div>';
    html += '</div>';
    html += '</section>';

    // ── 高级归因不可用说明 ──
    html += '<section class="sd-attribution-topcard" data-attribution-card="advanced">';
    html += '<h3>高级归因</h3>';
    html += '<div class="sd-attribution-unavailable">';
    html += 'Timing、coverage、bucket 分布与 credit 归因在当前数据源中未记录。';
    html += '</div>';
    html += '</section>';
    html += '</div>';

    setHtml(body, html);
  }

  function scopeLabel(scope) {
    if (scope === "subagent") return "子 agent";
    if (scope === "main") return "主会话";
    return scope || "—";
  }

  function formatAttributionTime(value) {
    if (!value) return "未记录";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString([], {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    });
  }

  function formatCompactToken(val, precision) {
    if (val == null) return "—";
    var formatted = typeof val === "number" ? formatSessionCompact(val) : String(val);
    if (precision === "estimated" || precision === "heuristic" || precision === "residual") return "~" + formatted;
    return formatted;
  }

  async function openAttributionModal(button) {
    var kind = button.getAttribute("data-payload-kind") || "";
    var isRequest = kind === "llm.request_attribution";
    var isResponse = kind === "llm.response_attribution";
    if (!isRequest && !isResponse) return false;

    var apiKind = isRequest ? "request" : "response";
    var url = attributionApiUrl(button, apiKind);
    if (!url) return false;

    var cacheKey = url;
    var modal = ensurePayloadModal();
    var title = button.getAttribute("data-payload-title") || button.textContent.trim() || "Attribution";
    var titleEl = qs(modal, "[data-payload-title]");
    var subtitleEl = qs(modal, "[data-payload-subtitle]");
    var body = qs(modal, "[data-payload-body]") || qs(modal, ".sd-modal-body");

    if (titleEl) titleEl.textContent = title;
    if (subtitleEl) subtitleEl.textContent = "loading...";

    if (body) setHtml(body, renderAttributionLoading(apiKind));
    modal.setAttribute("data-attribution-state", "fetching");
    modal.setAttribute("data-attribution-url", url);

    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "");

    try {
      var payload;
      if (_attributionCache.has(cacheKey)) {
        payload = _attributionCache.get(cacheKey);
      } else {
        var resp = await fetch(url, { headers: { "Accept": "application/json" } });
        if (!resp.ok) {
          var errData = await resp.json().catch(function () { return null; });
          // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`If the server returned a structured attribution error payload,`
          // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`render it directly instead of falling through to the generic catch.`
          if (errData && errData.kind === "llm.attribution_error") {
            renderAttributionError(body, errData, url);
            modal.setAttribute("data-attribution-state", "error");
            if (subtitleEl) subtitleEl.textContent = "error";
            return true;
          }
          // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`For other server errors (NotFound, etc.), also try to surface the message.`
          if (errData && errData.message) {
            var genericPayload = {
              error_type: "HTTP_" + resp.status,
              message: errData.message,
              fallback: errData.fallback || "Failed to load attribution data",
            };
            renderAttributionError(body, genericPayload, url);
            modal.setAttribute("data-attribution-state", "error");
            if (subtitleEl) subtitleEl.textContent = "error";
            return true;
          }
          throw { status: resp.status, data: errData };
        }
        payload = await resp.json();
        _attributionCache.set(cacheKey, payload);
      }

      if (payload.kind === "llm.attribution_error") {
        renderAttributionError(body, payload, url);
        modal.setAttribute("data-attribution-state", "error");
        if (subtitleEl) subtitleEl.textContent = "error";
      } else {
        renderAttributionSuccess(body, payload);
        modal.setAttribute("data-attribution-state", "success");
        if (subtitleEl) subtitleEl.textContent = payload.data.call_id || payload.data.request_id || "";
      }
    } catch (err) {
      var errorPayload = {
        error_type: err.status ? "HTTP_" + err.status : "NetworkError",
        message: err.data && err.data.message ? err.data.message : "Failed to load attribution data",
        fallback: "Attribution unavailable; base LLM call metadata is still available.",
      };
      renderAttributionError(body, errorPayload, url);
      modal.setAttribute("data-attribution-state", "error");
    }

    return true;
  }

  window.openAttributionModal = openAttributionModal;
