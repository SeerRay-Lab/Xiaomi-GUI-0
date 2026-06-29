# Xiaomi-GUI-0 — Project Page

A static project page for the **Xiaomi-GUI-0** technical report, styled after
academic project pages (e.g. phonebuddyai.github.io) with Xiaomi branding.

## Files

```
website/
├── index.html        # the page (single page, anchor sections)
├── style.css         # all styling (Xiaomi orange #ff6700 theme)
├── script.js         # animated bar charts, scroll reveal, copy-citation
└── assets/
    ├── figs/          # report figures, converted from figs/*.pdf to PNG
    └── logo/          # Xiaomi + HuggingFace logos (PNG)
```

## Local preview

```bash
cd website
python3 -m http.server 8000
# open http://localhost:8000
```

## Deploy to GitHub Pages

**Option A — `docs/` folder on `main`:**
1. Copy the contents of `website/` into a `docs/` folder at the repo root.
2. In the repo: **Settings → Pages → Source: `main` branch, `/docs` folder**.

**Option B — dedicated `<user>.github.io` repo:**
1. Create a repo named `<username>.github.io`.
2. Copy the contents of `website/` to its root (so `index.html` is at the top level).
3. Push. The site goes live at `https://<username>.github.io/`.

## To wire up the report PDF

The **Technical Report** button currently points to `#` (shows a hint on click).
Drop the compiled PDF at `assets/Xiaomi-GUI-0.pdf` and update the button in
`index.html`:

```html
<a class="btn btn-dark" href="assets/Xiaomi-GUI-0.pdf" target="_blank">
  <span class="ico">📄</span> Technical Report
</a>
```
(Remove the `data-pdf` attribute once a real link is set.)

## Regenerating figures from the LaTeX source

```bash
# from the report root
for f in figs/*.pdf; do
  pdftoppm -png -r 200 "$f" "website/assets/figs/$(basename "$f" .pdf)"
done
# pdftoppm appends "-1"; strip it:
cd website/assets/figs && for f in *-1.png; do mv "$f" "${f%-1.png}.png"; done
```

## Editing numbers

- Tables live directly in `index.html` (`#results`).
- Bar-chart data lives in `script.js` (`realmobileData`, `androidworldData`).
  Keep the two in sync if you update results.
