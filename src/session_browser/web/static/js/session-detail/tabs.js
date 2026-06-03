  /* ── Tab switching ── */

  function switchTab(page, tabName) {
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
  }
