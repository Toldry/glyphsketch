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

test("combining marks are shown on a dotted circle", async () => {
  const { displayText } = await import("../src/charset.ts");
  assert.equal(displayText({ char: "́", generalCategory: "Mn" }), "◌́");
  assert.equal(displayText({ char: "A", generalCategory: "Lu" }), "A");
});

test("the bounding-box rasterizer draws exactly what comparing every pixel draws", async () => {
  const { rasterizeSegments } = await import("../src/rasterize.ts");
  // The straightforward version: every pixel against every segment.
  const reference = (segments: Float64Array, size: number, penWidth: number): Uint8Array => {
    const image = new Uint8Array(size * size);
    for (let pixel = 0; pixel < size * size; pixel++) {
      const px = (pixel % size) + 0.5;
      const py = Math.floor(pixel / size) + 0.5;
      let nearest = Infinity;
      for (let index = 0; index < segments.length; index += 4) {
        const [ax, ay, bx, by] = [segments[index]!, segments[index + 1]!, segments[index + 2]!, segments[index + 3]!];
        const dx = bx - ax;
        const dy = by - ay;
        const lengthSquared = dx * dx + dy * dy;
        const t = Math.min(Math.max(lengthSquared > 0 ? ((px - ax) * dx + (py - ay) * dy) / lengthSquared : 0, 0), 1);
        nearest = Math.min(nearest, Math.hypot(px - (ax + t * dx), py - (ay + t * dy)));
      }
      const ink = Math.min(Math.max(penWidth / 2 + 0.5 - nearest, 0), 1);
      image[pixel] = Math.round(Math.fround(Math.fround(ink) * 255)); // halves don't occur here
    }
    return image;
  };
  let seed = 7;
  const random = (): number => ((seed = (seed * 16807) % 2147483647) / 2147483647) * 70 - 3;
  for (let drawing = 0; drawing < 20; drawing++) {
    const segments = Float64Array.from({ length: 4 * (1 + drawing * 3) }, random);
    // Some zero-length segments (taps).
    if (drawing % 4 === 0) segments.set([segments[0]!, segments[1]!], 2);
    assert.deepEqual(rasterizeSegments(segments, 64, 2.5), reference(segments, 64, 2.5), `drawing ${drawing}`);
  }
});
