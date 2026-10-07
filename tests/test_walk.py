import json
import os
import re
import shutil
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest
from walk import (
    SCROLL_LABEL,
    SEEDS,
    NotTestMode,
    attested,
    awaited,
    built,
    bypass_headers,
    checkout_guard,
    dedupe,
    fill,
    gate,
    handling,
    held,
    incomplete,
    load_hooks,
    load_model,
    load_site,
    loop_recovery,
    looping,
    mailed,
    merge_retry,
    more_below,
    new_stamp,
    offered,
    passed,
    patient,
    record_created,
    recover,
    report,
    retrying,
    run_token,
    run_write,
    settled,
    stale,
    stripe_test_mode,
    tolerant,
    unclickable,
    validate,
    write_atomic,
)

FIXTURE = Path(__file__).parent / "fixture"
SITE = load_site(FIXTURE)
HOOKS = load_hooks(FIXTURE)
ORIGIN = "https://example-abc123-team.vercel.app"
SANDBOX = SITE["write"]["sandbox_origin"]
CLERK = "https://clerk.example.com"


def test_a_rate_limited_text_helper_backs_off_and_alternates_models():
    calls, pauses = [], []

    def field_text(context):
        calls.append(os.environ["TEXT_MODEL"])
        if len(calls) < 3:
            raise RuntimeError("Model provider returned HTTP 429; no action executed.")
        return "2027-28", {}

    assert patient(field_text, ["a", "b"], pauses.append)({}) == ("2027-28", {})
    assert calls == ["a", "b", "a"] and pauses == [1, 2]

    def broken(context):
        raise RuntimeError("Model provider returned HTTP 400; no action executed.")

    with pytest.raises(RuntimeError, match="400"):
        patient(broken, ["a", "b"], pauses.append)({})

    empty = []

    def once_empty(context):
        empty.append(os.environ["TEXT_MODEL"])
        if len(empty) == 1:
            raise ValueError("Text helper returned no valid field value; nothing typed.")
        return "2027-28", {}

    assert patient(once_empty, ["a", "b"], pauses.append)({}) == ("2027-28", {}) and empty == ["a", "b"]


def test_a_walk_that_passes_only_on_retry_is_flaky_and_one_that_fails_twice_stays_failed():
    first = {"id": "a", "result": "fail", "reason": "loop"}
    assert merge_retry(first, {"id": "a", "result": "pass", "reason": "pass"}) == {
        "id": "a", "result": "flaky", "reason": "passed on retry after loop"}
    assert merge_retry(first, {"id": "a", "result": "fail", "reason": "done"}) == {
        "id": "a", "result": "fail", "reason": "loop; retry: done"}


def strict(answer, ids):  # upstream's rule, reduced: a known choice that is the most probable
    probabilities = answer["probabilities"]
    if answer["choice"] not in ids or probabilities[answer["choice"]] < max(probabilities.values()):
        raise ValueError("Invalid TypeSafe response; no action executed.")
    return answer


def test_a_near_tie_choice_is_accepted_but_not_a_clear_loser_or_unknown_option():
    check = tolerant(strict)
    ids = {"CLICK": "", "SCROLL_DOWN": ""}
    assert check({"choice": "SCROLL_DOWN", "probabilities": {"CLICK": 0.51, "SCROLL_DOWN": 0.49}}, ids)
    with pytest.raises(ValueError):
        check({"choice": "SCROLL_DOWN", "probabilities": {"CLICK": 0.7, "SCROLL_DOWN": 0.3}}, ids)
    with pytest.raises(ValueError):
        check({"choice": "BACK", "probabilities": {"CLICK": 0.5, "SCROLL_DOWN": 0.5}}, ids)


# site.json, one test per field, against the fixture


def test_site_json_fills_defaults_and_names_what_is_missing(tmp_path):
    assert SITE["max_actions"] == 40 and SITE["viewports"]["phone"] == [390, 844]
    (tmp_path / "site.json").write_text(json.dumps({"name": "x", "live_hosts": []}))
    with pytest.raises(ValueError, match="deployment_url_pattern, steps"):
        load_site(tmp_path)


def test_live_hosts_reads_go_back_to_the_build_under_test_and_writes_never_go_out():
    assert handling(SITE, "GET", "https://example.com/privacy/", ORIGIN, True) == "rewrite"
    assert handling(SITE, "GET", "https://www.example.com/terms/", ORIGIN, True) == "rewrite"
    assert handling(SITE, "POST", "https://example.com/api/intake/", ORIGIN, False) == "block"


def test_deployment_url_pattern_admits_deployments_and_the_sandbox_only():
    pattern = SITE["deployment_url_pattern"]
    assert re.search(pattern, ORIGIN) and re.search(pattern, SANDBOX)
    for live in ["https://example.com", "https://www.example.com", "https://example-abc123-team.vercel.app.evil.test"]:
        assert not re.search(pattern, live)


def test_protection_bypass_sends_the_vercel_header_to_the_deployment_only():
    base = {"accept": "text/html"}
    assert bypass_headers(ORIGIN + "/start", ORIGIN, base, "s3cret") == {**base, "x-vercel-protection-bypass": "s3cret"}
    assert bypass_headers(ORIGIN, ORIGIN, base, "s3cret")["x-vercel-protection-bypass"] == "s3cret"
    assert bypass_headers(CLERK + "/v1/environment", ORIGIN, base, "s3cret") == base
    assert bypass_headers("https://fonts.gstatic.com/s/x.woff2", ORIGIN, base, "s3cret") == base
    assert bypass_headers(ORIGIN + ".evil.test/", ORIGIN, base, "s3cret") == base
    assert bypass_headers(ORIGIN + "/start", ORIGIN, base, "") == base


def test_allow_lets_the_named_third_party_gets_through_and_stubs_or_blocks_the_rest():
    assert handling(SITE, "GET", ORIGIN + "/houston/", ORIGIN, False) == "allow"
    assert handling(SITE, "GET", ORIGIN + "/api/intake/?action=status", ORIGIN, False) == "allow"
    assert handling(SITE, "GET", "https://fonts.gstatic.com/s/x.woff2", ORIGIN, False) == "allow"
    # A path rule: Clerk's script and client state load; nothing else on that host does.
    assert handling(SITE, "GET", CLERK + "/npm/@clerk/clerk-js@5/dist/clerk.browser.js", ORIGIN, False) == "allow"
    assert handling(SITE, "GET", CLERK + "/v1/environment?_clerk_js_version=5", ORIGIN, False) == "allow"
    assert handling(SITE, "GET", CLERK + "/other/thing", ORIGIN, False) == "stub"
    assert handling(SITE, "POST", CLERK + "/v1/client/sessions", ORIGIN, False) == "block"
    # Third-party scripts and beacons get an empty success, so blocking them cannot throw in site code.
    assert handling(SITE, "GET", "https://www.googletagmanager.com/gtag/js", ORIGIN, False) == "stub"
    assert handling(SITE, "GET", "https://www.clarity.ms/tag/abc123", ORIGIN, False) == "stub"
    assert handling(SITE, "POST", "https://us.i.posthog.com/e/?ip=1", ORIGIN, False) == "block"
    assert handling(SITE, "POST", ORIGIN + "/api/newsletter", ORIGIN, False) == "block"
    # Navigating off the site is blocked, not stubbed, so a walk cannot end up on Stripe or a lookalike host.
    assert handling(SITE, "GET", "https://checkout.stripe.com/c/pay/cs_1", ORIGIN, True) == "block"
    assert handling(SITE, "GET", "https://example-abc123-team.vercel.app.evil.test/", ORIGIN, True) == "block"


def test_steps_come_from_site_json_and_the_summary_shows_the_steps_no_journey_walks():
    row = {"viewport": "phone", "result": "pass", "reason": "pass", "actions": 3, "seconds": 1.0,
           "jev_usd": 0.001, "known": None, "events": []}
    text = report([{**row, "id": "a", "step": "discover"}, {**row, "id": "b", "step": "discover"},
                   {**row, "id": "c", "step": "help"}], SITE["steps"])
    assert "| a | discover | phone | pass |" in text
    assert "Steps walked: discover 2, help 1" in text
    assert "Steps no journey walks: signin, pay" in text
    assert "Jev spend: 0.00300000 USD" in text


def test_avoid_keeps_the_site_wide_and_the_journey_controls_out_of_jevs_choices():
    actions = [{"kind": "click", "label": "Open the AI guide"}, {"kind": "fill", "label": "Send"},
               {"kind": "click", "label": "2. Your child. Needs answer"}, {"kind": "click", "label": "Continue"}]
    assert [a["label"] for a in offered(actions, [], "https://x/", SITE["avoid"])] == [
        "2. Your child. Needs answer", "Continue"]
    assert [a["label"] for a in offered(actions, [], "https://x/", SITE["avoid"] + r"|^\d\. ")] == ["Continue"]
    assert len(offered(actions, [], "https://x/")) == 4  # a site with no avoid hides nothing


def test_viewports_and_max_actions_are_validated_against_the_goals():
    assert validate([{"id": "a", "step": "help", "viewport": "tablet", "start": "/", "goal": "x", "pass": {"url": "/"}}],
                    SITE) == ["goal a: unknown viewport tablet"]
    assert validate([{"id": "a", "step": "help", "budget": "60", "start": "/", "goal": "x", "pass": {"url": "/"}}],
                    SITE) == ["goal a: budget must be an integer"]


def test_budget_usd_is_read_with_the_cap_semantics_the_runner_uses():
    assert SITE["budget_usd"] == 0.5
    assert load_site.__doc__ and "defaults" in load_site.__doc__
    assert {**SITE, "budget_usd": None}["budget_usd"] is None  # the field is data, the cap is in main()


def test_write_rules_let_through_the_payment_hosts_and_the_exact_api_requests_only():
    api = SANDBOX + "/api/intake/?action="
    assert handling(SITE, "POST", api + "checkout", SANDBOX, False, write=True) == "allow"
    assert handling(SITE, "POST", api + "signup", SANDBOX, False, write=True) == "allow"
    assert handling(SITE, "GET", "https://checkout.stripe.com/c/pay/cs_test_1", SANDBOX, True, write=True) == "allow"
    assert handling(SITE, "POST", "https://api.stripe.com/v1/payment_pages/cs_test_1/confirm", SANDBOX, False, write=True) == "allow"
    # Other actions, a second action parameter, other paths, other hosts and lookalikes stay blocked.
    for url in [api + "helper-turn", api + "checkout&action=x", SANDBOX + "/api/intake", SANDBOX + "/api/newsletter",
                "https://evilstripe.com/x", "https://example.com/api/intake/?action=checkout",
                ORIGIN + "/api/intake/?action=checkout"]:
        assert handling(SITE, "POST", url, SANDBOX, False, write=True) == "block", url
    assert handling(SITE, "PUT", api + "checkout", SANDBOX, False, write=True) == "block"
    assert handling(SITE, "GET", "https://stripe.com.evil.test/", SANDBOX, True, write=True) == "block"
    assert handling(SITE, "GET", "http://js.stripe.com/v3/", SANDBOX, False, write=True) == "stub"
    # Without --write nothing changes: no writes, no Stripe.
    assert handling(SITE, "POST", api + "checkout", SANDBOX, False) == "block"
    assert handling(SITE, "GET", "https://checkout.stripe.com/c/pay/cs_test_1", SANDBOX, True) == "block"


def test_an_api_allow_entry_can_name_another_origin_and_a_path_pattern():
    site = {**SITE, "write": {**SITE["write"], "api_allow": [
        {"method": "POST", "origin": CLERK, "path_pattern": "^/v1/client/"},
        {"method": "POST", "path_pattern": "^/api/sessions/[0-9a-f-]+/answers$"}]}}
    # An entry with an origin lets that third party be written to, and no other.
    assert handling(site, "POST", CLERK + "/v1/client/sign_ins", SANDBOX, False, write=True) == "allow"
    assert handling(site, "POST", "https://other.example.com/v1/client/sign_ins", SANDBOX, False, write=True) == "block"
    # An entry with no origin still means the sandbox origin, and the pattern matches the session
    # route without matching a sibling of it.
    assert handling(site, "POST", SANDBOX + "/api/sessions/0a1b-2c3d/answers", SANDBOX, False, write=True) == "allow"
    assert handling(site, "POST", SANDBOX + "/api/sessions/0a1b-2c3d/finish", SANDBOX, False, write=True) == "block"
    assert handling(site, "POST", CLERK + "/api/sessions/0a1b-2c3d/answers", SANDBOX, False, write=True) == "block"


