/** The whole engine: strokes → tiles and ranked characters, with timings. */

import { type Charset, parseCharset } from "./charset.ts";
import { type GlyphIndex, readIndex, similarities } from "./glyphIndex.ts";
import { embed, type Model, readModel } from "./model.ts";
import { type Candidate, Ranker, type Tile } from "./ranking.ts";
import { rasterize, type Stroke } from "./rasterize.ts";

export const MODEL_FILE = "glyphsketch-model.bin";
export const INDEX_FILE = "glyphsketch-index.bin";
export const CHARSET_FILE = "glyphsketch-charset.json";

export interface RecognizeOptions {
  /** Keyboard language (a key of `charset.keyboardScripts`); decides tile representatives. */
  language?: string;
  tiles?: number;
  characters?: number;
}

export interface Recognition {
  tiles: Tile[];
  characters: Candidate[];
  image: Uint8Array;
  timings: { rasterizeMs: number; encodeMs: number; rankMs: number; totalMs: number };
}

export class Recognizer {
  readonly model: Model;
  readonly index: GlyphIndex;
  readonly charset: Charset;
  readonly ranker: Ranker;

  constructor(model: Model, index: GlyphIndex, charset: Charset) {
    if (model.embeddingDim !== index.dims || charset.embeddingDim !== index.dims) {
      throw new Error("Model, index and charset disagree on the embedding size");
    }
    this.model = model;
    this.index = index;
    this.charset = charset;
    this.ranker = new Ranker(index.codePoints, charset);
  }

  static fromFiles(model: ArrayBuffer, index: ArrayBuffer, charsetJson: string): Recognizer {
    return new Recognizer(readModel(model), readIndex(index), parseCharset(charsetJson));
  }

  /** Load the three exported files from a base URL (ending in "/"). */
  static async load(baseUrl: string, fetcher: typeof fetch = fetch): Promise<Recognizer> {
    const [model, index, charset] = await Promise.all([
      fetcher(new URL(MODEL_FILE, baseUrl)).then(ok).then((response) => response.arrayBuffer()),
      fetcher(new URL(INDEX_FILE, baseUrl)).then(ok).then((response) => response.arrayBuffer()),
      fetcher(new URL(CHARSET_FILE, baseUrl)).then(ok).then((response) => response.text()),
    ]);
    return Recognizer.fromFiles(model, index, charset);
  }

  scriptsFor(language: string | undefined): string[] {
    return (language && this.charset.keyboardScripts[language]) || ["Latin"];
  }

  recognize(strokes: readonly Stroke[], options: RecognizeOptions = {}): Recognition {
    const start = performance.now();
    const image = rasterize(strokes, this.charset.rasterization);
    const rasterized = performance.now();
    const embedding = embed(this.model, image);
    const encoded = performance.now();
    const ranking = this.ranker.rank(similarities(this.index, embedding));
    const tiles = this.ranker.tiles(ranking, options.tiles ?? 5, this.scriptsFor(options.language));
    const characters = this.ranker.topCharacters(ranking, options.characters ?? 10);
    const ranked = performance.now();
    return {
      tiles,
      characters,
      image,
      timings: {
        rasterizeMs: rasterized - start,
        encodeMs: encoded - rasterized,
        rankMs: ranked - encoded,
        totalMs: ranked - start,
      },
    };
  }
}

function ok(response: Response): Response {
  if (!response.ok) throw new Error(`${response.url}: HTTP ${response.status}`);
  return response;
}
