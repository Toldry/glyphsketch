"""Turn dump XML into the characters a reader sees, for counting.

Only articles count (namespace 0, not redirects). Wikitext is cleaned with a few rules
rather than parsed: comments, code-like blocks and URLs are dropped; tags, link and
template brackets, template parameter names, table syntax and bold/italic quotes are
removed, while their text is kept. It isn't exact (template names survive as text, for
example), but the leftovers are ASCII, which is common anyway.

Maths is written in LaTeX inside ``<math>``, so ``∫`` would otherwise hardly ever
appear. LaTeX commands are mapped to code points with the reviewed Detexify mapping
(``resources/detexify_unicode.tsv``); other characters count as themselves, except
``-`` (typeset as the minus sign U+2212) and ``'`` (the prime U+2032). Braces, ``^``,
``_``, ``&`` and ``$`` are syntax and don't count.
"""

import html
import re
import unicodedata
from collections import Counter
from collections.abc import Iterator
from functools import lru_cache

from glyphsketch.realdata.detexify import MAPPING_PATH as DETEXIFY_MAPPING_PATH

PAGE_PATTERN = re.compile(r"<page>(.*?)</page>", re.S)
NAMESPACE_PATTERN = re.compile(r"<ns>(\d+)</ns>")
TEXT_PATTERN = re.compile(r"<text\b[^>]*>(.*?)</text>", re.S)

COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.S)
MATH_PATTERN = re.compile(r"<math\b[^>]*>(.*?)</math>", re.S | re.I)
DROPPED_BLOCK_PATTERN = re.compile(
    r"<(syntaxhighlight|source|pre|code|score|timeline|graph|mapframe|chem|ce)\b[^>]*>"
    r".*?</\1>",
    re.S | re.I,
)
TAG_PATTERN = re.compile(r"</?[A-Za-z][^<>]*/?>")
URL_PATTERN = re.compile(r"https?://[^\s\]|}<>]+")
MAGIC_WORD_PATTERN = re.compile(r"__[A-Z]+__")
TEMPLATE_PARAMETER_PATTERN = re.compile(r"\|\s*[\w-]+\s*=")
LINE_PREFIX_PATTERN = re.compile(r"^[*#:;]+|^=+|=+\s*$", re.M)
MARKUP_TOKENS = (
    "'''", "''", "{{", "}}", "[[", "]]", "[", "]", "{|", "|}", "|-", "|+", "|", "!!",
)  # fmt: skip

LATEX_TOKEN_PATTERN = re.compile(r"\\([A-Za-z]+)(?:\s*\{\s*([A-Za-z0-9])\s*\})?|\\(.)|(\S)")
LATEX_SYNTAX = set("{}^_&$~\\")
LATEX_CHARACTER_OVERRIDES = {"-": 0x2212, "'": 0x2032}
# Common commands the Detexify list only has under another name (\\le is \\leq), or lacks.
LATEX_ALIASES = {
    "\\le": 0x2264,
    "\\ge": 0x2265,
    "\\ne": 0x2260,
    "\\to": 0x2192,
    "\\gets": 0x2190,
    "\\lnot": 0x00AC,
    "\\land": 0x2227,
    "\\lor": 0x2228,
    "\\sqrt": 0x221A,
    "\\lbrace": 0x007B,
    "\\rbrace": 0x007D,
    "\\lvert": 0x007C,
    "\\rvert": 0x007C,
    "\\Vert": 0x2016,
    "\\implies": 0x27F9,
    "\\iff": 0x27FA,
}


# Styled alphabets with distinct shapes. \\mathbf, \\mathit and the like are drawn as
# plain letters, so they count as the letter itself.
STYLED_ALPHABETS = {
    "mathbb": ("DOUBLE-STRUCK",),
    "mathcal": ("SCRIPT",),
    "mathscr": ("SCRIPT",),
    "mathfrak": ("FRAKTUR", "BLACK-LETTER"),
}
DIGIT_NAMES = ["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"]


