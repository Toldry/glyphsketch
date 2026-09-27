"""Build ``resources/detexify_unicode.tsv``: Detexify symbol keys mapped to code points.

Sources, in order of precedence:

1. ``MANUAL``: entries written and checked by hand against drawings from the dataset
   (see the QA sheets described in DECISIONS.md). An entry of ``None`` means the symbol
   has no single-code-point Unicode equivalent and is not used.
2. Styled alphabets (``\\mathcal``, ``\\mathscr``, ``\\mathbb``, ``\\mathds``,
   ``\\mathfrak``) and upright Greek (``upgreek``), computed by rule, including the
   Letterlike Symbols "holes" of the Mathematical Alphanumeric Symbols block.
3. W3C's ``unicode.xml`` (XML Entity Definitions for Characters, W3C Software Notice and
   License): its ``<latex>``, ``<varlatex>``, ``<mathlatex>``, ``<AMS>`` and ``<IEEE>``
   commands. When a command names several characters, the one whose unicode-math command
   is exactly that command wins.

Usage: ``uv run python -m glyphsketch.tools.detexify_mapping`` (needs the ``detexify``
stage's ``symbols.json``; downloads the pinned ``unicode.xml``).
"""

import json
import re
import sys
import xml.etree.ElementTree as ElementTree
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from glyphsketch.charset import format_code_point
from glyphsketch.download import download_file
from glyphsketch.paths import stage_dir
from glyphsketch.realdata.detexify import MAPPING_PATH, SYMBOLS_FILE

UNICODE_XML_URL = "https://www.w3.org/2003/entities/2007xml/unicode.xml"
UNICODE_XML_SHA256 = "bcd6782c078f4f3521300c7d1f7a26ebd766011a62adf45c1111634c2291ac10"

# Mathematical Alphanumeric Symbols: first code point of each capital alphabet, and the
# letters that live in Letterlike Symbols instead.
STYLED_CAPITALS = {"script": 0x1D49C, "double-struck": 0x1D538, "fraktur": 0x1D504}
STYLED_SMALLS = {"script": 0x1D4B6, "double-struck": 0x1D552, "fraktur": 0x1D51E}
STYLED_HOLES = {
    "script": {"B": 0x212C, "E": 0x2130, "F": 0x2131, "H": 0x210B, "I": 0x2110,
               "L": 0x2112, "M": 0x2133, "R": 0x211B, "e": 0x212F, "g": 0x210A, "o": 0x2134},
    "double-struck": {"C": 0x2102, "H": 0x210D, "N": 0x2115, "P": 0x2119, "Q": 0x211A,
                      "R": 0x211D, "Z": 0x2124},
    "fraktur": {"C": 0x212D, "H": 0x210C, "I": 0x2111, "R": 0x211C, "Z": 0x2128},
}  # fmt: skip
DOUBLE_STRUCK_DIGIT_ZERO = 0x1D7D8
STYLE_COMMANDS = {
    "mathcal": "script",
    "mathscr": "script",
    "mathbb": "double-struck",
    "mathds": "double-struck",
    "mathfrak": "fraktur",
}
GREEK_LETTERS = {
    "alpha": 0x3B1, "beta": 0x3B2, "gamma": 0x3B3, "delta": 0x3B4, "epsilon": 0x3F5,
    "zeta": 0x3B6, "eta": 0x3B7, "theta": 0x3B8, "iota": 0x3B9, "kappa": 0x3BA,
    "lambda": 0x3BB, "mu": 0x3BC, "nu": 0x3BD, "xi": 0x3BE, "pi": 0x3C0, "rho": 0x3C1,
    "sigma": 0x3C3, "tau": 0x3C4, "upsilon": 0x3C5, "phi": 0x3D5, "chi": 0x3C7,
    "psi": 0x3C8, "omega": 0x3C9, "varepsilon": 0x3B5, "vartheta": 0x3D1, "varpi": 0x3D6,
    "varrho": 0x3F1, "varsigma": 0x3C2, "varphi": 0x3C6,
    "Gamma": 0x393, "Delta": 0x394, "Theta": 0x398, "Lambda": 0x39B, "Xi": 0x39E,
    "Pi": 0x3A0, "Sigma": 0x3A3, "Upsilon": 0x3A5, "Phi": 0x3A6, "Psi": 0x3A8,
    "Omega": 0x3A9,
}  # fmt: skip

