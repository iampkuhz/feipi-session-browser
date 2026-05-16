/**
 * inspector.js — Context Inspector (Task 11: 3-tab simplified)
 *
 * Provides Inspector.open(payload) / Inspector.close() / Inspector.switchTab(tabName).
 * Payload contract: { objectType, objectId, subtitle, overview: { metadata, warnings }, payload: { requestRaw, responseRaw, contentParts, missingReason }, tools: [...] }
 */
(function () {
  'use strict';

  var Inspector = {
    _currentTab: 'overview',
    _payload: null,
  };

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  Inspector.open = function (payload) {
    if (!payload) return;
    Inspector._payload = payload;

    var panel = document.querySelector('.inspector');
    if (!panel) return;

    // Update title/subtitle
    var titleEl = document.getElementById('insp-title');
    if (titleEl) titleEl.textContent = payload.title || 'Context Inspector';

    var subEl = document.getElementById('insp-sub');
    if (subEl) subEl.textContent = payload.subtitle || 'selected object';

    // Hide empty state, show tabs
    var emptyState = document.getElementById('insp-empty-state');
    if (emptyState) emptyState.style.display = 'none';

    var tabsEl = document.getElementById('insp-tabs');
    if (tabsEl) tabsEl.style.display = '';

    // Reset to overview tab
    Inspector._currentTab = 'overview';
    Inspector._renderTabContent();

    // Ensure inspector is visible (remove hide-right if set)
    document.body.classList.remove('hide-right');
  };

  Inspector.close = function () {
    // Reset to empty state
    var titleEl = document.getElementById('insp-title');
    if (titleEl) titleEl.textContent = 'Context Inspector';
    var subEl = document.getElementById('insp-sub');
    if (subEl) subEl.textContent = 'selected object=round/span/call';
    var emptyState = document.getElementById('insp-empty-state');
    if (emptyState) emptyState.style.display = '';
    var tabsEl = document.getElementById('insp-tabs');
    if (tabsEl) tabsEl.style.display = 'none';
    var contentEl = document.getElementById('insp-tab-content');
    if (contentEl) contentEl.innerHTML = '';
    Inspector._payload = null;
  };

  Inspector.switchTab = function (tabName) {
    Inspector._currentTab = tabName;
    // Update tab buttons
    var tabsEl = document.getElementById('insp-tabs');
    if (tabsEl) {
      var btns = tabsEl.querySelectorAll('button[data-tab]');
      for (var i = 0; i < btns.length; i++) {
        btns[i].classList.toggle('active', btns[i].getAttribute('data-tab') === tabName);
      }
    }
    Inspector._renderTabContent();
  };

  Inspector._renderTabContent = function () {
    var contentEl = document.getElementById('insp-tab-content');
    if (!contentEl) return;
    var payload = Inspector._payload;
    if (!payload) return;

    switch (Inspector._currentTab) {
      case 'overview':
        contentEl.innerHTML = Inspector._renderOverview(payload);
        break;
      case 'payload':
        contentEl.innerHTML = Inspector._renderPayload(payload);
        break;
      case 'tools':
        contentEl.innerHTML = Inspector._renderTools(payload);
        break;
    }
  };

  Inspector._renderOverview = function (payload) {
    var overview = payload.overview || {};
    var metadata = overview.metadata || {};
    var warnings = overview.warnings ? overview.warnings.slice() : [];

    // Auto-detect payload visibility mismatch
    var inputTokens = parseInt(metadata['Input tokens'] ? (typeof metadata['Input tokens'] === 'object' ? metadata['Input tokens'].value : metadata['Input tokens']) : '0') || 0;
    var pld = payload.payload || {};
    var requestRaw = pld.requestRaw || payload.request_payload_raw || '';
    var renderedCtxRaw = payload.rendered_context_raw || requestRaw;
    if (inputTokens > 0 && (!renderedCtxRaw || renderedCtxRaw === '')) {
      warnings.push('Input tokens exist, but rendered context is empty.');
    }

    var html = '';

    // Object type pill
    html += '<div class="object-pill">Selected Object · ' + escapeHtml(payload.objectType || 'unknown') + '</div>';

    // Scope note
    html += '<div class="scope-note">Inspector shows context for the selected round, call, or span.</div>';

    // Metadata panel
    html += '<div class="panel">';
    html += '<div class="panel-h">Metadata</div>';
    html += '<div class="panel-b"><div class="kv">';
    for (var key in metadata) {
      var val = typeof metadata[key] === 'object' ? metadata[key].value : metadata[key];
      var mono = typeof metadata[key] === 'object' && metadata[key].mono ? ' class="mono"' : '';
      html += '<div class="kv-row">' +
        '<span class="kv-k">' + escapeHtml(key) + '</span>' +
        '<span class="kv-v"' + mono + '>' + escapeHtml(val) + '</span>' +
        '</div>';
    }
    html += '</div></div></div>';

    // Warnings
    if (warnings.length > 0) {
      html += '<div class="warnbox">';
      for (var i = 0; i < warnings.length; i++) {
        html += '<div class="warn-item">' + escapeHtml(warnings[i]) + '</div>';
      }
      html += '</div>';
    }

    return html;
  };

  Inspector._renderPayload = function (payload) {
    var pld = payload.payload || {};
    var html = '';

    // "Open full viewer" entry
    html += '<div style="margin-bottom:8px">';
    html += '<button onclick="window.openFullPayloadViewer && window.openFullPayloadViewer(window.Inspector._payload)" style="font-size:11px;padding:4px 10px;border-radius:6px;border:1px solid var(--line);background:#fff;cursor:pointer;color:var(--t1)">Open full viewer</button>';
    html += '</div>';

    // Fallback to legacy field names for data consistency with Full Payload Viewer parts
    var requestRaw = pld.requestRaw || payload.request_payload_raw || '';
    var responseRaw = pld.responseRaw || payload.response_payload_raw || '';
    var contentParts = pld.contentParts || payload.content_parts || [];
    var renderedCtxRaw = payload.rendered_context_raw || requestRaw;
    var renderedCtxLen = payload.rendered_context_length || (renderedCtxRaw ? renderedCtxRaw.length : 0);
    var renderedCtxMissing = payload.rendered_context_missing_reason || (!renderedCtxRaw ? 'No rendered context available.' : '');
    var reqMissingReason = payload.request_payload_missing_reason || '';
    var respMissingReason = payload.response_payload_missing_reason || '';
    var toolCallsRaw = payload.tool_calls_raw || '';

    // ── Rendered Context part ──
    if (renderedCtxRaw) {
      html += '<div class="inspector-sub-viewer">';
      html += '<div class="inspector-sub-viewer__header">Rendered Context (' + renderedCtxLen + ' chars)</div>';
      html += '<div class="viewer viewer--raw">';
      html += '<div class="viewer__raw"><pre class="viewer__raw-pre">' + escapeHtml(renderedCtxRaw) + '</pre></div>';
      html += '</div></div>';
    } else if (renderedCtxMissing) {
      html += '<div class="inspector-sub-viewer">';
      html += '<div class="inspector-sub-viewer__header">Rendered Context</div>';
      html += '<div class="unavailable">' + escapeHtml(renderedCtxMissing) + '</div>';
      html += '</div>';
    }

    // ── Request Payload part ──
    if (requestRaw) {
      html += '<div class="inspector-sub-viewer">';
      html += '<div class="inspector-sub-viewer__header inspector-sub-viewer__header--mt">Request Payload</div>';
      html += '<div class="viewer viewer--raw">';
      html += '<div class="viewer__raw"><pre class="viewer__raw-pre">' + escapeHtml(requestRaw) + '</pre></div>';
      html += '</div></div>';
    } else if (reqMissingReason) {
      html += '<div class="inspector-sub-viewer">';
      html += '<div class="inspector-sub-viewer__header inspector-sub-viewer__header--mt">Request Payload</div>';
      html += '<div class="unavailable">' + escapeHtml(reqMissingReason) + '</div>';
      html += '</div>';
    }

    // ── Response Payload part ──
    if (responseRaw) {
      html += '<div class="inspector-sub-viewer">';
      html += '<div class="inspector-sub-viewer__header inspector-sub-viewer__header--mt">Response Payload</div>';
      html += '<div class="viewer viewer--raw">';
      html += '<div class="viewer__raw"><pre class="viewer__raw-pre">' + escapeHtml(responseRaw) + '</pre></div>';
      html += '</div></div>';
    } else if (respMissingReason) {
      html += '<div class="inspector-sub-viewer">';
      html += '<div class="inspector-sub-viewer__header inspector-sub-viewer__header--mt">Response Payload</div>';
      html += '<div class="unavailable">' + escapeHtml(respMissingReason) + '</div>';
      html += '</div>';
    }

    // ── Multipart Context (from content_parts) ──
    if (contentParts.length > 0) {
      html += '<div class="inspector-sub-viewer">';
      html += '<div class="inspector-sub-viewer__header inspector-sub-viewer__header--mt">Multipart Context (' + contentParts.length + ' parts)</div>';
      for (var i = 0; i < contentParts.length; i++) {
        var part = contentParts[i];
        var partContent = typeof part.content === 'string' ? part.content : JSON.stringify(part.content, null, 2);
        html += '<div class="viewer__part-header">';
        html += '<span class="viewer__part-title">' + escapeHtml(part.title || part.context_type) + '</span>';
        if (part.content_bytes) {
          var bytes = part.content_bytes;
          var label = bytes > 1024 * 1024 ? (bytes / (1024 * 1024)).toFixed(1) + ' MB' :
                       bytes > 1024 ? (bytes / 1024).toFixed(1) + ' KB' : bytes + ' B';
          html += '<span class="viewer__part-size">' + label + '</span>';
        }
        html += '</div>';
        html += '<div class="viewer viewer--raw">';
        html += '<div class="viewer__raw"><pre class="viewer__raw-pre">' + escapeHtml(partContent) + '</pre></div>';
        html += '</div>';
      }
      html += '</div>';
    }

    // ── Fallback when nothing available ──
    if (!requestRaw && !responseRaw && contentParts.length === 0 && !renderedCtxRaw && !reqMissingReason && !respMissingReason && !renderedCtxMissing) {
      html += '<div class="unavailable">' + escapeHtml(pld.missingReason || 'No payload data available.') + '</div>';
    }

    return html;
  };

  Inspector._renderTools = function (payload) {
    var tools = payload.tools || [];
    if (tools.length === 0) {
      return '<div class="empty-state"><div class="empty-state__icon">⊹</div><div class="empty-state__title">No tool calls</div><div class="empty-state__desc">This call did not invoke any tools.</div></div>';
    }
    var html = '<div class="tool-calls-list">';
    for (var i = 0; i < tools.length; i++) {
      var tc = tools[i];
      html += '<div class="tool-call-card">';
      html += '<div class="tool-call-header">';
      html += '<strong>' + escapeHtml(tc.name) + '</strong>';
      html += '<span class="tool-call-status ' + (tc.is_failed ? 'failed' : 'ok') + '">' + (tc.is_failed ? 'failed' : 'ok') + '</span>';
      html += '</div>';
      if (tc.duration_ms) {
        html += '<div class="tool-call-meta">' + tc.duration_ms + 'ms</div>';
      }
      if (tc.parameters) {
        html += '<details class="tool-call-params"><summary>Parameters</summary><pre class="mono text-xs">' + escapeHtml(typeof tc.parameters === 'string' ? tc.parameters : JSON.stringify(tc.parameters, null, 2)) + '</pre></details>';
      }
      if (tc.result_preview) {
        html += '<details class="tool-call-result"><summary>Result</summary><pre class="mono text-xs">' + escapeHtml(tc.result_preview) + '</pre></details>';
      }
      if (tc.is_failed && tc.error_message) {
        html += '<div class="tool-call-error">' + escapeHtml(tc.error_message) + '</div>';
      }
      html += '</div>';
    }
    html += '</div>';
    return html;
  };

  // Global exports
  window.Inspector = Inspector;
  window.openInspector = Inspector.open;
  window.closeInspector = Inspector.close;
})();
