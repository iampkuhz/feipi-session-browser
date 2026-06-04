  /* ── Attribution API fetch support ── */

  var _attributionCache = new Map();

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
    body.innerHTML = '<div class="sd-payload-error">' +
      '<h3>Attribution Load Failed</h3>' +
      '<div class="sd-error-meta">' +
      '<div class="sd-kv"><span>error_type</span><span>' + escapeHtml(errorPayload.error_type || "Unknown") + '</span></div>' +
      '<div class="sd-kv"><span>message</span><span>' + escapeHtml(errorPayload.message || "") + '</span></div>' +
      '</div>' +
      '<p>' + escapeHtml(errorPayload.fallback || "") + '</p>' +
      '<button type="button" class="sd-btn sd-btn--primary" data-action="retry-attribution">Retry</button>' +
      '</div>';
    var retryBtn = body.querySelector('[data-action="retry-attribution"]');
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        _attributionCache.delete(url);
        retryAttributionFetch(url, body);
      });
    }
  }

  function retryAttributionFetch(url, body) {
    body.innerHTML = renderAttributionLoading(url.indexOf("/request") !== -1 ? "request" : "response");
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

    // ── Call identity card (v2) ──
    if (callIdentity) {
      html += '<div class="sd-attribution-section-label">调用身份</div>';
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
    }

    // ── Two-column layout ──
    html += '<div class="sd-payload-shell sd-payload-shell--attribution">';

    // ── Left rail ──
    html += '<aside class="sd-payload-meta sd-attribution-rail">';

    // Card 1: Summary (use ~ for estimated values)
    // Support both v2 usage_summary and old usage fields
    var totalInput = usageSummary.total_input || usage.total_input;
    var freshInput = usageSummary.fresh_input || usage.fresh_input;
    var cacheRead = usageSummary.cache_read || usage.cache_read;
    var cacheWrite = usageSummary.cache_write || usage.cache_write;
    html += '<div class="sd-attribution-rail__card">';
    html += '<h3>' + (kind === "request" ? "请求摘要" : "响应摘要") + '</h3>';
    if (kind === "request") {
      html += '<div class="sd-kv"><span>总 token 消耗</span><span title="' + kvTitleAttr(totalInput) + '">' + formatTokenValue(totalInput) + '</span></div>';
      html += '<div class="sd-kv"><span>新鲜输入</span><span title="' + kvTitleAttr(freshInput) + '">' + formatTokenValue(freshInput) + '</span></div>';
      html += '<div class="sd-kv"><span>缓存读取</span><span title="' + kvTitleAttr(cacheRead) + '">' + formatTokenValue(cacheRead) + '</span></div>';
      html += '<div class="sd-kv"><span>缓存写入</span><span title="' + kvTitleAttr(cacheWrite) + '">' + formatTokenValue(cacheWrite) + '</span></div>';
      html += '<div class="sd-kv"><span>覆盖率</span><span title="' + kvTitleAttr(usage.coverage) + '">' + formatRatioValue(usage.coverage) + '</span></div>';
      var unkVal = (usage.unknown && usage.unknown.value) || 0;
      var totVal = (usage.total_input && usage.total_input.value) || 1;
      var unkPct = ((unkVal / totVal) * 100).toFixed(1);
      html += '<div class="sd-kv"><span>未定位</span><span title="' + formatCompactToken(unkVal) + '（' + unkPct + '%）">' + formatCompactToken(unkVal) + '（' + unkPct + '%）</span></div>';
    } else {
      html += '<div class="sd-kv"><span>总输出</span><span title="' + kvTitleAttr(usage.total_output) + '">' + formatTokenValue(usage.total_output) + '</span></div>';
      html += '<div class="sd-kv"><span>可见文本</span><span title="' + kvTitleAttr(usage.visible_text) + '">' + formatTokenValue(usage.visible_text) + '</span></div>';
      html += '<div class="sd-kv"><span>工具使用</span><span title="' + kvTitleAttr(usage.tool_use) + '">' + formatTokenValue(usage.tool_use) + '</span></div>';
      html += '<div class="sd-kv"><span>元数据</span><span title="' + kvTitleAttr(usage.metadata) + '">' + formatTokenValue(usage.metadata) + '</span></div>';
      html += '<div class="sd-kv"><span>覆盖率</span><span title="' + kvTitleAttr(usage.coverage) + '">' + formatRatioValue(usage.coverage) + '</span></div>';
      html += '<div class="sd-kv"><span>未定位</span><span title="' + kvTitleAttr(usage.unknown) + '">' + formatTokenValue(usage.unknown) + '</span></div>';
      if (usage.finish_reason && usage.finish_reason.value) {
        var frVal = String(usage.finish_reason.value);
        html += '<div class="sd-kv"><span>完成原因</span><span title="' + escapeHtml(frVal) + '">' + escapeHtml(frVal) + '</span></div>';
      }
    }
    html += '</div>'; // end summary card

    // Card 2: Timing
    if (timing.request_at && timing.request_at !== "—") {
      html += '<div class="sd-attribution-rail__card">';
      html += '<h3>时间线</h3>';
      html += '<div class="sd-kv"><span>请求发起</span><span title="' + escapeHtml(timing.request_at) + '">' + escapeHtml(timing.request_at) + '</span></div>';
      html += '<div class="sd-kv"><span>响应返回</span><span title="' + escapeHtml(timing.response_at || "—") + '">' + escapeHtml(timing.response_at || "—") + '</span></div>';
      html += '<div class="sd-kv"><span>耗时</span><span title="' + escapeHtml(timing.duration || "—") + '">' + escapeHtml(timing.duration || "—") + '</span></div>';
      html += '</div>'; // end timing card
    }

    // Card 3: Model + params
    if (model && model !== "unknown") {
      html += '<div class="sd-attribution-rail__card">';
      html += '<h3>模型信息</h3>';
      html += '<div class="sd-kv"><span>模型</span><span title="' + escapeHtml(model) + '">' + escapeHtml(model) + '</span></div>';
      if (kind === "request") {
        var srcLabel = data.source_label || "local logs";
        html += '<div class="sd-kv"><span>来源</span><span title="' + escapeHtml(srcLabel) + '">' + escapeHtml(srcLabel) + '</span></div>';
      }
      html += '</div>';
    }

    // Card 4: Request params (request only)
    if (kind === "request") {
      html += '<div class="sd-attribution-rail__card">';
      html += '<h3>请求参数</h3>';
      var callIdVal = data.call_id || "";
      html += '<div class="sd-kv"><span>Call ID</span><span title="' + escapeHtml(callIdVal) + '">' + escapeHtml(callIdVal) + '</span></div>';
      html += '</div>';
    }

    html += '</aside>'; // end left rail

    // ── Right main content ──
    html += '<main class="sd-payload-main sd-attribution-canvas">';

    var buckets = data.buckets || [];
    if (buckets.length > 0) {
      // Distribution bar
      html += '<div class="sd-attribution-section-label">用量分布</div>';
      html += '<div class="sd-attribution-distribution__bar">';
      var contributingBuckets = buckets.filter(function (b) { return b.contributes_to_total !== false && b.key !== "unlocated_residual" && b.key !== "unknown_overhead" && b.key !== "unknown"; });
      var totalForPct = 0;
      contributingBuckets.forEach(function (b) { totalForPct += (b.tokens || 0); });
      var residualBucket = buckets.find(function (b) { return b.key === "unlocated_residual" || b.key === "unknown_overhead" || b.key === "unknown"; });
      var grandTotal = totalForPct + (residualBucket ? (residualBucket.tokens || 0) : 0);
      contributingBuckets.forEach(function (b) {
        var pct = grandTotal > 0 ? (b.tokens / grandTotal * 100) : 0;
        var colorIdx = getBucketColorIndex(b.key);
        html += '<div class="sd-attribution-distribution__segment sd-attribution-segment--' + colorIdx + '" style="width:' + pct.toFixed(1) + '%" title="' + escapeHtml(b.label) + ': ' + b.tokens + ' tokens"></div>';
      });
      if (residualBucket && residualBucket.tokens > 0) {
        var unkPct2 = grandTotal > 0 ? (residualBucket.tokens / grandTotal * 100) : 0;
        html += '<div class="sd-attribution-distribution__segment sd-attribution-segment--7" style="width:' + unkPct2.toFixed(1) + '%" title="' + escapeHtml(residualBucket.label) + ': ' + residualBucket.tokens + ' tokens"></div>';
      }
      html += '</div>';

      // Bucket cards (expandable)
      html += '<div class="sd-attribution-section-label">贡献来源</div>';
      html += '<div class="sd-attribution-bucket-list">';
      buckets.forEach(function (b) {
        var idx = getBucketColorIndex(b.key);
        var hasDetails = b.details && (
          (b.details.items && b.details.items.length > 0) ||
          (b.details.explanation && b.details.explanation.length > 0) ||
          b.details.preview ||
          (b.details.kind === "tools" && b.details.items) ||
          (b.details.kind === "mcp_metadata" && b.details.items) ||
          (b.details.kind === "system_sources" && b.details.items) ||
          (b.details.kind === "message_history" && b.details.items) ||
          (b.details.kind === "tool_results" && b.details.items) ||
          (b.details.kind === "current_user_message") ||
          (b.details.kind === "unlocated") ||
          (b.details.kind === "hidden_estimate")
        );
        var isChild = b.contributes_to_total === false && b.parent_key;

        if (isChild) return; // skip child buckets from top-level list

        html += '<div class="sd-attribution-bucket-card" data-bucket-key="' + escapeHtml(b.key) + '">';
        html += '<div class="sd-attribution-bucket-head" data-bucket-toggle>';
        html += '<span class="sd-attribution-bucket-dot sd-attribution-bucket-dot--' + idx + '"></span>';
        html += '<span class="sd-attribution-bucket-label">' + escapeHtml(b.label || b.key) + '</span>';
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

    // ── v2 Coverage & Uncertainty ──
    if (coverage) {
      html += '<div class="sd-attribution-section-label">覆盖率与不确定性</div>';
      html += '<div class="sd-attribution-coverage">';
      html += '<div class="sd-kv"><span>Provider 总计</span><span>' + formatCompactToken(coverage.provider_total_input || 0) + '</span></div>';
      html += '<div class="sd-kv"><span>本地重建</span><span>' + formatCompactToken(coverage.reconstructed_total || 0) + '</span></div>';
      html += '<div class="sd-kv"><span>覆盖率</span><span>' + ((coverage.coverage_ratio || 0) * 100).toFixed(1) + '%</span></div>';
      html += '<div class="sd-kv"><span>残差</span><span>' + formatCompactToken(coverage.residual_tokens || 0) + '</span></div>';
      if (coverage.residual_likely_sources && coverage.residual_likely_sources.length > 0) {
        html += '<div class="sd-attribution-coverage-sources">可能来源：' + escapeHtml(coverage.residual_likely_sources.join("、")) + '</div>';
      }
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
    var d = b.details || {};
    var html = "";

    if (d.kind === "tools" && d.items) {
      html += '<div class="sd-bucket-detail-list">';
      d.items.forEach(function (item) {
        html += '<div class="sd-bucket-detail-item sd-bucket-detail-item--expandable" data-tool-detail-toggle>';
        html += '<div class="sd-bucket-detail-name">' + escapeHtml(item.name) + ' <b>' + formatCompactToken(item.estimated_tokens || 0) + 't</b></div>';
        html += '<div class="sd-bucket-detail-desc">' + escapeHtml(item.description_preview || "") + '</div>';
        html += '<div class="sd-bucket-detail-meta">';
        html += '<span>来源: ' + escapeHtml(item.source || "") + '</span>';
        html += '<span>~' + formatCompactToken(item.estimated_tokens || 0) + ' tokens</span>';
        html += '<span class="sd-bucket-detail-chevron">▸</span>';
        html += '</div>';
        // Expanded detail (hidden by default) — JSON format
        html += '<div class="sd-bucket-detail-expanded" hidden>';
        var jsonObj = {
          name: item.name || "",
          description: item.description || "",
          input_schema: item.input_schema ? (function() {
            try { return JSON.parse(item.input_schema); }
            catch(e) { return item.input_schema; }
          })() : {}
        };
        html += '<pre class="sd-bucket-detail-schema">' + escapeHtml(JSON.stringify(jsonObj, null, 2)) + '</pre>';
        html += '</div>';
        html += '</div>';
      });
      html += '</div>';
    } else if (d.kind === "tool_use" && d.items) {
      html += '<div class="sd-bucket-detail-section">';
      html += '<div class="sd-bucket-detail-meta" style="margin-bottom:8px">';
      html += '<span>定义总计: ~' + formatCompactToken(d.total_schema_tokens || 0) + ' tokens</span>';
      html += '<span>调用总计: ~' + formatCompactToken(d.total_call_tokens || 0) + ' tokens</span>';
      html += '<span>共 ' + (d.total_items || 0) + ' 个调用</span>';
      html += '</div>';
      html += '</div>';
      html += '<div class="sd-bucket-detail-list">';
      d.items.forEach(function (item) {
        html += '<div class="sd-bucket-detail-item">';
        html += '<div class="sd-bucket-detail-name">' + escapeHtml(item.name) + '</div>';
        html += '<div class="sd-bucket-detail-desc">' + escapeHtml(item.description_preview || "") + '</div>';
        html += '<div class="sd-bucket-detail-meta">';
        html += '<span>定义: ' + formatCompactToken(item.schema_tokens || 0) + ' tokens</span>';
        html += '<span>调用: ' + formatCompactToken(item.call_tokens || 0) + ' tokens</span>';
        html += '<span>合计: ' + formatCompactToken(item.total_tokens || 0) + ' tokens</span>';
        html += '</div>';
        if (item.input_schema_properties) {
          html += '<div class="sd-bucket-detail-desc" style="opacity:0.7">输入参数: ' + escapeHtml(item.input_schema_properties) + '</div>';
        }
        html += '</div>';
      });
      html += '</div>';
    } else if (d.kind === "system_sources" && d.items) {
      html += '<div class="sd-bucket-detail-list">';
      d.items.forEach(function (item) {
        html += '<div class="sd-bucket-detail-item">';
        html += '<div class="sd-bucket-detail-name">' + escapeHtml(item.file_path || "") + '</div>';
        html += '<div class="sd-bucket-detail-meta">';
        html += '<span>类型: ' + escapeHtml(item.source_type || "") + '</span>';
        if (item.tokens) html += '<span>~' + formatCompactToken(item.tokens) + ' tokens</span>';
        html += '</div>';
        if (item.preview) {
          html += '<pre class="sd-bucket-detail-preview">' + escapeHtml(item.preview) + '</pre>';
        }
        html += '</div>';
      });
      html += '</div>';
    } else if (d.kind === "message_history" && d.items) {
      html += '<div class="sd-bucket-detail-list">';
      d.items.forEach(function (item) {
        html += '<div class="sd-bucket-detail-item">';
        html += '<div class="sd-bucket-detail-meta">';
        html += '<span>第 ' + (item.round_id || "?") + ' 轮</span>';
        html += '<span>' + escapeHtml(item.role || "") + '</span>';
        if (item.tokens) html += '<span>~' + formatCompactToken(item.tokens) + ' tokens</span>';
        html += '</div>';
        html += '<div class="sd-bucket-detail-desc">' + escapeHtml(item.summary || "") + '</div>';
        html += '</div>';
      });
      html += '</div>';
    } else if (d.kind === "tool_results" && d.items) {
      html += '<div class="sd-bucket-detail-list">';
      d.items.forEach(function (item) {
        html += '<div class="sd-bucket-detail-item">';
        html += '<div class="sd-bucket-detail-name">' + escapeHtml(item.tool_name || "unknown") + '</div>';
        html += '<div class="sd-bucket-detail-desc">' + escapeHtml(item.summary || "") + '</div>';
        html += '<div class="sd-bucket-detail-meta">';
        if (item.tokens) html += '<span>~' + formatCompactToken(item.tokens) + ' tokens</span>';
        html += '</div>';
        html += '</div>';
      });
      html += '</div>';
    } else if (d.kind === "current_user_message") {
      html += '<div class="sd-bucket-detail-item">';
      if (d.tokens) html += '<div class="sd-bucket-detail-meta"><span>~' + formatCompactToken(d.tokens) + ' tokens</span></div>';
      if (d.preview) {
        html += '<pre class="sd-bucket-detail-preview sd-bucket-detail-preview--full">' + escapeHtml(d.preview) + '</pre>';
      }
      html += '</div>';
    } else if (d.kind === "mcp_metadata" && d.items) {
      html += '<div class="sd-bucket-detail-list">';
      d.items.forEach(function (item) {
        html += '<div class="sd-bucket-detail-item">';
        html += '<div class="sd-bucket-detail-name">' + escapeHtml(item.name || "") + '</div>';
        html += '<div class="sd-bucket-detail-meta"><span>~' + formatCompactToken(item.estimated_tokens || 0) + ' tokens</span></div>';
        html += '</div>';
      });
      html += '</div>';
    } else if (d.kind === "unlocated" && d.explanation) {
      html += '<ul class="sd-bucket-detail-explanation">';
      d.explanation.forEach(function (line) {
        html += '<li>' + escapeHtml(line) + '</li>';
      });
      html += '</ul>';
    } else if (d.kind === "hidden_estimate" && d.explanation) {
      html += '<ul class="sd-bucket-detail-explanation">';
      d.explanation.forEach(function (line) {
        html += '<li>' + escapeHtml(line) + '</li>';
      });
      html += '</ul>';
    } else if (d.preview) {
      html += '<pre class="sd-bucket-detail-preview">' + escapeHtml(d.preview) + '</pre>';
    } else if (d.explanation) {
      html += '<ul class="sd-bucket-detail-explanation">';
      d.explanation.forEach(function (line) {
        html += '<li>' + escapeHtml(line) + '</li>';
      });
      html += '</ul>';
    }

    return html || '<div class="sd-bucket-detail-empty">无详细信息</div>';
  }

  function getBucketColorIndex(key) {
    if (key === "unlocated_residual" || key === "unknown_overhead" || key === "unknown") return 7;
    var order = [
      "current_user_message", "preceding_tool_results", "prior_conversation_messages",
      "tool_schemas", "local_instruction_context", "agent_subagent_prompt",
      "mcp_tool_metadata", "top_level_system_estimate",
      "hidden_builtin_system_estimate",
    ];
    var idx = order.indexOf(key);
    return idx >= 0 ? (idx % 8) : 0;
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
    return escapeHtml(prefix + formatted);
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
      "preceding_tool_results": "sd-attribution-segment--tool",
      "prior_conversation_messages": "sd-attribution-segment--prior",
      "tool_schemas": "sd-attribution-segment--schema",
      "local_instruction_context": "sd-attribution-segment--local",
      "agent_subagent_prompt": "sd-attribution-segment--agent",
      "mcp_tool_metadata": "sd-attribution-segment--mcp",
      "top_level_system_estimate": "sd-attribution-segment--system",
      "hidden_builtin_system_estimate": "sd-attribution-segment--hidden",
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
