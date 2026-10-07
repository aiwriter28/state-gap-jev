# Let your agent guide setup

Give your agent the repository and the request in the README. It should inspect capabilities, select the mode, and run the smallest useful example before asking you to configure accounts.

| Mode | Required | First result |
| --- | --- | --- |
| Explore the example | A browser; Node.js 22+ to rerun checks | Readable before/after report and map |
| Map my workflow | Coding agent, shell/files, Node.js 22+ | Model, gaps, omission review, visual |
| Test my implementation | Above, Python 3.12+, uv, Chromium, a Jev key | Browser observations and evidence |

Clone [the repository](https://github.com/aiwriter28/state-gap-jev) or download its ZIP into a normal working directory.

```sh
git clone https://github.com/aiwriter28/state-gap-jev.git
cd state-gap-jev
```

You can use `SKILL.md` directly without installing it globally. A host that supports skills can install this directory through its normal skill installer, after its required security review. All dependencies and references belong to this package; no personal skill directory is required.

The agent should check `node --version`, then run the example. For browser mode check `uv --version`, use the pinned dependencies declared in the walker, and install the matching Playwright Chromium. Follow [journeys](journeys.md) for exact commands. Explain missing tools and perform authorized installation. Do not hide installation failures or claim compatibility without executing the example.

For live testing, use an existing provider account or guide the person to create an API key in [OpenRouter](https://openrouter.ai/settings/keys) or [TypeSafe](https://typesafe.ai). Put keys in an ignored secret store or environment, never in chat, a model, a goal, or a screenshot. Read only key availability when that is all setup needs. See [providers](providers.md).

On a remote agent without a graphical desktop, headless Chromium can run journeys. Interactive HTML can be downloaded and opened locally. If the host cannot run shell commands or a browser, map the design and state that live execution remains unavailable.

Each setup record should contain mode, runtime versions, chosen provider/model, browser status and the next actionable issue. Do not store secrets in it. Reuse working setup on later invocations.

Supported host claims must be backed by the release's [verification record](verification.md). Claude Code and Codex are the initial target hosts; other agents use these capability checks rather than an assumed compatibility badge.
