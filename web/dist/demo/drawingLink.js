/**
 * Drawings in a URL parameter, so a drawing can be linked to. The value is "1" (the format)
 * followed by base64url bytes: per stroke, its point count, then each point as the change
 * from the previous point (across strokes) in tenths of a pad pixel. Numbers are zigzag
 * varints, so a typical drawing takes a few hundred characters.
 */
export const DRAWING_PARAMETER = "d";
const FORMAT = "1";
function writeVarint(bytes, value) {
    let rest = value;
    while (rest >= 0x80) {
        bytes.push((rest & 0x7f) | 0x80);
        rest = Math.floor(rest / 0x80);
    }
    bytes.push(rest);
}
const zigzag = (value) => (value >= 0 ? 2 * value : -2 * value - 1);
const unzigzag = (value) => (value % 2 === 0 ? value / 2 : -(value + 1) / 2);
function toBase64Url(bytes) {
    let binary = "";
    for (const byte of bytes)
        binary += String.fromCharCode(byte);
    return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}
function fromBase64Url(text) {
    const binary = atob(text.replaceAll("-", "+").replaceAll("_", "/"));
    return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}
/** Strokes (points rounded to 0.1) → the parameter's value. */
export function encodeDrawing(strokes) {
    const bytes = [];
    let previousX = 0;
    let previousY = 0;
    for (const stroke of strokes) {
        writeVarint(bytes, stroke.length);
        for (const [x, y] of stroke) {
            const tenthsX = Math.round(x * 10);
            const tenthsY = Math.round(y * 10);
            writeVarint(bytes, zigzag(tenthsX - previousX));
            writeVarint(bytes, zigzag(tenthsY - previousY));
            previousX = tenthsX;
            previousY = tenthsY;
        }
    }
    return FORMAT + toBase64Url(bytes);
}
/** The parameter's value → strokes, or null if it isn't a drawing this format can read. */
export function decodeDrawing(value) {
    if (!value.startsWith(FORMAT))
        return null;
    let bytes;
    try {
        bytes = fromBase64Url(value.slice(FORMAT.length));
    }
    catch {
        return null;
    }
    let offset = 0;
    const readVarint = () => {
        let result = 0;
        let factor = 1;
        while (offset < bytes.length) {
            const byte = bytes[offset++];
            result += (byte & 0x7f) * factor;
            if (byte < 0x80)
                return result;
            factor *= 0x80;
        }
        return null;
    };
    const strokes = [];
    let x = 0;
    let y = 0;
    while (offset < bytes.length) {
        const count = readVarint();
        if (count === null || count === 0)
            return null;
        const stroke = [];
        for (let index = 0; index < count; index++) {
            const dx = readVarint();
            const dy = readVarint();
            if (dx === null || dy === null)
                return null;
            x += unzigzag(dx);
            y += unzigzag(dy);
            stroke.push([x / 10, y / 10]);
        }
        strokes.push(stroke);
    }
    return strokes.length > 0 ? strokes : null;
}
//# sourceMappingURL=drawingLink.js.map