'use strict';
const fs=require('node:fs'),path=require('node:path'),{sha}=require('./archive.cjs');
function load(dir){
 const file=path.join(dir,'index.local.json');
 if(!fs.existsSync(file))return {sessions:new Map(),status:'absent',hash:null};
 const index=JSON.parse(fs.readFileSync(file,'utf8'));
 if(index.schema!=='third_plus_venue_archive.v2')throw Error('Wrong venue archive version');
 const sessions=new Map(),loaded=new Map();
 for(const row of index.sessions){
  const name=path.resolve(dir,row.file),relative=path.relative(fs.realpathSync(dir),fs.realpathSync(name));
  if(relative.startsWith('..')||path.isAbsolute(relative)||/sealed|holdout/i.test(relative))throw Error('Forbidden venue archive path');
  const s={...row.header,event_count:row.events,_results:new Map()};
  if(!['third_plus_execution_session.v1','third_plus_venue_session.v2','third_plus_bar_session.v2'].includes(s.schema)||s.synthetic||s.event_id!==row.event_id||s.date!==row.date)throw Error('Venue archive identity mismatch');
  const data=()=>{
   if(!loaded.has(name)){
    const bytes=fs.readFileSync(name);if(sha(bytes)!==row.sha256)throw Error('Venue source hash mismatch');
    loaded.set(name,JSON.parse(bytes));
    if(loaded.size>8)loaded.delete(loaded.keys().next().value);
   }
   return loaded.get(name);
  };
  for(const field of ['events','bars','quotes','statuses'])Object.defineProperty(s,field,{get(){return data()[field];}});
  const key=row.kind==='entry'?row.event_id:row.event_id+'|'+row.date;
  if(sessions.has(key))throw Error('Duplicate venue archive session');sessions.set(key,s);
 }
 return {sessions,status:'conditional_venue_data',mode:index.mode||'venue_events',hash:sha(fs.readFileSync(file)),counts:index.counts};
}
module.exports={load};