def test_a_write_walk_waits_for_the_site_api_and_for_every_origin_api_allow_names():
    # the example app's first write run (2026-09-20): the anonymous sign-in returned, then Clerk activated the
    # session on its own origin while the walker, waiting only on the site's /api/, looked at the
    # placeholder screen and gave up. A person waits for the auth provider too.
    site = {**SITE, "write": {**SITE["write"], "api_allow": [
        {"method": "POST", "origin": CLERK, "path_pattern": "^/v1/"},
        {"method": "POST", "path": "/api/auth/anonymous"}]}}
    assert awaited(site, SANDBOX + "/api/auth/anonymous", SANDBOX)
    assert awaited(site, CLERK + "/v1/client/sign_ins", SANDBOX)
    assert awaited(site, CLERK + "/v1/environment?_clerk_js_version=5", SANDBOX)
    assert not awaited(site, SANDBOX + "/_next/static/chunks/main.js", SANDBOX)
    assert not awaited(site, "https://fonts.gstatic.com/s/inter.woff2", SANDBOX)
    assert not awaited(site, "https://other.example.com/v1/client/sign_ins", SANDBOX)


def test_an_api_allow_entry_names_exactly_one_path_rule_and_a_pattern_that_compiles():
    def check(rule):
        return validate([], {**SITE, "write": {**SITE["write"], "api_allow": [rule]}})

    both = "site.json write api_allow[0]: needs exactly one of path and path_pattern"
    assert check({"method": "POST", "path": "/api/x", "path_pattern": "^/api/x$"}) == [both]
    assert check({"method": "POST"}) == [both]
    assert check({"method": "POST", "path_pattern": "^/api/("}) == [
        "site.json write api_allow[0]: '^/api/(' is not a regex"]
    assert check({"method": "POST", "path_pattern": "^/api/x$"}) == []


def test_email_format_makes_a_walker_address_from_the_run_token_and_the_account_letter():
    stamp = "20260919T110512Z-3f9a"
    assert run_token(stamp) == "0919t1105123f9a"
    assert SITE["write"]["email_format"].format(run=run_token(stamp), name="a") == "tester+jev0919t1105123f9aa@example.com"


# the goals check


def test_the_fixture_goals_validate_and_each_rule_names_its_goal():
    assert validate(json.loads((FIXTURE / "goals.json").read_text()), SITE) == []
    assert validate(json.loads((FIXTURE / "goals-write.json").read_text()), SITE) == []
    good = {"id": "a", "step": "help", "start": "/", "goal": "x"}
    assert validate([{**good, "pass": {}}], SITE) == [
        "goal a: the pass check declares no condition (text, url, blocked, api or any)"]
    assert validate([{**good, "pass": {"on": "/x"}}], SITE) == [
        "goal a: the pass check declares no condition (text, url, blocked, api or any)"]
    assert validate([{**good, "pass": {"any": []}}], SITE) == ["goal a: any is empty"]
    assert validate([{**good, "pass": {"any": [{"text": ["x"]}, {}]}}], SITE) == [
        "goal a any[1]: the pass check declares no condition (text, url, blocked, api or any)"]
    assert validate([{**good, "pass": {"text": ["("]}}], SITE) == ["goal a: '(' is not a regex"]
    assert validate([{**good, "pass": {"url": "/"}, "step": "nowhere"}], SITE) == [
        "goal a: step nowhere is not in site.json steps"]
    assert validate([{**good, "pass": {"url": "/"}}, {**good, "pass": {"url": "/"}}], SITE) == ["duplicate id a"]
    assert validate([{**good, "pass": {"url": "/"}, "after": "b"}], SITE) == ["goal a: after names no journey (b)"]
    assert validate([{**good, "pass": {"url": "/"}, "known": True}], SITE) == [
        "goal a: known must be a string naming the decision"]
    assert validate([{**good, "pass": {"url": "/", "later": 1}}], SITE) == ["goal a: unknown pass key later"]


# the write gate, in the spec's order


def hooks_with(**overrides):
    attestation = HOOKS.preflight(SANDBOX, SITE)
    for key, value in overrides.items():
        section, field = key.split("__")
        attestation[section] = {**attestation[section], field: value} if isinstance(attestation[section], dict) else value
    return types.SimpleNamespace(preflight=lambda origin, site: attestation, created=HOOKS.created)


def test_the_gate_refuses_a_site_without_write_mode_and_any_origin_but_the_sandbox():
    assert gate({**SITE, "write": None}, SANDBOX, FIXTURE, HOOKS) == ["site.json has no write section"]
    for origin in [ORIGIN, "https://example.com", "http://example-sandbox.vercel.app",
                   "https://example-sandbox.vercel.app.evil.test", ""]:
        assert gate(SITE, origin, FIXTURE, HOOKS) == [f"--write walks only {SANDBOX}"], origin


def test_the_gate_refuses_an_unsupported_payment_provider_and_missing_hooks():
    site = {**SITE, "write": {**SITE["write"], "payment": "paypal"}}
    assert gate(site, SANDBOX, FIXTURE, HOOKS) == ["payment provider paypal is not supported (stripe only)"]
    assert gate(SITE, SANDBOX, FIXTURE, None) == ["hooks.py must define preflight and created for write mode"]
    assert gate(SITE, SANDBOX, FIXTURE, types.SimpleNamespace(preflight=HOOKS.preflight)) == [
        "hooks.py must define preflight and created for write mode"]


def test_the_gate_refuses_a_failing_preflight_for_each_attested_fact():
    assert attested(SITE, HOOKS.preflight(SANDBOX, SITE)) == []
    assert gate(SITE, SANDBOX, FIXTURE, hooks_with(payment__livemode=True)) == ["payment livemode is not false"]
    assert gate(SITE, SANDBOX, FIXTURE, hooks_with(payment__account="acct_live")) == [
        "payment account acct_live is not acct_test"]
    assert gate(SITE, SANDBOX, FIXTURE, hooks_with(payment__provider="paypal")) == [
        "payment provider paypal is not stripe"]
    assert gate(SITE, SANDBOX, FIXTURE, hooks_with(webhook__="https://example.com/api/stripe")) == [
        "webhook destination https://example.com/api/stripe is not the sandbox"]
    assert gate(SITE, SANDBOX, FIXTURE, hooks_with(auth__ref="other")) == ["Supabase auth ref other is not abcdefgh"]
    assert gate(SITE, SANDBOX, FIXTURE, hooks_with(auth__kind="okta")) == ["unknown auth kind okta"]
    clerk = hooks_with(auth__kind="clerk", auth__key="pk_live_abc")
    assert "Clerk is not the development instance (no pk_test_ key)" in gate(SITE, SANDBOX, FIXTURE, clerk)
    # A deployment that writes to the production database needs a recorded exception.
    site = {**SITE, "write": {k: v for k, v in SITE["write"].items() if k != "shared_database_exception"}}
    assert gate(site, SANDBOX, FIXTURE, HOOKS) == [
        "the deployment writes to the production database and site.json records no exception"]
    assert gate(site, SANDBOX, FIXTURE, hooks_with(database__production=False)) == []


def test_the_gate_refuses_a_missing_or_failing_cleanup_and_passes_the_fixture(tmp_path):
    for name in ["site.json", "hooks.py", "goals.json"]:
        shutil.copy(FIXTURE / name, tmp_path / name)
    assert gate(SITE, SANDBOX, tmp_path, HOOKS) == ["cleanup.py is missing"]
    (tmp_path / "cleanup.py").write_text("import sys; sys.exit('Refused: not logged in')")
    assert gate(SITE, SANDBOX, tmp_path, HOOKS) == [
        "cleanup.py dry run on an empty record failed: Refused: not logged in"]
    assert gate(SITE, SANDBOX, FIXTURE, HOOKS) == []


def test_a_walked_write_journey_counts_against_the_dollar_cap(tmp_path):
    (tmp_path / "hooks.py").write_text("def created(addresses, site):\n    return []\n")
    journeys = [{"id": "a", "step": "pay", "start": "/intake/", "goal": "x", "pass": {"url": "/"}},
                {"id": "b", "step": "pay", "start": "/intake/", "goal": "x", "pass": {"url": "/"}}]
    done = []

    class Pool:  # every journey costs 2 USD, and no browser runs
        def submit(self, fn, site, site_dir, origin, journey, out_dir, write):
            return types.SimpleNamespace(result=lambda: {"id": journey["id"], "result": "pass", "reason": "pass",
                                                         "jev_usd": 2.0, "final_url": ""})

    records = run_write(Pool(), {**SITE, "budget_usd": 1.0}, str(tmp_path), SANDBOX, journeys,
                        str(tmp_path / "out"), "20260920T000000Z-ab12",
                        lambda: sum(r["jev_usd"] for r in done), done)
    assert [(r["id"], r["result"]) for r in records] == [("a", "pass"), ("b", "skip")]
    assert records[1]["reason"] == "Jev spend is unknown or the stop threshold was reached"
    assert [r["id"] for r in done] == ["a"]


def test_requires_gates_a_journey_on_other_walks_passing_without_taking_their_browser(tmp_path):
    # the example app write-3 (2026-09-20): reveal-a must start from partner A's cookies (after invite-b) but only
    # once partner B's own walk assess-b has passed. after does both jobs at once, so requires does the second.
    (tmp_path / "hooks.py").write_text("def created(addresses, site):\n    return []\n")
    good = {"step": "pay", "start": "/", "goal": "x", "pass": {"url": "/"}}
    assert validate([{**good, "id": "a", "requires": ["zz"]}], SITE) == ["goal a: requires names no journey (zz)"]
    assert validate([{**good, "id": "a", "requires": "a"}], SITE) == ["goal a: requires must be a list of journey ids"]
    journeys = [{**good, "id": "a"}, {**good, "id": "b"}, {**good, "id": "c", "after": "a", "requires": ["b"]}]
    outcome = {"a": "pass", "b": "fail"}

    class Pool:
        def submit(self, fn, site, site_dir, origin, journey, out_dir, write):
            return types.SimpleNamespace(result=lambda: {"id": journey["id"], "result": outcome.get(journey["id"], "pass"),
                                                         "reason": outcome.get(journey["id"], "pass"), "jev_usd": 0.0,
                                                         "final_url": origin + "/" + journey["id"]})

    records = run_write(Pool(), SITE, str(tmp_path), SANDBOX, journeys, str(tmp_path / "out"),
                        "20260920T000000Z-ab12", lambda: 0.0, [])
    assert [(r["id"], r["result"]) for r in records] == [("a", "pass"), ("b", "fail"), ("c", "skip")]
    assert records[2]["reason"] == "requires b, which did not pass"
    outcome["b"] = "pass"
    records = run_write(Pool(), SITE, str(tmp_path), SANDBOX, journeys, str(tmp_path / "out"),
                        "20260920T000000Z-ab12", lambda: 0.0, [])
    assert [(r["id"], r["result"]) for r in records] == [("a", "pass"), ("b", "pass"), ("c", "pass")]


def test_a_wait_holds_until_the_page_changes_and_gives_up_after_the_ceiling():
    # the example app write-3 (2026-09-20): Jev chose WAIT on "Preparing your secure session", upstream slept
    # a tenth of a second, and the walk ended before Clerk's five-second activation. A person waits.
    texts = iter(["loading", "loading", "loading", "ready"])
    clock = {"t": 0.0}

    def sleep(seconds):
        clock["t"] += seconds

    assert held(lambda: next(texts), sleep, lambda: clock["t"], seconds=10) is True
    assert clock["t"] == 0.75
    clock["t"] = 0.0
    assert held(lambda: "stuck", sleep, lambda: clock["t"], seconds=10) is False
    assert clock["t"] >= 10


def test_a_scroll_reveal_page_is_read_only_once_it_stops_revealing():
    # the example site run 20260921T094206Z-ad63: Webflow's IX2 fades each section in as a scroll brings it into
    # view, and snapshot.js counts an element at opacity 0 as invisible, so the snapshot taken right
    # after the scroll read the page as empty. Five journeys looped and three went unstable on it.
    clock = {"t": 0.0}

    def sleep(seconds):
        clock["t"] += seconds

    revealing = iter([4, 40, 96, 120, 120, 120])
    assert settled(lambda: next(revealing), sleep, lambda: clock["t"]) == 120
    assert clock["t"] == 1.25
    # The reveal pauses before it starts, so two equal readings are not yet the page holding still.
    # These are the real counts from /ask-ms-ivey: stopping at the first repeat returns the empty page.
    clock["t"] = 0.0
    paused = iter([290, 290, 305, 305, 307, 307, 307])
    assert settled(lambda: next(paused), sleep, lambda: clock["t"]) == 307
    # A page that is already holding still costs half a second, not the whole window.
    clock["t"] = 0.0
    steady = iter([73, 73, 73])
    assert settled(lambda: next(steady), sleep, lambda: clock["t"]) == 73
    assert clock["t"] == 0.5
    # A page that never stops moving gives up at the deadline and reports what it last saw.
    clock["t"] = 0.0
    forever = iter(range(100))
    assert settled(lambda: next(forever), sleep, lambda: clock["t"], seconds=1.0) == 3


