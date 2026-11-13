# Overview page

A static, one-page overview of the repo family: vision, building blocks,
ideas, a worked example and a link to the
[Warehouse Designer](https://rhinos07.github.io/Warehouse-Designer/).
It has no build step and no server. `.github/workflows/pages.yaml`
publishes this folder with GitHub Pages.

The page is a map like the root `README.md`. Where the two disagree, the
README and the sibling repos win.

## Files

| File | Content |
|---|---|
| `index.html` | The page, including the mascot "Rho" and the icons as inline SVG |
| `style.css` | The "sketchbook" look: grid paper, hand-written headings, sticky notes |
| `diagram.js` | Draws the building-blocks diagram with Rough.js |
| `vendor/rough-4.6.6.js` | [Rough.js](https://roughjs.com/) 4.6.6, MIT, see `vendor/rough-LICENSE.txt` |
| `fonts/` | Caveat, Inter and JetBrains Mono (latin subset, from Fontsource), SIL OFL 1.1, see `fonts/OFL-*.txt` |

The fonts and Rough.js are stored here on purpose, so the page loads
nothing from third-party servers.

## Preview locally

```sh
python -m http.server --directory site 8000
```

Then open http://localhost:8000.
