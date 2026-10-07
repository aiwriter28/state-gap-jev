# Choose a Jev provider

Use whichever account you already have. Both paths use Jev for browser decisions. If both keys exist, set `JEV_PROVIDER` explicitly. The package never changes provider after an error.

| Setting | TypeSafe directly | OpenRouter |
| --- | --- | --- |
| `JEV_PROVIDER` | `typesafe` | `openrouter` |
| Secret in your environment | `TYPESAFE_API_KEY` | `OPENROUTER_API_KEY` |
| Pinned requested model | `jev-1.13.0` | `typesafe/jev-1.13` |
| Endpoint | `https://api.typesafe.ai/v1/systemone` | `https://openrouter.ai/api/alpha/decisions` |
| Usage accounting | Verified model's input-token price | Response `usage.cost` |

After putting your key in a local ignored secret store, check the selected connection:

```sh
JEV_PROVIDER=typesafe python3 scripts/probe-provider.py
# Or:
JEV_PROVIDER=openrouter python3 scripts/probe-provider.py
```

This sends one small synthetic request and costs a fraction of a cent at the verified prices. It does not test a browser or send any project content. The result includes the actual provider, model, decision, confidence and usage. Missing keys, an invalid answer or unknown usage fail the check.

The live connection checks on October 7, 2026 passed through both providers. Each processed 329 input tokens and reported 34 output tokens. Direct TypeSafe cost was calculated as $0.000013818 from its documented $0.042 per million input tokens, with free output. OpenRouter reported the same cost. Subsequent browser checks also passed: both providers failed to find the absent path in the broken fixture and reached the add-hours checkout in the corrected fixture. These are navigation observations, not payment or entitlement checks. See [verification](verification.md).

Jev returns decisions; it does not write free-form values. A journey that types into a form also needs a text helper configured with `TEXT_MODEL_API_KEY`, `TEXT_MODEL_BASE_URL`, and `TEXT_MODEL`. A direct TypeSafe key alone cannot supply that service. An OpenRouter key can support both services, billed separately. Text model compatibility must be checked at its own endpoint. Never apply an OpenRouter-only fallback model to an unrelated text endpoint.

The journey budget is a **Jev-only stop threshold**, not a total-run price guarantee. Text helper costs are additional. Requests already in flight can cross the threshold. Errors can leave a request's billing unknown; stop subsequent journeys rather than pretending those calls were free. Check provider billing for authoritative totals.

Contracts verified against [TypeSafe's API reference](https://docs.typesafe.ai/api), [TypeSafe's model documentation](https://docs.typesafe.ai/models), and [OpenRouter's Jev guide](https://openrouter.ai/blog/tutorials/how-to-use-jev/). OpenRouter uses its Decisions API for this integration. Ordinary chat completions are not a substitute. Recheck official contracts and prices before changing model pins.
