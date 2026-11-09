// Parse unfiltered public inventories. An empty application shell is not coverage.
import {plain,easternTime} from './core.mjs';
const months=['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'];
export function publisherClock(label,day=null){
 const text=plain(label),full=/^(\w+)\s+(\d{1,2}),?\s+(20\d{2}),?\s+(\d{1,2}:\d{2})\s+ET$/.exec(text),time=/^(\d{1,2}:\d{2})\s+ET$/.exec(text);
 if(full){const month=months.indexOf(full[1].slice(0,3).toLowerCase())+1;if(!month)throw new Error('Unknown publisher month');day=full[3]+'-'+String(month).padStart(2,'0')+'-'+full[2].padStart(2,'0');}
 if(!full&&!time||!/^20\d{2}-\d{2}-\d{2}$/.test(day||''))throw new Error('Publisher inventory clock missing');
 return easternTime(day,(full?.[4]||time[1]).padStart(5,'0')+':00');
}
export function publisherInventory(html,source,base){
 const rows=[];let blocks,day=null;
 if(source==='prnewswire'){
  const input=name=>new RegExp('<input\\b(?=[^>]*\\bname=["\']'+name+'["\'])(?=[^>]*\\bvalue=["\'](\\d+)["\'])[^>]*>','i').exec(html)?.[1];
  const year=input('year'),month=input('month'),date=input('day');if(year&&month&&date)day=year+'-'+month.padStart(2,'0')+'-'+date.padStart(2,'0');
  blocks=[...html.matchAll(/<a\b(?=[^>]*\bclass=["'][^"']*newsreleaseconsolidatelink)[^>]*>[\s\S]*?<\/a>/gi)].map(m=>m[0]);
 }else if(source==='globenewswire')blocks=[...html.matchAll(/<li\b[^>]*class=["']row["'][^>]*>([\s\S]*?)<\/li>/gi)].map(m=>m[1]);
 else throw new Error('Unsupported publisher inventory');
 if(!blocks.length||blocks.length>100)throw new Error('Publisher archive has no validated inventory');
 for(const block of blocks){
  const path=source==='prnewswire'?/<a\b[^>]*href=["']([^"']+)["']/i.exec(block)?.[1]:/<div\b[^>]*class=["']mainLink["'][^>]*>\s*<a\b[^>]*href=["']([^"']+)["']/i.exec(block)?.[1];
  const url=new URL((path||'').replaceAll('&amp;','&'),base),expected=source==='prnewswire'?'www.prnewswire.com':'rss.globenewswire.com';
  if(url.hostname!==expected||url.search||!/(?:news-releases\/|news-release\/).+\.html$/.test(url.pathname))throw new Error('Publisher archive release identity mismatch');
  const label=source==='prnewswire'?/<small\b[^>]*>([\s\S]*?)<\/small>/i.exec(block)?.[1]:/<div\b[^>]*class=["']date-source["'][^>]*>\s*<span>([^<]+)/i.exec(block)?.[1];
  const published_at=publisherClock(label||'',day),title=source==='prnewswire'?plain(/<h3\b[^>]*>([\s\S]*?)<\/h3>/i.exec(block)?.[1]||'').replace(plain(label||''),'').trim():plain(/<div\b[^>]*class=["']mainLink["'][^>]*>\s*<a\b[^>]*>([\s\S]*?)<\/a>/i.exec(block)?.[1]||'');
  if(!title)throw new Error('Publisher inventory title missing');rows.push({url:url.href,title,published_at,publication_precision:'minute'});
 }
 for(let i=1;i<rows.length;i++)if(Date.parse(rows[i].published_at)>Date.parse(rows[i-1].published_at))throw new Error('Publisher inventory order changed');
 if(new Set(rows.map(r=>r.url)).size!==rows.length)throw new Error('Duplicate publisher inventory identity');
 return rows;
}
