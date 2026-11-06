// External process only. Public financial documents never receive API credentials.
import https from 'node:https';
import {lookup} from 'node:dns/promises';
import {isIP} from 'node:net';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
export const hash=v=>createHash('sha256').update(v).digest('hex');
export const isSourceCooldown=e=>e?.code==='FINANCIAL_SOURCE_COOLDOWN'||[403,429].includes(e?.status)||/^Financial source (?:is in backoff|HTTP (?:403|429))$/.test(e?.message||e?.reason||'');
const cooldownError=retryAt=>Object.assign(new Error('Financial source is in backoff'),{code:'FINANCIAL_SOURCE_COOLDOWN',retryAt});
export function publicAddress(ip){
  if(isIP(ip)===4){const [a,b,c]=ip.split('.').map(Number);return !(a===0||a===10||a===127||a>=224||(a===169&&b===254)||(a===172&&b>=16&&b<=31)||(a===192&&b===168)||(a===100&&b>=64&&b<=127)||(a===198&&[18,19].includes(b))||(a===192&&b===0)||(a===198&&b===51&&c===100)||(a===203&&b===0&&c===113));}
  if(isIP(ip)!==6)return false;
  if(ip.toLowerCase().startsWith('::ffff:')){const tail=ip.slice(7);if(tail.includes('.'))return publicAddress(tail);const parts=tail.split(':');if(parts.length===2)return publicAddress([parseInt(parts[0],16)>>8,parseInt(parts[0],16)&255,parseInt(parts[1],16)>>8,parseInt(parts[1],16)&255].join('.'));return false;}
  return /^[23][a-f0-9]{0,3}:/i.test(ip)&&!/^2001:db8:|^2002:/i.test(ip);
}
export function primaryURL(value,origins=[]){
  const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||u.port||isIP(u.hostname.replace(/^\[|\]$/g,''))||u.hostname.endsWith('.local')||u.hostname==='localhost')throw new Error('Unsafe financial source URL');
  if(!['www.sec.gov','data.sec.gov','efts.sec.gov'].includes(u.hostname)&&!origins.includes(u.origin))throw new Error('Financial source origin is not verified for this issuer');return u;
}
export async function fetchPrimary(value,{origins=[],maximum=24000000,timeout=20000,wait=async()=>{},redirects=0}={}){
  const u=primaryURL(value,origins);await wait();let dnsTimer,addresses;try{addresses=await Promise.race([lookup(u.hostname,{all:true}),new Promise((_,reject)=>{dnsTimer=setTimeout(()=>reject(new Error('Financial DNS timeout')),timeout);})]);}finally{clearTimeout(dnsTimer);}if(!addresses.length||addresses.some(a=>!publicAddress(a.address)))throw new Error('Financial source resolves to a non-public address');const chosen=addresses.find(a=>a.family===4)||addresses[0];
  const result=await new Promise((resolve,reject)=>{
    const req=https.request(u,{method:'GET',servername:u.hostname,lookup:(_h,options,cb)=>options?.all?cb(null,[chosen]):cb(null,chosen.address,chosen.family),headers:{'user-agent':'MagisCapitalResearch/1.0 (financial coverage; drewgoldman01@gmail.com)','accept':'application/json, text/html, application/pdf, application/xml, text/plain, */*','accept-encoding':'identity'}},res=>{
      const chunks=[];let length=0;if(Number(res.headers['content-length'])>maximum){res.destroy();reject(new Error('Financial document size limit'));return;}
      res.on('data',b=>{length+=b.length;if(length>maximum){res.destroy(new Error('Financial document size limit'));return;}chunks.push(b);});res.on('error',reject);res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,bytes:Buffer.concat(chunks)}));
    });const timer=setTimeout(()=>req.destroy(new Error('Financial source timeout')),timeout);req.on('close',()=>clearTimeout(timer));req.on('error',reject);req.end();
  });
  if(result.status>=300&&result.status<400){if(redirects>=3||!result.headers.location)throw new Error('Financial redirect limit');return fetchPrimary(new URL(result.headers.location,u).href,{origins,maximum,timeout,wait,redirects:redirects+1});}
  if(result.status!==200){const e=new Error('Financial source HTTP '+result.status);e.status=result.status;e.retryAfter=Number(result.headers['retry-after'])||0;throw e;}
  return {...result,url:u.href,sha256:hash(result.bytes)};
}
export async function extractFiling(bytes,meta,{python=process.env.PYTHON|| (process.platform==='win32'?'python':'python3'),timeout=90000}={}){
  return new Promise((resolve,reject)=>{
    const child=spawn(python,[fileURLToPath(new URL('./fundamental_filing.py',import.meta.url))],{stdio:['pipe','pipe','pipe'],windowsHide:true,env:{...Object.fromEntries(Object.entries(process.env).filter(([k])=>['PATH','Path','SYSTEMROOT','SystemRoot','WINDIR','HOME','USERPROFILE','TMP','TEMP','TESSDATA_PREFIX','LANG'].includes(k))),PYTHONIOENCODING:'utf-8'}});let output='',failed=false;
    const timer=setTimeout(()=>{failed=true;child.kill();reject(new Error('Financial extraction time limit'));},timeout);
    child.stdout.on('data',b=>{output+=b;if(output.length>8000000){failed=true;child.kill();reject(new Error('Financial extraction output limit'));}});child.stderr.on('data',()=>{});child.stdin.on('error',()=>{});child.on('error',e=>{clearTimeout(timer);reject(e);});child.on('exit',code=>{clearTimeout(timer);if(failed)return;try{if(code!==0)throw new Error();resolve(JSON.parse(output));}catch{reject(new Error('Financial document extraction failed'));}});
    child.stdin.end(JSON.stringify({base64:Buffer.from(bytes).toString('base64'),meta}));
  });
}
export class FinancialSources {
  constructor(env,{offline=false,interval=1500}={}){this.env=env;this.offline=offline;this.interval=interval;this.last=0;this.cooldown=0;this.requests=0;}
  async get(url,{origins=[],mutable=false,maximum=24000000,refresh=false}={}){
    primaryURL(url,origins);const cacheKey='financials/http/'+hash(url)+'.json';const saved=await this.env.EVIDENCE.get(cacheKey),old=saved?await saved.json():null;
    if(old&&(!mutable||(!refresh&&Date.now()-Date.parse(old.captured_at)<3600000)||this.offline)){const object=await this.env.EVIDENCE.get(old.object_key);if(object){const bytes=Buffer.from(await object.arrayBuffer());if(bytes.length<=maximum&&hash(bytes)===old.sha256)return {...old,bytes};}}
    if(this.offline)throw new Error('Financial source is not cached');if(Date.now()<this.cooldown)throw cooldownError(this.cooldown);
    const wait=async()=>{await new Promise(r=>setTimeout(r,Math.max(0,this.interval-(Date.now()-this.last))));this.last=Date.now();this.requests++;};
    let doc;try{doc=await fetchPrimary(url,{origins,maximum,wait});}catch(e){if([403,429].includes(e.status)){this.cooldown=Date.now()+Math.max(300000,Math.min(3600000,(e.retryAfter||300)*1000));e.code='FINANCIAL_SOURCE_COOLDOWN';e.retryAt=this.cooldown;}throw e;}
    const record={url:doc.url,sha256:doc.sha256,object_key:'documents/'+doc.sha256,captured_at:new Date().toISOString(),bytes:doc.bytes.length,content_type:doc.headers['content-type']||'application/octet-stream'};
    await this.env.EVIDENCE.put(record.object_key,doc.bytes,{httpMetadata:{contentType:record.content_type}});await this.env.EVIDENCE.put(cacheKey,new TextEncoder().encode(JSON.stringify(record)),{httpMetadata:{contentType:'application/json'}});return {...record,bytes:doc.bytes};
  }
}
