import pytest

from engine.agent import parse_request
from engine.brand.colors import contrast, norm_hex, roles_from_palette, text_on
from engine.render.common import fit_size, split_number
from engine.util import extract_json, slugify


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure!\n```json\n{"a": {"b": 2}}\n```') == {"a": {"b": 2}}
    assert extract_json('<think>hmm {no}</think> here {"x": "}"} trailing') == {"x": "}"}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_slugify():
    assert slugify("Q3 Review: Café!") == "q3-review-cafe"
    assert slugify("") == "untitled"


def test_colors():
    assert norm_hex("abc") == "#AABBCC"
    assert round(contrast("#000000", "#FFFFFF")) == 21
    assert text_on("#111111") == "#FFFFFF"
    roles = roles_from_palette([("#1D4ED8", 0.6), ("#F59E0B", 0.3), ("#000000", 0.1)])
    assert roles["primary"] == "#1D4ED8" and roles["accent"] == "#F59E0B"


def test_numbers():
    assert split_number("$1,250.5M") == ("$", 1250.5, "M", 1)
    assert split_number("n/a")[1] is None
    size, ok = fit_size(["short"], 1000, 200, 40, 20)
    assert ok and size == 40


def test_parse_request_front_matter(tmp_path):
    f = tmp_path / "req.md"
    f.write_text("---\naction: edit\ndeck: q3\nslides: 8\n---\nSlide 2: add a chart\n", encoding="utf-8")
    r = parse_request(f)
    assert (r.action, r.deck, r.slides) == ("edit", "q3", 8)
    assert r.instructions == "Slide 2: add a chart"


def test_parse_request_folder_and_plain(tmp_path):
    d = tmp_path / "job"
    d.mkdir()
    (d / "request.md").write_text("Make a deck", encoding="utf-8")
    (d / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    r = parse_request(d)
    assert r.action == "create" and [p.name for p in r.files] == ["data.csv"]
    bad = tmp_path / "bad.md"
    bad.write_text("---\naction: explode\n---\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_request(bad)
