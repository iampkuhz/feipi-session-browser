/** Token measurement semantics shared by personal and isolated-import pages. */
(function () {
  'use strict';
  var keys = ['freshInput', 'cacheRead', 'cacheWrite', 'output'];
  var valid = ['provider_reported', 'estimated', 'unavailable', 'unknown', 'mixed'];
  var methods = {
    visible_context_v1: 'visible conversation context in project records',
    cache_transcript_v1: 'visible conversation context in the local transcript cache'
  };
  function provenance(tokens) { return tokens && tokens.provenance || {}; }
  function state(tokens, key) {
    var p = provenance(tokens);
    if (key === 'fresh') key = 'freshInput';
    if (key) return valid.indexOf(p[key]) >= 0 ? p[key] : 'unknown';
    var states = keys.map(function (part) { return state(tokens, part); });
    return states.every(function (part) { return part === states[0]; }) ? states[0] : 'mixed';
  }
  function contains(tokens, name) {
    return Number(provenance(tokens)[name + 'SessionCount'] || 0) > 0
      || keys.some(function (key) { return state(tokens, key) === name; });
  }
  function evidence(tokens) {
    var p = provenance(tokens);
    var parts = [];
    [['estimated', 'Estimated', 'Includes estimated Token counts'],
      ['unavailable', 'Not reported', 'Some Token counts were not reported'],
      ['unknown', 'Unknown source', 'The measurement source was not recorded']].forEach(function (entry) {
      if (!contains(tokens, entry[0])) return;
      var count = Number(p[entry[0] + 'SessionCount'] || 0);
      parts.push([entry[1], count ? count.toLocaleString('en-US') + ' session' + (count === 1 ? '' : 's') : entry[2]]);
    });
    if (p.estimationMethod && contains(tokens, 'estimated')) {
      var labels = new Set(p.estimationMethod.split(',').map(function (method) {
        return Object.hasOwn(methods, method.trim()) ? methods[method.trim()] : 'method not documented in this view';
      }));
      parts.push(['Estimate basis', Array.from(labels).join('; ')]);
    }
    if (!parts.length && state(tokens) === 'mixed') {
      parts.push(['Measurement', 'Token components have different measurement sources']);
    }
    return parts;
  }
  function note(tokens) {
    return evidence(tokens).map(function (part) { return part.join(': '); }).join(' · ');
  }
  function addDefinition(list, label, value, color, share) {
    var term = document.createElement('dt');
    term.textContent = label;
    if (color) term.className = 'token-component token-component--' + color;
    var definition = document.createElement('dd');
    definition.textContent = value;
    if (share != null) {
      var portion = document.createElement('small');
      portion.textContent = (share > 0 && share < 0.1 ? '<0.1' : share.toFixed(1)) + '%';
      definition.append(portion);
    }
    list.append(term, definition);
  }
  function amount(tokens, key, formatter) {
    var n = tokens && tokens[key];
    var precision = state(tokens, key === 'total' ? null : key);
    if (precision === 'unavailable' || n == null || !Number.isFinite(Number(n))
        || (Number(n) === 0 && (precision === 'unknown' || precision === 'mixed'))) return 'N/A';
    var approximate = precision === 'estimated'
      || (key === 'total' && precision === 'mixed' && contains(tokens, 'estimated'));
    return (approximate ? '≈' : '') + formatter(n);
  }
  function renderCell(cell, tokens, formatter, showOnBar) {
    var total = document.createElement('div');
    total.className = 'token-total';
    var display = document.createElement('span');
    display.className = 'token-total__value';
    display.textContent = amount(tokens, 'total', formatter);
    total.append(display);
    cell.replaceChildren(total);

    var bar = document.createElement('span');
    bar.className = 'tokenbar';
    bar.setAttribute('aria-hidden', 'true');
    var shown = Number(tokens && tokens.total);
    var exact = function (number) { return Number(number).toLocaleString('en-US'); };
    var parts = [];
    [['fresh', 'Fresh input', 'fresh'], ['cacheRead', 'Cache read', 'read'],
      ['cacheWrite', 'Cache write', 'write'], ['output', 'Output', 'out']].forEach(function (part) {
      var key = part[0];
      var precision = state(tokens, key);
      var n = Number(tokens && tokens[key]);
      var available = precision !== 'unknown' && precision !== 'unavailable'
        && amount(tokens, key, exact) !== 'N/A';
      var share = available && display.textContent !== 'N/A' && shown > 0 && n >= 0 && n <= shown
        ? n / shown * 100 : null;
      parts.push([part[1], value(tokens, key, exact), part[2], share]);
      if (share > 0) {
        var segment = document.createElement('span');
        segment.className = 'tokenbar-seg ' + part[2];
        segment.style.setProperty('--segment-width', share + '%');
        bar.append(segment);
      }
    });
    function composition() {
      var breakdown = document.createElement('div');
      breakdown.className = 'token-composition';
      var caption = document.createElement('p');
      caption.textContent = 'Token breakdown · Share of shown total';
      var list = document.createElement('dl');
      addDefinition(list, 'Shown total', amount(tokens, 'total', exact));
      parts.forEach(function (part) { addDefinition(list, part[0], part[1], part[2], part[3]); });
      breakdown.append(caption, list);
      return breakdown;
    }
    if (showOnBar) {
      var measurement = status(tokens);
      if (measurement) {
        var badge = document.createElement('span');
        badge.className = 'token-total__status';
        badge.textContent = measurement === 'Partial coverage' ? 'Partial' : measurement === 'Unknown source' ? 'Unknown' : measurement;
        badge.setAttribute('aria-label', measurement + (contains(tokens, 'estimated') && measurement !== 'Estimated' ? ', includes estimates' : ''));
        total.append(badge);
      }
      var trigger = document.createElement('button');
      trigger.type = 'button';
      trigger.className = 'token-bar-trigger';
      trigger.setAttribute('aria-label', 'Token breakdown');
      trigger.setAttribute('aria-expanded', 'false');
      trigger.setAttribute('aria-controls', 'token-bar-popover');
      trigger.append(bar);
      total.append(trigger);
      bindBar(trigger, function () {
        var block = composition();
        if (bar.childElementCount) block.firstChild.after(bar.cloneNode(true));
        var evidenceList = document.createElement('dl');
        evidenceList.className = 'token-evidence';
        var rows = evidence(tokens);
        (rows.length ? rows : [['Measurement', 'Provider reported']]).forEach(function (row) {
          addDefinition(evidenceList, row[0], row[1]);
        });
        return [block, evidenceList];
      });
      return;
    }
    if (bar.childElementCount) total.append(bar);
    attach(cell, tokens, composition());
    if (!status(tokens)) cell.querySelector('summary').textContent = 'Token breakdown';
  }
  var tokenPopover;
  var tokenTrigger;
  var closeTimer;
  function closeBar() {
    clearTimeout(closeTimer);
    if (tokenTrigger) tokenTrigger.setAttribute('aria-expanded', 'false');
    tokenTrigger = null;
    if (tokenPopover && tokenPopover.matches(':popover-open')) tokenPopover.hidePopover();
  }
  function scheduleClose() {
    clearTimeout(closeTimer);
    closeTimer = setTimeout(function () {
      if (tokenTrigger && !tokenTrigger.matches(':hover, :focus-visible') && !tokenPopover.matches(':hover')) closeBar();
    }, 160);
  }
  function bindBar(trigger, contents) {
    function open() {
      clearTimeout(closeTimer);
      if (!tokenPopover) {
        tokenPopover = document.createElement('div');
        tokenPopover.id = 'token-bar-popover';
        tokenPopover.className = 'token-bar-popover';
        tokenPopover.setAttribute('popover', 'auto');
        tokenPopover.setAttribute('role', 'region');
        tokenPopover.setAttribute('aria-label', 'Token measurement and composition');
        tokenPopover.addEventListener('pointerenter', function () { clearTimeout(closeTimer); });
        tokenPopover.addEventListener('pointerleave', scheduleClose);
        tokenPopover.addEventListener('toggle', function () {
          if (!tokenPopover.matches(':popover-open')) closeBar();
        });
        window.addEventListener('resize', closeBar);
        document.addEventListener('scroll', function (event) {
          if (!tokenPopover.contains(event.target)) closeBar();
        }, true);
        document.body.append(tokenPopover);
      }
      if (tokenTrigger === trigger && tokenPopover.matches(':popover-open')) return;
      if (tokenTrigger) tokenTrigger.setAttribute('aria-expanded', 'false');
      tokenTrigger = trigger;
      tokenPopover.replaceChildren.apply(tokenPopover, contents());
      if (!tokenPopover.matches(':popover-open')) tokenPopover.showPopover();
      var anchor = trigger.getBoundingClientRect();
      var panel = tokenPopover.getBoundingClientRect();
      var left = Math.max(8, Math.min(anchor.right - panel.width, document.documentElement.clientWidth - panel.width - 8));
      var top = anchor.bottom + 4;
      if (top + panel.height > window.innerHeight - 8) top = Math.max(8, anchor.top - panel.height - 4);
      tokenPopover.style.setProperty('--token-popover-x', left + 'px');
      tokenPopover.style.setProperty('--token-popover-y', top + 'px');
      trigger.setAttribute('aria-expanded', 'true');
    }
    trigger.addEventListener('pointerenter', function (event) { if (event.pointerType === 'mouse') open(); });
    trigger.addEventListener('pointerleave', scheduleClose);
    trigger.addEventListener('focus', function () { if (trigger.matches(':focus-visible')) open(); });
    trigger.addEventListener('blur', scheduleClose);
    trigger.addEventListener('click', function (event) {
      event.stopPropagation();
      open();
    });
  }
  function status(tokens) {
    if (state(tokens) === 'mixed') return 'Partial coverage';
    if (contains(tokens, 'estimated')) return 'Estimated';
    if (contains(tokens, 'unavailable')) return 'Not reported';
    if (contains(tokens, 'unknown')) return 'Unknown source';
    return '';
  }
  function value(tokens, key, formatter) {
    var precision = state(tokens, key === 'total' ? null : key);
    var amount = tokens && tokens[key];
    if (precision === 'unavailable') return 'Not reported';
    if (amount == null || !Number.isFinite(Number(amount))) return 'N/A · Unknown';
    if (precision === 'provider_reported') return formatter(amount);
    if (precision === 'unknown') return (Number(amount) ? formatter(amount) : 'N/A') + ' · Unknown';
    if (precision === 'mixed' && Number(amount) === 0) return 'N/A · Partial';
    var estimated = precision === 'estimated' || contains(tokens, 'estimated');
    return (estimated ? '≈' : '') + formatter(amount) + (precision === 'mixed' ? ' · Partial' : '');
  }
  function measuredInput(tokens) {
    return ['freshInput', 'cacheRead', 'cacheWrite'].every(function (key) { return state(tokens, key) === 'provider_reported'; });
  }
  function ratio(tokens, apiRatio) {
    tokens = tokens || { provenance: apiRatio && apiRatio.provenance };
    if (!measuredInput(tokens)) {
      var inputStates = ['freshInput', 'cacheRead', 'cacheWrite'].map(function (key) { return state(tokens, key); });
      if (inputStates.every(function (part) { return part === 'unavailable'; })) return 'N/A · Not reported';
      if (inputStates.every(function (part) { return part === 'unknown'; })) return 'N/A · Unknown';
      return 'N/A · Partial';
    }
    if (apiRatio && apiRatio.value == null) return 'N/A' + (apiRatio.reason === 'partial_token_measurement' ? ' · Partial' : '');
    var input = Number(tokens.fresh || 0) + Number(tokens.cacheRead || 0) + Number(tokens.cacheWrite || 0);
    var result = apiRatio ? apiRatio.value : (input > 0 ? Number(tokens.cacheRead || 0) / input : null);
    return result == null ? 'N/A' : (Number(result) * 100).toFixed(1) + '%';
  }
  function attach(element, tokens, extra) {
    if (!element) return;
    var host = element.querySelector('.metric-card__body') || element;
    var existing = host.querySelector('[data-token-provenance]');
    var rows = evidence(tokens);
    var message = rows.length;
    if (element.classList.contains('metric-cell')) {
      element.classList.toggle('token-provenance-group', Boolean(message));
      if (message) element.setAttribute('data-token-disclosure', '');
      else element.removeAttribute('data-token-disclosure');
    }
    if (element.classList.contains('hbar-legend__item')) {
      element.classList.toggle('token-provenance-flow', Boolean(message));
      if (message) element.setAttribute('data-token-disclosure', '');
      else element.removeAttribute('data-token-disclosure');
    }
    if (element.classList.contains('chart-card')) {
      [['.chart-card__head', 'token-provenance-group'], ['.chart-card__stats', 'token-provenance-flow']].forEach(function (part) {
        var child = element.querySelector(part[0]);
        if (!child) return;
        child.classList.toggle(part[1], Boolean(message));
        if (message) child.setAttribute('data-token-disclosure', '');
        else child.removeAttribute('data-token-disclosure');
      });
    }
    element.querySelectorAll('.metric-card__primary-row').forEach(function (row) {
      row.classList.toggle('token-provenance-primary', Boolean(message));
      if (message) row.setAttribute('data-token-disclosure', '');
      else row.removeAttribute('data-token-disclosure');
    });
    element.querySelectorAll('.metric-card__value, .sd-kpi__value, .token-total__value, .metric-token').forEach(function (value) {
      value.classList.toggle('token-provenance-value', Boolean(message));
      if (message) value.setAttribute('data-token-measurement', 'partial');
      else value.removeAttribute('data-token-measurement');
    });
    if (!message && !extra) { if (existing) existing.remove(); return; }
    var details = existing || document.createElement('details');
    if (!existing) {
      details.setAttribute('data-token-provenance', '');
      details.className = 'text-xs text-muted token-provenance';
      details.appendChild(document.createElement('summary'));
      // A disclosure inside a clickable row must not activate the row.
      details.addEventListener('click', function (event) { event.stopPropagation(); });
      host.appendChild(details);
    }
    details.firstElementChild.textContent = status(tokens) || 'Measurement details';
    while (details.childElementCount > 1) details.lastElementChild.remove();
    if (extra) details.appendChild(extra);
    if (message) {
      var list = document.createElement('dl');
      list.className = 'token-evidence';
      rows.forEach(function (row) { addDefinition(list, row[0], row[1]); });
      details.appendChild(list);
      if (['estimated', 'unavailable', 'unknown'].filter(function (key) {
        return Number(provenance(tokens)[key + 'SessionCount']) > 0;
      }).length > 1) {
        var explanation = document.createElement('p');
        explanation.textContent = 'Coverage counts can overlap; do not add them.';
        details.appendChild(explanation);
      }
    }
  }
  function merge(left, right) {
    if (!left) return right || {};
    var result = {};
    keys.forEach(function (key) {
      var a = state({ provenance: left }, key);
      var b = state({ provenance: right }, key);
      result[key] = a === b ? a : 'mixed';
    });
    ['estimated', 'unavailable', 'unknown'].forEach(function (name) {
      var key = name + 'SessionCount';
      result[key] = Number(left[key] || 0) + Number(right && right[key] || 0);
    });
    result.estimationMethod = Array.from(new Set([left.estimationMethod, right && right.estimationMethod].filter(Boolean))).join(',');
    return result;
  }
  window.TokenProvenance = {
    state: state, note: note, value: value, measuredInput: measuredInput, ratio: ratio, attach: attach, merge: merge,
    amount: amount, renderCell: renderCell,
    total: function (tokens, formatter) { return value(tokens, 'total', formatter); }
  };
}());
