// Bounded primary-report fallback; never download the images in an oversized SGML bundle.
import {plain,decode} from './core.mjs';
const MAX=24*1024*1024;
export function filingIndexDocuments(html,p){
  if(!/^\d{1,10}$/.test(p.cik||'')||!/^\d{10}-\d{2}-\d{6}$/.test(p.accession||''))throw new Error('Filing identity is invalid');
  const prefix=`/Archives/edgar/data/${Number(p.cik)}/${p.accession.replaceAll('-','')}/`,base='https://www.sec.gov'+prefix+p.accession+'-index.html',documents=[];
  for(const match of html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)){
    const cells=[...match[1].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map(m=>m[1]);if(cells.length<4)continue;
    const form=plain(cells[3]).toUpperCase(),primary=/^(?:8-K|6-K|10-[KQ]|20-F|40-F)(?:\/A)?$/.test(form)&&(!p.form||form===String(p.form).toUpperCase());if(!primary&&!/^EX-99(?:\.[A-Z0-9]+)?$/.test(form))continue;
    const href=/\bhref\s*=\s*["']([^"']+)["']/i.exec(cells[2])?.[1];if(!href)throw new Error('Filing index lacks a relevant document link');let u=new URL(decode(href),base);
    if(u.origin!=='https://www.sec.gov'||u.username||u.password||u.port)throw new Error('Filing index document has an unsafe origin');
    if(u.pathname.startsWith('/ix')&&u.searchParams.has('doc'))u=new URL(u.searchParams.get('doc'),'https://www.sec.gov');
    if(u.origin!=='https://www.sec.gov'||u.search||!u.pathname.startsWith(prefix)||!/^[A-Za-z0-9_.-]+\.(?:html?|txt|pdf)$/i.test(u.pathname.slice(prefix.length)))throw new Error('Filing index document identity or format is unsupported');u.hash='';
    if(!documents.some(d=>d.url===u.href))documents.push({url:u.href,form});
  }
  const primaries=documents.filter(d=>/^(?:8-K|6-K|10-[KQ]|20-F|40-F)(?:\/A)?$/.test(d.form)&&(!p.form||d.form===String(p.form).toUpperCase()));if(primaries.length!==1)throw new Error('Official filing index lacks an unambiguous primary report');const primary=primaries[0];
  if(documents.length>12)throw new Error('Filing exceeds the bounded relevant-exhibit count');return [primary,...documents.filter(d=>d!==primary)];
}
export async function loadFilingDocuments(env,p,fetchDocument){
  let original;
  try{original=await fetchDocument(p.url);}
  catch(e){if(!/Source exceeds document size limit/.test(e.message))throw e;}
  if(original){const text=new TextDecoder().decode(original.bytes),parts=[...text.matchAll(/<DOCUMENT>([\s\S]*?)<\/DOCUMENT>/gi)];if(!parts.some(m=>/<TYPE>\s*(?:8-K|6-K|10-[KQ]|20-F|40-F|EX-99)/i.test(m[1])&&/<PDF>/i.test(m[1])))return {documents:[original],texts:[text],raw:text,representation:'complete_submission'};}
  const indexURL=`https://www.sec.gov/Archives/edgar/data/${Number(p.cik)}/${p.accession.replaceAll('-','')}/${p.accession}-index.html`,index=await fetchDocument(indexURL,{maximum:2*1024*1024}),selected=filingIndexDocuments(new TextDecoder().decode(index.bytes),p),documents=[],parts=[];let bytes=0;
  for(const d of selected){const doc=await fetchDocument(d.url,{maximum:MAX});bytes+=doc.bytes.length;if(bytes>48*1024*1024)throw new Error('Relevant filing documents exceed aggregate size limit');documents.push({...doc,form:d.form});
    const pdf=String.fromCharCode(...doc.bytes.slice(0,5))==='%PDF-';if(pdf){if(!env.extractAnnouncementText)throw new Error('PDF announcement text reader is not configured');parts.push(await env.extractAnnouncementText(doc.bytes,{maximumMs:Math.max(1,Math.min(8000,(env.deadline||Date.now()+8000)-Date.now()))}));}else parts.push(new TextDecoder().decode(doc.bytes));
  }
  return {documents,texts:parts,raw:parts.join('\n\n'),representation:'official_primary_report_and_exhibits',index_url:indexURL};
}
