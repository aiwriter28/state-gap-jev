"""Behaviors the runner cannot express as data. Every function is optional; delete what the site
does not need. The runner loads this file from the site folder as a module.

- build(origin, site): {"commit": str, "deployment": str or None} for the deployment at origin, from
  the host's API (Vercel: GET /v13/deployments/<host>, meta.githubCommitSha). Recorded in run.json and
  checked by --expect-commit.
- production_probe(site): read-only checks of production for --probe, returned as a list of problem
  strings. For example, with the production key read from the environment: Stripe GET /v1/account and
  GET /v1/prices/<id> answer 200; the env var names `vercel env ls production` lists include every name
  Preview has. Name the variable in a problem and never its value. Never write anything.
- harmless(event): events the site produces by design, dropped from records (an anonymous 401).
- verification_link(email, origin, site): the newest verification link sent to email, pointed at
  origin. Needed only when a write goal starts from {verify_link_x}. Raise RuntimeError when none
  arrives within a reasonable wait.
- created(addresses, site): every row that exists right now for the run's addresses, as
  [{"kind": str, "id": str, "email": str, "status": str | None}]. The kind is a lowercase name
  (user, order, lead, booking; anything matching ^[a-z][a-z0-9_]*$ except account), and the runner
  writes each row to created.json under "<kind>s" for cleanup.py and fills {<kind>_id_<letter>} from
  it. The email must be one of addresses; any other row stops the run. Needed for write mode.
- preflight(origin, site): the sandbox attestation the write gate checks against site.json:
  {"auth": {"kind": "supabase", "ref": ...} or {"kind": "clerk", "key": "pk_test_..."},
   "database": {"production": bool},
   "payment": {"provider": "stripe", "account": "acct_...", "livemode": False},
   "webhook": "<the sandbox origin the provider's webhook calls>"}
  A site with no checkout leaves payment out of site.json write, and then attests no payment and no
  webhook. A site with no sign-in sets write.auth to "none" and attests {"kind": "none"}, so an
  inquiry form's preflight is {"auth": {"kind": "none"}, "database": {"production": False}}.
"""


def harmless(event):
    return False
