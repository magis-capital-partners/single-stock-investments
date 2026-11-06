import {readFileSync} from 'node:fs';
// Scheduled collectors apply the small, idempotent fallback indexes on their
// first start after a quota reset, even if the push-time migration was blocked.
export async function ensureRemoteReadIndexes(db){
 const key='track_read_indexes.v1';if(await db.prepare('SELECT value FROM rs_state WHERE key=?').bind(key).first())return;
 const sql=readFileSync(new URL('./migrations/0006_track_read_indexes.sql',import.meta.url),'utf8');
 for(const statement of sql.replace(/^--.*$/gm,'').split(';').map(s=>s.trim()).filter(Boolean))await db.prepare(statement).run();
 await db.prepare('INSERT OR IGNORE INTO rs_state(key,value,updated_at) VALUES(?,?,?)').bind(key,'applied',new Date().toISOString()).run();
}
