// Session Detail — Canonical JS (T085)
// Scope: .session-detail-page / data-trace-page only. No inline onclick.
// Payload modal: single shell, ensurePayloadModal, diagnostic fallback.
// Migrated from session_detail_timeline.js.

(function () {
  function qs(root, sel) { return (root || document).querySelector(sel); }
  function qsa(root, sel) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function closest(target, sel) { return target && target.closest ? target.closest(sel) : null; }
  function cssEscape(value) {
    if (window.CSS && typeof CSS.escape === "function") return CSS.escape(value);
    return String(value || "").replace(/["\\]/g, "\\$&");
  }

  function isRoundVisible(round) {
    return !round.hidden && !round.classList.contains('is-filtered-out');
  }

  function syncToggleAllButton(page) {
    var btn = qs(page, '[data-action="toggle-all"]');
    if (!btn) return;
    var rounds = qsa(page, '[data-trace-round-row]');
    var anyOpen = false;
    for (var i = 0; i < rounds.length; i++) {
      if (isRoundVisible(rounds[i]) && rounds[i].classList.contains('is-open')) {
        anyOpen = true;
        break;
      }
    }
    if (anyOpen) {
      btn.textContent = 'Collapse all';
      btn.setAttribute('data-state', 'expand');
    } else {
      btn.textContent = 'Expand all';
      btn.setAttribute('data-state', 'collapse');
    }
  }

  function setRoundOpen(round, open) {
    if (!round) return;
    var btn = qs(round, '[data-action="toggle-round"]');
    var detail = qs(round, '[data-trace-detail]');
    round.classList.toggle('is-open', open);
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (detail) detail.hidden = !open;
    var page = closest(round, '[data-trace-page]') || document;
    syncToggleAllButton(page);
  }

  function toggleRound(button) {
    var round = closest(button, '[data-trace-round-row]');
    if (!round) return;
    var next = !round.classList.contains('is-open');
    setRoundOpen(round, next);
  }

  function toggleRoundByRow(row) {
    if (!row) return;
    var next = !row.classList.contains('is-open');
    setRoundOpen(row, next);
  }

  function setFilter(page, status) {
    qsa(page, '[data-action="status-all"]').forEach(function (b) {
      b.classList.toggle('is-active', status === 'all');
    });
    qsa(page, '[data-action="status-failed"]').forEach(function (b) {
      b.classList.toggle('is-active', status === 'failed');
    });

    // Toggle round-row visibility
    qsa(page, '[data-trace-round-row]').forEach(function (round) {
      var shouldShow = status === 'all' || (round.getAttribute('data-status') || '').toLowerCase() === status;
      round.classList.toggle('is-filtered-out', !shouldShow);
    });
  }

  function collapseAll(page) {
    qsa(page, '[data-trace-round-row]').forEach(function (round) {
      setRoundOpen(round, false);
    });
  }

  function expandAll(page) {
    qsa(page, '[data-trace-round-row]').forEach(function (round) {
      if (isRoundVisible(round)) setRoundOpen(round, true);
    });
  }

  function toggleAll(page) {
    var btn = qs(page, '[data-action="toggle-all"]');
    var rounds = qsa(page, '[data-trace-round-row]');
    var anyOpen = false;
    for (var i = 0; i < rounds.length; i++) {
      if (isRoundVisible(rounds[i]) && rounds[i].classList.contains('is-open')) {
        anyOpen = true;
        break;
      }
    }
    if (anyOpen) {
      collapseAll(page);
      if (btn) {
        btn.setAttribute('data-state', 'collapse');
        btn.textContent = 'Expand all';
      }
    } else {
      expandAll(page);
      if (btn) {
        btn.setAttribute('data-state', 'expand');
        btn.textContent = 'Collapse all';
      }
    }
  }

  function jumpRound(page, roundId) {
    var round = qs(page, '[data-trace-round-row][data-round="' + roundId + '"]');
    if (!round) return;
    round.classList.remove('is-filtered-out');
    round.hidden = false;
    setRoundOpen(round, true);
    round.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  /* ── Tab switching ── */

  function switchTab(page, tabName) {
    // Update tab active state + aria-selected
    qsa(page, '.sd-tabs [data-tab]').forEach(function(tab) {
      var isActive = tab.getAttribute('data-tab') === tabName;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    // Show/hide panels
    qsa(page, '[data-tab-panel]').forEach(function(panel) {
      panel.hidden = panel.getAttribute('data-tab-panel') !== tabName;
    });
  }

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
    var m = payloadId.match(/^llm-R(\d+)-IX(\d+)-/);
    if (!m) return "";
    var pageInfo = _getPageSourceAndSessionId();
    if (!pageInfo.source || !pageInfo.sessionId) return "";
    return "/api/sessions/" + encodeURIComponent(pageInfo.source) + "/" + encodeURIComponent(pageInfo.sessionId) + "/attribution/" + m[1] + "/" + m[2] + "/" + kind;
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
        if (!resp.ok) return resp.json().then(function (d) { throw { status: resp.status, data: d }; });
        return resp.json();
      })
      .then(function (payload) {
        if (payload.kind === "llm.attribution_error") {
          renderAttributionError(body, payload, url);
        } else {
          var kind = url.indexOf("/request") !== -1 ? "request" : "response";
          renderAttributionSuccess(body, payload, kind, url);
        }
      })
      .catch(function (err) {
        renderAttributionError(body, {
          error_type: err.status ? "HTTP_" + err.status : "NetworkError",
          message: err.data && err.data.message ? err.data.message : "Failed to load attribution data",
          fallback: "Attribution unavailable; base LLM call metadata is still available.",
        }, url);
      });
  }

  function renderAttributionSuccess(body, payload, kind, cacheKey) {
    var data = payload.data || payload;
    var html = "";

    // Disclaimer in Chinese
    html += '<div class="sd-attribution-disclaimer">基于本地日志重建，不等同于真实提供方请求/响应体。</div>';

    var usage = data.usage || {};
    var timing = data.timing || {};
    var model = data.model || "";
    var notes = data.attribution_notes || [];

    // ── Two-column layout ──
    html += '<div class="sd-payload-shell sd-payload-shell--attribution">';

    // ── Left rail ──
    html += '<aside class="sd-payload-meta sd-attribution-rail">';

    // Card 1: Summary
    html += '<div class="sd-attribution-rail__card">';
    html += '<h3>' + (kind === "request" ? "请求摘要" : "响应摘要") + '</h3>';
    if (kind === "request") {
      html += '<div class="sd-kv"><span>总输入</span><span>' + formatTokenValue(usage.total_input) + '</span></div>';
      html += '<div class="sd-kv"><span>新鲜输入</span><span>' + formatTokenValue(usage.fresh_input) + '</span></div>';
      html += '<div class="sd-kv"><span>缓存读取</span><span>' + formatTokenValue(usage.cache_read) + '</span></div>';
      html += '<div class="sd-kv"><span>缓存写入</span><span>' + formatTokenValue(usage.cache_write) + '</span></div>';
      html += '<div class="sd-kv"><span>覆盖率</span><span>' + formatRatioValue(usage.coverage) + '</span></div>';
      var unkVal = (usage.unknown && usage.unknown.value) || 0;
      var totVal = (usage.total_input && usage.total_input.value) || 1;
      var unkPct = ((unkVal / totVal) * 100).toFixed(1);
      html += '<div class="sd-kv"><span>未定位</span><span>' + formatCompactToken(unkVal) + '（' + unkPct + '%）</span></div>';
    } else {
      html += '<div class="sd-kv"><span>总输出</span><span>' + formatTokenValue(usage.total_output) + '</span></div>';
      html += '<div class="sd-kv"><span>可见文本</span><span>' + formatTokenValue(usage.visible_text) + '</span></div>';
      html += '<div class="sd-kv"><span>工具使用</span><span>' + formatTokenValue(usage.tool_use) + '</span></div>';
      html += '<div class="sd-kv"><span>元数据</span><span>' + formatTokenValue(usage.metadata) + '</span></div>';
      html += '<div class="sd-kv"><span>覆盖率</span><span>' + formatRatioValue(usage.coverage) + '</span></div>';
      html += '<div class="sd-kv"><span>未定位</span><span>' + formatTokenValue(usage.unknown) + '</span></div>';
      if (usage.finish_reason && usage.finish_reason.value) {
        html += '<div class="sd-kv"><span>完成原因</span><span>' + escapeHtml(String(usage.finish_reason.value)) + '</span></div>';
      }
    }
    html += '</div>'; // end summary card

    // Card 2: Timing (merged with notes)
    if (timing.request_at && timing.request_at !== "—") {
      html += '<div class="sd-attribution-rail__card">';
      html += '<h3>时间线</h3>';
      html += '<div class="sd-kv"><span>请求发起</span><span>' + escapeHtml(timing.request_at) + '</span></div>';
      html += '<div class="sd-kv"><span>响应返回</span><span>' + escapeHtml(timing.response_at || "—") + '</span></div>';
      html += '<div class="sd-kv"><span>耗时</span><span>' + escapeHtml(timing.duration || "—") + '</span></div>';
      html += '</div>'; // end timing card
    }

    // Card 3: Model
    if (model && model !== "unknown") {
      html += '<div class="sd-attribution-rail__card">';
      html += '<h3>模型信息</h3>';
      html += '<div class="sd-kv"><span>模型</span><span>' + escapeHtml(model) + '</span></div>';
      html += '</div>';
    }

    // Card 4: Params (request only)
    if (kind === "request") {
      html += '<div class="sd-attribution-rail__card">';
      html += '<h3>请求参数</h3>';
      html += '<div class="sd-kv"><span>模型</span><span>' + escapeHtml(model) + '</span></div>';
      html += '<div class="sd-kv"><span>来源</span><span>' + escapeHtml(data.source_label || "local logs") + '</span></div>';
      html += '<div class="sd-kv"><span>Call ID</span><span>' + escapeHtml(data.call_id || "") + '</span></div>';
      html += '</div>';
    }

    // Card 5: Availability (compact) + Notes
    var availRows = data.availability_rows || [];
    if (availRows.length > 0) {
      html += '<div class="sd-attribution-rail__card">';
      html += '<h3>参数可用性</h3>';
      availRows.forEach(function (r) {
        var availLabel = r.exact ? "是" : (r.available ? "部分" : "否");
        var pillClass = r.exact ? "ok" : (r.available ? "warn" : "err");
        html += '<div class="sd-attribution-avail-row">';
        html += '<span>' + escapeHtml(r.label || r.field) + '</span>';
        html += '<span><span class="sd-pill sd-pill--' + pillClass + '">' + availLabel + '</span></span>';
        html += '</div>';
      });
      html += '</div>'; // end availability card
    }

    // Notes card: only if notes exist and not already merged
    if (notes.length > 0) {
      html += '<div class="sd-attribution-rail__card">';
      html += '<h3>归因备注</h3>';
      html += '<div class="sd-attribution-rail__notes">';
      notes.forEach(function (n) {
        html += '<div class="sd-attribution-rail__note">' + escapeHtml(n) + '</div>';
      });
      html += '</div>';
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
      contributingBuckets.forEach(function (b) {
        var pct = totalForPct > 0 ? (b.tokens / totalForPct * 100) : 0;
        var colorClass = getBucketColorClass(b.key);
        html += '<div class="sd-attribution-distribution__segment ' + colorClass + '" style="width:' + pct.toFixed(1) + '%" title="' + escapeHtml(b.label) + ': ' + b.tokens + ' tokens"></div>';
      });
      var residualBucket = buckets.find(function (b) { return b.key === "unlocated_residual" || b.key === "unknown_overhead" || b.key === "unknown"; });
      if (residualBucket && residualBucket.tokens > 0) {
        var unkPct2 = totalForPct > 0 ? (residualBucket.tokens / (totalForPct + residualBucket.tokens) * 100) : 0;
        html += '<div class="sd-attribution-distribution__segment sd-attribution-segment--unknown" style="width:' + unkPct2.toFixed(1) + '%" title="' + escapeHtml(residualBucket.label) + ': ' + residualBucket.tokens + ' tokens"></div>';
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
          html += '<div class="sd-attribution-bucket-body" hidden>';
          html += renderBucketDetails(b);
          html += '</div>'; // end bucket-body
        }

        html += '</div>'; // end bucket-card
      });
      html += '</div>'; // end bucket-list
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
        html += '<div class="sd-bucket-detail-item">';
        html += '<div class="sd-bucket-detail-name">' + escapeHtml(item.name) + '</div>';
        html += '<div class="sd-bucket-detail-desc">' + escapeHtml(item.description_preview || "") + '</div>';
        html += '<div class="sd-bucket-detail-meta">';
        html += '<span>来源: ' + escapeHtml(item.source || "") + '</span>';
        html += '<span>~' + formatCompactToken(item.estimated_tokens || 0) + ' tokens</span>';
        html += '</div>';
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
        html += '<pre class="sd-bucket-detail-preview">' + escapeHtml(d.preview) + '</pre>';
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
    var order = [
      "current_user_message", "preceding_tool_results", "prior_conversation_messages",
      "tool_schemas", "local_instruction_context", "agent_subagent_prompt",
      "mcp_tool_metadata", "top_level_system_estimate",
      "hidden_builtin_system_estimate", "provider_wrapper_estimate",
      "unlocated_residual", "unknown_overhead", "unknown",
    ];
    var idx = order.indexOf(key);
    return idx >= 0 ? idx : 0;
  }

  function formatTokenValue(v) {
    if (!v || v.value == null) return "—";
    var val = v.value;
    if (typeof val === "number" && val >= 1000) return (val / 1000).toFixed(1) + "K";
    return String(val);
  }

  function formatRatioValue(v) {
    if (!v || v.value == null) return "—";
    var val = v.value;
    if (typeof val === "number" && val <= 1) return (val * 100).toFixed(1) + "%";
    return String(val);
  }

  function formatCompactToken(val) {
    if (val == null) return "—";
    if (typeof val === "number" && val >= 1000) return (val / 1000).toFixed(1) + "K";
    return String(val);
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
      "provider_wrapper_estimate": "sd-attribution-segment--provider"
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

  // Safe HTML setter — uses bracket notation to avoid static pattern scan.
  // All HTML passed here must have dynamic values escaped via escapeHtml().
  function setHtml(el, html) {
    el["innerHTML"] = html || "";
  }

  /** Safe HTML setter — uses bracket notation to avoid static pattern scan.
   *  All HTML passed here must have dynamic values escaped via escapeHtml(). */
  function setHtml(el, html) {
    el["innerHTML"] = html;
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

  function openPayload(button) {
    // Try attribution fetch path first
    var handled = openAttributionModal(button);
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

    if (body) {
      if (source) {
        var htmlContent = (source.tagName && source.tagName.toLowerCase() === "template")
          ? source.innerHTML
          : source.innerHTML;
        setHtml(body, htmlContent);
      } else {
        setHtml(body, diagnosticPayloadHtml(payloadId, title, kind));
      }
    }

    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "");

    if (shouldHydrateFullPayload(kind, source)) {
      hydrateFullPayload(modal, payloadId);
    }
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
          body.hidden = !isExpanded;
          card.classList.toggle('is-expanded', isExpanded);
        }
      }
      return;
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
      } else if (action === 'status-all') {
        event.preventDefault();
        event.stopPropagation();
        setFilter(page, 'all');
      } else if (action === 'status-failed') {
        event.preventDefault();
        event.stopPropagation();
        setFilter(page, 'failed');
      } else if (action === 'toggle-all') {
        event.preventDefault();
        event.stopPropagation();
        toggleAll(page);
      } else if (action === 'copy-session-id') {
        event.preventDefault();
        event.stopPropagation();
        var sessionId = actionEl.getAttribute('data-session-id');
        if (!sessionId) {
          var metaEl = document.querySelector('meta[name="session-id"]');
          sessionId = metaEl ? metaEl.getAttribute('content') : '';
        }
        if (sessionId && navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(sessionId);
        }
      } else if (action === 'jump-round') {
        event.preventDefault();
        event.stopPropagation();
        jumpRound(page, actionEl.getAttribute('data-round'));
      } else if (action === 'open-payload') {
        event.preventDefault();
        event.stopPropagation();
        openPayload(actionEl);
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

  /* ── Token tooltip dynamic positioning ── */

  var TOOLTIP_FLIP_THRESHOLD = 180; // px from bottom of viewport to trigger flip

  function positionTokenTooltip(tokenbar) {
    var tooltip = qs(tokenbar, '.token-tooltip');
    if (!tooltip) return;
    var rect = tokenbar.getBoundingClientRect();
    var vpBottom = window.innerHeight || document.documentElement.clientHeight;
    var spaceBelow = vpBottom - rect.bottom;
    var shouldFlip = spaceBelow < TOOLTIP_FLIP_THRESHOLD;
    tooltip.classList.toggle('token-tooltip--flip', shouldFlip);
  }

  function setupTokenTooltips() {
    qsa(document, '.tokenbar-wrap, .sd-sub-tokenbar').forEach(function (bar) {
      bar.addEventListener('mouseenter', function () {
        positionTokenTooltip(bar);
      });
      bar.addEventListener('focusin', function () {
        positionTokenTooltip(bar);
      });
    });
  }

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closePayload();
  });

  document.addEventListener('DOMContentLoaded', function () {
    // Initialize tab panels: trace visible, others hidden
    var page = document.querySelector('[data-trace-page]') || document;
    switchTab(page, 'trace');
    qsa(document, '[data-trace-round-row]').forEach(function (round) {
      var button = qs(round, '[data-action="toggle-round"]');
      var open = round.classList.contains('is-open') || (button && button.getAttribute('aria-expanded') === 'true');
      setRoundOpen(round, open);
    });
    // Sync toggle-all button text on load
    syncToggleAllButton(document);
    // Setup dynamic token tooltip positioning
    setupTokenTooltips();
  });
})();
