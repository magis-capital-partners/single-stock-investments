// The key identifies the original bytes. Only probe known duplicates so a new
// announcement still goes directly to its evidence write.
export async function putDocument(evidence,key,bytes,options,{known=false}={}){
  if(known){
    try{
      if(evidence.hasDocument&&await evidence.hasDocument(key,bytes.length))return;
      if(evidence.head&&(await evidence.head(key))?.size===bytes.length)return;
    }catch{
      // A failed probe must not prevent the original archival write.
    }
  }
  await evidence.put(key,bytes,options);
}

export async function archiveIndexedDocument(env,{hash,url,bytes,capturedAt,contentType,customMetadata}){
  const key='documents/'+hash;
  const saved=await env.DB.prepare('SELECT object_key,bytes FROM rs_documents WHERE sha256=?').bind(hash).first();
  await putDocument(env.EVIDENCE,key,bytes,{httpMetadata:{contentType},customMetadata},{
    known:saved?.object_key===key&&saved.bytes===bytes.length,
  });
  if(!saved)await env.DB.prepare('INSERT OR IGNORE INTO rs_documents(sha256,url,object_key,captured_at,bytes,content_type) VALUES(?,?,?,?,?,?)').bind(hash,url,key,capturedAt,bytes.length,contentType).run();
  return key;
}
