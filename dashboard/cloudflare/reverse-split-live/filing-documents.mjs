// Bounded primary-report fallback; never download the images in an oversized SGML bundle.
import {plain,decode} from './core.mjs';
const MAX=24*1024*1024;
export function filingIndexDocuments(html,p){
  if(!/^\d{1,10}$/.test(p.cik||'')||!/^\d{10}-\d{2}-\d{6}$/.test(p.accession||''))throw new Error('Filing identity is invalid');
  const accession=p.accession.replaceAll('-',''),prefix=`/Archives/edgar/data/${Number(p.cik)}/${accession}/`,base='https://www.sec.gov'+prefix+p.accession+'-index.html',documents=[];
  // Joint reports may live under a co-registrant. Both identities must be
  // explicitly listed by the official accession index; arbitrary CIKs stay denied.
  const registrants=new Set([...html.matchAll(/(?:[?&](?:amp;)?CIK=)(\d{1,10})\b/gi)].map(m=>String(Number(m[1]))));
  for(const match of html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/gi)){
    const cells=[...match[1].matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/gi)].map(m=>m[1]);if(cells.length<4)continue;
    const form=plain(cells[3]).toUpperCase(),primary=/^(?:8-K|6-K|10-[KQ]|20-F|40-F)(?:\/A)?$/.test(form)&&(!p.form||form===String(p.form).toUpperCase());if(!primary&&!/^EX-99(?:\.[A-Z0-9]+)?$/.test(form))continue;
    const href=/\bhref\s*=\s*["']([^"']+)["']/i.exec(cells[2])?.[1];if(!href)throw new Error('Filing index lacks a relevant document link');let u=new URL(decode(href),base);
    if(u.origin!=='https://www.sec.gov'||u.username||u.password||u.port)throw new Error('Filing index document has an unsafe origin');
    if(u.pathname.startsWith('/ix')&&u.searchParams.has('doc'))u=new URL(u.searchParams.get('doc'),'https://www.sec.gov');
    const bound=/^\/Archives\/edgar\/data\/(\d+)\/(\d{18})\/([A-Za-z0-9_.-]+\.(?:html?|txt|pdf))$/i.exec(u.pathname);
    if(u.origin!=='https://www.sec.gov'||u.search||!bound||bound[2]!==accession||(String(Number(bound[1]))!==String(Number(p.cik))&&!(registrants.has(String(Number(p.cik)))&&registrants.has(String(Number(bound[1]))))))throw new Error('Filing index document identity or format is unsupported');u.hash='';
    if(!documents.some(d=>d.url===u.href))documents.push({url:u.href,form});
  }
  const primaries=documents.filter(d=>/^(?:8-K|6-K|10-[KQ]|20-F|40-F)(?:\/A)?$/.test(d.form)&&(!p.form||d.form===String(p.form).toUpperCase())),htmlPrimary=primaries.filter(d=>/\.html?$/i.test(d.url));
  const named=p.primaryDocument&&/^[A-Za-z0-9_.-]+\.(?:html?|txt|pdf)$/i.test(p.primaryDocument)?primaries.filter(d=>new URL(d.url).pathname.split('/').at(-1)===p.primaryDocument):[];
  const primary=named.length===1?named[0]:primaries.length===1?primaries[0]:htmlPrimary.length===1&&primaries.every(d=>d===htmlPrimary[0]||/\.pdf$/i.test(d.url))?htmlPrimary[0]:null;
  if(!primary)throw new Error('Official filing index lacks an unambiguous primary report');
  const exhibits=documents.filter(d=>!primaries.includes(d));if(exhibits.length>64)throw new Error('Filing exceeds the bounded relevant-exhibit count');return [primary,...exhibits];
}
export async function loadFilingDocuments(env,p,fetchDocument){
  const maximum=env.COLLECTOR_MODE==='external_collector'?96*1024*1024:MAX,aggregate=env.COLLECTOR_MODE==='external_collector'?128*1024*1024:48*1024*1024;
  let original;
  try{original=await fetchDocument(p.url);}
  catch(e){if(!/Source exceeds document size limit/.test(e.message))throw e;}
  if(original){const text=new TextDecoder().decode(original.bytes),parts=[...text.matchAll(/<DOCUMENT>([\s\S]*?)<\/DOCUMENT>/gi)];if(!parts.some(m=>/<TYPE>\s*(?:8-K|6-K|10-[KQ]|20-F|40-F|EX-99)/i.test(m[1])&&/<PDF>/i.test(m[1])))return {documents:[original],texts:[text],raw:text,representation:'complete_submission'};}
  const indexURL=`https://www.sec.gov/Archives/edgar/data/${Number(p.cik)}/${p.accession.replaceAll('-','')}/${p.accession}-index.html`,index=await fetchDocument(indexURL,{maximum:2*1024*1024}),identityDocuments=[index],documents=[],parts=[];let selected,bytes=0;
  try{selected=filingIndexDocuments(new TextDecoder().decode(index.bytes),p);}catch(error){
    if(!/unambiguous primary/.test(error.message))throw error;
    const metadata=await fetchDocument(`https://data.sec.gov/submissions/CIK${String(p.cik).padStart(10,'0')}.json`,{maximum:8*1024*1024}),sub=JSON.parse(new TextDecoder().decode(metadata.bytes));if(String(Number(sub.cik))!==String(Number(p.cik)))throw new Error('Primary report submissions identity mismatch');
    const recent=sub.filings?.recent,position=recent?.accessionNumber?.indexOf(p.accession);if(!(position>=0)||!recent.primaryDocument?.[position])throw error;
    selected=filingIndexDocuments(new TextDecoder().decode(index.bytes),{...p,primaryDocument:recent.primaryDocument[position]});identityDocuments.push(metadata);
  }
  for(const d of selected){const doc=await fetchDocument(d.url,{maximum});bytes+=doc.bytes.length;if(bytes>aggregate)throw new Error('Relevant filing documents exceed aggregate size limit');documents.push({...doc,form:d.form});
    const pdf=String.fromCharCode(...doc.bytes.slice(0,5))==='%PDF-';if(pdf){if(!env.extractAnnouncementText)throw new Error('PDF announcement text reader is not configured');try{parts.push(await env.extractAnnouncementText(doc.bytes,{pdfProfile:env.COLLECTOR_MODE==='external_collector'?'external_primary_report':'standard',maximumMs:Math.max(1,Math.min(env.COLLECTOR_MODE==='external_collector'?20000:8000,(env.deadline||Date.now()+(env.COLLECTOR_MODE==='external_collector'?20000:8000))-Date.now())),onReview:review=>env.onDocumentReview?.({...doc,url:d.url},review)}));}catch(error){await env.onDocumentIssue?.({...doc,url:d.url},error);throw error;}}else parts.push(new TextDecoder().decode(doc.bytes));
  }
  return {documents,texts:parts,raw:parts.join('\n\n'),representation:'official_primary_report_and_exhibits',index_url:indexURL,identity_documents:identityDocuments};
}
