'use strict';
// Offline import only. Historical lending/margin records never query a broker.
const fs=require('node:fs'),path=require('node:path'),{sha}=require('./archive.cjs');
const {nyClock}=require('../short_framework/adapters.cjs');
function load(dir){
 const file=path.join(dir,'historical_costs.local.json');
 if(!fs.existsSync(file))return {status:'absent',hash:null};
 const bytes=fs.readFileSync(file),d=JSON.parse(bytes),root=fs.realpathSync(dir);
 if(d.schema!=='third_plus_historical_costs.v1'||!Array.isArray(d.borrow_terms)||!Array.isArray(d.margin_terms))throw Error('Invalid historical cost archive');
 for(const row of [...d.borrow_terms,...d.margin_terms]){
  if(!/^cik\/\d+$/.test(row.issuer)||!row.ticker||!/^\d{4}-\d{2}-\d{2}$/.test(row.from)||!/^\d{4}-\d{2}-\d{2}$/.test(row.to)||row.to<row.from||!Number.isFinite(Date.parse(row.available_at))||!/^[a-f0-9]{64}$/.test(row.source_sha256||''))throw Error('Undated historical cost record');
  const source=fs.realpathSync(path.resolve(dir,row.source_file)),relative=path.relative(root,source);
  if(relative.startsWith('..')||path.isAbsolute(relative)||/sealed|holdout/i.test(relative)||sha(fs.readFileSync(source))!==row.source_sha256)throw Error('Historical cost source mismatch');
 }
 for(const row of d.borrow_terms)if(!(Number.isFinite(row.apr)&&row.apr>=0))throw Error('Invalid recorded borrow rate');
 for(const row of d.margin_terms)if(!(Number.isFinite(row.fraction)&&row.fraction>=0&&Number.isFinite(row.minimum_per_share)&&row.minimum_per_share>=0))throw Error('Invalid recorded margin');
 function select(rows,p,date){
  const cutoff=Date.parse(nyClock(date,'09:31:00'));
  const matches=rows.filter(r=>r.issuer===p.issuer&&r.ticker===(p.current_ticker||p.ticker)&&r.from<=date&&date<=r.to&&Date.parse(r.available_at)<=cutoff);
  if(matches.length!==1)return null; // Ambiguous evidence cannot choose the cheaper record.
  return matches[0];
 }
 return {status:'source_bound',hash:sha(bytes),borrowTerms:(p,date)=>select(d.borrow_terms,p,date),marginAt:(p,date)=>{
  const row=select(d.margin_terms,p,date);return row?p.units/p.factor*Math.max(row.minimum_per_share,row.fraction*(p.open_mark||p.mark)):null;
 }};
}
module.exports={load};
