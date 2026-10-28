/** One isolated model call. No repository, old valuation, credentials, PR or trade access. */
import {readFileSync, writeFileSync} from 'node:fs';

export function parseStageResult(text) {
  if (typeof text !== 'string' || text.length > 500_000) throw new Error('Missing or oversized stage JSON');
  const value = JSON.parse(text.trim().replace(/^```(?:json)?\s*\n([\s\S]*)\n```$/, '$1'));
  if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error('Stage must return a JSON object');
  return value;
}

export function modelSelection(id, {catalog=[], reasoningEffort}={}) {
  if (id === 'auto') {
    const router=catalog.find(m=>m.id === 'auto-smart');
    const cost=router?.parameters?.find(p=>p.id === 'optimize_for' && p.values.some(v=>v.value === 'cost'));
    // Prefer the documented cost router when enabled; "auto" is Cursor's
    // documented server-selected Auto on accounts without that router.
    return cost ? {id:router.id,params:[{id:cost.id,value:'cost'}]} : {id:'auto'};
  }
  const model=catalog.find(m=>m.id === id || m.aliases?.includes(id));
  if (!model) throw new Error(`Requested model ${id} is unavailable in this Cursor account; no fallback permitted`);
  if (!reasoningEffort) return {id:model.id};
  const parameter=model.parameters?.find(p=>
    ['reasoning_effort','reasoningEffort','effort','reasoning'].includes(p.id) && p.values.some(v=>v.value === reasoningEffort));
  if (!parameter) throw new Error(`Requested reasoning effort ${reasoningEffort} is unavailable for ${id}`);
  return {id:model.id,params:[{id:parameter.id,value:reasoningEffort}]};
}

export async function verifyCatalog({apiKey, policy, listModels}) {
  if (!apiKey) throw new Error('CURSOR_API_KEY is required for model discovery');
  const catalog=await (listModels || (await import('@cursor/sdk')).Cursor.models.list)({apiKey});
  const consumers=policy.model_ladder?.consumers || {};
  const selections={};
  try {
    for (const [stage,role] of Object.entries({author:'valuation_underwriter',challenger:'valuation_challenger',builder:'valuation_builder'})) {
      const config=consumers[role];
      if (!config?.model) throw new Error(`Missing explicit model policy for ${role}`);
      selections[stage]=modelSelection(config.model,{catalog,reasoningEffort:config.reasoning_effort});
    }
  } catch (error) {
    // Catalog metadata contains no credentials or issuer evidence.
    console.log(JSON.stringify({available_requested_models:catalog.filter(m=>/gpt-6|auto/.test(m.id))}));
    throw error;
  }
  return {provider:'cursor',selections,verified_at:new Date().toISOString()};
}

export async function executeStage({apiKey, model, reasoningEffort, stage, prompt, outputPath, receiptPath, create,
                                   catalog, listModels, timeoutMs=20*60*1000}) {
  if (!apiKey || !model || !['author','challenger','builder'].includes(stage)) throw new Error('Stage configuration is incomplete');
  catalog=catalog || await (listModels || (await import('@cursor/sdk')).Cursor.models.list)({apiKey});
  const selection=modelSelection(model,{catalog,reasoningEffort});
  const startedAt = new Date().toISOString();
  const factory=create || (await import('@cursor/sdk')).Agent.create;
  const agent = await factory({apiKey, model:selection,
    cloud:{repos:[],autoCreatePR:false,skipReviewerRequest:true,metadata:{purpose:'valuation-underwriting',stage}}});
  const receipt = {schema_version:'underwriting-call/1',stage,model,reasoning_effort:reasoningEffort,
    provider:'cursor',model_selection:selection,agent_id:agent.agentId,
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
    receipt.resolved_model=result.model;
    const mismatch=model !== 'auto' && result.model?.id && (result.model.id !== selection.id ||
      (result.model.params && selection.params?.some(p=>!result.model.params.some(r=>r.id === p.id && r.value === p.value))));
    if (mismatch) {
      receipt.status='model_selection_mismatch';
      writeFileSync(receiptPath,JSON.stringify(receipt,null,2)+'\n');
      throw new Error('Provider returned a different model than the requested selection');
    }
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
    if (process.argv.includes('--catalog')) {
      const policy=JSON.parse(readFileSync(new URL('../config/llm_usage_policy.json',import.meta.url),'utf8'));
      console.log(JSON.stringify(await verifyCatalog({apiKey:process.env.CURSOR_API_KEY,policy})));
    } else {
      await executeStage({apiKey:process.env.CURSOR_API_KEY,model:process.env.UNDERWRITING_MODEL,
      reasoningEffort:process.env.UNDERWRITING_REASONING_EFFORT || undefined,
      stage:process.env.UNDERWRITING_STAGE,prompt:readFileSync(process.env.UNDERWRITING_PROMPT,'utf8'),
      outputPath:process.env.UNDERWRITING_OUTPUT,receiptPath:process.env.UNDERWRITING_RECEIPT,
      timeoutMs:Math.min(20*60*1000,Number(process.env.UNDERWRITING_TIMEOUT_MS || 20*60*1000))});
      console.log(`Completed isolated ${process.env.UNDERWRITING_STAGE} stage.`);
    }
  } catch (error) {
    const key = process.env.CURSOR_API_KEY || '';
    console.error((String(error.message || error)).replaceAll(key || '\0','[redacted]').slice(0,1200));
    process.exitCode=1;
  }
}
