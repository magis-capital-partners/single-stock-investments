/* Audit the same model engine used by the dashboard, with exact stock identities. */
const fs=require('node:fs');
const path=require('node:path');
const V=require('../../dashboard/stock-valuation.js');
const W=require('../../dashboard/stock-valuation-view.js');
const args=process.argv.slice(2),arg=name=>args.includes(name)?args[args.indexOf(name)+1]:null;
const input=arg('--inputs'),data=arg('--data');
if(!input||!data)throw Error('Use --inputs private-valuation-inputs.json --data publication/data [--require-all-irrs] [--output report.json]');
const doc=JSON.parse(fs.readFileSync(input,'utf8')),core=JSON.parse(fs.readFileSync(path.join(data,'core.json'),'utf8'));
const models=doc.companies,expected=core.tickers.map(t=>t.ticker),errors=[],missing=[],methods={},gaps={};
let ready=0,irrs=0,rendered=0;
for(const ticker of expected){
  const m=models[ticker];
  if(!m||m.ticker!==ticker||m.schema_version!=='stock-valuation-model.v1'){errors.push(ticker+': missing model or identity');continue;}
  if(m.capital_actionable!==false||m.authority!=='screening_only')errors.push(ticker+': research model changed capital authority');
  methods[m.method]=(methods[m.method]||0)+1;
  const r=V.calculate(m);
  if(r.ready)ready++;else missing.push({ticker,reasons:[...new Set(Object.values(r.cases).flatMap(c=>c.gaps))]});
  for(const name of V.cases){
    const s=r.cases[name];
    if(s.irr!==null){
      irrs++;
      if(s.irr!==-1&&Math.abs(V.presentValue(s.flows,s.irr,r.inputs.entry_date)-r.inputs.entry_price)>Math.max(1e-7,r.inputs.entry_price*1e-8))errors.push(ticker+': '+name+' IRR does not reconcile');
      if(Math.abs(s.value-V.presentValue(s.flows,r.inputs.discount_rate,r.inputs.entry_date))>1e-7)errors.push(ticker+': '+name+' PV does not reconcile');
    }else if(!s.gaps.length)errors.push(ticker+': missing IRR without a reason');
    for(const gap of s.gaps)gaps[gap]=(gaps[gap]||0)+1;
  }
  const html=W.render({ticker,one_pager:{valuation_model:m}},{linkHtml:(url,label)=>`<a href="${url}">${label}</a>`});
  if((html.match(/<dt>Annual IRR<\/dt>/g)||[]).length!==3||!html.includes('Apply assumptions')||/NaN|Infinity|\bundefined\b/.test(html))errors.push(ticker+': incomplete valuation view');
  rendered++;
}
for(const ticker of Object.keys(models))if(!expected.includes(ticker))errors.push(ticker+': model is outside the dashboard universe');
const report={stocks:expected.length,models:Object.keys(models).length,rendered,models_with_three_irrs:ready,calculated_case_irrs:irrs,needs_inputs:missing.length,methods,gaps,errors,missing};
if(arg('--output'))fs.writeFileSync(arg('--output'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({...report,missing:undefined,gaps:undefined},null,2));
if(errors.length||(args.includes('--require-all-irrs')&&missing.length))process.exitCode=1;
