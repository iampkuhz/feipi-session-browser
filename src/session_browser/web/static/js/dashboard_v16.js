// Dashboard v16 small interactions.
// Range buttons are visual-only unless backend provides 7d data; keep behavior conservative.
(function(){
  document.addEventListener("click", function(event){
    const btn = event.target.closest("[data-dashboard-range]");
    if(!btn) return;
    const group = btn.closest("[data-dashboard-chart]");
    if(!group) return;
    group.querySelectorAll("[data-dashboard-range]").forEach(b => b.classList.toggle("active", b === btn));
    const value = btn.dataset.dashboardRange || "30d";
    group.dataset.range = value;
  });
})();