def test_a_control_that_cannot_be_pressed_is_set_aside_rather_than_chosen_for_ever():
    # the example site run 20260921T113138Z-ba67: the consent banner covers the mobile menu's Contact Us button and
    # upstream hit-tests before every input, so drop-in-price chose it twenty-six times, executed
    # nothing and ended unstable after five actions. Jev cannot see a covering; the runner has to.
    actions = [{"id": "e10", "label": "Contact Us"}, {"id": "e11", "label": "Privacy Policy"}]
    same = [{"choice": "e10", "fingerprint": "2faba7d8"}] * 4
    label, note = unclickable(same, actions, bans=0)
    assert label == "Contact Us" and "covering it" in note and "dismiss that first" in note
    assert unclickable(same, actions, bans=3) is None, "three is the ceiling, as for a looping control"
    # A choice that keeps changing, or a page that keeps moving, is not this.
    assert unclickable([{"choice": c, "fingerprint": "2faba7d8"} for c in "abcd"], actions, bans=0) is None
    assert unclickable([{"choice": "e10", "fingerprint": f} for f in "abcd"], actions, bans=0) is None
    assert unclickable(same[:3], actions, bans=0) is None, "three in a row is not yet a refusal"
    # The scroll is never set aside: a walk that cannot scroll cannot read the rest of a page.
    scroll = [{"choice": "scroll_down", "fingerprint": "x"}] * 4
    assert unclickable(scroll, [{"id": "scroll_down", "label": SCROLL_LABEL}], bans=0) is None


def test_a_blocked_navigation_leaves_an_error_page_the_walk_presses_back_from():
    # the example site run 20260921T111911Z-480c: gift-a-session pressed Give the Series as a Gift, the navigation
    # to the payment host was blocked as designed, and the walk spent its remaining budget on Chrome's
    # error page. The blocked request is already recorded, so the page is the only thing to undo.
    class Page:
        def __init__(self, url):
            self.url, self.back = url, 0

        def go_back(self, wait_until=None):
            self.back += 1
            self.url = "https://example.com/ask-ms-ivey"

    dead = Page("chrome-error://chromewebdata/")
    assert recover(dead) is True and dead.back == 1
    assert dead.url == "https://example.com/ask-ms-ivey"
    alive = Page("https://example.com/ask-ms-ivey")
    assert recover(alive) is False and alive.back == 0


def test_a_model_connection_failure_is_retried_twice_and_other_errors_are_not():
    # the example app write-7 (2026-09-20): one transport blip at action 163 of partner B's walk ended a
    # twelve-minute chain, because upstream retries HTTP 429 but raises at once on a connection error.
    calls, naps = [], []

    def flaky(*args):
        calls.append(args)
        if len(calls) < 3:
            raise RuntimeError("Model connection failed; no action executed.")
        return {"ok": True}

    assert retrying(flaky, naps.append)("url", "key", {}) == {"ok": True}
    assert len(calls) == 3 and naps == [1, 2]

    def dead(*args):
        raise RuntimeError("Model connection failed; no action executed.")

    with pytest.raises(RuntimeError, match="connection failed"):
        retrying(dead, naps.append)("url", "key", {})
    assert naps == [1, 2, 1, 2]

    def wrong(*args):
        raise RuntimeError("Model provider returned HTTP 400; no action executed.")

    with pytest.raises(RuntimeError, match="HTTP 400"):
        retrying(wrong, naps.append)("url", "key", {})
    assert naps == [1, 2, 1, 2]


def test_an_unproven_done_scrolls_first_only_while_the_page_continues_below():
    # the example app write-16 (2026-09-20): Jev reached the shared map, said blocked twice, and the link the
    # check wanted was under the fold; a person scrolls to the bottom before giving up.
    assert more_below({"actions": [{"id": "e1", "kind": "click"}, {"id": "scroll_down", "kind": "scroll"}]})
    assert not more_below({"actions": [{"id": "e1", "kind": "click"}]})


def test_the_checkout_guard_treats_a_page_that_left_stripe_mid_check_as_stale_not_live():
    # the example app write-17 (2026-09-20): after Pay, the guard read the URL on Stripe and the body on the
    # walkthrough the redirect had already reached, saw no Sandbox badge and halted the run as live mode.
    stripe = "https://checkout.stripe.com/c/pay/cs_test_a1"
    assert checkout_guard(stripe, stripe, "Sandbox Pay $79.00") is None
    with pytest.raises(ValueError, match="Observe again"):
        checkout_guard(stripe, "https://decidenorth-sandbox.vercel.app/walkthrough/x?session_id=cs_test_a1", "Your shared map")
    with pytest.raises(NotTestMode):
        checkout_guard("https://checkout.stripe.com/c/pay/cs_live_a1", "https://checkout.stripe.com/c/pay/cs_live_a1", "Pay $79.00")
    assert checkout_guard("https://example.com/", "https://example.com/", "anything") is None


def test_a_card_is_typed_only_on_a_test_mode_checkout():
    assert stripe_test_mode("https://checkout.stripe.com/c/pay/cs_test_a1B2#fid", "Sandbox\nExample\n$195.00")
    assert stripe_test_mode("https://checkout.stripe.com/c/pay/cs_test_a1B2", "TEST MODE Pay Example")
    assert not stripe_test_mode("https://checkout.stripe.com/c/pay/cs_live_a1B2", "Sandbox")
    assert not stripe_test_mode("https://checkout.stripe.com/c/pay/cs_test_a1B2", "Example $195.00 Pay")


# records, stamps and the exit code


def test_the_stamp_cannot_collide_within_a_second_and_the_token_is_short_and_lowercase():
    now = datetime(2026, 9, 19, 11, 5, 12, tzinfo=timezone.utc)
    stamps = {new_stamp(now) for _ in range(50)}
    assert len(stamps) == 50
    assert all(re.fullmatch(r"20260919T110512Z-[0-9a-f]{4}", s) for s in stamps)
    assert re.fullmatch(r"0919t110512[0-9a-f]{4}", run_token(next(iter(stamps))))


