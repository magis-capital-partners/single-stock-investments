// Keep quote evaluation alive while ordinary background publication drains.
// Ownership is released by the caller only after this final checkpoint closes.
export async function finishHandoff({keepQuotes,drain,quiesce,persist,close}){
 let failure;
 const attempt=async work=>{try{await work();}catch(error){failure??=error;}};
 if(!keepQuotes)await attempt(quiesce);
 await attempt(drain);
 if(keepQuotes)await attempt(quiesce);
 await attempt(persist);
 await attempt(close);
 if(failure)throw failure;
}
