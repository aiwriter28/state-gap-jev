# Set up the package with your agent

You can start by giving this repository to the coding agent you already use. The agent reads [SKILL.md](../SKILL.md), checks which tools it can run and guides you to a first useful result. You supply the workflow and business decisions; the agent handles the files and commands.

Start with the included fictional example. You can read its reports and open its maps without API keys. Live tests of a website come later, when you have chosen a Jev provider and a target to test.

## Step 1: Ask your agent to guide you

Copy the [agent prompt in the README](../README.md#1-give-the-repository-to-your-agent). Tell the agent if you want to explore the example, map your own workflow or test an implementation you have already built.

| Your starting point | What the agent should do first | What you get |
| --- | --- | --- |
| You want to understand the package | Walk through the included example | Before/after reports, a map and recorded browser results |
| You have a specification or client process | Read it and identify the participating systems and events | A workflow model, unresolved decisions and a visual |
| You have a website ready to test | Read the intended workflow and define success checks | Browser observations, screenshots and a list of untested paths |

For example, give it the existing-customer service-hours process and explain which agreement should receive the hours. It should read the project documents before asking you to repeat facts already recorded there.

## Step 2: Get a local copy

The agent can clone [the repository](https://github.com/aiwriter28/state-gap-jev) into a normal working folder:

```sh
git clone https://github.com/aiwriter28/state-gap-jev.git
cd state-gap-jev
```

If you prefer to download it yourself, choose **Code > Download ZIP** on GitHub and extract the folder. Give your agent the location of that folder.

You can use the package by asking the agent to read its `SKILL.md` directly. Global skill installation is optional. If you later want the host to discover the skill automatically, use that host's normal installer and required security review. Keep the package's scripts, documentation and examples together.

## Step 3: Check the tools needed for your first task

The agent should inspect what is available and explain any missing tool before setting it up. These requirements depend on what you want to do:

| Task | Required tools | Provider account? |
| --- | --- | --- |
| Read the reports and open the supplied visuals | A browser | No |
| Rerun the example or check your own workflow model | An agent with file/command tools and Node.js 22+ | No |
| Run a live browser journey | The above, Python 3.12+, uv and Playwright Chromium | TypeSafe or OpenRouter |

Node.js runs the workflow checker. Python runs the browser journey. uv prepares the pinned Python dependencies, and Playwright supplies the Chromium browser used for the test. Your agent should check versions and use the commands in [browser journeys](journeys.md); you do not need to assemble these commands from memory.

If the agent cannot run commands, it can help draft the workflow and explain the supplied reports. It should say which checks remain unexecuted. On a remote host, the browser runner can use headless Chromium, which runs without a visible desktop window. You can download the resulting HTML and open it on your own computer.

## Step 4: Run the example and read the result

From the repository folder, the agent runs:

```sh
node scripts/state-gap.mjs examples/add-hours/before.json
node scripts/state-gap.mjs examples/add-hours/after.json
```

The first exits `1` because the missing add-hours decision is intentional. It reports one gap, three unreachable payment states and a dead end. The second exits `0` because each of its 48 modeled combinations has a decision.

Ask the agent to explain that result in ordinary language and open `visuals/before-after.html`. A resolved model describes the decisions; browser and backend checks establish what the software does. The [example walkthrough](../examples/add-hours/README.md) shows both parts.

## Step 5: Map your own workflow

Give the agent the relevant specification or a description of the process, along with project files it can inspect. Useful details include who starts the process, which systems are involved, what a successful outcome looks like and who handles exceptions.

The agent should build the model, run the checker and show unresolved decisions. You answer business questions that the sources cannot settle. It should preserve unknown behavior as a gap rather than inventing an answer to make the report pass.

Before treating the model as ready, have it reviewed for requirements and events that may have been left out. The skill describes a fresh-context review; if your host cannot run that review, the agent should leave it visibly pending. Follow [workflow modeling](model.md) for the model contract.

## Step 6: Connect Jev when you want live browser tests

Jev is TypeSafe's AI decision model. Here it chooses from the page actions the browser runner makes available. The runner performs those actions and records whether your success checks were met. See the [tool explanation in the README](../README.md#jev-helps-choose-the-next-browser-action).

Your agent should offer two ways to connect:

- **TypeSafe directly:** use a TypeSafe account and `TYPESAFE_API_KEY`.
- **OpenRouter:** use an OpenRouter account and `OPENROUTER_API_KEY`.

Use an existing account when you have one. Otherwise, the agent can point you to [TypeSafe](https://typesafe.ai) or [OpenRouter's key settings](https://openrouter.ai/settings/keys) and guide you through the account steps that need your involvement. Choose the provider explicitly and reuse that choice on later runs.

Store the key in your environment or a local ignored secret store. An API key gives the runner access to your provider account and billable calls, so keep its value out of chat, models, goals and screenshots. The agent usually needs to check only whether the required key is present.

Follow the [provider guide](providers.md) for the small billable connection check. Then use the [journey guide](journeys.md) to run the local browser example before targeting your own site. The example only navigates to checkout. Journeys that type free-form text into forms also need a separate text-generation service, explained in the provider guide.

## Step 7: Choose the target and inspect the evidence

For your own project, start with a known preview or staging build and a read-only goal. Your agent should explain which build it will open, what it will try to do and the exact conditions that count as success. Real payment and account changes require the project-specific [sandbox setup](advanced.md).

After the run, ask it to show the results page, expand the checks and open the linked screenshots. A passed checkout-navigation test proves that route and visible offer were reached. Payment processing and account updates each need their own observations.

The agent should save a setup record with the mode, runtime versions, chosen provider/model, browser status and any next issue. It should omit secrets and reuse working setup on later requests. Host compatibility claims must follow the [verification record](verification.md); Claude Code and Codex are the initial tested hosts.
