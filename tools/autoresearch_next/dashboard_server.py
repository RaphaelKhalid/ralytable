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

AR0_HTML = """<!doctype html><meta charset=utf-8><title>Autoresearcher AR0</title>
<style>body{font:15px system-ui;margin:2rem;background:#10151c;color:#e8edf2}table{border-collapse:collapse;width:100%}td,th{padding:.35rem .55rem;border-bottom:1px solid #384553;text-align:left;font-size:13px}code{color:#9dd7ff}</style>
<h1>Autoresearcher AR0</h1><p id=s>loading...</p><table><thead><tr><th>phase</th><th>policy</th><th>seed</th><th>landscape</th><th>operator yield</th><th>best-so-far</th><th>AUC</th><th>coverage/QD</th><th>valid/duplicate</th><th>lineage</th><th>status</th></tr></thead><tbody id=t></tbody></table><script>
async function tick(){let r=await fetch('/api/status');let x=await r.json();let rows=x.rows||[];let summary=x.summary||{};let chosen=summary.chosen_policy||'not selected';s.textContent=`AR0 ${x.run.run_id} | ${rows.length} completed rows | chosen ${chosen} | loopback-only`;t.innerHTML=rows.slice(-100).reverse().map(e=>`<tr><td>${e.phase||'visible'}</td><td>${e.policy||''}</td><td>${e.seed||''}</td><td>${e.landscape||''}</td><td><code>${JSON.stringify(e.operator_yield||{})}</code></td><td>${e.best_so_far??''}</td><td>${e.auc_discovery??''}</td><td>${e.archive_coverage??''}/${e.qd_score??''}</td><td>${e.valid_proposal_rate??''}/${e.duplicate_rate??''}</td><td>${e.lineage_depth??''}</td><td>${e.status||'completed'}</td></tr>`).join('')}tick();setInterval(tick,2000)
</script>"""

AR1_HTML = """<!doctype html><meta charset=utf-8><title>Autoresearcher AR1</title>
<style>body{font:15px system-ui;margin:2rem;background:#10151c;color:#e8edf2}table{border-collapse:collapse;width:100%}td,th{padding:.35rem .55rem;border-bottom:1px solid #384553;text-align:left;font-size:13px}code{color:#9dd7ff}</style>
<h1>Autoresearcher AR1</h1><p id=s>loading...</p><table><thead><tr><th>phase</th><th>policy</th><th>seed</th><th>family</th><th>A</th><th>F</th><th>Q</th><th>valid/duplicate</th><th>lineage</th><th>status</th></tr></thead><tbody id=t></tbody></table><script>
async function tick(){let r=await fetch('/api/status');let x=await r.json();let rows=x.rows||[];let summary=x.summary||{};s.textContent=`AR1 ${x.run.run_id} | ${rows.length} rows | gate ${summary.eligible_gate??'pending'} | loopback-only`;t.innerHTML=rows.slice(-120).reverse().map(e=>`<tr><td>${e.phase||''}</td><td>${e.policy||''}</td><td>${e.seed||''}</td><td>${e.family||''}</td><td>${e.A_fi??''}</td><td>${e.F_fi??''}</td><td>${e.Q_fi??''}</td><td>${e.valid_proposal_rate??''}/${e.duplicate_rate??''}</td><td>${e.lineage_depth??''}</td><td>${e.status||'completed'}</td></tr>`).join('')}tick();setInterval(tick,2000)
</script>"""

AR2_HTML = """<!doctype html><meta charset=utf-8><title>Autoresearcher AR2</title>
<style>body{font:15px system-ui;margin:2rem;background:#10151c;color:#e8edf2}table{border-collapse:collapse;width:100%}td,th{padding:.35rem .55rem;border-bottom:1px solid #384553;text-align:left;font-size:13px}code{color:#9dd7ff}</style>
<h1>Autoresearcher AR2</h1><p id=s>loading...</p><table><thead><tr><th>phase</th><th>policy</th><th>seed</th><th>family</th><th>A</th><th>F</th><th>Q</th><th>valid/duplicate</th><th>burst</th><th>lineage</th><th>status</th></tr></thead><tbody id=t></tbody></table><script>
async function tick(){let r=await fetch('/api/status');let x=await r.json();let rows=x.rows||[];let summary=x.summary||{};s.textContent=`AR2 ${x.run.run_id} | ${rows.length} trial rows | gate ${summary.eligible_gate??'pending'} | promotion ${summary.promotion?.promote?'yes':'no'} | loopback-only`;t.innerHTML=rows.slice(-160).reverse().map(e=>`<tr><td>${e.phase||''}</td><td>${e.policy||''}${e.ablation?' / '+e.ablation:''}</td><td>${e.seed||''}</td><td>${e.family||''}</td><td>${e.A_fi?.toFixed?.(4)??''}</td><td>${e.F_fi?.toFixed?.(4)??''}</td><td>${e.Q_fi?.toFixed?.(4)??''}</td><td>${e.valid_proposal_rate?.toFixed?.(3)??''}/${e.duplicate_rate?.toFixed?.(3)??''}</td><td>${e.burst_count??''}</td><td>${e.lineage_depth??''}</td><td>${e.phase==='ablation'?'diagnostic':'completed'}</td></tr>`).join('')}tick();setInterval(tick,2000)
</script>"""


def latest_run(root: Path, phase: str = "smoke") -> Path:
    marker = root / ("AR0_ACTIVE_RUN" if phase == "ar0" else "AR1_ACTIVE_RUN" if phase == "ar1" else "AR2_ACTIVE_RUN" if phase == "ar2" else "ACTIVE_RUN")
    run_id = marker.read_text(encoding="utf-8").strip()
    run_root = Path("ar0") / "runs" if phase == "ar0" else Path("ar1") / "runs" if phase == "ar1" else Path("ar2") / "runs" if phase == "ar2" else Path("runs")
    return root / run_root / run_id


def serve_dashboard(root: Path, port: int, phase: str = "smoke") -> None:
    run_path = latest_run(root.resolve(), phase)
    from .ledger import AppendOnlyLedger
    ledger = AppendOnlyLedger(run_path / "ledger.sqlite3")
    run_id = run_path.name
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body = (AR0_HTML if phase == "ar0" else AR1_HTML if phase == "ar1" else AR2_HTML if phase == "ar2" else HTML).encode()
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body); return
            if self.path == "/api/status":
                payload = ledger.snapshot(run_id)
                if phase in ("ar0", "ar1", "ar2"):
                    rows = []
                    result_path = run_path / "results.jsonl"
                    if result_path.exists():
                        rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines() if line.strip()]
                    summary_path = run_path / "summary.json"
                    payload = {"phase": phase, "run": payload["run"], "rows": rows, "summary": json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}, "events": payload["events"]}
                body = json.dumps(payload, sort_keys=True).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body); return
            self.send_error(404)
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Dashboard: http://127.0.0.1:{port}/", flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); ledger.close()
