# Choose a Jev provider

Jev is [TypeSafe's AI decision model](https://docs.typesafe.ai/introduction). Given context and a question, it returns a defined choice or other structured answer. This package uses it to choose the next browser action toward a goal. The browser runner performs the action, and separate checks determine whether the goal passed.

You have two ways to access Jev. **TypeSafe directly** uses TypeSafe's own service and your TypeSafe account. **OpenRouter** gives you access to Jev through an OpenRouter account. The choice determines where the requests go, which API key you configure and which account is billed. [OpenRouter's Jev guide](https://openrouter.ai/blog/tutorials/how-to-use-jev/) explains its Decisions API.

Use whichever account you already have, or ask your agent to guide you through the choice. You need a provider only for live calls; reading the examples and checking workflow models works without one. If both keys exist, set `JEV_PROVIDER` explicitly. The package never changes provider after an error.

## Connect your chosen account

1. Use an existing API key, or create one through [TypeSafe](https://typesafe.ai) or [OpenRouter's key settings](https://openrouter.ai/settings/keys).
2. Put the key in your local environment or an ignored secret store. Your agent should guide you without asking you to paste its value into chat.
3. Select `typesafe` or `openrouter` with `JEV_PROVIDER`, using the matching key name in the table below.
4. Ask your agent to run the small connection check and explain its result. This is a billable API request; it does not yet open a browser or test a website.

| Setting | TypeSafe directly | OpenRouter |
| --- | --- | --- |
| `JEV_PROVIDER` | `typesafe` | `openrouter` |
| Secret in your environment | `TYPESAFE_API_KEY` | `OPENROUTER_API_KEY` |
| Pinned requested model | `jev-1.13.0` | `typesafe/jev-1.13` |
| Endpoint | `https://api.typesafe.ai/v1/systemone` | `https://openrouter.ai/api/alpha/decisions` |
| Usage accounting | Verified model's input-token price | Response `usage.cost` |

These are settings for the agent and runner. You do not need to edit API code to choose between the two supported providers.

After putting your key in a local ignored secret store, check the selected connection:

```sh
JEV_PROVIDER=typesafe python3 scripts/probe-provider.py
# Or:
JEV_PROVIDER=openrouter python3 scripts/probe-provider.py
```

This sends one small synthetic request and costs a fraction of a cent at the verified prices. It does not test a browser or send any project content. The result includes the actual provider, model, decision, confidence and usage. Missing keys, an invalid answer or unknown usage fail the check.

The live connection checks on October 7, 2026 passed through both providers. Each processed 329 input tokens and reported 34 output tokens. Direct TypeSafe cost was calculated as $0.000013818 from its documented $0.042 per million input tokens, with free output. OpenRouter reported the same cost. Subsequent browser checks also passed: both providers failed to find the absent path in the broken fixture and reached the add-hours checkout in the corrected fixture. These are navigation observations, not payment or entitlement checks. See [verification](verification.md).

## When a journey needs to type into a form

Choosing a button and writing a message are different tasks. Jev returns decisions. If a goal requires typing free-form text into a form, the runner also uses a text-generation model to produce that text. The included add-hours navigation example needs no text helper.

Configure the helper separately with `TEXT_MODEL_API_KEY`, `TEXT_MODEL_BASE_URL`, and `TEXT_MODEL`. A direct TypeSafe key alone cannot supply that service. An OpenRouter key can support both services, billed separately. Your agent should check the chosen text model at its own endpoint. Never apply an OpenRouter-only fallback model to an unrelated text endpoint.

## Understand the spending threshold

The journey budget is a **Jev-only stop threshold**, not a total-run price guarantee. Text helper costs are additional. Requests already in flight can cross the threshold. Errors can leave a request's billing unknown; stop subsequent journeys rather than pretending those calls were free. Check provider billing for authoritative totals.

Contracts verified against [TypeSafe's API reference](https://docs.typesafe.ai/api), [TypeSafe's model documentation](https://docs.typesafe.ai/models), and [OpenRouter's Jev guide](https://openrouter.ai/blog/tutorials/how-to-use-jev/). OpenRouter uses its Decisions API for this integration. Ordinary chat completions are not a substitute. Recheck official contracts and prices before changing model pins.
