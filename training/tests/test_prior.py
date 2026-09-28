import bz2
import math
from collections import Counter

import pytest

from glyphsketch.prior.build import log_prior, raise_to_flat_prior
from glyphsketch.prior.sample import (
    DumpFile,
    complete_streams,
    dump_files,
    load_prior_config,
    plan_chunks,
)
from glyphsketch.prior.wikitext import (
    article_texts,
    clean_wikitext,
    count_characters,
    latex_code_points,
)


def _page(title: str, text: str, namespace: int = 0, redirect: bool = False) -> str:
    redirect_tag = f'<redirect title="{title}" />' if redirect else ""
    return (
        f"<page><title>{title}</title><ns>{namespace}</ns>{redirect_tag}"
        f'<revision><text bytes="1" xml:space="preserve">{text}</text></revision></page>'
    )


def test_complete_streams_skip_the_partial_streams_at_both_ends() -> None:
    streams = [bz2.compress(f"<page>{index}</page>".encode() * 50) for index in range(5)]
    dump = b"".join(streams)
    start = len(streams[0]) // 2
    end = len(dump) - len(streams[4]) // 2
    recovered = list(complete_streams(dump[start:end]))
    assert [block[:7] for block in recovered] == [b"<page>1", b"<page>2", b"<page>3"]


def test_chunks_spread_evenly_over_all_parts_and_stay_inside_files() -> None:
    files = [DumpFile("a", 1000, ""), DumpFile("b", 3000, "")]
    chunks = plan_chunks(files, 4, 200)
    assert [chunk.file_name for chunk in chunks] == ["a", "b", "b", "b"]
    for chunk in chunks:
        size = 1000 if chunk.file_name == "a" else 3000
        assert 0 <= chunk.start < chunk.end <= size and chunk.end - chunk.start == 200


def test_dump_files_prefers_the_single_file_and_orders_parts() -> None:
    def status(names: list[str]) -> dict[str, object]:
        files = {name: {"size": 10, "sha1": "x"} for name in names}
        return {"jobs": {"articlesmultistreamdump": {"status": "done", "files": files}}}

    parts = [
        "xwiki-1-pages-articles-multistream10.xml-p9p10.bz2",
        "xwiki-1-pages-articles-multistream2.xml-p3p4.bz2",
        "xwiki-1-pages-articles-multistream-index2.txt-p3p4.bz2",
    ]
    assert [file.name for file in dump_files(status(parts))] == parts[1::-1]
    single = ["xwiki-1-pages-articles-multistream.xml.bz2", *parts]
    assert [file.name for file in dump_files(status(single))] == single[:1]


def test_only_articles_count() -> None:
    xml = (
        _page("A", "article")
        + _page("B", "talk", namespace=1)
        + _page("C", "#REDIRECT [[A]]", redirect=True)
    )
    assert list(article_texts(xml)) == ["article"]


def test_cleaning_keeps_visible_text_and_extracts_maths() -> None:
    wikitext = (
        "'''Bold''' [[Link|shown]] {{cite|title=x|url=y}} [https://a.org site] "
        "<ref>note</ref><!-- hidden -->"
        " see https://example.org/a <math>\\int_0^1 x\\,dx \\le 2</math> café&nbsp;"
        "<syntaxhighlight lang=c>int main();</syntaxhighlight>"
    )
    text, maths = clean_wikitext(wikitext)
    assert "Bold" in text and "shown" in text and "note" in text and "café" in text
    assert "site" in text and "title" not in text
    for dropped in ("'''", "[", "{{", "hidden", "https", "main", "<", "="):
        assert dropped not in text
    assert maths == ["\\int_0^1 x\\,dx \\le 2"]


def test_latex_maps_commands_and_skips_syntax() -> None:
    code_points = list(latex_code_points("\\int_0^1 x - y' \\le \\mathbb{R} \\alpha{}"))
    assert code_points[0] == ord("∫")
    assert ord("∫") in code_points and ord("≤") in code_points and ord("α") in code_points
    assert ord("ℝ") in code_points and 0x2212 in code_points and 0x2032 in code_points
    assert ord("_") not in code_points and ord("{") not in code_points


def test_count_characters_ignores_whitespace() -> None:
    counts, pages = count_characters(_page("A", "ab a\n<math>\\pi</math>"))
    assert pages == 1
    assert counts == Counter({ord("a"): 2, ord("b"): 1, ord("π"): 1})


def test_log_prior_averages_languages_and_smooths() -> None:
    counts = {"x": Counter({1: 3, 2: 1}), "y": Counter({3: 4})}
    prior = log_prior(counts, [1, 2, 3], smoothing=0.5)
    expected_one = ((3.5 / 5.5) + (0.5 / 5.5)) / 2
    assert prior[1] == pytest.approx(math.log(expected_one))
    assert prior[1] > prior[2] and prior[3] > prior[2]
    assert sum(math.exp(value) for value in prior.values()) == pytest.approx(1.0)


def test_config_lists_languages_with_scripts() -> None:
    config = load_prior_config()
    codes = [language.code for language in config.languages]
    assert "en" in codes and len(codes) == len(set(codes))
    assert all(language.scripts for language in config.languages)


def test_emoji_get_at_least_the_median_prior_of_characters_in_regular_use() -> None:
    prior = {1: -3.0, 2: -5.0, 3: -9.0, 6: -19.0, 4: -20.0, 5: -2.0}
    totals = {1: 5000, 2: 900, 3: 150, 6: 2, 5: 40}
    raised, level = raise_to_flat_prior(prior, {4, 5}, totals)
    assert level == -5.0  # median of 1, 2, 3; character 6 is too rare to count
    assert raised[4] == -5.0 and raised[5] == -2.0  # a frequent emoji keeps its own
    assert raised[6] == -19.0
