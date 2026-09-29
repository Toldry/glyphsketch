"""Font subsets that let the Android demo show every character it can recognize.

Phones ship far fewer fonts than a desktop browser can use, so many candidates (legacy
computing symbols, Hebrew accents, hieroglyphs) would show no glyph. This picks, for every
character the glyph stage covered, the first font in DISPLAY_FONTS that has it, and writes
one subset per font with just those characters (plus the dotted circle that combining
marks are shown on), from the Regular instance of variable fonts. The demo uses them only
for characters the phone's own fonts lack.

Only fonts whose license allows modified copies under the same name are used: the Noto
fonts and Klee One (OFL-1.1, no Reserved Font Name; checked in each license header). A few
characters that only DejaVu or GNU FreeFont cover stay without a bundled glyph: DejaVu's
license requires renaming modified fonts, and FreeFont is GPL.

Usage: ``uv run python -m glyphsketch.tools.display_fonts``
"""

import json
import shutil
from collections import defaultdict

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from glyphsketch.paths import REPO_ROOT, stage_dir

OUTPUT_DIR = REPO_ROOT / "android" / "demo" / "src" / "main" / "assets" / "fonts"
# In order of preference: sans text faces first, then the specialist fonts.
DISPLAY_FONTS = [
    "noto-sans",
    "noto-sans-hebrew",
    "noto-sans-arabic",
    "noto-sans-math",
    "noto-sans-symbols",
    "noto-sans-symbols-2",
    "noto-emoji",
    "noto-music",
    "noto-sans-egyptian-hieroglyphs",
    "noto-sans-mono",
    "noto-naskh-arabic",
    "klee-one",
]
DOTTED_CIRCLE = 0x25CC


def font_file(font_id: str) -> str:
    files = stage_dir("fonts") / "files"
    return next(path.name for path in files.iterdir() if path.stem == font_id)


def main() -> None:
    glyphs = json.loads((stage_dir("glyphs") / "glyphs.json").read_text(encoding="utf-8"))
    assigned: dict[str, list[int]] = defaultdict(list)
    uncovered = []
    for record in glyphs["characters"]:
        font = next((font for font in DISPLAY_FONTS if font in record["fonts"]), None)
        if font is None:
            uncovered.append(record["code_point"])
        else:
            assigned[font].append(record["code_point"])
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    options = subset.Options()
    options.layout_features = ["*"]  # keeps mark positioning for combining marks
    options.hinting = False
    options.name_IDs = ["*"]
    options.notdef_outline = True
    total = 0
    for font_id in DISPLAY_FONTS:
        if font_id not in assigned:
            continue
        font = TTFont(stage_dir("fonts") / "files" / font_file(font_id))
        if "fvar" in font:  # a variable font: keep only the default (Regular) instance
            defaults = {axis.axisTag: axis.defaultValue for axis in font["fvar"].axes}
            font = instancer.instantiateVariableFont(font, defaults)
        code_points = set(assigned[font_id])
        if DOTTED_CIRCLE in font.getBestCmap():
            code_points.add(DOTTED_CIRCLE)
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=sorted(code_points))
        subsetter.subset(font)
        path = OUTPUT_DIR / f"{font_id}.ttf"
        font.save(path)
        license_file = stage_dir("fonts") / "licenses" / f"{font_id}.txt"
        shutil.copyfile(license_file, OUTPUT_DIR / f"{font_id}-OFL.txt")
        size = path.stat().st_size
        total += size
        print(f"  {font_id}: {len(assigned[font_id])} characters, {size:,} bytes")
    print(f"{total / 1e6:.2f} MB of fonts; {len(uncovered)} characters without a bundled glyph")


if __name__ == "__main__":
    main()
