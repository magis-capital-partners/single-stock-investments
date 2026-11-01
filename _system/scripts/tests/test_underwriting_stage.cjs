const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const load=()=>import('../underwriting_stage.mjs');
const catalog=[{id:'test-model'},
 {id:'gpt-6.1-sol',parameters:[{id:'reasoning_effort',values:[{value:'medium'},{value:'high'}]}]},
 {id:'auto-smart',parameters:[{id:'optimize_for',values:[{value:'cost'},{value:'balanced'}]}]}];

test('requested Sol High and Cursor Auto resolve only through supported catalog selections',async()=>{
 const {modelSelection}=await load();
 assert.deepEqual(modelSelection('gpt-6.1-sol',{catalog,reasoningEffort:'high'}),
   {id:'gpt-6.1-sol',params:[{id:'reasoning_effort',value:'high'}]});
 assert.deepEqual(modelSelection('auto',{catalog}),{id:'auto-smart',params:[{id:'optimize_for',value:'cost'}]});
 assert.throws(()=>modelSelection('gpt-6.1-sol',{catalog:[],reasoningEffort:'high'}),/unavailable/);
 assert.throws(()=>modelSelection('gpt-6.1-sol',{catalog:[{id:'gpt-6.1-sol'}],reasoningEffort:'high'}),/reasoning/);
 assert.deepEqual(modelSelection('auto',{catalog:[]}),{id:'auto'});
 assert.deepEqual(modelSelection('gpt-6.1-sol',{reasoningEffort:'high',catalog:[{id:'gpt-6.1-sol-high'}]}),{id:'gpt-6.1-sol-high'});
 assert.deepEqual(modelSelection('gpt-6.1-sol',{reasoningEffort:'high',catalog:[{id:'gpt-6.1-sol',
   variants:[{params:[{id:'reasoning',value:'high'}]}]}]}),{id:'gpt-6.1-sol',params:[{id:'reasoning',value:'high'}]});
});

test('stage JSON parser rejects prose, arrays, oversized and missing output',async()=>{
 const {parseStageResult}=await load();
 assert.deepEqual(parseStageResult('```json\n{"ok":true}\n```'),{ok:true});
 for(const text of ['Here is JSON: {}','[]','x'.repeat(500001),undefined]) assert.throws(()=>parseStageResult(text));
});

test('stages have no repository and retain actual agent/run receipts',async()=>{
 const {executeStage}=await load();
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'underwriting-stage-'));
 let opts,closed=false;
 const receipt=await executeStage({apiKey:'test',model:'test-model',catalog,stage:'author',prompt:'Fresh evidence',
   outputPath:path.join(dir,'out.json'),receiptPath:path.join(dir,'receipt.json'),
   create:async options=>{opts=options;return{agentId:'isolated-author',close(){closed=true;},
     send:async()=>({id:'run-1',wait:async()=>({status:'finished',result:'{"schema":"contract"}'})})};}});
 assert.deepEqual(opts.cloud.repos,[]);
 assert.equal(opts.cloud.autoCreatePR,false);
 assert.equal(opts.cloud.envVars,undefined);
 assert.equal(receipt.agent_id,'isolated-author');
 assert.equal(receipt.run_id,'run-1');
 assert.equal(closed,true);
});

test('a timed-out paid stage is cancelled and its agent id survives',async()=>{
 const {executeStage}=await load();
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'underwriting-timeout-'));
 let cancelled=false;
 await assert.rejects(executeStage({apiKey:'test',model:'test-model',catalog,stage:'challenger',prompt:'Challenge',timeoutMs:5,
   outputPath:path.join(dir,'out.json'),receiptPath:path.join(dir,'receipt.json'),
   create:async()=>({agentId:'slow-agent',close(){},send:async()=>({id:'slow-run',wait:()=>new Promise(()=>{}),
     cancel:async()=>{cancelled=true;}})})}),/time budget/);
 assert.equal(cancelled,true);
 assert.equal(JSON.parse(fs.readFileSync(path.join(dir,'receipt.json'))).agent_id,'slow-agent');
});

test('an unavailable requested model cannot start a paid agent or silently fall back',async()=>{
 const {executeStage}=await load();
 let created=false;
 await assert.rejects(executeStage({apiKey:'test',model:'gpt-6.1-sol',reasoningEffort:'high',stage:'author',prompt:'Evidence',
   listModels:async()=>[],create:async()=>{created=true;}}),/unavailable/);
 assert.equal(created,false);
});

test('provider model mismatch is retained and cannot become a finished draft',async()=>{
 const {executeStage}=await load();
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'underwriting-model-'));
 const receiptPath=path.join(dir,'receipt.json');
 await assert.rejects(executeStage({apiKey:'test',model:'gpt-6.1-sol',reasoningEffort:'high',catalog,stage:'author',prompt:'Evidence',
   outputPath:path.join(dir,'out.json'),receiptPath,
   create:async()=>({agentId:'isolated-author',close(){},send:async()=>({id:'run',
     wait:async()=>({status:'finished',model:{id:'another-model'},result:'{}'})})})}),/different model/);
 assert.equal(fs.existsSync(path.join(dir,'out.json')),false);
 const receipt=JSON.parse(fs.readFileSync(receiptPath));
 assert.equal(receipt.status,'model_selection_mismatch');
 assert.equal(receipt.model_selection.params[0].value,'high');
});

test('catalog preflight independently resolves all three roles without an agent call',async()=>{
 const {verifyCatalog}=await load();
 const report=await verifyCatalog({apiKey:'test',listModels:async()=>catalog,policy:{model_ladder:{consumers:{
   valuation_underwriter:{model:'gpt-6.1-sol',reasoning_effort:'high'},
   valuation_challenger:{model:'gpt-6.1-sol',reasoning_effort:'high'},valuation_builder:{model:'auto'},
 }}}});
 assert.equal(report.selections.author.id,'gpt-6.1-sol');
 assert.equal(report.selections.challenger.params[0].value,'high');
 assert.equal(report.selections.builder.id,'auto-smart');
});

test('local Sol and compiler policy never contacts a model API for discovery',async()=>{
 const {verifyCatalog}=await load();
 const report=await verifyCatalog({policy:{model_ladder:{consumers:{
   valuation_underwriter:{model:'gpt-6.1-sol',reasoning_effort:'high',provider:'codex-local'},
   valuation_challenger:{model:'gpt-6.1-sol',reasoning_effort:'high',provider:'codex-local'},
   valuation_builder:{model:'underwriting-compiler/1',provider:'deterministic'},
 }}},listModels:async()=>{throw new Error('Unexpected model API request');}});
 assert.equal(report.provider,'local');
 assert.equal(report.selections.builder.model_calls,0);
});
