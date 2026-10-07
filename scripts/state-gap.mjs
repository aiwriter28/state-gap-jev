#!/usr/bin/env node

import { readFileSync } from "node:fs";

const USAGE = "Usage: node state-gap.mjs <model.json> [--for-operator | --json]";
const ID = /^[a-z][a-z0-9_]*$/;
const CANONICAL_SYSTEMS = [
  "payment",
  "fulfillment",
  "marketing groups",
  "campaign sends",
  "calendar",
  "reminder sequences",
  "file sharing",
  "CRM",
  "workflow engine",
];
const SEEDS = [
  ["refund", "Refund"],
  ["dispute", "Dispute"],
  ["chargeback", "Chargeback"],
  ["unsubscribe_after_purchase", "Unsubscribe after purchase"],
  ["address_change", "Address change"],
  ["duplicate_purchase", "Duplicate purchase"],
  ["late_or_repeated_webhook", "Late or repeated webhook"],
];
const AREAS = ["memory", "session", "local", "sync", "indexeddb"];

class InputError extends Error {}

function fail(path, message) {
  throw new InputError(`${path}: ${message}`);
}

function object(value, path) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail(path, "must be an object");
  }
  return value;
}

function array(value, path, { nonEmpty = false } = {}) {
  if (!Array.isArray(value)) fail(path, "must be an array");
  if (nonEmpty && value.length === 0) fail(path, "must not be empty");
  return value;
}

function closed(value, allowed, path) {
  for (const key of Object.keys(value)) {
    if (!allowed.includes(key)) fail(`${path}.${key}`, "is not allowed");
  }
}

function required(value, key, path) {
  if (!Object.hasOwn(value, key)) fail(`${path}.${key}`, "is required");
  return value[key];
}

function string(value, path) {
  if (typeof value !== "string") fail(path, "must be a string");
  const result = value.trim();
  if (!result) fail(path, "must not be empty after trimming");
  return result;
}

function optionalString(value, key, path) {
  return Object.hasOwn(value, key) ? string(value[key], `${path}.${key}`) : undefined;
}

function id(value, path) {
  const result = string(value, path);
  if (!ID.test(result)) fail(path, `${result} must match ${ID}`);
  return result;
}

function boolean(value, path) {
  if (typeof value !== "boolean") fail(path, "must be a boolean");
  return value;
}

function validateProfile(raw) {
  const path = "$.profile";
  const value = object(raw, path);
  closed(value, ["activities", "seeds"], path);
  const activities = array(required(value, "activities", path), `${path}.activities`)
    .map((activity, index) => string(activity, `${path}.activities[${index}]`));
  const seen = new Set();
  const seeds = array(required(value, "seeds", path), `${path}.seeds`).map((rawSeed, index) => {
    const seedPath = `${path}.seeds[${index}]`;
    const seed = object(rawSeed, seedPath);
    closed(seed, ["id", "name"], seedPath);
    const seedId = id(required(seed, "id", seedPath), `${seedPath}.id`);
    if (seen.has(seedId)) fail(`${seedPath}.id`, `duplicate seed id ${seedId}`);
    seen.add(seedId);
    return [seedId, optionalString(seed, "name", seedPath)];
  });
  return { activities, seeds };
}

function validatePersistence(raw, path, seedIds) {
  const value = object(raw, path);
  closed(value, ["area", "survives"], path);
  const area = string(required(value, "area", path), `${path}.area`);
  if (!AREAS.includes(area)) fail(`${path}.area`, `${area} must be one of ${AREAS.join(", ")}`);
  const survives = array(required(value, "survives", path), `${path}.survives`)
    .map((rawEvent, index) => {
      const eventPath = `${path}.survives[${index}]`;
      const eventId = id(rawEvent, eventPath);
      if (!seedIds.has(eventId)) fail(eventPath, `${eventId} is not a seed event`);
      return eventId;
    });
  if (new Set(survives).size !== survives.length) fail(`${path}.survives`, "must not repeat an event");
  return { area, survives };
}

function validateEvents(rawEvents, seeds) {
  const seen = new Set();
  const events = array(rawEvents, "$.events").map((raw, index) => {
    const path = `$.events[${index}]`;
    const value = object(raw, path);
    closed(value, ["id", "name"], path);
    const eventId = id(required(value, "id", path), `${path}.id`);
    if (seen.has(eventId)) fail(`${path}.id`, `duplicate event id ${eventId}`);
    seen.add(eventId);
    return { id: eventId, name: optionalString(value, "name", path), seeded: false };
  });

  for (const [seedId, name] of seeds) {
    if (!seen.has(seedId)) events.push({ id: seedId, name, seeded: true });
  }
  return events;
}

