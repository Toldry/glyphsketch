from pathlib import Path

import pytest

from glyphsketch.tools.detexify_mapping import build_mapping, rule_based, styled_letter

UNICODE_XML = """<?xml version="1.0"?>
<unicode>
 <charlist>
  <character id="U02261"><latex>\\equiv </latex></character>
  <character id="U02217">
   <latex>\\ast</latex><mathlatex set="unicode-math">\\ast</mathlatex>
  </character>
  <character id="U0002A"><latex>\\ast</latex></character>
  <character id="U02254"><latex>\\coloneq</latex></character>
  <character id="U02255"><latex>\\coloneq</latex></character>
  <character id="U0003C-020D2"><latex>\\nvless</latex></character>
 </charlist>
</unicode>
"""


@pytest.mark.parametrize(
    ("command", "code_point"),
    [
        ("\\mathds{R}", 0x211D),
        ("\\mathbb{A}", 0x1D538),
        ("\\mathds{1}", 0x1D7D9),
        ("\\mathcal{B}", 0x212C),
        ("\\mathscr{A}", 0x1D49C),
        ("\\mathfrak{C}", 0x212D),
        ("\\mathfrak{a}", 0x1D51E),
        ("\\upalpha", 0x3B1),
        ("\\upvarphi", 0x3C6),
        ("\\Updelta", 0x394),
    ],
)
def test_rule_based_styled_letters_and_upright_greek(command: str, code_point: int) -> None:
    result = rule_based(command)
    assert result is not None
    assert result[0] == code_point


def test_rules_ignore_other_commands() -> None:
    assert rule_based("\\uparrow") is None
    assert rule_based("\\mathrm{A}") is None
    assert styled_letter("fraktur", "1") is None


def test_unicode_xml_lookup_prefers_the_unicode_math_reading(tmp_path: Path) -> None:
    xml_path = tmp_path / "unicode.xml"
    xml_path.write_text(UNICODE_XML, encoding="utf-8")
    symbols: list[dict[str, object]] = [
        {"id": "latex2e-OT1-_equiv", "command": "\\equiv"},
        {"id": "latex2e-OT1-_star", "command": "\\ast"},
        {"id": "x-OT1-_coloneq", "command": "\\coloneq"},
        {"id": "x-OT1-_nvless", "command": "\\nvless"},
        {"id": "latex2e-OT1-_alpha", "command": "\\alpha"},
    ]
    mappings = {mapping.key: mapping for mapping in build_mapping(symbols, xml_path)}
    assert mappings["latex2e-OT1-_equiv"].code_point == 0x2261
    assert mappings["latex2e-OT1-_star"].code_point == 0x2217
    assert mappings["x-OT1-_coloneq"].source == "unresolved"
    assert mappings["x-OT1-_nvless"].source == "unresolved"
    assert mappings["latex2e-OT1-_alpha"].source == "unresolved"
