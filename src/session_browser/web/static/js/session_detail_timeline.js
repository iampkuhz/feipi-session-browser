// Session Detail Timeline v9 interactions.
// Scope: data-trace-page only. No inline onclick.

(function () {
  function qs(root, sel) { return root.querySelector(sel); }
  function qsa(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }
  function closest(target, sel) { return target && target.closest ? target.closest(sel) : null; }

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
    qsa(page, '[data-action="filter-status"]').forEach(function (b) {
      b.classList.toggle('is-active', (b.getAttribute('data-status') || '').toLowerCase() === status);
    });

    qsa(page, '[data-trace-round-row]').forEach(function (round) {
      var shouldShow = status === 'all' || (round.getAttribute('data-status') || '').toLowerCase() === status;
      round.hidden = !shouldShow;
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

  function openPayload(button) {
    var page = closest(button, '[data-trace-page]') || document;
    var modal = document.getElementById('payload-modal') || document.getElementById('sd-payload-modal');
    if (!modal) return;

    var payloadId = button.getAttribute('data-payload-id') || '';
    var title = button.getAttribute('data-payload-title') || button.textContent.trim() || 'Payload';
    var dataNode = payloadId ? qs(document, '[data-payload-source="' + payloadId + '"]') : null;
    var body = qs(modal, '[data-payload-body]') || qs(modal, '.sd-modal-body');

    if (qs(modal, '[data-payload-title]')) {
      qs(modal, '[data-payload-title]').textContent = title;
    }

    if (body) {
      if (dataNode) {
        body.innerHTML = dataNode.innerHTML;
      } else {
        body.innerHTML =
          '<section class="sd-payload-part">' +
          '<h3>Payload unavailable</h3>' +
          '<pre>未找到 payload 内容。可能原因：本地 session log 没有持久化 raw HTTP payload，或该按钮缺少 data-payload-id 映射。</pre>' +
          '</section>';
      }
    }

    if (typeof modal.showModal === 'function') modal.showModal();
    else modal.setAttribute('open', '');
  }

  document.addEventListener('click', function (event) {
    var actionEl = closest(event.target, '[data-action]');
    if (!actionEl) return;

    var action = actionEl.getAttribute('data-action');
    var page = closest(actionEl, '[data-trace-page]') || document;

    if (action === 'toggle-round') {
      event.preventDefault();
      toggleRound(actionEl);
    } else if (action === 'filter-status') {
      event.preventDefault();
      setFilter(page, (actionEl.getAttribute('data-status') || 'all').toLowerCase());
    } else if (action === 'collapse-all') {
      event.preventDefault();
      collapseAll(page);
    } else if (action === 'jump-round') {
      event.preventDefault();
      jumpRound(page, actionEl.getAttribute('data-round'));
    } else if (action === 'open-payload') {
      event.preventDefault();
      openPayload(actionEl);
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    qsa(document, '[data-trace-round-row]').forEach(function (round) {
      var button = qs(round, '[data-action="toggle-round"]');
      var open = round.classList.contains('is-open') || (button && button.getAttribute('aria-expanded') === 'true');
      setRoundOpen(round, open);
    });
  });
})();
