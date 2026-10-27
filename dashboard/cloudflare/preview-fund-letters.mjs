// Local development only. This directory is excluded from the deployed site.
import { createServer } from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { onRequestGet, onRequestPost } from '../functions/api/fund-letters.js';

const args=process.argv.slice(2);
const value=key=>args[args.indexOf(key)+1];
const port=args.includes('--port')?Number(value('--port')):8874;
const fixture=args.includes('--fixture');
if(!fixture&&!args.includes('--db'))throw new Error('Use --db PATH for the private archive, or --fixture for a synthetic UI test.');
const db=new DatabaseSync(fixture?':memory:':resolve(value('--db')));
db.exec(readFileSync(new URL('./migrations/0023_fund_letters.sql',import.meta.url),'utf8'));
const role=args.includes('--reader')?'reader':'owner';
if(fixture){
  db.exec("INSERT INTO fl_funds(id,name,manager,strategy) VALUES('test-fund','Example Fund · UI test','Example manager','A synthetic fixture for testing archive navigation.');");
  for(let n=0;n<105;n++){
    const q = n < 4 ? `2020Q${4 - n}` : '2019Q4';
    db.prepare('INSERT INTO fl_letters(id,fund_id,content_hash,pipeline_version,reporting_period,letter_date,ingested_at,published_revision) VALUES(?,?,?,?,?,?,?,?)').run('letter-'+n,'test-fund','hash-'+n,'fixture',q,n===0?'2020-10-15':null,'2026-10-23','revision-'+n);
    db.prepare('INSERT INTO fl_revisions(id,letter_id,created_at,published_at,author,status,overview,content_json,checks_json) VALUES(?,?,?,?,?,?,?,?,?)').run('revision-'+n,'letter-'+n,'2026-10-23','2026-10-23','UI fixture','published','This synthetic test letter describes an investment argument and a dated portfolio update.\n\nThe manager outlines selective additions to recurring-revenue compounders while maintaining cash discipline.',JSON.stringify({headline:'The fixture fund adds to recurring-revenue software while keeping cash reserves disciplined.',stance:{focus:'mixed',leaning_in:[{subject:'Recurring revenue equities',why:'The fixture fund favours durable customer payments over idle cash.',quote:'synthetic fixture'}],leaning_out:[{subject:'Cash',why:'The fixture fund keeps only a small cash balance.',quote:'synthetic fixture'}]}}),'{}');
    db.prepare('INSERT INTO fl_ideas(id,revision_id,letter_id,title,ticker,idea_type,activity,summary,ordinal) VALUES(?,?,?,?,?,?,?,?,?)').run('idea-1','revision-'+n,'letter-'+n,'A recurring revenue investment argument','TEST','long','new','The example fund argues that recurring customer payments create durable economics. This text is a synthetic interface fixture.\n\nIts argument rests on customer retention, distribution advantages and disciplined reinvestment. The fund identifies customer losses and execution as uncertainties.\n\nA real published article would include only arguments and figures reconciled to the historical letter.',0);
  }
}
const DB={prepare(sql){return{bind(...args){return{async all(){return{results:db.prepare(sql).all(...args)};},async first(){return db.prepare(sql).get(...args)||null;},async run(){return{meta:{changes:db.prepare(sql).run(...args).changes}};}};}};},async batch(statements){db.exec('BEGIN');try{const results=[];for(const statement of statements)results.push(await statement.run());db.exec('COMMIT');return results;}catch(error){db.exec('ROLLBACK');throw error;}}};
const assetRoot=fileURLToPath(new URL('../fund-letters/',import.meta.url));
const assets=new Map([['/fund-letters/','index.html'],['/fund-letters/index.html','index.html'],['/fund-letters/reader.js','reader.js'],['/fund-letters/reader.css','reader.css']]);
const server=createServer(async(req,res)=>{
  try{
    if(req.headers.host!==`127.0.0.1:${port}`&&req.headers.host!==`localhost:${port}`){res.writeHead(403);res.end();return;}
    const url=new URL(req.url,`http://127.0.0.1:${port}`);
    if(url.pathname==='/api/fund-letters'){
      const chunks=[];let size=0;for await(const chunk of req){size+=chunk.length;if(size>2_000_000){res.writeHead(413);res.end();return;}chunks.push(chunk);}
      const request=new Request(url,{method:req.method,headers:req.headers,...(req.method==='POST'?{body:Buffer.concat(chunks)}:{})});
      const context={request,env:{DB},data:{humanViewer:{email:role==='owner'?'drew@magiscapitalpartners.com':'reader@example.com',role}}};
      const response=await(req.method==='POST'?onRequestPost(context):onRequestGet(context));
      res.writeHead(response.status,Object.fromEntries(response.headers));res.end(await response.text());return;
    }
    const file=assets.get(url.pathname);
    if(!file){res.writeHead(404);res.end();return;}
    res.writeHead(200,{'content-type':file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html','cache-control':'no-store'});
    res.end(readFileSync(resolve(assetRoot,file)));
  }catch(error){res.writeHead(500);res.end(error.message);}
});
server.listen(port,'127.0.0.1',()=>console.log(`Local ${fixture?'synthetic UI test':'private archive'} · ${role} · http://127.0.0.1:${port}/fund-letters/`));
