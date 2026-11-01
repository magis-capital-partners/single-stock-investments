(function(global){
  'use strict';
  // Every company-specific model must declare an explicit issuer scope here.
  const registry = [{id:'respiratory',tickers:['QDEL'],file:'respiratory_model',render:(doc,h)=>global.InsightsViz.renderRespiratoryPanel(doc,h.escapeHtml)}];
  const relevant = ticker => registry.filter(m=>m.tickers.includes(ticker));
  async function mount(host,ticker,load,data,helpers) {
    const models=relevant(ticker);
    if(!host || !models.length)return;
    host.innerHTML='<p class="desk-caption">Loading company models…</p>';
    try {
      await Promise.all(models.map(m=>load(m.file)));
      if(!host.isConnected)return;
      host.innerHTML=models.map(m=>m.render(data[m.file],helpers)).join('');
    } catch (_) {if(host.isConnected)host.innerHTML='<p class="desk-caption">Company model unavailable. Reopen the company page to retry.</p>';}
  }
  global.CompanyModels={registry,relevant,mount};
})(window);
