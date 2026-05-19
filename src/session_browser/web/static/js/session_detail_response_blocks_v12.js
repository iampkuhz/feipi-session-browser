// Session Detail Response Blocks v12
(function(){
  "use strict";
  function qs(r,s){return r?r.querySelector(s):null}
  function qsa(r,s){return Array.prototype.slice.call((r||document).querySelectorAll(s))}
  function closest(t,s){return t&&t.closest?t.closest(s):null}
  function esc(v){return window.CSS&&CSS.escape?CSS.escape(v):String(v).replace(/"/g,'\\"')}
  function html(v){return String(v==null?'':v).replace(/[<>&"]/g,function(c){return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]})}
  function modal(){return document.getElementById("payload-modal")||document.getElementById("sd-payload-modal")}
  var backdrop=null;
  function openDialog(d){if(!d)return;if(typeof d.showModal==="function"){if(!d.open)d.showModal()}else{if(!backdrop){backdrop=document.createElement("div");backdrop.className="sd-payload-backdrop-polyfill";backdrop.onclick=closePayload}document.body.appendChild(backdrop);d.classList.add("polyfill-open");d.setAttribute("open","")}}
  function closePayload(){var d=modal();if(!d)return;if(typeof d.close==="function"&&d.open)d.close();else{d.removeAttribute("open");d.classList.remove("polyfill-open");if(backdrop&&backdrop.parentNode)backdrop.parentNode.removeChild(backdrop)}}
  function setRoundOpen(r,o){if(!r)return;r.classList.toggle("is-open",o);r.classList.toggle("open",o);var b=qs(r,'[data-action="toggle-round"]'),d=qs(r,"[data-trace-detail]");if(b)b.setAttribute("aria-expanded",o?"true":"false");if(d)d.hidden=!o}
  function setSubRoundOpen(r,o){if(!r)return;r.classList.toggle("is-open",o);var b=qs(r,'[data-action="toggle-sub-round"]'),d=qs(r,".sd-sub-steps");if(b)b.setAttribute("aria-expanded",o?"true":"false");if(d)d.hidden=!o}
  function visibleRounds(p){return qsa(p,"[data-trace-round-row]").filter(function(r){return !r.hidden})}
  function updateToggleAll(p){var b=qs(p,'[data-action="toggle-all"]');if(!b)return;var rs=visibleRounds(p),all=rs.length>0&&rs.every(function(r){return r.classList.contains("is-open")||r.classList.contains("open")});b.textContent=all?"Collapse all":"Expand all";b.setAttribute("data-state",all?"collapse":"expand")}
  function openPayload(btn){var d=modal();if(!d)return;var id=btn.getAttribute("data-payload-id")||"", title=btn.getAttribute("data-payload-title")||btn.textContent.trim()||"Payload";var t=id?qs(document,'template[data-payload-source="'+esc(id)+'"]'):null;var body=qs(d,"[data-payload-body]")||qs(d,".sd-payload-main");[["[data-payload-title]",title],["[data-payload-subtitle]",id||"missing payload id"],["[data-meta-id]",id||"—"],["[data-meta-kind]",t?(t.dataset.payloadKind||"—"):"missing"],["[data-meta-status]",t?(t.dataset.payloadStatus||"—"):"not found"],["[data-meta-size]",t?(t.dataset.payloadSize||"—"):"—"]].forEach(function(x){var n=qs(d,x[0]);if(n)n.textContent=x[1]});if(body)body.innerHTML=t?t.innerHTML:'<div class="sd-payload-warning">没有找到 payload source：'+html(id)+'</div>';openDialog(d)}
  document.addEventListener("click",function(e){var a=closest(e.target,"[data-action]");if(!a)return;var action=a.getAttribute("data-action"),page=closest(a,"[data-trace-page]")||document;
    if(action==="open-payload"){e.preventDefault();openPayload(a)}
    else if(action==="close-payload"){e.preventDefault();closePayload()}
    else if(action==="toggle-round"){e.preventDefault();var r=closest(a,"[data-trace-round-row]");setRoundOpen(r,!(r&&(r.classList.contains("is-open")||r.classList.contains("open"))));updateToggleAll(page)}
    else if(action==="toggle-sub-round"){e.preventDefault();var sr=closest(a,".sd-sub-round");setSubRoundOpen(sr,!(sr&&sr.classList.contains("is-open")))}
    else if(action==="toggle-all"){e.preventDefault();var ex=a.getAttribute("data-state")==="expand";visibleRounds(page).forEach(function(r){setRoundOpen(r,ex)});updateToggleAll(page)}
    else if(action==="filter-status"){e.preventDefault();var st=a.getAttribute("data-status")||"all";qsa(page,'[data-action="filter-status"]').forEach(function(b){b.classList.toggle("is-active",b===a);b.classList.toggle("active",b===a)});qsa(page,"[data-trace-round-row]").forEach(function(r){r.hidden=!(st==="all"||r.getAttribute("data-status")===st)});updateToggleAll(page)}
    else if(action==="jump-round"){e.preventDefault();var r=qs(page,'[data-trace-round-row][data-round="'+esc(a.getAttribute("data-round"))+'"]');if(r){r.hidden=false;setRoundOpen(r,true);r.scrollIntoView({block:"center",behavior:"smooth"});updateToggleAll(page)}}});
  document.addEventListener("click",function(e){var d=modal();if(d&&e.target===d)closePayload()});
  document.addEventListener("keydown",function(e){if(e.key==="Escape")closePayload()});
  document.addEventListener("DOMContentLoaded",function(){qsa(document,"[data-trace-page]").forEach(updateToggleAll)});
})();