def test_a_record_is_written_whole_or_not_at_all(tmp_path):
    path = tmp_path / "created.json"
    write_atomic(path, '{"a": 1}')
    write_atomic(path, '{"a": 2}')
    assert json.loads(path.read_text()) == {"a": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["created.json"]  # no temp file left behind


def test_an_incomplete_chain_or_a_skipped_journey_fails_the_run_unless_known():
    rows = [{"id": "a", "result": "pass", "known": None}, {"id": "b", "result": "skip", "known": None},
            {"id": "c", "result": "fail", "known": "D-1"}, {"id": "d", "result": "flaky", "known": None},
            {"id": "e", "result": "error", "known": None}]
    assert [r["id"] for r in incomplete(rows)] == ["b", "e"]
    assert incomplete(rows[:1] + rows[2:4]) == []


def test_known_harmless_events_come_from_the_site_hooks():
    assert HOOKS.harmless({"type": "http_error", "status": 401, "url": "https://x/api/intake/?action=orders"})
    assert not HOOKS.harmless({"type": "http_error", "status": 500, "url": "https://x/api/intake/?action=orders"})
    assert load_hooks(Path(__file__).parents[1] / "templates").harmless({"type": "page_error"}) is False
    assert load_hooks(Path("/nonexistent")) is None


# unchanged walker semantics


def test_matching_ignores_how_whitespace_is_split():
    seen = [("https://x/houston/", "the MP3\naudio\nguide and $195")]
    assert passed({"text": ["audio guide"]}, seen, [], [])


def test_a_click_that_did_nothing_on_this_page_is_not_offered_again():
    actions = [{"kind": "click", "label": "See if this report fits your family"},
               {"kind": "click", "label": "One focus child"}, {"kind": "scroll", "label": "Scroll down"}]
    history = [{"kind": "click", "action": "See if this report fits your family", "page_changed": False,
                "url": "https://x/houston/#fit"}]
    assert [a["label"] for a in offered(actions, history, "https://x/houston/#fit")] == [
        "One focus child", "Scroll down"]
    assert len(offered(actions, history, "https://x/about/")) == 3
    fields = [{"kind": "fill", "label": "What could you compromise on?"}, {"kind": "click", "label": "Continue"}]
    typed = [{"kind": "fill", "action": "What could you compromise on?", "page_changed": False, "url": "https://x/"}]
    assert [a["label"] for a in offered(fields, typed, "https://x/")] == ["Continue"]


def test_pass_needs_every_pattern_somewhere_on_a_matching_page():
    seen = [("https://x/houston/", "One payment of $195"), ("https://x/houston/#fit", "the MP3 audio guide")]
    assert passed({"text": [r"\$195", "audio guide"]}, seen, [], [])
    assert not passed({"text": [r"\$195", "refund"]}, seen, [], [])
    assert passed({"text": ["audio guide"], "on": "/houston/"}, seen, [], [])
    assert not passed({"text": [r"\$195"], "on": "/terms/"}, seen, [], [])


def test_pass_on_url_or_blocked_request():
    assert passed({"url": "/intake/"}, [], ["https://x/", "https://x/intake/"], [])
    assert not passed({"url": "/intake/"}, [], ["https://x/"], [])
    assert passed({"blocked": "POST .*/api/newsletter"}, [], [], ["POST https://x/api/newsletter"])
    assert not passed({"blocked": "POST .*/api/newsletter"}, [], [], ["GET https://x/api/newsletter"])


def test_every_condition_in_a_spec_must_hold():
    assert not passed({"url": "/terms/", "text": ["refund"]}, [("https://x/terms/", "Refunds")], ["https://x/"], [])


def test_any_passes_when_one_alternative_holds():
    spec = {"any": [{"text": ["hello@example\\.com"]}, {"url": "^mailto:hello@"}]}
    assert passed(spec, [], ["mailto:hello@example.com"], [])
    assert passed(spec, [("https://x/about/", "Write to hello@example.com")], [], [])
    assert not passed(spec, [("https://x/", "contact us")], ["https://x/"], [])


def test_pass_can_require_a_response_from_the_site_api():
    api = ["200 https://x/api/intake/?action=status", "404 https://x/api/intake/?action=session&orderId=abc"]
    assert passed({"api": "^404 .*action=session&orderId=abc"}, [], [], [], api)
    assert not passed({"api": "^200 .*action=session&orderId=abc"}, [], [], [], api)
    assert passed({"api": ["^200 .*action=status", "^404 .*action=session"]}, [], [], [], api)
    assert not passed({"api": ["^200 .*action=status", "^200 .*action=sign-out"]}, [], [], [], api)


def test_loop_is_the_same_action_at_the_same_place_three_times():
    at_top = ("https://x/", 0)
    assert not looping([(at_top, "Scroll down"), (("https://x/", 560), "Scroll down"), (("https://x/", 1120), "Scroll down")])
    assert looping([(at_top, "About"), (("https://x/about/", 0), "Home"), (at_top, "About"),
                    (("https://x/about/", 0), "Home"), (at_top, "About")])
    assert not looping([])


def test_a_read_walk_that_loops_sets_the_control_aside_instead_of_ending():
    # the example site post-release walk (2026-09-21): ai-or-human bounced between the About page and the
    # report page for three runs while three pages answered it under the fold. A write walk already set a
    # looping control aside and carried on; a read walk ended at once, so it never saw the rest of a page.
    about, fit = ("https://x/about/", 0), ("https://x/houston/#fit", 0)
    steps = [(about, "The report"), (fit, "Read why I built it"), (about, "The report"),
             (fit, "Read why I built it"), (fit, "Read why I built it")]
    label, note = loop_recovery(steps, bans=0, write=False)
    assert label == "Read why I built it"
    assert "keeps bringing you back" in note and "scroll" in note
    assert "is already done" in loop_recovery(steps, bans=0, write=True)[1]
    assert loop_recovery(steps, bans=3, write=False) is None
    assert loop_recovery(steps[:3], bans=0, write=False) is None
    assert loop_recovery([], bans=0, write=False) is None


def test_the_loop_recovery_never_sets_the_scroll_aside():
    # the example site run 20260921T094924Z-5e89: a walk came back to the top of the same page three times
    # and scrolled each time, so the recovery set Scroll down aside and the walk could read no page below
    # its fold after that. It then reached /method/, which answers the goal under the fold, and left again.
    top, down = ("https://x/houston/", 0), "Scroll down"
    steps = [(top, down), (("https://x/houston/", 560), down), (top, down), (("https://x/about/", 0), "About"),
             (top, down)]
    label, note = loop_recovery(steps, bans=0, write=False)
    assert label is None
    assert "not moving" in note and "scroll" in note


def test_dedupe_counts_repeats_and_ignores_query_strings():
    rows = dedupe([{"type": "blocked", "method": "GET", "url": "https://a/x.js?v=1"},
                   {"type": "blocked", "method": "GET", "url": "https://a/x.js?v=2"},
                   {"type": "page_error", "text": "Failed to fetch"}])
    assert [(r["type"], r["count"]) for r in rows] == [("blocked", 2), ("page_error", 1)]


def test_placeholders_are_filled_everywhere_in_a_journey():
    journey = {"start": "{verify_link_a}", "goal": "Sign in as {email_a} with {password_a}.",
               "pass": {"api": "^404 .*orderId={order_id_a}"}}
    assert fill(journey, {"verify_link_a": "https://x/intake/return/#verify=t", "email_a": "tester+jev1a@example.com",
                          "password_a": "Jevabc", "order_id_a": "11111111-2222-3333-4444-555555555555"}) == {
        "start": "https://x/intake/return/#verify=t", "goal": "Sign in as tester+jev1a@example.com with Jevabc.",
        "pass": {"api": "^404 .*orderId=11111111-2222-3333-4444-555555555555"}}


def test_record_created_asks_the_site_for_nothing_when_a_run_has_no_accounts(tmp_path):
    """A --only run whose journeys name no account letter has no addresses; the site's lookup is
    never called with an empty list, and the record is still written."""
    class Hooks:
        def created(self, addresses, site):
            raise AssertionError("called with " + repr(addresses))

    path = tmp_path / "created.json"
    assert record_created(path, {}, Hooks(), {}) == []
    assert json.loads(path.read_text()) == {"accounts": {}, "users": {}, "orders": {}}


# The build a run walked, and the production probe (review of 2026-09-23, recommendation 1).
# the example site's September 19 write walk ran against a deployment from before PR #294, so the owner-bound
# staging shipped with no walker evidence; and production checkout answered 502 for four days while every
# sandbox walk passed, because a walk never reads production.

WALK = Path(__file__).parents[1] / "scripts/walk.py"


def cli(*args, env=None):
    """walk.py as a person runs it, with the environment it would have and nothing more."""
    import subprocess
    import sys
    base = {k: v for k, v in os.environ.items() if k not in {"TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "JEV_PROVIDER"} and not k.startswith("TEXT_MODEL")}
    return subprocess.run([sys.executable, str(WALK), *args], capture_output=True, text=True, check=False,
                          env={**base, **(env or {})}, timeout=60)


def site_folder(tmp_path, hooks):
    """The fixture site with its own hooks.py, which appends each hook it is asked for to calls.log."""
    for name in ["site.json", "goals.json", "goals-write.json", "cleanup.py"]:
        shutil.copy(FIXTURE / name, tmp_path / name)
    (tmp_path / "hooks.py").write_text(
        "from pathlib import Path\n"
        "def _log(name):\n"
        "    with open(Path(__file__).parent / 'calls.log', 'a') as f:\n"
        "        f.write(name + '\\n')\n" + hooks)
    return tmp_path


def calls(folder):
    log = folder / "calls.log"
    return log.read_text().split() if log.exists() else []


def test_the_build_walked_is_recorded_and_reported():
    assert built(types.SimpleNamespace(build=lambda origin, site: {"commit": "a1b2c3d4e5", "deployment": "dpl_1"}),
                 SANDBOX, SITE) == {"commit": "a1b2c3d4e5", "deployment": "dpl_1"}
    assert built(None, SANDBOX, SITE) is None
    assert built(types.SimpleNamespace(), SANDBOX, SITE) is None
    for wrong in [None, "a1b2c3d", {"commit": ""}, {"commit": 7}, {"deployment": "dpl_1"}]:
        assert built(types.SimpleNamespace(build=lambda origin, site, w=wrong: w), SANDBOX, SITE) is None, wrong
    rows = [{"id": "a", "step": "pay", "viewport": "phone", "result": "pass", "reason": "pass", "actions": 3,
             "seconds": 1.0, "jev_usd": 0.001, "known": None, "events": []}]
    assert "Build walked: a1b2c3d4e5 (dpl_1)" in report(rows, ["pay"], {"commit": "a1b2c3d4e5", "deployment": "dpl_1"})
    assert "Build walked: unknown" in report(rows, ["pay"])


def test_expect_commit_passes_a_matching_prefix_and_refuses_anything_else():
    assert stale({"commit": "a1b2c3d4e5f6", "deployment": None}, "a1b2c3d") is None
    assert stale({"commit": "A1B2C3D4E5F6", "deployment": None}, "a1b2c3d") is None
    assert "9f9f9f9" in stale({"commit": "9f9f9f9f9f", "deployment": None}, "a1b2c3d")
    assert "no build" in stale(None, "a1b2c3d")
    for bad in ["", "a1b2c3", "a1b2c3dz", "x" * 41]:
        assert "7 to 40" in stale({"commit": "a1b2c3d4"}, bad), bad


def test_expect_commit_refuses_a_stale_build_before_anything_else_happens(tmp_path):
    folder = site_folder(tmp_path, "def build(origin, site):\n    _log('build')\n"
                                   "    return {'commit': '9f9f9f9f9f', 'deployment': 'dpl_old'}\n"
                                   "def preflight(origin, site):\n    _log('preflight')\n    return {}\n"
                                   "def created(addresses, site):\n    _log('created')\n    return []\n")
    run = cli(SANDBOX, "--write", "--site", str(folder), "--expect-commit", "a1b2c3d",
              env={"TYPESAFE_API_KEY": "unused"})
    assert run.returncode != 0 and "9f9f9f9f9f" in run.stdout + run.stderr
    assert calls(folder) == ["build"]
    assert not (folder / "runs").exists()
    missing = cli(SANDBOX, "--write", "--site", str(folder), "--expect-commit", env={"TYPESAFE_API_KEY": "unused"})
    assert missing.returncode != 0 and "--expect-commit" in missing.stdout + missing.stderr


def test_order_of_effects_nothing_runs_past_a_refusal(tmp_path):
    hooks = ("def build(origin, site):\n    _log('build')\n    return {'commit': 'a1b2c3d4e5', 'deployment': None}\n"
             "def preflight(origin, site):\n    _log('preflight')\n"
             "    return {'auth': {'kind': 'supabase', 'ref': 'abcdefgh'}, 'database': {'production': True},\n"
             "            'payment': {'provider': 'stripe', 'account': 'acct_test', 'livemode': True}, 'webhook': origin}\n"
             "def created(addresses, site):\n    _log('created')\n    return []\n"
             "def verification_link(email, origin, site):\n    _log('verification_link')\n    return origin\n")
    folder = site_folder(tmp_path, hooks)
    refused = cli(SANDBOX, "--write", "--site", str(folder), "--expect-commit", "a1b2c3d",
                  env={"TYPESAFE_API_KEY": "unused"})
    assert refused.returncode != 0 and "livemode" in refused.stdout + refused.stderr
    assert calls(folder) == ["build", "preflight"]
    assert not (folder / "runs").exists()
    # Goals that cannot run stop the run before any hook is asked anything.
    (folder / "calls.log").unlink()
    (folder / "goals-write.json").write_text(json.dumps([{"id": "a", "step": "nowhere", "start": "/", "goal": "x",
                                                         "pass": {"url": "/"}}]))
    invalid = cli(SANDBOX, "--write", "--site", str(folder), env={"TYPESAFE_API_KEY": "unused"})
    assert invalid.returncode != 0 and "nowhere" in invalid.stdout + invalid.stderr
    assert calls(folder) == [] and not (folder / "runs").exists()


def test_the_probe_prints_each_problem_and_needs_no_key_origin_or_browser(tmp_path):
    folder = site_folder(tmp_path, "def production_probe(site):\n    _log('production_probe')\n"
                                   "    return ['STRIPE_SECRET_KEY cannot read /v1/account (403)',\n"
                                   "            'EXAMPLE_FEATURE_ENABLED is set in Preview and not in Production']\n")
    run = cli("--probe", "--site", str(folder))
    assert run.returncode == 1, run.stdout + run.stderr
    assert "STRIPE_SECRET_KEY cannot read /v1/account (403)" in run.stdout
    assert "EXAMPLE_FEATURE_ENABLED is set in Preview and not in Production" in run.stdout
    assert calls(folder) == ["production_probe"]
    (folder / "hooks.py").write_text("def production_probe(site):\n    return []\n")
    clean = cli("--probe", "--site", str(folder))
    assert clean.returncode == 0 and "no problems" in clean.stdout
    for hooks, expected in [("def build(origin, site):\n    return None\n", "production_probe"),
                            ("def production_probe(site):\n    return 'fine'\n", "list of strings"),
                            ("def production_probe(site):\n    raise RuntimeError('vercel is not logged in')\n",
                             "vercel is not logged in")]:
        (folder / "hooks.py").write_text(hooks)
        broken = cli("--probe", "--site", str(folder))
        assert broken.returncode == 2 and expected in broken.stdout + broken.stderr, hooks
    for extra in [[SANDBOX], ["--write"], ["--only", "a"]]:
        refused = cli("--probe", "--site", str(folder), *extra)
        assert refused.returncode == 2, extra


# State-gap cells as walker goals (review of 2026-09-23, recommendation 2). On three sites no state-gap cell
# was ever walked: the example site's refund handler went live with no walk, and its model left out the sign-up
# staging where the walker found both live defects of September 21.

MODEL = {
    "systems": [],
    "events": [{"id": "checkout_completed"}, {"id": "owner_replied", "name": "Owner replied"}],
    "regions": [
        {"id": "payment", "states": [{"id": "visitor", "isInitial": True, "isFinal": False},
                                     {"id": "paid", "isInitial": False, "isFinal": True}],
         "transitions": [{"from": "visitor", "event": "checkout_completed", "to": "paid"},
                         {"from": "paid", "event": "refund", "to": "visitor"}]},
        {"id": "lead", "states": [{"id": "new", "isInitial": True, "isFinal": False},
                                  {"id": "answered", "isInitial": False, "isFinal": True}],
         "transitions": [{"from": "new", "event": "owner_replied", "to": "answered"}]}],
    "decisions": [{"region": "payment", "state": "paid", "event": "dispute",
                   "absent": {"owner": "Service operations", "recovery": "Answer in the dashboard."}},
                  {"region": "lead", "state": "new", "event": "refund", "ignored": "A lead has paid nothing."}],
}
CANDIDATES = ["payment.visitor.checkout_completed", "payment.paid.refund", "lead.new.owner_replied",
              "payment.paid.dispute"]


def model_site(tmp_path, model=MODEL):
    (tmp_path / "model.json").write_text(json.dumps(model))
    return {**SITE, "model": "model.json"}


def test_cells_validate_against_the_model_including_the_seeded_events(tmp_path):
    site = model_site(tmp_path)
    model = load_model(tmp_path, site)
    assert model["candidates"] == CANDIDATES
    good = {"id": "a", "step": "pay", "start": "/", "goal": "x", "pass": {"url": "/"}}
    # refund and dispute are seeded by state-gap: a model never lists them, and a goal may still name them.
    assert validate([{**good, "cells": ["payment.paid.refund", "payment.paid.dispute", "lead.new.owner_replied"]}],
                    site, model) == []
    assert validate([{**good, "cells": ["payment.paid.refund_issued", "leads.new.owner_replied", "payment.paid"]}],
                    site, model) == ["goal a: cell payment.paid.refund_issued is not in the model",
                                     "goal a: cell leads.new.owner_replied is not in the model",
                                     "goal a: cell payment.paid is not in the model"]
    assert validate([{**good, "cells": "payment.paid.refund"}], site, model) == [
        "goal a: cells must be a list of region.state.event"]
    assert validate([{**good, "cells": ["payment.paid.refund"]}], SITE) == [
        "goal a: cells need a state-gap model named by site.json model"]


def test_cells_validate_refuses_a_model_it_cannot_read(tmp_path):
    assert load_model(tmp_path, {**SITE, "model": "missing.json"})["problems"] == [
        f"site.json model {tmp_path / 'missing.json'} does not exist"]
    broken = {**MODEL, "regions": [{"id": "payment", "states": "visitor"}]}
    assert load_model(tmp_path, model_site(tmp_path, broken))["problems"] == [
        "model regions[0] needs an id, states and transitions as lists"]
    assert load_model(tmp_path, SITE) is None


def test_cells_report_lists_what_a_passing_walk_covered_and_every_candidate_nobody_walked():
    rows = [{"id": "pay-a", "step": "pay", "viewport": "phone", "result": "pass", "reason": "pass", "actions": 3,
             "seconds": 1.0, "jev_usd": 0.001, "known": None, "events": [],
             "cells": ["payment.visitor.checkout_completed"]},
            {"id": "refund-a", "step": "pay", "viewport": "phone", "result": "fail", "reason": "done", "actions": 3,
             "seconds": 1.0, "jev_usd": 0.001, "known": None, "events": [], "cells": ["payment.paid.refund"]}]
    text = report(rows, ["pay"], None, CANDIDATES)
    assert "Cells walked (1): payment.visitor.checkout_completed" in text
    assert ("Candidate cells no journey walks (3): payment.paid.refund, lead.new.owner_replied, "
            "payment.paid.dispute") in text
    assert "Cells walked" not in report(rows, ["pay"])


def test_cells_cli_prints_each_candidate_by_region_with_the_goals_that_walk_it(tmp_path):
    folder = site_folder(tmp_path, "")
    (folder / "model.json").write_text(json.dumps(MODEL))
    site = json.loads((folder / "site.json").read_text())
    (folder / "site.json").write_text(json.dumps({**site, "model": "model.json"}))
    goals = json.loads((folder / "goals-write.json").read_text())
    goals[0]["cells"] = ["payment.visitor.checkout_completed"]
    (folder / "goals-write.json").write_text(json.dumps(goals))
    run = cli("--cells", "--site", str(folder))
    assert run.returncode == 0, run.stdout + run.stderr
    lines = run.stdout.splitlines()
    assert "payment" in lines and "lead" in lines
    assert f"  planned payment.visitor.checkout_completed ({goals[0]['id']})" in lines
    assert "  -       payment.paid.dispute" in lines
    assert "4 candidate cells, 1 planned by a goal" in run.stdout
    assert calls(folder) == []
    (folder / "site.json").write_text(json.dumps(site))
    assert cli("--cells", "--site", str(folder)).returncode == 2
    assert cli("--cells", "--site", str(folder), SANDBOX).returncode == 2


def seed_ids(source):
    """The event ids in state-gap.mjs's SEEDS block, every row of it, with state-gap's id grammar."""
    block = re.search(r"const SEEDS = \[(.*?)\];", source, re.DOTALL).group(1)
    rows = re.findall(r"\[\s*\"([^\"]*)\"\s*,", block)
    assert len(rows) == block.count("["), "a SEEDS row the parser did not read"
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", r) for r in rows), rows
    return rows


def test_the_seeded_events_match_state_gap():
    # state-gap is the canonical list: its absence fails the check rather than waiving it.
    engine = Path(__file__).parents[1] / "scripts/state-gap.mjs"
    assert list(SEEDS) == seed_ids(engine.read_text())
    synthetic = 'const SEEDS = [\n  ["refund", "Refund"],\n  ["future2", "Future"],\n];'
    assert seed_ids(synthetic) == ["refund", "future2"]


# Steps outside the browser (review of 2026-09-23, recommendation 3). A refund is a Stripe action and a family
# email lands in a mailbox, so neither could be walked; the refund handler went live unexercised although the
# sandbox is in test mode, where a refund of the chain's own test order is one API call.

def journey(id, **extra):
    return {"id": id, "step": "pay", "start": "/", "goal": "x", "pass": {"url": "/"}, **extra}


class LoggingPool:
    """Runs no browser: each walk is logged and returns the result the test names."""
    def __init__(self, log, outcome=None):
        self.log, self.outcome = log, outcome or {}

    def submit(self, fn, site, site_dir, origin, journey, out_dir, write):
        self.log.append(("walk", journey["id"]))
        result = self.outcome.get(journey["id"], "pass")
        return types.SimpleNamespace(result=lambda: {"id": journey["id"], "result": result, "reason": result,
                                                     "jev_usd": 0.0, "final_url": origin + "/done"})


def hooks_folder(tmp_path, body):
    (tmp_path / "hooks.py").write_text("LOG = []\ndef created(addresses, site):\n    return []\n" + body)
    return tmp_path


def test_do_step_runs_each_hook_with_filled_values_before_the_browser_opens(tmp_path):
    folder = hooks_folder(tmp_path, "def refund(args, site):\n    LOG.append(('refund', args))\n"
                                    "def replay(args, site):\n    LOG.append(('replay', args))\n")
    hooks = load_hooks(folder)
    log = []
    hooks.LOG = log
    goals = [journey("refund-a", do=[{"hook": "refund", "args": {"account": "{email_a}", "amount": 19500}},
                                     {"hook": "replay", "args": {"event": "charge.refunded"}}])]
    assert validate(goals, SITE, write=True, hooks=hooks) == []
    import walk
    real = walk.load_hooks
    walk.load_hooks = lambda site_dir: hooks
    try:
        records = run_write(LoggingPool(log), SITE, str(folder), SANDBOX, goals, str(tmp_path / "out"),
                            "20260923T000000Z-ab12", lambda: 0.0, [])
    finally:
        walk.load_hooks = real
    email = SITE["write"]["email_format"].format(run=run_token("20260923T000000Z-ab12"), name="a")
    assert log == [("refund", {"account": email, "amount": 19500}), ("replay", {"event": "charge.refunded"}),
                   ("walk", "refund-a")]
    assert records[0]["result"] == "pass" and records[0]["do"] == ["refund", "replay"]


def test_do_step_names_only_public_site_hooks(tmp_path):
    hooks = load_hooks(hooks_folder(tmp_path, "def refund(args, site):\n    pass\ndef _secret(args, site):\n    pass\n"
                                              "NOT_A_HOOK = 3\n"))
    for step, message in [({"hook": "nosuch"}, "do hook nosuch is not a function in hooks.py"),
                          ({"hook": "_secret"}, "do hook _secret is not a function in hooks.py"),
                          ({"hook": "NOT_A_HOOK"}, "do hook NOT_A_HOOK is not a function in hooks.py"),
                          ({"hook": "created"}, "do hook created is one of the runner's own hooks"),
                          ({"hook": "refund", "args": [1]}, "do args must be an object"),
                          ("refund", "do must be a list of {hook, args}")]:
        do = step if isinstance(step, str) else [step]
        assert validate([journey("a", do=do)], SITE, write=True, hooks=hooks) == [f"goal a: {message}"], step


def test_do_step_that_raises_skips_its_journey_and_the_chain_follows_the_usual_rules(tmp_path):
    folder = hooks_folder(tmp_path, "def refund(args, site):\n    raise RuntimeError('stripe: no charge on order')\n")
    log = []
    goals = [journey("refund-a", do=[{"hook": "refund"}]), journey("after-refund", after="refund-a"),
             journey("independent")]
    records = run_write(LoggingPool(log), SITE, str(folder), SANDBOX, goals, str(tmp_path / "out"),
                        "20260923T000000Z-ab12", lambda: 0.0, [])
    assert [(r["id"], r["result"]) for r in records] == [("refund-a", "skip"), ("after-refund", "skip"),
                                                         ("independent", "pass")]
    assert records[0]["reason"] == "do refund failed: RuntimeError: stripe: no charge on order"
    assert log == [("walk", "independent")]


MESSAGE = {"subject": "Your refund of $195", "body": "We refunded order 42 today.", "to": "a@x", "received": 1000.0}


def test_mail_check_matches_only_a_message_after_the_start_with_every_pattern():
    clock = {"t": 1000.0}

    def sleep(seconds):
        clock["t"] += seconds

    def mailbox(*messages):
        return types.SimpleNamespace(mail=lambda address, since, site: list(messages))

    spec = {"to": "a", "subject": "refund", "body": ["order \\d+", "today"], "within": 30}
    assert mailed(spec, "a@x", 999.0, mailbox(MESSAGE), SITE, sleep, lambda: clock["t"]) == "Your refund of $195"
    assert clock["t"] == 1000.0, "a match on the first read does not wait"
    early = {**MESSAGE, "received": 998.0}
    assert mailed(spec, "a@x", 999.0, mailbox(early), SITE, sleep, lambda: clock["t"]) is None
    assert clock["t"] >= 1030.0, "it keeps reading until within has passed"
    clock["t"] = 1000.0
    missing = {**MESSAGE, "body": "We refunded order 42."}
    assert mailed(spec, "a@x", 999.0, mailbox(missing), SITE, sleep, lambda: clock["t"]) is None
    with pytest.raises(ValueError, match="hooks.mail"):
        mailed(spec, "a@x", 999.0, mailbox({"subject": "x"}), SITE, sleep, lambda: clock["t"])


def test_mail_check_is_a_postcondition_of_a_passing_walk(tmp_path):
    folder = hooks_folder(tmp_path, "def mail(address, since, site):\n"
                                    "    letter = address.split('@')[0][-1]\n"
                                    "    assert letter != 'c', 'a failed walk never reads the mailbox'\n"
                                    "    return [{'subject': 'Refund confirmed', 'body': 'b', 'to': address,\n"
                                    "             'received': since + 1}] if letter == 'a' else []\n")
    goals = [journey("refund-a", mail={"to": "a", "subject": "Refund"}),
             journey("refund-b", mail={"to": "b", "subject": "Refund", "within": 1}),
             journey("failed-c", mail={"to": "c", "subject": "Refund"})]
    records = run_write(LoggingPool([], {"failed-c": "fail"}), SITE, str(folder), SANDBOX, goals,
                        str(tmp_path / "out"), "20260923T000000Z-ab12", lambda: 0.0, [])
    assert [(r["id"], r["result"], r["reason"]) for r in records] == [
        ("refund-a", "pass", "pass"), ("refund-b", "fail", "mail"), ("failed-c", "fail", "fail")]
    assert records[0]["mail"] == "Refund confirmed" and records[1]["mail"] is None


def test_read_refuses_do_and_mail():
    assert validate([journey("a", do=[{"hook": "refund"}])], SITE) == ["goal a: do and mail are write mode only"]
    assert validate([journey("a", mail={"to": "a"})], SITE) == ["goal a: do and mail are write mode only"]
    for spec, message in [({"subject": "x"}, "mail needs to, an account letter"),
                          ({"to": "a", "within": 0}, "mail within must be 1 to 600 seconds"),
                          ({"to": "a", "within": 601}, "mail within must be 1 to 600 seconds"),
                          ({"to": "a", "body": "x"}, "mail body must be a list of patterns"),
                          ({"to": "a", "subject": "("}, "'(' is not a regex")]:
        mailbox = types.SimpleNamespace(mail=lambda address, since, site: [], created=HOOKS.created)
        assert validate([journey("a", mail=spec)], SITE, write=True, hooks=mailbox) == [f"goal a: {message}"], spec


def test_fill_values_puts_a_quote_or_backslash_through_unchanged():
    value = 'ord"er\\42'
    filled = fill(journey("a", start="/orders/{order_id_a}", do=[{"hook": "refund", "args": {"id": "{order_id_a}"}}]),
                  {"order_id_a": value})
    assert filled["start"] == "/orders/" + value
    assert filled["do"][0]["args"]["id"] == value


# Write mode for a business with no checkout and no sign-in (review of 2026-09-23, recommendation 4). An
# inquiry form that creates a lead, or a booking page that creates a booking, could not be walked in write
# mode: the gate required a Stripe attestation and Clerk or Supabase, and created.json held only users and
# orders.

NO_PAYMENT = {k: v for k, v in SITE["write"].items() if k not in {"payment", "payment_account"}}
LEAD_SITE = {**SITE, "write": {**NO_PAYMENT, "auth": "none"}}


def attesting(attestation):
    return types.SimpleNamespace(preflight=lambda origin, site: attestation, created=HOOKS.created)


def test_no_payment_passes_the_gate_without_a_payment_attestation_or_webhook():
    site = {**SITE, "write": NO_PAYMENT}
    bare = {"auth": {"kind": "supabase", "ref": "abcdefgh"}, "database": {"production": False}}
    assert attested(site, bare) == []
    assert gate(site, SANDBOX, FIXTURE, attesting(bare)) == []
    # The other attested facts still hold without a payment section.
    assert gate(site, SANDBOX, FIXTURE, attesting({**bare, "database": {"production": True}})) == []
    unexcepted = {**site, "write": {k: v for k, v in NO_PAYMENT.items() if k != "shared_database_exception"}}
    assert gate(unexcepted, SANDBOX, FIXTURE, attesting({**bare, "database": {"production": True}})) == [
        "the deployment writes to the production database and site.json records no exception"]
    assert gate(site, SANDBOX, FIXTURE, attesting({**bare, "auth": {"kind": "supabase", "ref": "other"}})) == [
        "Supabase auth ref other is not abcdefgh"]
    # A site that names a payment provider still needs its attestation and the sandbox webhook.
    assert gate(SITE, SANDBOX, FIXTURE, attesting(bare)) == [
        "payment provider None is not stripe", "payment livemode is not false",
        "payment account None is not acct_test", "webhook destination None is not the sandbox"]


def test_no_payment_blocks_every_stripe_host_in_a_write_walk():
    site = {**SITE, "write": {**NO_PAYMENT, "api_allow": NO_PAYMENT["api_allow"] + [
        {"method": "POST", "origin": "https://api.stripe.com", "path_pattern": "^/v1/"}]}}
    for method, url, navigation in [
            ("GET", "https://checkout.stripe.com/c/pay/cs_test_1", True),
            ("GET", "https://js.stripe.com/v3/", False),
            ("GET", "http://js.stripe.com/v3/", False),
            ("GET", "https://stripe.com/", True),
            ("POST", "https://api.stripe.com/v1/payment_pages/cs_test_1/confirm", False),
            ("GET", "https://m.stripe.network/inner.html", False),
            ("GET", "https://q.stripecdn.com/x.js", False),
            ("GET", "https://b.stripecdn.com/y.css", False)]:
        assert handling(site, method, url, SANDBOX, navigation, write=True) == "block", url
    # The site's own write requests still go through, and a lookalike host is not a Stripe host.
    assert handling(site, "POST", SANDBOX + "/api/intake/?action=signup", SANDBOX, False, write=True) == "allow"
    assert handling(site, "GET", "https://evilstripe.com/x.js", SANDBOX, False, write=True) == "stub"
    # A read walk is unchanged: a Stripe script is stubbed and a navigation to Stripe is blocked.
    assert handling(site, "GET", "https://js.stripe.com/v3/", SANDBOX, False) == "stub"
    assert handling(site, "GET", "https://checkout.stripe.com/c/pay/cs_test_1", SANDBOX, True) == "block"


def test_gate_accepts_auth_none_only_when_site_json_says_none():
    none = {"auth": {"kind": "none"}, "database": {"production": False}}
    assert gate(LEAD_SITE, SANDBOX, FIXTURE, attesting(none)) == []
    # With write.auth omitted, today's rule: Clerk or Supabase, and nothing else.
    legacy = {**SITE, "write": NO_PAYMENT}
    assert gate(legacy, SANDBOX, FIXTURE, attesting(none)) == ["unknown auth kind none"]
    assert gate(legacy, SANDBOX, FIXTURE, attesting({**none, "auth": {}})) == ["unknown auth kind None"]
    # With write.auth present, the attested kind must be that one.
    for declared, kind in [("clerk", "none"), ("supabase", "none"), ("none", "supabase"), ("none", "clerk")]:
        site = {**SITE, "write": {**NO_PAYMENT, "auth": declared}}
        attestation = {**none, "auth": {"kind": kind, "ref": "abcdefgh", "key": "pk_test_1"}}
        assert gate(site, SANDBOX, FIXTURE, attesting(attestation)) == [f"auth kind {kind} is not {declared}"], declared
    clerk = {**SITE, "write": {**NO_PAYMENT, "auth": "clerk"}}
    assert gate(clerk, SANDBOX, FIXTURE, attesting({**none, "auth": {"kind": "clerk", "key": "pk_test_1"}})) == []
    assert gate(clerk, SANDBOX, FIXTURE, attesting({**none, "auth": {"kind": "clerk", "key": "pk_live_1"}})) == [
        "Clerk is not the development instance (no pk_test_ key)"]
    supabase = {**SITE, "write": {**NO_PAYMENT, "auth": "supabase"}}
    assert gate(supabase, SANDBOX, FIXTURE, attesting({**none, "auth": {"kind": "supabase", "ref": "other"}})) == [
        "Supabase auth ref other is not abcdefgh"]
    # Declaring an auth kind the runner does not know does not make it known.
    okta = {**SITE, "write": {**NO_PAYMENT, "auth": "okta"}}
    assert gate(okta, SANDBOX, FIXTURE, attesting({**none, "auth": {"kind": "okta"}})) == ["unknown auth kind okta"]


def test_gate_still_refuses_every_existing_case_in_the_same_order(tmp_path):
    for site in [SITE, {**SITE, "write": {**SITE["write"], "auth": "supabase"}}]:
        assert gate(site, SANDBOX, FIXTURE, HOOKS) == []
        for override, message in [
                ({"payment__livemode": True}, "payment livemode is not false"),
                ({"payment__account": "acct_live"}, "payment account acct_live is not acct_test"),
                ({"payment__provider": "paypal"}, "payment provider paypal is not stripe"),
                ({"webhook__": "https://example.com/api/stripe"},
                 "webhook destination https://example.com/api/stripe is not the sandbox"),
                ({"auth__ref": "other"}, "Supabase auth ref other is not abcdefgh")]:
            assert gate(site, SANDBOX, FIXTURE, hooks_with(**override)) == [message], override
        unexcepted = {**site, "write": {k: v for k, v in site["write"].items() if k != "shared_database_exception"}}
        assert gate(unexcepted, SANDBOX, FIXTURE, HOOKS) == [
            "the deployment writes to the production database and site.json records no exception"]
    clerk = {**SITE, "write": {**SITE["write"], "auth": "clerk"}}
    assert gate(clerk, SANDBOX, FIXTURE, hooks_with(auth__kind="clerk", auth__key="pk_live_abc")) == [
        "Clerk is not the development instance (no pk_test_ key)"]
    assert "Clerk is not the development instance (no pk_test_ key)" in gate(
        SITE, SANDBOX, FIXTURE, hooks_with(auth__kind="clerk", auth__key="pk_live_abc"))
    for value in ["paypal", None, "", "Stripe"]:
        site = {**SITE, "write": {**SITE["write"], "payment": value}}
        assert gate(site, SANDBOX, FIXTURE, HOOKS) == [f"payment provider {value} is not supported (stripe only)"]
    assert gate(SITE, SANDBOX, FIXTURE, None) == ["hooks.py must define preflight and created for write mode"]
    assert gate(LEAD_SITE, SANDBOX, FIXTURE, None) == ["hooks.py must define preflight and created for write mode"]
    for name in ["site.json", "hooks.py"]:
        shutil.copy(FIXTURE / name, tmp_path / name)
    assert gate(SITE, SANDBOX, tmp_path, HOOKS) == ["cleanup.py is missing"]
    none = attesting({"auth": {"kind": "none"}, "database": {"production": False}})
    assert gate(LEAD_SITE, SANDBOX, tmp_path, none) == ["cleanup.py is missing"]
    (tmp_path / "cleanup.py").write_text("import sys; sys.exit('Refused: not logged in')")
    assert gate(LEAD_SITE, SANDBOX, tmp_path, none) == [
        "cleanup.py dry run on an empty record failed: Refused: not logged in"]
    # The order holds: each check refuses before the ones after it are asked.
    unsupported = {**LEAD_SITE, "write": {**LEAD_SITE["write"], "payment": "paypal"}}
    assert gate(unsupported, ORIGIN, FIXTURE, None) == [f"--write walks only {SANDBOX}"]
    assert gate(unsupported, SANDBOX, FIXTURE, None) == ["payment provider paypal is not supported (stripe only)"]
    assert gate(LEAD_SITE, SANDBOX, tmp_path, attesting({"auth": {"kind": "clerk"}})) == [
        "Clerk is not the development instance (no pk_test_ key)", "auth kind clerk is not none"]


def test_gate_dry_run_still_hands_cleanup_the_same_empty_record(tmp_path):
    for name in ["site.json", "hooks.py"]:
        shutil.copy(FIXTURE / name, tmp_path / name)
    (tmp_path / "cleanup.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "record = json.loads(Path(sys.argv[1], 'created.json').read_text())\n"
        "sys.exit(0 if record == {'accounts': {}, 'users': {}, 'orders': {}} else 'got ' + repr(record))\n")
    none = attesting({"auth": {"kind": "none"}, "database": {"production": False}})
    assert gate(LEAD_SITE, SANDBOX, tmp_path, none) == []


RUN = "20260923T000000Z-ab12"


def address(letter):
    return SITE["write"]["email_format"].format(run=run_token(RUN), name=letter)


def rows_hooks(tmp_path, *batches):
    """hooks.created answers each call with the next batch of rows, then repeats the last."""
    (tmp_path / "hooks.py").write_text("BATCHES = []\ndef created(addresses, site):\n"
                                       "    return BATCHES.pop(0) if len(BATCHES) > 1 else BATCHES[0]\n")
    hooks = load_hooks(tmp_path)
    hooks.BATCHES = list(batches)
    return hooks


def test_created_kinds_go_under_their_plural_keys(tmp_path):
    a, b = address("a"), address("b")
    hooks = rows_hooks(tmp_path, [
        {"kind": "user", "id": "u1", "email": a, "status": None},
        {"kind": "order", "id": "o1", "email": a, "status": "paid"},
        {"kind": "lead", "id": "l1", "email": a},
        {"kind": "lead", "id": "l2", "email": b},
        {"kind": "booking", "id": "bk1", "email": b, "status": "confirmed"},
        {"kind": "waitlist_entry2", "id": "w1", "email": b}])
    path = tmp_path / "created.json"
    record_created(path, {"a": a, "b": b}, hooks, SITE)
    assert json.loads(path.read_text()) == {
        "accounts": {"a": a, "b": b}, "users": {"u1": "a"}, "orders": {"o1": "a"}, "leads": {"l1": "a", "l2": "b"},
        "bookings": {"bk1": "b"}, "waitlist_entry2s": {"w1": "b"}}


def test_created_kinds_refuses_a_row_it_cannot_record(tmp_path):
    a = address("a")
    good = {"kind": "lead", "id": "l1", "email": a}
    for row, message in [
            ({"id": "l9", "email": a}, "hooks.created returned a row without kind"),
            ({"kind": "lead", "email": a}, "hooks.created returned a row without id"),
            ({"kind": "lead", "id": "l9"}, "hooks.created returned a row without email"),
            ({"kind": "lead", "id": "", "email": a}, "hooks.created returned a row without id"),
            ({"kind": "Lead", "id": "l9", "email": a}, "hooks.created returned kind 'Lead'"),
            ({"kind": "lead-form", "id": "l9", "email": a}, "hooks.created returned kind 'lead-form'"),
            ({"kind": "9lead", "id": "l9", "email": a}, "hooks.created returned kind '9lead'"),
            ({"kind": "account", "id": "l9", "email": a}, "hooks.created returned kind 'account'"),
            ({"kind": "lead", "id": "l9", "email": "someone@example.com"},
             "hooks.created returned a row for someone@example.com, which is not one of this run's addresses")]:
        path = tmp_path / "created.json"
        path.unlink(missing_ok=True)
        with pytest.raises(ValueError) as caught:
            record_created(path, {"a": a}, rows_hooks(tmp_path, [good, row]), SITE)
        assert message in str(caught.value), row
        # The rows that could be recorded are, so cleanup still sees them.
        assert json.loads(path.read_text()) == {"accounts": {"a": a}, "users": {}, "orders": {}, "leads": {"l1": "a"}}


class CapturingPool:
    """Runs no browser: records the journey each walk was given, after its placeholders were filled."""
    def __init__(self):
        self.journeys = []

    def submit(self, fn, site, site_dir, origin, journey, out_dir, write):
        self.journeys.append(journey)
        return types.SimpleNamespace(result=lambda: {"id": journey["id"], "result": "pass", "reason": "pass",
                                                     "jev_usd": 0.0, "final_url": origin + "/done"})


def test_created_kinds_fill_placeholders_first_seen_and_orders_paid_first(tmp_path, monkeypatch):
    import walk
    a = address("a")
    first = [{"kind": "order", "id": "o1", "email": a, "status": "open"},
             {"kind": "lead", "id": "l1", "email": a},
             {"kind": "booking", "id": "bk1", "email": a, "status": "held"}]
    later = [{"kind": "booking", "id": "bk2", "email": a, "status": "confirmed"},
             {"kind": "lead", "id": "l2", "email": a}, {"kind": "user", "id": "u1", "email": a, "status": None},
             {"kind": "order", "id": "o1", "email": a, "status": "open"},
             {"kind": "order", "id": "o2", "email": a, "status": "paid"}] + first[1:]
    hooks = rows_hooks(tmp_path, [], first, later)
    monkeypatch.setattr(walk, "load_hooks", lambda site_dir: hooks)
    goals = [journey("inquire-a", goal="Send an inquiry as {email_a}."), journey("book-a"),
             journey("check-a", start="/o/{order_id_a}/l/{lead_id_a}/b/{booking_id_a}/u/{user_id_a}")]
    pool = CapturingPool()
    records = run_write(pool, LEAD_SITE, str(tmp_path), SANDBOX, goals, str(tmp_path / "out"), RUN, lambda: 0.0, [])
    assert [(r["id"], r["result"]) for r in records] == [("inquire-a", "pass"), ("book-a", "pass"), ("check-a", "pass")]
    assert pool.journeys[0]["goal"] == f"Send an inquiry as {a}."
    assert pool.journeys[2]["start"] == "/o/o2/l/l1/b/bk1/u/u1"
    assert json.loads((tmp_path / "out" / "created.json").read_text()) == {
        "accounts": {"a": a}, "users": {"u1": "a"}, "orders": {"o1": "a", "o2": "a"},
        "leads": {"l1": "a", "l2": "a"}, "bookings": {"bk1": "a", "bk2": "a"}}


def test_created_kinds_an_unrecordable_row_stops_the_run(tmp_path, monkeypatch, capsys):
    import walk
    a = address("a")
    hooks = rows_hooks(tmp_path, [], [{"kind": "lead", "id": "l1", "email": a},
                                      {"kind": "lead", "id": "l2", "email": "stranger@example.com"}])
    monkeypatch.setattr(walk, "load_hooks", lambda site_dir: hooks)
    goals = [journey("inquire-a", goal="Send an inquiry as {email_a}."), journey("second"), journey("third")]
    pool = CapturingPool()
    records = run_write(pool, LEAD_SITE, str(tmp_path), SANDBOX, goals, str(tmp_path / "out"), RUN, lambda: 0.0, [])
    assert [j["id"] for j in pool.journeys] == ["inquire-a"], "nothing is walked after the stop"
    assert records[0]["id"] == "inquire-a" and records[0]["result"] == "pass"
    out = capsys.readouterr().out
    assert ("Stopped: hooks.created returned a row for stranger@example.com, which is not one of this run's "
            "addresses") in out
    # The journeys the stop left unwalked are reported as skips, so the run cannot exit 0.
    assert [(r["id"], r["result"]) for r in records[1:]] == [("second", "skip"), ("third", "skip")]
    assert incomplete(records) == records[1:]
    assert json.loads((tmp_path / "out" / "created.json").read_text()) == {
        "accounts": {"a": a}, "users": {}, "orders": {}, "leads": {"l1": "a"}}
    # A bad row before the first journey stops the run before anything is walked.
    hooks.BATCHES = [[{"kind": "account", "id": "x", "email": a}]]
    pool = CapturingPool()
    records = run_write(pool, LEAD_SITE, str(tmp_path), SANDBOX, goals, str(tmp_path / "out2"), RUN, lambda: 0.0, [])
    assert pool.journeys == [] and [r["result"] for r in records] == ["skip", "skip", "skip"]
    assert "Stopped: hooks.created returned kind 'account'" in capsys.readouterr().out
    assert json.loads((tmp_path / "out2" / "created.json").read_text()) == {
        "accounts": {"a": a}, "users": {}, "orders": {}}


# Codex review of milestone 1 (2026-09-23): F-01 a malformed deployment crossed the hook boundary, F-02 the
# new options took extra or missing values, F-03 nothing read the run.json a run actually writes.

def test_build_with_a_malformed_deployment_is_no_build():
    for deployment in [7, True, ["dpl"], float("nan"), object()]:
        assert built(types.SimpleNamespace(build=lambda o, s, d=deployment: {"commit": "a1b2c3d4", "deployment": d}),
                     SANDBOX, SITE) is None, deployment
    assert built(types.SimpleNamespace(build=lambda o, s: {"commit": "a1b2c3d4"}), SANDBOX, SITE) == {
        "commit": "a1b2c3d4", "deployment": None}


def test_expect_commit_and_site_take_exactly_one_value(tmp_path):
    folder = site_folder(tmp_path, "def build(origin, site):\n    _log('build')\n"
                                   "    return {'commit': 'a1b2c3d4e5', 'deployment': None}\n"
                                   "def production_probe(site):\n    _log('production_probe')\n    return []\n")
    key = {"TYPESAFE_API_KEY": "unused"}
    for extra in [["--expect-commit", "a1b2c3d", "deadbee"], ["--expect-commit", "a1b2c3d", "--expect-commit", "deadbee"]]:
        run = cli(SANDBOX, "--write", "--site", str(folder), *extra, env=key)
        assert run.returncode != 0 and "--expect-commit" in run.stdout + run.stderr, extra
    for mode in ["--probe", "--cells"]:
        assert cli(mode, "--site").returncode == 2
        assert cli(mode, "--site", str(folder), "--site", str(folder)).returncode == 2
    assert calls(folder) == [] and not (folder / "runs").exists()


def test_the_build_is_written_to_run_json_and_the_summary(tmp_path):
    key = {"TYPESAFE_API_KEY": "unused"}
    folder = site_folder(tmp_path, "def build(origin, site):\n    return {'commit': 'a1b2c3d4e5', 'deployment': 'dpl_9'}\n")
    (folder / "goals.json").write_text("[]")
    run = cli(ORIGIN, "--site", str(folder), "--out", str(tmp_path / "out"), env=key)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads((tmp_path / "out" / "run.json").read_text())["build"] == {"commit": "a1b2c3d4e5", "deployment": "dpl_9"}
    assert "Build walked: a1b2c3d4e5 (dpl_9)" in (tmp_path / "out" / "summary.md").read_text()
    (folder / "hooks.py").write_text("def harmless(event):\n    return False\n")
    run = cli(ORIGIN, "--site", str(folder), "--out", str(tmp_path / "out2"), env=key)
    assert json.loads((tmp_path / "out2" / "run.json").read_text())["build"] is None
    assert "Build walked: unknown" in (tmp_path / "out2" / "summary.md").read_text()


# Codex review of milestone 2 (2026-09-23): F-01 malformed model shapes threw, F-02 --cells counted a string tag
# as walked, F-03 the seeds check could be skipped, F-04 the model was missing from run.json.

def test_cells_validate_reports_every_malformed_model_shape_as_a_problem(tmp_path):
    region = MODEL["regions"][0]
    for broken, problem in [
            ({**MODEL, "events": ["checkout_completed"]}, "model events[0] needs an id"),
            ({**MODEL, "regions": ["payment"]}, "model regions[0] needs an id, states and transitions as lists"),
            ({**MODEL, "regions": [{**region, "states": ["visitor"]}]}, "model regions[0] states[0] needs an id"),
            ({**MODEL, "regions": [{**region, "transitions": ["checkout_completed"]}]},
             "model regions[0] transitions[0] needs from, event and to"),
            ({**MODEL, "decisions": ["absent"]}, "model decisions[0] needs region, state and event"),
            ({**MODEL, "decisions": [{"region": "payment", "state": "paid", "event": 3, "absent": {}}]},
             "model decisions[0] needs region, state and event")]:
        assert load_model(tmp_path, model_site(tmp_path, broken))["problems"] == [problem], problem
    assert load_model(tmp_path, {**SITE, "model": str(tmp_path / "model.json")})["problems"] == [
        "site.json model must be a path relative to the site folder"]
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "flow.state-gap.json").write_text(json.dumps(MODEL))
    (tmp_path / "ops").mkdir()
    # A project keeps its model beside the plan, outside ops/journeys, so a relative path may climb out.
    assert load_model(tmp_path / "ops", {**SITE, "model": "../plans/flow.state-gap.json"})["candidates"] == CANDIDATES


def test_cells_cli_refuses_malformed_goal_tags_rather_than_counting_them(tmp_path):
    folder = site_folder(tmp_path, "")
    (folder / "model.json").write_text(json.dumps(MODEL))
    site = json.loads((folder / "site.json").read_text())
    (folder / "site.json").write_text(json.dumps({**site, "model": "model.json"}))
    goals = json.loads((folder / "goals-write.json").read_text())
    for tag in ["xxpayment.paid.disputexx", None, {"payment.paid.dispute": 1}, ["payment.paid.dispute", 3],
                ["payment.paid.nothing"]]:
        (folder / "goals-write.json").write_text(json.dumps([{**goals[0], "cells": tag}]))
        run = cli("--cells", "--site", str(folder))
        assert run.returncode == 2 and "walked " not in run.stdout, tag
    (folder / "goals-write.json").write_text("[{")
    assert cli("--cells", "--site", str(folder)).returncode == 2


def test_the_model_is_part_of_run_provenance(tmp_path):
    key = {"TYPESAFE_API_KEY": "unused"}
    folder = site_folder(tmp_path, "")
    (folder / "goals.json").write_text("[]")
    first = cli(ORIGIN, "--site", str(folder), "--out", str(tmp_path / "a"), env=key)
    assert first.returncode == 0, first.stdout + first.stderr
    assert json.loads((tmp_path / "a" / "run.json").read_text())["inputs"]["model"] is None
    (folder / "model.json").write_text(json.dumps(MODEL))
    site = json.loads((folder / "site.json").read_text())
    (folder / "site.json").write_text(json.dumps({**site, "model": "model.json"}))
    cli(ORIGIN, "--site", str(folder), "--out", str(tmp_path / "b"), env=key)
    (folder / "model.json").write_text(json.dumps({**MODEL, "decisions": []}))
    cli(ORIGIN, "--site", str(folder), "--out", str(tmp_path / "c"), env=key)
    b, c = (json.loads((tmp_path / x / "run.json").read_text())["inputs"]["model"] for x in "bc")
    assert b and c and b != c


def test_a_model_field_that_is_not_a_path_is_refused_not_ignored(tmp_path):
    # Codex verification of milestone 2: 0, false, [] and "" read as no model.
    for value in [0, False, [], "", 3]:
        assert load_model(tmp_path, {**SITE, "model": value})["problems"] == [
            "site.json model must be a path relative to the site folder"], value
    assert load_model(tmp_path, {**SITE, "model": None}) is None
    assert load_model(tmp_path, SITE) is None


def test_run_json_names_the_model_path_beside_its_hash(tmp_path):
    folder = site_folder(tmp_path, "")
    (folder / "goals.json").write_text("[]")
    (folder / "model.json").write_text(json.dumps(MODEL))
    site = json.loads((folder / "site.json").read_text())
    (folder / "site.json").write_text(json.dumps({**site, "model": "model.json"}))
    cli(ORIGIN, "--site", str(folder), "--out", str(tmp_path / "a"), env={"TYPESAFE_API_KEY": "unused"})
    inputs = json.loads((tmp_path / "a" / "run.json").read_text())["inputs"]
    assert inputs["model_path"] == "model.json" and len(inputs["model"]) == 64


# Codex review of milestone 3 (2026-09-23): F-01 a mail hook could pass a message to someone else or dated in
# the future, F-02 null mail, a boolean within and a missing hooks.mail validated, F-03 a raising mail hook
# ended the run, F-04 a do hook that created a row and then raised left the row out of created.json.

def test_mail_check_accepts_only_a_message_to_the_address_dated_now_or_before(tmp_path):
    clock = {"t": 1000.0}
    sleep = lambda seconds: clock.__setitem__("t", clock["t"] + seconds)
    spec = {"to": "a", "subject": "refund", "within": 4}
    mine = {**MESSAGE, "to": "a@x"}
    box = lambda *m: types.SimpleNamespace(mail=lambda address, since, site: list(m))
    assert mailed(spec, "a@x", 999.0, box(mine), SITE, sleep, lambda: clock["t"]) == MESSAGE["subject"]
    assert mailed(spec, "A@X", 999.0, box(mine), SITE, sleep, lambda: clock["t"]) == MESSAGE["subject"]
    assert mailed(spec, "a@x", 999.0, box({**mine, "to": "b@x"}), SITE, sleep, lambda: clock["t"]) is None
    for bad in [{k: v for k, v in mine.items() if k != "to"}, {**mine, "received": float("nan")},
                {**mine, "received": float("inf")}, {**mine, "received": True}, {**mine, "received": 10 ** 12}]:
        clock["t"] = 1000.0
        with pytest.raises(ValueError, match="hooks.mail"):
            mailed(spec, "a@x", 999.0, box(bad), SITE, sleep, lambda: clock["t"])


def test_mail_check_validation_refuses_null_a_boolean_within_and_a_missing_hook():
    mailbox = types.SimpleNamespace(mail=lambda address, since, site: [], created=HOOKS.created)
    assert validate([journey("a", mail=None)], SITE, write=True, hooks=mailbox) == [
        "goal a: mail needs to, an account letter"]
    assert validate([journey("a", mail={"to": "a", "within": True})], SITE, write=True, hooks=mailbox) == [
        "goal a: mail within must be 1 to 600 seconds"]
    assert validate([journey("a", mail={"to": "a"})], SITE, write=True, hooks=HOOKS) == [
        "goal a: mail needs a mail(address, since, site) function in hooks.py"]
    assert validate([journey("a", mail={"to": "a"})], SITE, write=True, hooks=mailbox) == []


def test_mail_check_hook_that_raises_is_an_error_record_and_the_run_goes_on(tmp_path):
    folder = hooks_folder(tmp_path, "def mail(address, since, site):\n    raise RuntimeError('mailbox offline')\n")
    goals = [journey("refund-a", mail={"to": "a"}), journey("after-refund", after="refund-a"), journey("independent")]
    records = run_write(LoggingPool([]), SITE, str(folder), SANDBOX, goals, str(tmp_path / "out"),
                        "20260923T000000Z-ab12", lambda: 0.0, [])
    assert [(r["id"], r["result"]) for r in records] == [("refund-a", "error"), ("after-refund", "skip"),
                                                         ("independent", "pass")]
    assert records[0]["reason"] == "hooks.mail failed: RuntimeError: mailbox offline"


def test_do_step_that_raises_after_creating_a_row_still_records_the_row(tmp_path):
    folder = hooks_folder(tmp_path, "MADE = []\n"
                                    "def created(addresses, site):\n"
                                    "    return [{'kind': 'lead', 'id': 'L-1', 'email': addresses[0], 'status': None}] if MADE else []\n"
                                    "def ask(args, site):\n    MADE.append(1)\n    raise RuntimeError('timeout after insert')\n")
    goals = [journey("ask-a", start="/?who={email_a}", do=[{"hook": "ask"}])]
    records = run_write(LoggingPool([]), SITE, str(folder), SANDBOX, goals, str(tmp_path / "out"),
                        "20260923T000000Z-ab12", lambda: 0.0, [])
    assert records[0]["result"] == "skip"
    assert json.loads((tmp_path / "out" / "created.json").read_text())["leads"] == {"L-1": "a"}


# Codex review of milestone 4 (2026-09-23): F-01 a Stripe host written with a terminal dot slipped past the
# payment check, F-02 the attestation passed a production flag of 0, None or a missing payment account, F-03
# a row id of 1 and one of "1" collided in created.json, F-04 an order row without status raised KeyError.

def test_no_payment_blocks_a_stripe_host_written_with_a_terminal_dot():
    site = {**SITE, "allow": SITE["allow"] + [{"origin": o} for o in [
                "https://js.stripe.com", "https://js.stripe.com.", "https://m.stripe.network.",
                "https://q.stripecdn.com."]],
            "write": {**NO_PAYMENT, "api_allow": NO_PAYMENT["api_allow"] + [
                {"method": "POST", "origin": o, "path_pattern": "^/v1/"}
                for o in ["https://api.stripe.com", "https://api.stripe.com."]]}}
    for method, url, navigation in [
            ("POST", "https://api.stripe.com./v1/x", False),
            ("POST", "https://API.Stripe.COM./v1/x", False),
            ("GET", "https://checkout.stripe.com./c/pay/cs_test_1", True),
            ("GET", "https://js.stripe.com./v3/", False),
            ("GET", "https://m.stripe.network./inner.html", False),
            ("GET", "https://q.stripecdn.com./x.js", False),
            ("GET", "https://stripe.com./", True)]:
        assert handling(site, method, url, SANDBOX, navigation, write=True) == "block", url


def test_no_payment_or_payment_a_host_with_a_terminal_dot_is_judged_as_the_host():
    cases = [("GET", SANDBOX + "/houston/", True), ("POST", SANDBOX + "/api/intake/?action=signup", False),
             ("POST", SANDBOX + "/api/intake/?action=helper-turn", False), ("POST", SANDBOX + "/api/newsletter", False),
             ("GET", "https://example.com/privacy/", True), ("GET", "https://www.example.com/terms/", False),
             ("POST", "https://example.com/api/intake/?action=checkout", False),
             ("GET", CLERK + "/v1/environment", False), ("POST", CLERK + "/v1/client/sessions", False),
             ("POST", "https://api.stripe.com/v1/x", False), ("GET", "https://checkout.stripe.com/c/pay/cs_test_1", True)]
    for site in [SITE, {**SITE, "write": NO_PAYMENT}]:
        for write in [False, True]:
            for method, url, navigation in cases:
                netloc = url.split("/")[2]
                dotted = url.replace(netloc, netloc + ".", 1)
                assert handling(site, method, dotted, SANDBOX, navigation, write) == handling(
                    site, method, url, SANDBOX, navigation, write), (dotted, write)
    # A live host with a dot is still read from the build and never written to; the sandbox with a dot
    # still takes only the exact write requests, and none at all in a read walk.
    assert handling(SITE, "GET", "https://example.com./privacy/", SANDBOX, True, write=True) == "rewrite"
    assert handling(SITE, "POST", "https://example.com./api/intake/?action=checkout", SANDBOX, False, write=True) == "block"
    assert handling(SITE, "POST", SANDBOX + "./api/intake/?action=helper-turn", SANDBOX, False, write=True) == "block"
    assert handling(SITE, "POST", SANDBOX + "./api/intake/?action=signup", SANDBOX, False) == "block"
    assert handling(SITE, "GET", "https://example-sandbox.vercel.app.evil.test./", SANDBOX, True, write=True) == "block"


def test_gate_counts_only_false_as_not_production():
    site = {**SITE, "write": {k: v for k, v in SITE["write"].items() if k != "shared_database_exception"}}
    refused = ["the deployment writes to the production database and site.json records no exception"]
    for value in [0, 0.0, "", "false", [], {}, None, True]:
        assert gate(site, SANDBOX, FIXTURE, hooks_with(database__production=value)) == refused, value
    attestation = HOOKS.preflight(SANDBOX, SITE)
    assert gate(site, SANDBOX, FIXTURE, attesting({**attestation, "database": {}})) == refused
    assert gate(site, SANDBOX, FIXTURE, attesting({k: v for k, v in attestation.items() if k != "database"})) == refused
    assert gate(site, SANDBOX, FIXTURE, hooks_with(database__production=False)) == []
    # A recorded exception still admits the production database, whatever the flag says.
    for value in [0, None, True]:
        assert gate(SITE, SANDBOX, FIXTURE, hooks_with(database__production=value)) == [], value


def test_gate_refuses_a_payment_account_or_livemode_that_is_not_exact():
    unset = ["site.json write.payment_account is not a non-empty string"]
    for account in [None, "", 0, ["acct_test"]]:
        site = {**SITE, "write": {**SITE["write"], "payment_account": account}}
        assert gate(site, SANDBOX, FIXTURE, hooks_with(payment__account=account)) == unset, account
    omitted = {**SITE, "write": {k: v for k, v in SITE["write"].items() if k != "payment_account"}}
    assert gate(omitted, SANDBOX, FIXTURE, hooks_with(payment__account=None)) == unset
    assert gate(omitted, SANDBOX, FIXTURE, HOOKS) == unset
    attestation = HOOKS.preflight(SANDBOX, SITE)
    unattested = {**attestation, "payment": {k: v for k, v in attestation["payment"].items() if k != "account"}}
    assert gate(SITE, SANDBOX, FIXTURE, attesting(unattested)) == ["payment account None is not acct_test"]
    for value in [0, 0.0, None, "", "false", []]:
        assert gate(SITE, SANDBOX, FIXTURE, hooks_with(payment__livemode=value)) == [
            "payment livemode is not false"], value
    assert gate(SITE, SANDBOX, FIXTURE, HOOKS) == []


def test_created_kinds_refuses_an_id_or_email_that_is_not_a_string(tmp_path):
    a = address("a")
    bad = [{"kind": "lead", "id": 1, "email": a}, {"kind": "lead", "id": True, "email": a},
           {"kind": "lead", "id": 1.5, "email": a}, {"kind": "lead", "id": ["l3"], "email": a},
           {"kind": "lead", "id": {"x": 1}, "email": a}, {"kind": "lead", "id": "l4", "email": [a]},
           {"kind": "lead", "id": "l5", "email": {a: 1}}, {"kind": "lead", "id": "l6", "email": 7}]
    rows = [{"kind": "lead", "id": "1", "email": a}] + bad + [{"kind": "order", "id": "o1", "email": a, "status": "paid"}]
    path = tmp_path / "created.json"
    with pytest.raises(ValueError) as caught:
        record_created(path, {"a": a}, rows_hooks(tmp_path, rows), SITE)
    assert str(caught.value) == "; ".join(
        f"hooks.created returned a row whose id or email is not a string: {row!r}" for row in bad)
    # Every valid row is recorded, and the string id "1" is the only row under that key.
    assert json.loads(path.read_text()) == {
        "accounts": {"a": a}, "users": {}, "orders": {"o1": "a"}, "leads": {"1": "a"}}


def test_created_kinds_an_order_without_status_keeps_the_first_order_id(tmp_path, monkeypatch):
    import walk
    a = address("a")
    hooks = rows_hooks(tmp_path, [], [{"kind": "order", "id": "o1", "email": a}],
                       [{"kind": "order", "id": "o1", "email": a}, {"kind": "order", "id": "o2", "email": a}])
    monkeypatch.setattr(walk, "load_hooks", lambda site_dir: hooks)
    goals = [journey("order-a", goal="Order as {email_a}."), journey("again-a"),
             journey("check-a", start="/o/{order_id_a}")]
    pool = CapturingPool()
    records = run_write(pool, LEAD_SITE, str(tmp_path), SANDBOX, goals, str(tmp_path / "out"), RUN, lambda: 0.0, [])
    assert [(r["id"], r["result"]) for r in records] == [("order-a", "pass"), ("again-a", "pass"), ("check-a", "pass")]
    assert pool.journeys[2]["start"] == "/o/o1"
    assert json.loads((tmp_path / "out" / "created.json").read_text()) == {
        "accounts": {"a": a}, "users": {}, "orders": {"o1": "a", "o2": "a"}}


# Codex verification of milestone 4 (2026-09-23): a preflight answer of the wrong shape is refused, never raised.


@pytest.mark.parametrize("value", [["x"], "x", 7, None])
def test_gate_refuses_an_attestation_section_that_is_not_an_object(value):
    assert attested(SITE, value) == ["the preflight attestation is not an object"]
    assert gate(SITE, SANDBOX, FIXTURE, attesting(value)) == ["the preflight attestation is not an object"]
    no_exception = {**SITE, "write": {k: v for k, v in SITE["write"].items() if k != "shared_database_exception"}}
    production = "the deployment writes to the production database and site.json records no exception"
    # A section of the wrong shape is refused and then read as missing, so the other checks still run.
    cases = [(SITE, "payment", ["the preflight payment is not an object", "payment provider None is not stripe",
                                "payment livemode is not false", "payment account None is not acct_test"]),
             (SITE, "database", ["the preflight database is not an object"]),
             (no_exception, "database", ["the preflight database is not an object", production]),
             (SITE, "auth", ["the preflight auth is not an object", "unknown auth kind None"])]
    for site, section, refused in cases:
        attestation = {**HOOKS.preflight(SANDBOX, site), section: value}
        assert attested(site, attestation) == refused, section
        assert gate(site, SANDBOX, FIXTURE, attesting(attestation)) == refused, section
