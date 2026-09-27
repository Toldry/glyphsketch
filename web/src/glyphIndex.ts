/**
 * Reader and scoring for glyphsketch-index.bin (spec: docs/export_format.md). A character's
 * similarity is its best dot product over its vectors (one per font).
 */

import { checkMagic, Reader } from "./model.ts";

const INDEX_MAGIC = "GSKI";
const FORMAT_VERSION = 1;

export interface GlyphIndex {
  dims: number;
  codePoints: Uint32Array;
  starts: Uint32Array;
  scales: Float32Array;
  values: Int8Array;
}

export function readIndex(buffer: ArrayBuffer): GlyphIndex {
  const reader = new Reader(buffer);
  checkMagic(reader, INDEX_MAGIC, "index");
  const version = reader.u16();
  if (version !== FORMAT_VERSION) {
    throw new Error(`Unsupported index format version ${version}`);
  }
  const dims = reader.u16();
  const characters = reader.u32();
  const vectors = reader.u32();
  const codePoints = Uint32Array.from({ length: characters }, () => reader.u32());
  const starts = Uint32Array.from({ length: characters }, () => reader.u32());
  const scales = reader.float32(vectors);
  const values = reader.int8(vectors * dims);
  if (reader.offset !== reader.length) {
    throw new Error("Trailing bytes after the index vectors");
  }
  return { dims, codePoints, starts, scales, values };
}

/** Similarity of the embedding to every character, in the index's order. */
export function similarities(index: GlyphIndex, embedding: Float32Array): Float32Array {
  const { dims, starts, scales, values } = index;
  if (embedding.length !== dims) {
    throw new Error(`Expected a ${dims}-dimensional embedding`);
  }
  const vectorCount = scales.length;
  const result = new Float32Array(starts.length);
  for (let character = 0; character < starts.length; character++) {
    const end = character + 1 < starts.length ? starts[character + 1]! : vectorCount;
    let best = -Infinity;
    for (let vector = starts[character]!; vector < end; vector++) {
      let dot = 0;
      const offset = vector * dims;
      for (let dim = 0; dim < dims; dim++) dot += values[offset + dim]! * embedding[dim]!;
      dot *= scales[vector]!;
      if (dot > best) best = dot;
    }
    result[character] = best;
  }
  return result;
}
