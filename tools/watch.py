"""A live dashboard for whatever experiment is currently running.

Terminal tails have repeatedly failed here: progress bars use carriage returns,
so `tail -f` sees no new lines, and this session cannot open a visible console
window. So this serves a page instead.

It answers one question at a glance: what is running right now, and how is it
doing. Finished work is summarised underneath, compactly. It is read-only and
can never disturb a run.

    python tools/watch.py            # http://localhost:7900
    python tools/watch.py --port N
"""
import argparse
import json
import os
import pathlib
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
TMP = pathlib.Path(os.environ.get("TEMP", "/tmp")) / "claude"
SEARCH = [ROOT / "experiments"] + [p / "experiments" for p in TMP.glob("wt-*") if p.is_dir()]

RESULTS = ("results.jsonl", "judgements.jsonl", "metrics.jsonl", "progress.jsonl")
LOGS = ("train.log", "run.log", "audit.log", "stdout.log", "prep.log")
LIVE_SECONDS = 120

# columns worth showing per result file, in order; everything else is dropped
COLS = ["config", "seed", "val_ce", "val_loss", "val_acc", "val_ppl",
        "live_codes", "n_codes", "role_purity", "status", "seconds"]
SHORT = {"val_ce": "CE", "val_loss": "loss", "val_acc": "acc", "val_ppl": "ppl",
         "live_codes": "live", "n_codes": "of", "role_purity": "purity",
         "seconds": "sec"}


def last_frame(path, n=6):
    """Last n meaningful lines, taking the final frame of each carriage-return bar."""
    try:
        raw = path.read_bytes()[-20000:].decode("utf-8", "replace")
    except OSError:
        return []
    lines = [ln.split("\r")[-1].rstrip() for ln in raw.splitlines()]
    return [ln for ln in lines if ln.strip()][-n:]


def read_rows(path, limit=400):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for l in lines[-limit:]:
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    return out


def summarise(name, rows):
    """Turn a result file into a small table, or a one-line count if it does not fit."""
    if not rows:
        return None
    keys = [k for k in COLS if any(k in r for r in rows)]
    if not keys:
        return {"kind": "count", "n": len(rows)}
    real = [r for r in rows if not r.get("smoke")]
    real = real or rows
    body = []
    for r in real[-12:]:
        cells = []
        for k in keys:
            v = r.get(k)
            if isinstance(v, float):
                v = f"{v:.4f}" if abs(v) < 100 else f"{v:.0f}"
            cells.append("" if v is None else str(v))
        body.append(cells)
    return {"kind": "table", "head": [SHORT.get(k, k) for k in keys],
            "body": body, "n": len(real)}


def scan():
    found = {}
    for base in SEARCH:
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name.startswith((".", "_")):
                continue
            tables, logs, newest = [], [], 0.0
            for fn in RESULTS:
                f = d / fn
                if f.is_file() and f.stat().st_size:
                    t = summarise(fn, read_rows(f))
                    if t:
                        t["file"] = fn
                        tables.append(t)
                    newest = max(newest, f.stat().st_mtime)
            for fn in LOGS:
                f = d / fn
                if f.is_file() and f.stat().st_size:
                    age = time.time() - f.stat().st_mtime
                    logs.append({"file": fn, "age": age, "lines": last_frame(f)})
                    newest = max(newest, f.stat().st_mtime)
            if not tables and not logs:
                continue
            logs.sort(key=lambda x: x["age"])
            entry = {"name": d.name, "tables": tables, "logs": logs,
                     "age": time.time() - newest if newest else 1e9}
            # the same experiment exists in the repo and in agent worktrees;
            # keep whichever copy was touched most recently
            prev = found.get(d.name)
            if prev is None or entry["age"] < prev["age"]:
                found[d.name] = entry
    out = sorted(found.values(), key=lambda e: e["age"])
    for e in out:
        e["live"] = e["age"] < LIVE_SECONDS
        e["logs"] = [l for l in e["logs"] if l["age"] < 3600] if e["live"] else []
    return out


