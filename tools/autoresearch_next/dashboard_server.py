"""Loopback-only live dashboard for an active smoke tournament."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HTML = """<!doctype html><meta charset=utf-8><title>Autoresearch Next</title>
<style>body{font:15px system-ui;margin:2rem;background:#10151c;color:#e8edf2}pre{white-space:pre-wrap}table{border-collapse:collapse}td,th{padding:.35rem .7rem;border-bottom:1px solid #384553;text-align:left}</style>
<h1>Autoresearch Next</h1><p id=s>loading…</p><table><thead><tr><th>arm</th><th>status</th><th>candidate</th><th>raw learned</th><th>blind proxy</th><th>null</th><th>failure</th></tr></thead><tbody id=t></tbody></table><script>
async function tick(){let r=await fetch('/api/status');let x=await r.json();s.textContent=`run ${x.run.run_id} · ${x.experiments.length} ledger rows · loopback-only`;t.innerHTML=x.experiments.map(e=>{let m=e.metrics_json?JSON.parse(e.metrics_json):{};return `<tr><td>${e.arm}</td><td>${e.status}</td><td>${e.candidate_id}</td><td>${m.raw_learned_score??''}</td><td>${m.full_system_score??''}</td><td>${m.deterministic_null_score??0}</td><td>${e.error??''}</td></tr>`}).join('')}tick();setInterval(tick,2000)
</script>"""


def latest_run(root: Path) -> Path:
    run_id = (root / "ACTIVE_RUN").read_text(encoding="utf-8").strip()
    return root / "runs" / run_id


def serve_dashboard(root: Path, port: int) -> None:
    run_path = latest_run(root.resolve())
    from .ledger import AppendOnlyLedger
    ledger = AppendOnlyLedger(run_path / "ledger.sqlite3")
    run_id = run_path.name
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body = HTML.encode()
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body); return
            if self.path == "/api/status":
                body = json.dumps(ledger.snapshot(run_id), sort_keys=True).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body); return
            self.send_error(404)
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Dashboard: http://127.0.0.1:{port}/", flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); ledger.close()

