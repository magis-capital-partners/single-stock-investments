
/* Independent price and profile evidence for the Summary tab. */
(function (global) {
  'use strict';
  const cache = new Map();
  const charts = new WeakMap();
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const options = [['1M',30],['3M',91],['6M',183],['1Y',365],['5Y',1826],['All',Infinity]];
  const dayMs = 86400000;
  const dateLabel = value => new Intl.DateTimeFormat(undefined, {dateStyle:'medium',timeZone:'UTC'}).format(new Date(value));
  const formatPrice = (n, currency) => new Intl.NumberFormat(undefined, {
    style:'currency',currency,maximumFractionDigits:n<1?4:2,
  }).format(n);
  const sourceLink = (url, label) => /^https:\/\//.test(url || '') ?
    '<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(label)+'</a>' : '';

  async function load(ticker) {
    if (!cache.has(ticker)) {
      const url='/api/v1/research/summary?ticker='+encodeURIComponent(ticker);
      cache.set(ticker,fetch(url,{credentials:'same-origin'}).then(async response => {
        if (!response.ok) throw Error('Company description and prices are awaiting a verified release.');
        const record=await response.json();
        if (record.schema!=='stock-summary.v1' || (record.ticker!==ticker && !record.former_tickers?.includes(ticker))) {
          throw Error('The Summary release could not be verified.');
        }
        return record;
      }).catch(error=>{ cache.delete(ticker); throw error; }));
    }
    return cache.get(ticker);
  }

  function eligibleRanges(points) {
    if (!points?.length) return [];
    const span=(Date.parse(points.at(-1)[0])-Date.parse(points[0][0]))/dayMs;
    return options.filter(([,days])=>days<=span || days===Infinity);
  }

  function selectedPoints(points, name) {
    const days=options.find(([label])=>label===name)?.[1] ?? Infinity;
    const cutoff=Date.parse(points.at(-1)[0])-days*dayMs;
    return points.filter(([day])=>Date.parse(day)>=cutoff);
  }

  function destroy(root) {
    for (const host of root?.querySelectorAll('[data-stock-summary]') || []) {
      charts.get(host)?.destroy();
      charts.delete(host);
    }
  }

  function drawPrice(host, visible, currency) {
    const canvas=host.querySelector('[data-close-chart]');
    if (!canvas || !global.Chart) return;
    const style=getComputedStyle(host);
    const text=style.getPropertyValue('--text-secondary').trim() || '#a9b9cc';
    const grid=style.getPropertyValue('--border').trim() || '#334155';
    const accent=style.getPropertyValue('--accent-cyan').trim() || '#36c8dc';
    const points=visible.map(([date,close])=>({x:Date.parse(date),y:close}));
    const chart=new global.Chart(canvas,{
      type:'line',data:{datasets:[{data:points,borderColor:accent,borderWidth:2,pointRadius:0,
        pointHoverRadius:4,spanGaps:false,segment:{borderColor: c=> c.p1.parsed.x-c.p0.parsed.x>14*dayMs?'transparent':accent}}]},
      options:{responsive:true,maintainAspectRatio:false,animation:false,parsing:false,normalized:true,
        interaction:{mode:'nearest',intersect:false,axis:'x'},
        plugins:{legend:{display:false},tooltip:{callbacks:{
          title:items=>dateLabel(items[0].raw.x),label:ctx=>formatPrice(ctx.raw.y,currency),
        }}},
        scales:{x:{type:'linear',ticks:{maxTicksLimit:6,color:text,callback:value=>dateLabel(value)},grid:{display:false}},
          y:{ticks:{maxTicksLimit:6,color:text,callback:value=>formatPrice(value,currency)},grid:{color:grid}}},
      },
    });
    charts.set(host,chart);
  }

  function profileMarkup(profile, record) {
    const observed=profile.source_date || profile.observed;
    return '<div class="stock-profile"><h3>The business</h3><p>'+esc(profile.text || profile.reason)+'</p>'+
      (record.former_tickers?.length?'<p class="stock-summary-note">Former ticker '+esc(record.former_tickers.join(', '))+'</p>':'')+
      '<p class="stock-summary-note">'+sourceLink(profile.source,profile.excerpt?'Company profile excerpt':'Description source')+
      (observed?' · '+esc(observed):'')+'</p></div>';
  }

  function priceMarkup(price, range) {
    const source=sourceLink(price.source,'Price source');
    const listing=sourceLink(price.listing_source,'Listing confirmation');
    const split=sourceLink(price.split?.source,price.split?price.split.factor+'-for-1 split · '+price.split.date:'');
    if (!price.points?.length) return '<div class="stock-price"><h3>Closing price</h3><p>'+esc(price.reason)+'</p>'+source+'</div>';
    const visible=selectedPoints(price.points,range);
    const [first,last]=[visible[0],visible.at(-1)];
    const move=last[1]/first[1]-1;
    const change=new Intl.NumberFormat(undefined,{style:'percent',maximumFractionDigits:2,signDisplay:'exceptZero'}).format(move);
    return '<div class="stock-price"><div class="stock-price-heading"><div><h3>Closing price</h3><p class="stock-summary-note">'+
      esc(price.basis)+' · '+esc(price.currency)+' · '+esc(dateLabel(first[0]))+' – '+esc(dateLabel(last[0]))+'</p></div>'+
      '<div class="stock-price-value"><strong>'+esc(formatPrice(last[1],price.currency))+'</strong><small>'+esc(change)+' over selected period</small></div></div>'+
      '<div class="stock-price-ranges" role="group" aria-label="Price history period">'+eligibleRanges(price.points).map(([name])=>
        '<button type="button" data-close-range="'+name+'" aria-pressed="'+(range===name)+'">'+(name==='All'?'All history':name)+'</button>').join('')+'</div>'+
      (price.reason?'<p class="stock-price-status" role="status">'+esc(price.reason)+'</p>':'')+
      '<div class="stock-close-chart"><canvas data-close-chart role="img" aria-label="'+
      esc('Closing price in '+price.currency+' from '+first[0]+' to '+last[0])+'"></canvas></div>'+
      '<p class="stock-summary-note">'+[source,listing,split].filter(Boolean).join(' · ')+' · '+visible.length.toLocaleString()+' sessions in view</p>'+
      '<details><summary>Closing price data</summary><div class="stock-close-data"><table><thead><tr><th scope="col">Date</th><th scope="col">Close</th></tr></thead>'+
      '<tbody>'+[...visible].reverse().slice(0,20).map(([day,close])=>'<tr><td>'+esc(day)+'</td><td>'+esc(formatPrice(close,price.currency))+'</td></tr>').join('')+
      '</tbody></table></div><button type="button" data-close-download>Download selected daily closes</button></details></div>';
  }

  function download(price, range, ticker) {
    const lines=selectedPoints(price.points,range).map(([day,close])=>day+','+close+','+price.currency);
    const url=URL.createObjectURL(new Blob(['date,close,currency\n'+lines.join('\n')],{type:'text/csv'}));
    const link=document.createElement('a');
    link.href=url;
    link.download=ticker+'-closes.csv';
    link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1500);
  }

  function render(host, record, ticker, helpers) {
    const price=record.price;
    const periods=eligibleRanges(price.points);
    const returns=record.performance?{...ticker,one_pager:{...ticker.one_pager,performance:record.performance}}:ticker;
    let range=periods.some(([name])=>name==='1Y')?'1Y':'All';
    let mode='price';
    function redraw(focus) {
      charts.get(host)?.destroy();
      charts.delete(host);
      global.StockPerformance?.destroy(host);
      const controls='<div class="stock-price-tabs" role="group" aria-label="Chart view">'+
        '<button type="button" data-close-mode="price" aria-pressed="'+(mode==='price')+'">Price</button>'+
        '<button type="button" data-close-mode="return" aria-pressed="'+(mode==='return')+'">Total return</button></div>';
      host.innerHTML=profileMarkup(record.description,record)+controls+
        (mode==='price'?priceMarkup(price,range):global.StockPerformance?.render(returns,helpers) || '');
      if(mode==='price' && price.points?.length) drawPrice(host,selectedPoints(price.points,range),price.currency);
      if(mode==='return') global.StockPerformance?.mount(host,returns,helpers);
      if(focus) host.querySelector(focus)?.focus({preventScroll:true});
    }
    host.onclick=event=>{
      const button=event.target.closest('button');
      if (!button) return;
      if (button.dataset.closeRange) {
        range=button.dataset.closeRange;
        redraw('[data-close-range="'+range+'"]');
      }
      if (button.dataset.closeMode) {
        mode=button.dataset.closeMode;
        redraw('[data-close-mode="'+mode+'"]');
      }
      if (button.hasAttribute('data-close-download')) download(price,range,ticker.ticker);
    };
    redraw();
  }

  async function mount(host, ticker, helpers) {
    if (host.dataset.loaded) return;
    host.dataset.loaded='pending';
    host.innerHTML='<p role="status">Loading company description and closing prices…</p>';
    try {
      const record=await load(ticker.ticker);
      if (!host.isConnected) return;
      host.dataset.loaded='true';
      render(host,record,ticker,helpers);
    } catch (error) {
      delete host.dataset.loaded;
      host.innerHTML='<p role="status">'+esc(error.message)+'</p><button type="button">Retry company Summary</button>';
      host.querySelector('button').onclick=()=>mount(host,ticker,helpers);
    }
  }

  global.StockSummary={mount,destroy,load,eligibleRanges,selectedPoints};
  if (typeof module!=='undefined') module.exports=global.StockSummary;
})(typeof window!=='undefined'?window:globalThis);
