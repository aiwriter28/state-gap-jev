# Read the map, inspect the evidence

[Archify](https://github.com/tt-a1i/archify) is the diagram tool used to create the interactive workflow maps in this repository. A map gives you a way to follow the process and discuss it with a client or teammate. The supplied HTML maps are already generated, so viewing them requires only a browser.

State Gap supplies the workflow decisions. Browser runs supply observations. The results page connects those records and shows the precise checks behind an outcome. Keep those roles in mind: a drawn connection describes the workflow, while a recorded test describes what happened in a particular run.

## Open the included example

1. Clone the repository, or choose **Code > Download ZIP** on GitHub and extract it.
2. Open `visuals/before-after.html` from the local folder in your browser. Ask your agent to open it if you are unsure where the files are.
3. Follow the existing-customer path. The before view shows the missing add-hours path; the after view shows the proposed design.
4. Open `visuals/observed-results.html` to see how the recorded browser test relates to that design.
5. Open `examples/add-hours/typesafe-after.html` or `openrouter-after.html`. Expand the passing goal to read its checks, then follow the links to its record and screenshot.

Keep the extracted folder together. Results pages use relative links to records, frames and maps, so moving one page by itself can break those links. GitHub displays HTML source instead of running it. The PNG images in the README work directly on GitHub.

## Use the map and results controls

The supplied maps include guided views, search, focus, route exploration, light/dark themes and exports. Start with the guided view to understand the main path. Select a step to inspect its details, or search for a system such as payment. Route exploration helps you follow the connections authored in the map. Export a static image when you need a picture for a client discussion, or share the HTML for interaction.

The results page has status filters and expandable goal checks. For each recorded goal, read what the check required before interpreting its status:

| Status | Meaning |
| --- | --- |
| Pass | The recorded journey met its specified checks |
| Flaky | The first attempt failed and the retry passed; both attempts remain visible |
| Fail | The journey did not meet its checks |
| Error | A browser, provider or execution problem prevented a normal result; inspect the record |
| Skip | The goal was skipped, with the recorded reason |
| Untested | No linked observation exists for that model cell |

The corrected add-hours demo passes because it reaches the expected checkout URL and sees the offer text. Payment and account updates need separate checks. A goal that is only assigned to a model cell represents planned testing until a run supplies an observation.

## Generate results for your workflow

```sh
node scripts/results.mjs path/to/model.json path/to/results.html
# Attach one completed run and a corresponding Archify map:
node scripts/results.mjs path/to/model.json path/to/results.html --run path/to/run --diagram path/to/map.html
```

Keep the model, map and run folders together when sharing. The generator requires the model SHA-256 recorded in `run.json` to match the supplied model. It reads the original `summary.json` records, escapes their text and links available evidence. Missing files are shown as unavailable. It never promotes a planned goal tag to a passing result.

The result page provides status filtering and expandable goal checks. Pass/flaky/fail/error/skip apply to recorded goals; cells without a linked observation remain untested. Several linked observations remain individually visible. Inspect retries with original attempts. A goal checking navigation cannot prove payment or entitlement even when it tags a payment cell.

## Author the workflow map

Use Archify's current schema and validation instructions. The generated HTML is self-contained; users do not need Archify installed to view the supplied outputs. Regeneration requires a separately installed, security-reviewed copy of [Archify](https://github.com/tt-a1i/archify). The supplied visuals were rendered with the local 2.17 development version recorded in [maintenance](maintenance.md); they do not promise identical bytes from another release.

The agent should:

1. Read the model, deterministic report and exact run records. Choose at most 12 primary nodes per view, with one overview and smaller views for complex regions.
2. Use stable IDs and preserve the source mapping beside the diagram. Use explicit text labels for planned, unresolved, pass, fail, error, skip and untested. Color is supplemental.
3. Keep behavioral edges faithful to the model. Do not infer a new causal link from layout, a guided story, or the order of records. Separate recorded demonstrations from fresh observations.
4. Show a passed goal's precise check and run identity in the adjacent results page. Use its evidence links. Preserve the complete model and report outside the bounded visual.
5. Validate, deliver and inspect the actual HTML in light/dark themes. Check ordinary desktop widths and follow evidence links. Save artifact hashes and the distinction between automated rendering checks and visual inspection.

A visual can summarize the design while an adjacent results table carries all 48 or 480 cells. Do not build a new universal graph layout engine. If Archify cannot be installed or rendered on the host, use the engine's Mermaid diagram plus the results page, state the limitation, and retain interactive maps as pending.
