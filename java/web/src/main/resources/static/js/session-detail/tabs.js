  /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Tab switching ──` */

  function switchTab(page, tabName, updateUrl) {
    if (updateUrl == null) updateUrl = true;
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Update tab active state + aria-selected`
    qsa(page, '.sd-tabs [data-tab]').forEach(function(tab) {
      var isActive = tab.getAttribute('data-tab') === tabName;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Show/hide panels`
    qsa(page, '[data-tab-panel]').forEach(function(panel) {
      panel.hidden = panel.getAttribute('data-tab-panel') !== tabName;
    });
    if (updateUrl && window.history && window.URLSearchParams) {
      var url = new URL(window.location.href);
      url.searchParams.set('tab', tabName);
      window.history.replaceState({}, '', url.toString());
    }
  }
