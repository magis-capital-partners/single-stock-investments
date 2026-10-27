'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const R=require('./replay.cjs');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
function loadArchive(dir){
 const index=path.join(dir,'index.local.json');
 if(!fs.existsSync(index))return {sessions:new Map(),status:'absent',hash:null,files:[]};
 const doc=JSON.parse(fs.readFileSync(index,'utf8'));
 if(doc.schema!=='third_plus_execution_archive.v1'||!Array.isArray(doc.sessions))throw Error('Invalid execution archive');
 const sessions=new Map(),files=[];
 for(const r of doc.sessions){
  if(!['entry','cover'].includes(r.kind)||!r.event_id||!r.date||!/^[a-f0-9]{64}$/.test(r.sha256||''))throw Error('Invalid archive index row');
  const file=path.resolve(dir,r.file),relative=path.relative(fs.realpathSync(dir),fs.realpathSync(file));
  if(relative.startsWith('..')||path.isAbsolute(relative)||/holdout|sealed/i.test(relative))throw Error('Forbidden archive path');
  const bytes=fs.readFileSync(file);if(sha(bytes)!==r.sha256)throw Error('Execution archive hash mismatch');
  const s=JSON.parse(bytes.toString('utf8'));
  if(s.event_id!==r.event_id||s.date!==r.date||s.synthetic===true||s.schema!=='third_plus_execution_session.v1')throw Error('Archive identity/synthetic mismatch');
  R.validate(s);
  const key=r.kind==='entry'?r.event_id:r.event_id+'|'+r.date;
  if(sessions.has(key))throw Error('Duplicate archive session');
  sessions.set(key,s);files.push({key,sha256:r.sha256});
 }
 return {sessions,status:'source_attested_unvalidated_fills',hash:sha(fs.readFileSync(index)),files};
}
module.exports={loadArchive,sha};
