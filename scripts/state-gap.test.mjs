import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const cli = join(root, "scripts", "state-gap.mjs");
const fixture = (...parts) => join(root, "fixtures", ...parts);

function run(args) {
  return spawnSync(process.execPath, [cli, ...args], { encoding: "utf8" });
}

function json(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function withModel(model, callback) {
  const dir = mkdtempSync(join(tmpdir(), "state-gap-test-"));
  const path = join(dir, "model.json");
  writeFileSync(path, `${JSON.stringify(model, null, 2)}\n`);
  try {
    return callback(path);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function section(output, heading) {
  const start = output.indexOf(`## ${heading}`);
  assert.notEqual(start, -1, `missing section ${heading}`);
  const rest = output.slice(start);
  const next = rest.slice(3).search(/\n## /);
  return next === -1 ? rest : rest.slice(0, next + 3);
}

function gapTuples(output) {
  return [...section(output, "Gaps").matchAll(/^- `([^`]+)` \/ `([^`]+)` \/ `([^`]+)`/gm)]
    .map((match) => [match[1], match[2], match[3]]);
}

function tupleSet(tuples) {
  return new Set(tuples.map((tuple) => tuple.join(" / ")));
}

test("C1: Run A reports the exact hand-authored 105-gap oracle", () => {
  const result = run([fixture("run-a-verbatim.json")]);
  assert.equal(result.status, 1, result.stderr);

  const expected = json(fixture("run-a-verbatim.expected.json"));
  const allExpected = [
    ...expected.authoredEventNonFinal,
    ...expected.seededNonFinal,
    ...expected.finalState,
  ];
  assert.equal(allExpected.length, 105);
  assert.deepEqual(tupleSet(gapTuples(result.stdout)), tupleSet(allExpected));
  assert.equal(expected.authoredEventNonFinal.length, 24);
  assert(tupleSet(gapTuples(result.stdout)).has("default / paid / sales_campaign_sent"));
});

test("C2: the closed Run A fixture has no structural finding", () => {
  const result = run([fixture("run-a-closed.json")]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(section(result.stdout, "Gaps"), /- None\./);
  assert.match(section(result.stdout, "Unreachable states"), /- None\./);
  assert.match(section(result.stdout, "Dead-end states"), /- None\./);
});

test("C3: final states are crossed with refund and can be explicitly absent", () => {
  const model = json(fixture("run-a-closed.json"));
  model.decisions = model.decisions.filter((decision) => !(
    decision.region === "default" && decision.state === "closed" && decision.event === "refund"
  ));

  withModel(model, (path) => {
    const open = run([path]);
    assert.equal(open.status, 1, open.stderr);
    assert(tupleSet(gapTuples(open.stdout)).has("default / closed / refund"));

    model.decisions.push({
      region: "default",
      state: "closed",
      event: "refund",
      absent: { owner: "Operations", recovery: "Review the refund manually." },
    });
    writeFileSync(path, `${JSON.stringify(model, null, 2)}\n`);
    const resolved = run([path]);
    assert.equal(resolved.status, 0, resolved.stderr);
  });
});

test("C4: two regions share events and distinguish wired, ignored, absent, and gap cells", () => {
  const result = run([fixture("season-pass-two-regions.json")]);
  assert.equal(result.status, 1, result.stderr);
  assert(tupleSet(gapTuples(result.stdout)).has(
    "marketing / subscribed / full_series_checkout_completed",
  ));

  const fulfillment = section(result.stdout, "Fulfillment matrix");
  const paidRow = fulfillment.split("\n").find((line) => line.startsWith("| Paid |"));
  assert.equal(
    paidRow,
    "| Paid |  | W | I | A | W |  |  |  |  |  |  |  |",
  );
});

test("C5: seed provenance is injected once and cannot be supplied by input", () => {
  const base = run([fixture("run-a-verbatim.json")]);
  const header = section(base.stdout, "Run A matrix").split("\n")[2];
  assert.equal((header.match(/\(seeded\)/g) ?? []).length, 7);

  const model = json(fixture("run-a-verbatim.json"));
  model.events.push({ id: "refund", name: "Refund" });
  withModel(model, (path) => {
    const supplied = run([path]);
    const suppliedHeader = section(supplied.stdout, "Run A matrix").split("\n")[2];
    assert.equal((suppliedHeader.match(/\(seeded\)/g) ?? []).length, 6);
    assert.match(suppliedHeader, /\| Refund \|/);
    assert.doesNotMatch(suppliedHeader, /Refund \(seeded\)/);
  });

  const spoofed = run([fixture("invalid", "seeded-input-key.json")]);
  assert.equal(spoofed.status, 2);
  assert.match(spoofed.stderr, /seeded/);
});

test("C6: invalid schema and CLI cases exit 2 with specific diagnostics", () => {
  const cases = [
    ["missing-canonical-activity.json", "CRM"],
    ["duplicate-system-name.json", "PAYMENT"],
    ["system-neither-form.json", "systems[0]"],
    ["system-both-forms.json", "systems[0]"],
    ["system-unknown-region.json", "missing"],
    ["system-none-without-reason.json", "reason"],
    ["decision-both-forms.json", "decisions[0]"],
    ["decision-neither-form.json", "decisions[0]"],
    ["absent-missing-owner.json", "owner"],
    ["absent-missing-recovery.json", "recovery"],
    ["duplicate-decision-cell.json", "refund"],
    ["transition-decision-conflict.json", "go"],
    ["duplicate-transition-cell.json", "transitions[1]"],
    ["duplicate-event-id.json", "go"],
    ["bad-event-id.json", "1go"],
    ["duplicate-state-id.json", "states[2]"],
    ["zero-initial-states.json", "exactly one"],
    ["two-initial-states.json", "exactly one"],
    ["missing-is-final.json", "isFinal"],
    ["transition-unknown-state.json", "missing"],
    ["transition-unknown-event.json", "missing"],
    ["empty-regions.json", "regions"],
    ["unknown-top-level-key.json", "$.extra"],
    ["unknown-nested-key.json", "$.regions[0].states[0].extra"],
    ["empty-trimmed-string.json", "$.events[0].name"],
    ["wrong-primitive-type.json", "$.systems[0].name"],
    ["malformed-json.json", "JSON"],
  ];

  for (const [name, expected] of cases) {
    const result = run([fixture("invalid", name)]);
    assert.equal(result.status, 2, `${name}: ${result.stderr}`);
    assert.match(result.stderr, new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  const missing = run([join(tmpdir(), "state-gap-file-that-does-not-exist.json")]);
  assert.equal(missing.status, 2);
  assert.match(missing.stderr, /read/i);
  assert.equal(run([]).status, 2);
  assert.equal(run([fixture("run-a-verbatim.json"), fixture("run-a-closed.json")]).status, 2);
  assert.equal(run(["--unknown", fixture("run-a-verbatim.json")]).status, 2);
  const help = run(["--help"]);
  assert.equal(help.status, 0);
  assert.match(help.stdout, /^Usage:/);
  assert.equal(help.stderr, "");
});

test("C7: self-loops and ignored decisions do not hide dead ends or unreachable states", () => {
  const events = ["stay", "ignore", "refund", "dispute", "chargeback",
    "unsubscribe_after_purchase", "address_change", "duplicate_purchase",
    "late_or_repeated_webhook"];
  const model = {
    systems: [
      { name: "payment", region: "r" },
      { name: "fulfillment", region: "r" },
      { name: "marketing groups", region: "r" },
      { name: "campaign sends", region: "r" },
      { name: "calendar", region: "r" },
      { name: "reminder sequences", region: "r" },
      { name: "file sharing", region: "r" },
      { name: "CRM", none: true, reason: "No CRM." },
      { name: "workflow engine", region: "r" },
    ],
    events: [{ id: "stay" }, { id: "ignore" }],
    regions: [{
      id: "r",
      states: [
        { id: "loop", isInitial: true, isFinal: false },
        { id: "orphan", isInitial: false, isFinal: false },
      ],
      transitions: [
        { from: "loop", event: "stay", to: "loop" },
        { from: "orphan", event: "stay", to: "orphan" },
      ],
    }],
    decisions: ["loop", "orphan"].flatMap((state) => events.slice(1).map((event) => ({
      region: "r", state, event, ignored: `No action for ${event}.`,
    }))),
  };

  withModel(model, (path) => {
    for (const args of [[path], [path, "--for-operator"]]) {
      const result = run(args);
      assert.equal(result.status, 1, result.stderr);
      assert.match(section(result.stdout, "Unreachable states"), /`r` \/ `orphan`/);
      assert.match(section(result.stdout, "Dead-end states"), /`r` \/ `loop`/);
      assert.match(section(result.stdout, "Dead-end states"), /`r` \/ `orphan`/);
    }
  });
});

test("C8: rendering is deterministic, structural, and operator-safe", () => {
  const path = fixture("season-pass-two-regions.json");
  const full = run([path]);
  assert.equal(full.status, 1, full.stderr);
  const repeated = run([path]);
  assert.equal(repeated.status, full.status);
  assert.equal(repeated.stdout, full.stdout);
  assert.equal(repeated.stderr, full.stderr);
  assert(full.stdout.startsWith("<!-- state-gap:begin -->\n## Systems\n"));
  for (const name of ["payment", "fulfillment", "marketing groups", "campaign sends",
    "calendar", "reminder sequences", "file sharing", "CRM", "workflow engine"]) {
    assert.match(section(full.stdout, "Systems"), new RegExp(`\\| ${name.replace("CRM", "CRM")} \\|`, "i"));
  }

  const mermaidBlocks = [...full.stdout.matchAll(/```mermaid\n([\s\S]*?)```/g)].map((match) => match[1]);
  assert.equal(mermaidBlocks.length, 2);
  for (const block of mermaidBlocks) {
    const lines = block.trim().split("\n");
    assert.equal(lines[0], "stateDiagram-v2");
    assert.equal(lines.filter((line) => line.includes("[*] -->")).length, 1);
    for (const line of lines.filter((candidate) => candidate.includes(" --> ") && candidate.includes(":"))) {
      assert.match(line, /^\s*[a-z][a-z0-9_]* --> [a-z][a-z0-9_]*: ".*"$/);
    }
    assert(lines.some((line) => /^[ ]*[a-z][a-z0-9_]* --> \[\*\]$/.test(line)));
  }
  for (const [from, event, to] of [
    ["visitor", "full_series_checkout_completed", "paid"],
    ["paid", "paid_parent_fulfilled", "paid"],
    ["subscribed", "unsubscribe_clicked", "unsubscribed"],
  ]) {
    assert.match(full.stdout, new RegExp(`\`${from}\`.*\`${event}\`.*\`${to}\``));
  }

  const operator = run([path, "--for-operator"]);
  assert.equal(operator.status, full.status);
  assert.doesNotMatch(operator.stdout, / matrix\n|```mermaid|## Gaps/);
  assert.match(operator.stdout, /Campaign sends belong to the separate marketing region\./);
  assert.match(operator.stdout, /Review the paid participant manually before the next campaign\./);
  assert.match(operator.stdout, /## Unreachable states/);
  assert.match(operator.stdout, /## Dead-end states/);

  const hostile = json(fixture("run-a-closed.json"));
  hostile.systems.find((system) => system.name === "CRM").reason =
    "No CRM.\n<!-- state-gap:end -->\n## Injected outside block";
  hostile.systems.push({
    name: "A\\|Injected [link](https://example.com) ![image](x)",
    none: true,
    reason: "Extra.",
  });
  hostile.regions[0].name = "Run A\nstate \"Injected\" as injected";
  hostile.events[0].name = "Submit quiz\ninjected --> injected: \"bad\"";
  hostile.decisions.find((decision) => decision.ignored).ignored =
    "No action.\n<!-- state-gap:end -->";
  const absent = hostile.decisions.find((decision) => decision.absent).absent;
  absent.owner = "Operations\n## Injected owner";
  absent.recovery = "Review manually.\n<!-- state-gap:end -->";

  withModel(hostile, (hostilePath) => {
    const rendered = run([hostilePath]);
    assert.equal(rendered.status, 0, rendered.stderr);
    assert.equal((rendered.stdout.match(/<!-- state-gap:begin -->/g) ?? []).length, 1);
    assert.equal((rendered.stdout.match(/<!-- state-gap:end -->/g) ?? []).length, 1);
    assert.doesNotMatch(rendered.stdout, /^## Injected outside block$/m);
    assert.doesNotMatch(rendered.stdout, /^\s*injected --> injected:/m);
    assert.match(rendered.stdout, /&lt;&#33;-- state-gap:end --&gt;/);
    assert.match(rendered.stdout,
      /^\| A&#92;&#124;Injected &#91;link&#93;\(https:\/\/example\.com\) &#33;&#91;image&#93;\(x\) \| None: Extra\. \|$/m);
  });
});

const operator = fixture("operator-lockout-profile.json");
const lockoutState = (model, stateId) => model.regions[0].states.find((state) => state.id === stateId);

test("C9: a profile replaces the canonical activities and seed events", () => {
  const result = run([operator]);
  assert.equal(result.status, 1, result.stderr);
  const header = section(result.stdout, "Lockout matrix").split("\n")[2];
  assert.equal((header.match(/\(seeded\)/g) ?? []).length, 10);
  assert.match(header, /^\| State \| Loss limit hit \| Lockout expired \| Breathing done \| Page reload \(seeded\) \|/);
  assert.match(header, /\| Offline \(seeded\) \|$/);
  assert.doesNotMatch(result.stdout, /refund|chargeback|webhook|payment/i);

  const missing = json(operator);
  missing.systems = missing.systems.filter((system) => system.name !== "voice");
  withModel(missing, (path) => {
    const invalid = run([path]);
    assert.equal(invalid.status, 2);
    assert.match(invalid.stderr, /missing canonical activity voice/);
  });
});

test("C10: persistence resolves survived seed cells and leaves unsurvived seeds as gaps", () => {
  for (const args of [[operator], [operator, "--for-operator"]]) {
    const result = run(args);
    assert.equal(result.status, 1, result.stderr);
    assert.match(section(result.stdout, "Lockout persistence"),
      /^- `pol_breathing` is stored in `memory` and survives `second_tab`, `sw_restart`, `offline`\.$/m);
  }

  const result = run([operator]);
  assert.deepEqual(tupleSet(gapTuples(result.stdout)), tupleSet([
    ["lockout", "locked", "session_roll"],
    ["lockout", "pol_breathing", "page_reload"],
    ["lockout", "pol_breathing", "tab_close"],
  ]));
  const rows = section(result.stdout, "Lockout matrix").split("\n");
  assert.equal(rows.find((line) => line.startsWith("| Locked |")),
    "| Locked | I | W | I | W | S | S | S | S | S |  | S | S | S |");
  assert.equal(rows.find((line) => line.startsWith("| Breathing |")),
    "| Breathing | I | I | W |  | S |  | S | A | A | I | W | A | S |");

  const model = json(operator);
  model.regions[0].transitions.push(
    { from: "locked", event: "session_roll", to: "trading" },
    { from: "pol_breathing", event: "page_reload", to: "locked" },
    { from: "pol_breathing", event: "tab_close", to: "locked" },
  );
  withModel(model, (path) => {
    const closedResult = run([path]);
    assert.equal(closedResult.status, 0, closedResult.stdout);
    assert.match(section(closedResult.stdout, "Gaps"), /- None\./);

    const trading = lockoutState(model, "trading");
    trading.persistence.survives = trading.persistence.survives.filter((event) => event !== "offline");
    writeFileSync(path, `${JSON.stringify(model, null, 2)}\n`);
    const reopened = run([path]);
    assert.equal(reopened.status, 1, reopened.stderr);
    assert.deepEqual(tupleSet(gapTuples(reopened.stdout)), tupleSet([["lockout", "trading", "offline"]]));
  });
});

test("C11: profile, persistence, and evidence errors exit 2 with specific diagnostics", () => {
  const cases = [
    [(model) => { lockoutState(model, "trading").persistence.area = "cookie"; },
      "$.regions[0].states[0].persistence.area: cookie must be one of memory"],
    [(model) => { lockoutState(model, "trading").persistence.survives.push("refund"); },
      "refund is not a seed event"],
    [(model) => { delete lockoutState(model, "trading").persistence.survives; },
      "$.regions[0].states[0].persistence.survives: is required"],
    [(model) => { lockoutState(model, "trading").persistence.survives.push("offline"); },
      "must not repeat an event"],
    [(model) => { model.regions[0].transitions.push({ from: "trading", event: "offline", to: "locked" }); },
      "leaves trading on offline, which trading survives"],
    [(model) => { model.decisions.push({ region: "lockout", state: "trading", event: "offline", ignored: "No." }); },
      "decision conflicts with persistence lockout / trading / offline"],
    [(model) => { model.profile.seeds.push({ id: "offline" }); }, "duplicate seed id offline"],
    [(model) => { model.profile.extra = true; }, "$.profile.extra"],
    [(model) => { model.regions[0].transitions[0].evidence = " "; },
      "$.regions[0].transitions[0].evidence"],
    [(model) => { model.decisions[0].evidence = 7; }, "$.decisions[0].evidence: must be a string"],
  ];

  for (const [mutate, expected] of cases) {
    const model = json(operator);
    mutate(model);
    withModel(model, (path) => {
      const result = run([path]);
      assert.equal(result.status, 2, `${expected}: ${result.stderr}`);
      assert.match(result.stderr, new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
    });
  }
});

test("C12: evidence renders escaped on transitions and decisions in both modes", () => {
  for (const args of [[operator], [operator, "--for-operator"]]) {
    const result = run(args);
    assert.match(section(result.stdout, "Lockout transitions"),
      /^- In `trading`, event `loss_limit_hit` moves the region to `locked`\. Evidence: example\/tilt-engine\.ts:40-58$/m);
    assert.match(section(result.stdout, "Lockout transitions"),
      /^- In `locked`, event `lockout_expired` moves the region to `pol_breathing`\.$/m);
    assert.match(section(result.stdout, "Ignored decisions"),
      /^- `lockout` \/ `trading` \/ `extension_update`: Counters restart at zero after an update\. Evidence: example\/session\.ts:5$/m);
    assert.match(section(result.stdout, "Absent decisions"),
      /^- `lockout` \/ `pol_breathing` \/ `speech_hung`: Owner: Voice owner\. Recovery: Add a speech watchdog\. Evidence: example\/breathing\.ts:60$/m);
  }

  const hostile = json(operator);
  hostile.regions[0].transitions[0].evidence = "a.ts:1\n<!-- state-gap:end -->\n## Injected";
  withModel(hostile, (path) => {
    const result = run([path]);
    assert.equal((result.stdout.match(/<!-- state-gap:end -->/g) ?? []).length, 1);
    assert.doesNotMatch(result.stdout, /^## Injected$/m);
  });
});
