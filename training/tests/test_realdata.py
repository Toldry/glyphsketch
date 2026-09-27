import gzip
import zipfile
from pathlib import Path

import numpy as np
import pytest

from conftest import real_stage_dir_or_skip
from glyphsketch.charset import load_charset_config
from glyphsketch.realdata import detexify, omniglot, uji
from glyphsketch.realdata.build import SAMPLES_FILE
from glyphsketch.realdata.samples import DrawingSample, SampleSet
from glyphsketch.realdata.splits import (
    TEST_FRACTION,
    held_out_mask,
    is_test_writer,
    is_zero_shot_character,
    stable_fraction,
    training_mask,
    zero_shot_mask,
)


def _sample(code_point: int, writer: str, dataset: str = "toy") -> DrawingSample:
    strokes = [np.array([[0, 0], [1, 1]], dtype=np.float32), np.array([[2, 2]])]
    return DrawingSample(dataset, f"{writer}-{code_point}", writer, chr(code_point), code_point,
                         strokes)  # fmt: skip


def test_sample_set_round_trips_through_npz(tmp_path: Path) -> None:
    samples = SampleSet.from_samples([_sample(0x41, "w1"), _sample(0x3B1, "w2")])
    path = tmp_path / "samples.npz"
    samples.save(path)
    loaded = SampleSet.load(path)
    assert len(loaded) == 2
    assert loaded.code_points.tolist() == [0x41, 0x3B1]
    assert [stroke.tolist() for stroke in loaded.strokes(1)] == [[[0, 0], [1, 1]], [[2, 2]]]
    assert loaded.sample(0).writer == "w1"
    assert loaded.subset([1]).code_points.tolist() == [0x3B1]


DUMP = """\
SET client_encoding = 'UTF8';
CREATE TABLE samples (id integer NOT NULL, key text, strokes json);
COPY samples (id, key, strokes) FROM stdin;
1\tlatex2e-OT1-_alpha\t[[[10,20,1362942716695],[12,25,1362942716700]],[[30,40,1362942716800]]]
2\tlatex2e-OT1-_unmapped\t[[[1,2,1362942716695]]]
3\tlatex2e-OT1-_alpha\t[[[5,5,1400000000000],[6,7,1400000000100]]]
\\.
"""


def test_detexify_dump_parsing_and_pseudo_writers(tmp_path: Path) -> None:
    dump_path = tmp_path / "dump.sql.gz"
    with gzip.open(dump_path, "wt", encoding="utf-8") as stream:
        stream.write(DUMP)
    records = list(detexify.parse_dump(dump_path))
    assert [record.key for record in records] == [
        "latex2e-OT1-_alpha",
        "latex2e-OT1-_unmapped",
        "latex2e-OT1-_alpha",
    ]
    assert records[0].strokes[0].tolist() == [[10, 20], [12, 25]]
    assert detexify.pseudo_writer(records[0].first_timestamp_ms) == "day-2013-03-10"
    mapping = {
        "latex2e-OT1-_alpha": detexify.MappingEntry(
            "latex2e-OT1-_alpha", "\\alpha", 0x3B1, "w3c", ""
        )
    }
    samples = list(detexify.detexify_samples(dump_path, mapping, {0x3B1}))
    assert [sample.sample_id for sample in samples] == ["1", "3"]
    assert samples[1].writer == "day-2014-05-13"
    assert not list(detexify.detexify_samples(dump_path, mapping, {0x41}))


def test_omniglot_stroke_files_flip_y_and_split_strokes() -> None:
    strokes = omniglot.parse_stroke_file("START\n1.5,-2,0\n3,-4,10\nBREAK\n5,-6,20\nBREAK\n")
    assert [stroke.tolist() for stroke in strokes] == [[[1.5, 2.0], [3.0, 4.0]], [[5.0, 6.0]]]


def test_omniglot_samples_use_the_mapping_and_drawer_ids(tmp_path: Path) -> None:
    archive_names = list(omniglot.STROKE_ARCHIVES)
    with zipfile.ZipFile(tmp_path / archive_names[0], "w") as archive:
        archive.writestr("strokes_background/Greek/character01/0394_07.txt", "START\n1,1,0\n")
        archive.writestr("strokes_background/Greek/character02/0395_07.txt", "START\n1,1,0\n")
    with zipfile.ZipFile(tmp_path / archive_names[1], "w") as archive:
        archive.writestr("strokes_evaluation/Tengwar/character01/1000_01.txt", "START\n1,1,0\n")
    mapping = {("Greek", 1): omniglot.OmniglotMappingEntry("Greek", 1, 0x3B1, "")}
    samples = list(omniglot.omniglot_samples(tmp_path, mapping, {0x3B1}))
    assert len(samples) == 1
    assert samples[0].writer == "Greek/drawer07"
    assert samples[0].label == "Greek/character01"
    assert samples[0].code_point == 0x3B1


