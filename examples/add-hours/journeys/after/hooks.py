"""Synthetic fixture identity. Read only; the commit field holds a Git blob ID of the served page."""
import hashlib
import urllib.request


def build(origin, site):
    with urllib.request.urlopen(origin + site["fixture_path"], timeout=10) as response:
        body = response.read()
    blob = b"blob " + str(len(body)).encode() + b"\0" + body
    return {"commit": hashlib.sha1(blob).hexdigest(), "deployment": "synthetic fixture page (Git blob ID)"}