PAGE = r"""<!doctype html><meta charset=utf-8>
<title>ralytable / running</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<link rel=preconnect href=https://fonts.googleapis.com>
<link rel=preconnect href=https://fonts.gstatic.com crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Inter:wght@400;500;600&display=swap" rel=stylesheet>
<style>
:root{--bg:#0a0a0b;--card:#0f0f11;--fg:#eceae7;--dim:#7d7975;--faint:#4a4744;
      --line:#1f1f22;--accent:#e0362c;--ok:#3fb07a}
@media(prefers-color-scheme:light){:root{--bg:#faf9f7;--card:#fff;--fg:#16151a;
      --dim:#6e6a66;--faint:#a6a29e;--line:#e6e2de;--accent:#a70900;--ok:#1f7a4d}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:15px/1.5 Inter,system-ui,sans-serif;padding:28px 22px 60px;
     max-width:1120px;margin-inline:auto}
header{display:flex;align-items:baseline;gap:14px;margin-bottom:26px}
h1{font-size:14px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);
   font-weight:600;margin:0}
#clock{color:var(--faint);font-size:12px;margin-left:auto;
       font-family:'JetBrains Mono',monospace}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
      padding:20px 22px;margin-bottom:14px}
.card.live{border-color:color-mix(in srgb,var(--accent) 55%,var(--line))}
.top{display:flex;align-items:center;gap:10px;margin-bottom:2px}
h2{font-size:17px;margin:0;font-weight:600}
.pill{font-size:11px;letter-spacing:.1em;text-transform:uppercase;font-weight:600;
      padding:3px 9px;border-radius:99px;background:var(--accent);color:#fff}
.pill.done{background:transparent;color:var(--faint);border:1px solid var(--line)}
.dot{width:7px;height:7px;border-radius:99px;background:var(--accent);
     animation:p 1.6s ease-in-out infinite}
@keyframes p{50%{opacity:.25}}
@media(prefers-reduced-motion:reduce){.dot{animation:none}}
.sub{color:var(--faint);font-size:12.5px;margin:0 0 14px}
table{border-collapse:collapse;width:100%;font-family:'JetBrains Mono',monospace;
      font-size:12.5px;margin:0 0 4px}
th{text-align:right;color:var(--faint);font-weight:500;padding:0 0 6px 18px;
   border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left;padding-left:0}
td{text-align:right;padding:5px 0 5px 18px;white-space:nowrap;
   border-bottom:1px solid color-mix(in srgb,var(--line) 45%,transparent)}
tr:last-child td{border-bottom:none}
.wrap{overflow-x:auto}
pre{font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.65;
    color:var(--dim);background:transparent;margin:10px 0 0;padding:0;
    overflow-x:auto;white-space:pre}
.fname{color:var(--faint);font-size:11px;letter-spacing:.09em;text-transform:uppercase;
       margin:16px 0 8px;font-weight:600}
.fname:first-of-type{margin-top:0}
.empty{color:var(--faint);text-align:center;padding:44px 0}
</style>
<header><h1>Ralytable</h1><span id=clock></span></header>
<div id=app><div class=empty>looking&hellip;</div></div>
<script>
const esc = s => String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const ago = s => s<120?'just now':s<5400?Math.round(s/60)+' min ago':Math.round(s/3600)+' h ago';

function table(t){
  return `<div class=fname>${esc(t.file)} &middot; ${t.n} run${t.n===1?'':'s'}</div>`+
    (t.kind==='count' ? `<pre>${t.n} records</pre>` :
    `<div class=wrap><table><tr>${t.head.map(h=>`<th>${esc(h)}</th>`).join('')}</tr>`+
    t.body.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join('')}</tr>`).join('')+
    `</table></div>`);
}

async function tick(){
  let d; try{ d = await (await fetch('/data.json',{cache:'no-store'})).json(); }catch(e){ return; }
  document.getElementById('app').innerHTML = d.length ? d.map(e=>`
    <div class="card${e.live?' live':''}">
      <div class=top>
        ${e.live?'<span class=dot></span>':''}
        <h2>${esc(e.name)}</h2>
        <span class="pill${e.live?'':' done'}">${e.live?'running':'done'}</span>
      </div>
      <p class=sub>last activity ${ago(e.age)}</p>
      ${e.tables.map(table).join('')}
      ${e.logs.map(l=>`<div class=fname>${esc(l.file)}</div><pre>${
        esc(l.lines.join('\n'))}</pre>`).join('')}
    </div>`).join('') : '<div class=empty>nothing running</div>';
  document.getElementById('clock').textContent = new Date().toLocaleTimeString();
}
tick(); setInterval(tick, 3000);
</script>
"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/data.json"):
            body, ctype = json.dumps(scan()).encode(), "application/json"
        else:
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7900)
    port = ap.parse_args().port
    for p in range(port, port + 12):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), H)
        except OSError:
            continue
        print(f"\n  live dashboard:  http://localhost:{p}\n", flush=True)
        srv.serve_forever()
    raise SystemExit("no free port")
