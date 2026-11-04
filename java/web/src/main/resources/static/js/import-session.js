(function () {
  'use strict';

  var form = document.querySelector('[data-import-form]');
  if (!form) return;

  var fileInput = form.querySelector('[data-import-file]');
  var sourceInput = form.querySelector('[data-import-source]');
  var submitButton = form.querySelector('[data-import-submit]');
  var retryButton = form.querySelector('[data-import-retry]');
  var status = form.querySelector('[data-import-status]');
  var errorPanel = form.querySelector('[data-import-error]');
  var errorMessage = form.querySelector('[data-import-error-message]');
  var filename = form.querySelector('[data-import-filename]');
  var limit = Number(form.getAttribute('data-max-bytes'));
  var busy = false;

  function formatBytes(bytes) {
    if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toLocaleString() + ' MiB';
    return bytes.toLocaleString() + ' 字节';
  }

  var limitLabel = form.querySelector('[data-import-limit]');
  if (limitLabel && Number.isFinite(limit) && limit > 0) {
    limitLabel.textContent = formatBytes(limit);
  }

  function clearError() {
    errorPanel.hidden = true;
    errorMessage.textContent = '';
  }

  function showError(message) {
    errorMessage.textContent = message;
    errorPanel.hidden = false;
    status.textContent = '';
  }

  function setBusy(value) {
    busy = value;
    form.setAttribute('aria-busy', String(value));
    fileInput.disabled = value;
    sourceInput.disabled = value;
    submitButton.disabled = value;
    retryButton.disabled = value;
    submitButton.textContent = value ? '正在分析…' : '导入并分析';
  }

  // 仅允许导航到当前服务的导入详情，不能信任响应中的任意 URL。
  function detailLocation(result) {
    if (typeof result.import_id !== 'string' || !/^[A-Za-z0-9_-]+$/.test(result.import_id)
        || typeof result.detail_url !== 'string') {
      throw new Error('服务返回了无效的导入链接，请重新尝试。');
    }
    var target;
    try {
      target = new URL(result.detail_url, window.location.origin);
    } catch (invalidUrl) {
      throw new Error('服务返回了无效的导入链接，请重新尝试。');
    }
    if (target.origin !== window.location.origin || target.username || target.password
        || target.pathname !== '/imports/' + encodeURIComponent(result.import_id)
        || target.search || target.hash) {
      throw new Error('服务返回了无效的导入链接，请重新尝试。');
    }
    return target.pathname;
  }

  fileInput.addEventListener('change', function () {
    clearError();
    status.textContent = '';
    var file = fileInput.files[0];
    filename.textContent = file ? file.name + ' · ' + formatBytes(file.size) : '';
  });
  sourceInput.addEventListener('change', clearError);

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    if (busy || !form.reportValidity()) return;
    clearError();

    var file = fileInput.files[0];
    if (!file || fileInput.files.length !== 1 || !/\.jsonl$/i.test(file.name)) {
      showError('请选择一个 .jsonl 会话文件。');
      return;
    }
    if (!file.size) {
      showError('文件为空，请选择包含会话记录的 JSONL 文件。');
      return;
    }
    if (Number.isFinite(limit) && limit > 0 && file.size > limit) {
      showError('文件超过上限 ' + formatBytes(limit) + '，请选择较小的会话文件。');
      return;
    }

    var body = new FormData(form);
    setBusy(true);
    status.textContent = '正在上传并分析本文件，个人统计不会改变。';
    try {
      var response = await fetch(form.action, {
        method: 'POST',
        body: body,
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      var result;
      try {
        result = await response.json();
      } catch (parseError) {
        throw new Error('服务未返回有效的分析结果，请稍后重试。');
      }
      if (!result || typeof result !== 'object' || Array.isArray(result)) {
        throw new Error('服务未返回有效的分析结果，请稍后重试。');
      }
      if (!response.ok) {
        throw new Error(typeof result.message === 'string' && result.message
          ? result.message : '导入失败，请检查文件与来源后重试。');
      }
      window.location.assign(detailLocation(result));
    } catch (error) {
      showError(error instanceof Error ? error.message : '无法连接本地分析服务，请稍后重试。');
    } finally {
      setBusy(false);
    }
  });

  retryButton.addEventListener('click', function () {
    if (!busy) form.requestSubmit();
  });
}());
