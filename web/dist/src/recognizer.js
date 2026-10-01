/** The whole engine: strokes → tiles and ranked characters, with timings. */
import { parseCharset } from "./charset.js";
import { readIndex, similarities } from "./glyphIndex.js";
import { embed, readModel } from "./model.js";
import { Ranker } from "./ranking.js";
import { rasterize } from "./rasterize.js";
export const MODEL_FILE = "glyphsketch-model.bin";
export const INDEX_FILE = "glyphsketch-index.bin";
export const CHARSET_FILE = "glyphsketch-charset.json";
export class Recognizer {
    model;
    index;
    charset;
    ranker;
    constructor(model, index, charset) {
        if (model.embeddingDim !== index.dims || charset.embeddingDim !== index.dims) {
            throw new Error("Model, index and charset disagree on the embedding size");
        }
        this.model = model;
        this.index = index;
        this.charset = charset;
        this.ranker = new Ranker(index.codePoints, charset);
    }
    static fromFiles(model, index, charsetJson) {
        return new Recognizer(readModel(model), readIndex(index), parseCharset(charsetJson));
    }
    /** Load the three exported files from a base URL (ending in "/"). */
    static async load(baseUrl, fetcher = fetch) {
        const [model, index, charset] = await Promise.all([
            fetcher(new URL(MODEL_FILE, baseUrl)).then(ok).then((response) => response.arrayBuffer()),
            fetcher(new URL(INDEX_FILE, baseUrl)).then(ok).then((response) => response.arrayBuffer()),
            fetcher(new URL(CHARSET_FILE, baseUrl)).then(ok).then((response) => response.text()),
        ]);
        return Recognizer.fromFiles(model, index, charset);
    }
    scriptsFor(language) {
        return (language && this.charset.keyboardScripts[language]) || ["Latin"];
    }
    recognize(strokes, options = {}) {
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
function ok(response) {
    if (!response.ok)
        throw new Error(`${response.url}: HTTP ${response.status}`);
    return response;
}
//# sourceMappingURL=recognizer.js.map