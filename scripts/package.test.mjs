import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import test from 'node:test';
const run = (...args) => spawnSync(process.execPath, ['scripts/state-gap.mjs', ...args], {encoding:'utf8'});
test('JSON evidence agrees with the hand-authored example outcomes', () => {
  const before = run('examples/add-hours/before.json', '--json');
  assert.equal(before.status, 1, before.stderr);
  const b = JSON.parse(before.stdout);
  assert.deepEqual(b.gaps, [{region:'payment',state:'ready',event:'add_hours'}]);
  assert.equal(b.cells.find(c=>c.id==='payment.ready.add_hours').resolution, '');
  const after = run('examples/add-hours/after.json', '--json');
  assert.equal(after.status, 0, after.stderr);
  const a = JSON.parse(after.stdout);
  assert.equal(a.cells.length, 48);
  assert.deepEqual(a.gaps, []);
  assert.deepEqual(a.unreachable, []);
  assert.deepEqual(a.deadEnds, []);
  assert.equal(a.cells.find(c=>c.id==='payment.ready.add_hours').resolution, 'W');
  assert.equal(a.cells.find(c=>c.id==='entitlement.increased.refund').resolution, 'A');
});
test('JSON and operator flags cannot silently discard one requested output', () => {
  assert.equal(run('examples/add-hours/after.json','--json','--for-operator').status, 2);
});
