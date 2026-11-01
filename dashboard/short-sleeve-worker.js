importScripts('short-sleeve-engine.js');
self.onmessage = function(event) {
  try { self.postMessage({id:event.data.id,results:self.ShortSleeveEngine.monteCarlo(event.data.days,event.data.models)}); }
  catch(error) { self.postMessage({id:event.data.id,error:String(error.message||error)}); }
};
