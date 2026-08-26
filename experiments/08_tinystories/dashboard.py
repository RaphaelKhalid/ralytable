"""A dependency-free live dashboard for a long training run.

wandb/tensorboard/mlflow are not installed here and none of them should be a
requirement for watching a loop that prints numbers. This is a
ThreadingHTTPServer on a daemon thread serving exactly two things: one
self-contained HTML page (no CDN, no libraries -- the loss curves are inline
SVG paths built in the page's own JavaScript) and a /metrics.json endpoint the
page polls every 2 seconds.

THE SERVER MUST NEVER KILL TRAINING. Every entry point is wrapped: a failure to
bind falls through to the next port, a failure on any request is swallowed, and
if the whole thing cannot start, training carries on with a printed warning.
The trainer only ever touches `state`, a plain dict behind a lock.
"""
import json, threading, time
import http.server
import socketserver

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>TinyStories: dense vs discrete</title>
<style>
 :root{--bg:#0f1115;--fg:#e6e8ee;--dim:#8b93a7;--line:#242938;--ok:#5ac47d;
       --a:#6aa9ff;--b:#ff9f5a;--c:#c08bff;--d:#5ad0c4;--e:#ff6b8a;--f:#d4c65a}
 body{margin:0;background:var(--bg);color:var(--fg);
      font:13px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace}
 .wrap{max-width:1100px;margin:0 auto;padding:24px}
 h1{font-size:16px;font-weight:600;margin:0 0 2px}
 .sub{color:var(--dim);margin-bottom:18px}
 .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
       gap:10px;margin-bottom:18px}
 .card{background:#151823;border:1px solid var(--line);border-radius:8px;padding:10px 12px}
 .k{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.06em}
 .v{font-size:19px;margin-top:3px}
 .barwrap{height:8px;background:#1b1f2c;border-radius:4px;overflow:hidden;margin:8px 0 20px}
 .bar{height:100%;background:var(--ok);width:0;transition:width .4s}
 table{border-collapse:collapse;width:100%;margin-top:8px}
 th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line)}
 th{color:var(--dim);font-weight:500;font-size:11px;text-transform:uppercase}
 svg{width:100%;height:300px;background:#151823;border:1px solid var(--line);
     border-radius:8px}
 .legend span{margin-right:14px}
 .dot{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px}
 .dead{color:var(--e)}
</style></head><body><div class="wrap">
<h1>TinyStories &mdash; dense vs discrete bottleneck</h1>
<div class="sub" id="status">connecting...</div>
<div class="barwrap"><div class="bar" id="bar"></div></div>
<div class="grid" id="cards"></div>
<div class="legend" id="legend"></div>
<svg id="plot" viewBox="0 0 800 300" preserveAspectRatio="none"></svg>
<div class="sub" style="margin-top:6px">cross-entropy vs step (VQ commitment loss is
tracked separately and never summed into this curve)</div>
<h1 style="margin-top:24px">finished runs</h1>
<table id="done"><thead><tr id="dh"></tr></thead><tbody id="db"></tbody></table>
</div><script>
const COL=['--a','--b','--c','--d','--e','--f'];
function css(n){return getComputedStyle(document.documentElement).getPropertyValue(n)}
function fmt(s){s=Math.max(0,Math.round(s));
 return Math.floor(s/3600)+'h'+String(Math.floor(s%3600/60)).padStart(2,'0')
   +'m'+String(s%60).padStart(2,'0')+'s'}
function card(k,v){return '<div class="card"><div class="k">'+k+
 '</div><div class="v">'+v+'</div></div>'}
