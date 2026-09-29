# web

TypeScript inference engine and a demo page (drawing canvas → result tiles and candidates).
The engine has no runtime dependencies and runs the files in `../export/` as specified in
`../docs/export_format.md`.

## Commands

Run these in `web/` (Node 24 or later):

```sh
npm ci              # install the locked dev tools (the TypeScript compiler)
npm test            # parity tests against export/fixtures.json, and unit tests
npm run typecheck
npm run bench       # per-query latency on the fixture drawings
npm run serve       # build, then serve the demo at http://localhost:5173/web/demo/
```

In the devcontainer, VS Code forwards port 5173, so the demo opens in your normal browser.
The tests and the demo need an export: run `uv run python -m glyphsketch.pipeline export`
in `training/` if `export/` has no `.bin` files yet.

## Library

```ts
import { Recognizer } from "./dist/src/index.js";

const recognizer = await Recognizer.load("https://example.org/glyphsketch/export/");
const { tiles, characters, timings } = recognizer.recognize(
  [[[10, 10], [50, 90]], [[50, 90], [90, 10]]], // strokes of [x, y] points, y down
  { language: "en" }, // a key of recognizer.charset.keyboardScripts
);
// tiles[0].representative is the code point to show; tiles[0].members opens the chooser.
```

Source files: `src/rasterize.ts` (strokes → 64×64 image), `src/model.ts` (the encoder),
`src/glyphIndex.ts` (similarities), `src/ranking.ts` (prior and tiles),
`src/charset.ts` (metadata) and `src/recognizer.ts` (all of it together).

## Demo

`demo/` holds the page. Draw with a mouse, pen or finger. The candidates table (10 to 100
rows) ranks every character by score; click a character to type it, 📋 to copy it, the
look-alikes button for the others in its group (code point order), and the link for its
unicodefyi page. **Link** puts the drawing in the page address (parameter `d`, see
`demo/drawingLink.ts`) and copies the link. The page also shows the time per query and the
encoder's input image.

To build a personal test set, label a drawing (the top candidate fills the label in), press
**Save drawing**, and later **Export JSON** (format 2: label, strokes, the top five
candidates, time). Drawings stay in the browser's local storage until you export or delete
them.

**Installing it as an app.** The page is a progressive web app: `manifest.webmanifest`
names it and points to the icons in `icons/` (made by `glyphsketch.tools.logo`), and
`sw.js` caches the page, the engine and the model so it works offline. On Android, open the
published demo in Chrome and choose *Add to Home screen* or *Install app*; on iOS, Safari's
Share → *Add to Home Screen*. Service workers need HTTPS or localhost. The site build
stamps the commit into `sw.js`, so each deploy replaces the installed files.

## Publishing

`npm run site` builds the static site into `dist/site/`: the demo page, the compiled
engine and the three shipped export files, laid out like the repository, plus a
`source.json` that the page uses to link its source code (AGPL-3.0). The `Pages` workflow
(`.github/workflows/pages.yml`) runs the tests, builds the site and force-pushes it as a
single commit to the `gh-pages` branch, which GitHub Pages serves.
