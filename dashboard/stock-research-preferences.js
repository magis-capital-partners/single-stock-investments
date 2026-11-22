/* Browser cache plus authenticated, revision-checked cross-device persistence. */
(function(g){
'use strict';
const KEY='stock-research-workspace.v1';
const empty=()=>({templates:{},scenarios:{},watchlists:{},screens:{},alerts:{},imports:{},views:{}});
let data=empty(),revision=0,status='Saved on this browser',changed=false,loaded=false,ownerKey=null;
const listeners=new Set();let ready,chain=Promise.resolve();
try{const saved=JSON.parse(g.localStorage?.getItem(KEY)||'null');if(saved?.schema_version===KEY){data={...data,...saved.value};ownerKey=saved.viewer_key||null;}}catch{}
const snapshot=()=>JSON.parse(JSON.stringify(data));
function emit(){for(const fn of listeners)fn(status);}
function cache(){try{g.localStorage?.setItem(KEY,JSON.stringify({schema_version:KEY,viewer_key:ownerKey,value:data}));}catch{status='Browser storage is full; export your workspace to keep a copy.';}emit();}
function load(){
 if(!ready)ready=(async()=>{try{const r=await fetch('/api/v1/research/preferences?key=workspace',{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw Error('unavailable');const result=await r.json();revision=result.revision||0;if(ownerKey&&result.viewer_key&&ownerKey!==result.viewer_key){data=empty();changed=false;}ownerKey=result.viewer_key||ownerKey;if(!changed&&revision)data={...data,...result.value};loaded=true;status=revision?'Synced to your account':'Saved on this browser';cache();}catch{loaded=true;status='Saved on this browser · account sync unavailable';emit();}return snapshot();})();
 return ready;
}
function sync(){const value=snapshot();chain=chain.catch(()=>{}).then(async()=>{await load();try{const r=await fetch('/api/v1/research/preferences',{method:'PUT',credentials:'same-origin',headers:{'content-type':'application/json'},body:JSON.stringify({key:'workspace',value,revision})});if(r.status===409){status='Another device has newer changes. Export this workspace, then reload to reconcile.';emit();return;}if(!r.ok)throw Error('unavailable');const saved=await r.json();revision=saved.revision;status='Synced to your account';emit();}catch{status='Saved on this browser · account sync unavailable';emit();}});return chain;}
function set(category,key,value){if(!Object.hasOwn(data,category)||['__proto__','prototype','constructor'].includes(key))throw Error('Invalid saved item');changed=true;if(value===undefined)delete data[category][key];else data[category][key]=JSON.parse(JSON.stringify(value));cache();return sync();}
function get(category,key){return key===undefined?JSON.parse(JSON.stringify(data[category]||{})):JSON.parse(JSON.stringify(data[category]?.[key]??null));}
function restore(doc){if(doc?.schema_version!==KEY||!doc.value||typeof doc.value!=='object'||JSON.stringify(doc).length>500000)throw Error('Choose an exported research workspace under 500 KB.');for(const key of Object.keys(data)){const v=doc.value[key];if(v&&typeof v==='object'&&!Array.isArray(v))data[key]={...data[key],...v};}changed=true;cache();return sync();}
g.StockResearchPreferences={load,get,set,status:()=>status,on(fn){listeners.add(fn);return()=>listeners.delete(fn);},export:()=>({schema_version:KEY,value:snapshot()}),restore};
if(typeof module!=='undefined')module.exports=g.StockResearchPreferences;
})(typeof window!=='undefined'?window:globalThis);