def styled_letter(command: str, letter: str) -> int | None:
    """``\\mathbb{R}`` → ℝ: the maths alphanumeric character, or its Letterlike exception."""
    styles = STYLED_ALPHABETS.get(command)
    if styles is None:
        return None
    if letter.isdigit():
        kind = f"DIGIT {DIGIT_NAMES[int(letter)]}"
    else:
        kind = f"{'CAPITAL' if letter.isupper() else 'SMALL'} {letter.upper()}"
    for style in styles:
        for name in (f"MATHEMATICAL {styles[0]} {kind}", f"{style} {kind}"):
            try:
                return ord(unicodedata.lookup(name))
            except KeyError:
                continue
    return None


@lru_cache(maxsize=1)
def latex_commands() -> dict[str, int]:
    """LaTeX command (``\\alpha``, ``\\mathbb{R}``) → code point, from the Detexify mapping."""
    commands: dict[str, int] = dict(LATEX_ALIASES)
    for line in DETEXIFY_MAPPING_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        columns = line.split("\t")
        if len(columns) >= 3 and columns[2].startswith("U+"):
            commands.setdefault(columns[1].replace(" ", ""), int(columns[2][2:], 16))
    return commands


def latex_code_points(latex: str) -> Iterator[int]:
    commands = latex_commands()
    for match in LATEX_TOKEN_PATTERN.finditer(latex):
        name, argument, escaped, character = match.groups()
        if name is not None:
            with_argument = f"\\{name}{{{argument}}}" if argument else None
            if with_argument and with_argument in commands:
                yield commands[with_argument]
                continue
            styled = styled_letter(name, argument) if argument else None
            if styled is not None:
                yield styled
                continue
            if f"\\{name}" in commands:
                yield commands[f"\\{name}"]
            if argument:  # e.g. \mathrm{d}: the argument is still drawn
                yield ord(argument)
        elif escaped is not None:
            if escaped in "{}%#&$_":
                yield ord(escaped)
        elif character not in LATEX_SYNTAX:
            yield LATEX_CHARACTER_OVERRIDES.get(character, ord(character))


def article_texts(xml: str) -> Iterator[str]:
    """Raw wikitext of every article page (namespace 0, not a redirect) in dump XML."""
    for page in PAGE_PATTERN.finditer(xml):
        body = page.group(1)
        namespace = NAMESPACE_PATTERN.search(body)
        if namespace is None or namespace.group(1) != "0" or "<redirect" in body:
            continue
        text = TEXT_PATTERN.search(body)
        if text:
            yield html.unescape(text.group(1))


def clean_wikitext(wikitext: str) -> tuple[str, list[str]]:
    """(visible text, LaTeX of the ``<math>`` elements)."""
    text = COMMENT_PATTERN.sub("", wikitext)
    maths = MATH_PATTERN.findall(text)
    text = MATH_PATTERN.sub(" ", text)
    text = DROPPED_BLOCK_PATTERN.sub(" ", text)
    text = TAG_PATTERN.sub("", text)
    text = URL_PATTERN.sub("", text)
    text = MAGIC_WORD_PATTERN.sub("", text)
    text = TEMPLATE_PARAMETER_PATTERN.sub(" ", text)
    for token in MARKUP_TOKENS:
        text = text.replace(token, " " if token in ("|", "!!", "|-", "|+") else "")
    text = LINE_PREFIX_PATTERN.sub("", text)
    return html.unescape(text), maths


def count_characters(xml: str) -> tuple[Counter[int], int]:
    """Code point counts over the articles in ``xml`` (whitespace excluded), and pages."""
    text_counts: Counter[str] = Counter()
    counts: Counter[int] = Counter()
    pages = 0
    for wikitext in article_texts(xml):
        pages += 1
        text, maths = clean_wikitext(wikitext)
        text_counts.update(text)
        for latex in maths:
            counts.update(latex_code_points(latex))
    for character, count in text_counts.items():
        if not character.isspace():
            counts[ord(character)] += count
    return counts, pages
