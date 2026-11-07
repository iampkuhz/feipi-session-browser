/* 关联资源先暂存并核对索引代次，再更新页面；不修改全局请求函数。 */
(function () {
  'use strict';
  var HEADER = 'X-Session-Index-Generation';
  window.IndexSnapshot = {
    create: function () {
      var serial = 0;
      // SSR-only fields belong to this immutable document, not a later API batch.
      var documentGeneration = document.body.getAttribute('data-index-generation') || '';
      var generation = documentGeneration;
      var documentRecovery = false;
      var currentJobs = [];
      var hiddenRegions = null;
      var batchAlert = null;
      function quarantine(error, reloadDocument) {
        documentRecovery = documentRecovery || !!reloadDocument;
        if (!hiddenRegions) {
          var regions = Array.from(document.querySelectorAll('main'));
          if (!regions.length) regions = Array.from(document.body.children).filter(function (node) { return node.tagName !== 'SCRIPT'; });
          hiddenRegions = regions.map(function (node) { return { node: node, hidden: node.hidden }; });
          hiddenRegions.forEach(function (region) { region.node.hidden = true; });
        }
        if (batchAlert) batchAlert.remove();
        batchAlert = document.createElement('div');
        batchAlert.setAttribute('data-snapshot-batch-error', '');
        batchAlert.setAttribute('role', 'alert');
        batchAlert.appendChild(document.createTextNode('Page snapshot unavailable: ' + error.message + '. '));
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn';
        button.textContent = documentRecovery ? 'Reload entire page' : 'Retry entire page';
        button.addEventListener('click', function () {
          button.disabled = true;
          if (documentRecovery) { window.location.reload(); return; }
          run(currentJobs, false).finally(function () { button.disabled = false; });
        });
        batchAlert.appendChild(button);
        document.body.prepend(batchAlert);
      }
      function restore() {
        if (!hiddenRegions) return;
        hiddenRegions.forEach(function (region) { region.node.hidden = region.hidden; });
        hiddenRegions = null;
        if (batchAlert) batchAlert.remove();
        batchAlert = null;
        window.requestAnimationFrame(function () {
          window.dispatchEvent(new Event('resize'));
          window.dispatchEvent(new Event('index-snapshot-restored'));
        });
      }
      function errorNode(job, error, retry) {
        var key = job.key || job.url;
        var previous = Array.from(document.querySelectorAll('[data-snapshot-error]')).find(function (node) { return node.getAttribute('data-snapshot-error') === key; });
        if (previous) previous.remove();
        if (!error) return;
        if (job.error) { job.error(error, retry); return; }
        var node = document.createElement('div');
        node.setAttribute('data-snapshot-error', key);
        node.setAttribute('role', 'alert');
        node.appendChild(document.createTextNode('Unable to load ' + key + ': ' + error.message + '. '));
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn';
        button.textContent = 'Retry';
        button.addEventListener('click', function () { button.disabled = true; Promise.resolve(retry()).finally(function () { button.disabled = false; }); });
        node.appendChild(button);
        (document.querySelector('main') || document.body).prepend(node);
      }
      function read(job, expected) {
        var headers = { Accept: 'application/json' };
        if (expected) headers[HEADER] = expected;
        return fetch(job.url, { headers: headers, cache: 'no-store' }).then(function (response) {
          var stamp = response.headers.get(HEADER) || '';
          if (response.status === 409 || (expected && stamp && expected !== stamp)) return { changed: true, generation: stamp };
          if (!response.ok) return { error: new Error('HTTP ' + response.status), generation: stamp, unavailable: response.status === job.unavailableStatus };
          if (expected && !stamp) return { changed: true, generation: '' };
          return response.json().then(function (data) { return { data: data, generation: stamp }; })
            .catch(function (error) { return { error: error, generation: stamp }; });
        }).catch(function (error) { return { error: error, generation: '' }; });
      }
      function run(jobs, single) {
        if (documentRecovery) return Promise.resolve();
        var ticket = ++serial;
        function attempt(index) {
          return Promise.all(jobs.map(function (job) { return read(job, documentGeneration || (single ? generation : '')); })).then(function (parts) {
            if (ticket !== serial) return;
            // Never hydrate a new snapshot over SSR-only values from another document.
            // Missing stamps and 409 responses cannot downgrade a stamped document either.
            if (documentGeneration && parts.some(function (part) {
              return part.changed || (part.generation
                ? part.generation !== documentGeneration
                : !part.error || part.unavailable);
            })) {
              quarantine(new Error('Index generation no longer matches this document; reload the entire page'), true);
              return;
            }
            var successful = parts.filter(function (part) { return !part.error && !part.changed; });
            var stamps = successful.map(function (part) { return part.generation; });
            var known = parts.map(function (part) { return part.generation; }).filter(Boolean);
            var mixed = parts.some(function (part) { return part.changed; })
              || (single && known.length > 0 && known[0] !== generation)
              || known.some(function (stamp) { return stamp !== known[0]; })
              || (generation && stamps.some(function (stamp) { return !stamp; }))
              || (known.length > 0 && stamps.some(function (stamp) { return !stamp; }));
            if (mixed) {
              if (single) return run(currentJobs, false);
              if (index < 2) return attempt(index + 1);
              if (hiddenRegions) { quarantine(new Error('Index changed repeatedly; retry the entire page')); return; }
              jobs.forEach(function (job) { errorNode(job, new Error('Index changed repeatedly; no consistent snapshot rendered'), function () { return run(currentJobs, false); }); });
              return;
            }
            // 明确不支持的资源仍展示错误，但不阻塞其余完整同代资源；其它失败不能豁免。
            var requiredFailure = parts.some(function (part) { return part.error && !part.unavailable; });
            if (hiddenRegions && requiredFailure) {
              quarantine(new Error('Snapshot recovery requires every resource; one or more requests failed'));
              return;
            }
            if (!single && generation && known[0] && generation !== known[0] && requiredFailure) {
              jobs.forEach(function (job) { errorNode(job, new Error('New index snapshot is incomplete'), function () { return run(currentJobs, false); }); });
              return;
            }
            // 整批无代次头时兼容旧测试及独立资源，禁止混合有头与无头的成功结果。
            try {
              jobs.forEach(function (job, i) {
                var part = parts[i];
                errorNode(job, part.error, function () { return currentJobs.indexOf(job) < 0 ? Promise.resolve() : run([job], true); });
                if (!part.error) job.apply(part.data);
              });
            } catch (error) {
              quarantine(error);
              return;
            }
            if (!single && (known.length || successful.length)) generation = known[0] || '';
            document.body.setAttribute('data-index-generation', generation || 'legacy');
            restore();
          });
        }
        return attempt(0);
      }
      return { load: function (jobs) {
        currentJobs.forEach(function (job) { errorNode(job, null); });
        currentJobs = jobs;
        return run(jobs, false);
      } };
    }
  };
}());
