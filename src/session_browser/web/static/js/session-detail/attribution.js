  /* ── Attribution API fetch support ── */

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

    if (d.explanation && d.explanation.length) {
      leaves.unshift({
        title: "说明",
        summary: compactLeafPreview(d.explanation.join(" "), 190),
        meta: [],
        full: d.explanation.join("\n"),
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

  function attributionApiUrl(button, kind) {
    var payloadId = button.getAttribute("data-payload-id") || "";

    // Try main LLM call pattern: llm-R{round}-IX{call}-...
    var m = payloadId.match(/^llm-R(\d+)-IX(\d+)-/);
    if (m) {
      var pageInfo = _getPageSourceAndSessionId();
      if (!pageInfo.source || !pageInfo.sessionId) return "";
      return "/api/sessions/" + encodeURIComponent(pageInfo.source) + "/" + encodeURIComponent(pageInfo.sessionId) + "/attribution/" + m[1] + "/" + m[2] + "/" + kind;
    }

    // Try subagent pattern: sub-{sa_id}-IX{n}-request-attribution / sub-{sa_id}-IX{n}-response-attribution
    var sa_m = payloadId.match(/^sub-([^-]+(?:-[^-]+)*)-IX(\d+)-(request|response)-attribution$/);
    if (sa_m) {
      var saId = sa_m[1];
      var saCallIdx = sa_m[2];
      var pageInfo2 = _getPageSourceAndSessionId();
      if (!pageInfo2.source || !pageInfo2.sessionId) return "";
      return "/api/sessions/" + encodeURIComponent(pageInfo2.source) + "/" + encodeURIComponent(pageInfo2.sessionId) + "/attribution/subagent/" + encodeURIComponent(saId) + "/" + saCallIdx + "/" + kind;
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
            // Structured attribution error from server — render directly.
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
    var html = "";

    // Disclaimer in Chinese
    html += '<div class="sd-attribution-disclaimer">基于本地日志重建，不等同于真实提供方请求/响应体。</div>';

    var usage = data.usage || {};
    var usageSummary = data.usage_summary || usage;
    var timing = data.timing || {};
    var model = data.model || "";
    var notes = data.attribution_notes || [];
    var schemaVersion = data.schema_version || "";
    var callIdentity = data.call_identity || null;
    var orderedSpans = data.ordered_spans || [];
    var semanticBuckets = data.semantic_buckets || [];
    var coverage = data.coverage || null;
    var creditSummary = data.credit_summary || null;
    var diagnostics = data.diagnostics || null;
    var totalInput = coalesceDefined(usageSummary.total_input, usage.total_input);
    var freshInput = coalesceDefined(usageSummary.fresh_input, usage.fresh_input);
    var cacheRead = coalesceDefined(usageSummary.cache_read, usage.cache_read);
    var cacheWrite = coalesceDefined(usageSummary.cache_write, usage.cache_write);
    var coverageProviderTotal = coverageMetricValue(coverage, "provider_total_input");
    var coverageRequestContentTotal = coverageMetricValue(coverage, "request_content_total");
    var coverageReconstructedTotal = coverageMetricValue(coverage, "reconstructed_total");
    var coverageRatio = coverageMetricValue(coverage, "coverage_ratio");
    var coverageResidualTokens = coverageMetricValue(coverage, "residual_tokens");

    // ── Top summary: identity and request/response summary side by side ──
    html += '<div class="sd-attribution-topgrid">';
    if (callIdentity) {
      html += '<section class="sd-attribution-topcard">';
      html += '<h3>调用身份</h3>';
      html += '<div class="sd-attribution-identity-grid">';
      html += '<div class="sd-kv"><span>Agent</span><span>' + escapeHtml(callIdentity.agent_runtime || "—") + '</span></div>';
      html += '<div class="sd-kv"><span>API Family</span><span>' + escapeHtml(callIdentity.api_family || "—") + '</span></div>';
      html += '<div class="sd-kv"><span>Provider</span><span>' + escapeHtml(callIdentity.provider_or_broker || "—") + '</span></div>';
      if (callIdentity.underlying_provider) {
        html += '<div class="sd-kv"><span>底层 Provider</span><span>' + escapeHtml(callIdentity.underlying_provider) + '</span></div>';
      }
      html += '<div class="sd-kv"><span>Model</span><span>' + escapeHtml(callIdentity.model || "—") + '</span></div>';
      html += '<div class="sd-kv"><span>计费单位</span><span>' + escapeHtml((callIdentity.billing_units || []).join(", ") || "—") + '</span></div>';
      if (callIdentity.mapping_confidence != null) {
        html += '<div class="sd-kv"><span>映射置信度</span><span>' + ((callIdentity.mapping_confidence * 100).toFixed(0)) + '%</span></div>';
      }
      html += '</div>';
      html += '</section>';
    }
    html += '<section class="sd-attribution-topcard">';
    html += '<h3>' + (kind === "request" ? "请求摘要" : "响应摘要") + '</h3>';
    html += '<div class="sd-attribution-summary-grid">';
    if (kind === "request") {
      var requestDenominator = coverageRequestContentTotal || numericValue(freshInput);
      html += '<div class="sd-kv"><span>内容分母</span><span title="Request 内容 bucket 分母；Cache Read 是 provider accounting，不作为并列内容来源">' + formatCompactToken(requestDenominator) + '</span></div>';
      html += '<div class="sd-kv"><span>新鲜输入</span><span title="' + kvTitleAttr(freshInput) + '">' + formatTokenValue(freshInput) + '</span></div>';
      html += '<div class="sd-kv"><span>缓存读取</span><span title="' + kvTitleAttr(cacheRead) + '">' + formatTokenValue(cacheRead) + '</span></div>';
      html += '<div class="sd-kv"><span>缓存写入</span><span title="' + kvTitleAttr(cacheWrite) + '">' + formatTokenValue(cacheWrite) + '</span></div>';
      if (coverage) {
        html += '<div class="sd-kv"><span>Provider 总计</span><span title="Provider input-side total；包含 Fresh 与 Cache Read">' + formatCompactToken(coverageProviderTotal) + '</span></div>';
        html += '<div class="sd-kv"><span>本地重建</span><span title="本地日志可重建并已归因的 request 内容，不包含 provider cache hit accounting">' + formatCompactToken(coverageReconstructedTotal) + '</span></div>';
        html += '<div class="sd-kv"><span>覆盖率</span><span title="本地重建 / 内容分母">' + formatPercentNumber(coverageRatio) + '</span></div>';
        html += '<div class="sd-kv"><span>残差</span><span title="内容分母 - 本地重建">' + formatCompactToken(coverageResidualTokens) + '</span></div>';
      } else {
        html += '<div class="sd-kv"><span>覆盖率</span><span title="' + kvTitleAttr(usage.coverage) + '">' + formatRatioValue(usage.coverage) + '</span></div>';
        var unkValTop = numericValue(usage.unknown);
        var unkPctTop = requestDenominator > 0 ? ((unkValTop / requestDenominator) * 100).toFixed(1) : "0.0";
        html += '<div class="sd-kv"><span>未定位</span><span title="' + formatCompactToken(unkValTop) + '（' + unkPctTop + '%）">' + formatCompactToken(unkValTop) + '（' + unkPctTop + '%）</span></div>';
      }
    } else {
      html += '<div class="sd-kv"><span>总输出</span><span title="' + kvTitleAttr(usage.total_output) + '">' + formatTokenValue(usage.total_output) + '</span></div>';
      html += '<div class="sd-kv"><span>可见文本</span><span title="' + kvTitleAttr(usage.visible_text) + '">' + formatTokenValue(usage.visible_text) + '</span></div>';
      html += '<div class="sd-kv"><span>工具使用</span><span title="' + kvTitleAttr(usage.tool_use) + '">' + formatTokenValue(usage.tool_use) + '</span></div>';
      html += '<div class="sd-kv"><span>元数据</span><span title="' + kvTitleAttr(usage.metadata) + '">' + formatTokenValue(usage.metadata) + '</span></div>';
      html += '<div class="sd-kv"><span>覆盖率</span><span title="' + kvTitleAttr(usage.coverage) + '">' + formatRatioValue(usage.coverage) + '</span></div>';
      html += '<div class="sd-kv"><span>未定位</span><span title="' + kvTitleAttr(usage.unknown) + '">' + formatTokenValue(usage.unknown) + '</span></div>';
    }
    html += '</div>';
    html += '</section>';
    html += '<section class="sd-attribution-topcard">';
    html += '<h3>调用信息</h3>';
    html += '<div class="sd-attribution-call-grid">';
    html += '<div class="sd-kv"><span>模型</span><span title="' + escapeHtml(model || "—") + '">' + escapeHtml(model || "—") + '</span></div>';
    if (kind === "request") {
      var srcLabel = data.source_label || "local logs";
      html += '<div class="sd-kv"><span>来源</span><span title="' + escapeHtml(srcLabel) + '">' + escapeHtml(srcLabel) + '</span></div>';
      var callIdVal = data.call_id || "";
      html += '<div class="sd-kv"><span>Call ID</span><span title="' + escapeHtml(callIdVal || "—") + '">' + escapeHtml(callIdVal || "—") + '</span></div>';
    } else if (data.call_id) {
      html += '<div class="sd-kv"><span>Call ID</span><span title="' + escapeHtml(data.call_id) + '">' + escapeHtml(data.call_id) + '</span></div>';
    }
    html += '<div class="sd-kv"><span>请求发起</span><span title="' + escapeHtml(timing.request_at || "—") + '">' + escapeHtml(timing.request_at || "—") + '</span></div>';
    html += '<div class="sd-kv"><span>响应返回</span><span title="' + escapeHtml(timing.response_at || "—") + '">' + escapeHtml(timing.response_at || "—") + '</span></div>';
    html += '<div class="sd-kv"><span>耗时</span><span title="' + escapeHtml(timing.duration || "—") + '">' + escapeHtml(timing.duration || "—") + '</span></div>';
    html += '</div>';
    html += '</section>';
    html += '</div>';

    // ── Full-width attribution canvas ──
    html += '<div class="sd-payload-shell sd-payload-shell--attribution">';
    html += '<main class="sd-payload-main sd-attribution-canvas">';

    var buckets = data.buckets || [];
    if (buckets.length > 0) {
      // Distribution bar
      html += '<div class="sd-attribution-section-label">用量分布</div>';
      html += '<div class="sd-attribution-distribution__bar">';
      var residualKeys = { "unlocated_residual": true, "unknown_overhead": true, "unknown": true };
      var isResidualBucket = function (b) { return !!(b && residualKeys[b.key]); };
      var contributingBuckets = buckets.filter(function (b) { return b.contributes_to_total !== false && !isResidualBucket(b); });
      var totalForPct = 0;
      contributingBuckets.forEach(function (b) { totalForPct += (b.tokens || 0); });
      var residualBucket = buckets.find(isResidualBucket);
      var grandTotal = totalForPct + (residualBucket ? (residualBucket.tokens || 0) : 0);
      var denominatorLabel = "分母 = " + formatCompactToken(grandTotal);
      if (kind === "request") {
        var requestInputDenominator = coverageRequestContentTotal || numericValue(freshInput);
        if (requestInputDenominator > 0) {
          grandTotal = requestInputDenominator;
          denominatorLabel = "分母 Fresh = " + formatCompactToken(requestInputDenominator) + "；Cache Read 仅在摘要中作为 provider accounting 展示";
        }
      }
      contributingBuckets.forEach(function (b) {
        var pct = grandTotal > 0 ? (b.tokens / grandTotal * 100) : 0;
        var widthPct = Math.max(0, Math.min(100, pct));
        var colorIdx = getBucketColorIndex(b.color_key || b.canonical_key || b.key);
        html += '<div class="sd-attribution-distribution__segment sd-attribution-segment--' + colorIdx + '" style="width:' + widthPct.toFixed(1) + '%;flex:0 0 ' + widthPct.toFixed(1) + '%" title="' + escapeHtml(b.label) + ': ' + b.tokens + ' tokens · ' + pct.toFixed(1) + '%"></div>';
      });
      if (kind !== "request" && residualBucket && residualBucket.tokens > 0) {
        var unkPct2 = grandTotal > 0 ? (residualBucket.tokens / grandTotal * 100) : 0;
        html += '<div class="sd-attribution-distribution__segment sd-attribution-segment--8" style="width:' + Math.min(100, unkPct2).toFixed(1) + '%;flex:0 0 ' + Math.min(100, unkPct2).toFixed(1) + '%" title="' + escapeHtml(residualBucket.label) + ': ' + residualBucket.tokens + ' tokens · ' + unkPct2.toFixed(1) + '%"></div>';
      }
      html += '</div>';
      html += '<div class="sd-attribution-distribution__note">' + escapeHtml(denominatorLabel) + '</div>';

      // Bucket cards (expandable)
      html += '<div class="sd-attribution-section-label">贡献来源</div>';
      html += '<div class="sd-attribution-bucket-list">';
      buckets.forEach(function (b) {
        var idx = getBucketColorIndex(b.color_key || b.canonical_key || b.key);
        var hasDetails = bucketHasDetails(b);
        var isChild = b.contributes_to_total === false && b.parent_key;

        if (isChild) return; // skip child buckets from top-level list

        html += '<div class="sd-attribution-bucket-card' + (hasDetails ? ' is-expandable' : '') + '" data-bucket-key="' + escapeHtml(b.key) + '" data-canonical-key="' + escapeHtml(b.canonical_key || b.key) + '" data-color-key="' + escapeHtml(b.color_key || b.canonical_key || b.key) + '" data-bucket-label="' + escapeHtml(b.label || b.key) + '">';
        html += '<div class="sd-attribution-bucket-head"' + (hasDetails ? ' data-bucket-toggle aria-expanded="false"' : '') + '>';
        html += '<span class="sd-attribution-bucket-dot sd-attribution-bucket-dot--' + idx + '"></span>';
        html += '<span class="sd-attribution-bucket-label">' + escapeHtml(b.label || b.key) + '</span>';
        if (b.count_label) {
          html += '<span class="sd-attribution-bucket-count">' + escapeHtml(b.count_label) + '</span>';
        }
        // Merge tokens + %
        html += '<span class="sd-attribution-bucket-usage">' + formatCompactToken(b.tokens) + '（' + (b.percent || 0).toFixed(1) + '%）</span>';
        html += '<span class="sd-precision-tag sd-precision-tag--' + escapeHtml(b.precision || "") + '">' + translatePrecision(b.precision) + '</span>';
        if (hasDetails) {
          html += '<span class="sd-attribution-bucket-chevron">▾</span>';
        }
        html += '</div>'; // end bucket-head

        if (hasDetails) {
          var detailKind = (b.details && b.details.kind) ? b.details.kind : "";
          html += '<div class="sd-attribution-bucket-body" hidden' +
            (detailKind ? ' data-bucket-detail-kind="' + escapeHtml(detailKind) + '"' : '') + '>';
          html += renderBucketDetails(b);
          html += '</div>'; // end bucket-body
        }

        html += '</div>'; // end bucket-card
      });
      html += '</div>'; // end bucket-list
    }

    // ── v2 Ordered API Spans ──
    if (orderedSpans.length > 0) {
      html += '<div class="sd-attribution-section-label">有序 API 片段 (' + orderedSpans.length + ')</div>';
      html += '<div class="sd-attribution-span-list">';
      orderedSpans.forEach(function (s) {
        html += '<div class="sd-attribution-span-row">';
        html += '<span class="sd-attribution-span-index">' + (s.order_index != null ? s.order_index : '') + '</span>';
        html += '<span class="sd-attribution-span-kind">' + escapeHtml(s.semantic_kind || "") + '</span>';
        html += '<span class="sd-attribution-span-path" title="' + escapeHtml(s.api_path || "") + '">' + escapeHtml((s.api_path || "").substring(0, 40)) + '</span>';
        html += '<span class="sd-attribution-span-tokens">' + formatCompactToken(s.tokens || s.token_estimate || 0) + 't</span>';
        if (s.cache_read_tokens) html += '<span class="sd-attribution-span-cr" title="cache read">CR:' + s.cache_read_tokens + '</span>';
        if (s.cache_write_tokens) html += '<span class="sd-attribution-span-cw" title="cache write">CW:' + s.cache_write_tokens + '</span>';
        if (s.fresh_tokens) html += '<span class="sd-attribution-span-fresh" title="fresh">F:' + s.fresh_tokens + '</span>';
        if (s.precision) html += '<span class="sd-precision-tag sd-precision-tag--' + escapeHtml(s.precision) + '">' + translatePrecision(s.precision) + '</span>';
        html += '</div>';
      });
      html += '</div>';
    }

    // ── v2 Credit Summary (Qoder) ──
    if (creditSummary) {
      html += '<div class="sd-attribution-section-label">Credit 归因</div>';
      html += '<div class="sd-attribution-credit">';
      if (creditSummary.total_credits != null) {
        html += '<div class="sd-kv"><span>Total Credits</span><span>' + creditSummary.total_credits.toFixed(2) + '</span></div>';
      }
      if (creditSummary.credit_source) {
        html += '<div class="sd-kv"><span>来源</span><span>' + escapeHtml(creditSummary.credit_source) + '</span></div>';
      }
      if (creditSummary.notes && creditSummary.notes.length > 0) {
        html += '<div class="sd-attribution-credit-notes">' + creditSummary.notes.map(function (n) { return escapeHtml(n); }).join("<br>") + '</div>';
      }
      html += '</div>';
    }

    // ── v2 Diagnostics Warnings ──
    if (diagnostics && diagnostics.warnings && diagnostics.warnings.length > 0) {
      html += '<div class="sd-attribution-section-label">诊断警告</div>';
      html += '<ul class="sd-attribution-warnings">';
      diagnostics.warnings.forEach(function (w) {
        html += '<li>' + escapeHtml(w) + '</li>';
      });
      html += '</ul>';
    }

    html += '</main>'; // end right main
    html += '</div>'; // end two-column shell

    setHtml(body, html);
  }

  // ── Bucket detail renderer ──

  function renderBucketDetails(b) {
    var leaves = normalizeBucketLeafItems(b);
    if (!leaves.length) return '<div class="sd-bucket-detail-empty">无详细信息</div>';
    var html = '<div class="sd-bucket-leaf-list">';
    leaves.forEach(function (leaf) {
      html += renderBucketLeafCard(leaf);
    });
    html += '</div>';
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

  /** Dynamically load bucket detail content from backend API. */
  function loadBucketDetailDynamic(modal, bodyEl, roundIdx, bucketKey) {
    // Skip if already loaded
    if (bodyEl.getAttribute("data-bucket-detail-loaded") === "1") return;

    var pageInfo = _getPageSourceAndSessionId();
    var source = pageInfo.source;
    var sessionId = pageInfo.sessionId;

    // Use modal-stored values as fallback
    if (!source && modal) source = modal.getAttribute("data-bucket-detail-source") || "";
    if (!sessionId && modal) sessionId = modal.getAttribute("data-bucket-detail-session-id") || "";

    if (!source || !sessionId) return;

    var apiUrl = "/api/sessions/" + encodeURIComponent(source) + "/" +
      encodeURIComponent(sessionId) + "/bucket-detail/" + roundIdx + "/" + bucketKey;

    // Show loading state
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
      "residual": "残余",
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
      "tool_schemas": "sd-attribution-segment--schema",
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

    // Extract round_index from payloadId for bucket-detail API
    var payloadId = button.getAttribute("data-payload-id") || "";
    var roundIdx = "";
    var rm = payloadId.match(/^llm-R(\d+)-IX(\d+)-/);
    if (rm) roundIdx = rm[1];

    var cacheKey = url;
    var modal = ensurePayloadModal();
    if (roundIdx) modal.setAttribute("data-bucket-detail-round", roundIdx);

    // Store session source for bucket-detail API
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
          // If the server returned a structured attribution error payload,
          // render it directly instead of falling through to the generic catch.
          if (errData && errData.kind === "llm.attribution_error") {
            renderAttributionError(body, errData, url);
            modal.setAttribute("data-attribution-state", "error");
            if (subtitleEl) subtitleEl.textContent = "error";
            return true;
          }
          // For other server errors (NotFound, etc.), also try to surface the message.
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
