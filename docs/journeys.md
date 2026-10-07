# Test the implemented journey

Start from the customer's need before reading page wording. Write a persona goal and an independent success check. A useful goal is to add five hours to an existing agreement. A useful check requires the add-hours checkout URL and its expected offer. Any page containing hours is too weak.

## Run the example

Install the browser once:

```sh
uv run --python 3.12 --with playwright==1.63.0 playwright install chromium
```

Start the synthetic site in one terminal:

```sh
python3 examples/add-hours/demo.py
```

In another terminal, with your chosen provider's key already in the environment:

```sh
JEV_PROVIDER=typesafe uv run --python 3.12 scripts/walk.py http://127.0.0.1:18765 --site examples/add-hours/journeys/after
# Or use the OpenRouter account:
JEV_PROVIDER=openrouter uv run --python 3.12 scripts/walk.py http://127.0.0.1:18765 --site examples/add-hours/journeys/after
```

Use `journeys/before` to run the broken version. Its failed goal and exit 1 are expected. The corrected version passes the navigation check and exits 0. There is no text helper, purchase, account creation or analytics in this fixture. Its build field identifies the exact served index page by Git blob ID, rather than a deployed Git commit. The local port is fixed in both example site configurations; update their exact allowlist if you change it.

The pinned upstream dependency and Playwright version are declared in `scripts/walk.py`; uv creates their environment. Node.js is needed for model validation and the results generator. No globally installed sibling skill is required.

## Configure your own site

Copy `templates/` to a project folder such as `ops/journeys/`. Review `hooks.py` before running it: hooks are executable project code. Configure `site.json` with:

| Field | Meaning |
| --- | --- |
| `name`, `steps` | Human name and stable journey-map step IDs |
| `deployment_url_pattern` | Anchored pattern allowing only intended preview builds |
| `live_hosts` | Production links that must redirect to the build under test |
| `allow` | Explicit third-party GET origins, with optional path regex |
| `model` | Model path relative to the site folder |
| `viewports` | Named width/height pairs; phone and desktop have defaults |
| `max_actions`, `budget_usd` | Per-journey actions and whole-run Jev stop threshold |
| `avoid` | Optional controls to exclude, such as voice or paid AI tools |
| `protection_bypass` | Require `VERCEL_AUTOMATION_BYPASS_SECRET`, sent only to the target origin |

Before running, verify target identity and suppression of every analytics path, including same-origin collectors and server-side events. Third-party reads are restricted, and mutations are blocked in read mode. GET requests can still have server-side effects, so a deployment URL or query flag alone does not prove isolation.

Use `hooks.build(origin, site)` to obtain the actual deployed commit and deployment ID from the host. For release testing, require the expected commit:

```sh
uv run --python 3.12 scripts/walk.py https://your-preview.example --site ops/journeys --expect-commit COMMIT_SHA
```

An absent or different build refuses the run before browser actions. `--probe --site ops/journeys` calls an optional read-only `production_probe(site)` hook and needs no Jev key or browser.

## Goals and checks

Each goal has `id`, `step`, `start`, `goal`, and `pass`. Optional fields are `viewport`, `budget`, `avoid`, `cells`, `known`, and `note`. IDs are safe folder names. `known` records an accepted issue reference so a known failure does not fail the whole run; it remains a visible failure. `note` records the reason for changing a check. Preserve the original evidence.

```json
{
  "id": "add-hours",
  "step": "add_hours",
  "start": "/account/",
  "goal": "Add five hours to my existing agreement and open its checkout.",
  "pass": {"url": "/add-hours/checkout$", "text": ["five service hours"]},
  "cells": ["payment.ready.add_hours"]
}
```

Supported pass conditions: `text` (list of case-insensitive regexes), optional `on` (restrict text to matching URLs), `url`, `blocked`, `api` (one regex or a list), or `any` (alternative complete checks). Conditions in a check are combined. Observations accumulate across visited pages; text is visible browser text, and the walk's own typed values are removed. API checks observe status and URL, not backend truth. Use project hooks or a separate backend check when that truth matters.

Run `python3 scripts/walk.py --cells --site ops/journeys` to see candidate cells and **planned** goal tags without keys or a browser. Validate the full model separately with State Gap first. Wired transitions and explicit absent decisions are candidates; a candidate without a goal remains untested. Use `--only ID ...` to select a subset and `--out DIR` to choose a new run folder.

Prove a critical check fails against a deliberately broken implementation or wrong expected value before trusting it. Read mode retries failures once and reports a retry pass as **flaky**. Write mode never retries automatically. Review failure frames before calling an observation a product defect: bad checks, absent text configuration, provider errors and browser errors are different causes.

## Evidence

Each run saves `run.json` with input/runner hashes, target and provider, plus `summary.json` and `summary.md`. Each journey has `record.json`, `final.png` when captured, and intermediate `frames/`. Retries retain their own directory and both attempts in the summary. Records include actual returned models, usage, precise checks, actions, and unfiltered original outcomes. An error before a screenshot exists is reported honestly.

Generate the interactive evidence table:

```sh
node scripts/results.mjs path/to/model.json path/to/results.html --run path/to/run --diagram path/to/map.html
```

The model hash must match. **Pass, flaky, fail, error and skip describe observations. Untested describes the absence of an observation.** Passing navigation does not prove payment, fulfillment, received mail or idempotency. Read the [advanced contracts](advanced.md) before configuring sandbox writes.
