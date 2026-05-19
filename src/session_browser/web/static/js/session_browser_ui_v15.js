// Session Browser UI v15 interactions.
// Scope: session detail payload interactions and conservative page interactions.
// Required actions:
// - toggle-round
// - toggle-all
// - filter-status
// - jump-round
// - open-payload
// - close-payload
(function(){
  "use strict";

  function qs(root, sel){ return (root || document).querySelector(sel); }
  function qsa(root, sel){ return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function closest(target, sel){ return target && target.closest ? target.closest(sel) : null; }
  function esc(value){
    if(window.CSS && typeof CSS.escape === "function") return CSS.escape(value);
    return String(value || "").replace(/"/g, '\\"');
  }

  function setRoundOpen(round, open){
    if(!round) return;
    round.classList.toggle("is-open", open);
    round.classList.toggle("open", open);
    const btn = qs(round, '[data-action="toggle-round"]');
    const detail = qs(round, "[data-trace-detail]");
    if(btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    if(detail) detail.hidden = !open;
  }

  function updateToggleAll(page){
    const btn = qs(page, '[data-action="toggle-all"]');
    if(!btn) return;
    const rounds = qsa(page, "[data-trace-round-row]").filter(r => !r.hidden);
    const allOpen = rounds.length > 0 && rounds.every(r => r.classList.contains("is-open") || r.classList.contains("open"));
    btn.textContent = allOpen ? "Collapse all" : "Expand all";
    btn.dataset.state = allOpen ? "collapse" : "expand";
  }

  function setFilter(page, status){
    qsa(page, '[data-action="filter-status"]').forEach(btn => {
      const on = (btn.dataset.status || "").toLowerCase() === status;
      btn.classList.toggle("is-active", on);
      btn.classList.toggle("active", on);
    });
    qsa(page, "[data-trace-round-row]").forEach(round => {
      round.hidden = !(status === "all" || (round.dataset.status || "").toLowerCase() === status);
    });
    updateToggleAll(page);
  }

  function jumpRound(page, roundId){
    const round = qs(page, '[data-trace-round-row][data-round="' + esc(roundId) + '"]');
    if(!round) return;
    round.hidden = false;
    setRoundOpen(round, true);
    round.scrollIntoView({behavior:"smooth", block:"center"});
    updateToggleAll(page);
  }

  function openPayload(button){
    const modal = document.getElementById("payload-modal") || document.getElementById("sd-payload-modal");
    if(!modal) return;
    const id = button.dataset.payloadId || "";
    const title = button.dataset.payloadTitle || button.textContent.trim() || "Payload";
    const source = id ? qs(document, 'template[data-payload-source="' + esc(id) + '"]') : null;
    const kind = source ? (source.dataset.payloadKind || "unknown") : "missing";
    const status = source ? (source.dataset.payloadStatus || "—") : "not found";
    const size = source ? (source.dataset.payloadSize || "—") : "—";

    // v15 modal: [data-payload-title], [data-payload-subtitle], [data-meta-field]
    const titleEl = qs(modal, "[data-payload-title]") || qs(modal, ".sd-modal-title[data-payload-title]");
    const subtitleEl = qs(modal, "[data-payload-subtitle]") || qs(modal, ".sd-modal-sub");
    const body = qs(modal, "[data-payload-body]") || qs(modal, ".sd-payload-main[data-payload-body]");

    if(titleEl) titleEl.textContent = title;
    if(subtitleEl) subtitleEl.textContent = id || "missing payload id";

    // v15 meta: data-meta-field
    qsa(modal, "[data-meta-field]").forEach(el => {
      const key = el.dataset.metaField;
      if(key === "payload_id") el.textContent = id || "—";
      if(key === "kind") el.textContent = kind;
      if(key === "status") el.textContent = status;
      if(key === "source") el.textContent = source ? "template" : "missing";
    });

    // v12 meta: data-meta-id, data-meta-kind, etc.
    const metaId = qs(modal, "[data-meta-id]");
    const metaKind = qs(modal, "[data-meta-kind]");
    const metaStatus = qs(modal, "[data-meta-status]");
    const metaSize = qs(modal, "[data-meta-size]");
    if(metaId) metaId.textContent = id || "—";
    if(metaKind) metaKind.textContent = kind;
    if(metaStatus) metaStatus.textContent = status;
    if(metaSize) metaSize.textContent = size;

    if(body){
      if(source){
        body.innerHTML = source.innerHTML;
      } else {
        body.innerHTML = '<div class="payload-warning sd-payload-warning">未找到 payload 内容。检查 data-payload-id 是否有对应 template[data-payload-source]；不要空白。</div>';
      }
    }

    if(typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "");
  }

  function closePayload(){
    const modal = document.getElementById("payload-modal") || document.getElementById("sd-payload-modal");
    if(!modal) return;
    if(typeof modal.close === "function" && modal.open) modal.close();
    else modal.removeAttribute("open");
  }

  document.addEventListener("click", function(event){
    const actionEl = closest(event.target, "[data-action]");
    if(!actionEl) return;
    const action = actionEl.dataset.action;
    const page = closest(actionEl, "[data-trace-page]") || document;
    if(action === "toggle-round"){
      event.preventDefault();
      const round = closest(actionEl, "[data-trace-round-row]");
      setRoundOpen(round, !(round && (round.classList.contains("is-open") || round.classList.contains("open"))));
      updateToggleAll(page);
    } else if(action === "toggle-all"){
      event.preventDefault();
      const shouldExpand = actionEl.dataset.state === "expand";
      qsa(page, "[data-trace-round-row]").filter(r => !r.hidden).forEach(r => setRoundOpen(r, shouldExpand));
      updateToggleAll(page);
    } else if(action === "filter-status"){
      event.preventDefault();
      setFilter(page, (actionEl.dataset.status || "all").toLowerCase());
    } else if(action === "jump-round"){
      event.preventDefault();
      jumpRound(page, actionEl.dataset.round);
    } else if(action === "open-payload"){
      event.preventDefault();
      openPayload(actionEl);
    } else if(action === "close-payload"){
      event.preventDefault();
      closePayload();
    }
  });

  document.addEventListener("keydown", function(event){
    if(event.key === "Escape") closePayload();
  });

  document.addEventListener("DOMContentLoaded", function(){
    qsa(document, "[data-trace-round-row]").forEach(round => {
      const btn = qs(round, '[data-action="toggle-round"]');
      const open = round.classList.contains("is-open") || round.classList.contains("open") || (btn && btn.getAttribute("aria-expanded") === "true");
      setRoundOpen(round, open);
    });
    qsa(document, "[data-trace-page]").forEach(updateToggleAll);
  });
})();