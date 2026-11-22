/* Shared financial definitions and chart transforms; no investment authority. */
(function(g){
'use strict';
const finite=x=>typeof x==='number'&&Number.isFinite(x), clone=x=>JSON.parse(JSON.stringify(x));
const definitions={
 revenue:['Revenue','income','money'],gross_profit:['Gross profit','income','money'],operating_income:['Operating income','income','money'],net_income:['Net income attributable to shareholders','income','money'],ebitda:['EBITDA','income','money'],diluted_eps:['Diluted EPS','income','per_share'],basic_eps:['Basic EPS','income','per_share'],
 ocf:['Operating cash flow','cashflow','money'],capex:['Capital expenditure','cashflow','money'],free_cash_flow:['Free cash flow','cashflow','money'],sbc:['Stock compensation','cashflow','money'],buybacks:['Share repurchases','cashflow','money'],issuance:['Share issuance proceeds','cashflow','money'],dividends:['Dividends paid','cashflow','money'],acquisitions:['Acquisitions','cashflow','money'],
 cash:['Cash and equivalents','balance','money'],debt:['Total debt','balance','money'],assets:['Total assets','balance','money'],equity:['Common equity','balance','money'],tangible_equity:['Tangible common equity','balance','money'],shares:['Common shares outstanding','balance','shares'],diluted_shares:['Weighted diluted shares','income','shares'],loans:['Loans','balance','money'],deposits:['Deposits','balance','money'],credit_provision:['Credit provision','income','money'],net_interest_income:['Net interest income','income','money'],noninterest_income:['Non-interest income','income','money'],
 gross_margin:['Gross margin','profitability','percent'],operating_margin:['Operating margin','profitability','percent'],net_margin:['Net margin','profitability','percent'],fcf_margin:['FCF margin','profitability','percent'],ebitda_margin:['EBITDA margin','profitability','percent'],roe:['Return on average common equity','profitability','percent'],roa:['Return on average assets','profitability','percent'],roic:['Return on invested capital','profitability','percent'],net_debt:['Net debt','balance','money'],interest_coverage:['EBIT / interest expense','profitability','multiple'],
 revenue_per_share:['Revenue per diluted share','per_share','per_share'],fcf_per_share:['FCF per diluted share','per_share','per_share'],book_value_per_share:['Common book value per share','per_share','per_share'],tangible_book_per_share:['Tangible book per share','per_share','per_share'],
 pe:['P/E','valuation','multiple'],ps:['P/S','valuation','multiple'],pfcf:['P/FCF','valuation','multiple'],pb:['Price / common book','valuation','multiple'],ptbv:['Price / tangible book','valuation','multiple'],ev_sales:['EV / sales','valuation','multiple'],ev_ebitda:['EV / EBITDA','valuation','multiple'],ev_ebit:['EV / EBIT','valuation','multiple'],fcf_yield:['FCF yield','valuation','percent'],earnings_yield:['Earnings yield','valuation','percent']
};
const formulas={free_cash_flow:'Operating cash flow − capital expenditure; reported cash-flow classification is retained.',gross_margin:'Gross profit / revenue × 100',operating_margin:'Operating income / revenue × 100',net_margin:'Net income attributable to shareholders / revenue × 100',fcf_margin:'(Operating cash flow − capital expenditure) / revenue × 100',ebitda:'Operating income + reported depreciation and amortization; only compatible periods.',pe:'Then-available reported-share market capitalization / then-available TTM common earnings; positive earnings only.',ps:'Market capitalization using then-available reported shares / then-available TTM revenue.',pfcf:'Market capitalization using then-available reported shares / then-available TTM (operating cash flow − capital expenditure).',pb:'Market capitalization / latest available common equity.',ptbv:'Market capitalization / latest available tangible common equity.',ev_sales:'Enterprise value / then-available TTM revenue.',ev_ebitda:'Enterprise value / then-available TTM EBITDA.',ev_ebit:'Enterprise value / then-available TTM operating income.',fcf_yield:'TTM free cash flow / market capitalization × 100',earnings_yield:'TTM common earnings / market capitalization × 100',roe:'TTM common earnings / average opening and closing common equity × 100',roa:'TTM net income / average opening and closing total assets × 100',roic:'Reported NOPAT / average reported invested capital × 100; absent inputs remain unavailable.',net_debt:'Total debt − cash and equivalents',interest_coverage:'Operating income / interest expense',tangible_equity:'Common equity − goodwill − other intangible assets'};
const profiles={operating:['revenue','net_income','free_cash_flow','operating_margin'],bank:['net_interest_income','net_income','book_value_per_share','roe'],insurance:['net_income','book_value_per_share','roe','equity'],holding:['book_value_per_share','equity','net_income','cash'],fund:['assets','cash','book_value_per_share'],property:['revenue','ocf','debt','net_income'],development:['cash','ocf','shares','revenue'],cyclical:['revenue','operating_margin','free_cash_flow','debt']};
const presets={growth:['revenue','net_income','diluted_eps'],cash:['ocf','capex','free_cash_flow'],profitability:['gross_margin','operating_margin','net_margin','fcf_margin'],valuation:['pe','ps','pfcf'],shareholder:['revenue_per_share','diluted_eps','fcf_per_share','diluted_shares'],allocation:['buybacks','issuance','dividends','acquisitions'],balance:['cash','debt','net_debt','interest_coverage']};
const shareIds=new Set(['shares','diluted_shares','basic_eps','diluted_eps','book_value_per_share','tangible_book_per_share','revenue_per_share','fcf_per_share']),alignedCache=new WeakMap();
function metric(doc,id){
 let row=doc?.series?.find(s=>s.id===id)||null;if(!row)return null;
 let cache=alignedCache.get(doc);if(!cache){cache=new Map();alignedCache.set(doc,cache);}if(cache.has(id))return cache.get(id);
 if(row.statement==='valuation'&&doc.share_basis&&!doc.share_basis.eligible){row={...row,monthly:[],gap:doc.share_basis.reason||'A verified common-share basis is required.'};cache.set(id,row);return row;}
 if(id==='pe'){const earnings=doc.series.find(s=>s.id==='earnings_yield');if(earnings)row={...row,definition:formulas.pe,monthly:(earnings.monthly||[]).filter(p=>p.value>0).map(p=>({...p,value:100/p.value,basis:formulas.pe}))};}
 else if(shareIds.has(id)){
  if(doc.share_basis&&!doc.share_basis.eligible&&/multiple listed|ADR|conversion|share class|preferred|payoff|claim/i.test([doc.share_basis.reason,...(doc.gaps||[])].join(' '))){row={...row,annual:[],quarterly:[],gap:'The reported issuer share basis has not been reconciled to this quoted security.'};cache.set(id,row);return row;}
  const basis=doc.share_basis||{},adjust=p=>{
   if(['basic_eps','diluted_eps'].includes(id)&&/EPS rounding/.test(p.basis||''))return null;
   if(doc.view_basis==='first'||!basis.eligible)return {...p,share_basis_status:'unverified'};
   let refs=[p.source,...(p.source_refs||[])].filter(Boolean);
   if(['book_value_per_share','tangible_book_per_share','revenue_per_share','fcf_per_share'].includes(id))refs=refs.filter(r=>/shares/i.test(r.locator||''));
   const dates=[...new Set(refs.map(r=>r.filed).filter(Boolean))];if(!dates.length)return {...p,share_basis_status:'unverified'};
   const factors=new Set(dates.map(filed=>(basis.splits||[]).filter(s=>s.date>filed).reduce((n,s)=>n*s.factor,1)));
   if(factors.size!==1)return null;const factor=[...factors][0];if(!(factor>0))return null;
   const value=row.unit==='shares'?p.value*factor:p.value/factor;if(!finite(value))return null;
   return {...p,value,reported_value:p.reported_value??p.value,share_factor:factor,share_basis_status:'aligned',basis:(p.basis||'Reported')+'; split-aligned to '+basis.as_of+' share basis',source_refs:[...(p.source_refs||[p.source]),{url:basis.source_url,locator:'Captured split ledger; factors applied after the original source filing date'}]};
  };
  row={...row,...Object.fromEntries(['annual','quarterly'].map(f=>[f,(row[f]||[]).map(adjust).filter(Boolean)]))};
 }
 cache.set(id,row);return row;
}
function unit(doc,s){return s?.unit|| (definitions[s?.id]?.[2]==='money'?doc.currency:definitions[s?.id]?.[2]);}
function validDate(s){return /^\d{4}-\d{2}-\d{2}$/.test(s||'')&&Number.isFinite(Date.parse(s))&&new Date(s).toISOString().slice(0,10)===s;}
function points(doc,id,frequency='annual'){
 const s=metric(doc,id);if(!s)return [];
 if(s.statement==='valuation')return s.monthly||[];
 if(frequency!=='ttm')return s[frequency]||[];
 if(s.statement==='balance')return s.quarterly?.length?s.quarterly:s.annual||[];
 if(doc.view_basis==='first'&&(s.unit==='shares'||/\/shares$/.test(s.unit||'')))return [];
 const perShare={revenue_per_share:'revenue',fcf_per_share:'free_cash_flow'};
 if(perShare[id]){const right=new Map(points(doc,'diluted_shares','ttm').map(p=>[p.period,p]));return points(doc,perShare[id],'ttm').filter(p=>right.get(p.period)?.value>0).map(p=>({...p,value:p.value/right.get(p.period).value,share_basis_status:right.get(p.period).share_basis_status,basis:'TTM flow / duration-weighted TTM diluted shares',source_refs:[...(p.source_refs||[p.source]),...(right.get(p.period).source_refs||[right.get(p.period).source])]}));}
 const ratio={gross_margin:['gross_profit','revenue'],operating_margin:['operating_income','revenue'],net_margin:['net_income','revenue'],fcf_margin:['free_cash_flow','revenue'],ebitda_margin:['ebitda','revenue'],interest_coverage:['operating_income','interest_expense',1]};
 if(ratio[id]){const [a,b,scale=100]=ratio[id],right=new Map(points(doc,b,'ttm').map(p=>[p.period,p]));return points(doc,a,'ttm').filter(p=>right.get(p.period)?.value>0).map(p=>({...p,value:p.value/right.get(p.period).value*scale,basis:formulas[id],source_refs:[...(p.source_refs||[p.source]),...(right.get(p.period).source_refs||[right.get(p.period).source])]}));}
 if(definitions[id]?.[2]==='percent'||s.unit==='percent')return s.ttm||[];
 const q=(s.quarterly||[]).filter(p=>finite(p.value)&&validDate(p.period)).sort((a,b)=>a.period.localeCompare(b.period)),out=[];
 for(let i=3;i<q.length;i++){
  const a=q.slice(i-3,i+1);if(!a.every((p,j)=>!j||(Date.parse(p.period)-Date.parse(a[j-1].period))/86400000>=60&&(Date.parse(p.period)-Date.parse(a[j-1].period))/86400000<=110&&(!p.start||(Date.parse(p.start)-Date.parse(a[j-1].period))/86400000>=0&&(Date.parse(p.start)-Date.parse(a[j-1].period))/86400000<=2)))continue;
  if(shareIds.has(id)&&a.some(p=>p.share_basis_status==='unverified'))continue;
  let value=a.reduce((n,p)=>n+p.value,0);
  if(s.unit==='shares'){if(!a.every(p=>validDate(p.start)))continue;const d=a.map(p=>(Date.parse(p.period)-Date.parse(p.start))/86400000+1);value=a.reduce((n,p,j)=>n+p.value*d[j],0)/d.reduce((x,y)=>x+y,0);}
  out.push({...a[3],value,source_refs:a.flatMap(p=>p.source_refs||[p.source]).filter(Boolean),basis:'Four consecutive fiscal quarters'+(s.unit==='shares'?' · duration-weighted shares':'')});
 }
 const merged=new Map(out.map(p=>[p.period,p]));for(const p of s.annual||[])merged.set(p.period,{...p,basis:p.basis||'Reported full fiscal year (twelve months)'});
 return [...merged.values()].sort((a,b)=>a.period.localeCompare(b.period));
}
function transform(values,mode='value',unitName='',frequency='annual'){
 const p=values.filter(p=>finite(p.value));
 if(mode==='value')return clone(p);
 if(mode==='indexed'){const first=p[0];if(!first||first.value<=0)return [];return p.map(x=>({...x,value:x.value/first.value*100,basis:'Indexed to 100 at '+first.period}));}
 if(mode==='change'){const first=p[0];if(!first||first.value<=0)return [];return p.map(x=>({...x,value:(x.value/first.value-1)*100,basis:'Change since '+first.period}));}
 if(mode==='qoq'&&frequency==='annual')return [];
 const lag=mode==='qoq'?(frequency==='monthly'?3:1):frequency==='annual'?1:frequency==='monthly'?12:4,out=[];
 for(let i=lag;i<p.length;i++){const a=p[i-lag],b=p[i],days=(Date.parse(b.period)-Date.parse(a.period))/86400000,expected=mode==='qoq'?91:365;if(days<expected*.8||days>expected*1.2)continue;
  if(unitName==='percent')out.push({...b,value:b.value-a.value,basis:'Percentage-point change versus '+a.period});
  else if(a.value>0)out.push({...b,value:(b.value/a.value-1)*100,basis:'Growth versus '+a.period});
 }
 return out;
}
function windowed(p,years){if(!p.length||years==='all')return p;const last=Date.parse(p.at(-1).period),start=last-Number(years)*365.25*86400000;return p.filter(p=>Date.parse(p.period)>=start);}
function stats(p){const v=p.map(p=>p.value).filter(finite).sort((a,b)=>a-b);if(!v.length)return null;const quantile=q=>{const n=(v.length-1)*q,i=Math.floor(n);return v[i]+(v[Math.ceil(n)]-v[i])*(n-i);},last=p.filter(p=>finite(p.value)).at(-1);return {min:v[0],max:v.at(-1),median:quantile(.5),p25:quantile(.25),p75:quantile(.75),mean:v.reduce((a,b)=>a+b,0)/v.length,percentile:100*v.filter(x=>x<=last.value).length/v.length,count:v.length};}
function cagr(p){if(p.length<2||p[0].value<=0||p.at(-1).value<=0)return null;const years=(Date.parse(p.at(-1).period)-Date.parse(p[0].period))/86400000/365.25;return years>0?(Math.pow(p.at(-1).value/p[0].value,1/years)-1)*100:null;}
function format(value,unitName='number',compact=false){if(!finite(value))return '—';let v=value,tail='';if(compact&&!['percent','multiple','index'].includes(unitName)){const scales=[[1e12,'T'],[1e9,'B'],[1e6,'M'],[1e3,'K']];for(const [n,label]of scales)if(Math.abs(v)>=n){v/=n;tail=label;break;}}return new Intl.NumberFormat(undefined,{maximumFractionDigits:Math.abs(v)<1?3:2}).format(v)+tail+(unitName==='percent'?'%':unitName==='pp'?' pp':unitName==='multiple'?'×':'');}
function latest(doc,id,frequency='ttm'){let p=points(doc,id,frequency);if(!p.length)p=points(doc,id,'annual');if(!p.length)p=points(doc,id,'quarterly');const last=p.filter(p=>finite(p.value)).at(-1)||null;const asof=doc.freshness_as_of||doc.as_of;if(last&&validDate(asof)&&(Date.parse(asof)-Date.parse(last.period))/86400000>(metric(doc,id)?.statement==='valuation'?45:550))return null;return last;}
function screen(rows,rules){return rows.filter(r=>rules.every(rule=>{const v=r.latest?.[rule.metric]?.value;if(!finite(v))return false;const x=Number(rule.value);return rule.op==='gte'?v>=x:rule.op==='lte'?v<=x:rule.op==='gt'?v>x:rule.op==='lt'?v<x:v===x;}));}
function evaluateAlerts(doc,rules){return rules.filter(r=>!r.ticker||r.ticker===doc.ticker).flatMap(r=>{const p=latest(doc,r.metric);if(!p||!screen([{latest:{[r.metric]:p}}],[r]).length)return [];return [{...r,value:p.value,period:p.period,source:p.source,key:[r.id,doc.ticker,p.period,p.value].join('|')}];});}
function reverseGrowth(price,anchor,multiple,years){return price>0&&anchor>0&&multiple>0&&years>0?(Math.pow(price/(anchor*multiple),1/years)-1)*100:null;}
function reverseModel(V,model,{price,anchor,multiple,years,payout,required}){
 if(!V||![price,anchor,multiple].every(x=>finite(x)&&x>0)||!Number.isInteger(years)||years<1||years>30||!finite(payout)||payout<0||payout>1||!finite(required)||required<=-1)throw Error('Use positive inputs, whole years from 1–30, and a payout from 0–100%.');
 const key=model.method==='owner_cash'?'incremental_roic':model.method==='book'?'roe':'growth';
 const labels={incremental_roic:'Return on new investment',roe:'Return on opening common equity',growth:model.method==='transition'?'Annual revenue growth':'Annual anchor growth'};
 const calc=value=>{const c={...model.cases.base,[key]:value,exit_multiple:multiple,payout};if(model.method==='owner_cash')c.reinvestment=1-payout;if(model.method==='nav')c.distribution_yield=payout;return V.calculate(model,{inputs:{entry_price:price,anchor,horizon:years},cases:{base:c}}).cases.base;};
 const baseline=calc(.05);if(baseline.gaps.length)throw Error(baseline.gaps.join('; '));
 const pv=x=>V.presentValue(calc(x).flows,required,model.inputs.entry_date);
 let lo=-.9,hi=1,low=pv(lo),high=pv(hi);if(!finite(low)||!finite(high)||low>price||high<price||Math.abs(high-low)<1e-12)throw Error('No implied-assumption solution within the model’s supported range (−90% to +100% annually).');
 for(let i=0;i<100;i++){const mid=(lo+hi)/2;if(pv(mid)>price)hi=mid;else lo=mid;}
 return {key,label:labels[key],value:(lo+hi)/2,required,cashGrowth:key==='incremental_roic'?(lo+hi)/2*(1-payout):null};
}
function impliedMargin(price,revenue,multiple,years,growth=0,dilution=0){const future=revenue*Math.pow((1+growth)/(1+dilution),years);return price>0&&future>0&&multiple>0?price/(future*multiple)*100:null;}
function sensitivity(V,model,prices,multiples){if(!V||!model)return [];return prices.map(price=>multiples.map(m=>{const cases={};for(const name of V.cases)cases[name]={...model.cases[name],exit_multiple:m};const result=V.calculate(model,{inputs:{entry_price:price},cases});return {price,multiple:m,irr:result.cases.base.irr,value:result.cases.base.value,gaps:result.cases.base.gaps};}));}
function estimateRows(doc,imports=[]){return [...(doc.expectations||[]),...imports].filter(e=>e.ticker===doc.ticker&&['street','management','research'].includes(e.kind)&&validDate(e.period)&&validDate(e.as_of)&&finite(e.value)&&e.source).sort((a,b)=>a.as_of.localeCompare(b.as_of));}
function beats(doc,estimates){return estimates.filter(e=>e.kind==='street').flatMap(e=>{const row=metric(doc,e.metric),frequency=e.frequency||'quarterly',first=row?.[frequency+'_as_reported'];const p=(first||points(doc,e.metric,frequency)).find(p=>p.period===e.period);const event=doc.events?.filter(x=>['earnings_release','results'].includes(x.type)&&x.period===e.period&&validDate(x.date)).sort((a,b)=>a.date.localeCompare(b.date))[0],explicit=p?.published_at||event?.date,released=explicit||p?.source?.filed;if(!p||!released||e.as_of>=(explicit||e.period)||e.unit&&row?.unit&&e.unit!==row.unit)return [];return [{...e,comparison_basis:explicit?'Before documented results release':'Before fiscal period end; exact results release is unverified',actual:p.value,difference:p.value-e.value,surprise_pct:e.value!==0?(p.value-e.value)/Math.abs(e.value)*100:null,released,actual_source:p.source}];});}
function answer(doc,question){const text=String(question||'').toLowerCase();let ids=Object.keys(definitions).filter(id=>text.includes(id.replaceAll('_',' '))||text.includes(definitions[id][0].toLowerCase()));const aliases=[[/\b(fcf|free cash)\b/,'free_cash_flow'],[/\b(revenue|sales)\b/,'revenue'],[/\b(earnings|profit|eps)\b/,'diluted_eps'],[/\b(debt|leverage)\b/,'debt'],[/\b(margin)\b/,'operating_margin'],[/\b(dilution|share count)\b/,'diluted_shares'],[/p\/?e\b/,'pe'],[/p\/?s\b/,'ps'],[/p\/?fcf\b/,'pfcf']];for(const [pattern,id]of aliases)if(pattern.test(text))ids.push(id);ids=[...new Set(ids)].slice(0,6);return ids.map(id=>{const s=metric(doc,id),p=latest(doc,id),hist=points(doc,id,'annual');return {id,label:s?.label||definitions[id][0],point:p,previous:hist.length>1?hist.at(-2):null,definition:formulas[id]||s?.definition,unit:s?.unit||definitions[id][2],growth:s?.unit==='percent'||hist.some(p=>p.share_basis_status==='unverified')?null:cagr(hist),gap:s?.gap||'No comparable sourced value is available.'};});}
g.StockResearchMetrics={definitions,formulas,profiles,presets,finite,validDate,metric,unit,points,transform,windowed,stats,cagr,format,latest,screen,evaluateAlerts,reverseGrowth,reverseModel,impliedMargin,sensitivity,estimateRows,beats,answer};
if(typeof module!=='undefined')module.exports=g.StockResearchMetrics;
})(typeof window!=='undefined'?window:globalThis);
