
document.addEventListener('click', function(e){
  const a=e.target.closest('[data-action]');
  if(!a)return;
  if(a.dataset.action==='toggle-round'){
    const r=a.closest('.round'); if(r) r.classList.toggle('open');
  }
  if(a.dataset.action==='toggle-all'){
    const rounds=[...document.querySelectorAll('.round')];
    const all=rounds.every(r=>r.classList.contains('open'));
    rounds.forEach(r=>r.classList.toggle('open',!all));
    a.textContent=all?'Expand all':'Collapse all';
  }
});
