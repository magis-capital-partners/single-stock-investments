// Retry temporary transport failures without extending the bounded job deadline.
export async function recoverWatch(run,{maximumMs,clock=Date.now,pause=ms=>new Promise(r=>setTimeout(r,ms)),report=event=>console.error(JSON.stringify(event)),shouldStop=()=>false}={}){
  if(!(maximumMs>0))throw new Error('Positive collector duration required');
  const deadline=clock()+maximumMs;
  for(let attempt=1;;attempt++){
    if(shouldStop())throw new Error('Collector stop requested');
    try{return await run(Math.max(1,deadline-clock()));}
    catch(error){
      const temporary=/timeout|timed out|aborted|fetch failed|ECONNRESET|EAI_AGAIN|(?:Research|Evidence) storage HTTP (?:429|5\d\d)/i.test(error?.message||'');
      const delay=attempt*15000;
      if(!temporary||attempt>=3||clock()+delay>=deadline||shouldStop())throw error;
      report({event:'collector_restart',reason:'temporary_network_failure',attempt,next_attempt:attempt+1,delay_seconds:delay/1000});
      await pause(delay);
    }
  }
}
