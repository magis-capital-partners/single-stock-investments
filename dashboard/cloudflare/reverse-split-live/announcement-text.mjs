import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {applyAnnouncementReview} from './announcement-reviews.mjs';
export function extractAnnouncementText(bytes,{maximumMs=8000,spawnProcess=spawn,onReview=async()=>{},pdfProfile='standard'}={}){
  if(!['standard','external_primary_report'].includes(pdfProfile))return Promise.reject(new Error('Unsupported announcement PDF profile'));
  if(bytes.length>(pdfProfile==='external_primary_report'?48:24)*1024*1024)return Promise.reject(new Error('Announcement PDF exceeds byte limit'));
  return new Promise((resolve,reject)=>{
    const child=spawnProcess(process.platform==='win32'?'python':'python3',[fileURLToPath(new URL('./announcement_text.py',import.meta.url))],{stdio:['pipe','pipe','pipe'],windowsHide:true,env:{...Object.fromEntries(Object.entries(process.env).filter(([k])=>['PATH','Path','SYSTEMROOT','SystemRoot','WINDIR','HOME','USERPROFILE','TMP','TEMP','LANG','TESSDATA_PREFIX'].includes(k))),PYTHONIOENCODING:'utf-8'}});let stdout='',done=false;
    const finish=(error,text)=>{if(done)return;done=true;clearTimeout(timer);if(error){child.kill();reject(error);}else resolve(text);},timer=setTimeout(()=>finish(new Error('Announcement PDF text timeout')),Math.max(1,maximumMs));
    child.on('error',()=>finish(new Error('Announcement PDF text reader unavailable')));child.stdin.on('error',()=>finish(new Error('Announcement PDF text reader input failed')));child.stdout.on('data',b=>{stdout+=b;if(Buffer.byteLength(stdout)>8*1024*1024)finish(new Error('Announcement PDF text output limit'));});child.stderr.on('data',()=>{});child.on('exit',async code=>{if(code!==0)return finish(new Error('Announcement PDF requires verified readable text'));try{const result=applyAnnouncementReview(JSON.parse(stdout),createHash('sha256').update(bytes).digest('hex'));if(result.visual_review)await onReview(result.visual_review);if(result.complete!==true&&Array.isArray(result.review_pages)&&result.review_pages.length){const error=new Error('Announcement PDF requires verified readable text; OCR candidates require review');error.extraction_diagnostic=result;return finish(error);}if(result.schema!=='announcement_text.v1'||typeof result.text!=='string'||!result.text.trim()||result.complete!==true)throw new Error();finish(null,result.text);}catch{finish(new Error('Announcement PDF text identity is invalid'));}});child.stdin.end(JSON.stringify({base64:Buffer.from(bytes).toString('base64'),profile:pdfProfile}));
  });
}
