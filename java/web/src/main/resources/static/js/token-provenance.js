/** Token measurement semantics shared by personal and isolated-import pages. */
(function () {
  'use strict';
  var keys = ['freshInput', 'cacheRead', 'cacheWrite', 'output'];
  var valid = ['provider_reported', 'estimated', 'unavailable', 'unknown', 'mixed'];
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
  function note(tokens) {
    var p = provenance(tokens);
    var parts = [];
    [['estimated', 'Estimated'], ['unavailable', 'Not reported'], ['unknown', 'Unknown source']].forEach(function (entry) {
      if (!contains(tokens, entry[0])) return;
      var count = Number(p[entry[0] + 'SessionCount'] || 0);
      parts.push(entry[1] + (count ? ': ' + count + ' session' + (count === 1 ? '' : 's') : ''));
    });
    if (state(tokens) === 'mixed') parts.unshift('Partial / mixed measurement');
    if (p.estimationMethod && contains(tokens, 'estimated')) parts.push('Method: ' + p.estimationMethod);
    return parts.join(' · ');
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
  function attach(element, tokens) {
    if (!element) return;
    var host = element.querySelector('.metric-card__body') || element;
    var existing = host.querySelector('[data-token-provenance]');
    var message = note(tokens);
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
    if (!message) { if (existing) existing.remove(); return; }
    var label = existing || document.createElement('div');
    label.setAttribute('data-token-provenance', '');
    label.className = 'text-xs text-muted token-provenance';
    label.textContent = message;
    if (!existing) host.appendChild(label);
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
    total: function (tokens, formatter) { return value(tokens, 'total', formatter); }
  };
}());
