  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Lazy load round detail from API ──` */

  function getApiBase() {
    var meta = document.querySelector('meta[name="payload-api-base"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function lazyLoadRoundDetail(row, options, previousDetail) {
    if (row.pendingRoundDetail) return row.pendingRoundDetail;
    var roundId = row.getAttribute('data-round');
    if (!roundId) return null;
    var apiBase = getApiBase();
    if (!apiBase) return null;
    var url = apiBase.replace(/\/$/, '') + '/round/' + encodeURIComponent(roundId);
    var targeted = Boolean(options?.target);
    if (targeted) url += '?' + new URLSearchParams({ target: options.target, target_kind: options.targetKind });
    qsa(row.parentNode, '[data-loading-for="' + cssEscape(roundId) + '"]').forEach(function (stale) { stale.remove(); });

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Insert loading indicator using DOM APIs`
    var loadingRow = document.createElement('tr');
    loadingRow.className = 'sd-round-detail-loading';
    loadingRow.setAttribute('data-loading-for', roundId);
    var tdLoading = document.createElement('td');
    tdLoading.setAttribute('colspan', '6');
    var divLoading = document.createElement('div');
    divLoading.className = 'sd-loading-indicator';
    divLoading.textContent = 'Loading ' + roundDisplayLabel(roundId, row) + '...';
    tdLoading.appendChild(divLoading);
    loadingRow.appendChild(tdLoading);
    row.parentNode.insertBefore(loadingRow, row.nextSibling);

    setRoundOpen(row, true);

    row.pendingRoundDetail = readSessionContentPage(url)
      .then(function (data) {
        // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Remove loading row`
        if (loadingRow && loadingRow.parentNode) loadingRow.parentNode.removeChild(loadingRow);

        if (!row.isConnected || (options?.current && !options.current())) return;
        if (previousDetail) previousDetail.remove();

        // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Inject the expanded row HTML after the summary row`
        var detailRow = document.createElement('tr');
        detailRow.className = 'expanded-row';
        detailRow.hidden = !row.classList.contains('is-open') || !isRoundVisible(row);
        detailRow.id = 'round-' + roundId + '-detail';
        detailRow.setAttribute('data-trace-detail', '');
        var tdDetail = document.createElement('td');
        tdDetail.setAttribute('colspan', '6');
        detailRow.appendChild(tdDetail);
        setHtml(tdDetail, data.html || renderRoundDetailFromJson(data.round, roundId, row, data, true));
        row.parentNode.insertBefore(detailRow, row.nextSibling);
        tdDetail.addEventListener('change', function (event) {
          if (event.target.matches('[data-tool-kind-filter]')) applyToolKindFilter(tdDetail);
        });
        tdDetail.addEventListener('toggle', function (event) {
          if (event.target.matches('[data-tool-payload-pair]') && event.target.open) loadToolPayloadPair(event.target);
        }, true);
        qsa(detailRow, '[data-sub-round-id]').forEach(function (subRound) {
          if (typeof syncSubRoundToggle === 'function') syncSubRoundToggle(subRound);
        });
        qsa(detailRow, '[data-subagent-block]').forEach(function (block) {
          if (typeof syncSubagentToggle === 'function') syncSubagentToggle(block);
        });

        // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Mark as loaded`
        row.setAttribute('data-detail-loaded', 'true');
        setupRoundContentPages(tdDetail, data, roundId, row);
        if (targeted && (data.offset || data.toolOffset)) {
          var note = document.createElement('p');
          note.textContent = '定位片段 · 从'
            + (data.offset ? '调用记录 ' + (data.offset + 1) : '工具 ' + (data.toolOffset + 1)) + ' 开始 ';
          var first = document.createElement('button');
          first.type = 'button';
          first.className = 'sd-btn sd-btn--secondary sd-btn--sm';
          first.textContent = '查看此轮开头';
          first.onclick = function () {
            runReadingNavigation(function () { return lazyLoadRoundDetail(row, null, detailRow); });
          };
          note.append(first);
          tdDetail.prepend(note);
        }
        TokenProvenance.bindTooltips(tdDetail);

        // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Inject payload sources as <template> elements if present`
        if (data.payload_sources && data.payload_sources.length > 0) {
          injectPayloadSources(data.payload_sources);
        }
      })
      .catch(function (err) {
        if (targeted) {
          loadingRow.remove();
          if (!previousDetail && row.isConnected) setRoundOpen(row, false);
          throw err;
        }
        if (loadingRow && loadingRow.parentNode) {
          var msg;
          if (err.data && err.data.error) {
            msg = err.data.error;
          } else if (err.status) {
            msg = 'Failed to load round detail (HTTP ' + err.status + ')';
          } else {
            msg = err.message || 'Failed to load round detail';
          }
          // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Replace loading row content with error state using DOM APIs`
          while (loadingRow.firstChild) loadingRow.removeChild(loadingRow.firstChild);
          var tdError = document.createElement('td');
          tdError.setAttribute('colspan', '6');
          var divError = document.createElement('div');
          divError.className = 'sd-round-detail-error';
          var spanError = document.createElement('span');
          spanError.textContent = roundDisplayLabel(roundId, row) + ' load failed: ' + msg;
          divError.appendChild(spanError);
          var btnRetry = document.createElement('button');
          btnRetry.type = 'button';
          btnRetry.className = 'sd-btn sd-btn--primary sd-btn--sm';
          btnRetry.setAttribute('data-action', 'retry-round');
          btnRetry.setAttribute('data-round', roundId);
          btnRetry.textContent = /refresh/i.test(msg) ? 'Refresh page' : 'Retry';
          if (/refresh/i.test(msg)) {
            btnRetry.setAttribute('data-action', 'load-content-page');
            btnRetry.loadContentPage = function () { window.location.reload(); };
          }
          divError.appendChild(btnRetry);
          tdError.appendChild(divError);
          loadingRow.appendChild(tdError);
        }
        if (row.isConnected && !previousDetail) setRoundOpen(row, false);
        throw err;
      }).finally(function () { row.pendingRoundDetail = null; });
    return row.pendingRoundDetail;
  }

  function setupRoundContentPages(target, first, roundId, row) {
    var loaded = Number(first.offset || 0) + (first.round && first.round.calls || []).length;
    var memberPager = null;
    var base = getApiBase().replace(/\/$/, '') + '/round/' + encodeURIComponent(roundId);
    function pageUrl(memberCursor, toolCursor) {
      var params = new URLSearchParams();
      if (memberCursor) params.set('cursor', memberCursor);
      if (toolCursor) params.set('tool_cursor', toolCursor);
      return base + (params.toString() ? '?' + params.toString() : '');
    }
    function toolsPager(data, memberCursor, pageTarget) {
      var toolCount = Number(data.toolOffset || 0) + (data.round && data.round.tools || []).length;
      var pager = null;
      function update(part) {
        pager = contentPager(pageTarget, 'round-tools', toolCount, part.toolTotal ?? toolCount, part.nextToolCursor, function (cursor) {
          return readSessionContentPage(pageUrl(memberCursor, cursor)).then(function (next) {
            if (!pageTarget.isConnected) return;
            var tools = next.round && next.round.tools || [];
            tools.forEach(function (tool) {
              var owner = tool.declaredByCallId || '';
              var actions = qs(pageTarget, '[data-call-actions="' + cssEscape(owner) + '"]');
              var block = document.createElement('div');
              setMarkup(block, renderToolTimelineItems([tool], roundId, tool.scope === 'subagent'));
              if (actions) {
                actions.append(...block.children);
                var call = qs(pageTarget, '[data-execution-call="' + cssEscape(owner) + '"]');
                var preview = call && qs(call, '[data-action-summary]');
                if (preview) {
                  var summary = toolResponsePreview(qsa(actions, '[data-tool-execution-kind]').map(function (item) {
                    return { executionKind: item.dataset.toolExecutionKind };
                  }));
                  preview.textContent = summary;
                  preview.title = summary;
                  var kind = qs(call, '.sd-tool-kind');
                  if (kind && call.matches('[data-timeline-item="assistant_text"]')) kind.textContent = 'TOOLS';
                }
              } else pageTarget.insertBefore(block, pager);
            });
            applyToolKindFilter(target);
            toolCount += tools.length;
            update(next);
          });
        }, pager);
      }
      if (data.nextToolCursor || data.toolsComplete === false) update(data);
    }
    function membersPager(data) {
      memberPager = contentPager(target, 'round-members', loaded, data.total ?? loaded, data.nextCursor, function (cursor) {
        return readSessionContentPage(pageUrl(cursor, '')).then(function (next) {
          if (!target.isConnected) return;
          var block = document.createElement('div');
          setMarkup(block, renderRoundDetailFromJson(next.round, roundId, row, next));
          target.insertBefore(block, memberPager);
          TokenProvenance.bindTooltips(block);
          loaded += (next.round && next.round.calls || []).length;
          toolsPager(next, cursor, block);
          applyToolKindFilter(target);
          membersPager(next);
        });
      }, memberPager);
    }
    toolsPager(first, first.memberCursor || '', target);
    if (first.nextCursor) membersPager(first);
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

  function renderRoundDetailFromJson(round, roundId, row, page, fresh) {
    round = round || {};
    var calls = Array.isArray(round.calls) ? round.calls : [];
    var toolCallIds = Array.isArray(round.toolCallIds) ? round.toolCallIds : [];
    var tools = Array.isArray(round.tools) ? round.tools : [];
    var assistantTexts = round.callAssistantTexts || {};
    var mainCalls = calls.filter(function (call) { return !call || call.scope !== 'subagent'; });
    var subagentCalls = calls.filter(function (call) { return call && call.scope === 'subagent'; });
    var callCount = Math.max(Number(row.dataset.roundCallCount || 0), page?.total ?? calls.length);
    var single = callCount === 1;
    var parentSummary = row.querySelector('.summary-title')?.textContent.trim();
    var html = '<div class="sd-round-detail">';
    if (tools.length && (fresh || !row.nextElementSibling?.querySelector('[data-tool-kind-filter]'))) {
      html += '<label class="ui-select sd-tool-filter"><span class="ui-select__label">工具类别</span><select class="ui-select__control" data-tool-kind-filter>'
        + '<option value="">全部</option>' + Array.from(new Set(tools.map(toolCategory)))
          .map(function (kind) { return '<option value="' + kind + '">' + toolCategoryLabel(kind) + '</option>'; }).join('')
        + '</select></label>';
    }
    html += '<div class="sd-timeline">';
    if (!calls.length) {
      var inputOnly = callCount === 0 && row.getAttribute('data-is-user-input') === 'true';
      var inputAvailable = inputOnly && row.getAttribute('data-observed-input-available') === 'true';
      html += '<div class="sd-card-empty">' + (inputAvailable
        ? '输入原文见本轮入口。'
        : inputOnly ? '此轮没有可展示的输入正文或模型调用记录。'
        : 'No normalized calls returned by the round API.') + '</div>';
    } else {
      var hasChildContent = subagentCalls.length > 0;
      mainCalls.forEach(function (call, idx) {
        var callText = assistantTexts[call.callId] || '';
        if (single && callText.trim() === parentSummary) callText = '';
        var declared = toolsForCall(call, tools);
        var phase = callPhaseLabel(call);
        var showCallRow = Boolean(callText || phase || (!single && !declared.length));
        if (showCallRow) html += renderAssistantTimelineItem(roundId, call, idx + 1, callText, declared, single, phase);
        hasChildContent ||= showCallRow || declared.length > 0;
        var toolRows = renderToolTimelineItems(declared, roundId, false, call);
        html += '<div class="sd-call-tools" data-call-tools="' + escapeRoundHtml(call.callId)
          + '" data-call-actions="' + escapeRoundHtml(call.callId) + '"'
          + (declared.length && !showCallRow ? ' data-execution-call="' + escapeRoundHtml(call.callId) + '"' : '') + '>'
          + (declared.length > 1 ? '<div class="sd-call-tools__label">同一调用</div>' : '')
          + (declared.length && !showCallRow && !single ? toolOnlyCallAccess(call, roundId) : '')
          + toolRows + '</div>';
      });
      if (!mainCalls.length && toolCallIds.length) {
        var unownedTools = tools.filter(function (tool) {
          return !calls.some(function (call) { return toolBelongsToCall(tool, call); });
        });
        html += renderToolTimelineItems(unownedTools, roundId, false);
        hasChildContent ||= unownedTools.length > 0;
      }
      html += renderSubagentTimeline(subagentCalls, tools, roundId, assistantTexts, single);
      if (!hasChildContent) html += '<div class="sd-card-empty" data-execution-call="'
        + escapeRoundHtml(calls[0].callId || '') + '">没有额外事件；调用原文见本轮入口。</div>';
    }
    html += '</div></div>';
    return html;
  }

  function contentPayloadButton(payloadId, kind, title, label, attributionPath) {
    return '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm" data-action="open-payload" data-payload-id="'
      + escapeRoundHtml(payloadId) + '" data-payload-kind="' + escapeRoundHtml(kind)
      + '" data-payload-title="' + escapeRoundHtml(title) + '"'
      + ' title="' + escapeRoundHtml({llm_request: '模型 Request：可能消费此前工具结果，不代表重新执行', llm_response: '模型 Response：助手文本及工具调用声明；执行输出见 Tool Result', tool_input: 'Tool Input：工具命令与参数', tool_result: 'Tool Result：工具执行结果'}[kind] || title) + '"'
      + (attributionPath ? ' data-attribution-path="' + escapeRoundHtml(attributionPath) + '"' : '')
      + '>' + escapeRoundHtml(label) + '</button>';
  }

  function memberAttributionPath(roundId, callId, kind) {
    return '/attribution/' + encodeURIComponent(roundId) + '/1/' + kind + '?call_id=' + encodeURIComponent(callId);
  }

  function memberPayloadButtons(call, roundId, payloadTitle) {
    if (!call.callId) return '';
    return ['req', 'resp'].map(function (side) {
      var kind = side === 'req' ? 'request' : 'response';
      var label = side === 'req' ? 'Request' : 'Response';
      var path = memberAttributionPath(roundId, call.callId, kind);
      return contentPayloadButton(payloadIdFor(call, side), payloadKindFor(call, side), payloadTitle + ' · ' + label, label, path);
    }).join('');
  }

  var toolCategoryLabels = new Map(Object.entries({
    read: '读取', search: '搜索', write: '写入', edit: '编辑', shell: 'Shell', python: 'Python',
    javascript: 'JavaScript', wait: '等待', stop: '终止', 'process-input': '进程输入',
    agent: 'Agent 调度', web: '网页', tool: '其他工具'
  }));

  function toolCategory(tool) {
    return toolCategoryLabels.has(tool.executionKind) ? tool.executionKind : 'tool';
  }

  function toolCategoryLabel(kind) {
    return toolCategoryLabels.get(kind);
  }

  function toolResponsePreview(tools) {
    var counts = new Map();
    tools.forEach(function (tool) {
      var kind = toolCategory(tool);
      counts.set(kind, (counts.get(kind) || 0) + 1);
    });
    return Array.from(counts, function (entry) {
      return toolCategoryLabel(entry[0]) + (entry[1] > 1 ? ' × ' + entry[1] : '');
    }).join(' · ');
  }

  function callPhaseLabel(call) {
    return call.phaseLabel || '';
  }

  function callTimes(call) {
    return timeEvidence(localTime(call.timestamp), '时间', 'sd-time-point')
      + timeEvidence(durationFromMillis(call.durationMs), '耗时', 'sd-time-duration');
  }

  function toolOnlyCallAccess(call, roundId) {
    var label = call.callKey || call.callId;
    return '<div class="sd-call-sources"><b>' + escapeRoundHtml(label) + '</b>'
      + callTimes(call)
      + '<span title="本次调用 Token">' + escapeRoundHtml(TokenProvenance.amount(call.usage || {}, 'total', compactTokens)) + '</span>'
      + memberPayloadButtons(call, roundId, roundDisplayLabel(roundId) + ' · ' + label) + '</div>';
  }

  function renderAssistantTimelineItem(roundId, call, callIndex, callText, tools, single, phase) {
    call = call || {};
    var usage = call.usage || {};
    var callLabel = call.callKey || ('C' + callIndex);
    var displayText = [phase, callText || (!phase ? toolResponsePreview(tools) : '')].filter(Boolean).join(' · ')
      || '模型调用原文见本行入口';
    var tokenDisplay = escapeRoundHtml(TokenProvenance.amount(usage, 'total', compactTokens));
    var scopeDisplay = call.scope === 'subagent' ? '子 agent' : '主会话';
    var callTitle = '本地响应记录 ' + callLabel + ' · ' + scopeDisplay + ' · callId: ' + (call.callId || '未记录') + '；不代表独立 provider 请求';
    var payloadTitle = roundDisplayLabel(roundId) + ' · ' + callLabel;
    return '<div class="sd-timeline-item" data-timeline-item="assistant_text" data-execution-call="' + escapeRoundHtml(call.callId || '') + '">'
      + '<span class="sd-timeline-dot sd-timeline-dot--text"></span>'
      + '<section class="sd-tool-group sd-tool-group--flat">'
      + '<div class="sd-tool-row sd-tool-row--quiet sd-event-row sd-event-row--compact sd-event-row--assistant_text">'
      + '<span class="sd-tool-kind">' + (callText ? 'TEXT' : tools.length ? 'TOOLS' : 'RESPONSE') + '</span>'
      + '<span class="sd-tool-cmd sd-event-row__text"' + (callText || phase ? '' : ' data-action-summary') + ' title="' + escapeRoundHtml(displayText) + '">'
      + (!single && call.callKey ? '<b class="sd-call-identity">' + escapeRoundHtml(call.callKey) + '</b> · ' : '')
      + escapeRoundHtml(displayText) + '</span>'
      + '<span class="sd-tool-result"></span>'
      + (single ? '<span></span><span></span>' : callTimes(call))
      + '<span class="sd-exit sd-exit--muted" title="' + escapeRoundHtml(callTitle) + '">' + scopeDisplay + '</span>'
      + (single ? '<span></span>' : '<span class="sd-tool-tokens" tabindex="0" data-token-breakdown="' + escapeRoundHtml(JSON.stringify({ tokens: usage, providerOnly: true })) + '" title="' + escapeRoundHtml(TokenProvenance.note(usage) || '调用 Token') + '">' + tokenDisplay + '</span>')
      + '<span class="sd-tool-actions">'
      + (single ? '' : memberPayloadButtons(call, roundId, payloadTitle))
      + '</span></div></section></div>';
  }

  function applyToolKindFilter(container) {
    var filter = qs(container, '[data-tool-kind-filter]');
    if (!filter) return;
    var available = new Set(Array.from(filter.options, function (option) { return option.value; }));
    qsa(container, '[data-tool-execution-kind]').forEach(function (item) {
      var kind = item.getAttribute('data-tool-execution-kind');
      if (!available.has(kind) && toolCategoryLabels.has(kind)) {
        filter.add(new Option(toolCategoryLabel(kind), kind));
        available.add(kind);
      }
      item.hidden = Boolean(filter.value) && filter.value !== kind;
    });
    qsa(container, '[data-call-tools]').forEach(function (group) {
      group.hidden = !group.querySelector('[data-tool-execution-kind]:not([hidden])');
    });
  }

  function observedToolTime(tool) {
    var nanos = tool.observation?.durationNanos;
    if (Number.isFinite(nanos) && nanos >= 0) return durationLabel(nanos / 1e9);
    return durationLabel(Number.isFinite(tool.durationMs) ? tool.durationMs / 1000 : null);
  }

  function renderToolTimelineItems(tools, roundId, isSubagent, call) {
    if (!tools || !tools.length) return '';
    return tools.map(function (tool, index) {
      var status = toolStatusLabel(tool);
      var failed = isFailedTool(tool);
      var timeText = observedToolTime(tool);
      var toolTimestamp = localTime(tool.timestamp);
      var scopeText = isSubagent ? '子 Agent' : '';
      var executionKind = toolCategory(tool);
      var kindLabel = toolCategoryLabel(executionKind);
      var action = [tool.name !== kindLabel ? tool.name : '', tool.inputPreview].filter(Boolean).join(' · ');
      return '<div class="sd-timeline-item" data-timeline-item="tool-call" data-tool-execution-kind="' + escapeRoundHtml(executionKind) + '">'
        + '<span class="sd-timeline-dot sd-timeline-dot--tool"></span>'
        + '<section class="sd-tool-group sd-tool-group--flat">'
        + '<div class="sd-tool-row' + (failed ? ' sd-tool-row--failed sd-tool-row--fail' : '')
        + (status ? '' : ' sd-tool-row--quiet') + '" data-status="' + (failed ? 'failed' : (status ? 'observed' : 'unknown')) + '" data-tool-call-id="' + escapeRoundHtml(tool.toolCallId || '') + '" data-declaring-call-id="' + escapeRoundHtml(tool.declaredByCallId || '') + '" data-declaring-call-scope="' + (isSubagent || tool.scope === 'subagent' ? 'subagent' : 'main') + '"'
        + (call?.callKey ? ' data-declaring-call-key="' + escapeRoundHtml(call.callKey) + '"' : '')
        + (toolTimestamp ? ' data-tool-observed-timestamp="' + escapeRoundHtml(toolTimestamp) + '"' : '')
        + (tool.name ? ' data-tool-visible-name="' + escapeRoundHtml(tool.name) + '"' : '')
        + (timeText !== '未记录' ? ' data-tool-observed-time="' + escapeRoundHtml(timeText) + '"' : '')
        + ' title="声明调用: ' + escapeRoundHtml(tool.declaredByCallId || '未记录') + '">'
        + '<span class="sd-tool-kind">' + (tools.length > 1 ? String(index + 1) : '') + '</span>'
        + '<span class="sd-tool-cmd" title="' + escapeRoundHtml(action || kindLabel) + '"><strong class="sd-action-category">'
        + escapeRoundHtml(kindLabel) + '</strong>' + (action ? ' · ' + escapeRoundHtml(action) : '') + '</span>'
        + '<span class="sd-tool-result' + (failed ? ' sd-tool-result--failed sd-tool-result--fail' : '') + '" title="状态：' + escapeRoundHtml(status) + '">' + escapeRoundHtml(status) + '</span>'
        + timeEvidence(toolTimestamp, '发起时间', 'sd-time-point', '来源记录的工具声明时间，非执行器启动时间')
        + timeEvidence(timeText, '耗时', 'sd-time-duration')
        + '<span' + (scopeText ? ' class="sd-exit' + (failed ? ' sd-exit--err' : '') + '"' : '') + '>' + escapeRoundHtml(scopeText) + '</span>'
        + '<span class="sd-tool-tokens"></span><span class="sd-tool-actions">'
        + (tool.resultObserved === true && tool.toolCallId
          ? contentPayloadButton('tool:result:' + tool.toolCallId, 'tool_result', (tool.name || 'Tool') + ' · Result', 'Result', '') : '')
        + '</span></div><details class="sd-tool-payload-pair" data-tool-payload-pair data-tool-id="' + escapeRoundHtml(tool.toolCallId || '') + '" data-result-observed="' + (tool.resultObserved === true) + '">'
        + '<summary>工具原文' + (tool.resultObserved !== true ? ' · 无结果' : '') + '</summary>' + toolObservationHtml(tool) + '<div class="sd-tool-payload-grid"></div></details></section></div>';
    }).join('');
  }

  function loadToolPayloadPair(details) {
    if (details.getAttribute('data-loaded') === 'true') return;
    details.setAttribute('data-loaded', 'true');
    var grid = details.querySelector('.sd-tool-payload-grid');
    ['input', 'result'].forEach(function (side) {
      var section = document.createElement('section');
      var title = document.createElement('h4');
      title.textContent = side === 'input' ? 'Tool Input' : 'Tool Result';
      var body = document.createElement('pre');
      body.textContent = '正在加载…';
      section.append(title, body);
      grid.appendChild(section);
      if (side === 'result' && details.getAttribute('data-result-observed') === 'false') {
        body.textContent = '结果未记录';
        return;
      }
      function load() {
        var tool = details.getAttribute('data-tool-id');
        var id = 'tool:' + side + ':' + tool;
        var detailRow = details.closest('[data-trace-detail]');
        var round = detailRow && (detailRow.id.match(/^round-(\d+)-detail$/) || [])[1];
        return readSessionContentPage(getApiBase().replace(/\/$/, '') + '/payload/' + encodeURIComponent(id), {
          kind: 'tool-result', tool: tool, round: round,
          valid: function () {
            return round && tool && details.getAttribute('data-result-observed') === 'true'
              && details.open && details.contains(document.activeElement) && !details.closest('[hidden]');
          }
        })
          .then(function (data) {
            body.textContent = data.content || data.text || '内容未记录';
            if (side === 'input' && (data.content || data.text)) {
              var action = document.createElement('div');
              var label = side === 'input' ? 'Input' : 'Result';
              setMarkup(action, contentPayloadButton(id, 'tool_' + side, title.textContent, label, ''));
              title.after(action);
            }
          })
          .catch(function (error) {
            body.textContent = error.message;
            var retry = document.createElement('button');
            retry.className = 'sd-btn sd-btn--secondary sd-btn--sm';
            retry.textContent = /refresh/i.test(error.message) ? 'Refresh page' : 'Retry';
            retry.addEventListener('click', function () {
              retry.remove();
              if (/refresh/i.test(error.message)) window.location.reload();
              else load();
            });
            section.appendChild(retry);
          });
      }
      load();
    });
  }

  function renderSubagentTimeline(subagentCalls, tools, roundId, assistantTexts, single) {
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
        + '<span class="sd-pill sd-pill--sm" data-subagent-state="unknown">状态未记录</span>'
        + '<span class="sd-subagent__meta">' + escapeRoundHtml(String(groupTools.length)) + ' tools'
        + (single ? '' : ', ' + escapeRoundHtml(TokenProvenance.total({ total: totalTokens }, compactTokens)) + ' tokens') + '</span>'
        + '<button type="button" class="sd-btn sd-btn--secondary sd-btn--sm sd-subagent__toggle" data-action="toggle-subagent-rounds" aria-expanded="false">Expand all</button>'
        + '</div><div class="sd-sub-rounds">';
      groupCalls.forEach(function (call, idx) {
        html += renderSubRound(call, toolsForCall(call, tools), idx + 1, assistantTexts || {}, roundId, single);
      });
      html += '</div></section></div></div>';
    });
    return html;
  }

  function renderSubRound(call, tools, indexInSubagent, assistantTexts, roundId, single) {
    var usage = call.usage || {};
    var sr = subRoundLabel(call, indexInSubagent);
    var callText = [callPhaseLabel(call), assistantTexts[call.callId] || toolResponsePreview(tools)].filter(Boolean).join(' · ')
      || (single ? '子 Agent' : '模型调用原文见本行入口');
    return '<div class="sd-sub-round" data-sub-round-id="' + escapeRoundHtml(String(indexInSubagent)) + '" data-execution-call="' + escapeRoundHtml(call.callId || '') + '" data-sub-round-open="false">'
      + '<div class="sd-sub-round__summary" data-sub-round-toggle>'
      + '<button type="button" class="sd-sub-round__toggle" data-action="toggle-sub-round" aria-expanded="false" aria-label="Toggle subround ' + escapeRoundHtml(sr) + '"><span aria-hidden="true">›</span></button>'
      + '<span class="sd-sub-id">' + escapeRoundHtml(sr) + '</span>'
      + '<span class="sd-sub-title"' + (assistantTexts[call.callId] ? '' : ' data-action-summary') + ' title="' + escapeRoundHtml(callText) + '">' + escapeRoundHtml(callText) + '</span>'
      + '<span class="sd-attribution-actions sd-attribution-actions--subround" aria-label="内容与 Token 归因">'
      + (single ? '' : memberPayloadButtons(call, roundId, 'Subagent · ' + sr))
      + '</span>'
      + (single ? '<span></span><span></span><span></span>' : callTimes(call) + tokenbarSub(usage))
      + '</div><div class="sd-sub-steps" data-sub-round-steps data-call-actions="' + escapeRoundHtml(call.callId || '') + '" hidden>'
      + renderToolTimelineItems(tools, roundId, true, call)
      + '</div></div>';
  }

  function roundDisplayLabel(roundId, row) {
    if (!row) row = Array.from(document.querySelectorAll('.round-row[data-round]')).find(function (candidate) {
      return candidate.getAttribute('data-round') === String(roundId);
    });
    return row && row.getAttribute('data-round-label') || '记录 ' + roundId;
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
    var exit = tool.observation?.exitCode ?? tool.exitCode;
    var status = String(tool.status || '').trim().toLowerCase();
    var explicit = String(tool.observation?.status || '').toLowerCase();
    return (exit != null && Number(exit) !== 0) || ['failed', 'error', 'cancelled'].includes(explicit)
      || (Boolean(status) && !['ok', 'success', 'completed', 'running', 'pending', 'queued'].includes(status));
  }

  function toolStatusLabel(tool) {
    if (!tool) return '';
    var exit = tool.observation?.exitCode ?? tool.exitCode;
    if (exit != null && Number(exit) !== 0) return '退出码 ' + exit;
    if (isFailedTool(tool)) return ({
      failed: '失败', error: '失败', cancelled: '已取消',
      text_heuristic_failure: '文本提示失败', tool_error: '工具报错'
    })[tool.status] || ({
      failed: '失败', error: '失败', cancelled: '已取消'
    })[tool.observation?.status] || '失败信号';
    return '';
  }

  function toolObservationHtml(tool) {
    var observed = tool.observation;
    if (!observed) return '';
    var facts = [observed.source, observed.kind, observed.status, observed.issue].filter(Boolean);
    if (observed.exitCode != null) facts.push('退出码 ' + observed.exitCode);
    return facts.length ? '<p class="sd-chart-note">' + escapeRoundHtml(facts.join(' · ')) + '</p>' : '';
  }

  function timeEvidence(value, label, className, note) {
    var recorded = value && value !== '未记录';
    return '<span class="' + className + '" data-clock-label="' + label + '" title="' + label + '：'
      + escapeRoundHtml(recorded ? value : '未记录') + (recorded && note ? '（' + note + '）' : '') + '">'
      + escapeRoundHtml(recorded ? value : '—') + '</span>';
  }

  function durationFromMillis(value) {
    return durationLabel(Number.isFinite(value) ? value / 1000 : null);
  }

  function durationLabel(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return '未记录';
    var tenths = Math.round(seconds * 10);
    if (seconds > 0 && tenths === 0) return '<0.1 秒';
    var minutes = Math.floor(tenths / 600);
    var secondsLabel = (tenths % 600) / 10 + ' 秒';
    return minutes > 0 ? minutes + ' 分 ' + secondsLabel : secondsLabel;
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
    if (n >= 1000000) return Number((n / 1000000).toFixed(1)) + 'M';
    if (n >= 1000) return Number((n / 1000).toFixed(1)) + 'K';
    return String(Math.round(n));
  }

  function tokenbarSub(usage) {
    usage = usage || {};
    var total = Number(usage.total || 0);
    var fresh = pct(usage.fresh, total);
    var read = pct(usage.cacheRead, total);
    var write = pct(usage.cacheWrite, total);
    var out = pct(usage.output, total);
    return '<span class="sd-sub-tokenbar" tabindex="0" data-token-breakdown="' + escapeRoundHtml(JSON.stringify({ tokens: usage, providerOnly: true })) + '"><span>' + escapeRoundHtml(TokenProvenance.total(usage, compactTokens)) + '</span><span class="tokenbar-sub" aria-hidden="true">'
      + '<span class="fresh" style="--segment-width:' + fresh + '%"></span>'
      + '<span class="read" style="--segment-width:' + read + '%"></span>'
      + '<span class="write" style="--segment-width:' + write + '%"></span>'
      + '<span class="out" style="--segment-width:' + out + '%"></span></span>'
      + '</span>';
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

  function escapeRoundHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch];
    });
  }
