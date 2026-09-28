/** glyphsketch-charset.json: per-character metadata and the ranking settings. */

import type { RasterizationSettings } from "./rasterize.ts";

export interface CharacterInfo {
  codePoint: number;
  char: string;
  name: string;
  block: string;
  script: string;
  generalCategory: string;
  group: number;
  logPrior: number;
}

export interface Charset {
  unicodeVersion: string;
  inputSize: number;
  embeddingDim: number;
  rasterization: RasterizationSettings;
  priorWeight: number;
  keyboardScripts: Record<string, string[]>;
  characters: Map<number, CharacterInfo>;
  attribution: string[];
}

interface RawCharset {
  format: number;
  unicode_version: string;
  input_size: number;
  embedding_dim: number;
  rasterization: {
    content_fraction: number;
    pen_width_fraction: number;
    simplify_tolerance_pixels: number;
  };
  ranking: { prior_weight: number };
  keyboard_scripts: Record<string, string[]>;
  columns: string[];
  characters: (string | number)[][];
  attribution: string[];
}

export function parseCharset(json: string): Charset {
  const raw = JSON.parse(json) as RawCharset;
  if (raw.format !== 1) {
    throw new Error(`Unsupported charset format ${raw.format}`);
  }
  const column = new Map(raw.columns.map((name, position) => [name, position]));
  const get = (row: (string | number)[], name: string): string | number => {
    const position = column.get(name);
    if (position === undefined) throw new Error(`Charset column ${name} is missing`);
    return row[position]!;
  };
  const characters = new Map<number, CharacterInfo>();
  for (const row of raw.characters) {
    const codePoint = Number(get(row, "code_point"));
    characters.set(codePoint, {
      codePoint,
      char: String.fromCodePoint(codePoint),
      name: String(get(row, "name")),
      block: String(get(row, "block")),
      script: String(get(row, "script")),
      generalCategory: String(get(row, "general_category")),
      group: Number(get(row, "group")),
      logPrior: Number(get(row, "log_prior")),
    });
  }
  return {
    unicodeVersion: raw.unicode_version,
    inputSize: raw.input_size,
    embeddingDim: raw.embedding_dim,
    rasterization: {
      imageSize: raw.input_size,
      contentFraction: raw.rasterization.content_fraction,
      penWidthFraction: raw.rasterization.pen_width_fraction,
      simplifyTolerancePixels: raw.rasterization.simplify_tolerance_pixels,
    },
    priorWeight: raw.ranking.prior_weight,
    keyboardScripts: raw.keyboard_scripts,
    characters,
    attribution: raw.attribution,
  };
}

export const DOTTED_CIRCLE = "\u25CC";

/** How to show a character on its own: a combining mark (general category M…) sits on a
 * dotted circle, ◌́, so it is visible. Typing inserts the bare character. */
export function displayText(info: Pick<CharacterInfo, "char" | "generalCategory">): string {
  return info.generalCategory.startsWith("M") ? DOTTED_CIRCLE + info.char : info.char;
}
