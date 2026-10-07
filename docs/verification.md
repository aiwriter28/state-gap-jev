# Verification record

October 7, 2026. Verification for the initial public release.

## Executed checks

| Check | Result |
| --- | --- |
| `npm test` | Exit 0, 18 tests passed |
| `uv run --python 3.12 --with pytest --with playwright==1.63.0 pytest -q tests` | Exit 0, 123 tests passed, no skips |
| Fresh dependency cache and fresh Chromium headless shell, same Python suite | Exit 0, 123 tests passed |
| Fresh release checkout, Node and Python suites | Exit 0, 18 Node and 123 Python tests passed |
| Ruff, source/tests/templates/demo and example hooks | Exit 0, both normal and isolated default configuration |
| Skill-creator manifest validator | Exit 0, skill valid |
| Markdown links, model/report equality and browser-record hashes | Passed; records match the exact current models and runner bytes |
| Both Jev API probes | Valid selected decision, probabilities, confidence and usage |
| Before/after browser fixture through both providers | Both before runs fail as intended; both after runs pass navigation |
| Archify delivery, all three diagrams | 9/9 showcase checks each, zero errors/warnings |
| Archify browser containment | Four desktop sizes per diagram passed |
| Visual review | Light/dark images inspected; share cards exported in the actual viewer and reopened |
| Results interaction | PASS filter, expanded exact check and linked final frame verified in the browser |
| Claude Code and Codex paired task evaluations | Isolated configuration and repository copies; details below |
| Trigger checks, three intended tasks and three near misses | 6/6 in the isolated sequential run; one observation per query |

The snapshot browser tests exposed an inherited scroll race. They now wait for the actual pane movement/visible target rather than sampling immediately after a wheel event. The adapter, custom profiles, planned-coverage wording, retry accounting, output preservation, webhook origin and goal-path fixes each retain regression coverage.

There is no JavaScript lint configuration. Node tests and the Fallow audit are the executed JavaScript checks. Fallow exits 1 on the reused `snapshot.js`: one unused-file false positive because Python loads the JavaScript as text, plus five existing complexity findings. Nine real browser tests exercise this snapshot. Its functional code is unchanged from the reviewed source; only private example names in comments were generalized. These are visible inherited findings, not a passing audit. No Fallow suppression, threshold change or automatic fix was used.

## Recorded provider evidence

These are the final synthetic fixture runs, including retries. No text helper was called. The total is measured Jev spend, not a promise about future costs.

| Provider and fixture | Outcome | Jev requests | Jev spend |
| --- | --- | --- | --- |
| typesafe, before | FAIL | 6 | $0.000399756 |
| typesafe, after | PASS | 1 | $0.000063924 |
| openrouter, before | FAIL | 6 | $0.000399756 |
| openrouter, after | PASS | 1 | $0.000063924 |

TypeSafe returned `jev-1.13.0`; OpenRouter returned `typesafe/jev-1.13-20260917`. Each corrected run reached checkout in one action. The broken runs preserved both failing attempts. Payment processing, exactly five credited hours, refund execution, mail receipt and idempotency remain untested by this demo.

## Host and skill evaluation

The two task cases cover credential-free onboarding (Claude Code) and interpreting a structural pass plus browser evidence (Codex). Each ran with and without the skill, against the same documentation and fixtures. Existing account authentication was reused; provider keys were removed. Claude used a fresh configuration directory with no personal skills or MCPs. Codex ignored user config, disabled hooks and host-skill discovery, used no project instruction files, and ran in read-only mode. It still emitted experimental-feature and skill-context-budget warnings. Its skill condition explicitly read this repository's SKILL.md, so this verifies explicit use, not clean ambient skill discovery. These are desktop-host checks, not a claim of testing every OS or agent.

The first Claude pair was unable to print exit codes because the test harness omitted shell permissions for `echo`. The corrected pair ran the commands with no permission denials; the initial records were retained. The original Codex event stream omitted some enclosing tool calls, including image reads. Those ephemeral runs cannot establish every process claim. A follow-up with full tool-call/result capture confirmed successful screenshot reads that were absent from the ordinary CLI summary stream. Missing entries in that summary are not proof that an action was skipped; the original capture limitation remains documented.

The initial parallel trigger test scored 4/6 while multiple identical temporary skill descriptions shared one directory. Sequential isolation removed that interference and scored 6/6. This small result is a smoke check, not a statistically reliable trigger rate or a reason to claim improved model quality.

The initial four task runs passed their four assertions. The baseline has the same README and examples, so this establishes usability, not a benefit caused by the entry skill. Review found a paraphrased summary described as exact output and an overly broad completeness phrase. The original outputs and grading remain preserved. A release revision clarified model-relative completeness, summary labeling and the requirement for recorded verification evidence.

The follow-up compares the revised and prior entry skills on the same two tasks with six assertions each. Claude Code captured its tool events directly. The first Codex pair had incomplete process capture and was retained outside the scored comparison; the corrected pair retains full tool-call/result evidence and confirms both screenshot inspections. Reports distinguish observed checks from unchecked capability and implementation claims. The standard skill-creator review viewer contains the outputs, grades, timing and limitations. This small comparison does not establish a general quality or performance gain.

All four scored follow-up outputs passed five of six assertions. The remaining failure is explicit summary labeling: agents paraphrased the reports without labeling that prose as a summary. The successful tool records support the verification claims in the corrected evidence runs. This wording limitation remains visible; the criterion was not weakened to turn it into a pass.

Each task ran once per condition, with different hosts for different tasks. Timings and token totals describe these runs only; they do not establish a general performance gain. A later evaluation should test omitted events, stale hashes, misleading success text and flaky retries rather than rely only on the supplied walkthrough.

## Security and release scope

The two-stage scanner reports the reviewed Journey Walker HIGH/CRITICAL patterns. The source reuse was explicitly approved, the exact behavior was inspected, and the integrated package was rescanned. See [security review](security.md). This is a documented exception, not a clean automated security pass.

The source repository is [aiwriter28/state-gap-jev](https://github.com/aiwriter28/state-gap-jev). Author-owned package files use [MIT](../LICENSE); the original third-party notices remain included. Review outputs and benchmark caveats are retained in the maintainer's local evaluation workspace.

No production customer workflow, real sandbox payment, mail delivery, project cleanup adapter or private installed skill was changed or verified. Existing independent audit work is untouched.

## Visual source identities

| File | SHA-256 |
| --- | --- |
| `before-after.html` | `29cc80475915204fb59d5abbd3f05bf19a1a9cc78ddcfb9a629802f65134a3fb` |
| `before-after.workflow.json` | `e81fbc703b0755517e08f5ba7291fbdc32c903a7d622103cae1565847f1a05f4` |
| `observed-results.html` | `f2bd6caed734121b505670870df83f878ab97a538bf9872ef6fe5304725f3b55` |
| `observed-results.workflow.json` | `bad4570dfe04f68ba2610ed1ff86f2e1e37b4a4b1daa79866698aae4bbb5613c` |
| `overview.html` | `f369f8924c829ca99dbe3252073e2ec0c8d3ee7d871791151fae5fc5ab8bffb3` |
| `overview.workflow.json` | `0cc316f967cdbd8e8135e4c5a76177cbd8dd40305e9f719be701fe764aa7ac39` |
