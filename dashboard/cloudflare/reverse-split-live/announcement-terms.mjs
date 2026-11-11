// Bind current implementation terms to their clauses; preserve legal and trading
// clocks separately. Ambiguous approvals and genuinely conflicting terms fall back
// to the conservative legacy classifier.
const numbers={one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10,twelve:12,fifteen:15,twenty:20,thirty:30,forty:40,fifty:50,hundred:100};
const month='January|February|March|April|May|June|July|August|September|October|November|December';
function dates(s){return [...s.matchAll(new RegExp(`(?:${month})\\s+\\d{1,2}(?:st|nd|rd|th)?[,]?\\s+20\\d{2}|20\\d{2}-\\d{2}-\\d{2}`,'gi'))].flatMap(m=>{const n=Date.parse(m[0].replace(/(\d)(st|nd|rd|th)\b/,'$1'));return Number.isFinite(n)?[new Date(n).toISOString().slice(0,10)]:[];});}
function normalize(s){return s.replace(/\bone hundred(?:\s*\(100\))?/gi,'100').replace(/\b(one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty|forty|fifty|hundred)(?:\s*\(\s*\d+\s*\))?/gi,(_,w)=>String(numbers[w.toLowerCase()]));}
function ratios(s){
 const text=normalize(s),out=[];
 for(const m of text.matchAll(/\b1\s*[-:]?\s*(?:for|to|:)\s*[-:]?\s*(\d[\d,]*(?:\.\d+)?)\b|\b(\d[\d,]*(?:\.\d+)?)\s*[-:]?\s*(?:for|to|:)\s*[-:]?\s*1\b/gi)){const n=Number((m[1]||m[2]).replaceAll(',',''));if(n>1)out.push(n);}
 for(const m of text.matchAll(/\b1\s+(?:post[ -]split\s+|new\s+|common\s+|ordinary\s+|shares?\s+){1,8}for\s+(?:every\s+)?(\d+)\s+(?:pre[ -]split\s+|existing\s+|old\s+|common\s+|ordinary\s+){0,5}shares?\b/gi))if(Number(m[1])>1)out.push(Number(m[1]));
 for(const m of text.matchAll(/\b1\s+(?:post[ -]split|new)[^.;]{0,110}?\bfor\s+(?:every\s+)?(\d+)\s+(?:pre[ -]split|old|existing)\s+shares?\b/gi))if(Number(m[1])>1)out.push(Number(m[1]));
 for(const m of text.matchAll(/\b(\d+)\s+(?:issued\s+and\s+outstanding\s+|existing\s+|ordinary\s+|common\s+|old\s+|pre[ -]split\s+|shares?\s+|of\s+|the\s+|company[’']s\s+){0,12}(?:into|for)\s+1\s+(?:ordinary\s+|common\s+|new\s+|post[ -]split\s+){0,4}shares?\b/gi))if(Number(m[1])>1)out.push(Number(m[1]));
 return [...new Set(out)];
}
export function selectedAnnouncementTerms(text,day){
 if(/(?:reverse.{0,15}split|share consolidation).{0,100}(?:will not proceed|cancel(?:led|ed)|abandon)|(?:cancel(?:led|ed)|abandon).{0,100}(?:reverse.{0,15}split|share consolidation)/i.test(text))return null;
 const clauses=text.replace(/\b([ap])\.m\./gi,'$1m').replace(/\s+/g,' ').split(/(?<=[.!?])\s+/).map(s=>s.trim()).filter(Boolean),actions=[];let actionDates=[],legalDates=[],tradingDates=[],evidence=[];
 for(let i=0;i<clauses.length;i++){
  const s=clauses[i],context=(clauses[i-1]||'')+' '+s;
  if(/\b(?:prior|previous|historical)\s+(?:completed\s+)?(?:reverse|stock|share|split)|became effective|took effect|was effected|had effected/i.test(s))continue;
  if(/will not|cancelled|canceled|abandon|not to proceed/i.test(s))continue;
  const selected=/will (?:effect|implement|conduct)|has (?:approved|determined|selected)|approved (?:a |the )?(?:reverse |stock )?(?:split ratio|share consolidation)|announc(?:e|es|ed).{0,100}(?:reverse.{0,15}split|share consolidation)|(?:reverse|consolidation).{0,100}(?:will|shall|expected to) (?:become|take effect|be effective)|(?:board|directors).{0,100}approved/i.test(s);
  const provisional=/subject to.{0,100}(?:shareholder|stockholder|transaction|merger|closing)|if.{0,40}approved|may.{0,30}(?:effect|implement)|proposed (?:reverse|stock split|share consolidation)|range (?:of|from)|between.{0,80}and/i.test(s);
  if(selected&&!provisional){const rs=ratios(s);if(rs.length)actions.push(...rs);}
  if(!/split|consolidation|trading|certificate|amendment/i.test(context))continue;
  if(!/effective|take effect|takes effect|begin trading|commence trading|start trading|open for trading|trading.{0,45}(?:begin|commence|start)/i.test(s))continue;
  for(const m of s.matchAll(new RegExp(`(?:${month})\\s+\\d{1,2}(?:st|nd|rd|th)?[,]?\\s+20\\d{2}|20\\d{2}-\\d{2}-\\d{2}`,'gi'))){
   const d=dates(m[0])[0];if(!d||(day&&d<day))continue;
   const before=s.slice(Math.max(0,m.index-400),m.index),last=pattern=>[...before.matchAll(pattern)].at(-1)?.index??-1;
   const trigger=last(/effective(?=\s+(?:as of|on|at|from)\b|\s*$)|take effect|takes effect|begin trading|commence trading|start trading|open for trading|trading.{0,65}(?:begin|commence|start)/gi);if(trigger<0||before.length-trigger>240)continue;
   const trade=last(/trading|trade on|trade under/gi),legal=last(/certificate|amendment|legally|legal effective/gi),split=last(/reverse.{0,15}split|share consolidation/gi);
   if(trade>legal&&trade>split)tradingDates.push(d);else if(legal>split)legalDates.push(d);else actionDates.push(d);
  }
  evidence.push(s);
 }
 const unique=a=>[...new Set(a)],rs=unique(actions);actionDates=unique(actionDates);legalDates=unique(legalDates);tradingDates=unique(tradingDates);
 if(rs.length!==1||actionDates.length>1||legalDates.length>1||tradingDates.length>1)return null;
 const effective=actionDates[0]||legalDates[0]||tradingDates[0];if(!effective)return null;
 const conditions=clauses.filter(s=>/subject to.{0,150}(?:approval|merger|closing|transaction)/i.test(s)&&/split|consolidation|trading/i.test(s)).slice(0,4);
 return {implementation_conditions:conditions,status:'scheduled',ratio:rs[0],effective_date:effective,legal_effective_date:legalDates[0]||actionDates[0]||null,trading_date:tradingDates[0]||null,ratio_candidates:rs,date_candidates:unique([...actionDates,...legalDates,...tradingDates]),evidence:evidence.slice(0,6),reason:'Selected ratio with separately bound effective and trading dates',terms_version:'clause_bound_dates.2026-11-11.v1'};
}
