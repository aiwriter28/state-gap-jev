"""Browser checks for the four marked changes in snapshot.js. Needs Playwright and Chromium:

    uv run --with playwright==1.63.0 --with pytest python -m pytest test_snapshot.py

Skipped when Playwright is not importable, so the offline suite still runs with plain python3."""

from pathlib import Path

import pytest
from walk import tap_point

playwright = pytest.importorskip("playwright.sync_api")

SNAPSHOT = (Path(__file__).parents[1] / "scripts/snapshot.js").read_text()

PAGE = """
<label><input type="radio" name="kids" value="1" style="position:absolute;opacity:0;width:0;height:0">One focus child</label>
<label>Decision date <input type="date" name="when"></label>
<label>Password <input type="password" name="pw"></label>
<label>Country <select name="country">{options}</select></label>
<button type="submit">Pay</button>
""".format(options="".join(f'<option value="{i}">Country {i}</option>' for i in range(60)))


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


def snapshot(browser, write=False, goal=""):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    if write:
        context.add_init_script(f"window.__jevWrite = true; window.__jevGoal = {goal!r};")
    page = context.new_page()
    page.set_content(PAGE)
    state = page.evaluate(SNAPSHOT)
    context.close()
    return state


def test_a_visible_label_stands_in_for_its_hidden_radio(browser):
    labels = [a["label"] for a in snapshot(browser)["actions"] if a.get("role") == "radio"]
    assert labels == ["One focus child"]


def test_a_date_input_counts_as_a_text_box(browser):
    dates = [a for a in snapshot(browser)["actions"] if a["label"] == "Decision date" and a["kind"] == "fill"]
    assert dates and dates[0]["role"] == "textbox"


def test_a_password_field_is_offered_only_in_a_write_walk(browser):
    assert not [a for a in snapshot(browser)["actions"] if a["label"] == "Password"]
    assert [a for a in snapshot(browser, write=True)["actions"] if a["label"] == "Password" and a["kind"] == "fill"]


def test_a_long_dropdown_offers_only_the_options_the_goal_names_in_a_write_walk(browser):
    read = [a for a in snapshot(browser)["actions"] if a["kind"] == "select"]
    assert len(read) == 59  # every option but the selected one, in a read walk
    write = [a for a in snapshot(browser, write=True, goal="You live in Country 7 and pay $195.")["actions"]
             if a["kind"] == "select"]
    assert [a["value"] for a in write] == ["7"]


OVERLAID = """
<div style="position:relative;width:300px;height:40px">
  <input type="radio" name="pm" id="card" style="position:absolute;left:8px;top:12px;width:16px;height:16px">
  <button type="button" id="row" style="position:absolute;inset:0;background:transparent;border:0"
          onclick="document.getElementById('card').checked=true"></button>
</div>
<div style="position:relative;width:300px;height:40px">
  <input type="radio" name="pm" id="other" style="position:absolute;left:8px;top:12px;width:16px;height:16px">
  <div id="banner" style="position:absolute;inset:0;background:transparent"></div>
</div>
"""


def test_a_target_under_an_interactive_overlay_is_tapped_at_its_center_and_a_banner_is_not(browser):
    # Stripe Checkout (the example app write-10 and 11, 2026-09-20) lays a transparent accordion button over each
    # payment-method row, so the Card radio never contains the element at its own center and upstream refuses
    # the click forever. A person taps the spot; a sticky banner over a control is still a covering to report.
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.set_content(OVERLAID)
    page.evaluate(SNAPSHOT)
    nodes = page.evaluate("() => { const out = {}; for (const [id, e] of window.__jevFast.nodes) out[e.id] = id; return out; }")
    point = tap_point(page.evaluate, nodes["card"])
    assert point and point["x"] < 60
    page.mouse.click(point["x"], point["y"])
    assert page.evaluate("document.getElementById('card').checked")
    assert tap_point(page.evaluate, nodes["other"]) is None
    context.close()


PANED = """
<style>html,body{margin:0;height:100%;overflow:hidden}
#shell{height:100vh;display:grid;grid-template-rows:auto minmax(0,1fr)}
#pane{overflow:auto;min-height:0}</style>
<div id="shell"><h1>Shared map</h1><div id="pane">
  <p style="height:1400px">Why couples get stuck here</p>
  <p id="deep">Question to start the conversation</p>
</div></div>
"""


def test_a_page_that_scrolls_inside_a_pane_still_offers_scroll_down(browser):
    # the example app's walkthrough shell is capped to the window since 2026-09-20 (V13), so the map and its detail
    # panel scroll inside a pane while the window never moves. visual-3 (2026-09-21) could not reach the
    # conversation question under a dimension because Scroll down was offered only when the document scrolls.
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.set_content(PANED)
    before = page.evaluate(SNAPSHOT)
    assert "Question to start the conversation" not in before["text"]
    assert [a for a in before["actions"] if a["id"] == "scroll_down"], "no Scroll down offered for a pane"
    page.mouse.move(640, 400)
    page.mouse.wheel(0, 680)
    page.wait_for_function("document.querySelector('#pane').scrollTop > 0")
    page.mouse.wheel(0, 680)
    page.wait_for_function("document.querySelector('#deep').getBoundingClientRect().bottom <= innerHeight")
    after = page.evaluate(SNAPSHOT)
    assert "Question to start the conversation" in after["text"]
    assert after["scroll"]["y"] > before["scroll"]["y"], "the record must see the pane move"
    assert [a for a in after["actions"] if a["id"] == "scroll_up"]
    context.close()


