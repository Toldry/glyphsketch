/** glyphsketch-charset.json: per-character metadata and the ranking settings. */
export function parseCharset(json) {
    const raw = JSON.parse(json);
    if (raw.format !== 1) {
        throw new Error(`Unsupported charset format ${raw.format}`);
    }
    const column = new Map(raw.columns.map((name, position) => [name, position]));
    const get = (row, name) => {
        const position = column.get(name);
        if (position === undefined)
            throw new Error(`Charset column ${name} is missing`);
        return row[position];
    };
    const characters = new Map();
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
export function displayText(info) {
    return info.generalCategory.startsWith("M") ? DOTTED_CIRCLE + info.char : info.char;
}
//# sourceMappingURL=charset.js.map