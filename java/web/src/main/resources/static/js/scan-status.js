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
        reload.dataset.action = 'reload-page';
        content.appendChild(reload);
        target.appendChild(panel);
    }

    function refresh() {
        if (document.visibilityState === 'hidden') return;
        fetch('/api/scan-status', { cache: 'no-store' }).then(function (response) {
            if (!response.ok) throw new Error('scan_status_unavailable');
            return response.json();
        }).then(display).catch(function () {
            display({ status: 'unknown', message: '扫描状态读取失败，当前页面数据是否最新尚未确认。请刷新状态重试。' });
        });
    }
    refresh();
    window.setInterval(refresh, 15000);
}());