function validateRegions(rawRegions, events, seedIds) {
  const eventIds = new Set(events.map((event) => event.id));
  const regionIds = new Set();
  const regions = array(rawRegions, "$.regions", { nonEmpty: true }).map((raw, regionIndex) => {
    const path = `$.regions[${regionIndex}]`;
    const value = object(raw, path);
    closed(value, ["id", "name", "states", "transitions"], path);
    const regionId = id(required(value, "id", path), `${path}.id`);
    if (regionIds.has(regionId)) fail(`${path}.id`, `duplicate region id ${regionId}`);
    regionIds.add(regionId);

    const stateIds = new Set();
    const states = array(required(value, "states", path), `${path}.states`, { nonEmpty: true })
      .map((rawState, stateIndex) => {
        const statePath = `${path}.states[${stateIndex}]`;
        const state = object(rawState, statePath);
        closed(state, ["id", "name", "isInitial", "isFinal", "persistence"], statePath);
        const stateId = id(required(state, "id", statePath), `${statePath}.id`);
        if (stateIds.has(stateId)) fail(`${statePath}.id`, `duplicate state id ${stateId}`);
        stateIds.add(stateId);
        return {
          id: stateId,
          name: optionalString(state, "name", statePath),
          isInitial: boolean(required(state, "isInitial", statePath), `${statePath}.isInitial`),
          isFinal: boolean(required(state, "isFinal", statePath), `${statePath}.isFinal`),
          persistence: Object.hasOwn(state, "persistence")
            ? validatePersistence(state.persistence, `${statePath}.persistence`, seedIds)
            : undefined,
        };
      });
    if (states.filter((state) => state.isInitial).length !== 1) {
      fail(`${path}.states`, "must contain exactly one isInitial state");
    }
    const survivedCells = new Set(states.flatMap((state) => (
      state.persistence?.survives.map((event) => `${state.id}\u0000${event}`) ?? []
    )));

    const cells = new Set();
    const transitions = array(required(value, "transitions", path), `${path}.transitions`)
      .map((rawTransition, transitionIndex) => {
        const transitionPath = `${path}.transitions[${transitionIndex}]`;
        const transition = object(rawTransition, transitionPath);
        closed(transition, ["from", "event", "to", "evidence"], transitionPath);
        const from = id(required(transition, "from", transitionPath), `${transitionPath}.from`);
        const event = id(required(transition, "event", transitionPath), `${transitionPath}.event`);
        const to = id(required(transition, "to", transitionPath), `${transitionPath}.to`);
        if (!stateIds.has(from)) fail(`${transitionPath}.from`, `unknown state ${from}`);
        if (!stateIds.has(to)) fail(`${transitionPath}.to`, `unknown state ${to}`);
        if (!eventIds.has(event)) fail(`${transitionPath}.event`, `unknown event ${event}`);
        const cell = `${from}\u0000${event}`;
        if (cells.has(cell)) fail(transitionPath, `duplicate transition cell ${from} / ${event}`);
        cells.add(cell);
        if (survivedCells.has(cell) && to !== from) {
          fail(transitionPath, `leaves ${from} on ${event}, which ${from} survives`);
        }
        return { from, event, to, evidence: optionalString(transition, "evidence", transitionPath) };
      });
    return {
      id: regionId,
      name: optionalString(value, "name", path),
      states,
      transitions,
      transitionCells: cells,
      survivedCells,
    };
  });
  return { regions, regionIds };
}

function validateSystems(rawSystems, regionIds, activities) {
  const seen = new Set();
  const systems = array(rawSystems, "$.systems").map((raw, index) => {
    const path = `$.systems[${index}]`;
    const value = object(raw, path);
    closed(value, ["name", "region", "none", "reason"], path);
    const name = string(required(value, "name", path), `${path}.name`);
    const normalizedName = name.toLocaleLowerCase("en-US");
    if (seen.has(normalizedName)) fail(`${path}.name`, `duplicate system name ${name}`);
    seen.add(normalizedName);

    const hasRegion = Object.hasOwn(value, "region");
    const hasNone = Object.hasOwn(value, "none");
    if (hasRegion === hasNone) fail(path, "must use exactly one of region or none");
    if (hasRegion) {
      if (Object.hasOwn(value, "reason")) fail(`${path}.reason`, "is not allowed with region");
      const region = id(value.region, `${path}.region`);
      if (!regionIds.has(region)) fail(`${path}.region`, `unknown region ${region}`);
      return { name, region };
    }
    if (value.none !== true) fail(`${path}.none`, "must be true");
    const reason = string(required(value, "reason", path), `${path}.reason`);
    return { name, none: true, reason };
  });

  for (const canonical of activities) {
    if (!seen.has(canonical.toLocaleLowerCase("en-US"))) {
      fail("$.systems", `missing canonical activity ${canonical}`);
    }
  }
  return systems;
}