NONE = None
# Hand-checked entries: command -> (code point or None, note).
MANUAL: dict[str, tuple[int | None, str]] = {
    # latex2e and friends
    "\\--": (0x2013, "text en dash"),
    "\\---": (0x2014, "text em dash"),
    "\\----": (NONE, "a dash longer than an em dash; no Unicode equivalent"),
    "!`": (0x00A1, ""),
    "|": (0x007C, ""),
    "\\|": (0x2016, "math double vertical line"),
    "\\{": (0x007B, ""),
    "\\}": (0x007D, ""),
    "\\SS": (NONE, "renders as two letters SS"),
    "\\emptyset": (0x2205, ""),
    "\\mathellipsis": (0x2026, ""),
    "\\mathparagraph": (0x00B6, ""),
    "\\mathsection": (0x00A7, ""),
    "\\mathunderscore": (0x005F, ""),
    "\\quotedblbase": (0x201E, ""),
    "\\quotesinglbase": (0x201A, ""),
    "\\sqrt{}": (0x221A, ""),
    "\\textasciicircum": (0x005E, ""),
    "\\textasteriskcentered": (0x2217, ""),
    "\\textbar": (0x007C, ""),
    "\\textbraceleft": (0x007B, ""),
    "\\textbraceright": (0x007D, ""),
    "\\textellipsis": (0x2026, ""),
    "\\textgreater": (0x003E, ""),
    "\\textless": (0x003C, ""),
    "\\textquotedbl": (0x0022, ""),
    "\\textquoteleft": (0x2018, ""),
    "\\textquoteright": (0x2019, ""),
    "\\textunderscore": (0x005F, ""),
    "\\triangle": (0x25B3, ""),
    "\\neq": (0x2260, ""),
    "\\leadsto": (0x2933, "unicode-math \\leadsto"),
    # ambiguous in unicode.xml: resolved to the LaTeX glyph
    "\\AA": (0x00C5, ""),
    "\\ast": (0x2217, ""),
    "\\bullet": (0x2219, ""),
    "\\cdot": (0x22C5, ""),
    "\\setminus": (0x2216, ""),
    "\\diamond": (0x22C4, ""),
    "\\bigcirc": (0x25EF, ""),
    "\\triangleleft": (0x25C3, ""),
    "\\triangleright": (0x25B9, ""),
    "\\perp": (0x22A5, ""),
    "\\models": (0x22A7, ""),
    "\\circlearrowleft": (0x21BA, ""),
    "\\circlearrowright": (0x21BB, ""),
    "\\epsilon": (0x03F5, "LaTeX's \\epsilon is the lunate form"),
    "\\varepsilon": (0x03B5, ""),
    "\\Upsilon": (0x03A5, ""),
    "\\Omega": (0x03A9, ""),
    "\\eth": (0x00F0, ""),
    "\\textperiodcentered": (0x00B7, "unicode.xml gives U+02D9"),
    "\\textdoublepipe": (0x01C1, "unicode.xml gives U+01C2"),
    "\\nsubseteqq": (NONE, "only as U+2AC5 with combining solidus"),
    "\\nsupseteqq": (NONE, "only as U+2AC6 with combining solidus"),
    "\\uranus": (0x26E2, "astronomical Uranus; marvosym's \\Uranus is U+2645"),
    "\\blacksquare": (0x25A0, ""),
    # amsmath
    "\\dotsb": (0x22EF, "centered dots"),
    "\\dotsc": (0x2026, "baseline dots"),
    "\\dotsi": (0x22EF, "centered dots"),
    "\\dotsm": (0x22EF, "centered dots"),
    "\\dotso": (0x2026, "baseline dots"),
    "\\idotsint": (NONE, "several integral signs"),
    # amssymb
    "\\centerdot": (0x25AA, "amssymb draws it as a small filled square"),
    "\\dashleftarrow": (0x21E0, ""),
    "\\dashrightarrow": (0x21E2, ""),
    "\\gvertneqq": (NONE, "only as U+2269 with variation selector 1"),
    "\\lvertneqq": (NONE, "only as U+2268 with variation selector 1"),
    "\\ngeqq": (NONE, "only as U+2267 with combining solidus"),
    "\\ngeqslant": (NONE, "only as U+2A7E with combining solidus"),
    "\\nleqq": (NONE, "only as U+2266 with combining solidus"),
    "\\nleqslant": (NONE, "only as U+2A7D with combining solidus"),
    "\\npreceq": (NONE, "only as U+2AAF with combining solidus"),
    "\\nsucceq": (NONE, "only as U+2AB0 with combining solidus"),
    "\\nshortmid": (0x2224, ""),
    "\\nshortparallel": (0x2226, ""),
    "\\shortmid": (0x2223, ""),
    "\\shortparallel": (0x2225, ""),
    "\\smallfrown": (0x2322, ""),
    "\\smallsmile": (0x2323, ""),
    "\\thickapprox": (0x2248, "bold variant"),
    "\\thicksim": (0x223C, "bold variant"),
    "\\varsubsetneq": (0x228A, "stroke variant"),
    "\\varsubsetneqq": (0x2ACB, "stroke variant"),
    "\\varsupsetneq": (0x228B, "stroke variant"),
    "\\varsupsetneqq": (0x2ACC, "stroke variant"),
    # cmll
    "\\parr": (0x214B, ""),
    "\\with": (0x0026, ""),
    # esint
    "\\dotsint": (NONE, "several integral signs"),
    "\\landdownint": (NONE, "no Unicode equivalent"),
    "\\landupint": (NONE, "no Unicode equivalent"),
    "\\ointclockwise": (0x2232, ""),
    "\\sqiint": (NONE, "no Unicode equivalent"),
    "\\varoiint": (0x222F, ""),
    "\\varointctrclockwise": (0x2233, ""),
    # gensymb
    "\\celsius": (0x2103, ""),
    "\\ohm": (0x2126, ""),
    # latexsym / mathdots / skull
    "\\iddots": (0x22F0, ""),
    "\\skull": (0x2620, ""),
    # marvosym
    "\\Ankh": (0x2625, ""),
    "\\Aquarius": (0x2652, ""),
    "\\Aries": (0x2648, ""),
    "\\Bat": (NONE, "pictogram"),
    "\\Cancer": (0x264B, ""),
    "\\Capricorn": (0x2651, ""),
    "\\Celtcross": (NONE, "Celtic cross is outside the charset"),
    "\\CircledA": (0x24B6, ""),
    "\\Cross": (0x271D, ""),
    "\\Denarius": (NONE, "Roman denarius sign is outside the charset"),
    "\\EUR": (0x20AC, ""),
    "\\EURcr": (0x20AC, ""),
    "\\EURdig": (0x20AC, ""),
    "\\EURhv": (0x20AC, ""),
    "\\EURtm": (0x20AC, ""),
    "\\Earth": (0x2641, ""),
    "\\Ecommerce": (NONE, "pictogram"),
    "\\Email": (NONE, "pictogram"),
    "\\Emailct": (NONE, "pictogram"),
    "\\EyesDollar": (NONE, "pictogram"),
    "\\FAX": (NONE, "pictogram"),
    "\\Faxmachine": (NONE, "pictogram"),
    "\\fax": (NONE, "pictogram"),
    "\\Frowny": (0x2639, ""),
    "\\Gemini": (0x264A, ""),
    "\\Heart": (0x2661, ""),
    "\\Jupiter": (0x2643, ""),
    "\\Leo": (0x264C, ""),
    "\\Letter": (0x2709, ""),
    "\\Libra": (0x264E, ""),
    "\\Lightning": (0x21AF, ""),
    "\\MVAt": (0x0040, ""),
    "\\MVRightarrow": (0x2192, "marvosym arrow, drawn as a plain arrow"),
    "\\Mars": (0x2642, ""),
    "\\Mercury": (0x263F, ""),
    "\\Mobilefone": (NONE, "pictogram"),
    "\\Moon": (0x263D, "drawn as a crescent bulging right"),
    "\\Mundus": (NONE, "globe pictogram"),
    "\\Neptune": (0x2646, ""),
    "\\Pfund": (0x2114, "pound (weight) sign"),
    "\\Pickup": (NONE, "pictogram"),
    "\\Pisces": (0x2653, ""),
    "\\Pluto": (0x2BD3, "astrological Pluto; wasysym's \\pluto is U+2647"),
    "\\Sagittarius": (0x2650, ""),
    "\\Saturn": (0x2644, ""),
    "\\Scorpio": (0x264F, ""),
    "\\Shilling": (NONE, "no Unicode equivalent"),
    "\\Smiley": (0x263A, ""),
    "\\Sun": (0x2609, ""),
    "\\Taurus": (0x2649, ""),
    "\\Telefon": (0x260E, ""),
    "\\Uranus": (0x2645, ""),
    "\\Venus": (0x2640, ""),
    "\\Virgo": (0x264D, ""),
    "\\Yinyang": (0x262F, ""),
    # stmaryrd
    "\\Lbag": (0x27C5, ""),
    "\\Rbag": (0x27C6, ""),
    "\\inplus": (NONE, "no Unicode equivalent"),
    "\\niplus": (NONE, "no Unicode equivalent"),
    "\\leftrightarroweq": (NONE, "no Unicode equivalent"),
    "\\lightning": (0x21AF, ""),
    "\\llbracket": (0x27E6, ""),
    "\\rrbracket": (0x27E7, ""),
    "\\llceil": (NONE, "no Unicode equivalent"),
    "\\rrceil": (NONE, "no Unicode equivalent"),
    "\\llfloor": (NONE, "no Unicode equivalent"),
    "\\rrfloor": (NONE, "no Unicode equivalent"),
    "\\nnearrow": (NONE, "no Unicode equivalent"),
    "\\nnwarrow": (NONE, "no Unicode equivalent"),
    "\\ssearrow": (NONE, "no Unicode equivalent"),
    "\\sswarrow": (NONE, "no Unicode equivalent"),
    "\\shortdownarrow": (0x2193, "short variant"),
    "\\shortleftarrow": (0x2190, "short variant"),
    "\\shortrightarrow": (0x2192, "short variant"),
    "\\shortuparrow": (0x2191, "short variant"),
    # textcomp
    "\\textbaht": (0x0E3F, ""),
    "\\textbardbl": (0x2016, ""),
    "\\textbigcircle": (0x25EF, ""),
    "\\textblank": (0x2422, ""),
    "\\textcentoldstyle": (0x00A2, ""),
    "\\textcircledP": (0x2117, ""),
    "\\textcolonmonetary": (0x20A1, ""),
    "\\textcopyleft": (0x1F12F, ""),
    "\\textdblhyphen": (0x2E40, ""),
    "\\textdblhyphenchar": (0x2E40, ""),
    "\\textdiscount": (0x2052, ""),
    "\\textdiv": (0x00F7, ""),
    "\\textdollaroldstyle": (0x0024, ""),
    "\\textdong": (0x20AB, ""),
    "\\textdownarrow": (0x2193, ""),
    "\\textestimated": (0x212E, ""),
    "\\texteuro": (0x20AC, ""),
    "\\textflorin": (0x0192, ""),
    "\\textfractionsolidus": (0x2044, ""),
    "\\textguarani": (0x20B2, ""),
    "\\textinterrobang": (0x203D, ""),
    "\\textinterrobangdown": (0x2E18, ""),
    "\\textlangle": (0x27E8, ""),
    "\\textlbrackdbl": (0x27E6, ""),
    "\\textleftarrow": (0x2190, ""),
    "\\textlira": (0x20A4, ""),
    "\\textlnot": (0x00AC, ""),
    "\\textlquill": (0x2045, ""),
    "\\textminus": (0x2212, ""),
    "\\textmusicalnote": (0x266A, ""),
    "\\textnaira": (0x20A6, ""),
    "\\textonesuperior": (0x00B9, ""),
    "\\textopenbullet": (0x25E6, ""),
    "\\textpeso": (0x20B1, ""),
    "\\textpilcrow": (0x00B6, ""),
    "\\textpm": (0x00B1, ""),
    "\\textquotestraightbase": (NONE, "no Unicode equivalent"),
    "\\textquotestraightdblbase": (NONE, "no Unicode equivalent"),
    "\\textrangle": (0x27E9, ""),
    "\\textrbrackdbl": (0x27E7, ""),
    "\\textrecipe": (0x211E, ""),
    "\\textreferencemark": (0x203B, ""),
    "\\textrightarrow": (0x2192, ""),
    "\\textrquill": (0x2046, ""),
    "\\textservicemark": (0x2120, ""),
    "\\textsurd": (0x221A, ""),
    "\\textthreequartersemdash": (NONE, "no Unicode equivalent"),
    "\\textthreesuperior": (0x00B3, ""),
    "\\texttwelveudash": (NONE, "no Unicode equivalent"),
    "\\texttwosuperior": (0x00B2, ""),
    "\\textuparrow": (0x2191, ""),
    "\\textwon": (0x20A9, ""),
    # tipa
    "\\textObardotlessj": (0x025F, "older form of the barred dotless j"),
    "\\textOlyoghlig": (0x026E, "older form of the lezh ligature"),
    "\\textbabygamma": (0x0264, ""),
    "\\textbarb": (0x0180, ""),
    "\\textbarc": (0xA793, ""),
    "\\textbard": (0x0111, ""),
    "\\textbardotlessj": (0x025F, ""),
    "\\textbarg": (0x01E5, ""),
    "\\textbarglotstop": (0x02A1, ""),
    "\\textbari": (0x0268, ""),
    "\\textbarl": (0x019A, ""),
    "\\textbaro": (0x0275, ""),
    "\\textbarrevglotstop": (0x02A2, ""),
    "\\textbaru": (0x0289, ""),
    "\\textbeltl": (0x026C, ""),
    "\\textbeta": (0x03B2, ""),
    "\\textbullseye": (0x0298, ""),
    "\\textceltpal": (NONE, "no Unicode equivalent"),
    "\\textchi": (0x03C7, ""),
    "\\textcloseepsilon": (0x029A, ""),
    "\\textcloseomega": (0x0277, ""),
    "\\textcloserevepsilon": (0x025E, ""),
    "\\textcommatailz": (0x0225, ""),
    "\\textcorner": (0x02FA, ""),
    "\\textcrb": (0x0180, ""),
    "\\textcrd": (0x0111, ""),
    "\\textcrg": (0x01E5, ""),
    "\\textcrh": (0x0127, ""),
    "\\textcrinvglotstop": (0x01BE, ""),
    "\\textcrlambda": (0x019B, ""),
    "\\textcrtwo": (0x01BB, ""),
    "\\textctc": (0x0255, ""),
    "\\textctd": (0x0221, ""),
    "\\textctdctzlig": (NONE, "no Unicode equivalent"),
    "\\textctesh": (0x0286, ""),
    "\\textctj": (0x029D, ""),
    "\\textctn": (0x0235, ""),
    "\\textctt": (0x0236, ""),
    "\\textcttctclig": (NONE, "no Unicode equivalent"),
    "\\textctyogh": (0x0293, ""),
    "\\textctz": (0x0291, ""),
    "\\textdctzlig": (0x02A5, ""),
    "\\textdoublebaresh": (NONE, "no Unicode equivalent"),
    "\\textdoublebarpipe": (0x01C2, ""),
    "\\textdoublebarslash": (NONE, "no Unicode equivalent"),
    "\\textdoublevertline": (0x2016, ""),
    "\\textdownstep": (0xA71C, ""),
    "\\textdyoghlig": (0x02A4, ""),
    "\\textdzlig": (0x02A3, ""),
    "\\textepsilon": (0x025B, ""),
    "\\textesh": (0x0283, ""),
    "\\textfishhookr": (0x027E, ""),
    "\\textg": (0x0261, ""),
    "\\textgamma": (0x0263, ""),
    "\\textglobfall": (0x2198, ""),
    "\\textglobrise": (0x2197, ""),
    "\\textglotstop": (0x0294, ""),
    "\\texthalflength": (0x02D1, ""),
    "\\texthardsign": (0x044A, ""),
    "\\texthooktop": (NONE, "a diacritic"),
    "\\texthtb": (0x0253, ""),
    "\\texthtbardotlessj": (0x0284, ""),
    "\\texthtc": (0x0188, ""),
    "\\texthtd": (0x0257, ""),
    "\\texthtg": (0x0260, ""),
    "\\texthth": (0x0266, ""),
    "\\texththeng": (0x0267, ""),
    "\\texthtk": (0x0199, ""),
    "\\texthtp": (0x01A5, ""),
    "\\texthtq": (0x02A0, ""),
    "\\texthtrtaild": (0x1D91, ""),
    "\\texthtscg": (0x029B, ""),
    "\\texthtt": (0x01AD, ""),
    "\\textinvglotstop": (0x0296, ""),
    "\\textinvscr": (0x0281, ""),
    "\\textiota": (0x0269, ""),
    "\\textlambda": (0x03BB, ""),
    "\\textlengthmark": (0x02D0, ""),
    "\\textlhookt": (0x01AB, ""),
    "\\textlhtlongi": (NONE, "no Unicode equivalent"),
    "\\textlhtlongy": (NONE, "no Unicode equivalent"),
    "\\textlonglegr": (0x027C, ""),
    "\\textlptr": (0x02C2, ""),
    "\\textltailm": (0x0271, ""),
    "\\textltailn": (0x0272, ""),
    "\\textltilde": (0x026B, ""),
    "\\textlyoghlig": (0x026E, ""),
    "\\textomega": (0x03C9, ""),
    "\\textopencorner": (0x02F9, ""),
    "\\textopeno": (0x0254, ""),
    "\\textpalhook": (NONE, "a diacritic"),
    "\\textpipe": (0x01C0, ""),
    "\\textprimstress": (0x02C8, ""),
    "\\textraiseglotstop": (0x02C0, ""),
    "\\textraisevibyi": (NONE, "no Unicode equivalent"),
    "\\textramshorns": (0x0264, ""),
    "\\textrevapostrophe": (0x02BD, ""),
    "\\textreve": (0x0258, ""),
    "\\textrevepsilon": (0x025C, ""),
    "\\textrevglotstop": (0x0295, ""),
    "\\textrevyogh": (0x01B9, ""),
    "\\textrhookrevepsilon": (0x025D, ""),
    "\\textrhookschwa": (0x025A, ""),
    "\\textrhoticity": (0x02DE, ""),
    "\\textrptr": (0x02C3, ""),
    "\\textrtaild": (0x0256, ""),
    "\\textrtaill": (0x026D, ""),
    "\\textrtailn": (0x0273, ""),
    "\\textrtailr": (0x027D, ""),
    "\\textrtails": (0x0282, ""),
    "\\textrtailt": (0x0288, ""),
    "\\textrtailz": (0x0290, ""),
    "\\textrthook": (NONE, "a diacritic"),
    "\\textsca": (0x1D00, ""),
    "\\textscb": (0x0299, ""),
    "\\textsce": (0x1D07, ""),
    "\\textscg": (0x0262, ""),
    "\\textsch": (0x029C, ""),
    "\\textschwa": (0x0259, ""),
    "\\textsci": (0x026A, ""),
    "\\textscj": (0x1D0A, ""),
    "\\textscl": (0x029F, ""),
    "\\textscn": (0x0274, ""),
    "\\textscoelig": (0x0276, ""),
    "\\textscomega": (0xAB65, ""),
    "\\textscr": (0x0280, ""),
    "\\textscripta": (0x0251, ""),
    "\\textscriptg": (0x0261, ""),
    "\\textscriptv": (0x028B, ""),
    "\\textscu": (0x1D1C, ""),
    "\\textscy": (0x028F, ""),
    "\\textsecstress": (0x02CC, ""),
    "\\textsoftsign": (0x044C, ""),
    "\\textstretchc": (0x0297, ""),
    "\\texttctclig": (0x02A8, ""),
    "\\textteshlig": (0x02A7, ""),
    "\\textthorn": (0x00FE, ""),
    "\\texttoneletterstem": (NONE, "no Unicode equivalent"),
    "\\texttslig": (0x02A6, ""),
    "\\textturna": (0x0250, ""),
    "\\textturncelig": (NONE, "no Unicode equivalent"),
    "\\textturnh": (0x0265, ""),
    "\\textturnlonglegr": (0x027A, ""),
    "\\textturnm": (0x026F, ""),
    "\\textturnmrleg": (0x0270, ""),
    "\\textturnr": (0x0279, ""),
    "\\textturnrrtail": (0x027B, ""),
    "\\textturnscripta": (0x0252, ""),
    "\\textturnt": (0x0287, ""),
    "\\textturnv": (0x028C, ""),
    "\\textturnw": (0x028D, ""),
    "\\textturny": (0x028E, ""),
    "\\textupsilon": (0x028A, ""),
    "\\textupstep": (0xA71B, ""),
    "\\textvertline": (0x007C, ""),
    "\\textvibyi": (NONE, "no Unicode equivalent"),
    "\\textvibyy": (NONE, "no Unicode equivalent"),
    "\\textwynn": (0x01BF, ""),
    "\\textyogh": (0x0292, ""),
    # wasysym
    "\\Bowtie": (0x22C8, ""),
    "\\DOWNarrow": (0x25BC, ""),
    "\\LEFTarrow": (0x25C0, ""),
    "\\RIGHTarrow": (0x25B6, ""),
    "\\UParrow": (0x25B2, ""),
    "\\LHD": (0x25C0, ""),
    "\\RHD": (0x25B6, ""),
    "\\lhd": (0x25C1, ""),
    "\\rhd": (0x25B7, ""),
    "\\unlhd": (0x22B4, ""),
    "\\unrhd": (0x22B5, ""),
    "\\ascnode": (0x260A, ""),
    "\\descnode": (0x260B, ""),
    "\\ataribox": (NONE, "pictogram"),
    "\\bell": (0x237E, ""),
    "\\brokenvert": (0x00A6, ""),
    "\\cent": (0x00A2, ""),
    "\\checked": (0x2713, ""),
    "\\clock": (NONE, "pictogram"),
    "\\conjunction": (0x260C, ""),
    "\\currency": (0x00A4, ""),
    "\\earth": (0x2641, ""),
    "\\frownie": (0x2639, ""),
    "\\fullmoon": (0x25CB, ""),
    "\\newmoon": (0x25CF, ""),
    "\\invdiameter": (0x29B8, ""),
    "\\kreuz": (0x2720, ""),
    "\\mars": (0x2642, ""),
    "\\ocircle": (0x25CB, ""),
    "\\opposition": (0x260D, ""),
    "\\permil": (0x2030, ""),
    "\\phone": (0x260E, ""),
    "\\pointer": (0x21E8, "outlined arrow"),
    "\\smiley": (0x263A, ""),
    "\\vernal": (0x2648, ""),
    "\\wasylozenge": (0x2311, ""),
}


