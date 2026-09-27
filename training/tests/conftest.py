from pathlib import Path

import pytest

from glyphsketch.paths import DATA_DIR_ENV_VAR, data_dir

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def isolated_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point ``$DATA_DIR`` at an empty temporary directory for the duration of a test."""
    data_root = tmp_path / "data"
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(data_root))
    return data_root


def real_stage_dir_or_skip(stage_name: str, required_file: str) -> Path:
    """Return a stage's real output directory in ``$DATA_DIR``, or skip the test."""
    try:
        directory = data_dir() / stage_name
    except RuntimeError:
        pytest.skip("$DATA_DIR is not configured")
    if not (directory / required_file).exists():
        pytest.skip(f"run the '{stage_name}' pipeline stage first")
    return directory


FIXTURE_UNICODE_DATA = """\
0000;<control>;Cc;0;BN;;;;;N;NULL;;;;
0020;SPACE;Zs;0;WS;;;;;N;;;;;
0041;LATIN CAPITAL LETTER A;Lu;0;L;;;;;N;;;;0061;
0061;LATIN SMALL LETTER A;Ll;0;L;;;;;N;;;0041;;0041
00AD;SOFT HYPHEN;Cf;0;BN;;;;;N;;;;;
00B7;MIDDLE DOT;Po;0;ON;;;;;N;;;;;
00E9;LATIN SMALL LETTER E WITH ACUTE;Ll;0;L;0065 0301;;;;N;;;00C9;;00C9
0149;LATIN SMALL LETTER N PRECEDED BY APOSTROPHE;Ll;0;L;<compat> 02BC 006E;;;;N;;;;;
0301;COMBINING ACUTE ACCENT;Mn;230;NSM;;;;;N;;;;;
0391;GREEK CAPITAL LETTER ALPHA;Lu;0;L;;;;;N;;;;03B1;
05D0;HEBREW LETTER ALEF;Lo;0;R;;;;;N;;;;;
231A;WATCH;So;0;ON;;;;;N;;;;;
4E00;<CJK Ideograph, First>;Lo;0;L;;;;;N;;;;;
4E02;<CJK Ideograph, Last>;Lo;0;L;;;;;N;;;;;
AC00;<Hangul Syllable, First>;Lo;0;L;;;;;N;;;;;
D7A3;<Hangul Syllable, Last>;Lo;0;L;;;;;N;;;;;
E000;<Private Use, First>;Co;0;L;;;;;N;;;;;
F8FF;<Private Use, Last>;Co;0;L;;;;;N;;;;;
FDFC;RIAL SIGN;Sc;0;AL;<isolated> 0631 06CC 0627 0644;;;;N;;;;;
"""

FIXTURE_BLOCKS = """\
# Blocks-fixture.txt
0000..007F; Basic Latin
0080..00FF; Latin-1 Supplement
0100..017F; Latin Extended-A
0300..036F; Combining Diacritical Marks
0370..03FF; Greek and Coptic
0590..05FF; Hebrew
2300..23FF; Miscellaneous Technical
4E00..9FFF; CJK Unified Ideographs
AC00..D7AF; Hangul Syllables
E000..F8FF; Private Use Area
FB50..FDFF; Arabic Presentation Forms-A
"""

FIXTURE_SCRIPTS = """\
0000          ; Common # Cc       <control-0000>
0020          ; Common # Zs       SPACE
0041          ; Latin # L&       LATIN CAPITAL LETTER A
0061          ; Latin # L&       LATIN SMALL LETTER A
00AD          ; Common # Cf       SOFT HYPHEN
00B7          ; Common # Po       MIDDLE DOT
00E9          ; Latin # L&       LATIN SMALL LETTER E WITH ACUTE
0149          ; Latin # L&       LATIN SMALL LETTER N PRECEDED BY APOSTROPHE
0301          ; Inherited # Mn       COMBINING ACUTE ACCENT
0391          ; Greek # L&       GREEK CAPITAL LETTER ALPHA
05D0          ; Hebrew # Lo       HEBREW LETTER ALEF
231A          ; Common # So       WATCH
4E00..4E02    ; Han # Lo   [3] CJK UNIFIED IDEOGRAPH-4E00..CJK UNIFIED IDEOGRAPH-4E02
FDFC          ; Arabic # Sc       RIAL SIGN
"""

FIXTURE_SCRIPT_EXTENSIONS = """\
00B7          ; Grek Latn #Po MIDDLE DOT
"""

FIXTURE_PROPERTY_VALUE_ALIASES = """\
sc ; Arab                             ; Arabic
sc ; Grek                             ; Greek
sc ; Hani                             ; Han
sc ; Hebr                             ; Hebrew
sc ; Latn                             ; Latin
sc ; Zinh                             ; Inherited                        ; Qaai
sc ; Zyyy                             ; Common
"""

FIXTURE_DERIVED_AGE = """\
0000..00FF    ; 1.1 #  [256]
0149          ; 1.1 #       LATIN SMALL LETTER N PRECEDED BY APOSTROPHE
0301          ; 1.1 #       COMBINING ACUTE ACCENT
0391          ; 1.1 #       GREEK CAPITAL LETTER ALPHA
05D0          ; 1.1 #       HEBREW LETTER ALEF
231A          ; 1.1 #       WATCH
4E00..4E02    ; 1.1 #  [3]
FDFC          ; 3.2 #       RIAL SIGN
"""

FIXTURE_PROP_LIST = """\
0149          ; Deprecated # L&       LATIN SMALL LETTER N PRECEDED BY APOSTROPHE
"""

FIXTURE_EMOJI_DATA = """\
﻿# emoji-data.txt
231A..231B    ; Emoji_Presentation   # E0.6   [2] (⌚..⌛)    watch..hourglass done
"""


@pytest.fixture
def fixture_ucd_dir(tmp_path: Path) -> Path:
    """A tiny UCD directory with the same layout as the pinned download."""
    root = tmp_path / "ucd-fixture"
    contents = {
        "ucd/UnicodeData.txt": FIXTURE_UNICODE_DATA,
        "ucd/Blocks.txt": FIXTURE_BLOCKS,
        "ucd/Scripts.txt": FIXTURE_SCRIPTS,
        "ucd/ScriptExtensions.txt": FIXTURE_SCRIPT_EXTENSIONS,
        "ucd/PropertyValueAliases.txt": FIXTURE_PROPERTY_VALUE_ALIASES,
        "ucd/DerivedAge.txt": FIXTURE_DERIVED_AGE,
        "ucd/PropList.txt": FIXTURE_PROP_LIST,
        "ucd/emoji/emoji-data.txt": FIXTURE_EMOJI_DATA,
    }
    for relative_path, text in contents.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root
