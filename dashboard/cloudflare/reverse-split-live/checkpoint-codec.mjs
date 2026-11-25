import {gzip,gunzip} from 'node:zlib';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
import {open} from 'node:fs/promises';
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

export function createCheckpointCompressor(){
  let previous=[];

  return async function compress(image){
    if(image.length<=0||image.length>MAX)throw new Error('Checkpoint exceeds bounded restore size');
    const handle=await open(image.path,'r');
    const rawHash=createHash('sha256'),blockBytes=COMPACT_BLOCK_BYTES;
    const count=Math.ceil(image.length/blockBytes),blocks=new Array(count);
    const input=Buffer.allocUnsafe(Math.min(2*BLOCK_BYTES,image.length));
    let storedBytes=0, reused=0;
    try{
      // Read the private file in order for the exact recovery hash, then
      // encode two streams of changed blocks without tying up the pool.
      for(let position=0;position<image.length;position+=input.length){
        const batch=input.subarray(0,Math.min(input.length,image.length-position));
        let offset=0;
        while(offset<batch.length){
          const {bytesRead}=await handle.read(batch,offset,batch.length-offset,position+offset);
          if(!bytesRead)throw new Error('Incomplete collector checkpoint capture');
          offset+=bytesRead;
        }
        rawHash.update(batch);
        let nextBlock=0;
        async function encode(){
          while(nextBlock<batch.length){
            const at=nextBlock;
            nextBlock+=blockBytes;
            const index=(position+at)/blockBytes;
            const bytes=batch.subarray(at,at+blockBytes),digest=hash(bytes),prior=previous[index];
            const block=prior?.digest===digest?prior:{digest,stored:Buffer.from(await zip(bytes,{level:1}))};
            blocks[index]=block;
            storedBytes+=block.stored.length;
            if(block===prior)reused++;
          }
        }
        const encoded=await Promise.allSettled([encode(),encode()]);
        const failure=encoded.find(result=>result.status==='rejected');
        if(failure)throw failure.reason;
      }
    }finally{await handle.close();}
    // Preserve a useful cache even when the compressed image grows past the
    // memory bound. Other blocks still encode and restore normally.
    let cacheBytes=0;
    previous=blocks.map(block=>{
      if(cacheBytes+block.stored.length>MAX_CACHED_BYTES)return null;
      cacheBytes+=block.stored.length;
      return block;
    });
    return {compression:'gzip',stored_bytes:storedBytes,sha256:rawHash.digest('hex'),blocks,
      compressed_blocks:count-reused,reused_compression_blocks:reused};
  };
}

function assembleBlocks(blocks,storedBytes){
  const stored=Buffer.concat(blocks.map(block=>block.stored),storedBytes);
  return {stored,stored_bytes:storedBytes,stored_sha256:hash(stored)};
}

export function assembleCheckpoint(encoded){
  return assembleBlocks(encoded.blocks,encoded.stored_bytes);
}

export function encodeCheckpointDelta(encoded,baseDigests){
  if(!encoded.blocks||!baseDigests)return null;
  const indices=[],changed=[];
  let storedBytes=0;
  for(const [index,block] of encoded.blocks.entries()){
    if(block.digest===baseDigests[index])continue;
    indices.push(index);changed.push(block);storedBytes+=block.stored.length;
  }
  if(!indices.length||storedBytes>=encoded.stored_bytes*.6)return null;
  return {...assembleBlocks(changed,storedBytes),indices};
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