WRAPPED = """
<style>body{margin:0;font:16px system-ui}
#banner{position:fixed;left:0;right:0;bottom:0;background:#fff;padding:12px}
p{margin:0;width:200px}</style>
<div id="banner"><p>Both stay off unless you allow analytics. <a id="privacy" href="#"
onclick="window.__tapped = true; return false">Privacy Policy</a></p></div>
"""


def test_a_link_that_wraps_onto_a_second_line_is_tapped_on_its_first_line(browser):
    # the example site run 20260921T110520Z-0a28: the consent banner's Privacy Policy link wraps, so the centre of
    # its bounding box falls between its two line boxes and the topmost element there is its own
    # paragraph. Upstream hit-tests before every input, so child-data chose that link eleven times,
    # executed nothing at all and ended unstable with zero actions.
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.set_content(WRAPPED)
    page.evaluate(SNAPSHOT)
    node = page.evaluate(
        "() => { for (const [id, e] of window.__jevFast.nodes) if (e.id === 'privacy') return id; return null; }")
    assert page.evaluate("document.getElementById('privacy').getClientRects().length") > 1, "the link must wrap"
    assert page.evaluate(
        "() => { const e = document.getElementById('privacy'), r = e.getBoundingClientRect();"
        " return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2).tagName; }") == "P"
    point = tap_point(page.evaluate, node)
    assert point, "a link that wraps is its own layout, not a covered control"
    page.mouse.click(point["x"], point["y"])
    assert page.evaluate("window.__tapped === true")
    context.close()


COVERED_BELOW = """
<style>body{margin:0;height:1400px}
#next{position:absolute;top:700px;left:20px;width:120px;height:48px}
#bar{position:fixed;left:0;right:0;bottom:0;height:120px;background:#fff}</style>
<button id="next" onclick="window.__pressed = true">Next</button>
<div id="bar">We use analytics</div>
"""


def test_a_button_half_under_a_sticky_bar_is_tapped_on_the_part_that_is_clear(browser):
    # the example site run 20260921T114357Z-dc0a: the consent banner covered the lower half of the quiz's Next
    # button, upstream refused the click, and the walk spent thirty actions scrolling before it
    # stumbled on No thanks. A person taps the part of the button they can see.
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.set_content(COVERED_BELOW)
    page.evaluate(SNAPSHOT)
    node = page.evaluate(
        "() => { for (const [id, e] of window.__jevFast.nodes) if (e.id === 'next') return id; return null; }")
    assert page.evaluate(
        "() => { const r = document.getElementById('next').getBoundingClientRect();"
        " return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2).id; }") == "bar"
    point = tap_point(page.evaluate, node)
    assert point, "a button whose top half is clear is reachable"
    page.mouse.click(point["x"], point["y"])
    assert page.evaluate("window.__pressed === true")
    context.close()


DIALOG = """
<style>html,body{margin:0;height:100%}
#veil{position:fixed;inset:0;background:rgba(0,0,0,.4)}
#modal{position:fixed;left:20px;top:75px;width:350px;height:600px;overflow:auto;background:#fff}</style>
<div id="veil"></div>
<div id="modal"><p style="height:1200px">Question 2 of 10</p><button id="next">Next</button></div>
"""


def test_a_dialog_scrolls_only_when_the_wheel_lands_inside_it(browser):
    # the example site run 20260921T115151Z-eca3: the quiz is a modal with its own scroller, and upstream sends the
    # wheel wherever the pointer last was, which on a fresh page is the top-left corner outside the
    # modal. The page behind it scrolled instead, so quiz-score answered two of ten questions, scrolled
    # thirty times and never reached Next. snapshot.js looks for the pane under the viewport centre,
    # so that is where the wheel has to land.
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.set_content(DIALOG)
    page.evaluate(SNAPSHOT)
    assert [a for a in page.evaluate(SNAPSHOT)["actions"] if a["id"] == "scroll_down"], "no scroll offered"
    page.mouse.move(0, 0)
    page.evaluate("window.addEventListener('wheel', () => requestAnimationFrame(() => {window.__wheeled = true}), {once:true})")
    page.mouse.wheel(0, 560)
    page.wait_for_function("window.__wheeled === true")
    assert page.evaluate("document.getElementById('modal').scrollTop") == 0, "the corner is not the dialog"
    size = page.viewport_size
    page.mouse.move(size["width"] // 2, size["height"] // 2)
    page.mouse.wheel(0, 560)
    page.wait_for_function("document.getElementById('modal').scrollTop > 0")
    assert page.evaluate("document.getElementById('modal').scrollTop") > 0
    context.close()
