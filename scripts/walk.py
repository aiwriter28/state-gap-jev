# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "jev-ultrafast @ git+https://github.com/browser-use/jev-ultrafast@1231850a0bf1a0c0341fe408ef1668dbbfdfac46",
#   "playwright==1.63.0",
# ]
# ///
"""Walk customer journeys against a deployment with TypeSafe's Jev choosing each step.

Built on browser-use/jev-ultrafast (MIT): Jev picks an operation and an element from a numbered
table of the page's visible controls, and code performs it. This runner swaps upstream's shared
Chrome for isolated headless Chromium, one process per journey, and lets the site be read but
never written to: only GETs to the deployment origin and the hosts site.json allows reach the
network. Third-party scripts and beacons get an empty success; every write and every navigation off
the site is aborted and logged. A walk cannot sign in, pay, subscribe or email.

Each journey stops as soon as its pass check holds. Anything else is a fail with a reason
(done, blocked, loop, budget, unstable, needs_text) for a person or Claude to verify from the
saved frames.

--write walks goals-write.json on the site's sandbox origin only, after the gate passes: it signs
up, signs in and pays with test cards where the site has them, so the site's own write endpoints
named in site.json and the payment provider are let through too. Journeys run one at a time, a journey
can continue from another's cookies (after), and every row the run creates (accounts, orders, leads,
bookings) is recorded in created.json for the site's cleanup.py.

Everything a site needs is in its folder (ops/journeys/ at the git root, or --site DIR): site.json
for the facts, goals.json and goals-write.json for the journeys, hooks.py for the few behaviors the
runner cannot express as data, cleanup.py for write mode. SKILL.md beside this file is the runbook.

usage: uv run walk.py ORIGIN [--write] [--only ID ...] [--out DIR] [--site DIR] [--expect-commit SHA]
       uv run walk.py --probe [--site DIR]
       uv run walk.py --cells [--site DIR]
"""

import hashlib
import json
import math
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from providers import adapt, configure

HERE = Path(__file__).parent
DEFAULTS = {"live_hosts": [], "protection_bypass": False, "allow": [], "avoid": None, "max_actions": 40,
            "budget_usd": 1.0, "viewports": {"desktop": [1280, 800], "phone": [390, 844]}}
REQUIRED = ["name", "live_hosts", "deployment_url_pattern", "steps"]
PAYMENT_HOSTS = {"stripe": ("stripe.com", "stripe.network", "stripecdn.com")}  # the only provider supported
PASS_KEYS = {"text", "on", "url", "blocked", "api", "any"}
# state-gap adds these events to every model (SEEDS in state-gap.mjs), so a goal may tag them; a test keeps
# the two lists equal.
SEEDS = ("refund", "dispute", "chargeback", "unsubscribe_after_purchase", "address_change", "duplicate_purchase",
         "late_or_repeated_webhook")
MAX_REJECTIONS = 2
SCROLL_LABEL = "Scroll down"  # snapshot.js gives the scroll action this label
NOT_YET = ("Not finished: the answer the goal asks for is not visible yet. Keep looking: scroll, "
           "open the menu, open a question, or try another page.")
NOT_YET_WRITE = ("Not finished: the goal is not complete yet. Do its next step on this page: answer what the page "
                 "asks, then scroll to its Continue, Pay or Confirm button and press it.")
COMMIT = r"[0-9a-fA-F]{7,40}"  # what --expect-commit accepts: a full or abbreviated git commit
DATE_TYPES = ["date", "month", "week", "time", "datetime-local"]
# The same visibility test snapshot.js applies, so the settle watches exactly what the snapshot reads.
REVEALED = """[...document.querySelectorAll('body *')].filter(e =>
  e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})).length"""
STRIPE_IDLE = """() => ![...document.querySelectorAll('button[type=submit] *')].some(e =>
  e.children.length === 0 && e.textContent.trim() === 'Processing' &&
  e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}))"""
# The runner's own hooks; a goal's do step may call any other public function in hooks.py.
RUNNER_HOOKS = {"build", "production_probe", "preflight", "created", "verification_link", "harmless", "mail"}
PLACEHOLDER = r"\{(?:(?:email|password|verify_link|[a-z][a-z0-9_]*_id)_(\w+)|last_url)\}"
ROW_KIND = r"[a-z][a-z0-9_]*"  # a created row's kind; its rows go under "<kind>s" in created.json

# Upstream tunes its rules for forms. Customers mostly hunt for information, and only the part of
# the page inside the viewport is sent, so without these the walk clicks around the menu instead.
READING_RULES = """
Only the part of the page inside the viewport is shown. When looking for information, SCROLL_DOWN
through the current page before navigating away if the answer could be further down it.
If a visible question, button or section title matches what you are looking for, CLICK it to open it.
DONE requires the answer itself to be visible; a matching question or heading alone is not enough.
After answering the questions in a form, SCROLL_DOWN to find its result or its continue button.
Never repeat an action from recent_actions whose page_changed is false; choose a different action.
A visible email address, or a link that opens email, counts as a way to contact someone.
Links such as Privacy, Terms, Contact and account or report sign-in are usually in the footer:
SCROLL_DOWN to the bottom of the page to find them before opening the menu again."""


def load_site(site_dir):
    """site.json with defaults filled in. Missing required fields fail before anything runs."""
    site = {**DEFAULTS, **json.loads((Path(site_dir) / "site.json").read_text())}
    missing = [k for k in REQUIRED if k not in site]
    if missing:
        raise ValueError(f"site.json is missing {', '.join(missing)}")
    return site


