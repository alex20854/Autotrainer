import pytest

from lib import frontmatter


def test_round_trip():
    data = {"id": "2026-08-08-bikeerg-z2", "duration_s": 2801, "sources": [{"kind": "health"}]}
    body = "Felt easy today.\n\nSecond paragraph."
    doc = frontmatter.dump(data, body)
    parsed, parsed_body = frontmatter.parse(doc)
    assert parsed == data
    assert parsed_body.strip() == body


def test_frontmatter_only_document():
    doc = "---\nid: x\n---\n"
    data, body = frontmatter.parse(doc)
    assert data == {"id": "x"}
    assert body == ""


def test_rejects_missing_frontmatter():
    with pytest.raises(frontmatter.FrontmatterError):
        frontmatter.parse("just a markdown file\n")


def test_update_preserves_body(tmp_path):
    path = tmp_path / "session.md"
    frontmatter.save(path, {"id": "s1", "computed": None}, "athlete notes here")
    frontmatter.update(path, {"computed": {"decoupling_pct": 3.1}})
    data, body = frontmatter.load(path)
    assert data["computed"] == {"decoupling_pct": 3.1}
    assert data["id"] == "s1"
    assert "athlete notes here" in body
