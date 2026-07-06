  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Lazy load round detail from API ──` */

  function getApiBase() {
    var meta = document.querySelector('meta[name="payload-api-base"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function lazyLoadRoundDetail(row) {
    var roundId = row.getAttribute('data-round');
    if (!roundId) return null;
    var apiBase = getApiBase();
    if (!apiBase) return null;
    var url = apiBase.replace(/\/$/, '') + '/round/' + encodeURIComponent(roundId);

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Insert loading indicator using DOM APIs`
    var loadingRow = document.createElement('tr');
    loadingRow.className = 'sd-round-detail-loading';
    loadingRow.setAttribute('data-loading-for', roundId);
    var tdLoading = document.createElement('td');
    tdLoading.setAttribute('colspan', '6');
    var divLoading = document.createElement('div');
    divLoading.className = 'sd-loading-indicator';
    divLoading.textContent = 'Loading round R' + roundId + '...';
    tdLoading.appendChild(divLoading);
    loadingRow.appendChild(tdLoading);
    row.parentNode.insertBefore(loadingRow, row.nextSibling);

    setRoundOpen(row, true);

    return fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (resp) {
        if (!resp.ok) {
          var status = resp.status;
          return resp.json().then(function (d) { throw { status: status, data: d }; }).catch(function () {
            throw { status: status, data: null };
          });
        }
        return resp.json();
      })
      .then(function (data) {
        // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Remove loading row`
        if (loadingRow && loadingRow.parentNode) loadingRow.parentNode.removeChild(loadingRow);

        // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Inject the expanded row HTML after the summary row`
        var detailRow = document.createElement('tr');
        detailRow.className = 'expanded-row';
        detailRow.id = 'round-' + roundId + '-detail';
        detailRow.setAttribute('data-trace-detail', '');
        var tdDetail = document.createElement('td');
        tdDetail.setAttribute('colspan', '6');
        detailRow.appendChild(tdDetail);
        setHtml(tdDetail, data.html || renderRoundDetailFromJson(data.round, roundId));
        row.parentNode.insertBefore(detailRow, row.nextSibling);
        qsa(detailRow, '[data-sub-round-id]').forEach(function (subRound) {
          if (typeof syncSubRoundToggle === 'function') syncSubRoundToggle(subRound);
        });
        qsa(detailRow, '[data-subagent-block]').forEach(function (block) {
          if (typeof syncSubagentToggle === 'function') syncSubagentToggle(block);
        });

        // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Mark as loaded`
        row.setAttribute('data-detail-loaded', 'true');

        // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Inject payload sources as <template> elements if present`
        if (data.payload_sources && data.payload_sources.length > 0) {
          injectPayloadSources(data.payload_sources);
        }
      })
      .catch(function (err) {
        if (loadingRow && loadingRow.parentNode) {
          var msg;
          if (err.data && err.data.error) {
            msg = err.data.error;
          } else if (err.status) {
            msg = 'Failed to load round detail (HTTP ' + err.status + ')';
          } else {
            msg = 'Failed to load round detail';
          }
          // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Replace loading row content with error state using DOM APIs`
          while (loadingRow.firstChild) loadingRow.removeChild(loadingRow.firstChild);
          var tdError = document.createElement('td');
          tdError.setAttribute('colspan', '6');
          var divError = document.createElement('div');
          divError.className = 'sd-round-detail-error';
          var spanError = document.createElement('span');
          spanError.textContent = 'Round R' + roundId + ' load failed: ' + msg;
          divError.appendChild(spanError);
          var btnRetry = document.createElement('button');
          btnRetry.type = 'button';
          btnRetry.className = 'sd-btn sd-btn--primary sd-btn--sm';
          btnRetry.setAttribute('data-action', 'retry-round');
          btnRetry.setAttribute('data-round', roundId);
          btnRetry.textContent = 'Retry';
          divError.appendChild(btnRetry);
          tdError.appendChild(divError);
          loadingRow.appendChild(tdError);
        }
        setRoundOpen(row, false);
        throw err;
      });
  }

  function injectPayloadSources(sources) {
    var container = document.querySelector('[data-payload-sources-container]');
    if (!container) {
      container = document.createElement('div');
      container.setAttribute('data-payload-sources-container', '');
      container.className = 'sd-hidden';
      document.body.appendChild(container);
    }
    for (var i = 0; i < sources.length; i++) {
      var src = sources[i];
      if (!src.payload_id) continue;
      if (container.querySelector('[data-payload-source="' + cssEscape(src.payload_id) + '"]')) continue;
      var tpl = document.createElement('template');
      tpl.setAttribute('data-payload-source', src.payload_id);
      tpl.setAttribute('data-payload-kind', src.kind || 'unknown');
      tpl.setAttribute('data-payload-status', src.status || 'available');
      tpl.setAttribute('data-payload-size', src.size || '—');
      tpl.setAttribute('data-payload-token-estimate', src.token_estimate || '');
      if (src.html) {
        setHtml(tpl, src.html);
      } else if (typeof payloadNodeFromJson === 'function') {
        tpl.content.appendChild(payloadNodeFromJson(src));
      } else if (src.text) {
        var pre = document.createElement('pre');
        pre.textContent = src.text;
        tpl.content.appendChild(pre);
      }
      container.appendChild(tpl);
    }
  }

  function renderRoundDetailFromJson(round, roundId) {
    round = round || {};
    var calls = Array.isArray(round.calls) ? round.calls : [];
    var toolCallIds = Array.isArray(round.toolCallIds) ? round.toolCallIds : [];
    var html = '<div class="sd-round-detail"><div class="sd-detail-grid">'
      + '<section class="sd-card"><h3>Round R' + escapeRoundHtml(roundId) + ' detail</h3>'
      + '<p>' + escapeRoundHtml(String(calls.length)) + ' LLM calls and '
      + escapeRoundHtml(String(toolCallIds.length)) + ' tool calls are indexed for this round.</p></section>'
      + '<section class="sd-card"><h3>Calls</h3>';
    if (!calls.length) {
      html += '<div class="sd-card-empty">No normalized calls returned by the round API.</div>';
    } else {
      html += '<table class="sd-compact-table"><tbody>';
      calls.forEach(function (call, idx) {
        var callIndex = idx + 1;
        var usage = call.usage || {};
        var reqId = payloadIdFor(call, 'req');
        var respId = payloadIdFor(call, 'resp');
        var reqKind = payloadKindFor(call, 'req');
        var respKind = payloadKindFor(call, 'resp');
        html += '<tr><th>' + escapeRoundHtml(call.callKey || call.callId || ('call ' + callIndex)) + '</th>'
          + '<td><span class="mono">' + escapeRoundHtml(call.model || '') + '</span> · '
          + escapeRoundHtml(String(usage.total || 0)) + ' tokens '
          + '<div class="sd-payload-control-group" aria-label="Round R' + escapeRoundHtml(roundId) + ' call ' + callIndex + ' payload controls">'
          + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm" data-action="open-payload" data-payload-id="'
          + escapeRoundHtml(reqId) + '" data-payload-kind="' + escapeRoundHtml(reqKind)
          + '" data-payload-title="Request ' + escapeRoundHtml(call.callKey || call.callId || callIndex) + '">Request payload</button> '
          + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm" data-action="open-payload" data-payload-id="'
          + escapeRoundHtml(respId) + '" data-payload-kind="' + escapeRoundHtml(respKind)
          + '" data-payload-title="Response ' + escapeRoundHtml(call.callKey || call.callId || callIndex) + '">Response payload</button> '
          + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm" data-action="open-attribution" data-attribution-kind="request" data-attribution-url="'
          + escapeRoundHtml(attributionUrl(roundId, callIndex, 'request')) + '" data-payload-title="调用详情">Request attribution</button> '
          + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm" data-action="open-attribution" data-attribution-kind="response" data-attribution-url="'
          + escapeRoundHtml(attributionUrl(roundId, callIndex, 'response')) + '" data-payload-title="调用详情">Response attribution</button>'
          + '</div></td></tr>';
      });
      html += '</tbody></table>';
    }
    html += '</section><section class="sd-card"><h3>Signals</h3><table class="sd-compact-table"><tbody>'
      + '<tr><th>Status</th><td>' + (toolCallIds.length > 0 ? 'loaded' : 'no tools') + '</td></tr>'
      + '<tr><th>Calls</th><td>' + escapeRoundHtml(String(calls.length)) + '</td></tr>'
      + '<tr><th>Tools</th><td>' + escapeRoundHtml(String(toolCallIds.length)) + '</td></tr>'
      + '</tbody></table></section></div></div>';
    return html;
  }

  function payloadIdFor(call, side) {
    var prefix = call && call.scope === 'subagent' ? 'sa' : 'main';
    return prefix + ':' + side + ':' + (call && call.callId ? call.callId : '');
  }

  function payloadKindFor(call, side) {
    var subagent = call && call.scope === 'subagent';
    if (side === 'req') return subagent ? 'subagent_request' : 'llm_request';
    return subagent ? 'subagent_response' : 'llm_response';
  }

  function attributionUrl(roundId, callIndex, kind) {
    var apiBase = getApiBase().replace(/\/$/, '');
    return apiBase + '/attribution/' + encodeURIComponent(roundId) + '/' + encodeURIComponent(callIndex) + '/' + kind;
  }

  function escapeRoundHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch];
    });
  }
