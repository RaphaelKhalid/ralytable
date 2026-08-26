/* Raly playground.
 *
 * The whole compiler front end runs in this tab. Every keystroke calls
 * `analyze` in the wasm module and gets back structured data: tokens with
 * spans, diagnostics with labelled spans and notes. Highlighting, squiggles,
 * tooltips and the caret-style panel are all rendered here from that data —
 * the only string the compiler renders for us is the caret block itself, so
 * what you read on this page is character-for-character what the CLI prints.
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  var srcEl = $('source');
  var hlEl = $('highlight');
  var diagListEl = $('diaglist');
  var tokBodyEl = $('tokbody');
  var jsonEl = $('jsonout');
  var tipEl = $('tip');

  var wasm = null;
  var latest = null;
  var marks = [];        // rendered <span> elements carrying a diagnostic
  var debounceId = 0;

  // ---------------------------------------------------------------- boot

  function fail(msg) {
    var box = document.createElement('div');
    box.className = 'boot-error';
    box.textContent = msg;
    document.querySelector('main').before(box);
  }

  function decodeBase64(b64) {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
  }

  function boot() {
    if (typeof wasm_bindgen !== 'function') {
      fail('The wasm glue did not load. Run playground/build.sh to regenerate wasm/.');
      return;
    }
    if (typeof window.RALY_WASM_BASE64 !== 'string') {
      fail('The embedded wasm payload is missing. Run playground/build.sh to regenerate wasm/.');
      return;
    }
    try {
      wasm_bindgen.initSync({ module: decodeBase64(window.RALY_WASM_BASE64) });
      wasm = wasm_bindgen;
    } catch (e) {
      fail('WebAssembly failed to start: ' + e);
      return;
    }
    $('ver').textContent = 'raly ' + wasm.version() + ' · wasm';
    start();
  }

  // ------------------------------------------------------------- escaping

  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ------------------------------------------------------- offset mapping
  //
  // The compiler counts bytes; JavaScript strings count UTF-16 code units.
  // For ASCII the two agree, which is exactly why getting this wrong is easy
  // to miss — and the homoglyph examples, where every interesting character is
  // multi-byte, are where it shows. `byteMap[b]` is the string index that byte
  // offset `b` falls inside.

  var byteMap = null;

  function buildByteMap(text) {
    var byteLen = 0;
    var i, cp;
    for (i = 0; i < text.length;) {
      cp = text.codePointAt(i);
      byteLen += cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
      i += cp > 0xffff ? 2 : 1;
    }
    var map = new Int32Array(byteLen + 1);
    var b = 0;
    for (i = 0; i < text.length;) {
      cp = text.codePointAt(i);
      var n = cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4;
      for (var k = 0; k < n; k++) map[b + k] = i;
      b += n;
      i += cp > 0xffff ? 2 : 1;
    }
    map[byteLen] = text.length;
    return map;
  }

  function jsIdx(byteOffset) {
    if (!byteMap) return byteOffset;
    if (byteOffset < 0) return 0;
    if (byteOffset >= byteMap.length) return byteMap[byteMap.length - 1];
    return byteMap[byteOffset];
  }

  // ---------------------------------------------------- highlight + marks
  //
  // Tokens give the colour; diagnostic labels give the underline. The two sets
  // of spans do not nest, so the source is cut at the union of every boundary
  // and each resulting slice carries whichever classes cover it.

  function renderHighlight(text, analysis) {
    var cuts = { 0: true };
    cuts[text.length] = true;

    var i, j;
    var tokens = analysis.tokens;
    for (i = 0; i < tokens.length; i++) {
      cuts[jsIdx(tokens[i].span.start)] = true;
      cuts[jsIdx(tokens[i].span.end)] = true;
    }

    // Every label, flattened, remembering which diagnostic it came from.
    var labels = [];
    for (i = 0; i < analysis.diagnostics.length; i++) {
      var d = analysis.diagnostics[i];
      for (j = 0; j < d.labels.length; j++) {
        var l = d.labels[j];
        // Zero-width labels (end of file, end of line) still need a target to
        // hover, so widen them by one character where there is one.
        var s = jsIdx(l.span.start);
        var e = jsIdx(l.span.end);
        if (e <= s) e = Math.min(text.length, s + 1);
        if (e <= s && s > 0) s = s - 1;
        labels.push({ start: s, end: e, style: l.style, message: l.message, diag: i });
        cuts[s] = true;
        cuts[e] = true;
      }
    }

    var points = Object.keys(cuts).map(Number).sort(function (a, b) { return a - b; });

    var html = '';
    marks = [];
    var markPlan = [];

    for (i = 0; i + 1 < points.length; i++) {
      var from = points[i];
      var to = points[i + 1];
      if (to <= from) continue;
      var slice = text.slice(from, to);

      var cls = [];
      var tokClass = classAt(tokens, from);
      if (tokClass) cls.push('t-' + tokClass);

      var hit = null;
      for (j = 0; j < labels.length; j++) {
        if (labels[j].start <= from && labels[j].end >= to) {
          if (!hit || labels[j].style === 'primary') hit = labels[j];
        }
      }
      if (hit) {
        cls.push(hit.style === 'primary' ? 'm-primary' : 'm-secondary');
        var sev = analysis.diagnostics[hit.diag].severity;
        if (sev === 'warning') cls.push('m-warn');
        markPlan.push(hit);
      }

      html += '<span class="' + cls.join(' ') + '"' + (hit ? ' data-mark="' + markPlan.length + '"' : '') +
        '>' + esc(slice) + '</span>';
    }

    // A trailing newline collapses in the layer but not in the textarea; a
    // sentinel keeps the two the same height so scrolling stays in sync.
    html += '<span>​</span>';
    hlEl.innerHTML = html;

    var nodes = hlEl.querySelectorAll('[data-mark]');
    for (i = 0; i < nodes.length; i++) {
      marks.push({ el: nodes[i], label: markPlan[Number(nodes[i].getAttribute('data-mark')) - 1] });
    }
  }

  function classAt(tokens, offset) {
    // Tokens are in source order and never overlap; a linear scan over a
    // screenful of code is cheaper than the bookkeeping to avoid it.
    for (var i = 0; i < tokens.length; i++) {
      var start = jsIdx(tokens[i].span.start);
      var end = jsIdx(tokens[i].span.end);
      if (start <= offset && offset < end) return tokens[i].class;
      if (start > offset) break;
    }
    return null;
  }

  // --------------------------------------------------------- caret output
  //
  // `rendered` is the compiler's own ASCII output. The only liberty taken is
  // bolding the caret/underline row so it reads on a screen; the bytes of the
  // text itself are untouched.

  function renderCaretBlock(rendered) {
    var lines = rendered.replace(/\s+$/, '').split('\n');
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      var line = esc(lines[i]);
      // Bold the underline row: a gutter `|` followed by a run of ^ or -.
      out.push(line.replace(/(\|\s*)((?:\^|-)+)/, '$1<b>$2</b>'));
    }
    return out.join('\n');
  }

  function renderDiagnostics(analysis) {
    diagListEl.textContent = '';

    if (!analysis.diagnostics.length) {
      var empty = document.createElement('div');
      empty.className = 'empty';
      var big = document.createElement('div');
      big.className = 'big';
      big.textContent = analysis.counts.tokens
        ? 'Lexed clean — ' + analysis.counts.tokens + ' tokens, no diagnostics'
        : 'Nothing to lex yet';
      var sub = document.createElement('div');
      sub.className = 'sub';
      sub.textContent = 'The parser and type system are not built, so this is as far as the compiler goes.';
      empty.appendChild(big);
      empty.appendChild(sub);
      diagListEl.appendChild(empty);
      return;
    }

    analysis.diagnostics.forEach(function (d, idx) {
      var card = document.createElement('div');
      card.className = 'diag sev-' + d.severity;
      card.tabIndex = 0;
      card.setAttribute('role', 'button');
      card.title = d.codeDescription;

      var head = document.createElement('div');
      head.className = 'diag-head';

      var sev = document.createElement('span');
      sev.className = 'sev';
      sev.textContent = d.severity;

      var code = document.createElement('span');
      code.className = 'code';
      code.textContent = d.code;

      var msg = document.createElement('span');
      msg.className = 'diag-msg';
      msg.textContent = d.message;

      head.appendChild(sev);
      head.appendChild(code);
      head.appendChild(msg);

      if (d.focus) {
        var at = document.createElement('span');
        at.className = 'diag-at';
        at.textContent = d.focus.line + ':' + d.focus.column;
        head.appendChild(at);
      }

      var pre = document.createElement('pre');
      pre.innerHTML = renderCaretBlock(d.rendered);

      card.appendChild(head);
      card.appendChild(pre);

      var jump = function () { jumpTo(d, idx); };
      card.addEventListener('click', jump);
      card.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); jump(); }
      });

      diagListEl.appendChild(card);
    });
  }

  function jumpTo(d, idx) {
    if (!d.focus) return;
    var start = jsIdx(d.focus.start);
    var end = Math.max(jsIdx(d.focus.end), start + 1);
    srcEl.focus();
    srcEl.setSelectionRange(start, Math.min(end, srcEl.value.length));
    scrollOffsetIntoView(idx);
    updatePosition();
  }

  function scrollOffsetIntoView(diagIdx) {
    for (var i = 0; i < marks.length; i++) {
      if (marks[i].label.diag === diagIdx) {
        var r = marks[i].el.getBoundingClientRect();
        if (r.top < 60 || r.bottom > window.innerHeight - 40) {
          window.scrollBy({ top: r.top - window.innerHeight / 3, behavior: 'smooth' });
        }
        marks[i].el.classList.add('m-flash');
        (function (el) { setTimeout(function () { el.classList.remove('m-flash'); }, 900); })(marks[i].el);
        return;
      }
    }
  }

  // -------------------------------------------------------------- tokens

  function renderTokens(analysis) {
    var rows = '';
    var tokens = analysis.tokens;
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      if (t.kind === 'Eof') continue;
      var text = t.text.replace(/\t/g, '↹').replace(/\n/g, '⏎');
      rows += '<tr><td class="t-' + t.class + '">' + esc(t.kind) + '</td>' +
        '<td class="txt">' + esc(text) + '</td>' +
        '<td class="num">' + t.span.start + '‥' + t.span.end + '</td>' +
        '<td class="num">' + t.span.line + ':' + t.span.column + '</td></tr>';
    }
    tokBodyEl.innerHTML = rows || '<tr><td colspan="4" style="color:var(--fg-faint)">no tokens</td></tr>';
  }

  // -------------------------------------------------------------- tooltip

  function hideTip() { tipEl.classList.remove('on'); }

  function showTip(x, y, label, diag) {
    tipEl.textContent = '';
    var code = document.createElement('span');
    code.className = 'tip-code';
    code.textContent = diag.code + ' · ' + diag.severity + ' · ' + label.style;
    tipEl.appendChild(code);
    tipEl.appendChild(document.createTextNode(label.message || diag.message));
    tipEl.classList.add('on');

    var r = tipEl.getBoundingClientRect();
    var left = Math.min(Math.max(8, x - r.width / 2), window.innerWidth - r.width - 8);
    var top = y - r.height - 12;
    if (top < 8) top = y + 20;
    tipEl.style.left = left + 'px';
    tipEl.style.top = top + 'px';
  }

  function hitTest(x, y) {
    for (var i = 0; i < marks.length; i++) {
      var rects = marks[i].el.getClientRects();
      for (var j = 0; j < rects.length; j++) {
        var r = rects[j];
        if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return marks[i];
      }
    }
    return null;
  }

  // --------------------------------------------------------------- status

  function updatePosition() {
    var upto = srcEl.value.slice(0, srcEl.selectionStart);
    var nl = upto.lastIndexOf('\n');
    var line = upto.split('\n').length;
    var col = Array.from(upto.slice(nl + 1)).length + 1;
    $('st-pos').textContent = line + ':' + col;
  }

  // -------------------------------------------------------------- analyse

  function analyseNow() {
    var text = srcEl.value;
    var t0 = performance.now();
    var analysis;
    try {
      analysis = wasm.analyze(text);
    } catch (e) {
      fail('analyze() threw: ' + e);
      return;
    }
    var ms = performance.now() - t0;
    latest = analysis;
    byteMap = buildByteMap(text);

    renderHighlight(text, analysis);
    renderDiagnostics(analysis);
    renderTokens(analysis);
    jsonEl.textContent = JSON.stringify(analysis, null, 2);

    var c = analysis.counts;
    $('st-tokens').textContent = c.tokens + (c.tokens === 1 ? ' token' : ' tokens') +
      ' · ' + c.lines + (c.lines === 1 ? ' line' : ' lines');
    var ds = $('st-diags');
    if (c.errors || c.warnings) {
      ds.className = 'err';
      var bits = [];
      if (c.errors) bits.push(c.errors + (c.errors === 1 ? ' error' : ' errors'));
      if (c.warnings) bits.push(c.warnings + (c.warnings === 1 ? ' warning' : ' warnings'));
      ds.textContent = bits.join(', ');
    } else {
      ds.className = 'ok';
      ds.textContent = 'no errors';
    }
    $('st-time').textContent = ms.toFixed(1) + ' ms';

    var p = analysis.phases;
    $('phase').textContent = 'lex ' + p.lex + ' · parse ' + p.parse.replace('not-implemented', 'not built');

    syncScroll();
  }

  function schedule() {
    clearTimeout(debounceId);
    debounceId = setTimeout(analyseNow, 90);
  }

  function syncScroll() {
    hlEl.scrollTop = srcEl.scrollTop;
    hlEl.scrollLeft = srcEl.scrollLeft;
  }

  // ------------------------------------------------------------- examples

  function buildExamples() {
    var bar = $('examples');
    (window.RALY_EXAMPLES || []).forEach(function (ex, i) {
      var b = document.createElement('button');
      b.className = 'chip';
      b.type = 'button';
      b.textContent = ex.name;
      b.title = ex.blurb;
      b.setAttribute('aria-pressed', i === 0 ? 'true' : 'false');
      b.addEventListener('click', function () {
        var all = bar.querySelectorAll('.chip');
        for (var k = 0; k < all.length; k++) all[k].setAttribute('aria-pressed', 'false');
        b.setAttribute('aria-pressed', 'true');
        srcEl.value = ex.source;
        srcEl.setSelectionRange(0, 0);
        analyseNow();
        updatePosition();
      });
      bar.appendChild(b);
    });
  }

  // ----------------------------------------------------------------- tabs

  function wireTabs() {
    var tabs = document.querySelectorAll('.tab');
    for (var i = 0; i < tabs.length; i++) {
      (function (tab) {
        tab.addEventListener('click', function () {
          for (var k = 0; k < tabs.length; k++) {
            tabs[k].setAttribute('aria-selected', 'false');
            $(tabs[k].getAttribute('aria-controls')).classList.remove('active');
          }
          tab.setAttribute('aria-selected', 'true');
          $(tab.getAttribute('aria-controls')).classList.add('active');
        });
      })(tabs[i]);
    }
  }

  // ----------------------------------------------------------------- init

  function start() {
    buildExamples();
    wireTabs();

    srcEl.addEventListener('input', schedule);
    srcEl.addEventListener('scroll', syncScroll);
    srcEl.addEventListener('keyup', updatePosition);
    srcEl.addEventListener('click', updatePosition);
    srcEl.addEventListener('select', updatePosition);

    // Tab inserts four spaces rather than leaving the editor.
    srcEl.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Tab' || ev.ctrlKey || ev.metaKey || ev.altKey) return;
      ev.preventDefault();
      var s = srcEl.selectionStart;
      var e = srcEl.selectionEnd;
      srcEl.value = srcEl.value.slice(0, s) + '    ' + srcEl.value.slice(e);
      srcEl.setSelectionRange(s + 4, s + 4);
      analyseNow();
      updatePosition();
    });

    srcEl.addEventListener('mousemove', function (ev) {
      var hit = hitTest(ev.clientX, ev.clientY);
      if (hit && latest) showTip(ev.clientX, ev.clientY, hit.label, latest.diagnostics[hit.label.diag]);
      else hideTip();
    });
    srcEl.addEventListener('mouseleave', hideTip);
    window.addEventListener('scroll', hideTip, { passive: true });

    srcEl.value = (window.RALY_EXAMPLES && window.RALY_EXAMPLES[0]) ? window.RALY_EXAMPLES[0].source : '';
    analyseNow();
    updatePosition();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