def load_hooks(site_dir):
    """The site's hooks.py as a module, or None. Its functions are the behaviors data cannot express."""
    path = Path(site_dir) / "hooks.py"
    if not path.exists():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("site_hooks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def retrying(post, sleep=time.sleep):
    """Upstream's model call retries HTTP 429 but raises at once on a transport error; one blip ended
    a twelve-minute write chain. A connection failure is retried twice, a second and then two apart."""
    def call(*args, **kwargs):
        for attempt in range(3):
            try:
                return post(*args, **kwargs)
            except RuntimeError as exc:
                if "connection failed" not in str(exc) or attempt == 2:
                    raise
                sleep(attempt + 1)
    return call


TAP_POINT = """(node => {
  const e = window.__jevFast?.nodes.get(node);
  if (!e?.isConnected) return null;
  const boxes = [...e.getClientRects()];
  if (!boxes.length) return null;
  const within = (x, y) => x >= 0 && y >= 0 && x < innerWidth && y < innerHeight;
  const lands = (x, y) => { const h = document.elementFromPoint(x, y); return !!h && e.contains(h); };
  const r = e.getBoundingClientRect(), cx = r.x + r.width / 2, cy = r.y + r.height / 2;
  if (!r.width || !r.height || !within(cx, cy)) return null;
  if (lands(cx, cy)) return null;  // nothing is in the way: upstream clicks it itself
  // Something stands between the control's centre and the pointer: the element's own line layout
  // where a link wraps, a sticky banner over the lower half of a button, an accordion row over a
  // radio. A person taps a part of the control that is not covered, so look for one.
  for (const b of boxes)
    for (const fy of [0.5, 0.25, 0.75])
      for (const fx of [0.5, 0.25, 0.75]) {
        const x = b.x + b.width * fx, y = b.y + b.height * fy;
        if (within(x, y) && lands(x, y)) return {x, y};
      }
  // No part of it can be reached. Only an interactive overlay stands in for the control (an accordion
  // row over a radio, a label over its box); a banner or a floating button over it is still a covering.
  const hit = document.elementFromPoint(cx, cy);
  if (!hit) return null;
  return hit.closest('button,a,label,[role="button"],[role="radio"],[role="checkbox"],[role="option"],[role="tab"]')
    ? {x: cx, y: cy} : null;
})"""


def tap_point(evaluate, node):
    """Where a person taps a control that sits under a transparent interactive overlay, or None."""
    return evaluate(f"{TAP_POINT}({node})")


def more_below(page):
    """The snapshot offers Scroll down only while the page continues under the fold."""
    return any(a.get("id") == "scroll_down" for a in page.get("actions", []))


def checkout_guard(url_before, url_after, body):
    """Before a click, fill or select on Stripe Checkout the page must show it is test mode. The URL is
    read before the body and again after: a page that left Stripe in between (the redirect after Pay)
    is stale and observed again, never mistaken for live mode."""
    if urlparse(url_before).hostname != "checkout.stripe.com":
        return
    if url_after != url_before:
        raise ValueError("Page changed since this decision. Observe again.")
    if not stripe_test_mode(url_before, body):
        raise NotTestMode(url_before.split("#")[0])
    return


def held(read, sleep, now, seconds=10, every=0.25):
    """Jev chose to wait: hold until the page's text changes, at most `seconds`. True when it changed.
    Upstream sleeps a tenth of a second; a session activating or a partner-status poll takes longer."""
    before, deadline = read(), now() + seconds
    while now() < deadline:
        sleep(every)
        if read() != before:
            return True
    return False


def settled(read, sleep, now, seconds=3.0, every=0.25, quiet=0.5):
    """Hold until the reading has not moved for `quiet`, at most `seconds`, and report what it last
    read. A scroll-reveal animation fades a section in once a scroll brings it into view, and
    `snapshot.js` counts an element at opacity 0 as invisible, so a snapshot taken the instant the
    scroll lands reads most of the page as empty. The reveal pauses before it starts, so two equal
    readings in a row are not yet the page holding still: they are just as likely to be that pause."""
    last, since = None, now()
    deadline = since + seconds
    while now() < deadline:
        reading = read()
        if reading != last:
            last, since = reading, now()
        elif now() - since >= quiet:
            return reading
        sleep(every)
    return last


def recover(page):
    """Chrome leaves its own error page behind when a navigation is blocked, and every walk that
    presses a buy button lands on one. The attempt is already recorded where a `blocked` pass check
    reads it, so a person presses back and carries on with the rest of the journey."""
    if not page.url.startswith("chrome-error://"):
        return False
    page.go_back(wait_until="load")
    return True


def awaited(site, url, origin):
    """A request a person waits for before acting again: the site's own API, and every origin a
    write.api_allow entry names, since an auth provider activates the session on its own host."""
    parts = urlparse(url)
    return url.startswith(origin + "/api/") or f"{parts.scheme}://{parts.netloc}" in {
        r["origin"] for r in (site.get("write") or {}).get("api_allow", []) if "origin" in r}


def handling(site, method, url, origin, navigation, write=False):
    """allow: reaches the network. rewrite: a read of the live domain, sent to the build under
    test instead. stub: an empty success, for third-party scripts and beacons, so blocking them
    cannot throw in site code. block: aborted and logged, for every write and every navigation
    off the site. A write walk also lets through the payment provider's hosts and the exact write
    requests site.json names, on the sandbox origin or on an origin an entry names (an auth
    provider's own API); everything else stays blocked. A write walk on a site with no payment
    blocks every payment host outright, so nothing it does can reach a checkout. The host is judged
    lowercase and without a terminal dot, the form DNS treats as the same host."""
    parts = urlparse(url)
    host = (parts.hostname or "").removesuffix(".")
    netloc = host + (f":{parts.port}" if parts.port else "")
    request_origin = f"{parts.scheme}://{netloc}"
    rules = site.get("write") or {}

    def on(hosts):
        return any(host == h or host.endswith("." + h) for h in hosts)

    if write and parts.scheme == "https" and on(PAYMENT_HOSTS.get(rules.get("payment"), ())):
        return "allow"
    if write and "payment" not in rules and on(h for hosts in PAYMENT_HOSTS.values() for h in hosts):
        return "block"
    if method != "GET":
        def path_matches(rule):
            return bool(re.search(rule["path_pattern"], parts.path)) if "path_pattern" in rule \
                else parts.path.rstrip("/") == rule["path"].rstrip("/")

        return "allow" if write and any(
            request_origin == r.get("origin", origin) and r["method"] == method and path_matches(r)
            and all(parse_qs(parts.query).get(k) in [[v] for v in values] for k, values in r.get("query", {}).items())
            for r in rules.get("api_allow", [])) else "block"
    if request_origin == origin:
        return "allow"
    if any(request_origin == a["origin"] and re.search(a.get("path", ""), parts.path) for a in site["allow"]):
        return "allow"
    if netloc in site["live_hosts"]:
        return "rewrite"
    return "block" if navigation else "stub"


def bypass_headers(url, origin, headers, secret):
    """Vercel Authentication guards deployment URLs; the automation bypass header opens them for the
    walk. Sent only to the deployment origin, never to any other host."""
    if secret and (url.startswith(origin + "/") or url == origin):
        return {**headers, "x-vercel-protection-bypass": secret}
    return headers


class NotTestMode(Exception):
    """Stripe Checkout without its test-mode marker. The run stops before anything is typed there."""


def stripe_test_mode(url, text):
    """Stripe Checkout in test mode: a cs_test_ session and the visible Sandbox or Test mode badge."""
    return "/cs_test_" in url and bool(re.search(r"\b(sandbox|test mode)\b", text, re.IGNORECASE))


def validate(goals, site, model=None, write=False, hooks=None):
    """Why the goals cannot run: every problem, or an empty list. Checked before anything starts."""
    wrong, ids = [], [g.get("id") for g in goals]
    wrong += [f"duplicate id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]

    def compiles(pattern, where):
        try:
            re.compile(pattern)
        except (re.error, TypeError):
            wrong.append(f"{where}: {pattern!r} is not a regex")

    def conditions(spec, where):
        if not isinstance(spec, dict) or not set(spec) & PASS_KEYS - {"on"}:
            wrong.append(f"{where}: the pass check declares no condition (text, url, blocked, api or any)")
            return
        wrong.extend(f"{where}: unknown pass key {k}" for k in spec if k not in PASS_KEYS)
        for p in spec.get("text", []) + [spec[k] for k in ("on", "url", "blocked") if k in spec] + (
                [spec["api"]] if isinstance(spec.get("api"), str) else spec.get("api", [])):
            compiles(p, where)
        if "any" in spec:
            if not spec["any"]:
                wrong.append(f"{where}: any is empty")
            for i, s in enumerate(spec["any"]):
                conditions(s, f"{where} any[{i}]")

    for g in goals:
        where = f"goal {g.get('id')}"
        if not isinstance(g.get("id"), str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", g["id"]) or g["id"] == "retry":
            wrong.append(f"{where}: id must be a safe folder name other than retry")
        for key in ("id", "step", "start", "goal"):
            if not isinstance(g.get(key), str) or not g[key]:
                wrong.append(f"{where}: {key} must be a non-empty string")
        if g.get("step") not in site["steps"]:
            wrong.append(f"{where}: step {g.get('step')} is not in site.json steps")
        if g.get("viewport", "phone") not in site["viewports"]:
            wrong.append(f"{where}: unknown viewport {g.get('viewport')}")
        if "after" in g and g["after"] not in ids:
            wrong.append(f"{where}: after names no journey ({g['after']})")
        if "requires" in g and not (isinstance(g["requires"], list) and all(isinstance(r, str) for r in g["requires"])):
            wrong.append(f"{where}: requires must be a list of journey ids")
        elif "requires" in g:
            wrong += [f"{where}: requires names no journey ({r})" for r in g["requires"] if r not in ids]
        if "cells" in g:
            if not (isinstance(g["cells"], list) and all(isinstance(c, str) for c in g["cells"])):
                wrong.append(f"{where}: cells must be a list of region.state.event")
            elif not model:
                wrong.append(f"{where}: cells need a state-gap model named by site.json model")
            else:
                wrong += [f"{where}: cell {c} is not in the model" for c in g["cells"] if c not in model["cells"]]
        if ("do" in g or "mail" in g) and not write:
            wrong.append(f"{where}: do and mail are write mode only")
        elif write:
            wrong += [f"{where}: {w}" for w in steps_outside(g, hooks, compiles, where)]
        if "known" in g and not isinstance(g["known"], str):
            wrong.append(f"{where}: known must be a string naming the decision")
        if "budget" in g and not isinstance(g["budget"], int):
            wrong.append(f"{where}: budget must be an integer")
        if g.get("avoid") is not None:
            compiles(g["avoid"], where)
        conditions(g.get("pass"), where)
    if site.get("avoid") is not None:
        compiles(site["avoid"], "site.json avoid")
    for i, rule in enumerate((site.get("write") or {}).get("api_allow", [])):
        where = f"site.json write api_allow[{i}]"
        if ("path" in rule) == ("path_pattern" in rule):
            wrong.append(f"{where}: needs exactly one of path and path_pattern")
        elif "path_pattern" in rule:
            compiles(rule["path_pattern"], where)
    return wrong


def steps_outside(goal, hooks, compiles, where):
    """Why a write goal's do and mail cannot run. compiles reports a bad pattern the way validate does."""
    wrong, do = [], goal.get("do", [])
    if not (isinstance(do, list) and all(isinstance(d, dict) and isinstance(d.get("hook"), str) for d in do)):
        return ["do must be a list of {hook, args}"]
    for d in do:
        name = d["hook"]
        if name in RUNNER_HOOKS:
            wrong.append(f"do hook {name} is one of the runner's own hooks")
        elif name.startswith("_") or not callable(getattr(hooks, name, None)):
            wrong.append(f"do hook {name} is not a function in hooks.py")
        if not isinstance(d.get("args", {}), dict):
            wrong.append("do args must be an object")
    if "mail" in goal:
        mail = goal["mail"]
        if not (isinstance(mail, dict) and isinstance(mail.get("to"), str) and re.fullmatch(r"\w+", mail["to"])):
            return wrong + ["mail needs to, an account letter"]
        if not callable(getattr(hooks, "mail", None)):
            wrong.append("mail needs a mail(address, since, site) function in hooks.py")
        within = mail.get("within", 90)
        if not (type(within) is int and 1 <= within <= 600):
            wrong.append("mail within must be 1 to 600 seconds")
        if not (isinstance(mail.get("body", []), list) and all(isinstance(b, str) for b in mail.get("body", []))):
            wrong.append("mail body must be a list of patterns")
        else:
            for pattern in [mail.get("subject", "")] + mail.get("body", []):
                compiles(pattern, where)
    return wrong


def mailed(spec, address, since, hooks, site, sleep=time.sleep, now=time.time):
    """The subject of the first message to address received at or after since whose subject and body
    match every pattern, reading the mailbox until spec's within seconds pass; None when none arrives."""
    deadline = now() + spec.get("within", 90)
    while True:
        messages = hooks.mail(address, since, site)

        def dated(m):  # a real timestamp, allowing five minutes of clock difference with the mail server
            return type(m.get("received")) in (int, float) and math.isfinite(m["received"]) and m["received"] <= now() + 300

        if not (isinstance(messages, list) and all(isinstance(m, dict) and dated(m) and all(
                isinstance(m.get(k), str) for k in ("subject", "body", "to")) for m in messages)):
            raise ValueError("hooks.mail must return a list of {subject, body, to, received} dated no later than now")
        for m in messages:
            if m["to"].lower() == address.lower() and m["received"] >= since and re.search(spec.get("subject", ""), m["subject"], re.IGNORECASE) and all(
                    re.search(b, m["body"], re.IGNORECASE) for b in spec.get("body", [])):
                return m["subject"]
        if now() >= deadline:
            return None
        sleep(min(2, max(0.1, deadline - now())))


def load_model(site_dir, site):
    """The state-gap model site.json names, read only as far as the walker needs it: every cell a goal
    may tag, and the candidates to walk (each wired transition, then each absent decision). None when
    site.json names no model. Checking the model itself is state-gap.mjs's job."""
    if site.get("model") is None:
        return None
    if not isinstance(site["model"], str) or not site["model"] or Path(site["model"]).is_absolute():
        return {"problems": ["site.json model must be a path relative to the site folder"]}
    path = Path(site_dir) / site["model"]
    if not path.exists():
        return {"problems": [f"site.json model {path} does not exist"]}
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return {"problems": [f"site.json model {path} is not JSON: {exc}"]}
    lists = isinstance(raw, dict) and all(isinstance(raw.get(k), list) for k in ("events", "regions", "decisions"))
    if not lists:
        return {"problems": ["model needs events, regions and decisions as lists"]}
    def named(item, *keys):
        return isinstance(item, dict) and all(isinstance(item.get(k), str) and item[k] for k in keys)

    problems = [f"model events[{i}] needs an id" for i, e in enumerate(raw["events"]) if not named(e, "id")]
    for i, r in enumerate(raw["regions"]):
        if not (named(r, "id") and isinstance(r.get("states"), list) and isinstance(r.get("transitions"), list)):
            problems.append(f"model regions[{i}] needs an id, states and transitions as lists")
            continue
        problems += [f"model regions[{i}] states[{j}] needs an id" for j, st in enumerate(r["states"]) if not named(st, "id")]
        problems += [f"model regions[{i}] transitions[{j}] needs from, event and to" for j, t in enumerate(r["transitions"])
                     if not named(t, "from", "event", "to")]
    problems += [f"model decisions[{i}] needs region, state and event" for i, d in enumerate(raw["decisions"])
                 if not named(d, "region", "state", "event")]
    if problems:
        return {"problems": problems}
    seeds = SEEDS
    if "profile" in raw:
        profile = raw["profile"]
        if not isinstance(profile, dict) or not isinstance(profile.get("seeds"), list) or not all(
                named(seed, "id") for seed in profile["seeds"]):
            return {"problems": ["model profile needs seeds as a list of named events"]}
        seeds = [seed["id"] for seed in profile["seeds"]]
    events = [e["id"] for e in raw["events"]] + [e for e in seeds if e not in {e["id"] for e in raw["events"]}]
    regions = [r["id"] for r in raw["regions"]]
    cells = {f"{r['id']}.{s['id']}.{e}" for r in raw["regions"] for s in r["states"] for e in events}
    wired = [f"{r['id']}.{t['from']}.{t['event']}" for r in raw["regions"] for t in r["transitions"]]
    absent = [f"{d['region']}.{d['state']}.{d['event']}" for d in raw["decisions"] if "absent" in d]
    return {"problems": [], "regions": regions, "cells": cells, "candidates": list(dict.fromkeys(wired + absent))}


def attested(site, attestation):
    """Why the preflight attestation does not clear the gate. Checked against site.json's write section.
    A site with no payment has no payment or webhook to attest. write.auth, when present, names the one
    auth kind the attestation must report, and only an explicit "none" admits a site with no sign-in.
    A section of the wrong shape is refused and then read as missing."""
    if not isinstance(attestation, dict):
        return ["the preflight attestation is not an object"]
    rules, sections = site["write"], ("payment", "database", "auth")
    wrong = [f"the preflight {name} is not an object" for name in sections
             if not isinstance(attestation.get(name, {}), dict)]
    payment, database, auth = (v if isinstance(v := attestation.get(name, {}), dict) else {} for name in sections)
    if "payment" in rules:
        if payment.get("provider") != rules.get("payment"):
            wrong.append(f"payment provider {payment.get('provider')} is not {rules.get('payment')}")
        if payment.get("livemode") is not False:
            wrong.append("payment livemode is not false")
        if not (isinstance(rules.get("payment_account"), str) and rules["payment_account"]):
            wrong.append("site.json write.payment_account is not a non-empty string")
        elif payment.get("account") != rules["payment_account"]:
            wrong.append(f"payment account {payment.get('account')} is not {rules['payment_account']}")
        webhook = str(attestation.get("webhook", ""))
        if webhook != rules["sandbox_origin"] and not webhook.startswith(rules["sandbox_origin"] + "/"):
            wrong.append(f"webhook destination {attestation.get('webhook')} is not the sandbox")
    if database.get("production") is not False and not rules.get("shared_database_exception"):
        wrong.append("the deployment writes to the production database and site.json records no exception")
    if auth.get("kind") == "clerk" and not str(auth.get("key", "")).startswith("pk_test_"):
        wrong.append("Clerk is not the development instance (no pk_test_ key)")
    if auth.get("kind") == "supabase" and rules.get("auth_ref") and auth.get("ref") != rules["auth_ref"]:
        wrong.append(f"Supabase auth ref {auth.get('ref')} is not {rules['auth_ref']}")
    if "auth" in rules and auth.get("kind") != rules["auth"]:
        wrong.append(f"auth kind {auth.get('kind')} is not {rules['auth']}")
    elif auth.get("kind") not in {"clerk", "supabase"} | ({"none"} if rules.get("auth") == "none" else set()):
        wrong.append(f"unknown auth kind {auth.get('kind')}")
    return wrong


def gate(site, origin, site_dir, hooks):
    """Why write mode is refused, in the spec's order, or an empty list. Nothing has been mutated yet."""
    rules = site.get("write")
    if not rules:
        return ["site.json has no write section"]
    if origin != rules["sandbox_origin"]:
        return [f"--write walks only {rules['sandbox_origin']}"]
    if "payment" in rules and rules["payment"] not in PAYMENT_HOSTS:
        return [f"payment provider {rules['payment']} is not supported (stripe only)"]
    if hooks is None or not hasattr(hooks, "preflight") or not hasattr(hooks, "created"):
        return ["hooks.py must define preflight and created for write mode"]
    if wrong := attested(site, hooks.preflight(origin, site)):
        return wrong
    cleanup = Path(site_dir) / "cleanup.py"
    if not cleanup.exists():
        return ["cleanup.py is missing"]
    with tempfile.TemporaryDirectory() as empty:
        Path(empty, "created.json").write_text(json.dumps({"accounts": {}, "users": {}, "orders": {}}))
        dry = subprocess.run([sys.executable, str(cleanup), empty], capture_output=True, text=True, check=False, cwd=site_dir)
    if dry.returncode != 0:
        return [f"cleanup.py dry run on an empty record failed: {(dry.stderr or dry.stdout).strip()[-300:]}"]
    return []


def built(hooks, origin, site):
    """The commit and deployment the site's hooks.build reports for the target, or None when there is
    no hook or its answer is not {"commit": str, "deployment": str or None}."""
    answer = hooks.build(origin, site) if hasattr(hooks, "build") else None
    if not (isinstance(answer, dict) and isinstance(answer.get("commit"), str) and answer["commit"]
            and isinstance(answer.get("deployment"), (str, type(None)))):
        return None
    return {"commit": answer["commit"], "deployment": answer.get("deployment")}


def stale(build, expect):
    """Why --expect-commit refuses the run, or None when the target is that commit (a prefix of it)."""
    if not re.fullmatch(COMMIT, expect or ""):
        return f"--expect-commit takes one commit of 7 to 40 hex characters, not {expect!r}"
    if not build:
        return "hooks.build reported no build for the target"
    if not build["commit"].lower().startswith(expect.lower()):
        return f"the target is build {build['commit']}, not {expect}"
    return None


def one(args, name):
    """The one value given after name, or None when name is absent, repeated, or has no value or several."""
    values = option(args, name)
    return values[0] if args.count(name) == 1 and len(values) == 1 else None


def site_only(args):
    """A mode that takes nothing but --site DIR: no origin, --write or --only."""
    site_arg = ["--site", one(args, "--site")] if "--site" in args else []
    if args[1:] != site_arg:
        print(f"usage: walk.py {args[0]} [--site DIR]  (no origin, --write or --only)")
        return False
    return True


def probe(args):
    """--probe [--site DIR]: the site's read-only production checks. Exit 1 when a problem is reported,
    2 when the probe cannot run. No origin, no Jev key and no browser: it reads, and prints what it found."""
    if not site_only(args):
        return 2
    site_dir = site_folder(args)
    hooks = load_hooks(site_dir)
    if not hasattr(hooks, "production_probe"):
        print(f"hooks.py in {site_dir} defines no production_probe(site). Nothing was checked.")
        return 2
    try:
        problems = hooks.production_probe(load_site(site_dir))
    except Exception as exc:  # noqa: BLE001 - isolate failures in project-owned hooks
        # The probe could not read what it checks: not a finding, and not a pass
        print(f"The probe could not run: {type(exc).__name__}: {exc}"[:400])
        return 2
    if not (isinstance(problems, list) and all(isinstance(p, str) for p in problems)):
        print("production_probe must return a list of strings, one per problem.")
        return 2
    print("\n".join(f"- {p}" for p in problems) if problems else "Production probe: no problems.")
    return 1 if problems else 0


def cells(args):
    """--cells [--site DIR]: every candidate cell of the site's state-gap model by region, and the goals in
    goals.json and goals-write.json that tag it. No origin, no Jev key, no browser."""
    if not site_only(args):
        return 2
    site_dir = site_folder(args)
    site = load_site(site_dir)
    model = load_model(site_dir, site)
    if not model or model["problems"]:
        print("site.json names no readable state-gap model:\n- " + "\n- ".join((model or {}).get("problems")
                                                                               or ["no model field"]))
        return 2
    goals, wrong, hooks = [], [], load_hooks(site_dir)
    for name, write in (("goals.json", False), ("goals-write.json", True)):
        if not (site_dir / name).exists():
            continue
        try:  # a tag counts only once the goals it sits in would run: an invalid tag is never reported as walked
            batch = json.loads((site_dir / name).read_text())
        except json.JSONDecodeError as exc:
            wrong.append(f"{name} is not JSON: {exc}")
            continue
        if not (isinstance(batch, list) and all(isinstance(g, dict) for g in batch)):
            wrong.append(f"{name} must be a list of goals")
            continue
        wrong += [f"{name}: {w}" for w in validate(batch, site, model, write, hooks)]
        goals += batch
    if wrong:
        print("The goals cannot be read:\n- " + "\n- ".join(wrong))
        return 2
    by = {c: [g["id"] for g in goals if c in g.get("cells", [])] for c in model["candidates"]}
    for region in model["regions"]:
        print(region)
        for c in [c for c in model["candidates"] if c.split(".")[0] == region]:
            print(f"  {'planned' if by[c] else '-':<7} {c}" + (f" ({', '.join(by[c])})" if by[c] else ""))
    print(f"{len(by)} candidate cells, {sum(1 for ids in by.values() if ids)} planned by a goal")
    return 0


def fill(journey, values):
    """Put a run's accounts, links and record IDs into a journey's {name} placeholders, one string at a
    time, so a value with a quote or a backslash arrives as it is."""
    if isinstance(journey, dict):
        return {k: fill(v, values) for k, v in journey.items()}
    if isinstance(journey, list):
        return [fill(v, values) for v in journey]
    if isinstance(journey, str):
        for name, value in values.items():
            journey = journey.replace("{" + name + "}", value)
    return journey


def tolerant(strict):
    """Upstream also requires Jev's choice to be the single most probable option. At low confidence
    the choice is sometimes a near tie; accept it when it is within 0.05 of the top."""
    def validate_choice(answer, ids):
        try:
            return strict(answer, ids)
        except ValueError:
            probabilities = answer.get("probabilities") or {}
            if not probabilities:
                raise
            top = max(probabilities, key=probabilities.get)
            strict({**answer, "choice": top}, ids)  # every other check must still hold
            if probabilities.get(answer.get("choice"), -1) < probabilities[top] - 0.05:
                raise
            return answer
    return validate_choice


def patient(field_text, models, pause=time.sleep):
    """The text helper's provider rate-limits in bursts (September 19: HTTP 429 on mercury-2.5 while
    mercury-2 answered), and now and then returns no value for a field the goal plainly gives (a school
    year). Back off and alternate models for both; any other failure is raised at once."""
    def call(context):
        for attempt in range(2 * len(models)):
            os.environ["TEXT_MODEL"] = models[attempt % len(models)]
            try:
                return field_text(context)
            except (RuntimeError, ValueError) as exc:
                if not re.search(r"HTTP 429|no valid field value", str(exc)) or attempt == 2 * len(models) - 1:
                    raise
                pause(2 ** attempt)
    return call


def configured_text(field_text):
    """Require an explicit text endpoint and model only when a journey needs form text."""
    def call(context):
        if not all(os.environ.get(k) for k in ("TEXT_MODEL_API_KEY", "TEXT_MODEL_BASE_URL", "TEXT_MODEL")):
            raise ValueError("Text helper needs TEXT_MODEL_API_KEY, TEXT_MODEL_BASE_URL and TEXT_MODEL together.")
        return field_text(context)
    return call


def offered(actions, history, url, avoid=None):
    """The controls Jev may choose from. Leaves out a click or a typed field that already did nothing
    on this page, as a person would not tap it or type it again, and any control the avoid pattern
    names (site.json avoid joined with the journey's: paid guides, chapter lists Jev hops along)."""
    dead = {(h["kind"], h["action"]) for h in history if h.get("kind") in {"click", "fill"}
            and h.get("page_changed") is False and h.get("url") == url}
    return [a for a in actions if (a["kind"], a["label"]) not in dead and not (avoid and re.search(avoid, a["label"]))]


def passed(spec, seen, urls, blocked, api=()):
    """Every condition in the spec must hold, or one spec under any. seen is (url, visible text);
    api is "STATUS URL" for each response from the site's own /api/, and a spec's api is one pattern or
    a list that must all match."""
    if "any" in spec:
        return any(passed(s, seen, urls, blocked, api) for s in spec["any"])
    pages = [" ".join(text.split()) for url, text in seen if re.search(spec.get("on", ""), url)]
    return (
        all(any(re.search(p, text, re.IGNORECASE) for text in pages) for p in spec.get("text", []))
        and ("url" not in spec or any(re.search(spec["url"], u) for u in urls))
        and ("blocked" not in spec or any(re.search(spec["blocked"], b) for b in blocked))
        and all(any(re.search(p, a) for a in api) for p in ([spec["api"]] if isinstance(spec.get("api"), str)
                                                              else spec.get("api", [])))
    )


def looping(seen):
    """seen is ((url, scroll y), action) per executed step; the same one a third time is a loop."""
    return bool(seen) and seen.count(seen[-1]) >= 3


def loop_recovery(steps, bans, write, limit=3):
    """The control to set aside and what to tell Jev when a walk keeps taking the same action at the same
    place, or None once the walk has been set back on its feet `limit` times. Read walks recover too: on
    the example site a walk bounced between two nav links while the pages under them held the answer. The
    scroll is never set aside, whatever it repeats: a walk that cannot scroll cannot read a page's rest."""
    if not looping(steps) or bans >= limit:
        return None
    label = steps[-1][1]
    if label == SCROLL_LABEL:
        return None, "This page is not moving. " + NOT_YET
    return label, (f"{label} is already done. " + NOT_YET_WRITE if write else
                   f"{label} keeps bringing you back to the same place. Leave it alone. " + NOT_YET)


def unclickable(decisions, actions, bans, limit=3, repeats=4):
    """The control to set aside and what to tell Jev when one choice keeps coming back and nothing is
    ever performed, or None. Upstream hit-tests before every input, so a control under a sticky banner
    is refused for ever: the same choice returns on an unchanged page and the walk spends its whole
    model budget without acting. The same choice on the same page four times over is that. Jev cannot
    see a covering, so the runner has to. The scroll is never set aside, as in `loop_recovery`."""
    if bans >= limit or len(decisions) < repeats:
        return None
    tail = decisions[-repeats:]
    if len({d.get("choice") for d in tail}) > 1 or len({str(d.get("fingerprint")) for d in tail}) > 1:
        return None
    label = next((a["label"] for a in actions if a["id"] == tail[-1].get("choice")), None)
    if not label or label == SCROLL_LABEL:
        return None
    return label, (f"{label} cannot be pressed: something is covering it. If a banner, a cookie notice "
                   f"or a dialog is in the way, close or dismiss that first, then carry on. " + NOT_YET)


def dedupe(events):
    rows = {}
    for e in events:
        key = (e["type"], e.get("method"), e.get("status"), (e.get("url") or e.get("text") or "").split("?")[0])
        rows.setdefault(key, {**e, "count": 0})["count"] += 1
    return list(rows.values())


def write_atomic(path, text):
    """A record is complete or absent, never half written: a crash mid-write cannot leave a truncated file."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def new_stamp(now=None):
    """A run stamp two runs in one second cannot share: UTC to the second plus a random suffix."""
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)


def run_token(stamp):
    """The stamp as a short lowercase token for the run's email addresses: mmddthhmmss plus the suffix."""
    return (stamp[4:15] + stamp[17:]).lower()


def install(current):
    """Patch jev-ultrafast to run on a Playwright page. Imported late so the tests need no packages."""
    import jev_ultrafast.agent as agent_module
    import jev_ultrafast.model as model_module
    from jev_ultrafast import browser as jb
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    sessions = {}

    def cdp(method, session_id=None, **params):
        session = sessions[session_id]
        if method == "Input.dispatchMouseEvent" and params.get("type") == "mouseWheel":
            # Upstream scrolls 560 px at a fixed desktop point. Scroll most of a screen, mid-viewport.
            step = round(current["height"] * 0.85)
            params.update(x=current["width"] // 2, y=current["height"] // 2,
                          deltaY=step if params["deltaY"] > 0 else -step)
        if method == "Input.insertText":
            current["typed"].append(params["text"])
            # Typed characters do not reach a date field; set its value the way a picker would.
            kept = session.send("Runtime.evaluate", {"returnByValue": True, "expression": f"""(el => {{
              if (!el || !{json.dumps(DATE_TYPES)}.includes(el.type)) return null;
              el.value = {json.dumps(params["text"])};
              el.dispatchEvent(new Event('input', {{bubbles: true}}));
              el.dispatchEvent(new Event('change', {{bubbles: true}}));
              return el.value !== '';
            }})(document.activeElement)"""})["result"].get("value")
            if kept is not None:
                return {}
        return session.send(method, params)

    class PlaywrightBrowser(jb.Browser):
        def __init__(self, url):
            self.page = current["context"].new_page()
            self.session = id(self.page)
            sessions[self.session] = current["context"].new_cdp_session(self.page)
            self.target = self.page
            current["watch"](self.page)
            self.page.goto(url, wait_until="load", timeout=30000)
            self.first_entry = self.call("Page.getNavigationHistory")["currentIndex"]
            self.nudged = set()

        def observe(self, screenshot=True):
            # Write walks: wait until the site's API has been quiet for half a second (a click can chain
            # requests, such as checkout after a profile save), at most 30 s. Pumps Playwright's events.
            settle, quiet = time.monotonic() + 30, time.monotonic()
            while current["write"] and time.monotonic() < settle:
                if current["pending"]:
                    quiet = time.monotonic()
                elif time.monotonic() - quiet >= 0.5:
                    break
                self.page.wait_for_timeout(100)
            if not current["write"]:
                # A read walk mostly scrolls, and a scroll-reveal page fades its next section in once
                # the scroll brings it into view. Look after it stops revealing, not the instant it lands.
                settled(lambda: self.evaluate(REVEALED),
                        lambda s: self.page.wait_for_timeout(s * 1000), time.monotonic)
            if urlparse(self.page.url).hostname == "checkout.stripe.com":  # Checkout draws its form after load
                try:
                    self.page.locator("#email, #cardNumber").first.wait_for(state="visible", timeout=20000)
                    # After Pay, the button shows Processing until Stripe answers; a person waits for it.
                    self.page.wait_for_function(STRIPE_IDLE, timeout=30000)
                except PlaywrightTimeout:
                    pass  # observe what is there; a page that never settles is itself a finding
            for attempt in range(3):
                try:
                    info = super().observe(screenshot)
                    break
                except jb.StalePage:  # still navigating: wait for the next document instead of failing
                    if attempt == 2:
                        raise
                    self.page.wait_for_load_state("load")
            if self.call("Page.getNavigationHistory")["currentIndex"] > self.first_entry:
                info["actions"].append({"id": "back", "kind": "back", "label": "Go back to the previous page"})
            text = info["text"]
            for typed in current["typed"]:  # the walk's own words are not evidence
                text = text.replace(typed, "")
            current["seen"].append((info["url"], text))
            return info

        def act(self, action, page, text=None):
            if action["kind"] in {"click", "fill", "select"}:
                before = self.page.url
                body = self.page.inner_text("body") if urlparse(before).hostname == "checkout.stripe.com" else ""
                try:
                    checkout_guard(before, self.page.url, body)  # the URL is read again after the body
                except ValueError as exc:
                    raise jb.StalePage(str(exc))
            node = action.get("node")
            if action["kind"] in {"click", "fill", "select"} and node not in self.nudged and self.evaluate(
                f"(e => {{ if (!e) return false; const r = e.getBoundingClientRect();"
                f" const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);"
                # An ancestor at the centre is the element's own line layout, which tap_point handles.
                f" return !hit || (!e.contains(hit) && !hit.contains(e)); }})"
                f"(window.__jevFast.nodes.get({node}))"
            ):
                # Something (a sticky bar, a floating button) covers it. Upstream would refuse the click
                # forever; a person nudges the page, so center it once and look again.
                self.nudged.add(node)
                self.evaluate(f"window.__jevFast.nodes.get({node}).scrollIntoView({{block: 'center'}})")
                raise jb.StalePage("Target was covered; scrolled it into view. Observe again.")
            if action["kind"] == "click":
                # A mailto or tel link opens another app, so record it where a pass check can see it.
                href = self.evaluate(f"window.__jevFast.nodes.get({action['node']})?.closest('a')?.href ?? ''")
                if href and not href.startswith("http"):
                    current["urls"].append(href)
                if point := tap_point(self.evaluate, node):  # Stripe's accordion button over the Card radio
                    if not self.fresh(page, action):
                        raise jb.StalePage("Page changed since this decision. Observe again.")
                    self.page.mouse.click(point["x"], point["y"])
                    self.after_input = action
                    return {"executed": action["id"]}
            if action["kind"] == "wait" and current["write"]:  # a person who waits, waits
                held(lambda: self.page.inner_text("body"), lambda s: self.page.wait_for_timeout(s * 1000),
                     time.monotonic)
                self.after_input = None
                return {"executed": "wait"}
            if action["kind"] == "scroll":
                # snapshot.js offers the scroll a pane under the middle of the viewport can still make,
                # but upstream sends the wheel wherever the pointer last was, which on a fresh page is
                # the top-left corner, outside any dialog. the example site's quiz modal never moved while the page
                # behind it scrolled, so quiz-score answered two of ten questions and gave up.
                size = self.page.viewport_size
                self.page.mouse.move(size["width"] // 2, size["height"] // 2)
            if action["kind"] != "back":
                return super().act(action, page, text=text)
            if not self.fresh(page, action):
                raise jb.StalePage("Page changed since this decision. Observe again.")
            self.page.go_back(wait_until="load")
            self.after_input = None
            return {"executed": "back"}

        def close(self):
            if self.target:
                self.page.close()
                self.target = None

    jb.cdp = cdp  # Browser.call and browser_operation look cdp up in the module globals
    # Our copy of upstream's snapshot; its header lists the changes.
    jb.READ_STATE = (HERE / "snapshot.js").read_text()
    jb.MARKER = f"(() => {{ const state={jb.READ_STATE}; return state?.marker ?? null; }})()"
    model_module.NEXT_ACTION += READING_RULES
    model_module.validate_choice = tolerant(model_module.validate_choice)
    model_module.post_json = retrying(adapt(model_module.post_json, current["provider"], current["ledger"]))
    # Upstream indexes this variable before calling the adapted transport. The placeholder is never sent.
    os.environ.setdefault("TYPESAFE_API_KEY", "selected-provider-adapter")
    choose = agent_module.choose
    agent_module.choose = lambda page, goal, history: choose(
        {**page, "actions": offered(page["actions"], history, page["url"], current.get("avoid"))}, goal, history)
    if os.environ.get("TEXT_MODEL"):
        agent_module.field_text = patient(agent_module.field_text, [os.environ["TEXT_MODEL"]])
    agent_module.field_text = configured_text(agent_module.field_text)
    agent_module.MAX_STEPS = max(agent_module.MAX_STEPS, current["budget"])  # a paid flow is long
    agent_module.Browser = PlaywrightBrowser
    return agent_module.Agent


def walk(site, site_dir, origin, journey, out_dir, write=False):
    from playwright.sync_api import sync_playwright

    hooks = load_hooks(site_dir)
    harmless = getattr(hooks, "harmless", None) or (lambda event: False)
    out = Path(out_dir) / journey["id"]
    out.mkdir(parents=True, exist_ok=True)
    width, height = site["viewports"][journey.get("viewport", "phone")]
    budget = journey.get("budget", site["max_actions"])
    events, urls, blocked, seen, api, pending = [], [], [], [], [], set()
    started = time.perf_counter()
    final_url = ""
    secret = os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET", "") if site["protection_bypass"] else ""

    def stamp(event):
        events.append({**event, "t_ms": round((time.perf_counter() - started) * 1000)})

    def policy(route, request):
        how = handling(site, request.method, request.url, origin, request.is_navigation_request(), write)
        if how == "allow":
            return route.continue_(headers=bypass_headers(request.url, origin, request.all_headers(), secret))
        if how == "stub":
            return route.fulfill(status=200, body="")
        if how == "rewrite":
            parts = urlparse(request.url)
            return route.fulfill(status=302, headers={"location": origin + parts.path + (
                "?" + parts.query if parts.query else "") + ("#" + parts.fragment if parts.fragment else "")})
        blocked.append(f"{request.method} {request.url}")
        stamp({"type": "blocked", "method": request.method, "url": request.url[:200]})
        route.abort("blockedbyclient")

    def watch(page):
        # ERR_BLOCKED_BY_CLIENT is our own request policy, not the site.
        page.on("console", lambda m: m.type == "error" and "ERR_BLOCKED_BY_CLIENT" not in m.text
                and stamp({"type": "console_error", "text": m.text[:300], "url": m.location.get("url", "")[:200]}))
        page.on("pageerror", lambda e: stamp({"type": "page_error", "text": str(e)[:300]}))
        page.on("response", lambda r: r.status >= 400 and r.url.startswith(origin)
                and stamp({"type": "http_error", "status": r.status, "url": r.url[:200]}))
        page.on("framenavigated", lambda f: urls.append(f.url))  # frames too: a flow can open in one
        page.on("response", lambda r: r.url.startswith(origin + "/api/") and api.append(f"{r.status} {r.url}"))
        if write:  # a person waits for the site to answer before tapping again; Jev would leave mid-request
            page.on("request", lambda r: awaited(site, r.url, origin) and pending.add(r))
            page.on("requestfinished", lambda r: pending.discard(r))
            page.on("requestfailed", lambda r: pending.discard(r))
            page.on("framenavigated", lambda f: f == page.main_frame and pending.clear())  # a new page

    avoid = "|".join(filter(None, [site["avoid"], journey.get("avoid")])) or None
    provider, ledger = configure(), []
    current = {"seen": seen, "urls": urls, "typed": [], "watch": watch, "width": width, "height": height,
               "budget": budget, "pending": pending, "write": write, "avoid": avoid,
               "provider": provider, "ledger": ledger}
    Agent = install(current)
    state, error, status = None, None, None
    start = journey["start"] if journey["start"].startswith("http") else origin + journey["start"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        # A write journey with after starts from that journey's cookies, as a new tab would.
        context = browser.new_context(viewport={"width": width, "height": height}, service_workers="block",
                                      storage_state=journey.get("state"))
        if write:  # snapshot.js then offers password fields and trims long dropdowns to the goal's options
            context.add_init_script(f"window.__jevWrite = true; window.__jevGoal = {json.dumps(journey['goal'])};")
        context.route("**/*", policy)
        current["context"] = context
        try:
            with Agent(start, journey["goal"], record_dir=out / "frames") as agent:
                state = agent.state
                status = "pass" if passed(journey["pass"], seen, urls, blocked, api) else None
                steps, where, rejected, bans = [], None, 0, 0
                try:
                    for state in [] if status else agent.run():
                        if len(state["history"]) > len(steps):
                            steps.append((where, state["history"][-1]["action"]))
                        # A form's steps share a URL and scroll place, so a write walk also tells them apart by text.
                        where = (state["page"]["url"], state["page"]["scroll"]["y"]) + (
                            (hash(state["page"]["text"]),) if write else ())
                        if passed(journey["pass"], seen, urls, blocked, api):
                            status = "pass"
                        elif recover(agent.browser.page):
                            # A blocked navigation off the site leaves Chrome's error page behind, and
                            # every walk that presses a buy button lands on one. The attempt is already
                            # recorded where a `blocked` pass check reads it, so the walk goes back and
                            # carries on. It does not spend a rejection: that page answered nothing.
                            agent.state["status"] = "ready"
                            agent.state["history"].append(
                                {"step": len(state["history"]) + 1, "kind": "note", "page_changed": None,
                                 "action": "That link left the site and was blocked. You are back on the page "
                                           "you came from; the answer has to be found here.",
                                 "url": agent.browser.page.url})
                            continue
                        elif state["status"] in {"done", "blocked"} and rejected < max(MAX_REJECTIONS, budget // 20):
                            # The pass check is the verifier: an unproven DONE or BLOCKED gets a nudge.
                            rejected += 1
                            agent.state["status"] = "ready"
                            scrolled = ""
                            if more_below(state["page"]):  # a person looks at the rest of the page before giving up
                                agent.browser.page.mouse.wheel(0, 560)
                                scrolled = "Scrolled down for you. "
                            agent.state["history"].append({"step": len(state["history"]) + 1,
                                                           "action": scrolled + (NOT_YET_WRITE if write else NOT_YET),
                                                           "kind": "note", "page_changed": None,
                                                           "url": state["page"]["url"]})
                            continue
                        elif recovery := loop_recovery(steps, bans, write):
                            # The repeated control is set aside and the walk carries on, at most three times:
                            # in write mode Jev at low confidence re-ticks a box already set instead of pressing
                            # Continue, and in read mode it takes the same link back to a page it has just left.
                            bans += 1
                            label, note = recovery
                            if label:
                                current["avoid"] = "|".join(
                                    filter(None, [current["avoid"], f"^{re.escape(label)}$"]))
                            agent.state["history"].append({"step": len(state["history"]) + 1, "kind": "note",
                                                           "action": note, "page_changed": None,
                                                           "url": state["page"]["url"]})
                            continue
                        elif recovery := unclickable(state["decisions"], state["page"]["actions"], bans):
                            bans += 1
                            label, note = recovery
                            current["avoid"] = "|".join(
                                filter(None, [current["avoid"], f"^{re.escape(label)}$"]))
                            agent.state["history"].append({"step": len(state["history"]) + 1, "kind": "note",
                                                           "action": note, "page_changed": None,
                                                           "url": state["page"]["url"]})
                            continue
                        elif looping(steps):
                            status = "loop"
                        elif len(state["history"]) >= budget:
                            status = "budget"
                        elif len(state["decisions"]) > 3 * len(state["history"]) + 10:
                            status = "unstable"  # decisions keep going stale: the page will not settle
                        if status:
                            break
                except ValueError as exc:
                    if "Text helper" in str(exc):  # a field wanted a value the goal does not give
                        field = next((a["label"] for a in agent.state["page"]["actions"]
                                      if a["id"] == agent.state["decisions"][-1]["choice"]), "?")
                        status = f"needs_text: {field}"
                    elif "model-call budget" in str(exc):
                        status = "unstable"
                    else:
                        raise
                status = status or state["status"]
                agent.browser.page.screenshot(path=str(out / "final.png"))
                final_url = agent.browser.page.url
                if write:
                    context.storage_state(path=str(out / "state.json"))
        except Exception as exc:  # noqa: BLE001 - preserve evidence across third-party browser failures
            # A harness failure is not a site finding
            error = f"{type(exc).__name__}: {exc}"[:400]
        browser.close()

    history = state["history"] if state else []
    decisions = state["decisions"] if state else []
    cost = None if any(entry["cost_usd"] is None for entry in ledger) else sum(entry["cost_usd"] for entry in ledger)
    record = {
        "id": journey["id"],
        "step": journey.get("step"),
        "viewport": journey.get("viewport", "phone"),
        "goal": journey["goal"],
        "pass_check": journey["pass"],
        "known": journey.get("known"),
        "cells": journey.get("cells", []),
        "result": "error" if error else "pass" if status == "pass" else "fail",
        "reason": error or status,
        "actions": len(history),
        "seconds": round(time.perf_counter() - started, 1),
        "jev_calls": len(ledger),
        "jev_usd": cost,
        "jev_provider": provider["provider"],
        "jev_models": list(dict.fromkeys(entry["model"] for entry in ledger)),
        "jev_usage": ledger,
        "text_calls": len(state.get("text_calls", [])) if state else 0,
        "steps": [{k: h.get(k) for k in ("step", "operation", "action", "text", "confidence", "page_changed", "url")}
                  for h in history],
        "last_text": seen[-1][1][:1500] if seen else "",
        "events": [e for e in dedupe(events) if not harmless(e)],
        "urls": urls,
        "api": api,
        "final_url": final_url,
        # the last decisions, so an unstable walk shows whether the page churned (fingerprints change)
        # or the choices were rejected (the same fingerprint again and again)
        "decisions": [{"choice": d.get("choice"), "confidence": d.get("confidence"), "elapsed_ms": d.get("elapsed_ms"),
                       "page": str(d.get("fingerprint"))[:8]} for d in decisions[-40:]],
    }
    write_atomic(out / "record.json", json.dumps(record, indent=2))
    return record


def report(records, steps, build=None, candidates=None):
    lines =["| journey | step | screen | result | actions | seconds | Jev $ | note |",
             "|---|---|---|---|---|---|---|---|"]
    for r in records:
        note = f"known: {r['known']}" if r["known"] and r["result"] in {"fail", "error", "skip"} else ""
        result = r["result"] if r["result"] == "pass" else f"{r['result']} ({r['reason']})"
        cost = "unknown" if r['jev_usd'] is None else f"{r['jev_usd']:.8f}"
        lines.append(f"| {r['id']} | {r.get('step')} | {r['viewport']} | {result} | {r['actions']} | "
                     f"{r['seconds']} | {cost} | {note} |")
    walked = [s for s in steps if any(r.get("step") == s for r in records)]
    lines += ["", "Build walked: " + (f"{build['commit']} ({build['deployment']})" if build and build["deployment"]
                                      else build["commit"] if build else "unknown"),
              "Steps walked: " + ", ".join(f"{s} {sum(r.get('step') == s for r in records)}" for s in walked),
              "Steps no journey walks: " + ", ".join(s for s in steps if s not in walked),
              "Jev spend: " + ("unknown (check provider billing)" if any(r['jev_usd'] is None for r in records)
                               else f"{sum(r['jev_usd'] for r in records):.8f} USD")]
    if candidates is not None:  # a cell counts once a goal that tags it passed in this run
        walked = list(dict.fromkeys(c for r in records if r["result"] in {"pass", "flaky"} for c in r.get("cells", [])))
        missed = [c for c in candidates if c not in walked]
        lines += [f"Cells walked ({len(walked)}): " + ", ".join(walked),
                  f"Candidate cells no journey walks ({len(missed)}): " + ", ".join(missed)]
    site = [(r["id"], e) for r in records for e in r["events"] if e["type"] != "blocked"]
    if site:
        lines += ["", "Site events (errors the walks saw, excluding requests this runner blocked):", ""]
        lines += [f"- {i}: {e['type']} {e.get('status', '')} {e.get('url') or e.get('text')} (x{e['count']})"
                  for i, e in site]
    return "\n".join(lines) + "\n"


def merge_retry(first, retry):
    """Walks vary run to run, so a failure gets one retry before it counts."""
    totals = {}
    if "jev_usd" in first:
        totals = {"attempts": [first, retry],
                  "jev_usd": None if first['jev_usd'] is None or retry['jev_usd'] is None else first['jev_usd'] + retry['jev_usd']}
        totals.update({key: first.get(key, 0) + retry.get(key, 0)
                       for key in ("jev_calls", "text_calls", "actions", "seconds")})
    if retry["result"] == "pass":
        return {**first, **totals, "result": "flaky", "reason": f"passed on retry after {first['reason']}"}
    return {**first, **totals, "reason": f"{first['reason']}; retry: {retry['reason']}"}


def option(args, name):
    """The values after --name, up to the next --flag."""
    rest = args[args.index(name) + 1:] if name in args else []
    return rest[:next((i for i, a in enumerate(rest) if a.startswith("--")), len(rest))]


def skipped(journey, reason):
    return {"id": journey["id"], "step": journey.get("step"), "viewport": journey.get("viewport", "phone"),
            "goal": journey["goal"], "pass_check": journey["pass"], "known": journey.get("known"),
            "cells": journey.get("cells", []), "result": "skip",
            "reason": reason, "actions": 0, "seconds": 0, "jev_calls": 0, "jev_usd": 0, "text_calls": 0, "steps": [],
            "events": [], "urls": [], "api": [], "final_url": ""}


def incomplete(records):
    """The records that fail the run: a fail, an error or a skip (an incomplete chain, an unresolved
    placeholder or the dollar cap) that no known note explains."""
    return [r for r in records if r["result"] in {"fail", "error", "skip"} and not r["known"]]


def record_created(path, accounts, hooks, site):
    """Add every row that now exists for the run's addresses to created.json under "<kind>s" (users,
    orders, leads, bookings), which cleanup.py reads. Written before the first journey and after each
    one, so a crash leaves a record, and the record names the addresses, so an interrupted run is
    reconciled from them. A row that cannot be recorded raises ValueError once the others are written."""
    created = json.loads(path.read_text()) if path.exists() else {"accounts": accounts, "users": {}, "orders": {}}
    owner = {email: name for name, email in accounts.items()}
    rows = hooks.created(list(accounts.values()), site) if accounts else []
    wrong = []
    for row in rows:
        missing = [k for k in ("kind", "id", "email") if not isinstance(row, dict) or row.get(k) in (None, "")]
        if missing:
            wrong.append(f"hooks.created returned a row without {', '.join(missing)}: {row!r}")
        elif not (isinstance(row["id"], str) and isinstance(row["email"], str)):
            wrong.append(f"hooks.created returned a row whose id or email is not a string: {row!r}")
        elif not (isinstance(row["kind"], str) and re.fullmatch(ROW_KIND, row["kind"])) or row["kind"] == "account":
            wrong.append(f"hooks.created returned kind {row['kind']!r}, which is not a lowercase name other than account")
        elif row["email"] not in owner:
            wrong.append(f"hooks.created returned a row for {row['email']}, which is not one of this run's addresses")
        else:
            created.setdefault(row["kind"] + "s", {})[row["id"]] = owner[row["email"]]
    write_atomic(path, json.dumps(created, indent=2))
    if wrong:
        raise ValueError("; ".join(wrong))
    return rows


def did(do, hooks, site):
    """Run a write goal's do hooks in order. The reason the journey is skipped when one raises, or None."""
    for d in do:
        try:
            getattr(hooks, d["hook"])(d.get("args", {}), site)
        except Exception as exc:  # noqa: BLE001 - reconcile partial writes after any project-hook failure
            # The site's own action failed: the journey cannot start from its state
            return f"do {d['hook']} failed: {type(exc).__name__}: {exc}"[:400]
    return None


def run_write(pool, site, site_dir, origin, journeys, out_dir, stamp, spent, done):
    """Journeys run one at a time, in file order. Each account letter in a placeholder gets a fresh
    address and password; a journey with after starts from that journey's cookies and last page
    and is skipped unless it passed. Stops the run at once if Stripe Checkout is not in test mode or
    hooks.created returns a row it cannot record (the journeys not walked are then skips), and skips
    what is left once the dollar cap is reached."""
    hooks = load_hooks(site_dir)
    names = sorted(set(re.findall(PLACEHOLDER, json.dumps(journeys))) - {""}
                   | {j["mail"]["to"] for j in journeys if "mail" in j})
    values = {}
    for name in names:
        values[f"email_{name}"] = site["write"]["email_format"].format(run=run_token(stamp), name=name)
        values[f"password_{name}"] = "Jev" + secrets.token_hex(8)
    created = Path(out_dir, "created.json")
    created.parent.mkdir(parents=True, exist_ok=True)
    accounts = {name: values[f"email_{name}"] for name in names}
    records = {}

    def stopped(exc):
        print(f"Stopped: {exc}")
        return list(records.values()) + [skipped(j, f"the run stopped: {exc}"[:400]) for j in journeys
                                         if j["id"] not in records]

    def reconcile():
        """Record every row the run's addresses own now, and give the first of each kind (a paid order
        over an unpaid one) to the placeholders later journeys use."""
        for row in record_created(created, accounts, hooks, site):
            name = next(n for n, e in accounts.items() if e == row["email"])
            key = f"{row['kind']}_id_{name}"
            if key not in values or row["kind"] == "order" and row.get("status") == "paid":
                values[key] = row["id"]

    try:
        record_created(created, accounts, hooks, site)
    except ValueError as exc:
        return stopped(exc)
    for journey in journeys:
        if spent() >= site["budget_usd"]:
            records[journey["id"]] = skipped(journey, "Jev spend is unknown or the stop threshold was reached")
            continue
        after = records.get(journey.get("after"))
        if journey.get("after") and (not after or after["result"] != "pass"):
            records[journey["id"]] = skipped(journey, f"after {journey['after']} did not pass")
            continue
        unmet = [r for r in journey.get("requires", []) if (records.get(r) or {}).get("result") != "pass"]
        if unmet:  # a pass elsewhere in the run (the partner's walk) without taking that walk's browser
            records[journey["id"]] = skipped(journey, f"requires {unmet[0]}, which did not pass")
            continue
        values["last_url"] = after["final_url"] if after else ""
        started = time.time()  # before any do hook: mail the hooks cause counts, mail from before does not
        try:
            for name in re.findall(r"\{verify_link_(\w+)\}", journey["start"]):
                values[f"verify_link_{name}"] = hooks.verification_link(accounts[name], origin, site)
        except RuntimeError as exc:
            records[journey["id"]] = skipped(journey, str(exc))
            continue
        journey = {**fill(journey, values), **({"state": str(Path(out_dir, after["id"], "state.json"))} if after else {})}
        if re.search(PLACEHOLDER, journey["start"] + json.dumps([journey["pass"], journey.get("do", [])])):
            records[journey["id"]] = skipped(journey, "a placeholder has no value in this run")
            continue
        if failed := did(journey.get("do", []), hooks, site):
            records[journey["id"]] = skipped(journey, failed)
            try:  # a hook can write before it fails, and cleanup reads only what is recorded
                reconcile()
            except ValueError as exc:
                return stopped(exc)
            continue
        record = pool.submit(walk, site, site_dir, origin, journey, out_dir, True).result()
        record = records[journey["id"]] = {**record, "do": [d["hook"] for d in journey.get("do", [])]}
        if "mail" in journey and record["result"] == "pass":
            try:
                subject = mailed(journey["mail"], accounts[journey["mail"]["to"]], started, hooks, site)
            except ValueError as exc:
                subject, record = None, {**record, "result": "error", "reason": str(exc)}
            except Exception as exc:  # noqa: BLE001 - project mailbox failures become explicit execution errors
                # The mailbox could not be read: not a pass, not a site finding
                subject, record = None, {**record, "result": "error",
                                         "reason": f"hooks.mail failed: {type(exc).__name__}: {exc}"[:400]}
            record = records[journey["id"]] = {**record, "mail": subject, **(
                {"result": "fail", "reason": "mail"} if subject is None and record["result"] == "pass" else {})}
            if Path(out_dir, journey["id"], "record.json").exists():
                write_atomic(Path(out_dir, journey["id"], "record.json"), json.dumps(record, indent=2))
        done.append(record)  # what this journey cost counts before the next one's cap check
        try:
            reconcile()
        except ValueError as exc:
            return stopped(exc)
        if "NotTestMode" in str(record["reason"]):
            print(f"Stopped: Stripe Checkout showed no test-mode marker ({record['reason']}). Nothing was typed.")
            return stopped("Stripe Checkout showed no test-mode marker")
    return list(records.values())


def site_folder(args):
    """--site DIR, else ops/journeys/ at the git root of the current directory."""
    if given := option(args, "--site"):
        return Path(given[0]).resolve()
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    if root.returncode != 0:
        sys.exit("Not inside a git repository and no --site DIR given.")
    return Path(root.stdout.strip(), "ops", "journeys")


def provenance(site_dir, goals_path, origin, write, stamp, site, build=None):
    """What this run was made of, so a record can be tied to exact inputs later."""
    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None

    revision = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False)
    return {"stamp": stamp, "origin": origin, "build": build, "mode": "write" if write else "read", "site": site["name"],
            "site_dir": Path(site_dir).name, "budget_usd": site["budget_usd"],
            "runner": {"revision": revision.stdout.strip() or None, "walk_py": sha(HERE / "walk.py"),
                       "snapshot_js": sha(HERE / "snapshot.js")},
            "inputs": {"site_json": sha(Path(site_dir, "site.json")), "goals": sha(goals_path),
                       "hooks_py": sha(Path(site_dir, "hooks.py")),
                       "model": sha(Path(site_dir, site["model"])) if isinstance(site.get("model"), str) else None,
                       "model_path": site["model"] if isinstance(site.get("model"), str)
                       else None}}


def main():
    from concurrent.futures import ProcessPoolExecutor

    args = sys.argv[1:]
    if args[:1] == ["--probe"]:
        sys.exit(probe(args))
    if args[:1] == ["--cells"]:
        sys.exit(cells(args))
    if not args or args[0].startswith("--"):
        sys.exit(__doc__.split("usage: ")[1])
    try:
        provider = configure()
    except ValueError as exc:
        sys.exit(str(exc))
    origin = args[0].rstrip("/")
    if "--expect-commit" in args and not re.fullmatch(COMMIT, one(args, "--expect-commit") or ""):
        sys.exit("--expect-commit takes one commit of 7 to 40 hex characters. Nothing was run.")
    write = "--write" in args
    site_dir = site_folder(args)
    if not (site_dir / "site.json").exists():
        sys.exit(f"No site.json in {site_dir}. Start from templates/site.json beside this runner.")
    site = load_site(site_dir)
    hooks = load_hooks(site_dir)
    if not re.search(site["deployment_url_pattern"], origin):
        sys.exit(f"{origin} does not match site.json deployment_url_pattern; a walk on the live domain is refused.")
    if site["protection_bypass"] and not os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET"):
        sys.exit("site.json says the deployment is protected: set VERCEL_AUTOMATION_BYPASS_SECRET "
                 "(Vercel Protection Bypass for Automation). Nothing was run.")
    goals_path = site_dir / ("goals-write.json" if write else "goals.json")
    goals = json.loads(goals_path.read_text())
    model = load_model(site_dir, site)
    if model and model["problems"]:
        sys.exit("The state-gap model cannot be read:\n- " + "\n- ".join(model["problems"]))
    if wrong := validate(goals, site, model, write, hooks):
        sys.exit("The goals cannot run:\n- " + "\n- ".join(wrong))
    # Everything that can refuse the run happens before the run folder exists: the goals, the build, the gate.
    build = built(hooks, origin, site)
    if "--expect-commit" in args and (wrong := stale(build, one(args, "--expect-commit"))):
        sys.exit(f"--expect-commit refused the run: {wrong}. Nothing was run.")
    if write and (wrong := gate(site, origin, site_dir, hooks)):
        sys.exit("--write is refused:\n- " + "\n- ".join(wrong) + "\nNothing was run.")
    only = set(option(args, "--only"))
    if missing := only - {g['id'] for g in goals}:
        sys.exit("Unknown journey IDs: " + ", ".join(sorted(missing)))
    stamp = new_stamp()
    out_dir = (option(args, "--out") or [str(site_dir / "runs" / stamp)])[0]
    if Path(out_dir).exists():
        sys.exit("Output folder already exists. Choose a new folder to preserve original evidence.")
    print(f"Site: {site['name']} ({site_dir})\nOutput: {out_dir}\nTarget: {origin}\n"
          f"Mode: {'write' if write else 'read'}\nJev stop threshold: {site['budget_usd']} USD\n"
          f"Provider: {provider['provider']} ({provider['model']})\n")

    journeys = [j for j in goals if not only or j["id"] in only]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    identity = provenance(site_dir, goals_path, origin, write, stamp, site, build)
    identity['jev'] = {k: provider[k] for k in ('provider', 'model', 'url')}
    write_atomic(Path(out_dir, "run.json"), json.dumps(identity, indent=2))
    done = []  # every record so far, retries included, for the dollar cap

    def spent():
        # ponytail: the cap counts Jev spend, which is measured; text-model calls are counted, not priced.
        return math.inf if any(r["jev_usd"] is None for r in done) else sum(r["jev_usd"] for r in done)

    workers = 1 if write else min(8, max(1, len(journeys)))
    # A fresh process per journey: install() patches the upstream modules for one walk.
    with ProcessPoolExecutor(max_workers=workers, max_tasks_per_child=1) as pool:
        def run(batch, folder):
            out = []
            for i in range(0, len(batch), workers):
                if spent() >= site["budget_usd"]:
                    out += [skipped(j, "Jev spend is unknown or the stop threshold was reached") for j in batch[i:]]
                    break
                chunk = batch[i:i + workers]
                out += list(pool.map(walk, [site] * len(chunk), [str(site_dir)] * len(chunk), [origin] * len(chunk),
                                     chunk, [folder] * len(chunk)))
                done.extend(out[-len(chunk):])
            return out
        records = run_write(pool, site, str(site_dir), origin, journeys, out_dir, stamp, spent, done) if write \
            else run(journeys, out_dir)
        failed = {r["id"] for r in records if r["result"] != "pass"}
        if failed and not write:  # a write journey is not repeated: it would create more accounts
            retried = {r["id"]: r for r in run([j for j in journeys if j["id"] in failed], str(Path(out_dir, "retry")))}
            records = [merge_retry(r, retried[r["id"]]) if r["id"] in retried and retried[r["id"]]["result"] != "skip"
                       else r for r in records]
    write_atomic(Path(out_dir, "summary.json"), json.dumps(records, indent=2))
    write_atomic(Path(out_dir, "summary.md"), f"Walked {origin} at {stamp}\n\n" + report(records, site["steps"], build, model and model["candidates"]))
    print(report(records, site["steps"], build, model and model["candidates"]) + f"\nFrames and records: {out_dir}")
    if write:
        print(f"Now run: python3 {site_dir / 'cleanup.py'} {out_dir}   (dry run), then again with --apply")
    sys.exit(1 if incomplete(records) else 0)


if __name__ == "__main__":
    main()
