# State Gap + Jev

Find missing steps in a client's workflow, explain them with a visual map, and test what happens when someone uses the website.

Imagine you're building a customer portal for a client who sells service hours. New customers can sign an agreement, pay and get started. Everything looks ready. Then an existing customer wants to buy five more hours under the agreement they already have.

Where do they click? Should they go through another contract? When payment succeeds, which system adds the hours? What happens if payment fails, or the same payment notification arrives twice?

This repository helps your coding agent work through those questions with you. It checks the workflow you've described, creates a map you can discuss with your client, and can run browser journeys against the implementation. You can start with the included example without creating an account or buying API credits.

![Before: an existing customer has no add-hours path. After: the design specifies checkout and coordinated updates. Implementation testing is separate.](visuals/before-after.png)

## The tools in plain English

You use this package through a coding agent such as Claude Code or Codex. A skill is a set of instructions and supporting files that your agent reads to carry out a particular job. The instructions in this repository are in [SKILL.md](SKILL.md); your agent handles the files and commands while you explain the workflow and make business decisions.

### State Gap checks the workflow you've described

State Gap is the workflow-checking part of this package. Your agent turns the specification into a model of situations and events. A situation might be an existing customer with a valid agreement. An event might be that customer requesting more hours.

The checker looks for a decision about each relevant combination. Does the request move the customer to checkout? Is it deliberately ignored, with a reason? Is the feature intentionally absent, with someone responsible for recovery? An unanswered combination remains a gap.

It also reports steps that cannot be reached and situations with no way forward. The check follows the supplied model, so your agent still needs to review the original specification for requirements the model may have missed.

### Jev helps choose the next browser action

