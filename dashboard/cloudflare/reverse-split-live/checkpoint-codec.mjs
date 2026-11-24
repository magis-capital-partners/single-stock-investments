import {gzip,gunzip} from 'node:zlib';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
import {setImmediate as yieldToLoop} from 'node:timers/promises';
const zip=promisify(gzip),unzip=promisify(gunzip),MAX=2*1024*1024*1024,hash=bytes=>createHash('sha256').update(bytes).digest('hex');
export async function compressCheckpoint(bytes){
 if(bytes.length>MAX)throw new Error('Checkpoint exceeds bounded restore size');const stored=await zip(bytes,{level:1});return {stored,compression:'gzip',stored_bytes:stored.length,stored_sha256:hash(stored)};
}

const BLOCK_BYTES=1024*1024, MAX_CACHED_BYTES=256*1024*1024;

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
      compressed_blocks:count-reused,reused_compression_blocks:reused};
  };
}

export async function restoreCheckpoint(stored,receipt){
 if(!Number.isInteger(receipt.bytes)||receipt.bytes<=0||receipt.bytes>MAX)throw new Error('Invalid bounded checkpoint receipt');
 if(receipt.compression&&receipt.compression!=='gzip')throw new Error('Unsupported checkpoint compression');
 if(receipt.compression&&(stored.length!==receipt.stored_bytes||hash(stored)!==receipt.stored_sha256))throw new Error('Compressed checkpoint checksum mismatch; original evidence preserved');
 const bytes=receipt.compression?await unzip(stored,{maxOutputLength:receipt.bytes}):stored;
 if(bytes.length!==receipt.bytes||hash(bytes)!==receipt.sha256)throw new Error('Collector checkpoint checksum mismatch; original evidence preserved');return bytes;
}
