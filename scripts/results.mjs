#!/usr/bin/env node
// Join deterministic model cells with one immutable run. Archify remains the map renderer.
import {readFileSync, writeFileSync, existsSync} from 'node:fs';
import {dirname, join, relative, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
const escape = value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;');
const read = path => JSON.parse(readFileSync(path,'utf8'));
try {
  const [modelPath, output, ...args] = process.argv.slice(2);
  if (!modelPath || !output?.endsWith('.html') || args.length % 2 || args.some((a,i)=>i%2===0&&!['--run','--diagram'].includes(a)))
    throw new Error('Usage: node scripts/results.mjs model.json output.html [--run DIR] [--diagram map.html]');
  const options = Object.fromEntries(Array.from({length:args.length/2},(_,i)=>[args[2*i],args[2*i+1]]));
  const engine = spawnSync(process.execPath,[join(dirname(fileURLToPath(import.meta.url)),'state-gap.mjs'),modelPath,'--json'],{encoding:'utf8'});
  if (![0,1].includes(engine.status)) throw new Error(engine.stderr || 'Model validation failed');
  const report = JSON.parse(engine.stdout);
  const modelHash = createHash('sha256').update(readFileSync(modelPath)).digest('hex');
  const cellIds = new Set(report.cells.map(c=>c.id));
  let records=[], run=null;
  const runDir = options['--run'];
  if (runDir) {
    run = read(join(runDir,'run.json'));
    if (run.inputs?.model !== modelHash) throw new Error('Run model hash does not match this model. Use the original model for this run.');
    records = read(join(runDir,'summary.json'));
    if (!Array.isArray(records)) throw new Error('summary.json must be the walker record list');
    for (const row of records) {
      if (!/^[a-zA-Z0-9_-]+$/.test(row.id) || !['pass','flaky','fail','error','skip'].includes(row.result) || !Array.isArray(row.cells ?? [])) throw new Error('Invalid run record');
      if ((row.cells??[]).some(c=>!cellIds.has(c))) throw new Error('Run record tags a cell outside the model');
    }
  }
  const link = (path,label) => existsSync(path) ? `<a href="${escape(relative(dirname(resolve(output)),resolve(path)).split('/').map(encodeURIComponent).join('/'))}">${escape(label)}</a>` : `<span>${escape(label)} (file unavailable)</span>`;
  const design={W:'PLANNED: wired',I:'PLANNED: ignored',A:'PLANNED: absent, owner assigned',S:'PLANNED: survives','':'UNRESOLVED'};
  const rows=report.cells.map(cell=>{
    const tagged=records.filter(r=>(r.cells??[]).includes(cell.id));
    const observations=tagged.length ? tagged.map(r=>`<details><summary><b class="${r.result}">${r.result.toUpperCase()}</b> ${escape(r.id)}</summary><p>${escape(r.goal??'')}</p><p>Check: <code>${escape(JSON.stringify(r.pass_check??{}))}</code></p><p>${escape(r.reason??'')}</p>${link(join(runDir,r.id,'record.json'),'Original record')} · ${link(join(runDir,r.id,'final.png'),'Final frame')}${r.result==='flaky'||r.attempts ? ' · '+link(join(runDir,'retry',r.id,'record.json'),'Retry record')+' · '+link(join(runDir,'retry',r.id,'final.png'),'Retry frame') : ''}</details>`).join('') : '<b class="untested">UNTESTED</b>';
    return `<tr data-status="${tagged.length?tagged.map(r=>r.result).join(' '):'untested'}"><td><code>${escape(cell.id)}</code></td><td>${design[cell.resolution]}</td><td>${observations}</td></tr>`;
  }).join('\n');
  const map=options['--diagram'];
  if(map && !existsSync(map)) throw new Error('Diagram file does not exist');
  const html=`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Workflow evidence</title>
<style>body{font:16px/1.55 system-ui,sans-serif;color:#18333d;background:#f4f3ed;margin:0;padding:clamp(20px,4vw,64px)}main{max-width:1200px;margin:auto}h1{font-size:clamp(32px,5vw,56px);letter-spacing:-.04em;margin:.4em 0}a{color:#005e71}table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;vertical-align:top;padding:16px;border-bottom:1px solid #d8dedc}code{overflow-wrap:anywhere}summary{cursor:pointer}.pass{color:#176149}.fail,.error{color:#a92c2c}.flaky,.skip{color:#795314}.untested{color:#56646b}select{font:inherit;padding:8px;margin:12px}aside{padding:18px;border-left:4px solid #b56823;background:#fff8e9;margin:24px 0}.table{overflow:auto}small{color:#485c65}details p{max-width:480px}a:focus-visible,summary:focus-visible,select:focus-visible{outline:3px solid #a84b17;outline-offset:3px}</style>
<main><small>STATE GAP + JEV</small><h1>What is decided?<br>What was actually checked?</h1><p>${report.cells.length} modeled cells · ${report.gaps.length} unresolved · ${report.unreachable.length} unreachable states · ${report.deadEnds.length} dead ends</p>
<p>${run?`Run: <strong>${escape(run.stamp)}</strong> · ${link(join(runDir,'run.json'),'Run identity')} · ${link(join(runDir,'summary.json'),'All records')}`:'Design-only view. No browser run attached.'}</p>
${map?`<p>${link(map,'Open interactive workflow map')}</p>`:''}
<aside>A linked goal can pass its recorded check while other properties of that cell remain untested. Planned behavior, ignored events and assigned recovery are design decisions. They do not prove implementation. Retry outcomes must be inspected alongside original attempts.</aside>
<label for="status">Show execution status</label><select id="status"><option value="all">All cells</option>${['pass','flaky','fail','error','skip','untested'].map(s=>`<option value="${s}">${s.toUpperCase()}</option>`).join('')}</select>
<div class="table"><table><thead><tr><th>Model cell</th><th>Design</th><th>Linked goal observations</th></tr></thead><tbody>${rows}</tbody></table></div><p><small>Model SHA-256: ${modelHash}</small></p></main>
<script>document.querySelector('#status').addEventListener('change',event=>{for(const row of document.querySelectorAll('tbody tr'))row.hidden=event.target.value!=='all'&&!row.dataset.status.split(' ').includes(event.target.value);});</script></html>`;
  writeFileSync(output,html);
  console.log(`Saved ${output}: ${report.cells.length} cells, ${records.length} goal observations.`);
} catch(error) {console.error(error.message);process.exitCode=2;}