function draw(curves){
 const p=document.getElementById('plot'); const W=800,H=300,PAD=34;
 let xs=[],ys=[];
 for(const c of curves){for(const pt of c.pts){xs.push(pt[0]);ys.push(pt[1])}}
 if(!xs.length){p.innerHTML='';return}
 const x0=0,x1=Math.max(...xs)||1,y0=Math.min(...ys),y1=Math.max(...ys);
 const sx=v=>PAD+(v-x0)/(x1-x0||1)*(W-PAD-8);
 const sy=v=>H-PAD-(v-y0)/(y1-y0||1)*(H-PAD-14);
 let o='';
 for(let i=0;i<=4;i++){const yv=y0+(y1-y0)*i/4, y=sy(yv);
  o+='<line x1="'+PAD+'" x2="'+(W-8)+'" y1="'+y+'" y2="'+y+'" stroke="'+css('--line')+
     '" stroke-width="1"/><text x="2" y="'+(y+4)+'" fill="'+css('--dim')+
     '" font-size="10">'+yv.toFixed(2)+'</text>'}
 o+='<text x="'+(W-40)+'" y="'+(H-8)+'" fill="'+css('--dim')+'" font-size="10">'+
    Math.round(x1)+'</text>';
 curves.forEach((c,i)=>{if(c.pts.length<2)return;
  const d=c.pts.map((pt,j)=>(j?'L':'M')+sx(pt[0]).toFixed(1)+' '+sy(pt[1]).toFixed(1)).join(' ');
  o+='<path d="'+d+'" fill="none" stroke="'+css(COL[i%COL.length])+'" stroke-width="1.6"/>'});
 p.innerHTML=o;
 document.getElementById('legend').innerHTML=curves.map((c,i)=>
  '<span><i class="dot" style="background:'+css(COL[i%COL.length])+'"></i>'+c.name+'</span>').join('');
}
async function tick(){
 let m; try{m=await (await fetch('/metrics.json',{cache:'no-store'})).json()}
 catch(e){document.getElementById('status').textContent='dashboard offline';return}
 const r=m.run||{};
 document.getElementById('status').textContent =
   (m.phase||'')+'  |  run '+(m.run_index||0)+' of '+(m.n_runs||0)+
   (r.name?('  |  '+r.name+'  seed '+r.seed):'');
 const frac=r.total?r.step/r.total:(m.done_frac||0);
 document.getElementById('bar').style.width=(frac*100).toFixed(1)+'%';
 document.getElementById('cards').innerHTML=[
  card('step',(r.step||0)+' / '+(r.total||0)),
  card('cross-entropy',(r.ce!=null?r.ce.toFixed(4):'-')),
  card('commit loss',(r.commit!=null?r.commit.toExponential(2):'n/a')),
  card('val CE',(r.val_ce!=null?r.val_ce.toFixed(4):'-')),
  card('tokens/sec',(r.tps!=null?Math.round(r.tps).toLocaleString():'-')),
  card('elapsed',fmt(r.elapsed||0)),
  card('eta this run',fmt(r.eta||0)),
  card('eta all runs',fmt(m.eta_total||0)),
  card('gpu mem',(r.gpu_gb!=null?r.gpu_gb.toFixed(2)+' GB':'-')),
  card('live codes',(r.live_codes!=null?r.live_codes:'n/a')),
  card('params',(r.params!=null?(r.params/1e6).toFixed(2)+'M':'-')),
  card('batch',(r.batch!=null?r.batch+(r.accum>1?(' x'+r.accum):''):'-')),
 ].join('');
 draw(m.curves||[]);
 const rows=m.results||[];
 const cols=['config','seed','val_ce','val_acc','val_ppl','commit','live_codes',
             'params','tokens','seconds','status'];
 document.getElementById('dh').innerHTML=cols.map(c=>'<th>'+c+'</th>').join('');
 document.getElementById('db').innerHTML=rows.map(r=>'<tr'+
  (r.status&&r.status!=='ok'?' class="dead"':'')+'>'+cols.map(c=>{
   let v=r[c]; if(typeof v==='number')v=(c==='params'||c==='tokens')?
     v.toLocaleString():v.toFixed(4);
   return '<td>'+(v==null?'-':v)+'</td>'}).join('')+'</tr>').join('');
}
tick(); setInterval(tick,2000);
</script></body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    state = None

    def log_message(self, *a):
        pass                                  # never spam the training console

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path.startswith("/metrics.json"):
                with self.state["lock"]:
                    body = json.dumps(self.state["data"]).encode()
                self._send(body, "application/json")
            else:
                self._send(PAGE.encode(), "text/html; charset=utf-8")
        except Exception:
            pass                              # a broken pipe must not matter


class Dashboard:
    """Thread-safe metrics mailbox plus the HTTP server that renders it."""

    def __init__(self, port=7777, tries=8, enabled=True):
        self.lock = threading.Lock()
        self.data = {"phase": "starting", "curves": [], "results": [],
                     "run": {}, "run_index": 0, "n_runs": 0, "eta_total": 0}
        self.url = None
        self._curves = {}
        if not enabled:
            return
        for p in range(port, port + tries):
            try:
                srv = socketserver.ThreadingTCPServer(("127.0.0.1", p), _Handler)
                srv.daemon_threads = True
                _Handler.state = {"lock": self.lock, "data": self.data}
                t = threading.Thread(target=self._serve, args=(srv,), daemon=True)
                t.start()
                self.url = f"http://localhost:{p}"
                return
            except OSError:
                continue
        print("  (dashboard: no free port in "
              f"{port}..{port+tries-1}; continuing without it)", flush=True)

    @staticmethod
    def _serve(srv):
        try:
            srv.serve_forever(poll_interval=0.5)
        except Exception as e:                # never propagate into training
            print(f"\n  (dashboard server stopped: {type(e).__name__}: {e})", flush=True)

    def set(self, **kw):
        with self.lock:
            self.data.update(kw)

    def set_run(self, **kw):
        with self.lock:
            self.data["run"].update(kw)

    def point(self, name, step, ce):
        """Append to a named loss curve, thinned so the page stays light."""
        with self.lock:
            pts = self._curves.setdefault(name, [])
            pts.append([step, ce])
            if len(pts) > 400:                # decimate rather than grow forever
                del pts[::2]
            self.data["curves"] = [{"name": k, "pts": v}
                                   for k, v in self._curves.items()]

    def result(self, rec):
        with self.lock:
            self.data["results"].append(rec)
