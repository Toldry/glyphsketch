import assert from "node:assert/strict";
import { test } from "node:test";

import { decodeDrawing, encodeDrawing } from "../demo/drawingLink.ts";

test("a drawing survives the round trip through a link, to 0.1 pixel", () => {
  const strokes = [
    [[10.04, 20], [30.5, 25.25], [300, 0]],
    [[5, 5]],
    [[0, 339.9], [12.3, 1.1]],
  ] as const;
  const value = encodeDrawing(strokes);
  assert.match(value, /^1[A-Za-z0-9_-]+$/);
  assert.deepEqual(decodeDrawing(value), [
    [[10, 20], [30.5, 25.3], [300, 0]],
    [[5, 5]],
    [[0, 339.9], [12.3, 1.1]],
  ]);
});

test("links that aren't drawings are rejected", () => {
  assert.equal(decodeDrawing(""), null);
  assert.equal(decodeDrawing("2abc"), null);
  assert.equal(decodeDrawing("1"), null);
  assert.equal(decodeDrawing("1gA"), null); // a truncated varint
});
