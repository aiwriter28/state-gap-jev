"""Serve the synthetic navigation fixture on loopback. No data is stored."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class DemoHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        self.send_error(405, "Synthetic navigation demo: purchases are not implemented")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent / "site"
    print(f"Demo: http://127.0.0.1:{args.port}/before/ or /after/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), partial(DemoHandler, directory=str(root))).serve_forever()
