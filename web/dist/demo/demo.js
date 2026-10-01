/** The demo page: draw, see the ranked candidates, save labelled drawings locally. */
import { displayText, Recognizer, } from "../src/index.js";
import { DRAWING_PARAMETER, decodeDrawing, encodeDrawing } from "./drawingLink.js";
// Relative to the page (web/demo/), not to the compiled script in web/dist/demo/.
const EXPORT_URL = new URL("../../export/", document.baseURI);
const SAVED_KEY = "glyphsketch.labelledDrawings";
const CANDIDATE_COUNT_KEY = "glyphsketch.candidateCount";
const DETAILS_URL = "https://unicodefyi.com/char/";
const element = (id) => {
    const found = document.getElementById(id);
    if (!found)
        throw new Error(`Missing #${id}`);
    return found;
};
const pad = element("pad");
const inputCanvas = element("input");
const candidatesBody = element("candidates").tBodies[0];
const timings = element("timings");
const output = element("output");
const candidateCountSelect = element("candidate-count");
const chooser = element("chooser");
const labelInput = element("label");
const savedText = element("saved");
const strokes = [];
let current = null;
let recognizer = null;
let lastRecognition = null;
function storage(key, fallback) {
    try {
        const raw = localStorage.getItem(key);
        return raw === null ? fallback : JSON.parse(raw);
    }
    catch {
        return fallback;
    }
}
function store(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    }
    catch {
        // Private windows may refuse storage; the demo still works without it.
    }
}
function drawPad() {
    const context = pad.getContext("2d");
    const scale = pad.width / pad.getBoundingClientRect().width;
    context.clearRect(0, 0, pad.width, pad.height);
    context.lineCap = "round";
    context.lineJoin = "round";
    context.lineWidth = 6 * scale;
    context.strokeStyle = getComputedStyle(document.body).color;
    context.fillStyle = context.strokeStyle;
    for (const stroke of current ? [...strokes, current] : strokes) {
        if (stroke.length === 1) {
            context.beginPath();
            context.arc(stroke[0][0] * scale, stroke[0][1] * scale, 3 * scale, 0, 2 * Math.PI);
            context.fill();
            continue;
        }
        context.beginPath();
        stroke.forEach(([x, y], index) => index === 0 ? context.moveTo(x * scale, y * scale) : context.lineTo(x * scale, y * scale));
        context.stroke();
    }
}
function drawInputImage(image) {
    const context = inputCanvas.getContext("2d");
    const pixels = context.createImageData(64, 64);
    for (let index = 0; index < 64 * 64; index++) {
        const shade = 255 - (image?.[index] ?? 0);
        pixels.data.set([shade, shade, shade, 255], index * 4);
    }
    context.putImageData(pixels, 0, 0);
}
/** The character as shown on its own (combining marks on a dotted circle). */
function shown(codePoint) {
    const info = recognizer?.charset.characters.get(codePoint);
    return info ? displayText(info) : String.fromCodePoint(codePoint);
}
/** U+XXXX notation. */
function code(codePoint) {
    return `U+${codePoint.toString(16).toUpperCase().padStart(4, "0")}`;
}
function describe(codePoint) {
    return `${code(codePoint)} ${recognizer?.charset.characters.get(codePoint)?.name ?? ""}`;
}
/** The other members of a character's look-alike group, in code point order. */
function lookAlikes(codePoint) {
    const info = recognizer?.charset.characters.get(codePoint);
    if (!recognizer || !info)
        return [];
    return recognizer.ranker.members(info.group).filter((member) => member !== codePoint);
}
function cell(...children) {
    const td = document.createElement("td");
    td.append(...children);
    return td;
}
/** A name cell that shows the full name on hover when the column cuts it short. */
function nameCell(name) {
    const td = cell(name);
    td.title = name;
    return td;
}
function button(label, title, onClick) {
    const result = document.createElement("button");
    result.type = "button";
    result.textContent = label;
    result.title = title;
    result.setAttribute("aria-label", title);
    result.addEventListener("click", () => onClick(result));
    return result;
}
async function copy(codePoint, source) {
    try {
        await navigator.clipboard.writeText(String.fromCodePoint(codePoint));
        source.textContent = "✓";
    }
    catch {
        source.textContent = "✗"; // no clipboard access (e.g. not served over HTTPS)
    }
    setTimeout(() => (source.textContent = "📋"), 1200);
}
function type(codePoint) {
    output.value += String.fromCodePoint(codePoint);
    labelInput.value = String.fromCodePoint(codePoint);
}
function showChooser(members, anchor) {
    chooser.replaceChildren(...members.map((codePoint) => {
        const button = document.createElement("button");
        button.type = "button";
        const glyph = document.createElement("span");
        glyph.className = "char";
        glyph.textContent = shown(codePoint);
        const name = document.createElement("span");
        name.className = "name";
        name.textContent = describe(codePoint);
        button.append(glyph, name);
        button.addEventListener("click", () => {
            type(codePoint);
            chooser.hidden = true;
        });
        return button;
    }));
    const box = anchor.getBoundingClientRect();
    chooser.hidden = false;
    chooser.style.left = `${Math.max(16, Math.min(box.left, innerWidth - chooser.offsetWidth - 16))}px`;
    chooser.style.top = `${Math.max(16, Math.min(box.bottom + 4, innerHeight - chooser.offsetHeight - 16))}px`;
    chooser.scrollTop = 0;
}
function renderResults(recognition) {
    candidatesBody.replaceChildren();
    drawInputImage(recognition?.image ?? null);
    if (!recognition) {
        timings.textContent = recognizer ? "Draw a character." : timings.textContent;
        return;
    }
    recognition.characters.forEach((candidate, position) => {
        const { codePoint } = candidate;
        const row = document.createElement("tr");
        const glyph = button(shown(codePoint), describe(codePoint), () => type(codePoint));
        glyph.className = "char";
        const details = document.createElement("a");
        details.href = `${DETAILS_URL}${code(codePoint)}/`;
        details.target = "_blank";
        details.rel = "noopener noreferrer";
        details.textContent = "unicodefyi ↗";
        const others = lookAlikes(codePoint);
        let lookAlikeCell;
        if (others.length === 0) {
            lookAlikeCell = cell();
        }
        else {
            const tile = button(shown(others[0]), `${others.length} look-alike${others.length === 1 ? "" : "s"}`, (source) => showChooser(others, source));
            tile.className = "tile";
            if (others.length > 1) {
                const more = document.createElement("span");
                more.className = "more";
                more.textContent = `+${others.length - 1}`;
                tile.append(more);
            }
            lookAlikeCell = cell(tile);
        }
        row.append(cell(String(position + 1)), cell(candidate.score.toFixed(3)), cell(glyph), cell(button("📋", `Copy ${code(codePoint)}`, (source) => void copy(codePoint, source))), cell(code(codePoint)), nameCell(recognizer?.charset.characters.get(codePoint)?.name ?? ""), lookAlikeCell, cell(details));
        row.cells[0].className = "rank";
        row.cells[1].className = "score";
        row.cells[4].className = "code";
        row.cells[5].className = "name";
        candidatesBody.append(row);
    });
    const { rasterizeMs, encodeMs, rankMs, totalMs } = recognition.timings;
    timings.textContent =
        `${totalMs.toFixed(1)} ms per query: rasterize ${rasterizeMs.toFixed(1)}, ` +
            `encode ${encodeMs.toFixed(1)}, rank ${rankMs.toFixed(1)}.`;
    if (!labelInput.matches(":focus")) {
        labelInput.value = String.fromCodePoint(recognition.characters[0]?.codePoint ?? 32).trim();
    }
}
function recognize() {
    if (!recognizer || strokes.length === 0) {
        lastRecognition = null;
        renderResults(null);
        return;
    }
    lastRecognition = recognizer.recognize(strokes, { characters: Number(candidateCountSelect.value) });
    renderResults(lastRecognition);
}
function padPoint(event) {
    const box = pad.getBoundingClientRect();
    return [event.clientX - box.left, event.clientY - box.top];
}
pad.addEventListener("pointerdown", (event) => {
    pad.setPointerCapture(event.pointerId);
    current = [padPoint(event)];
    drawPad();
});
pad.addEventListener("pointermove", (event) => {
    if (!current)
        return;
    for (const sample of event.getCoalescedEvents?.() ?? [event])
        current.push(padPoint(sample));
    drawPad();
});
const finishStroke = () => {
    if (!current)
        return;
    strokes.push(current);
    current = null;
    drawPad();
    recognize();
};
pad.addEventListener("pointerup", finishStroke);
pad.addEventListener("pointercancel", finishStroke);
element("undo").addEventListener("click", () => {
    strokes.pop();
    drawPad();
    recognize();
});
element("clear").addEventListener("click", () => {
    strokes.length = 0;
    drawPad();
    recognize();
});
const linkButton = element("link");
linkButton.addEventListener("click", () => {
    const url = new URL(location.href);
    if (strokes.length === 0) {
        url.searchParams.delete(DRAWING_PARAMETER);
        history.replaceState(null, "", url);
        return;
    }
    url.searchParams.set(DRAWING_PARAMETER, encodeDrawing(strokes));
    history.replaceState(null, "", url);
    const done = (message) => {
        linkButton.textContent = message;
        setTimeout(() => (linkButton.textContent = "Link"), 1500);
    };
    navigator.clipboard.writeText(url.href).then(() => done("Link copied"), () => done("Link in address bar"));
});
/** A drawing from the page address (see the Link button), scaled down if it doesn't fit
 * this pad. */
