/** Parity with the Python reference: export/fixtures.json (see docs/export_format.md). */

import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { embed, rasterize, Recognizer, similarities, type Stroke } from "../src/index.ts";

const EXPORT_DIR = new URL("../../export/", import.meta.url);
const TOLERANCE = 1e-4;

interface FixtureTile {
  representative: number;
  members: number[];
  score: number;
}

interface FixtureCase {
  label: string;
  strokes: [number, number][][];
  image_uint8_base64: string;
  embedding: number[];
  top_characters: number[];
  top_scores: number[];
  tiles: Record<string, FixtureTile[]>;
}

function file(name: string): ArrayBuffer {
  const bytes = readFileSync(new URL(name, EXPORT_DIR));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

// The export is committed with the final encoder; until then it exists only after running
// the export stage locally.
const available = existsSync(new URL("fixtures.json", EXPORT_DIR));
const recognizer = available
  ? Recognizer.fromFiles(
      file("glyphsketch-model.bin"),
      file("glyphsketch-index.bin"),
      readFileSync(new URL("glyphsketch-charset.json", EXPORT_DIR), "utf-8"),
    )
  : (null as unknown as Recognizer);
const fixtures = available
  ? (JSON.parse(readFileSync(new URL("fixtures.json", EXPORT_DIR), "utf-8")) as { cases: FixtureCase[] })
  : { cases: [] };

if (!available) {
  test("parity fixtures", { skip: "export/ has no exported files; run the export stage" }, () => {});
}

function expectedImage(fixture: FixtureCase): Uint8Array {
  return new Uint8Array(Buffer.from(fixture.image_uint8_base64, "base64"));
}

/** Same ranking, allowing neighbours whose expected scores differ by less than TOLERANCE to swap. */
function assertSameRanking(actual: number[], expected: number[], scores: number[], label: string): void {
  for (let position = 0; position < expected.length; position++) {
    if (actual[position] === expected[position]) continue;
    const swapped = expected.indexOf(actual[position]!);
    assert.ok(
      swapped >= 0 && Math.abs(scores[swapped]! - scores[position]!) < TOLERANCE,
      `${label}: position ${position} is U+${actual[position]?.toString(16)}, expected U+${expected[position]?.toString(16)}`,
    );
  }
}

for (const fixture of fixtures.cases) {
  test(`fixture ${fixture.label}`, () => {
    const strokes: Stroke[] = fixture.strokes.map((stroke) => stroke.map(([x, y]) => [x, y] as const));
    const expected = expectedImage(fixture);
    const image = rasterize(strokes, recognizer.charset.rasterization);
    let maxPixelDifference = 0;
    for (let index = 0; index < image.length; index++) {
      maxPixelDifference = Math.max(maxPixelDifference, Math.abs(image[index]! - expected[index]!));
    }
    assert.ok(maxPixelDifference <= 1, `image differs by ${maxPixelDifference}`);

    // From the expected image on, so a one-level pixel difference can't mask a model bug.
    const embedding = embed(recognizer.model, expected);
    fixture.embedding.forEach((value, dim) => {
      assert.ok(Math.abs(embedding[dim]! - value) < TOLERANCE, `embedding[${dim}]`);
    });

    const scores = similarities(recognizer.index, embedding);
    const top = recognizer.ranker.topCharacters(scores, fixture.top_characters.length);
    top.forEach((candidate, position) => {
      const expectedScore = fixture.top_scores[fixture.top_characters.indexOf(candidate.codePoint)];
      assert.ok(expectedScore !== undefined && Math.abs(candidate.score - expectedScore) < TOLERANCE,
        `score of U+${candidate.codePoint.toString(16)} at ${position}`);
    });
    assertSameRanking(top.map((candidate) => candidate.codePoint), fixture.top_characters,
      fixture.top_scores, fixture.label);

    for (const [script, expectedTiles] of Object.entries(fixture.tiles)) {
      const tiles = recognizer.ranker.tiles(scores, expectedTiles.length, [script]);
      assert.deepEqual(tiles.map((tile) => tile.members), expectedTiles.map((tile) => tile.members),
        `${script} tiles`);
    }
  });
}

test("recognize runs the whole pipeline and times it", { skip: !available }, () => {
  const fixture = fixtures.cases[0]!;
  const strokes: Stroke[] = fixture.strokes.map((stroke) => stroke.map(([x, y]) => [x, y] as const));
  const result = recognizer.recognize(strokes, { language: "el" });
  assert.equal(result.tiles.length, 5);
  assert.deepEqual(result.tiles[0]!.members, fixture.tiles["Greek"]![0]!.members);
  assert.ok(result.timings.totalMs >= result.timings.encodeMs);
});

test("a group's members come in code point order", { skip: !available }, () => {
  const group = recognizer.charset.characters.get(0x41)!.group;
  const members = recognizer.ranker.members(group);
  assert.ok(members.includes(0x41) && members.includes(0x391) && members.includes(0x410));
  assert.deepEqual(members, [...members].sort((a, b) => a - b));
  assert.equal(members[0], 0x41);
});
