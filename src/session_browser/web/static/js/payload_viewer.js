/**
 * payload_viewer.js — Full Payload Viewer (Task 12)
 *
 * Parts switching + View switching + JSON syntax highlighting.
 * All resources local — no external dependencies.
 */
(function () {
  'use strict';

  var PayloadViewer = {
    _currentPart: null,
    _currentView: 'json',
    _data: {},
  };

  /* ── JSON Syntax Highlighting ─────────────────────────────── */
  function highlightJSON(jsonStr) {
    if (!jsonStr) return '<span class="warn">null</span>';
    try {
      var parsed = JSON.parse(jsonStr);
      var formatted = JSON.stringify(parsed, null, 2);
    } catch (e) {
      // Not valid JSON — escape and return as-is
      return escapeHtml(jsonStr);
    }
    // Highlight: keys = blue, strings = green, null/bool = yellow, numbers = cyan
    return formatted
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"([^"\\]*(?:\\.[^"\\]*)*)"\s*:/g, '<span class="key">"$1"</span>:')
      .replace(/:\s*"([^"\\]*(?:\\.[^"\\]*)*)"/g, ': <span class="str">"$1"</span>')
      .replace(/:\s*(null|true|false)/g, ': <span class="warn">$1</span>')
      .replace(/:\s*(-?\d+\.?\d*)/g, ': <span class="num">$1</span>');
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /* ── Format bytes ─────────────────────────────────────────── */
  function formatBytes(bytes) {
    if (bytes == null || isNaN(bytes)) return '—';
    if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return bytes + ' B';
  }

  /* ── Register a payload viewer instance ───────────────────── */
  // Usage: PayloadViewer.register(containerEl, { parts: { request: { raw, json, rendered }, ... } })
  PayloadViewer.register = function (containerEl, data) {
    containerEl._viewerData = data;

    // Part switching
    var parts = containerEl.querySelectorAll('.viewer-side .part');
    for (var i = 0; i < parts.length; i++) {
      (function (part) {
        part.addEventListener('click', function () {
          var partName = this.getAttribute('data-payload-part');
          switchPart(containerEl, partName);
        });
      })(parts[i]);
    }

    // View switching
    var views = containerEl.querySelectorAll('.view-switch button[data-payload-switch]');
    for (var i = 0; i < views.length; i++) {
      (function (btn) {
        btn.addEventListener('click', function () {
          var viewName = this.getAttribute('data-payload-switch');
          switchView(containerEl, viewName);
        });
      })(views[i]);
    }

    // Initialize first part
    var firstPart = containerEl.querySelector('.viewer-side .part');
    if (firstPart) {
      switchPart(containerEl, firstPart.getAttribute('data-payload-part'));
    }
  };

  function switchPart(containerEl, partName) {
    var data = containerEl._viewerData;
    if (!data || !data.parts || !data.parts[partName]) return;

    // Update part nav
    var parts = containerEl.querySelectorAll('.viewer-side .part');
    for (var i = 0; i < parts.length; i++) {
      parts[i].classList.toggle('active', parts[i].getAttribute('data-payload-part') === partName);
    }

    containerEl._currentPart = partName;
    var partData = data.parts[partName];

    // Populate views
    var jsonView = containerEl.querySelector('[data-payload-view="json"]');
    var renderedView = containerEl.querySelector('[data-payload-view="rendered"]');
    var rawView = containerEl.querySelector('[data-payload-view="raw"]');

    if (jsonView) {
      if (partData.json) {
        jsonView.innerHTML = '<pre class="code">' + highlightJSON(partData.json) + '</pre>';
      } else if (partData.raw) {
        jsonView.innerHTML = '<pre class="code">' + highlightJSON(partData.raw) + '</pre>';
      } else {
        jsonView.innerHTML = '<pre class="code">' + highlightJSON(JSON.stringify({ message: 'No data available', part: partName }, null, 2)) + '</pre>';
      }
    }

    if (renderedView) {
      if (partData.rendered) {
        renderedView.innerHTML = partData.rendered;
      } else if (partData.raw) {
        renderedView.innerHTML = '<pre class="code">' + escapeHtml(partData.raw) + '</pre>';
      } else {
        renderedView.innerHTML = '<div class="unavailable">No rendered content for this part.</div>';
      }
    }

    if (rawView) {
      if (partData.raw) {
        rawView.innerHTML = '<pre class="code">' + escapeHtml(partData.raw) + '</pre>';
      } else {
        rawView.innerHTML = '<pre class="code">' + highlightJSON(JSON.stringify({ message: 'No raw data', part: partName }, null, 2)) + '</pre>';
      }
    }

    // Show/hide payload-unavailable badge
    var badge = containerEl.querySelector('.payload-unavailable');
    if (badge) {
      var hasData = partData.raw || partData.json || partData.rendered;
      badge.style.display = hasData ? 'none' : '';
    }

    // Reset to current view
    switchView(containerEl, containerEl._currentView || 'json');
  }

  function switchView(containerEl, viewName) {
    containerEl._currentView = viewName;

    var views = containerEl.querySelectorAll('[data-payload-view]');
    for (var i = 0; i < views.length; i++) {
      views[i].style.display = views[i].getAttribute('data-payload-view') === viewName ? '' : 'none';
    }

    var btns = containerEl.querySelectorAll('.view-switch button[data-payload-switch]');
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle('active', btns[i].getAttribute('data-payload-switch') === viewName);
    }
  }

  // Auto-init: find all .viewer-shell[data-viewer="payload"] on DOMContentLoaded
  function initAll() {
    var shells = document.querySelectorAll('.viewer-shell[data-viewer="payload"]');
    for (var i = 0; i < shells.length; i++) {
      (function (shell) {
        // Build data from hidden templates or inline script
        var dataEl = shell.querySelector('script[type="application/json"][data-viewer-data]');
        if (dataEl) {
          try {
            var data = JSON.parse(dataEl.textContent);
            PayloadViewer.register(shell, data);
          } catch (e) {
            console.error('PayloadViewer: failed to parse data', e);
          }
        }
      })(shells[i]);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }

  // Expose globally
  window.PayloadViewer = PayloadViewer;
  window.switchViewerPart = switchPart;
  window.switchViewerView = switchView;

  /* ── Full payload viewer overlay ───────────────────────────── */
  window.openFullPayloadViewer = function (payload) {
    if (!payload) return;

    // Remove existing overlay
    var existing = document.querySelector('.payload-viewer-overlay');
    if (existing) existing.remove();

    var pld = payload.payload || {};
    var requestRaw = pld.requestRaw || payload.request_payload_raw || '';
    var responseRaw = pld.responseRaw || payload.response_payload_raw || '';
    var renderedCtxRaw = payload.rendered_context_raw || requestRaw;
    var contentParts = pld.contentParts || payload.content_parts || [];

    // Build parts data for PayloadViewer.register
    var partsData = {
      parts: {
        request: { raw: requestRaw, json: '', rendered: '' },
        rendered: { raw: renderedCtxRaw, json: '', rendered: '' },
        response: { raw: responseRaw, json: '', rendered: '' },
      }
    };
    // Add sizes
    partsData.parts.request.size = requestRaw ? requestRaw.length : 0;
    partsData.parts.rendered.size = renderedCtxRaw ? renderedCtxRaw.length : 0;
    partsData.parts.response.size = responseRaw ? responseRaw.length : 0;

    // Create overlay
    var overlay = document.createElement('div');
    overlay.className = 'payload-viewer-overlay';
    overlay.innerHTML =
      '<div class="overlay-backdrop">' +
        '<div class="overlay-shell">' +
          '<div class="overlay-head">' +
            '<span class="overlay-title">Full Payload Viewer — ' + escapeHtml(payload.objectType || 'unknown') + '</span>' +
            '<button class="overlay-close" onclick="window.closeFullPayloadViewer()" aria-label="Close">&times;</button>' +
          '</div>' +
          '<div class="viewer-shell" data-viewer="payload">' +
            '<aside class="viewer-side">' +
              '<div class="nav-label">Parts</div>' +
              (requestRaw ? '<div class="part active" data-payload-part="request"><span>Request Payload</span><span class="mono">' + formatBytes(partsData.parts.request.size) + '</span></div>' : '') +
              (renderedCtxRaw ? '<div class="part" data-payload-part="rendered"><span>Rendered Context</span><span class="mono">' + formatBytes(partsData.parts.rendered.size) + '</span></div>' : '') +
              (responseRaw ? '<div class="part" data-payload-part="response"><span>Response Payload</span><span class="mono">' + formatBytes(partsData.parts.response.size) + '</span></div>' : '') +
              (contentParts.length > 0 ? '<div class="part" data-payload-part="tools"><span>Multipart (' + contentParts.length + ')</span><span class="mono">' + contentParts.length + '</span></div>' : '') +
            '</aside>' +
            '<main class="viewer-main">' +
              '<div class="viewer-toolbar"><div class="view-switch">' +
                '<button class="active" data-payload-switch="json">JSON</button>' +
                '<button data-payload-switch="rendered">Rendered</button>' +
                '<button data-payload-switch="raw">Raw</button>' +
              '</div></div>' +
              '<div class="viewer-content">' +
                '<div data-payload-view="json" style="padding:12px"><pre class="code">' + escapeHtml(requestRaw || 'No request payload.') + '</pre></div>' +
                '<div data-payload-view="rendered" style="display:none;padding:12px"><pre class="code">' + escapeHtml(renderedCtxRaw || 'No rendered context.') + '</pre></div>' +
                '<div data-payload-view="raw" style="display:none;padding:12px"><pre class="code">' + escapeHtml(responseRaw || 'No response payload.') + '</pre></div>' +
              '</div>' +
            '</main>' +
          '</div>' +
        '</div>' +
      '</div>';

    document.body.appendChild(overlay);

    // Init PayloadViewer
    var shell = overlay.querySelector('.viewer-shell[data-viewer="payload"]');
    if (shell) {
      PayloadViewer.register(shell, partsData);
    }
  };

  window.closeFullPayloadViewer = function () {
    var overlay = document.querySelector('.payload-viewer-overlay');
    if (overlay) overlay.remove();
  };

  // Close on Escape
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      window.closeFullPayloadViewer();
    }
  });
})();
