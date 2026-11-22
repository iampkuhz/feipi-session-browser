(function () {
    'use strict';
    var target = document.querySelector('[data-scan-status-banner]');
    if (!target || /^\/(imports|export)(\/|$)/.test(window.location.pathname)) return;

    function node(tag, className, text) {
        var element = document.createElement(tag);
        element.className = className;
        element.textContent = text;
        return element;
    }

    function display(status) {
        target.replaceChildren();
        if (status.status === 'success') return;
        var panel = node('section', 'state-strip', '');
        var content = node('div', '', '');
        panel.appendChild(content);
        panel.setAttribute('role', status.status === 'failure' ? 'alert' : 'status');
        content.appendChild(node('div', 'state-title', status.status === 'failure' ? '最新扫描失败' : '扫描状态'));
        content.appendChild(node('p', 'muted', status.message || '扫描状态暂不可用，请刷新状态重试。'));
        if (status.status === 'failure') {
            content.appendChild(node('p', 'mono', 'Processed: ' + status.processedCount + ' · Published from this scan: ' + status.publishedProcessedCount + ' · Errors: ' + status.errorCount));
            (status.reasons || []).forEach(function (reason) {
                content.appendChild(node('p', 'mono', [reason.source, reason.phase, reason.code, reason.line ? 'line ' + reason.line : 'line unknown'].join(' · ')));
                if (reason.explanation) content.appendChild(node('p', 'muted', reason.explanation));
            });
            content.appendChild(node('p', 'muted', '修复原因后，在使用相同索引目录的终端执行原扫描命令；刷新页面本身不会触发扫描。'));
            content.appendChild(node('p', 'mono', status.retryCommand || ''));
        }
        var reload = node('button', 'btn', '刷新状态');
        reload.type = 'button';
        reload.addEventListener('click', function () {
            reload.disabled = true;
            reload.textContent = '正在读取…';
            refresh();
        });
        content.appendChild(reload);
        var checked = node('small', 'muted', ' 最近检查：' + new Date().toLocaleTimeString('zh-CN', { hour12: false }));
        content.appendChild(checked);
        target.appendChild(panel);
    }

    var pending = false;
    function refresh() {
        if (pending || document.visibilityState === 'hidden') return;
        pending = true;
        fetch('/api/scan-status', {
            cache: 'no-store', headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(10000)
        }).then(function (response) {
            if (!response.ok) {
                var reason = { 404: '状态接口不存在', 500: '服务未能读取状态记录', 503: '本地服务暂不可用' };
                throw new Error('HTTP ' + response.status + (reason[response.status] ? '，' + reason[response.status] : ''));
            }
            return response.json().catch(function () { throw new Error('响应不是有效的 JSON'); });
        }, function (error) {
            throw new Error(error.name === 'TimeoutError' ? '本地服务在 10 秒内未响应' : '无法连接本地服务');
        }).then(function (data) {
            if (!data || !['success', 'running', 'failure', 'unknown'].includes(data.status)) {
                throw new Error('响应缺少有效的扫描状态');
            }
            display(data);
        }).catch(function (error) {
            display({ status: 'unknown', message: '扫描状态读取失败：' + error.message + '。当前页面数据是否最新尚未确认。' });
        }).finally(function () { pending = false; });
    }
    refresh();
    window.setInterval(refresh, 15000);
}());
