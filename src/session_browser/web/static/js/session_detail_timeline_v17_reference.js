// Session Detail v17 payload modal reference.
// Merge into src/session_browser/web/static/js/session_detail_timeline.js.
// Do not create a second competing event system.
(function () {
  "use strict";

  function qs(root, sel) { return (root || document).querySelector(sel); }
  function closest(target, sel) { return target && target.closest ? target.closest(sel) : null; }
  function cssEscape(value) {
    if (window.CSS && typeof CSS.escape === "function") return CSS.escape(value);
    return String(value || "").replace(/["\\]/g, "\\$&");
  }
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function ensurePayloadModal() {
    var modal = document.getElementById("sd-payload-modal") || document.getElementById("payload-modal");
    if (modal) return modal;

    modal = document.createElement("dialog");
    modal.id = "sd-payload-modal";
    modal.className = "sd-payload-modal";
    modal.innerHTML = [
      '<div class="sd-modal-panel payload-modal__panel">',
      '  <div class="sd-modal-head payload-modal__head">',
      '    <div><div class="sd-modal-title payload-modal__title" data-payload-title>Payload</div>',
      '    <div class="sd-modal-subtitle payload-modal__subtitle" data-payload-subtitle>—</div></div>',
      '    <button type="button" class="sd-btn sd-btn--secondary sd-btn--sm sd-modal-close" data-action="close-payload">Close</button>',
      '  </div>',
      '  <div class="sd-modal-body payload-modal__body" data-payload-body></div>',
      '</div>'
    ].join("");
    document.body.appendChild(modal);
    return modal;
  }

  function diagnosticPayloadHtml(payloadId, title) {
    return [
      '<div class="sd-payload-shell payload-shell">',
      '  <aside class="sd-payload-meta payload-meta">',
      '    <h3>Metadata</h3>',
      '    <div class="sd-kv"><span>payload id</span><span>', escapeHtml(payloadId || "—"), '</span></div>',
      '    <div class="sd-kv"><span>kind</span><span>diagnostic</span></div>',
      '    <div class="sd-kv"><span>status</span><span>missing source</span></div>',
      '  </aside>',
      '  <main class="sd-payload-main payload-main">',
      '    <div class="sd-payload-warning payload-warning">',
      '      未找到 payload source。按钮必须保留；当前显示诊断而不是空白。请检查 data-payload-id 与 template[data-payload-source] 映射，以及后端是否创建 diagnostic payload。',
      '    </div>',
      '    <section class="sd-payload-section payload-section"><h3>Requested payload</h3>',
      '      <pre>', escapeHtml(title || "Payload"), '</pre>',
      '    </section>',
      '  </main>',
      '</div>'
    ].join("");
  }

  function openPayload(button) {
    var modal = ensurePayloadModal();
    var payloadId = button.getAttribute("data-payload-id") || "";
    var title = button.getAttribute("data-payload-title") || button.textContent.trim() || "Payload";
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
        body.innerHTML = source.tagName && source.tagName.toLowerCase() === "template"
          ? source.innerHTML
          : source.innerHTML;
      } else {
        body.innerHTML = diagnosticPayloadHtml(payloadId, title);
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

  document.addEventListener("click", function (event) {
    var actionEl = closest(event.target, "[data-action]");
    if (!actionEl) return;
    var action = actionEl.getAttribute("data-action");
    if (action === "open-payload") {
      event.preventDefault();
      openPayload(actionEl);
    } else if (action === "close-payload") {
      event.preventDefault();
      closePayload();
    }
  }, true);

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closePayload();
  });
})();
