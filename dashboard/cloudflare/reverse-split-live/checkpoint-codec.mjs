import {gzip,gunzip} from 'node:zlib';
import {promisify} from 'node:util';
import {createHash} from 'node:crypto';
const zip=promisify(gzip),unzip=promisify(gunzip),MAX=1024*1024*1024,hash=bytes=>createHash('sha256').update(bytes).digest('hex');
export async function compressCheckpoint(bytes){
 if(bytes.length>MAX)throw new Error('Checkpoint exceeds bounded restore size');const stored=await zip(bytes,{level:1});return {stored,compression:'gzip',stored_bytes:stored.length,stored_sha256:hash(stored)};
}
export async function restoreCheckpoint(stored,receipt){
 if(!Number.isInteger(receipt.bytes)||receipt.bytes<=0||receipt.bytes>MAX)throw new Error('Invalid bounded checkpoint receipt');
 if(receipt.compression&&receipt.compression!=='gzip')throw new Error('Unsupported checkpoint compression');
 if(receipt.compression&&(stored.length!==receipt.stored_bytes||hash(stored)!==receipt.stored_sha256))throw new Error('Compressed checkpoint checksum mismatch; original evidence preserved');
 const bytes=receipt.compression?await unzip(stored,{maxOutputLength:receipt.bytes}):stored;
 if(bytes.length!==receipt.bytes||hash(bytes)!==receipt.sha256)throw new Error('Collector checkpoint checksum mismatch; original evidence preserved');return bytes;
}
