import {putState} from './shadow-service.mjs';
// The clock alone must not force another billed database publication.
export async function putSummaryIfChanged(env,key,value,now){
  const old=await env.DB.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first();
  const content=x=>{const {generated_at,...rest}=x;return JSON.stringify(rest);};
  if(old&&content(JSON.parse(old.value))===content(value))return false;
  await putState(env,key,value,now);return true;
}
