import assert from "node:assert/strict";
import { test } from "node:test";

import { rasterize, simplifyStroke } from "../src/rasterize.ts";

test("a tap becomes a centred round dot", () => {
  const image = rasterize([[[5, 5]]]);
  assert.equal(image.length, 64 * 64);
  assert.equal(image[32 * 64 + 32], 255);
  assert.equal(image[0], 0);
  assert.equal(image[32 * 64 + 31], image[31 * 64 + 32]);
});

test("a horizontal line spans 7/8 of the image, plus its round caps", () => {
  const image = rasterize([[[0, 0], [100, 0]]]);
  const row = Array.from(image.subarray(32 * 64, 33 * 64));
  const inked = row.map((value, column) => (value > 127 ? column : -1)).filter((column) => column >= 0);
  assert.equal(inked[0], 3); // as training/src/glyphsketch/strokes.py at 64 px
  assert.equal(inked.at(-1), 60);
});

test("simplification keeps the corner and drops collinear points", () => {
  const points = [[0, 0], [1, 0], [2, 0], [2, 1], [2, 2]] as const;
  assert.deepEqual(simplifyStroke(points, 0.25), [[0, 0], [2, 0], [2, 2]]);
});

test("an empty drawing is rejected", () => {
  assert.throws(() => rasterize([[]]));
});
