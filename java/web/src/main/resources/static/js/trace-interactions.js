// Session Browser UI — payload interactions and conservative page interactions.
// Scope: session detail payload interactions and conservative page interactions.
// Required actions:
// - toggle-round
// - toggle-all
// - jump-round
// - open-payload  (handled by session-detail/payload.js)
// - close-payload (handled by session-detail/payload.js)
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
    const roundId = round.getAttribute("data-round");
    const detail = qs(round, "[data-trace-detail]") || (roundId ? document.getElementById("round-" + roundId + "-detail") : null);
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

  function jumpRound(page, roundId){
    const round = qs(page, '[data-trace-round-row][data-round="' + esc(roundId) + '"]');
    if(!round) return;
    round.hidden = false;
    setRoundOpen(round, true);
    round.scrollIntoView({behavior:"smooth", block:"center"});
    updateToggleAll(page);
  }

  /* open-payload / close-payload handled by session-detail/payload.js */

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
    } else if(action === "jump-round"){
      if(closest(actionEl, "[data-trace-page]")) return;
      event.preventDefault();
      jumpRound(page, actionEl.dataset.round);
    }
    /* open-payload / close-payload handled by session-detail/payload.js */
  });

  document.addEventListener("keydown", function(event){
    /* Escape to close payload handled by session-detail/payload.js */
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
