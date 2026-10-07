# The model and what its result means

A model contains `systems`, `events`, `regions`, `decisions`, and optionally `profile`. See the complete [example](../examples/add-hours/after.json).

Every region has exactly one initial state. State and event IDs use lowercase snake_case and start with a letter. All references must resolve. Each state crosses every shared event into one cell, identified as `region.state.event`.

| Mark | Meaning | Required information |
| --- | --- | --- |
| W | Wired in the model | Transition with `from`, `event`, `to` |
| I | Intentionally ignored | Decision with `ignored` reason |
| A | Intentionally absent | Decision with `absent.owner` and `absent.recovery` |
| S | State survives a seed event | `persistence.area` and `persistence.survives` |
| Blank | Unresolved | A real product decision |

Transitions and decisions may include an `evidence` string identifying a source file or specification section. Evidence may describe intended behavior. It does not automatically mean observed implementation evidence.

A decision contains `region`, `state`, `event`, and exactly one of `ignored` or `absent`. Never mark a cell ignored simply because its implementation is missing. `A` explicitly records missing behavior and its owner/recovery.

Without a profile, required activities are payment, fulfillment, marketing groups, campaign sends, calendar, reminder sequences, file sharing, CRM and workflow engine. Each must be assigned to a region or marked `none: true` with a reason. Extra unique activities are allowed. The engine injects refund, dispute, chargeback, unsubscribe_after_purchase, address_change, duplicate_purchase and late_or_repeated_webhook.

A profile replaces both lists:

```json
{"activities":["storage","voice"],"seeds":[{"id":"page_reload"},{"id":"speech_failed"}]}
```

The actual profile belongs under `profile` in a complete model. Never add the computed `seeded` property yourself. State persistence supports memory, session, local, sync and indexeddb. `survives` references seed IDs only. A survived cell may also have a self-loop; conflicting transitions or decisions are invalid.

```sh
node scripts/state-gap.mjs path/to/model.json
node scripts/state-gap.mjs path/to/model.json --json
node scripts/state-gap.mjs path/to/model.json --for-operator
```

All output modes share exit codes: 0 structurally resolved, 1 gaps/unreachable/dead-end states, 2 input/usage error, 3 unexpected internal error. The Markdown report contains matrices and Mermaid diagrams. JSON provides stable cell IDs and the same findings for visual authoring.

A structural pass proves only that the modeled cells are resolved and topology checks passed. It cannot discover unnamed systems or prove that implementations, cross-system timing, payments or recovery work. Preserve uncertainty and run the fresh-context omission review.
