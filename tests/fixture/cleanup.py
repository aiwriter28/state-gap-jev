"""Fixture cleanup, to the contract's shape only: takes a run folder, reads created.json, and its dry run
(the default) exits 0 on an empty record. It never deletes anything.

usage: python3 cleanup.py RUN_DIR [--apply]
"""

import json
import sys
from pathlib import Path

args = sys.argv[1:]
if not args or args[0].startswith("--"):
    sys.exit(__doc__.split("usage: ")[1].split("\n")[0])
record = json.loads(Path(args[0], "created.json").read_text())
print(f"Recorded: {len(record['users'])} accounts, {len(record['orders'])} orders ({args[0]})")
if "--apply" in args:
    sys.exit("The fixture cleanup never deletes anything.")
print("Dry run. Nothing deleted.")
