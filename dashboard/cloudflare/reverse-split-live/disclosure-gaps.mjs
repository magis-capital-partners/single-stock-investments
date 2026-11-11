// Source-bound diagnosis only. Never creates financial facts or relaxes freshness.
export function financialDisclosureGap(bytes,source,observed_at){
 const text=new TextDecoder().decode(bytes).replace(/<[^>]*>/g,' ').replace(/&nbsp;|&#160;/g,' ').replace(/\s+/g,' ');
 const passages=text.split(/(?<=[.!?])\s+/).filter(s=>/annual report|quarterly report|form 10-[kq]/i.test(s)&&/not (?:yet |timely )?filed|failed to (?:timely )?file|not timely fil|delinquen|late fil/i.test(s));
 if(!passages.length||!source.sha256||!source.url)return null;
 return {kind:'issuer_filing_delinquency',source_url:source.url,source_sha256:source.sha256,published_at:source.published_at,observed_at,passages:passages.slice(0,4).map(s=>s.slice(0,1800)),financial_facts_created:false};
}
