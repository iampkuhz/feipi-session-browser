// UI primitives for Agent Run Profiler.
// Keep generic behavior here. Page-specific behavior should use data attributes.
(function () {
  function closest(el, selector) {
    while (el && el.nodeType === 1) {
      if (el.matches && el.matches(selector)) return el;
      el = el.parentElement;
    }
    return null;
  }
  document.addEventListener("click", function (event) {
    var button = closest(event.target, "[data-sort-key]");
    if (!button) return;
    var form = closest(button, "form");
    if (!form) return;
    var key = button.getAttribute("data-sort-key");
    var sortInput = form.querySelector('input[name="sort"]');
    if (sortInput) {
      event.preventDefault();
      sortInput.value = key;
      form.submit();
    }
  });
})();
