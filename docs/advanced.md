# Advanced sandbox testing

The runner enforces these contracts. Your agent must write and test project-specific adapters before enabling sandbox writes. The shipped example proves navigation only.

## Write scope and target identity

Use a named sandbox origin with an exact write-request allowlist. Verify the deployed build, payment test-mode account, auth instance, database and test-address pattern before a write. A shared database requires an explicit recorded exception and proven isolation. Unknown integrations stay unverified.

The write gate supports attestations for Stripe test payments and Clerk, Supabase or explicitly no auth. Other providers require a reviewed adapter. The absence of payment configuration grants no payment authority. Vercel protection bypass, when needed, must be sent only to the selected deployment origin.

## Dependent account journeys

A dependent step can inherit a previous step's browser state only after it passed. Separate required steps let two test accounts complete their respective prerequisites. Generate unique test addresses and passwords per run. Resolve verification links from the intended test mailbox and record ownership of created rows. An unresolved account, URL or record placeholder skips the dependent step.

## Provider events and received mail

Named hooks perform authorized sandbox actions the browser cannot, such as refunding a recorded test order, replaying a provider event or invoking a test cron endpoint. Validate hook arguments and restrict target records to the run's ownership. Browser success is one check; provider and backend state need their own observations.

A mail check reads the intended inbox and matches the recipient, subject, body and receipt timestamp after the action started. Sending successfully is not evidence of receipt. Mailbox errors are execution errors; an absent matching message is a failed mail check.

## Ownership and cleanup

Write runs maintain an atomic `created.json` ledger. Reconcile after provider hooks and after browser actions, including partial failures. Record IDs plus exact owning test addresses. Cleanup must accept only that ledger, verify each row's ownership and offer a dry-run. Refuse empty or ambiguous ownership, broad account deletion and production targets.

After cleanup, verify the intended test rows are gone and report residue or failures. Do not claim generic automatic cleanup for an arbitrary integration. Never delete unrelated data to produce a clean report.

## Release evidence

Preserve sandbox observations, browser frames, backend checks, original retries, model identity and build identity together. Run a separate read-only production configuration probe when relevant. That probe can verify configuration; it does not replace a tested production customer journey or authorize production writes.

## Adapter reference

Add `write` to `site.json` only after the intended sandbox actions are authorized:

```json
{
  "sandbox_origin": "https://sandbox.example.test",
  "auth": "supabase",
  "auth_ref": "your-test-project",
  "payment": "stripe",
  "payment_account": "acct_test_account",
  "email_format": "tester+{run}{name}@your-test-mailbox.example",
  "api_allow": [{"method": "POST", "path": "/api/checkout"}]
}
```

Each API rule needs exactly one `path` or `path_pattern`, a `method`, and optionally an exact `origin` and allowed query values. Read the actual caller chain to include auth origins and callbacks precisely. With no `payment` field, payment-provider requests are blocked even if another rule would allow them. Match the sandbox webhook origin exactly. A missing or non-boolean `database.production` is not evidence of isolation; only `false` passes without a recorded `shared_database_exception`.

The hook signatures are documented in `templates/hooks.py`. `preflight` returns auth, database, payment and webhook attestations from the actual deployment/provider; it must not simply echo the desired configuration. `created(addresses, site)` returns every currently owned row as `{kind, id, email, status?}`. Missing fields, invalid kinds and foreign addresses stop the run after preserving rows that can be recorded. Custom row kinds are supported.

Write goals live in `goals-write.json`. `after` inherits one passing journey's browser state. `requires` lists other journeys that must have passed. Account placeholders include `{email_a}`, `{password_a}`, `{verify_link_a}`, `{order_id_a}` and the corresponding IDs for other row kinds. `{last_url}` comes from `after`. Journeys execute in file order, so list prerequisites first. A hook failure or unresolved required placeholder skips the dependent journey.

`do` is a list of `{"hook": "refund", "args": {"order": "{order_id_a}"}}` actions. Each named public function in project `hooks.py` accepts `(args, site)` and must act only on authorized sandbox records. Built-in runner hooks cannot be invoked this way. `mail` is `{"to": "a", "subject": "refund", "body": ["credited"], "within": 90}`. The receipt hook returns `{subject, body, to, received}` where `received` is epoch seconds. It rejects wrong recipients, malformed timestamps and messages from before the action. `within` is 1 to 600 seconds.

The cleanup command is project-specific:

```sh
uv run --python 3.12 scripts/walk.py https://sandbox.example.test --site ops/journeys --write --expect-commit COMMIT_SHA
python3 ops/journeys/cleanup.py RUN_DIR
python3 ops/journeys/cleanup.py RUN_DIR --apply
```

The runner first dry-runs cleanup with an empty ownership ledger. Cleanup takes only a run folder, reads all row kinds, and refuses mismatched owners, missing rows that the test account owns, or addresses outside `email_format`. Applying it must expire test checkout sessions, handle late webhooks, remove owned private files/rows/auth accounts, and verify unrelated counts are unchanged. Record intentionally retained provider data. Before enabling write mode, prove four cleanup fixtures: a foreign owner, a crash after account creation, partial deletion and a late webhook. These are adapter acceptance criteria, not claims that this repository tested your integrations.

Respect recorded `rate_limits` when planning write runs. The runner does not automatically pace provider-specific rate limits. Run cleanup after every write run, including failures, and report any residue. Do not silently clean up against another target.
