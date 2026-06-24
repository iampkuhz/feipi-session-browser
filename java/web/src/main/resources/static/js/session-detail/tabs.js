  /* ── Tab switching ── */

  function switchTab(page, tabName, updateUrl) {
    if (updateUrl == null) updateUrl = true;
    // Update tab active state + aria-selected
    qsa(page, '.sd-tabs [data-tab]').forEach(function(tab) {
      var isActive = tab.getAttribute('data-tab') === tabName;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    // Show/hide panels
    qsa(page, '[data-tab-panel]').forEach(function(panel) {
      panel.hidden = panel.getAttribute('data-tab-panel') !== tabName;
    });
    if (updateUrl && window.history && window.URLSearchParams) {
      var url = new URL(window.location.href);
      url.searchParams.set('tab', tabName);
      window.history.replaceState({}, '', url.toString());
    }
  }
