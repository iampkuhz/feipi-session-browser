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
        setHtml(tdDetail, data.html || renderRoundDetailFromJson(data.round, roundId, row));
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
      } else if (src.text || src.content) {
        if (typeof payloadNodeFromJson === 'function') {
          tpl.content.appendChild(payloadNodeFromJson(src));
        } else if (src.text) {
          var pre = document.createElement('pre');
          pre.textContent = src.text;
          tpl.content.appendChild(pre);
        }
      } else {
        tpl.setAttribute('data-payload-index-only', 'true');
      }
      container.appendChild(tpl);
    }
  }

  function renderRoundDetailFromJson(round, roundId, row) {
    round = round || {};
    var calls = Array.isArray(round.calls) ? round.calls : [];
    var toolCallIds = Array.isArray(round.toolCallIds) ? round.toolCallIds : [];
    var tools = Array.isArray(round.tools) ? round.tools : [];
    var assistantTexts = round.callAssistantTexts || {};
    var mainCalls = calls.filter(function (call) { return !call || call.scope !== 'subagent'; });
    var subagentCalls = calls.filter(function (call) { return call && call.scope === 'subagent'; });
    var html = '<div class="sd-round-detail"><div class="sd-timeline">';
    if (!calls.length) {
      html += '<div class="sd-card-empty">No normalized calls returned by the round API.</div>';
    } else {
      mainCalls.forEach(function (call, idx) {
        var callText = assistantTexts[call.callId] || '';
        html += renderAssistantTimelineItem(roundId, call, idx + 1, callText, toolsForCall(call, tools).length);
        html += renderToolTimelineItems(toolsForCall(call, tools), roundId, false);
      });
      if (!mainCalls.length && toolCallIds.length) {
        html += renderToolTimelineItems(tools, roundId, false);
      }
      html += renderSubagentTimeline(subagentCalls, tools, roundId, assistantTexts);
    }
    html += '</div></div>';
    return html;
  }

  function contentPayloadButton(payloadId, kind, title, label) {
    return '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm" data-action="open-payload" data-payload-id="'
      + escapeRoundHtml(payloadId) + '" data-payload-kind="' + escapeRoundHtml(kind)
      + '" data-payload-title="' + escapeRoundHtml(title) + '">' + escapeRoundHtml(label) + '</button>';
  }

  function renderAssistantTimelineItem(roundId, call, callIndex, callText, toolCount) {
    call = call || {};
    var usage = call.usage || {};
    var callLabel = call.callKey || ('C' + callIndex);
    var displayText = callText || (toolCount ? toolCount + ' 个工具指令 · 响应文本未记录' : '响应文本未记录');
    var timeDisplay = localTime(call.timestamp) || '未记录';
    var tokenDisplay = usage.total > 0 ? escapeRoundHtml(compactTokens(usage.total)) + ' tokens' : '未记录';
    var scopeDisplay = call.scope === 'subagent' ? '子 agent' : '主会话';
    var callTitle = '本地响应记录 ' + callLabel + ' · ' + scopeDisplay + ' · callId: ' + (call.callId || '未记录') + '；不代表独立 provider 请求';
    var payloadTitle = 'R' + roundId + ' · ' + callLabel;
    return '<div class="sd-timeline-item" data-timeline-item="assistant_text">'
      + '<span class="sd-timeline-dot sd-timeline-dot--text"></span>'
      + '<section class="sd-tool-group sd-tool-group--flat">'
      + '<div class="sd-tool-row sd-event-row sd-event-row--compact sd-event-row--assistant_text">'
      + '<span class="sd-tool-kind">' + (callText ? 'TEXT' : 'RESPONSE') + '</span>'
      + '<span class="sd-tool-cmd sd-event-row__text" title="' + escapeRoundHtml(displayText) + '">' + escapeRoundHtml(displayText) + '</span>'
      + '<span class="sd-tool-result" title="' + escapeRoundHtml(call.model || '模型未记录') + '">' + escapeRoundHtml(call.model || '模型未记录') + '</span>'
      + '<span class="sd-tool-time">' + escapeRoundHtml(timeDisplay) + '</span>'
      + '<span class="sd-exit sd-exit--muted" title="' + escapeRoundHtml(callTitle) + '">记录 ' + escapeRoundHtml(callLabel) + '</span>'
      + '<span class="sd-tool-tokens">' + tokenDisplay + '</span>'
      + '<span class="sd-tool-actions">'
      + contentPayloadButton(payloadIdFor(call, 'req'), payloadKindFor(call, 'req'), payloadTitle + ' · Request', 'Request')
      + contentPayloadButton(payloadIdFor(call, 'resp'), payloadKindFor(call, 'resp'), payloadTitle + ' · Response', 'Response')
      + '</span></div></section></div>';
  }

  function renderToolTimelineItems(tools, roundId, isSubagent) {
    if (!tools || !tools.length) return '';
    return tools.map(function (tool, idx) {
      var status = toolStatusLabel(tool);
      var failed = isFailedTool(tool);
      var preview = tool.inputPreview || '';
      var cmdText = preview || '输入未记录';
      var cmdTitle = (preview ? tool.name + ': ' : '') + cmdText;
      var timeText = tool.durationMs != null ? durationLabel(tool.durationMs) : '未记录';
      var scopeText = isSubagent ? '子 agent' : '主会话';
      return '<div class="sd-timeline-item" data-timeline-item="tool-call">'
        + '<span class="sd-timeline-dot sd-timeline-dot--tool"></span>'
        + '<section class="sd-tool-group sd-tool-group--flat">'
        + '<div class="sd-tool-row' + (failed ? ' sd-tool-row--failed sd-tool-row--fail' : '') + '" data-status="' + (failed ? 'failed' : 'ok') + '" data-tool-call-id="' + escapeRoundHtml(tool.toolCallId || '') + '">'
        + '<span class="sd-tool-kind">' + escapeRoundHtml(toolKind(tool.name)) + '</span>'
        + '<span class="sd-tool-cmd" title="' + escapeRoundHtml(cmdTitle) + '">' + escapeRoundHtml(cmdText) + '</span>'
        + '<span class="sd-tool-result' + (failed ? ' sd-tool-result--failed sd-tool-result--fail' : '') + '" title="' + escapeRoundHtml(status) + '">' + escapeRoundHtml(status) + '</span>'
        + '<span class="sd-tool-time">' + escapeRoundHtml(timeText) + '</span>'
        + '<span class="sd-exit' + (failed ? ' sd-exit--err' : '') + '">' + escapeRoundHtml(scopeText) + '</span>'
        + '<span class="sd-tool-tokens" title="未记录此工具的独立 token 用量；请查看模型调用归因">无独立 token</span>'
        + '<span class="sd-tool-actions">'
        + contentPayloadButton('tool:input:' + (tool.toolCallId || ''), 'tool_input', (tool.name || 'Tool') + ' · Input', 'Input')
        + contentPayloadButton('tool:result:' + (tool.toolCallId || ''), 'tool_result', (tool.name || 'Tool') + ' · Result', 'Result')
        + '</span>'
        + '</div></section></div>';
    }).join('');
  }

  function renderSubagentTimeline(subagentCalls, tools, roundId, assistantTexts) {
    if (!subagentCalls.length) return '';
    var groups = groupSubagentCalls(subagentCalls);
    var html = '';
    Object.keys(groups).forEach(function (subagentId) {
      var groupCalls = groups[subagentId];
      var groupTools = tools.filter(function (tool) {
        return groupCalls.some(function (call) { return toolBelongsToCall(tool, call); });
      });
      var totalTokens = groupCalls.reduce(function (sum, call) {
        return sum + Number(call && call.usage && call.usage.total || 0);
      }, 0);
      html += '<div class="sd-subagent-nested"><div class="sd-timeline-item" data-timeline-item="subagent">'
        + '<span class="sd-timeline-dot sd-timeline-dot--sub"></span>'
        + '<section class="sd-subagent" data-subagent-block data-subagent-id="' + escapeRoundHtml(subagentId) + '">'
        + '<div class="sd-subagent__head">'
        + '<span class="sd-subagent__title">Subagent</span>'
        + '<span class="sd-pill sd-pill--model sd-pill--sm">独立上下文</span>'
        + '<span class="sd-pill sd-pill--ok sd-pill--sm">completed</span>'
        + '<span class="sd-subagent__meta">' + escapeRoundHtml(String(groupTools.length)) + ' tools, ' + escapeRoundHtml(compactTokens(totalTokens)) + ' tokens</span>'
        + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm sd-subagent__toggle" data-action="toggle-subagent-rounds" aria-expanded="false">Expand all</button>'
        + '</div><div class="sd-sub-rounds">';
      groupCalls.forEach(function (call, idx) {
        html += renderSubRound(call, toolsForCall(call, tools), subagentId, idx + 1, assistantTexts || {});
      });
      html += '</div></section></div></div>';
    });
    return html;
  }

  function renderSubRound(call, tools, subagentId, indexInSubagent, assistantTexts) {
    var usage = call.usage || {};
    var sr = subRoundLabel(call, indexInSubagent);
    var requestId = 'sub-' + subagentId + '-IX' + indexInSubagent + '-request-attribution';
    var responseId = 'sub-' + subagentId + '-IX' + indexInSubagent + '-response-attribution';
    var callText = (assistantTexts || {})[call.callId] || (tools.length ? tools.length + ' 个工具指令' : '响应文本未记录');
    return '<div class="sd-sub-round" data-sub-round-id="' + escapeRoundHtml(String(indexInSubagent)) + '" data-sub-round-open="false">'
      + '<div class="sd-sub-round__summary" data-sub-round-toggle>'
      + '<button type="button" class="sd-sub-round__toggle" data-action="toggle-sub-round" aria-expanded="false" aria-label="Toggle subround ' + escapeRoundHtml(sr) + '"><span aria-hidden="true">›</span></button>'
      + '<span class="sd-sub-id">' + escapeRoundHtml(sr) + '</span>'
      + '<span class="sd-sub-title" title="' + escapeRoundHtml(callText) + '">' + escapeRoundHtml(callText) + '</span>'
      + '<span class="sd-attribution-actions sd-attribution-actions--subround" aria-label="内容与 Token 归因">'
      + contentPayloadButton(payloadIdFor(call, 'req'), payloadKindFor(call, 'req'), 'Subagent · Request', 'Request')
      + contentPayloadButton(payloadIdFor(call, 'resp'), payloadKindFor(call, 'resp'), 'Subagent · Response', 'Response')
      + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm sd-attr-btn sd-attr-btn--warn" data-action="open-payload" data-payload-id="' + escapeRoundHtml(requestId) + '" data-payload-kind="llm.request_attribution" data-payload-title="Subagent · Request Attribution">输入归因</button> '
      + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm sd-attr-btn sd-attr-btn--warn" data-action="open-payload" data-payload-id="' + escapeRoundHtml(responseId) + '" data-payload-kind="llm.response_attribution" data-payload-title="Subagent · Response Attribution">输出归因</button>'
      + '</span>'
      + '<span class="sd-sub-time">' + escapeRoundHtml(localTime(call.timestamp) || '未记录') + '</span>'
      + tokenbarSub(usage)
      + '</div><div class="sd-sub-steps" data-sub-round-steps hidden>'
      + renderToolTimelineItems(tools, '', true)
      + '</div></div>';
  }

  function rowText(row, selector) {
    var el = row && row.querySelector ? row.querySelector(selector) : null;
    return el ? el.textContent.trim() : '';
  }

  function groupSubagentCalls(calls) {
    var groups = {};
    calls.forEach(function (call) {
      var id = subagentId(call);
      if (!groups[id]) groups[id] = [];
      groups[id].push(call);
    });
    return groups;
  }

  function subagentId(call) {
    var explicit = call && call.subagentId;
    if (explicit) return String(explicit);
    var callId = call && call.callId ? String(call.callId) : 'subagent';
    return callId.replace(/-SR\d+$/, '');
  }

  function subRoundLabel(call, fallbackIndex) {
    var callId = call && call.callId ? String(call.callId) : '';
    var match = callId.match(/-SR(\d+)$/);
    return 'SR' + (match ? match[1] : fallbackIndex);
  }

  function toolsForCall(call, tools) {
    if (!call) return [];
    return (tools || []).filter(function (tool) { return toolBelongsToCall(tool, call); });
  }

  function toolBelongsToCall(tool, call) {
    if (!tool || !call) return false;
    if (tool.declaredByCallId) return tool.declaredByCallId === call.callId;
    // 消费先前结果不代表重新执行；声明身份缺失时只使用 response 边。
    var ids = Array.isArray(call.responseToolCallIds) ? call.responseToolCallIds : [];
    return ids.indexOf(tool.toolCallId) !== -1;
  }

  function isFailedTool(tool) {
    if (!tool) return false;
    if (tool.exitCode != null && Number(tool.exitCode) !== 0) return true;
    var status = String(tool.status || '').trim().toLowerCase();
    return Boolean(status) && status !== 'ok' && status !== 'success' && status !== 'completed';
  }

  function toolKind(name) {
    var value = String(name || 'tool').replace(/[^A-Za-z]/g, '').toUpperCase();
    return (value || 'TOOL').slice(0, 4);
  }

  function toolStatusLabel(tool) {
    if (!tool) return '—';
    if (tool.status) return tool.status;
    if (tool.exitCode != null) return 'exit ' + tool.exitCode;
    return 'completed';
  }

  function durationLabel(ms) {
    var value = Number(ms || 0);
    if (!Number.isFinite(value) || value < 0) return '未记录';
    if (value < 1000) return value + ' ms';
    return (value / 1000).toFixed(value < 10000 ? 1 : 0) + 's';
  }

  function localTime(value) {
    if (!value) return '';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  function compactTokens(value) {
    var n = Number(value || 0);
    if (typeof formatCompactToken === 'function') return formatCompactToken(n);
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(Math.round(n));
  }

  function tokenbarSub(usage) {
    usage = usage || {};
    var total = Number(usage.total || 0);
    var fresh = pct(usage.fresh, total);
    var read = pct(usage.cacheRead, total);
    var write = pct(usage.cacheWrite, total);
    var out = pct(usage.output, total);
    return '<span class="sd-sub-tokenbar" tabindex="0"><span class="tokenbar-sub" aria-hidden="true">'
      + '<span class="fresh" style="--segment-width:' + fresh + '%"></span>'
      + '<span class="read" style="--segment-width:' + read + '%"></span>'
      + '<span class="write" style="--segment-width:' + write + '%"></span>'
      + '<span class="out" style="--segment-width:' + out + '%"></span></span>'
      + '<div class="token-tooltip" aria-hidden="true"><div class="token-tooltip__title">Token Breakdown</div>'
      + '<div class="token-tooltip__row"><span>Total</span><span class="token-tooltip__value">' + escapeRoundHtml(compactTokens(total)) + '</span></div>'
      + '</div></span>';
  }

  function pct(value, total) {
    if (!total) return 0;
    return Math.max(0, Math.min(100, Math.round((Number(value || 0) / total) * 1000) / 10));
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
