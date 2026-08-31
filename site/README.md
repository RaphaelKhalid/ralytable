# site/

The public Ralytable website. It uses static files and has no build step or runtime dependencies.

```
site/
├── index.html             project overview and demos
├── research.html          summary of the latest coding experiment
├── interpretability.html  interactive codebook explorer
├── blind-test.html        story-model comparison
├── codebook.json          generated data for the codebook explorer
└── data/                   checked-in data for the latest-run panel
```

## Serve it

Opening `site/index.html` directly with `file://` works for everything except the
playground link check (see below). To serve properly:

```
python -m http.server 8000 --directory site
```

then visit <http://localhost:8000>.

Any static server works — `npx serve site`, `caddy file-server --root site`, etc.

## Deploy it

Because the site is static and has no build step, any static host will work.

**GitHub Pages.** Settings → Pages → Deploy from a branch, and either publish the
`docs/` folder (rename `site/` to `docs/`) or push `site/`'s contents to a
`gh-pages` branch:

```
git subtree push --prefix site origin gh-pages
```

**Cloudflare Pages / Netlify / Vercel.** Build command: none. Output directory:
`site`. The deployable `web/` copy is synchronized from `site/` for the current
repository layout.

## Conventions this page keeps

- **No external requests except Google Fonts.** `fonts.googleapis.com` and
  `fonts.gstatic.com` are the only hosts contacted. There are no CDN scripts,
  analytics requests, or remote images. Each font has a local fallback stack.
- **Dark by default, theme-aware.** `data-theme="dark"` is on `<html>`; a full
  light palette is defined for `prefers-color-scheme: light`, so the page is never
  a dark card on a white host.
- **Motion is reveal-on-scroll only**, and it is disabled entirely under
  `prefers-reduced-motion: reduce`, which also short-circuits the
  `IntersectionObserver` path so nothing stays invisible.
- **No horizontal page scroll.** Wide content — the diagnostics, the code
  comparisons — scrolls inside its own `overflow-x: auto` panel. Caret alignment in
  the rendered diagnostics depends on `white-space: pre` and a real monospace
  face; do not let those panels wrap.
- **Keep claims tied to evidence.** Every number on the page is reproducible from
  this repository. The `RALY1002` diagnostic in the hero is character-for-character
  what `cargo run -p raly -- check examples/broken.raly` prints today. The
  `RALY5001` capacity diagnostic is a *design* and is labelled as one in three
  places. Anything not yet built must be described as planned or missing on the
  page itself, not only in the commit message.

## Playground

The hero links to `./playground/`, which is being built separately. The link is
non-breaking: a `HEAD` request on load falls back to the GitHub directory and
relabels the button if the playground is not deployed alongside this page. Under
`file://` the check is skipped and the link is left as-is.
