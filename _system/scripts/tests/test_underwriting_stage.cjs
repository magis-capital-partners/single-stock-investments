const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const load=()=>import('../underwriting_stage.mjs');

test('stage JSON parser rejects prose, arrays, oversized and missing output',async()=>{
 const {parseStageResult}=await load();
 assert.deepEqual(parseStageResult('```json\n{"ok":true}\n```'),{ok:true});
 for(const text of ['Here is JSON: {}','[]','x'.repeat(500001),undefined]) assert.throws(()=>parseStageResult(text));
});

test('stages have no repository and retain actual agent/run receipts',async()=>{
 const {executeStage}=await load();
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'underwriting-stage-'));
 let opts,closed=false;
 const receipt=await executeStage({apiKey:'test',model:'test-model',stage:'author',prompt:'Fresh evidence',
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
 await assert.rejects(executeStage({apiKey:'test',model:'test-model',stage:'challenger',prompt:'Challenge',timeoutMs:5,
   outputPath:path.join(dir,'out.json'),receiptPath:path.join(dir,'receipt.json'),
   create:async()=>({agentId:'slow-agent',close(){},send:async()=>({id:'slow-run',wait:()=>new Promise(()=>{}),
     cancel:async()=>{cancelled=true;}})})}),/time budget/);
 assert.equal(cancelled,true);
 assert.equal(JSON.parse(fs.readFileSync(path.join(dir,'receipt.json'))).agent_id,'slow-agent');
});
