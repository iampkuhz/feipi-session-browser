  /* ── Lazy load round detail from API ── */

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

    // Insert loading indicator using DOM APIs
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
        // Remove loading row
        if (loadingRow && loadingRow.parentNode) loadingRow.parentNode.removeChild(loadingRow);

        // Inject the expanded row HTML after the summary row
        var detailRow = document.createElement('tr');
        detailRow.className = 'expanded-row';
        detailRow.id = 'round-' + roundId + '-detail';
        detailRow.setAttribute('data-trace-detail', '');
        var tdDetail = document.createElement('td');
        tdDetail.setAttribute('colspan', '6');
        detailRow.appendChild(tdDetail);
        setHtml(tdDetail, data.html);
        row.parentNode.insertBefore(detailRow, row.nextSibling);
        qsa(detailRow, '[data-sub-round-id]').forEach(function (subRound) {
          if (typeof syncSubRoundToggle === 'function') syncSubRoundToggle(subRound);
        });
        qsa(detailRow, '[data-subagent-block]').forEach(function (block) {
          if (typeof syncSubagentToggle === 'function') syncSubagentToggle(block);
        });

        // Mark as loaded
        row.setAttribute('data-detail-loaded', 'true');

        // Inject payload sources as <template> elements if present
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
          // Replace loading row content with error state using DOM APIs
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
