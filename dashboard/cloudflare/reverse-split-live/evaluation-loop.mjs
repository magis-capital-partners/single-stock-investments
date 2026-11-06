// Serialize position changes while quote notifications bypass slow source downloads.
export function createEvaluationLoop({evaluate,shouldEvaluate=()=>true,onError=()=>{},minimumIntervalMs=500}={}){
  let tail=Promise.resolve(),closed=false,timer=null,notificationPending=false,lastStart=0;
  const run=event=>{
    if(closed)return Promise.resolve();const task=tail.catch(()=>{}).then(async()=>{lastStart=Date.now();return evaluate(event);});tail=task;return task;
  };
  return {
    run,
    notify(ticker){
      if(closed||notificationPending||(ticker!==null&&!shouldEvaluate(ticker)))return;notificationPending=true;
      timer=setTimeout(()=>{timer=null;run(null).catch(onError).finally(()=>{notificationPending=false;});},Math.max(0,minimumIntervalMs-(Date.now()-lastStart)));
    },
    async close(){closed=true;if(timer){clearTimeout(timer);timer=null;notificationPending=false;}await tail.catch(onError);},
  };
}