@dataclass(frozen=True)
class Mapping:
    key: str
    command: str
    code_point: int | None
    source: str
    note: str


def normalize_command(command: str) -> str:
    return re.sub(r"\s+", "", command.strip())


def styled_letter(style: str, letter: str) -> int | None:
    if letter in STYLED_HOLES.get(style, {}):
        return STYLED_HOLES[style][letter]
    if "A" <= letter <= "Z":
        return STYLED_CAPITALS[style] + ord(letter) - ord("A")
    if "a" <= letter <= "z":
        return STYLED_SMALLS[style] + ord(letter) - ord("a")
    if letter.isdigit() and style == "double-struck":
        return DOUBLE_STRUCK_DIGIT_ZERO + int(letter)
    return None


def rule_based(command: str) -> tuple[int | None, str] | None:
    styled = re.fullmatch(r"\\(math[a-z]+)\{(\w)\}", command)
    if styled and styled.group(1) in STYLE_COMMANDS:
        code_point = styled_letter(STYLE_COMMANDS[styled.group(1)], styled.group(2))
        return code_point, f"{STYLE_COMMANDS[styled.group(1)]} letter"
    upright = re.fullmatch(r"\\[Uu]p(var)?([A-Za-z]+)", command)
    if upright:
        name = (upright.group(1) or "") + upright.group(2)
        if command.startswith("\\Up"):
            name = name[0].upper() + name[1:]
        if name in GREEK_LETTERS:
            return GREEK_LETTERS[name], "upright Greek"
    return None


