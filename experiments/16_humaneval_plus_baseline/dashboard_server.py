"""Loopback-only dashboard for append-only HumanEval+ run records."""

from __future__ import annotations

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


class Handler(SimpleHTTPRequestHandler):
    record: Path

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path == "/api/record":
            events = []
            if self.record.exists():
                for line in self.record.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            body = json.dumps({"latest": events[-1] if events else None, "events": events[-20:]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if urlparse(self.path).path == "/":
            self.path = "/dashboard.html"
        return super().do_GET()

    def log_message(self, format: str, *args: object) -> None:
        print(format % args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True, help="append-only JSONL run record")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    Handler.record = args.record.resolve()
    request_handler = partial(Handler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), request_handler)
    print(f"HumanEval+ dashboard: http://127.0.0.1:{args.port}/")
    print(f"Record: {Handler.record}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
