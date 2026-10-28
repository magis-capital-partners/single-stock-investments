/** One isolated model call. No repository, old valuation, credentials, PR or trade access. */
import {readFileSync, writeFileSync} from 'node:fs';

export function parseStageResult(text) {
  if (typeof text !== 'string' || text.length > 500_000) throw new Error('Missing or oversized stage JSON');
  const value = JSON.parse(text.trim().replace(/^```(?:json)?\s*\n([\s\S]*)\n```$/, '$1'));
  if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error('Stage must return a JSON object');
  return value;
}

export function modelSelection(id) {
  return id === 'claude-sonnet-5' ? {id, params: [
    {id:'thinking',value:'true'},{id:'context',value:'1m'},{id:'effort',value:'high'},
  ]} : {id};
}

export async function executeStage({apiKey, model, stage, prompt, outputPath, receiptPath, create, timeoutMs=20*60*1000}) {
  if (!apiKey || !model || !['author','challenger','builder'].includes(stage)) throw new Error('Stage configuration is incomplete');
  const startedAt = new Date().toISOString();
  const factory=create || (await import('@cursor/sdk')).Agent.create;
  const agent = await factory({apiKey, model:modelSelection(model),
    cloud:{repos:[],autoCreatePR:false,skipReviewerRequest:true,metadata:{purpose:'valuation-underwriting',stage}}});
  const receipt = {schema_version:'underwriting-call/1',stage,model,agent_id:agent.agentId,
    started_at:startedAt,status:'created'};
  writeFileSync(receiptPath, JSON.stringify(receipt,null,2)+'\n');
  let timer;
  try {
    const run = await agent.send(prompt);
    receipt.run_id=run.id;
    receipt.status='running';
    writeFileSync(receiptPath, JSON.stringify(receipt,null,2)+'\n');
    const result = await Promise.race([run.wait(),new Promise((_,reject)=>{
      timer=setTimeout(()=>{
        receipt.status='timeout_cancel_requested';
        writeFileSync(receiptPath,JSON.stringify(receipt,null,2)+'\n');
        run.cancel().catch(()=>{});
        reject(new Error('Underwriting stage exceeded its time budget; cancellation requested'));
      },timeoutMs);
    })]);
    receipt.finished_at=new Date().toISOString();
    receipt.status=result.status;
    receipt.usage=result.usage;
    writeFileSync(receiptPath,JSON.stringify(receipt,null,2)+'\n');
    if (result.status !== 'finished' || !agent.agentId) throw new Error('The isolated model call did not complete');
    const payload = parseStageResult(result.result);
    writeFileSync(outputPath,JSON.stringify(payload,null,2)+'\n');
    return receipt;
  } finally {
    clearTimeout(timer);
    agent.close();
  }
}

if (process.argv[1]?.replaceAll('\\','/').endsWith('/underwriting_stage.mjs')) {
  try {
    await executeStage({apiKey:process.env.CURSOR_API_KEY,model:process.env.UNDERWRITING_MODEL,
      stage:process.env.UNDERWRITING_STAGE,prompt:readFileSync(process.env.UNDERWRITING_PROMPT,'utf8'),
      outputPath:process.env.UNDERWRITING_OUTPUT,receiptPath:process.env.UNDERWRITING_RECEIPT,
      timeoutMs:Math.min(20*60*1000,Number(process.env.UNDERWRITING_TIMEOUT_MS || 20*60*1000))});
    console.log(`Completed isolated ${process.env.UNDERWRITING_STAGE} stage.`);
  } catch (error) {
    const key = process.env.CURSOR_API_KEY || '';
    console.error((String(error.message || error)).replaceAll(key || '\0','[redacted]').slice(0,1200));
    process.exitCode=1;
  }
}
