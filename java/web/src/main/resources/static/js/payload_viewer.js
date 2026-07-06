/* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`* * payload_viewer.js — Full Payload Viewer (Task 12) * * Parts switching + View switching + JSON syntax highlighting. * All resources local — no external dependencies.` */
(function () {
  'use strict';

  var PayloadViewer = {
    _currentPart: null,
    _currentView: 'json',
    _data: {},
  };

  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── JSON Syntax Highlighting ───────────────────────────────` */
  function highlightJSON(jsonStr) {
    if (!jsonStr) return '<span class="warn">null</span>';
    try {
      var parsed = JSON.parse(jsonStr);
      var formatted = JSON.stringify(parsed, null, 2);
    } catch (e) {
      // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Not valid JSON — escape and return as-is`
      return escapeHtml(jsonStr);
    }
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Highlight: keys = blue, strings = green, null/bool = yellow, numbers = cyan`
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

  function clearElement(el) {
    while (el.firstChild) {
      el.removeChild(el.firstChild);
    }
  }

  function createEl(tag, attrs, children) {
    var el = document.createElement(tag);
    attrs = attrs || {};
    for (var key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue;
      if (key === 'className') {
        el.className = attrs[key];
      } else if (key === 'text') {
        el.textContent = attrs[key];
      } else if (key === 'hidden') {
        el.hidden = !!attrs[key];
      } else if (key === 'style') {
        el.setAttribute('style', attrs[key]);
      } else {
        el.setAttribute(key, attrs[key]);
      }
    }
    children = children || [];
    for (var i = 0; i < children.length; i++) {
      if (children[i]) el.appendChild(children[i]);
    }
    return el;
  }

  function codePre(text) {
    return createEl('pre', { className: 'code', text: text || '' });
  }

  function jsonDisplay(raw) {
    if (!raw) return 'null';
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch (e) {
      return String(raw);
    }
  }

  function setCodeText(container, text) {
    clearElement(container);
    container.appendChild(codePre(text));
  }

  function setUnavailable(container, text) {
    clearElement(container);
    container.appendChild(createEl('div', { className: 'unavailable', text: text }));
  }

  function appendPart(side, partName, label, size, enabled, active) {
    if (!enabled) return;
    side.appendChild(
      createEl(
        'div',
        { className: 'part' + (active ? ' active' : ''), 'data-payload-part': partName },
        [
          createEl('span', { text: label }),
          createEl('span', { className: 'mono', text: formatBytes(size) }),
        ]
      )
    );
  }

  function payloadPanel(viewName, text, hidden) {
    return createEl(
      'div',
      {
        'data-payload-view': viewName,
        style: 'padding:12px',
        hidden: hidden,
      },
      [codePre(text)]
    );
  }

  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Format bytes ───────────────────────────────────────────` */
  function formatBytes(bytes) {
    if (bytes == null || isNaN(bytes)) return '—';
    if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return bytes + ' B';
  }

  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Register a payload viewer instance ─────────────────────` */
  // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Usage: PayloadViewer.register(containerEl, { parts: { request: { raw, json, rendered }, ... } })`
  PayloadViewer.register = function (containerEl, data) {
    containerEl._viewerData = data;

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Part switching`
    var parts = containerEl.querySelectorAll('.viewer-side .part');
    for (var i = 0; i < parts.length; i++) {
      (function (part) {
        part.addEventListener('click', function () {
          var partName = this.getAttribute('data-payload-part');
          switchPart(containerEl, partName);
        });
      })(parts[i]);
    }

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`View switching`
    var views = containerEl.querySelectorAll('.view-switch button[data-action="payload-switch"]');
    for (var i = 0; i < views.length; i++) {
      (function (btn) {
        btn.addEventListener('click', function () {
          var viewName = this.getAttribute('data-payload-mode');
          switchView(containerEl, viewName);
        });
      })(views[i]);
    }

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Initialize first part`
    var firstPart = containerEl.querySelector('.viewer-side .part');
    if (firstPart) {
      switchPart(containerEl, firstPart.getAttribute('data-payload-part'));
    }
  };

  function switchPart(containerEl, partName) {
    var data = containerEl._viewerData;
    if (!data || !data.parts || !data.parts[partName]) return;

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Update part nav`
    var parts = containerEl.querySelectorAll('.viewer-side .part');
    for (var i = 0; i < parts.length; i++) {
      parts[i].classList.toggle('active', parts[i].getAttribute('data-payload-part') === partName);
    }

    containerEl._currentPart = partName;
    var partData = data.parts[partName];

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Populate views`
    var jsonView = containerEl.querySelector('[data-payload-view="json"]');
    var renderedView = containerEl.querySelector('[data-payload-view="rendered"]');
    var rawView = containerEl.querySelector('[data-payload-view="raw"]');

    if (jsonView) {
      if (partData.json) {
        setCodeText(jsonView, jsonDisplay(partData.json));
      } else if (partData.raw) {
        setCodeText(jsonView, jsonDisplay(partData.raw));
      } else {
        setCodeText(
          jsonView,
          JSON.stringify({ message: 'No data available', part: partName }, null, 2)
        );
      }
    }

    if (renderedView) {
      if (partData.rendered) {
        setCodeText(renderedView, partData.rendered);
      } else if (partData.raw) {
        setCodeText(renderedView, partData.raw);
      } else {
        setUnavailable(renderedView, 'No rendered content for this part.');
      }
    }

    if (rawView) {
      if (partData.raw) {
        setCodeText(rawView, partData.raw);
      } else {
        setCodeText(rawView, JSON.stringify({ message: 'No raw data', part: partName }, null, 2));
      }
    }

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Show/hide payload-unavailable badge`
    var badge = containerEl.querySelector('.payload-unavailable');
    if (badge) {
      var hasData = partData.raw || partData.json || partData.rendered;
      badge.hidden = hasData;
    }

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Reset to current view`
    switchView(containerEl, containerEl._currentView || 'json');
  }

  function switchView(containerEl, viewName) {
    containerEl._currentView = viewName;

    var views = containerEl.querySelectorAll('[data-payload-view]');
    for (var i = 0; i < views.length; i++) {
      views[i].hidden = views[i].getAttribute('data-payload-view') !== viewName;
    }

    var btns = containerEl.querySelectorAll('.view-switch button[data-action="payload-switch"]');
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle('active', btns[i].getAttribute('data-payload-mode') === viewName);
    }
  }

  // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Auto-init: find all .viewer-shell[data-viewer="payload"] on DOMContentLoaded`
  function initAll() {
    var shells = document.querySelectorAll('.viewer-shell[data-viewer="payload"]');
    for (var i = 0; i < shells.length; i++) {
      (function (shell) {
        // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Build data from hidden templates or inline script`
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

  // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Expose globally`
  window.PayloadViewer = PayloadViewer;
  window.switchViewerPart = switchPart;
  window.switchViewerView = switchView;

  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Full payload viewer overlay ─────────────────────────────` */
  window.openFullPayloadViewer = function (payload) {
    if (!payload) return;

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Remove existing overlay`
    var existing = document.querySelector('.payload-viewer-overlay');
    if (existing) existing.remove();

    var pld = payload.payload || {};
    var requestRaw = pld.requestRaw || payload.request_payload_raw || '';
    var responseRaw = pld.responseRaw || payload.response_payload_raw || '';
    var renderedCtxRaw = payload.rendered_context_raw || '';
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Only fall back renderedCtx to requestRaw if explicitly set (they are distinct concepts)`
    if (!renderedCtxRaw && requestRaw) {
      renderedCtxRaw = requestRaw;
    }
    var contentParts = pld.contentParts || payload.content_parts || [];

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Determine whether any payload data is actually available`
    var hasAnyData = !!(requestRaw || responseRaw || renderedCtxRaw || (contentParts && contentParts.length > 0));

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Build parts data for PayloadViewer.register`
    var partsData = {
      parts: {
        request: { raw: requestRaw || '', json: '', rendered: '' },
        rendered: { raw: renderedCtxRaw || '', json: '', rendered: '' },
        response: { raw: responseRaw || '', json: '', rendered: '' },
      }
    };
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Add sizes`
    partsData.parts.request.size = requestRaw ? requestRaw.length : 0;
    partsData.parts.rendered.size = renderedCtxRaw ? renderedCtxRaw.length : 0;
    partsData.parts.response.size = responseRaw ? responseRaw.length : 0;

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Build missing-reason for fallback`
    var missingReason = payload.payload_missing_reason ||
      pld.missingReason ||
      'Payload not captured for this agent type or request.';

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Create overlay`
    var overlay = document.createElement('div');
    overlay.className = 'payload-viewer-overlay';
    var side = createEl('aside', { className: 'viewer-side' }, [
      createEl('div', { className: 'nav-label', text: 'Parts' }),
    ]);
    appendPart(side, 'request', 'Request Payload', partsData.parts.request.size, !!requestRaw, true);
    appendPart(
      side,
      'rendered',
      'Rendered Context',
      partsData.parts.rendered.size,
      !!renderedCtxRaw,
      !requestRaw
    );
    appendPart(side, 'response', 'Response Payload', partsData.parts.response.size, !!responseRaw, false);
    appendPart(
      side,
      'tools',
      'Multipart (' + contentParts.length + ')',
      contentParts.length,
      !!(contentParts && contentParts.length > 0),
      false
    );

    var viewSwitch = createEl('div', { className: 'view-switch' }, [
      createEl(
        'button',
        { className: 'active', 'data-action': 'payload-switch', 'data-payload-mode': 'json', text: 'JSON' }
      ),
      createEl(
        'button',
        { 'data-action': 'payload-switch', 'data-payload-mode': 'rendered', text: 'Rendered' }
      ),
      createEl('button', { 'data-action': 'payload-switch', 'data-payload-mode': 'raw', text: 'Raw' }),
      createEl(
        'button',
        {
          'data-action': 'payload-switch',
          'data-payload-mode': 'diff',
          title: 'Compare two payloads (select two parts first)',
          text: 'Diff',
        }
      ),
    ]);
    var toolbar = createEl('div', { className: 'viewer-toolbar' }, [viewSwitch]);
    if (!hasAnyData) {
      toolbar.appendChild(
        createEl('span', { className: 'badge warn payload-unavailable-badge', text: 'payload unavailable' })
      );
    }

    var viewerContent = createEl('div', { className: 'viewer-content' });
    if (hasAnyData) {
      viewerContent.appendChild(
        payloadPanel('json', requestRaw || renderedCtxRaw || 'No request payload.', false)
      );
      viewerContent.appendChild(
        payloadPanel('rendered', renderedCtxRaw || requestRaw || 'No rendered context.', true)
      );
      viewerContent.appendChild(
        payloadPanel('raw', responseRaw || requestRaw || 'No response payload.', true)
      );
      viewerContent.appendChild(
        payloadPanel('diff', 'Diff view: select two parts to compare (e.g., Request vs Response).', true)
      );
    } else {
      viewerContent.appendChild(
        createEl('div', { className: 'empty-state payload-empty-state' }, [
          createEl('div', { className: 'empty-state__icon', text: '⊙' }),
          createEl('div', { className: 'empty-state__title', text: 'Payload Unavailable' }),
          createEl('div', { className: 'empty-state__desc', text: missingReason }),
        ])
      );
    }

    var shell = createEl('div', { className: 'viewer-shell', 'data-viewer': 'payload' }, [
      side,
      createEl('main', { className: 'viewer-main' }, [toolbar, viewerContent]),
    ]);
    overlay.appendChild(
      createEl('div', { className: 'overlay-backdrop' }, [
        createEl('div', { className: 'overlay-shell' }, [
          createEl('div', { className: 'overlay-head' }, [
            createEl('span', {
              className: 'overlay-title',
              text: 'Full Payload Viewer — ' + (payload.objectType || 'unknown'),
            }),
            createEl('button', {
              className: 'overlay-close',
              'data-action': 'close-full-payload',
              'aria-label': 'Close',
              text: '×',
            }),
          ]),
          shell,
        ]),
      ])
    );

    document.body.appendChild(overlay);

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Init PayloadViewer (only if data is available)`
    if (hasAnyData) {
      var shell = overlay.querySelector('.viewer-shell[data-viewer="payload"]');
      if (shell) {
        PayloadViewer.register(shell, partsData);
      }
    }
  };

  window.closeFullPayloadViewer = function () {
    var overlay = document.querySelector('.payload-viewer-overlay');
    if (overlay) overlay.remove();
  };

  // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Close on Escape`
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      window.closeFullPayloadViewer();
    }
  });
})();