def load_unicode_xml(path: Path) -> tuple[dict[str, set[int]], dict[int, str]]:
    """Map normalized commands to single code points, and code points to unicode-math."""
    commands: dict[str, set[int]] = defaultdict(set)
    unicode_math: dict[int, str] = {}
    for character in ElementTree.parse(path).getroot().iter("character"):
        parts = character.get("id", "U")[1:].split("-")
        if len(parts) != 1:
            continue
        code_point = int(parts[0], 16)
        for child in character:
            if child.tag not in ("latex", "varlatex", "mathlatex", "AMS", "IEEE"):
                continue
            if not child.text:
                continue
            command = normalize_command(child.text)
            commands[command].add(code_point)
            if child.tag == "mathlatex" and child.get("set") == "unicode-math":
                unicode_math[code_point] = command
    return commands, unicode_math


def build_mapping(symbols: list[dict[str, object]], unicode_xml: Path) -> list[Mapping]:
    commands, unicode_math = load_unicode_xml(unicode_xml)
    mappings = []
    for symbol in symbols:
        key = str(symbol["id"])
        command = normalize_command(str(symbol["command"]))
        if command in MANUAL:
            code_point, note = MANUAL[command]
            source = "manual" if code_point is not None else "none"
            mappings.append(Mapping(key, command, code_point, source, note))
            continue
        ruled = rule_based(command)
        if ruled is not None:
            mappings.append(Mapping(key, command, ruled[0], "rule", ruled[1]))
            continue
        candidates = commands.get(command, set())
        if len(candidates) > 1:
            preferred = {cp for cp in candidates if unicode_math.get(cp) == command}
            candidates = preferred if len(preferred) == 1 else candidates
        if len(candidates) == 1:
            mappings.append(Mapping(key, command, next(iter(candidates)), "w3c", ""))
        else:
            note = "ambiguous in unicode.xml" if candidates else "not in unicode.xml"
            mappings.append(Mapping(key, command, None, "unresolved", note))
    return mappings