[Jev is an AI decision model made by TypeSafe](https://docs.typesafe.ai/introduction). You give it context and a question with defined answers, and it returns a structured decision with probabilities. For example, it can choose one action from a list of available page controls.

In this package, a browser runner reads the visible page text and controls, asks Jev which action to take toward a goal, then performs that action in Chromium. The runner repeats this process and records what happened. Separate success checks decide whether the journey passed.

For our client example, the goal is to find the way to buy five more hours under an existing agreement and open the correct checkout. This can expose a page that sends every customer into a new-contract flow even though the specification says existing customers can add hours.

Your usual coding agent continues to guide you and work on the project. Jev supplies decisions inside the browser test. TypeSafe explains this relationship in its [guide to Jev and coding agents](https://docs.typesafe.ai/introduction/coding-agents).

You can access Jev through either **TypeSafe directly** or **OpenRouter**, a service through which you can access AI models using an OpenRouter account. Both options are supported here. You choose the account to use when you're ready for live testing; the example and design checks need neither.

### Archify turns the workflow into an interactive map

[Archify](https://github.com/tt-a1i/archify) creates diagrams you can open in a browser. In this package, the maps help you follow the customer path, inspect steps and understand where a decision is missing or still planned. They give you something concrete to review with a client or teammate.

The supplied maps are already generated. You can open them without installing Archify or creating an account. Your agent can use a separately installed Archify skill to make new maps for your project. The [visuals guide](docs/visuals.md) explains that process and the fallback when Archify is unavailable.

Archify provides the diagram. State Gap checks the described workflow, and the Jev browser runner collects observations from the implemented pages. The results viewer connects those observations to the model so you can see what a test checked and which paths still need testing.

## Walk through the client example

The repository includes a fictional service-hours portal, two versions of its workflow and recorded browser tests. Follow the example before setting up your own project.

### 1. Give the repository to your agent

Paste this into your coding agent:

```text
Open https://github.com/aiwriter28/state-gap-jev and read SKILL.md.
Guide me through setup, cloning the repository locally when needed.
Assume I haven't used State Gap, Jev or Archify before. Explain each tool
in plain language when we use it, and handle the setup commands for me.

Start with the included service-hours example. Run the before and after
workflow checks, show me the visual comparison and recorded browser
results, and explain what each result proves.

Then help me map one of my own workflows. When we're ready to test
the website, offer Jev through TypeSafe directly or OpenRouter.
Reuse my choice and keep API keys out of chat.
```

Your agent should check its environment and follow the [step-by-step setup guide](docs/setup.md). Claude Code and Codex are the initial tested hosts. Other coding agents need the file, command and browser capabilities described there.

### 2. See the missing customer path

The first model describes payment and later updates, but never says how an existing customer starts buying more hours. The check reports one missing decision, three payment states that cannot be reached and a dead end.

Your agent runs this from the repository folder:

```sh
node scripts/state-gap.mjs examples/add-hours/before.json
```

Exit code `1` is expected here: the example deliberately contains findings. Read the [before report](examples/add-hours/before-report.md) alongside the visual at the top of this page.

### 3. See the resolved design

The second model adds the missing path from the existing customer to checkout:

```sh
node scripts/state-gap.mjs examples/add-hours/after.json
```

It exits `0`: all 48 combinations in this model now have an explicit decision. The [after report](examples/add-hours/after-report.md) shows those decisions. This establishes that the described model has no unresolved cells; the website still needs its own tests.

You do not need to write model JSON yourself to get started. Your agent creates and updates it from the specification and decisions you provide.

### 4. Open the interactive visuals

After cloning the repository or downloading its ZIP, open these files in your browser:

| File | What to look at |
| --- | --- |
| [Before/after map](visuals/before-after.html) | The missing path and the proposed design that resolves it |
| [Observed-results map](visuals/observed-results.html) | The recorded browser outcome and the limits of the evidence |
| [Recorded TypeSafe results](examples/add-hours/typesafe-after.html) | A passing journey, its exact checks and linked screenshots |
| [Recorded OpenRouter results](examples/add-hours/openrouter-after.html) | The same corrected journey through the other provider |

GitHub shows HTML as source code. To use a map, ask your agent to open the local file, or choose **Code > Download ZIP**, extract it and open the HTML file from the extracted folder. Keep the folder together so the results page can find its linked records and screenshots. The [visuals guide](docs/visuals.md) walks through the controls and status labels.

### 5. Understand what the browser test found

Both providers were used on the included broken and corrected pages. On the broken version, the customer cannot find the required add-hours checkout. On the corrected version, the runner reaches that checkout and sees the expected offer text.

That is a navigation result. A real payment, five additional hours in the client's account, an email receipt and refund handling each need their own checks. The observed-results map shows one modeled combination with navigation evidence and 47 without a linked observation. The [example walkthrough](examples/add-hours/README.md) includes the failed runs and retries as well as the passes.

### 6. Apply the method to your client's project

Give your agent the relevant specification, pages, existing decisions and the workflow you want to examine. For example:

```text
Use State Gap + Jev to review the existing-customer add-hours workflow
in this project. Read the specification and relevant implementation.
Map what should happen from the customer's request through checkout,
payment and the account update, including failures and repeated events.
Show me unresolved decisions before making assumptions, and create a
visual I can use to discuss the workflow with the client.
```

Your agent produces the model, a readable report and a visual. You resolve business questions such as whether another agreement is required or who handles an unmatched payment. Once the design is ready, the agent can define browser goals with precise success checks and connect the results to the same model.

![The method: map the design, resolve decisions, define goals, run Jev and inspect evidence.](visuals/overview.png)

## When you're ready for live testing

Live browser tests need Python, a Chromium browser and a Jev API key. Your agent should check and set up the required tools, then help you use the provider account you prefer:

| Choice | Use it when | Account and billing |
| --- | --- | --- |
| TypeSafe directly | You want to call Jev through TypeSafe's own service | Your TypeSafe key and TypeSafe account |
| OpenRouter | You already use OpenRouter or prefer to access Jev through that service | Your OpenRouter key and OpenRouter account |

The [provider guide](docs/providers.md) explains the configuration and a small connection check. Live calls are billed by the selected provider. Journeys that type free-form text into forms also need a separately configured text model; the included navigation example does not.

Start with the local demo or a known preview/staging build. Your agent should explain the target and planned actions before running the test. Testing a real payment or account change requires the project-specific setup in the [advanced testing guide](docs/advanced.md).

## Find the guide you need

| Guide | Use it for |
| --- | --- |
| [Setup](docs/setup.md) | Getting a first result through your agent, with or without API keys |
| [Example](examples/add-hours/README.md) | Understanding the complete before/after walkthrough and recorded results |
| [Workflow modeling](docs/model.md) | How the agent describes states, events, missing decisions and recovery |
| [Providers](docs/providers.md) | Choosing TypeSafe or OpenRouter and connecting to Jev |
| [Browser journeys](docs/journeys.md) | Writing goals, running tests and inspecting the evidence |
| [Visuals and results](docs/visuals.md) | Opening maps, reading status labels and creating your own visuals |
| [Verification](docs/verification.md) | Executed tests, provider runs and known limitations |
| [Security](docs/security.md) | Executable project hooks, provider data flow and reviewed scanner findings |

The example is fictional. Keep real client recordings and credentials private. This repository shares the modeling method with the separate State Gap Mapper web application; using the repository requires no account in that application.

For package changes, read [maintenance](docs/maintenance.md). Licensed under [MIT](LICENSE), with [third-party notices](THIRD_PARTY_NOTICES.md).
