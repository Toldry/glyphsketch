from glyphsketch.eval_report import _package_description, comparison_section


def test_package_description_comes_from_the_export_summary() -> None:
    package = {"characters": 10776, "shipped_bytes": 6_300_000}
    assert _package_description(package) == "10,776 characters, 6.3 MB, int8"
    assert _package_description(None) == "int8"


def test_comparison_uses_the_index_size() -> None:
    overall = {
        "samples": 50,
        "characters": 20,
        "top1": 0.5,
        "top5": 0.8,
        "top1_confusable": 0.6,
        "top5_confusable": 0.9,
    }
    report = {"recognizer": "r", "overall": overall}
    comparison = {
        "symbols": 400,
        "index_characters": 10000,
        "eligible_samples": 100,
        "test_samples": 50,
        "test_characters": 20,
        "reports": dict.fromkeys(
            ("detypify", "glyphsketch-restricted", "glyphsketch", "glyphsketch-tiles"), report
        ),
    }
    text = "\n".join(comparison_section(comparison))
    assert "retrieves among 10,000 characters" in text
    assert "covers 25 times as many" in text