function validateDecisions(rawDecisions, regions, events) {
  const eventIds = new Set(events.map((event) => event.id));
  const regionsById = new Map(regions.map((region) => [region.id, region]));
  const seen = new Set();
  return array(rawDecisions, "$.decisions").map((raw, index) => {
    const path = `$.decisions[${index}]`;
    const value = object(raw, path);
    closed(value, ["region", "state", "event", "ignored", "absent", "evidence"], path);
    const regionId = id(required(value, "region", path), `${path}.region`);
    const stateId = id(required(value, "state", path), `${path}.state`);
    const eventId = id(required(value, "event", path), `${path}.event`);
    const region = regionsById.get(regionId);
    if (!region) fail(`${path}.region`, `unknown region ${regionId}`);
    if (!region.states.some((state) => state.id === stateId)) {
      fail(`${path}.state`, `unknown state ${stateId}`);
    }
    if (!eventIds.has(eventId)) fail(`${path}.event`, `unknown event ${eventId}`);

    const hasIgnored = Object.hasOwn(value, "ignored");
    const hasAbsent = Object.hasOwn(value, "absent");
    if (hasIgnored === hasAbsent) fail(path, "must use exactly one of ignored or absent");
    const cell = `${regionId}\u0000${stateId}\u0000${eventId}`;
    if (seen.has(cell)) fail(path, `duplicate decision cell ${regionId} / ${stateId} / ${eventId}`);
    if (region.transitionCells.has(`${stateId}\u0000${eventId}`)) {
      fail(path, `decision conflicts with transition ${regionId} / ${stateId} / ${eventId}`);
    }
    if (region.survivedCells.has(`${stateId}\u0000${eventId}`)) {
      fail(path, `decision conflicts with persistence ${regionId} / ${stateId} / ${eventId}`);
    }
    seen.add(cell);

    if (hasIgnored) {
      return { region: regionId, state: stateId, event: eventId,
        ignored: string(value.ignored, `${path}.ignored`),
        evidence: optionalString(value, "evidence", path) };
    }
    const absent = object(value.absent, `${path}.absent`);
    closed(absent, ["owner", "recovery"], `${path}.absent`);
    return {
      region: regionId,
      state: stateId,
      event: eventId,
      absent: {
        owner: string(required(absent, "owner", `${path}.absent`), `${path}.absent.owner`),
        recovery: string(required(absent, "recovery", `${path}.absent`), `${path}.absent.recovery`),
      },
      evidence: optionalString(value, "evidence", path),
    };
  });
}

function validate(raw) {
  const value = object(raw, "$");
  closed(value, ["profile", "systems", "events", "regions", "decisions"], "$");
  for (const key of ["systems", "events", "regions", "decisions"]) required(value, key, "$" );
  const profile = Object.hasOwn(value, "profile")
    ? validateProfile(value.profile)
    : { activities: CANONICAL_SYSTEMS, seeds: SEEDS };
  const events = validateEvents(value.events, profile.seeds);
  const seedIds = new Set(profile.seeds.map(([seedId]) => seedId));
  const { regions, regionIds } = validateRegions(value.regions, events, seedIds);
  const systems = validateSystems(value.systems, regionIds, profile.activities);
  const decisions = validateDecisions(value.decisions, regions, events);
  return { systems, events, regions, decisions };
}

function cellResolution(wired, decision, survived) {
  if (wired) return "W";
  if (decision?.ignored) return "I";
  if (decision?.absent) return "A";
  if (survived) return "S";
  return "";
}

function resolveCells(model, region, decisions) {
  const transitions = new Set(region.transitions.map((transition) => (
    `${transition.from}\u0000${transition.event}`
  )));
  const cells = new Map();
  const gaps = [];
  for (const state of region.states) {
    for (const event of model.events) {
      const local = `${state.id}\u0000${event.id}`;
      const decision = decisions.get(`${region.id}\u0000${state.id}\u0000${event.id}`);
      const resolution = cellResolution(transitions.has(local), decision, region.survivedCells.has(local));
      cells.set(local, resolution);
      if (!resolution) gaps.push({ region: region.id, state: state.id, event: event.id });
    }
  }
  return { cells, gaps };
}

