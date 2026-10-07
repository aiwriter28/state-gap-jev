# Read the map, inspect the evidence

Archify renders the diagrams. State Gap supplies deterministic cells, and browser runs supply observations. The results page connects those records without claiming that drawing a path tested it.

Open the supplied HTML locally to use guided views, search, focus, route exploration, theme switching and exports. GitHub's source viewer cannot run the interactive HTML. The README images work directly on GitHub.

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
