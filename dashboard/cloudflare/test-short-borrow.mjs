import assert from 'node:assert/strict';
import test from 'node:test';
import {parseSymbol,onRequestGet} from '../functions/api/v1/short-borrow.js';
test('borrow tickers reject SQL and path syntax',()=>{assert.equal(parseSymbol(' xxii '),'XXII');assert.equal(parseSymbol("x' OR 1=1"),null);assert.equal(parseSymbol('../private'),null);});
test('borrow API rejects bad symbols before querying',async()=>{const r=await onRequestGet({request:new Request('https://test/api/v1/short-borrow?symbol=bad%20symbol'),env:{}});assert.equal(r.status,400);});
test('borrow API fails visibly without a database',async()=>{const r=await onRequestGet({request:new Request('https://test/api/v1/short-borrow?symbol=XXII'),env:{}});assert.equal(r.status,503);});
test('absent ticker remains unknown and never becomes a locate',async()=>{let count=0;const db={prepare(sql){return {bind(){return this;},async first(){return ++count===1?{id:'v',as_of:new Date().toISOString()}:null;},async all(){return {results:[]};}};}};const r=await onRequestGet({request:new Request('https://test/api/v1/short-borrow?symbol=XXII'),env:{DB:db}});const d=await r.json();assert.equal(d.status,'not_listed');assert.equal(d.latest,null);assert.equal(d.locate_approved,false);});