function analyzeTopology(region) {
  const initial = region.states.find((state) => state.isInitial);
  const reachable = new Set([initial.id]);
  const queue = [initial.id];
  for (let index = 0; index < queue.length; index += 1) {
    for (const transition of region.transitions) {
      if (transition.from === queue[index] && !reachable.has(transition.to)) {
        reachable.add(transition.to);
        queue.push(transition.to);
      }
    }
  }
  const unreachable = region.states
    .filter((state) => !reachable.has(state.id))
    .map((state) => ({ region: region.id, state: state.id }));
  const deadEnds = region.states
    .filter((state) => !state.isFinal && !region.transitions.some((transition) => (
      transition.from === state.id && transition.to !== state.id
    )))
    .map((state) => ({ region: region.id, state: state.id }));
  return { unreachable, deadEnds };
}

function analyze(model) {
  const decisions = new Map(model.decisions.map((decision) => [
    `${decision.region}\u0000${decision.state}\u0000${decision.event}`,
    decision,
  ]));
  const gaps = [];
  const unreachable = [];
  const deadEnds = [];
  const regionData = model.regions.map((region) => {
    const resolved = resolveCells(model, region, decisions);
    const topology = analyzeTopology(region);
    gaps.push(...resolved.gaps);
    unreachable.push(...topology.unreachable);
    deadEnds.push(...topology.deadEnds);
    return { region, cells: resolved.cells };
  });
  return { regionData, gaps, unreachable, deadEnds };
}

const markdown = (value) => value
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll("`", "&#96;")
  .replaceAll("\\", "&#92;")
  .replaceAll("|", "&#124;")
  .replaceAll("[", "&#91;")
  .replaceAll("]", "&#93;")
  .replaceAll("!", "&#33;")
  .replace(/\r\n?|\n/g, "<br>");
const mermaid = (value) => value
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replace(/\r\n?|\n/g, " ")
  .replaceAll("\\", "\\\\")
  .replaceAll('"', '\\"');
const display = (item) => item.name ?? item.id;
const evidence = (item) => (item.evidence ? ` Evidence: ${markdown(item.evidence)}` : "");

function eventDisplay(event) {
  return `${display(event)}${event.seeded ? " (seeded)" : ""}`;
}

function renderSystems(systems) {
  const lines = ["## Systems", "", "| System | Resolution |", "|---|---|"];
  for (const system of systems) {
    const resolution = system.region
      ? `Region \`${system.region}\``
      : `None: ${markdown(system.reason)}`;
    lines.push(`| ${markdown(system.name)} | ${resolution} |`);
  }
  return lines;
}

function renderMatrix(region, events, cells) {
  const lines = [
    `## ${markdown(display(region))} matrix`,
    "",
    `| State | ${events.map((event) => markdown(eventDisplay(event))).join(" | ")} |`,
    `|---|${events.map(() => "---").join("|")}|`,
  ];
  for (const state of region.states) {
    const values = events.map((event) => cells.get(`${state.id}\u0000${event.id}`));
    lines.push(`| ${markdown(display(state))} | ${values.join(" | ")} |`);
  }
  return lines;
}

function renderMermaid(region, events) {
  const eventsById = new Map(events.map((event) => [event.id, event]));
  const lines = [`## ${markdown(display(region))} Mermaid`, "", "```mermaid", "stateDiagram-v2"];
  for (const state of region.states) lines.push(`  state "${mermaid(display(state))}" as ${state.id}`);
  lines.push(`  [*] --> ${region.states.find((state) => state.isInitial).id}`);
  for (const transition of region.transitions) {
    lines.push(`  ${transition.from} --> ${transition.to}: "${mermaid(eventDisplay(eventsById.get(transition.event)))}"`);
  }
  for (const state of region.states.filter((candidate) => candidate.isFinal)) {
    lines.push(`  ${state.id} --> [*]`);
  }
  lines.push("```");
  return lines;
}

function renderTransitions(region, events) {
  const eventsById = new Map(events.map((event) => [event.id, event]));
  const lines = [`## ${markdown(display(region))} transitions`, ""];
  if (region.transitions.length === 0) return [...lines, "- None."];
  for (const transition of region.transitions) {
    const seed = eventsById.get(transition.event).seeded ? " (seeded)" : "";
    lines.push(`- In \`${transition.from}\`, event \`${transition.event}\`${seed} moves the region to \`${transition.to}\`.${evidence(transition)}`);
  }
  return lines;
}

function renderPersistence(region) {
  const persisted = region.states.filter((state) => state.persistence);
  if (persisted.length === 0) return [];
  const lines = ["", `## ${markdown(display(region))} persistence`, ""];
  for (const state of persisted) {
    const survives = state.persistence.survives.map((event) => `\`${event}\``).join(", ");
    lines.push(`- \`${state.id}\` is stored in \`${state.persistence.area}\` and survives ${survives || "no seed event"}.`);
  }
  return lines;
}