UJI_TEXT = (
    "// UJI: 100 units per millimetre\r\n"
    "// ASCII char: a\r\n"
    "WORD a trn_UJI_W01-01\r\n"
    "  NUMSTROKES 2\r\n"
    "  POINTS 2 # 1 2 3 4\r\n"
    "  POINTS 1 # 5 6\r\n"
    "// Non-ASCII char: ntilde\r\n"
    "WORD ñ tst_UPV_W18-02\r\n"
    "  NUMSTROKES 1\r\n"
    "  POINTS 1 # 7 8\r\n"
)


def test_uji_parsing_handles_crlf_and_writer_ids() -> None:
    parsed = list(uji.parse_uji_text(UJI_TEXT))
    assert [(char, writer, repetition) for char, writer, repetition, _ in parsed] == [
        ("a", "UJI_W01", 1),
        ("ñ", "UPV_W18", 2),
    ]
    assert [stroke.tolist() for stroke in parsed[0][3]] == [[[1, 2], [3, 4]], [[5, 6]]]


def test_uji_samples_skip_characters_outside_the_glyph_set(tmp_path: Path) -> None:
    with zipfile.ZipFile(tmp_path / uji.ARCHIVE_NAME, "w") as archive:
        archive.writestr(uji.DATA_MEMBER, UJI_TEXT)
    samples = list(uji.uji_samples(tmp_path, {ord("ñ")}))
    assert [(sample.label, sample.sample_id) for sample in samples] == [("ñ", "UPV_W18-ñ-2")]


def test_splits_are_deterministic_and_roughly_the_right_size() -> None:
    assert stable_fraction("x") == stable_fraction("x")
    writers = [f"writer{index}" for index in range(4000)]
    share = np.mean([is_test_writer("toy", writer) for writer in writers])
    assert abs(share - TEST_FRACTION) < 0.03
    assert is_zero_shot_character(0x41) == is_zero_shot_character(0x41)


def test_training_mask_excludes_test_writers_and_zero_shot_characters() -> None:
    samples = SampleSet.from_samples(
        _sample(code_point, f"writer{writer}")
        for code_point in range(0x100, 0x140)
        for writer in range(30)
    )
    train = training_mask(samples)
    assert not (train & held_out_mask(samples)).any()
    assert not (train & zero_shot_mask(samples)).any()
    assert train.any() and (~train).any()


def test_detexify_mapping_file_is_complete_and_explains_every_gap() -> None:
    mapping = detexify.load_mapping()
    assert len(mapping) == 1098
    for entry in mapping.values():
        assert entry.source in {"manual", "rule", "w3c", "none"}, entry.key
        if entry.code_point is None:
            assert entry.source == "none" and entry.note, entry.key
    assert mapping["latex2e-OT1-_phi"].code_point == 0x3D5
    assert mapping["latex2e-OT1-_varphi"].code_point == 0x3C6
    assert mapping["latex2e-OT1-_epsilon"].code_point == 0x3F5
    assert mapping["dsfont-OT1-_mathds{R}"].code_point == 0x211D


def test_omniglot_mapping_file_covers_six_alphabets() -> None:
    mapping = omniglot.load_mapping()
    alphabets = {alphabet for alphabet, _ in mapping}
    assert alphabets == {
        "Latin",
        "Greek",
        "Cyrillic",
        "Hebrew",
        "Malay_(Jawi_-_Arabic)",
        "Old_Church_Slavonic_(Cyrillic)",
    }
    for entry in mapping.values():
        if entry.code_point is None:
            assert entry.note.startswith("excluded:")
    assert mapping[("Latin", 1)].code_point == ord("a")
    assert mapping[("Hebrew", 22)].code_point == ord("ת")


@pytest.mark.data
def test_real_samples() -> None:
    realdata_dir = real_stage_dir_or_skip("realdata", SAMPLES_FILE)
    samples = SampleSet.load(realdata_dir / SAMPLES_FILE)
    assert len(samples) > 200_000
    assert set(samples.datasets.tolist()) == {"detexify", "omniglot", "uji"}
    blocks = set(load_charset_config().blocks)
    assert blocks
    alpha = (samples.labels == "latex2e-OT1-_alpha") & (samples.datasets == "detexify")
    assert set(samples.code_points[alpha].tolist()) == {0x3B1}
    uji_rows = samples.datasets == "uji"
    assert all(
        chr(code_point) == label
        for code_point, label in zip(
            samples.code_points[uji_rows].tolist(), samples.labels[uji_rows].tolist(), strict=True
        )
    )
    is_test = held_out_mask(samples)
    assert 0.1 < is_test.mean() < 0.3
    test_writers = set(samples.writers[is_test].tolist())
    train_writers = set(samples.writers[~is_test].tolist())
    assert not test_writers & train_writers
