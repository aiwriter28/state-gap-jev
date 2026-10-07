# Security review

This package makes explicit network requests to the chosen Jev provider. Browser page text, controls and the current journey goal are sent there. A configured text helper separately receives form context. Use synthetic or authorized project data, keep API keys in your local secret store, and review the provider's data policy before sending confidential pages.

The runner loads project `hooks.py` as executable code. Hooks can read provider state or perform authorized sandbox actions, so review them before use. `cleanup.py` is also project code. The browser request policy cannot sandbox a Python hook. The generated Archify HTML includes its own viewer runtime and font; it works locally without an external renderer.

The two-stage SkillSpector/Cisco scan was run on the original components and the integrated package. It is **not a clean automated pass**. The maintainer reviewed and approved reuse of the existing source after these findings:

| Scanner finding | Reviewed behavior |
| --- | --- |
| Infinite-loop heuristic | The mailbox poll has an explicit deadline and bounded sleep |
| Credential-read heuristic | A test function name ending in `read(tmp_path)` matches the pattern; it does not read credentials |
| Inline script injection | The flagged onclick is a synthetic browser overlay regression fixture |
| Dynamic execution plus subprocess | A project hook loader, cleanup dry-run and Git identity commands; hooks require review |
| Environment access and HTTP imports | Named credential configuration and documented provider/loopback requests |
| Undeclared network usage | The current Codex validator rejects the top-level `compatibility` field expected by this scanner rule. Network access to the chosen Jev provider is declared in the skill body and setup guide. |
| Embedded runtime/font and report markers | Bundled Archify code and report formatting; source and upstream notices retained |

No security scanner rules were suppressed or code obfuscated to manufacture a pass. Repeat your own required review on the exact version you install. Scanner findings are evidence to inspect, not proof that a package is safe or unsafe on their own. The recorded exception applies to the reviewed source; a new behavior or target requires a fresh review.