def write_mapping(mappings: list[Mapping], path: Path) -> None:
    lines = [
        "# Detexify symbol keys mapped to Unicode code points.",
        "# Generated by glyphsketch.tools.detexify_mapping; edit MANUAL there, not this file.",
        "# Columns: key, LaTeX command, code point (empty if none), source, note.",
        "# Sources: manual = checked by hand; rule = styled alphabet or upright Greek;",
        "# w3c = W3C unicode.xml; none = no single-code-point equivalent.",
        "# The w3c rows come from https://www.w3.org/2003/entities/2007xml/unicode.xml,",
        "# Copyright David Carlisle 1999-2015, W3C Software Notice and License",
        "# (full text and change notice in LICENSES/W3C-20021231.txt).",
    ]
    for mapping in sorted(mappings, key=lambda item: item.key):
        code_point = format_code_point(mapping.code_point) if mapping.code_point else ""
        fields = (mapping.key, mapping.command, code_point, mapping.source, mapping.note)
        lines.append("\t".join(fields))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    tools_dir = stage_dir("tools")
    unicode_xml = download_file(UNICODE_XML_URL, tools_dir / "unicode.xml", UNICODE_XML_SHA256)
    symbols = json.loads((stage_dir("detexify") / SYMBOLS_FILE).read_text(encoding="utf-8"))
    mappings = build_mapping(symbols, unicode_xml)
    write_mapping(mappings, MAPPING_PATH)
    by_source: dict[str, int] = defaultdict(int)
    for mapping in mappings:
        by_source[mapping.source] += 1
    print(f"Wrote {MAPPING_PATH} ({len(mappings)} keys): {dict(by_source)}")
    for mapping in mappings:
        if mapping.source == "unresolved":
            print(f"  unresolved: {mapping.key} {mapping.command} ({mapping.note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
