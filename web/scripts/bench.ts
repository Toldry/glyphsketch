/** Per-query latency of the TypeScript engine on the fixture drawings (Node). */

import { readFileSync } from "node:fs";

import { Recognizer, type Stroke } from "../src/index.ts";

const EXPORT_DIR = new URL("../../export/", import.meta.url);

function file(name: string): ArrayBuffer {
  const bytes = readFileSync(new URL(name, EXPORT_DIR));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

const loadStart = performance.now();
const recognizer = Recognizer.fromFiles(
  file("glyphsketch-model.bin"),
  file("glyphsketch-index.bin"),
  readFileSync(new URL("glyphsketch-charset.json", EXPORT_DIR), "utf-8"),
);
const loadMs = performance.now() - loadStart;
const cases = (JSON.parse(readFileSync(new URL("fixtures.json", EXPORT_DIR), "utf-8")) as {
  cases: { strokes: [number, number][][] }[];
}).cases;
const drawings: Stroke[][] = cases.map((fixture) => fixture.strokes.map((stroke) => stroke.map(([x, y]) => [x, y] as const)));

for (let round = 0; round < 3; round++) for (const drawing of drawings) recognizer.recognize(drawing);
const timings: Record<"rasterizeMs" | "encodeMs" | "rankMs" | "totalMs", number[]> = {
  rasterizeMs: [], encodeMs: [], rankMs: [], totalMs: [],
};
for (let round = 0; round < 8; round++) {
  for (const drawing of drawings) {
    const { timings: t } = recognizer.recognize(drawing);
    for (const key of Object.keys(timings) as (keyof typeof timings)[]) timings[key].push(t[key]);
  }
}
const median = (values: number[]): number => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)]!;
const p95 = (values: number[]): number => [...values].sort((a, b) => a - b)[Math.floor(values.length * 0.95)]!;
console.log(`load ${loadMs.toFixed(0)} ms; ${timings.totalMs.length} queries`);
for (const [key, values] of Object.entries(timings)) {
  console.log(`${key.padEnd(12)} median ${median(values).toFixed(1)} ms, p95 ${p95(values).toFixed(1)} ms`);
}