function renderTupleSection(title, values, line) {
  const lines = [`## ${title}`, ""];
  if (values.length === 0) lines.push("- None.");
  else for (const value of values) lines.push(line(value));
  return lines;
}

function render(model, analysis, forOperator) {
  const eventById = new Map(model.events.map((event) => [event.id, event]));
  const lines = ["<!-- state-gap:begin -->", ...renderSystems(model.systems)];
  for (const { region, cells } of analysis.regionData) {
    lines.push("");
    if (!forOperator) {
      lines.push(...renderMatrix(region, model.events, cells), "", ...renderMermaid(region, model.events), "");
    }
    lines.push(...renderTransitions(region, model.events), ...renderPersistence(region));
  }
  if (!forOperator) {
    lines.push("", ...renderTupleSection("Gaps", analysis.gaps, (gap) => {
      const seeded = eventById.get(gap.event).seeded ? " (seeded)" : "";
      return `- \`${gap.region}\` / \`${gap.state}\` / \`${gap.event}\`${seeded}`;
    }));
  }
  lines.push("", ...renderTupleSection("Ignored decisions",
    model.decisions.filter((decision) => decision.ignored),
    (decision) => `- \`${decision.region}\` / \`${decision.state}\` / \`${decision.event}\`: ${markdown(decision.ignored)}${evidence(decision)}`));
  lines.push("", ...renderTupleSection("Absent decisions",
    model.decisions.filter((decision) => decision.absent),
    (decision) => `- \`${decision.region}\` / \`${decision.state}\` / \`${decision.event}\`: Owner: ${markdown(decision.absent.owner)}. Recovery: ${markdown(decision.absent.recovery)}${evidence(decision)}`));
  lines.push("", ...renderTupleSection("Unreachable states", analysis.unreachable,
    (value) => `- \`${value.region}\` / \`${value.state}\``));
  lines.push("", ...renderTupleSection("Dead-end states", analysis.deadEnds,
    (value) => `- \`${value.region}\` / \`${value.state}\``));
  lines.push("<!-- state-gap:end -->");
  return `${lines.join("\n")}\n`;
}

function parseArguments(args) {
  if (args.length === 1 && args[0] === "--help") return { help: true };
  const unknown = args.find((arg) => arg.startsWith("-") && !["--for-operator", "--json"].includes(arg));
  const operatorCount = args.filter((arg) => arg === "--for-operator").length;
  const jsonCount = args.filter((arg) => arg === "--json").length;
  const positionals = args.filter((arg) => !arg.startsWith("-"));
  if (unknown || operatorCount > 1 || jsonCount > 1 || (operatorCount && jsonCount) || positionals.length !== 1) {
    throw new InputError(unknown ? `unknown flag ${unknown}` : "expected exactly one model file");
  }
  return { path: positionals[0], forOperator: operatorCount === 1, json: jsonCount === 1 };
}

function main() {
  let args;
  try {
    args = parseArguments(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    console.error(USAGE);
    return 2;
  }
  if (args.help) {
    console.log(USAGE);
    return 0;
  }

  let text;
  try {
    text = readFileSync(args.path, "utf8");
  } catch (error) {
    console.error(`Could not read ${args.path}: ${error.message}`);
    console.error(USAGE);
    return 2;
  }
  let raw;
  try {
    raw = JSON.parse(text);
  } catch (error) {
    console.error(`Invalid JSON in ${args.path}: ${error.message}`);
    return 2;
  }

  try {
    const model = validate(raw);
    const analysis = analyze(model);
    const report = {
      schemaVersion: 1,
      cells: analysis.regionData.flatMap(({ region, cells }) =>
        [...cells].map(([key, resolution]) => {
          const [state, event] = key.split("\u0000");
          return { id: `${region.id}.${state}.${event}`, region: region.id, state, event, resolution };
        })),
      gaps: analysis.gaps, unreachable: analysis.unreachable, deadEnds: analysis.deadEnds,
    };
    process.stdout.write(args.json ? `${JSON.stringify(report, null, 2)}\n` : render(model, analysis, args.forOperator));
    return analysis.gaps.length || analysis.unreachable.length || analysis.deadEnds.length ? 1 : 0;
  } catch (error) {
    if (error instanceof InputError) {
      console.error(`Invalid model ${error.message}`);
      return 2;
    }
    console.error(`Internal error: ${error.message}`);
    return 3;
  }
}

process.exitCode = main();
