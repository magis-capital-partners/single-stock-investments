import {gzip,gunzip} from 'node:zlib';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
import {setImmediate as yieldToLoop} from 'node:timers/promises';
const zip=promisify(gzip),unzip=promisify(gunzip),MAX=2*1024*1024*1024,hash=bytes=>createHash('sha256').update(bytes).digest('hex');
export async function compressCheckpoint(bytes){
 if(bytes.length>MAX)throw new Error('Checkpoint exceeds bounded restore size');const stored=await zip(bytes,{level:1});return {stored,compression:'gzip',stored_bytes:stored.length,stored_sha256:hash(stored)};
}

const BLOCK_BYTES=1024*1024, MAX_CACHED_BYTES=256*1024*1024;
export const BLOCK_DELTA_FORMAT='sqlite_block_delta.v1';
export const COMPACT_BLOCK_DELTA_FORMAT='sqlite_block_delta.v2';
export const COMPACT_BLOCK_BYTES=64*1024;
const deltaBlockBytes=new Map([[BLOCK_DELTA_FORMAT,BLOCK_BYTES],[COMPACT_BLOCK_DELTA_FORMAT,COMPACT_BLOCK_BYTES]]);
export const supportsCheckpointDelta=format=>deltaBlockBytes.has(format);

// Independently deflated blocks are standard concatenated gzip members. The
// existing restore path (including older releases) still validates the exact
// same reconstructed database. Cache only one generation of encoded blocks.
export function createCheckpointCompressor(){
  let previous=[];
  return async function compress(bytes){
    if(bytes.length>MAX)throw new Error('Checkpoint exceeds bounded restore size');
    if(bytes.length<=BLOCK_BYTES){
      previous=[];
      return {...await compressCheckpoint(bytes),compressed_blocks:1,reused_compression_blocks:0};
    }
    const count=Math.ceil(bytes.length/BLOCK_BYTES),next=new Array(count);
    let offset=0, reused=0;
    async function encode(){
      while(offset<count){
        const index=offset++;
        const block=bytes.subarray(index*BLOCK_BYTES,(index+1)*BLOCK_BYTES);
        const digest=hash(block);
        if(previous[index]?.digest===digest){
          next[index]=previous[index];
          reused++;
        }else{
          next[index]={digest,stored:await zip(block,{level:1})};
        }
        if((index+1)%16===0)await yieldToLoop();
      }
    }
    // Leave libuv capacity for report compression and file I/O. A failed
    // encoder cannot leave a sibling still reading a subsequent generation.
    const encoders=await Promise.allSettled([encode(),encode()]);
    const failure=encoders.find(result=>result.status==='rejected');
    if(failure)throw failure.reason;
    const stored=Buffer.concat(next.map(block=>block.stored));
    let position=0;
    // Slices share this output buffer, so the cache keeps at most one
    // existing payload and no duplicate copy of it.
    previous=stored.length<=MAX_CACHED_BYTES?next.map(block=>{
      const end=position+block.stored.length;
      const part={digest:block.digest,stored:stored.subarray(position,end)};
      position=end;
      return part;
    }):[];
    return {stored,compression:'gzip',stored_bytes:stored.length,stored_sha256:hash(stored),
      compressed_blocks:count-reused,reused_compression_blocks:reused,blocks:previous.length?previous:next};
  };
}

export function encodeCheckpointDelta(encoded,baseDigests){
  if(!encoded.blocks||!baseDigests)return null;
  const indices=[],members=[];
  let storedBytes=0;
  for(const [index,block] of encoded.blocks.entries()){
    if(block.digest===baseDigests[index])continue;
    indices.push(index);members.push(block.stored);storedBytes+=block.stored.length;
  }
  if(!indices.length||storedBytes>=encoded.stored_bytes*.6)return null;
  const stored=Buffer.concat(members,storedBytes);
  return {stored,stored_bytes:storedBytes,stored_sha256:hash(stored),indices};
}

function boundedReceipt(receipt){
  if(!Number.isInteger(receipt.bytes)||receipt.bytes<=0||receipt.bytes>MAX)throw new Error('Invalid bounded checkpoint receipt');
}
function checkStored(stored,receipt){
  if(stored.length!==receipt.stored_bytes||hash(stored)!==receipt.stored_sha256)throw new Error('Compressed checkpoint checksum mismatch; original evidence preserved');
}
function checkRestored(bytes,receipt){
  if(bytes.length!==receipt.bytes||hash(bytes)!==receipt.sha256)throw new Error('Collector checkpoint checksum mismatch; original evidence preserved');
  return bytes;
}
export async function restoreCheckpoint(stored,receipt){
 boundedReceipt(receipt);
 if(receipt.format||receipt.compression&&receipt.compression!=='gzip')throw new Error('Unsupported full checkpoint encoding');
 if(receipt.compression)checkStored(stored,receipt);
 const bytes=receipt.compression?await unzip(stored,{maxOutputLength:receipt.bytes}):stored;
 return checkRestored(bytes,receipt);
}

export async function restoreCheckpointDelta(stored,receipt,base){
  boundedReceipt(receipt);
  const blockBytes=deltaBlockBytes.get(receipt.format);
  const indices=receipt.changed_blocks,count=Math.ceil(receipt.bytes/blockBytes);
  if(!blockBytes||receipt.compression!=='gzip'||!Array.isArray(indices)||!indices.length||indices.length>count||
     indices.some((index,offset)=>!Number.isInteger(index)||index<0||index>=count||offset>0&&index<=indices[offset-1]))throw new Error('Invalid checkpoint delta block indices');
  checkStored(stored,receipt);
  const lengthOf=index=>Math.min(blockBytes,receipt.bytes-index*blockBytes);
  const changeBytes=indices.reduce((total,index)=>total+lengthOf(index),0);
  const changed=await unzip(stored,{maxOutputLength:changeBytes});
  if(changed.length!==changeBytes)throw new Error('Checkpoint delta length mismatch');
  const bytes=receipt.bytes<=base.length?base.subarray(0,receipt.bytes):Buffer.alloc(receipt.bytes);
  if(receipt.bytes>base.length)bytes.set(base);
  let offset=0;
  for(const index of indices){
    const stop=offset+lengthOf(index);
    bytes.set(changed.subarray(offset,stop),index*blockBytes);
    offset=stop;
  }
  return checkRestored(bytes,receipt);
}
