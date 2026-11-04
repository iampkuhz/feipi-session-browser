  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Attribution API fetch support ──` */

  /** 安全取回 primary 值，0 视为有效值，仅在 null/undefined 时 fallback。 */
  function coalesceDefined(primary, fallback) {
    return primary !== null && primary !== undefined ? primary : fallback;
  }

  var _attributionCache = new Map();
  var _toolDetailCache = new Map();
  var _toolDetailSeq = 0;

  function registerToolDetail(detail) {
    var id = "tool-detail-" + (++_toolDetailSeq);
    _toolDetailCache.set(id, detail || {});
    return id;
  }

  function lazyToolDetailHtml(detail) {
    var detailId = registerToolDetail(detail);
    return '<div class="sd-bucket-detail-expanded" hidden data-tool-detail-id="' + escapeHtml(detailId) + '" data-tool-detail-rendered="0">' +
      '<div class="sd-bucket-detail-empty">点击工具项后加载完整 JSON。</div>' +
      '</div>';
  }

  function compactToolPreview(value) {
    var text = String(value || "").replace(/\s+/g, " ").trim();
    if (text.length <= 120) return text;
    return text.slice(0, 117) + "...";
  }

  function hydrateToolDetailItem(item) {
    var expanded = qs(item, '.sd-bucket-detail-expanded');
    if (!expanded || expanded.getAttribute("data-tool-detail-rendered") === "1") return;
    var detailId = expanded.getAttribute("data-tool-detail-id") || "";
    var detail = _toolDetailCache.get(detailId);
    if (!detail) {
      setHtml(expanded, '<div class="sd-bucket-detail-empty">完整 JSON 不可用。</div>');
      expanded.setAttribute("data-tool-detail-rendered", "1");
      return;
    }
    setHtml(expanded, '<pre class="sd-bucket-detail-schema">' + escapeHtml(JSON.stringify(detail, null, 2)) + '</pre>');
    expanded.setAttribute("data-tool-detail-rendered", "1");
  }

  function compactLeafPreview(value, limit) {
    var text = String(value || "").replace(/\s+/g, " ").trim();
    var max = limit || 180;
    if (text.length <= max) return text;
    return text.slice(0, Math.max(0, max - 3)) + "...";
  }

  function stringifyDetailValue(value) {
    if (value === null || value === undefined || value === "") return "";
    if (typeof value === "string") return value;
    try {
      return JSON.stringify(value, null, 2);
    } catch (err) {
      return String(value);
    }
  }

  function leafFullContent(item) {
    if (!item) return "";
    return stringifyDetailValue(
      item.full_content ||
      item.content ||
      item.raw_content ||
      item.raw ||
      item.full_text ||
      item.text ||
      item.input_json ||
      item.call_json ||
      item.input_schema ||
      item.description ||
      item.preview ||
      item.content_preview ||
      item.result_preview ||
      item.summary
    );
  }

  function leafTitle(item, fallback) {
    if (!item) return fallback || "detail";
    return item.label || item.name || item.file_path || item.tool_name || item.source_type ||
      item.content_type || item.role || fallback || "detail";
  }

  function leafSummary(item) {
    if (!item) return "";
    return compactLeafPreview(
      item.summary ||
      item.description_preview ||
      item.command_preview ||
      item.input_preview ||
      item.result_preview ||
      item.preview ||
      item.content_preview ||
      item.full_content ||
      item.content ||
      item.description ||
      "",
      190
    );
  }

  function leafMetaParts(item) {
    var parts = [];
    if (!item) return parts;
    if (item.role) parts.push(String(item.role));
    if (item.content_type) parts.push(String(item.content_type));
    if (item.tool_name) parts.push(String(item.tool_name));
    if (item.source_type) parts.push("来源: " + String(item.source_type));
    else if (item.source) parts.push("来源: " + String(item.source));
    var tokenVal = coalesceDefined(item.tokens, coalesceDefined(item.estimated_tokens, item.content_token_estimate));
    if (tokenVal) parts.push("~" + formatCompactToken(tokenVal) + " tokens");
    if (item.message_index !== null && item.message_index !== undefined) parts.push("#" + String(item.message_index));
    if (item.has_full_content === false) parts.push("preview only");
    return parts;
  }

  function bucketHasDetails(b) {
    if (!b) return false;
    var d = b.details || {};
    return !!(
      (d.items && d.items.length > 0) ||
      (d.explanation && d.explanation.length > 0) ||
      d.preview ||
      d.full_content ||
      d.content ||
      d.raw_content ||
      b.summary ||
      b.content_preview ||
      b.source ||
      b.count_label
    );
  }

  function normalizeBucketLeafItems(b) {
    var d = b.details || {};
    var leaves = [];
    if (d.items && d.items.length) {
      d.items.forEach(function (item, idx) {
        var full = leafFullContent(item);
        leaves.push({
          title: leafTitle(item, (b.label || b.key || "detail") + " #" + (idx + 1)),
          summary: leafSummary(item),
          meta: leafMetaParts(item),
          full: full,
        });
      });
    } else if (d.kind === "current_user_message") {
      leaves.push({
        title: b.label || "Current user message",
        summary: compactLeafPreview(d.preview || d.full_content || b.content_preview || b.summary || "", 190),
        meta: d.tokens ? ["~" + formatCompactToken(d.tokens) + " tokens"] : [],
        full: stringifyDetailValue(d.full_content || d.content || d.preview || b.content_preview || b.summary),
      });
    } else if (d.preview || d.full_content || d.content || d.raw_content) {
      leaves.push({
        title: b.label || d.kind || "detail",
        summary: compactLeafPreview(d.preview || d.full_content || d.content || d.raw_content || "", 190),
        meta: d.tokens ? ["~" + formatCompactToken(d.tokens) + " tokens"] : [],
        full: stringifyDetailValue(d.full_content || d.content || d.raw_content || d.preview),
      });
    }

    if (!leaves.length && (b.summary || b.content_preview || b.source || b.count_label)) {
      leaves.push({
        title: b.label || b.key || "detail",
        summary: compactLeafPreview(b.summary || b.content_preview || "", 190),
        meta: [
          b.source ? "来源: " + b.source : "",
          b.count_label || "",
          b.tokens ? "~" + formatCompactToken(b.tokens) + " tokens" : "",
        ].filter(Boolean),
        full: stringifyDetailValue(b.content_preview || b.summary || ""),
      });
    }
    return leaves;
  }

  function bucketExplanationLines(b) {
    var d = (b && b.details) || {};
    if (!d.explanation || !d.explanation.length) return [];
    return d.explanation.map(function (line) {
      return String(line || "").trim();
    }).filter(Boolean);
  }

  function renderBucketExplanationRow(lines) {
    if (!lines || !lines.length) return "";
    return '<div class="sd-bucket-explanation-row" data-bucket-inline-detail>' +
      lines.map(function (line) {
        return '<span>' + escapeHtml(line) + '</span>';
      }).join('<br>') +
      '</div>';
  }

  function renderBucketLeafCard(leaf) {
    var meta = (leaf.meta || []).filter(Boolean);
    var full = leaf.full || "";
    var html = '<div class="sd-bucket-leaf-card" data-bucket-leaf-card>';
    html += '<button type="button" class="sd-bucket-leaf-head" data-bucket-leaf-toggle aria-expanded="false">';
    html += '<span class="sd-bucket-leaf-title">' + escapeHtml(leaf.title || "detail") + '</span>';
    html += '<span class="sd-bucket-leaf-summary">' + escapeHtml(leaf.summary || "无摘要") + '</span>';
    if (meta.length) {
      html += '<span class="sd-bucket-leaf-meta">' + escapeHtml(meta.join(" · ")) + '</span>';
    } else {
      html += '<span class="sd-bucket-leaf-meta">完整信息</span>';
    }
    html += '<span class="sd-bucket-leaf-chevron">▸</span>';
    html += '</button>';
    html += '<div class="sd-bucket-leaf-full" hidden>';
    if (full) {
      html += '<pre class="sd-bucket-detail-preview sd-bucket-detail-preview--full">' + escapeHtml(full) + '</pre>';
    } else {
      html += '<div class="sd-bucket-detail-empty">没有可展示的完整内容。</div>';
    }
    html += '</div>';
    html += '</div>';
    return html;
  }

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

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Try main LLM call pattern: llm-R{round}-IX{call}-...`
    var m = payloadId.match(/^llm-R(\d+)-IX(\d+)-/);
    if (m) {
      var apiBase = _getSessionScopedApiBase();
      if (!apiBase) return "";
      return apiBase + "/attribution/" + m[1] + "/" + m[2] + "/" + kind;
    }

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Try subagent pattern: sub-{sa_id}-IX{n}-request-attribution / sub-{sa_id}-IX{n}-response-attribution`
    var sa_m = payloadId.match(/^sub-([^-]+(?:-[^-]+)*)-IX(\d+)-(request|response)-attribution$/);
    if (sa_m) {
      var saId = sa_m[1];
      var saCallIdx = sa_m[2];
      var subagentApiBase = _getSessionScopedApiBase();
      if (!subagentApiBase) return "";
      return subagentApiBase + "/attribution/subagent/" + encodeURIComponent(saId) + "/" + saCallIdx + "/" + kind;
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
          var kind = url.indexOf("/request") !== -1 ? "request" : "response";
          renderAttributionSuccess(body, payload, kind, url);
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

  function renderAttributionSuccess(body, payload, kind, cacheKey) {
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
    html += '<h3>' + (kind === "request" ? "请求 Token" : "响应 Token") + '</h3>';
    html += '<div class="sd-attribution-summary-grid">';
    html += '<div class="sd-kv"><span>Total</span><span>' + escapeHtml(TokenProvenance.total(measuredTokens, formatCompactToken)) + ' tokens</span></div>';
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

  // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`── Bucket detail renderer ──`

  function renderBucketDetails(b) {
    var explanationLines = bucketExplanationLines(b);
    var leaves = normalizeBucketLeafItems(b);
    if (!explanationLines.length && !leaves.length) return '<div class="sd-bucket-detail-empty">无详细信息</div>';
    var html = renderBucketExplanationRow(explanationLines);
    if (leaves.length) {
      html += '<div class="sd-bucket-leaf-list" data-bucket-inline-detail>';
      leaves.forEach(function (leaf) {
        html += renderBucketLeafCard(leaf);
      });
      html += '</div>';
    }
    return html;
  }

  function getBucketColorIndex(key) {
    if (key === "unlocated_residual" || key === "unknown_overhead" || key === "unknown") return 8;
    var order = [
      "current_user_input", "conversation_messages", "tool_result_context",
      "tool_definitions", "local_instruction_context", "agent_subagent_prompt",
      "mcp_tool_metadata", "builtin_system_prompt", "unlocated_residual",
    ];
    var idx = order.indexOf(key);
    return idx >= 0 ? (idx % 9) : 7;
  }

  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`* Dynamically load bucket detail content from backend API.` */
  function loadBucketDetailDynamic(modal, bodyEl, roundIdx, bucketKey) {
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Skip if already loaded`
    if (bodyEl.getAttribute("data-bucket-detail-loaded") === "1") return;

    var pageInfo = _getPageSourceAndSessionId();
    var source = pageInfo.source;
    var sessionId = pageInfo.sessionId;

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Use modal-stored values as fallback`
    if (!source && modal) source = modal.getAttribute("data-bucket-detail-source") || "";
    if (!sessionId && modal) sessionId = modal.getAttribute("data-bucket-detail-session-id") || "";

    var apiBase = _getSessionScopedApiBase();
    if (!apiBase && source && sessionId) {
      apiBase = "/api/sessions/" + encodeURIComponent(source) + "/" + encodeURIComponent(sessionId);
    }
    if (!apiBase) return;

    var apiUrl = apiBase + "/bucket-detail/" + encodeURIComponent(roundIdx) + "/" + encodeURIComponent(bucketKey);

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Show loading state`
    bodyEl.textContent = '';
    var loadingDiv = document.createElement('div');
    loadingDiv.className = 'sd-bucket-detail-loading';
    loadingDiv.textContent = '加载中…';
    bodyEl.appendChild(loadingDiv);

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
          setHtml(bodyEl, html);
          bodyEl.setAttribute("data-bucket-detail-loaded", "1");
        } else if (data.note) {
          setHtml(bodyEl, '<div class="sd-bucket-detail-empty">' + escapeHtml(data.note) + '</div>');
        } else {
          setHtml(bodyEl, '<div class="sd-bucket-detail-empty">无详细内容</div>');
        }
      })
      .catch(function (err) {
        setHtml(bodyEl, '<div class="sd-bucket-detail-empty">加载失败: ' + escapeHtml(err.message) + '</div>');
      });
  }

  function kvTitleAttr(v) {
    if (!v || v.value == null) return "—";
    var val = v.value;
    var formatted = typeof val === "number" && val >= 1000 ? (val / 1000).toFixed(1) + "K" : String(val);
    var prec = v.precision || "";
    var prefix = (prec === "estimated" || prec === "heuristic" || prec === "residual") ? "~" : "";
    var parts = [prefix + formatted];
    if (v.source) parts.push("source: " + v.source);
    if (v.fill_strategy) parts.push("strategy: " + v.fill_strategy);
    if (v.note) parts.push("note: " + v.note);
    return escapeHtml(parts.join(" · "));
  }

  function numericValue(v) {
    if (!v || v.value == null) return 0;
    var val = Number(v.value);
    return Number.isFinite(val) ? val : 0;
  }

  function coverageMetricValue(coverage, key) {
    if (!coverage || coverage[key] == null) return null;
    var val = Number(coverage[key]);
    return Number.isFinite(val) ? val : null;
  }

  function formatTokenValue(v) {
    if (!v || v.value == null) return "—";
    var val = v.value;
    var formatted = typeof val === "number" && val >= 1000 ? (val / 1000).toFixed(1) + "K" : String(val);
    var prec = v.precision || "";
    if (prec === "estimated" || prec === "heuristic" || prec === "residual") return "~" + formatted;
    return formatted;
  }

  function formatRatioValue(v) {
    if (!v || v.value == null) return "—";
    var val = v.value;
    if (typeof val === "number" && val <= 1) return (val * 100).toFixed(1) + "%";
    return String(val);
  }

  function formatPercentNumber(val) {
    if (val == null) return "—";
    var num = Number(val);
    if (!Number.isFinite(num)) return "—";
    return (num <= 1 ? num * 100 : num).toFixed(1) + "%";
  }

  function formatCompactToken(val, precision) {
    if (val == null) return "—";
    var formatted = typeof val === "number" && val >= 1000 ? (val / 1000).toFixed(1) + "K" : String(val);
    if (precision === "estimated" || precision === "heuristic" || precision === "residual") return "~" + formatted;
    return formatted;
  }

  function translatePrecision(p) {
    var map = {
      "exact": "精确",
      "provider_reported": "提供方报告",
      "transcript_exact": "转录精确",
      "estimated": "估算",
      "heuristic": "启发式",
      "residual": "未定位",
      "unavailable": "不可用"
    };
    return map[p] || p || "—";
  }

  function getBucketColorClass(key) {
    var map = {
      "current_user_message": "sd-attribution-segment--user",
      "current_user_input": "sd-attribution-segment--user",
      "preceding_tool_results": "sd-attribution-segment--tool",
      "tool_result_context": "sd-attribution-segment--tool",
      "prior_conversation_messages": "sd-attribution-segment--prior",
      "conversation_messages": "sd-attribution-segment--prior",
      "tool_call": "sd-attribution-segment--tool",
      "tool_definitions": "sd-attribution-segment--schema",
      "local_instruction_context": "sd-attribution-segment--local",
      "agent_subagent_prompt": "sd-attribution-segment--agent",
      "mcp_tool_metadata": "sd-attribution-segment--mcp",
      "top_level_system_estimate": "sd-attribution-segment--system",
      "hidden_builtin_system_estimate": "sd-attribution-segment--hidden",
      "builtin_system_prompt": "sd-attribution-segment--hidden",
    };
    return map[key] || "sd-attribution-segment--default";
  }

  async function openAttributionModal(button) {
    var kind = button.getAttribute("data-payload-kind") || "";
    var isRequest = kind === "llm.request_attribution";
    var isResponse = kind === "llm.response_attribution";
    if (!isRequest && !isResponse) return false;

    var apiKind = isRequest ? "request" : "response";
    var url = attributionApiUrl(button, apiKind);
    if (!url) return false;

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Extract round_index from payloadId for bucket-detail API`
    var payloadId = button.getAttribute("data-payload-id") || "";
    var roundIdx = "";
    var rm = payloadId.match(/^llm-R(\d+)-IX(\d+)-/);
    if (rm) roundIdx = rm[1];

    var cacheKey = url;
    var modal = ensurePayloadModal();
    if (roundIdx) modal.setAttribute("data-bucket-detail-round", roundIdx);

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Store session source for bucket-detail API`
    var pageInfo = _getPageSourceAndSessionId();
    if (pageInfo.source) modal.setAttribute("data-bucket-detail-source", pageInfo.source);
    if (pageInfo.sessionId) modal.setAttribute("data-bucket-detail-session-id", pageInfo.sessionId);
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
        renderAttributionSuccess(body, payload, apiKind, cacheKey);
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
