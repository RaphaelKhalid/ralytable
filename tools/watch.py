"""A live dashboard for whatever experiment is currently running.

Terminal tails have repeatedly failed here: progress bars use carriage returns,
so `tail -f` sees no new lines and shows nothing, and this session cannot open a
visible console window. So this serves a page instead.

It is deliberately generic. It scans for experiment directories, finds whatever
result and log files exist, and renders them. Nothing needs to know about it, so
it works for a run that is already in flight.

    python tools/watch.py            # http://localhost:7900
    python tools/watch.py --port N

Ctrl+C to stop. It only reads files; it can never disturb a running experiment.
"""
import argparse
import html
import json
import os
import pathlib
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
TMP = pathlib.Path(os.environ.get("TEMP", "/tmp")) / "claude"

# where experiments live: in the repo, and in the worktrees agents run from
SEARCH = [ROOT / "experiments"] + [
    p / "experiments" for p in TMP.glob("wt-*") if p.is_dir()
]

RESULT_FILES = ("results.jsonl", "judgements.jsonl", "metrics.jsonl", "progress.jsonl")
LOG_FILES = ("train.log", "run.log", "audit.log", "stdout.log", "prep.log")


def tail(path, n=14):
    try:
        raw = path.read_bytes()[-40000:].decode("utf-8", "replace")
    except OSError:
        return ""
    # progress bars use \r; keep the last frame of each line
    lines = [ln.split("\r")[-1].rstrip() for ln in raw.splitlines()]
    return "\n".join(ln for ln in lines if ln.strip())[-4000:]


def scan():
    out = []
    for base in SEARCH:
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name.startswith((".", "_")):
                continue
            rows, logs = [], []
            for name in RESULT_FILES:
                f = d / name
                if f.is_file() and f.stat().st_size:
                    try:
                        parsed = [json.loads(l) for l in
                                  f.read_text(encoding="utf-8").splitlines() if l.strip()]
                    except (json.JSONDecodeError, OSError):
                        parsed = []
                    if parsed:
                        rows.append({"file": name, "n": len(parsed),
                                     "last": parsed[-3:]})
            for name in LOG_FILES:
                f = d / name
                if f.is_file() and f.stat().st_size:
                    logs.append({"file": name, "text": tail(f),
                                 "age": time.time() - f.stat().st_mtime})
            if rows or logs:
                out.append({"name": d.name,
                            "where": "repo" if base.is_relative_to(ROOT) else "worktree",
                            "results": rows, "logs": logs})
    return out


PAGE = """<!doctype html><meta charset=utf-8>
<title>ralytable / running</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b0b0c;--fg:#e8e6e3;--dim:#8b8785;--line:#232326;--accent:#a70900}
@media(prefers-color-scheme:light){:root{--bg:#fbfaf9;--fg:#17161a;--dim:#6b6764;--line:#e3e0dc;--accent:#a70900}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 ui-monospace,"SF Mono",Menlo,Consolas,monospace;padding:22px}
h1{font-size:15px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);font-weight:500;margin:0 0 18px}
.exp{border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:0 0 16px}
.exp h2{font-size:15px;margin:0 0 4px;color:var(--accent)}
.meta{color:var(--dim);font-size:12px;margin-bottom:10px}
pre{background:rgba(127,127,127,.07);border-radius:7px;padding:10px 12px;overflow-x:auto;margin:8px 0 0;font-size:12.5px;white-space:pre;max-height:340px}
.f{color:var(--dim);font-size:12px;margin-top:12px}
.live{color:var(--accent)}
#t{color:var(--dim);font-size:12px;margin-top:20px}
</style>
<h1>ralytable &middot; what is running</h1>
<div id=app></div>
<div id=t></div>
<script>
async function tick(){
  let d; try{ d = await (await fetch('/data.json',{cache:'no-store'})).json(); }catch(e){ return; }
  const esc = s => s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  document.getElementById('app').innerHTML = d.length ? d.map(e=>`
    <div class=exp>
      <h2>${esc(e.name)}</h2>
      <div class=meta>${e.where}</div>
      ${e.results.map(r=>`<div class=f>${esc(r.file)} &middot; ${r.n} record${r.n===1?'':'s'}</div>
        <pre>${esc(r.last.map(x=>JSON.stringify(x)).join('\\n'))}</pre>`).join('')}
      ${e.logs.map(l=>`<div class="f${l.age<90?' live':''}">${esc(l.file)} &middot; ${
        l.age<90?'live':Math.round(l.age/60)+'m ago'}</div><pre>${esc(l.text)}</pre>`).join('')}
    </div>`).join('') : '<div class=exp>nothing running</div>';
  document.getElementById('t').textContent = 'refreshed ' + new Date().toLocaleTimeString();
}
tick(); setInterval(tick, 3000);
</script>
"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/data.json"):
            body = json.dumps(scan()).encode()
            ctype = "application/json"
        else:
            body = PAGE.encode()
            ctype = "text/html; charset=utf-8"
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
        print(f"\n  live dashboard:  http://localhost:{p}\n")
        print(f"  watching {len(SEARCH)} location(s); refreshes every 3s")
        print("  Ctrl+C to stop. It only reads files.\n", flush=True)
        srv.serve_forever()
    raise SystemExit("no free port")
