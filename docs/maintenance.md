# Maintain one package source

This repository is the source for the portable package. Installed releases should be replaced as a complete unit through the host's skill installer, after security review. Do not patch separate installed copies or silently repoint older private workflows. Any migration of existing installations must preserve their site adapters and verify their own tests.

The initial deterministic engine was adapted from State Gap, adding JSON output without changing the matrix rules. The browser integration reuses the reviewed Journey Walker source, with a recorded approval for scanner findings. Keep source provenance, dependency pins and focused patches in the release record.

The visual source specifications and rendered HTML ship together. Rendering used Archify 2.17.0-dev.1 (MIT). Runtime code is embedded in the delivered HTML; no Archify authoring code is bundled as an installer. Preserve its MIT and embedded JetBrains Mono OFL notices. No brand icons are used.

## Verification when changing behavior

```sh
npm test
uv run --python 3.12 --with pytest pytest -q tests
```

Run the browser suite with `uv run --python 3.12 --with pytest --with playwright==1.63.0 pytest -q tests`. For provider changes, repeat the small live API contract and the controlled browser example through both providers. A credential check cannot replace that browser run.

Review scope, correctness, safety, accessibility, maintainability and test quality separately. Retain deliberately broken examples so checks prove they can fail. Rebuild example reports after model changes and ensure every visual claim matches them. Keep generated private run evidence, security reports, local graph indexes and environment files out of commits.

Use the current Anthropic skill-creator workflow for meaningful behavior evaluations with baseline comparisons and a human-readable review viewer. Test setup from clean environments for Claude Code and Codex. A fresh chat on the same configured machine alone does not prove portability.

Publication remains pending license/destination verification and the acceptance checks in [verification](verification.md). Nothing in the draft claims a released GitHub URL.
