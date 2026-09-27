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

`demo/` holds the page. Draw with a mouse, pen or finger. Tap a tile to type it, and
long-press or right-click it for its look-alikes. The keyboard selector changes which member
a tile shows (Latin A or Greek Α). The page also shows the ranked candidates, the time per
query and the encoder's input image.

To build a personal test set, label a drawing (the top tile fills the label in), press
**Save drawing**, and later **Export JSON**. Drawings stay in the browser's local storage
until you export or delete them.
