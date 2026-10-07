import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, writeFileSync, readFileSync, rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
const model='examples/add-hours/after.json';
function fixture(fn) {const d=mkdtempSync(join(tmpdir(),'gap-results-'));try{fn(d);}finally{rmSync(d,{recursive:true,force:true});}}
const run=(d,...args)=>spawnSync(process.execPath,['scripts/results.mjs',model,join(d,'results.html'),...args],{encoding:'utf8'});
test('a resolved model with no run produces no passing execution claim',()=>fixture(d=>{
 const r=run(d);assert.equal(r.status,0,r.stderr);
 const html=readFileSync(join(d,'results.html'),'utf8');
 assert.match(html,/48 modeled cells/);assert.match(html,/UNTESTED/);assert.doesNotMatch(html.split('<tbody>')[1].split('</tbody>')[0],/>PASS</);
}));
test('a passing tagged goal keeps its limited check, while unexecuted cells remain untested',()=>fixture(d=>{
 const hash=createHash('sha256').update(readFileSync(model)).digest('hex');
 writeFileSync(join(d,'run.json'),JSON.stringify({stamp:'synthetic',inputs:{model:hash}}));
 writeFileSync(join(d,'summary.json'),JSON.stringify([{id:'navigate',result:'pass',cells:['payment.ready.add_hours'],pass_check:{blocked:'POST /purchase'},goal:'<script>alert(1)</script>'}]));
 const r=run(d,'--run',d);assert.equal(r.status,0,r.stderr);
 const html=readFileSync(join(d,'results.html'),'utf8');
 assert.match(html,/>PASS</);assert.match(html,/POST \/purchase/);assert.match(html,/UNTESTED/);
 assert.doesNotMatch(html,/<script>alert/);assert.match(html,/&lt;script&gt;/);
}));
test('mismatched run identity refuses to attach evidence to another design',()=>fixture(d=>{
 writeFileSync(join(d,'run.json'),JSON.stringify({stamp:'old',inputs:{model:'wrong'}}));writeFileSync(join(d,'summary.json'),'[]');
 const r=run(d,'--run',d);assert.equal(r.status,2);assert.match(r.stderr,/model hash/);
}));
test('flaky results retain original and retry evidence instead of becoming a clean pass',()=>fixture(d=>{
 const hash=createHash('sha256').update(readFileSync(model)).digest('hex');
 writeFileSync(join(d,'run.json'),JSON.stringify({stamp:'retry-run',inputs:{model:hash}}));
 writeFileSync(join(d,'summary.json'),JSON.stringify([{id:'navigate',result:'flaky',cells:['payment.ready.add_hours'],reason:'passed on retry',pass_check:{url:'/checkout'}}]));
 const r=run(d,'--run',d);assert.equal(r.status,0,r.stderr);
 const html=readFileSync(join(d,'results.html'),'utf8');
 assert.match(html,/>FLAKY</);assert.match(html,/Retry record/);assert.match(html,/Original record/);
}));
