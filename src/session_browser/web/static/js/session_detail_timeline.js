// Session Detail Timeline v17 interactions.
// Scope: data-trace-page only. No inline onclick.
// Payload modal: single shell, ensurePayloadModal, diagnostic fallback.

(function () {
  function qs(root, sel) { return (root || document).querySelector(sel); }
  function qsa(root, sel) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function closest(target, sel) { return target && target.closest ? target.closest(sel) : null; }
  function cssEscape(value) {
    if (window.CSS && typeof CSS.escape === "function") return CSS.escape(value);
    return String(value || "").replace(/["\\]/g, "\\$&");
  }

  function setRoundOpen(round, open) {
    if (!round) return;
    var btn = qs(round, '[data-action="toggle-round"]');
    var detail = qs(round, '[data-trace-detail]');
    round.classList.toggle('is-open', open);
    if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (detail) detail.hidden = !open;
  }

  function toggleRound(button) {
    var round = closest(button, '[data-trace-round-row]');
    if (!round) return;
    var next = !round.classList.contains('is-open');
    setRoundOpen(round, next);
  }

  function setFilter(page, status) {
    qsa(page, '.trace-panel__chip[data-status], .sd-seg-btn[data-action^="status-"]').forEach(function (b) {
      b.classList.toggle('is-active', (b.getAttribute('data-status') || '').toLowerCase() === status);
    });

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

  function jumpRound(page, roundId) {
    var round = qs(page, '[data-trace-round-row][data-round="' + roundId + '"]');
    if (!round) return;
    round.hidden = false;
    setRoundOpen(round, true);
    round.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  /* ── Payload modal: single shell ── */

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
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
    modal.innerHTML = [
      '<div class="sd-modal-panel payload-modal__panel">',
      '  <div class="sd-modal-head payload-modal__head">',
      '    <div><div class="sd-modal-title payload-modal__title" id="sd-payload-title" data-payload-title>Payload</div>',
      '    <div class="sd-modal-subtitle payload-modal__subtitle" data-payload-subtitle>—</div></div>',
      '    <button type="button" class="sd-btn sd-btn--secondary sd-btn--sm sd-modal-close" data-action="close-payload">Close</button>',
      '  </div>',
      '  <div class="sd-modal-body payload-modal__body" data-payload-body></div>',
      '</div>'
    ].join("");
    document.body.appendChild(modal);
    return modal;
  }

  function openPayload(button) {
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
        body.innerHTML = (source.tagName && source.tagName.toLowerCase() === "template")
          ? source.innerHTML
          : source.innerHTML;
      } else {
        body.innerHTML = diagnosticPayloadHtml(payloadId, title, kind);
      }
    }

    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "");
  }

  function closePayload() {
    var modal = document.getElementById("sd-payload-modal") || document.getElementById("payload-modal");
    if (!modal) return;
    if (typeof modal.close === "function" && modal.open) modal.close();
    else modal.removeAttribute("open");
  }

  /* ── Event delegation (single listener) ── */

  document.addEventListener('click', function (event) {
    var actionEl = closest(event.target, '[data-action]');
    if (!actionEl) return;

    var action = actionEl.getAttribute('data-action');
    var page = closest(actionEl, '[data-trace-page]') || document;

    if (action === 'toggle-round') {
      event.preventDefault();
      event.stopPropagation();
      toggleRound(actionEl);
    } else if (action === 'status-all' || action === 'status-failed') {
      event.preventDefault();
      event.stopPropagation();
      setFilter(page, action.replace('status-', '').toLowerCase());
    } else if (action === 'collapse-all') {
      event.preventDefault();
      event.stopPropagation();
      collapseAll(page);
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
    }
  }, true);

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closePayload();
  });

  document.addEventListener('DOMContentLoaded', function () {
    qsa(document, '[data-trace-round-row]').forEach(function (round) {
      var button = qs(round, '[data-action="toggle-round"]');
      var open = round.classList.contains('is-open') || (button && button.getAttribute('aria-expanded') === 'true');
      setRoundOpen(round, open);
    });
  });
})();
