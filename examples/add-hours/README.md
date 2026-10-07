# An existing customer needs five more hours

This fictional example connects a design gap to a visible browser symptom. Nothing here processes payments, sends mail or creates accounts.

1. Read [the specification](spec.md).
2. Run `node scripts/state-gap.mjs examples/add-hours/before.json`. Exit 1 is expected: one missing decision, three unreachable states and one dead end.
3. Run the same command with `after.json`. Exit 0 means all 48 modeled cells have an explicit design decision. It does not prove the implementation.
4. Open [the design map](../../visuals/before-after.html) and [design-only results](results.html) locally. GitHub displays HTML source rather than running the viewer.
5. Read [the recorded browser evidence](#recorded-browser-evidence), or follow [the journey guide](../../docs/journeys.md) to rerun it with your chosen Jev provider.

## Recorded browser evidence

These are real observations of the bundled synthetic pages, recorded October 7, 2026. They are not a fresh test of your application. Click through the generated result tables to see the precise checks and frames.

| Provider | Broken example | Corrected example |
| --- | --- | --- |
| TypeSafe directly | [FAIL, including retry](typesafe-before.html) | [PASS: checkout navigation](typesafe-after.html) |
| OpenRouter | [FAIL, including retry](openrouter-before.html) | [PASS: checkout navigation](openrouter-after.html) |

The same goal asks to add five service hours to the existing agreement. Its pass check requires the add-hours checkout URL and visible offer text. The broken page only offers a new contract. The corrected page exposes the add-hours checkout, and the runner stops there.

[Explore the observed-results map](../../visuals/observed-results.html). One cell has navigation evidence; 47 cells have no linked observation. Payment, entitlement updates, received mail, repeated webhooks and refunds remain untested. Recovery owners in the model are fictional design decisions.

The `evidence/` directory contains original run identities, checks, both attempts when retried, provider/model usage, summaries and screenshots. A build field explicitly labeled Git blob ID identifies the served index page. These small synthetic recordings are intentionally distributable. Keep real project runs private.

The browser demo uses loopback port 18765 and rejects POST requests. Its server serves only `site/`, not credentials or the rest of the repository.
