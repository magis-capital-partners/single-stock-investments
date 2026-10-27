'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const C=require('./historical_costs.cjs'),{sha}=require('./archive.cjs');
test('historical rates are issuer, symbol, date, source and information-clock bound',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'third-plus-costs-'));
 try{
  assert.equal(C.load(dir).status,'absent');
  fs.writeFileSync(path.join(dir,'evidence.txt'),'Fixture historical source');
  const row={issuer:'cik/1',ticker:'T',from:'2026-01-05',to:'2026-01-06',available_at:'2026-01-05T14:00:00Z',source_file:'evidence.txt',source_sha256:sha(fs.readFileSync(path.join(dir,'evidence.txt')))};
  const file=path.join(dir,'historical_costs.local.json'),d={schema:'third_plus_historical_costs.v1',borrow_terms:[{...row,apr:.7}],margin_terms:[{...row,fraction:1,minimum_per_share:2.5}]};fs.writeFileSync(file,JSON.stringify(d));
  const c=C.load(dir),p={issuer:'cik/1',ticker:'T',units:10,factor:1,open_mark:2};
  assert.equal(c.borrowTerms(p,'2026-01-05').apr,.7);assert.equal(c.marginAt(p,'2026-01-05'),25);
  assert.equal(c.borrowTerms({...p,issuer:'cik/2'},'2026-01-05'),null);assert.equal(c.borrowTerms(p,'2026-01-07'),null);
  d.borrow_terms[0].available_at='2026-01-05T16:00:00Z';fs.writeFileSync(file,JSON.stringify(d));assert.equal(C.load(dir).borrowTerms(p,'2026-01-05'),null);
  fs.writeFileSync(path.join(dir,'evidence.txt'),'Changed source');assert.throws(()=>C.load(dir),/source mismatch/);
 }finally{
  const target=fs.realpathSync(dir),parent=fs.realpathSync(os.tmpdir());
  if(path.dirname(target)!==parent||!path.basename(target).startsWith('third-plus-costs-'))throw Error('Unexpected test cleanup path');
  fs.rmSync(target,{recursive:true,force:true});
 }
});
