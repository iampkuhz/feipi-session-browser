// Session Detail Timeline v11 interactions.
// Contract:
// - no inline onclick
// - every visible action uses [data-action]
// - open-payload maps button[data-payload-id] -> template[data-payload-source]
// - toggle-all is a reversible Collapse all / Expand all button
(function () {
  "use strict";

  function qs(root, selector) {
    return root ? root.querySelector(selector) : null;
  }

  function qsa(root, selector) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  function closest(target, selector) {
    return target && target.closest ? target.closest(selector) : null;
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(value);
    return String(value).replace(/"/g, '\\"');
  }

  function setRoundOpen(round, open) {
    if (!round) return;
    round.classList.toggle("is-open", open);
    round.classList.toggle("open", open); // tolerate legacy CSS while migrating
    var button = qs(round, '[data-action="toggle-round"]');
    var detail = qs(round, "[data-trace-detail]");
    if (button) button.setAttribute("aria-expanded", open ? "true" : "false");
    if (detail) detail.hidden = !open;
  }

  function setSubRoundOpen(subRound, open) {
    if (!subRound) return;
    subRound.classList.toggle("is-open", open);
    var button = qs(subRound, '[data-action="toggle-sub-round"]');
    var detail = qs(subRound, ".sd-sub-steps");
    if (button) button.setAttribute("aria-expanded", open ? "true" : "false");
    if (detail) detail.hidden = !open;
  }

  function visibleRounds(page) {
    return qsa(page, "[data-trace-round-row]").filter(function (round) {
      return !round.hidden;
    });
  }

  function updateToggleAll(page) {
    var button = qs(page, '[data-action="toggle-all"]');
    if (!button) return;
    var rounds = visibleRounds(page);
    var allOpen = rounds.length > 0 && rounds.every(function (round) {
      return round.classList.contains("is-open") || round.classList.contains("open");
    });
    button.textContent = allOpen ? "Collapse all" : "Expand all";
    button.setAttribute("data-state", allOpen ? "collapse" : "expand");
  }

  function toggleAll(page, button) {
    var shouldExpand = (button.getAttribute("data-state") || "collapse") === "expand";
    visibleRounds(page).forEach(function (round) {
      setRoundOpen(round, shouldExpand);
    });
    updateToggleAll(page);
  }

  function setFilter(page, status) {
    qsa(page, '[data-action="filter-status"]').forEach(function (button) {
      button.classList.toggle("is-active", (button.getAttribute("data-status") || "").toLowerCase() === status);
      button.classList.toggle("active", (button.getAttribute("data-status") || "").toLowerCase() === status);
    });

    qsa(page, "[data-trace-round-row]").forEach(function (round) {
      var shouldShow = status === "all" || (round.getAttribute("data-status") || "").toLowerCase() === status;
      round.hidden = !shouldShow;
    });

    updateToggleAll(page);
  }

  function jumpRound(page, roundId) {
    if (!roundId) return;
    var round = qs(page, '[data-trace-round-row][data-round="' + cssEscape(roundId) + '"]');
    if (!round) return;
    round.hidden = false;
    setRoundOpen(round, true);
    round.scrollIntoView({ block: "center", behavior: "smooth" });
    updateToggleAll(page);
  }

  function setPayloadTab(modal, active) {
    qsa(modal, ".sd-payload-tab").forEach(function (tab) {
      var on = (tab.getAttribute("data-tab") || "content") === active;
      tab.classList.toggle("is-active", on);
      tab.classList.toggle("active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });

    var layout = qs(modal, ".sd-payload-layout");
    if (layout) layout.setAttribute("data-active-tab", active);
  }

  function readPayloadTemplate(payloadId) {
    if (!payloadId) return null;
    return qs(document, 'template[data-payload-source="' + cssEscape(payloadId) + '"]');
  }

  function readPayloadApiBase() {
    var meta = qs(document, 'meta[name="payload-api-base"]');
    if (meta) return meta.getAttribute("content") || "";
    return "";
  }

  function htmlEscape(text) {
    return String(text).replace(/[<>&]/g, function (c) {
      return {"<": "&lt;", ">": "&gt;", "&": "&amp;"}[c];
    });
  }

  function openPayload(button) {
    var modal = document.getElementById("payload-modal") || document.getElementById("sd-payload-modal");
    if (!modal) return;

    var payloadId = button.getAttribute("data-payload-id") || "";
    var title = button.getAttribute("data-payload-title") || button.textContent.trim() || "Payload";
    var template = readPayloadTemplate(payloadId);
    var body = qs(modal, "[data-payload-body]") || qs(modal, ".sd-modal-body");
    var titleNode = qs(modal, "[data-payload-title]");
    var subtitleNode = qs(modal, "[data-payload-subtitle]");
    var metaId = qs(modal, "[data-meta-id]");
    var metaKind = qs(modal, "[data-meta-kind]");
    var metaStatus = qs(modal, "[data-meta-status]");
    var metaSize = qs(modal, "[data-meta-size]");
    var metaFinish = qs(modal, "[data-meta-finish]");
    var metaTs = qs(modal, "[data-meta-ts]");
    var apiBase = readPayloadApiBase();

    if (titleNode) titleNode.textContent = title;
    if (subtitleNode) subtitleNode.textContent = payloadId || "missing payload id";

    if (template) {
      if (metaKind) metaKind.textContent = template.dataset.payloadKind || "—";
      if (metaStatus) metaStatus.textContent = template.dataset.payloadStatus || "—";
      if (metaSize) metaSize.textContent = template.dataset.payloadSize || "—";

      // Try to read finish_reason and timestamp from the parent LLM card
      var card = closest(button, "[data-inline-call-card]") || closest(button, "[data-sub-llm-card]");
      if (card) {
        if (metaFinish) metaFinish.textContent = card.dataset.finishReason || "—";
        if (metaTs) metaTs.textContent = card.dataset.timestamp || "—";
      } else {
        if (metaFinish) metaFinish.textContent = "—";
        if (metaTs) metaTs.textContent = "—";
      }

      body.innerHTML = template.innerHTML;
    } else {
      if (metaKind) metaKind.textContent = "missing";
      if (metaStatus) metaStatus.textContent = "not found";
      if (metaSize) metaSize.textContent = "—";
      if (metaFinish) metaFinish.textContent = "—";
      if (metaTs) metaTs.textContent = "—";
      body.innerHTML =
        '<div class="sd-payload-empty">没有找到 payload source。请检查按钮 data-payload-id 是否能匹配 template[data-payload-source]，以及后端是否输出 payload_sources。</div>' +
        '<section class="sd-payload-content"><h3>Debug</h3><pre>button.data-payload-id = ' +
        htmlEscape(payloadId || "(empty)") +
        '</pre></section>';
    }

    // Lazy-load full payload from API if available
    if (apiBase && payloadId) {
      // Show loading indicator
      if (metaStatus) metaStatus.textContent = "loading…";
      var loadingHtml = '<div class="sd-payload-empty">Loading full payload…</div>';
      // Append loading hint without wiping existing template content immediately
      var loadingMarker = document.createElement("div");
      loadingMarker.className = "sd-payload-loading";
      loadingMarker.innerHTML = loadingHtml;
      // We'll replace body content once the fetch succeeds
      var fetchUrl = apiBase.replace(/\/+$/, "") + "/payload/" + encodeURIComponent(payloadId);
      fetch(fetchUrl)
        .then(function (resp) {
          if (!resp.ok) {
            return resp.json().then(function (errData) {
              throw new Error(errData.error || ("HTTP " + resp.status));
            });
          }
          return resp.json();
        })
        .then(function (data) {
          // Update metadata from API response (untruncated)
          if (metaId) metaId.textContent = data.payload_id || payloadId;
          if (metaKind) metaKind.textContent = data.kind || "—";
          if (metaStatus) metaStatus.textContent = data.status || "available";
          if (metaSize) metaSize.textContent = data.size || "—";
          if (metaFinish) metaFinish.textContent = data.finish_reason || "—";
          if (metaTs) metaTs.textContent = data.timestamp || "—";

          // Update modal title/subtitle
          if (titleNode && data.title) titleNode.textContent = data.title;
          if (subtitleNode) subtitleNode.textContent = payloadId || "";

          // Render full untruncated content
          if (data.text) {
            body.innerHTML =
              '<section class="sd-payload-content">' +
              '<h3>' + htmlEscape(data.title || "Payload") + '</h3>' +
              '<pre>' + htmlEscape(data.text) + '</pre>' +
              '</section>';
          } else {
            body.innerHTML =
              '<section class="sd-payload-content">' +
              '<h3>Empty</h3>' +
              '<pre>(payload text is empty)</pre>' +
              '</section>';
          }
        })
        .catch(function (err) {
          var errMsg = htmlEscape(err.message || String(err));
          if (metaStatus) metaStatus.textContent = "error";
          body.innerHTML =
            '<section class="sd-payload-content">' +
            '<h3>Loading failed</h3>' +
            '<pre>Failed to load payload: ' + errMsg + '</pre>' +
            '</section>';
        });
    }

    setPayloadTab(modal, "content");
    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "");
  }

  document.addEventListener("click", function (event) {
    var actionEl = closest(event.target, "[data-action]");
    if (!actionEl) return;

    var action = actionEl.getAttribute("data-action");
    var page = closest(actionEl, "[data-trace-page]") || document;

    if (action === "toggle-round") {
      event.preventDefault();
      var round = closest(actionEl, "[data-trace-round-row]");
      setRoundOpen(round, !(round && (round.classList.contains("is-open") || round.classList.contains("open"))));
      updateToggleAll(page);
      return;
    }

    if (action === "toggle-sub-round") {
      event.preventDefault();
      var subRound = closest(actionEl, ".sd-sub-round");
      setSubRoundOpen(subRound, !(subRound && subRound.classList.contains("is-open")));
      return;
    }

    if (action === "toggle-all") {
      event.preventDefault();
      toggleAll(page, actionEl);
      return;
    }

    if (action === "filter-status") {
      event.preventDefault();
      setFilter(page, (actionEl.getAttribute("data-status") || "all").toLowerCase());
      return;
    }

    if (action === "jump-round") {
      event.preventDefault();
      jumpRound(page, actionEl.getAttribute("data-round"));
      return;
    }

    if (action === "open-payload") {
      event.preventDefault();
      openPayload(actionEl);
      return;
    }

    if (action === "close-payload") {
      event.preventDefault();
      var modal = closest(actionEl, "dialog") || document.getElementById("payload-modal");
      if (modal && typeof modal.close === "function") modal.close();
      else if (modal) modal.removeAttribute("open");
      return;
    }

    if (action === "payload-tab") {
      event.preventDefault();
      var modalForTab = closest(actionEl, "dialog");
      setPayloadTab(modalForTab, actionEl.getAttribute("data-tab") || "content");
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    qsa(document, "[data-trace-round-row]").forEach(function (round) {
      var button = qs(round, '[data-action="toggle-round"]');
      var open = round.classList.contains("is-open") || round.classList.contains("open") || (button && button.getAttribute("aria-expanded") === "true");
      setRoundOpen(round, open);
    });

    qsa(document, ".sd-sub-round").forEach(function (subRound) {
      var button = qs(subRound, '[data-action="toggle-sub-round"]');
      var open = subRound.classList.contains("is-open") || (button && button.getAttribute("aria-expanded") === "true");
      setSubRoundOpen(subRound, open);
    });

    qsa(document, "[data-trace-page]").forEach(updateToggleAll);
  });
})();