function drawingFromAddress() {
    const value = new URL(location.href).searchParams.get(DRAWING_PARAMETER);
    const drawing = value === null ? null : decodeDrawing(value);
    if (!drawing)
        return null;
    const size = pad.getBoundingClientRect().width;
    const extent = Math.max(...drawing.flat().flatMap(([x, y]) => [x, y]));
    const scale = extent > size ? size / extent : 1;
    return drawing.map((stroke) => stroke.map(([x, y]) => [x * scale, y * scale]));
}
candidateCountSelect.addEventListener("change", () => {
    store(CANDIDATE_COUNT_KEY, candidateCountSelect.value);
    recognize();
});
document.addEventListener("pointerdown", (event) => {
    if (!chooser.hidden && !chooser.contains(event.target))
        chooser.hidden = true;
});
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape")
        chooser.hidden = true;
});
function savedDrawings() {
    return storage(SAVED_KEY, []).map(({ label, strokes, candidates, tiles, savedAt }) => ({
        label,
        strokes,
        candidates: candidates ?? tiles ?? [],
        savedAt,
    }));
}
function showSavedCount() {
    const count = savedDrawings().length;
    savedText.textContent = count === 0 ? "No drawings saved." : `${count} drawing${count === 1 ? "" : "s"} saved.`;
}
element("save").addEventListener("click", () => {
    const label = labelInput.value.trim();
    if (strokes.length === 0 || [...label].length !== 1) {
        savedText.textContent = "Draw something and give it a one-character label first.";
        return;
    }
    const drawings = savedDrawings();
    drawings.push({
        label,
        strokes: strokes.map((stroke) => stroke.map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10])),
        candidates: (lastRecognition?.characters ?? [])
            .slice(0, 5)
            .map((candidate) => String.fromCodePoint(candidate.codePoint)),
        savedAt: new Date().toISOString(),
    });
    store(SAVED_KEY, drawings);
    strokes.length = 0;
    drawPad();
    recognize();
    showSavedCount();
});
element("export").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify({ format: 2, drawings: savedDrawings() }, null, 1)], {
        type: "application/json",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `glyphsketch-drawings-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
});
element("forget").addEventListener("click", () => {
    if (savedDrawings().length > 0 && confirm("Delete all saved drawings from this browser?")) {
        store(SAVED_KEY, []);
        showSavedCount();
    }
});
/** The published site has source.json (web/scripts/build_site.ts): link the source code, as
 * the AGPL asks of a hosted program. Served locally, the file is absent and nothing shows. */
async function showSourceLink() {
    try {
        const response = await fetch(new URL("../../source.json", document.baseURI));
        if (!response.ok)
            return;
        const { repository, commit } = (await response.json());
        if (!repository)
            return;
        const paragraph = document.createElement("p");
        const link = document.createElement("a");
        link.href = commit ? `${repository}/tree/${commit}` : repository;
        link.textContent = repository.replace("https://", "");
        paragraph.append("Source code (AGPL-3.0): ", link, commit ? ` at ${commit.slice(0, 7)}.` : ".");
        element("attribution").append(paragraph);
    }
    catch {
        // No source.json: running from a local checkout.
    }
}
async function start() {
    drawPad();
    drawInputImage(null);
    showSavedCount();
    const count = storage(CANDIDATE_COUNT_KEY, "10");
    candidateCountSelect.value = ["10", "20", "50", "100"].includes(count) ? count : "10";
    try {
        recognizer = await Recognizer.load(EXPORT_URL.href);
    }
    catch (error) {
        timings.textContent = `Could not load the model from ${EXPORT_URL.pathname}: ${String(error)}`;
        return;
    }
    element("attribution").textContent = recognizer.charset.attribution.join(" ");
    void showSourceLink();
    timings.textContent = "Draw a character.";
    strokes.push(...(drawingFromAddress() ?? []));
    drawPad();
    recognize();
}
/** Installable and offline (manifest.webmanifest, sw.js). Browsers allow service workers on
 * HTTPS and localhost only; elsewhere the demo simply runs without one. */
function registerServiceWorker() {
    if (!("serviceWorker" in navigator))
        return;
    navigator.serviceWorker.register("sw.js").catch((error) => {
        console.warn("No offline support:", error);
    });
}
registerServiceWorker();
void start();
//# sourceMappingURL=demo.js.map