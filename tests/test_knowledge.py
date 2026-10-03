"""Consistency checks on the engine's own knowledge base (knowledge/).

No fixtures: these read the engine's files directly, so they pass with
AUTOTRAINER_WORKSPACE unset or pointing nowhere. They pin structure and
cross-references, never the coaching content itself.
"""
import re
from datetime import date

import yaml

import apply_merges as am
import build_index as bi
from conftest import REPO_ROOT
from lib import frontmatter

KNOWLEDGE = REPO_ROOT / "knowledge"
STYLES = sorted((KNOWLEDGE / "styles").glob("*.md"))

# spec §10 fields, plus the evidence-audit fields (cardio-coach-spec.md §10)
STYLE_FIELDS = (
    "style", "name", "protocol", "primary_adaptations", "evidence_grade",
    "key_sources", "machine_suitability", "verification_tier",
    "minimum_effective_dose", "time_to_measurable_benefit",
    "consistency_requirement", "detraining_decay", "contraindications",
    "progression_rules", "evidence_grade_code", "studied_population",
    "key_source_ids",
)
GRADE_CODE = re.compile(r"^[ABCD](/[ABCD])?$")
SOURCE_KEYS = ("id", "kind", "citation", "cited_in", "exists", "claim_checked",
               "doi", "pmid", "url", "checked_on", "note")
STUB_MARKER = "- Status: UNCONFIRMED - no console photo yet"
OPEN_DECISION_STUBS = {"versaclimber"}
# files that may name a sources.yaml id; each must appear in that id's cited_in
CITING_FILES = sorted(
    list(KNOWLEDGE.glob("**/*.md")) + [KNOWLEDGE / "reference-values.yaml"]
    + list((REPO_ROOT / "skills" / "coach").glob("*.md"))
    + [REPO_ROOT / "cardio-coach-spec.md",
       REPO_ROOT / "templates" / "workspace" / "benchmarks.md"]
)


def _sources() -> dict:
    data = yaml.safe_load((KNOWLEDGE / "sources.yaml").read_text(encoding="utf-8"))
    return {s["id"]: s for s in data["sources"]}


def _style(path):
    fm, _ = frontmatter.load(path)
    return fm


def _headed_sections(path) -> dict[str, str]:
    """`## heading` -> section text, skipping headings inside code fences."""
    sections, current, in_fence = {}, None, False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            current = line[3:].strip()
            assert current not in sections, f"{path.name}: duplicate heading {current!r}"
            sections[current] = ""
            continue
        if current is not None:
            sections[current] += line + "\n"
    return sections


# ------------------------------------------------------------------- styles

def test_styles_exist():
    assert len(STYLES) >= 11


def test_style_required_fields():
    for path in STYLES:
        fm = _style(path)
        missing = [f for f in STYLE_FIELDS if f not in fm]
        assert not missing, f"{path.name}: missing {missing}"
        assert fm["style"] == path.stem, path.name
        assert fm["verification_tier"] in (1, 2, 3), path.name
        assert isinstance(fm["studied_population"], str) and fm["studied_population"].strip()


def test_style_grade_code_and_split():
    for path in STYLES:
        fm = _style(path)
        code = fm["evidence_grade_code"]
        assert isinstance(code, str) and GRADE_CODE.match(code), f"{path.name}: {code!r}"
        split = fm.get("evidence_grade_split")
        if split is not None:
            # a split names the claim behind each of the two codes
            assert isinstance(split, dict) and len(split) == 2, path.name
            assert set(split.values()) == set(code.split("/")), path.name


def test_style_grade_code_agrees_with_headline_grade():
    # the machine-readable code must carry the dossier's headline letters; it
    # may add a second letter only where a split names the claim behind it
    for path in STYLES:
        fm = _style(path)
        headline = set(re.findall(r"\b[ABCD]\b", str(fm["evidence_grade"])))
        code = set(fm["evidence_grade_code"].split("/"))
        assert headline, f"{path.name}: no letter in evidence_grade"
        if fm.get("evidence_grade_split") is None:
            assert code == headline, f"{path.name}: code {code} vs headline {headline}"
        else:
            assert headline <= code, f"{path.name}: code {code} drops headline {headline}"


def test_style_key_source_ids_resolve():
    sources = _sources()
    for path in STYLES:
        ids = _style(path)["key_source_ids"]
        assert isinstance(ids, list), path.name
        for sid in ids:
            assert sid in sources, f"{path.name}: unknown source id {sid!r}"
            cited = [c.split("#")[0] for c in sources[sid]["cited_in"]]
            assert f"knowledge/styles/{path.name}" in cited, \
                f"sources.yaml {sid}: cited_in should list styles/{path.name}"


def test_style_machine_suitability_uses_modalities():
    allowed = bi.MODALITIES | {"all"}
    for path in STYLES:
        suit = _style(path)["machine_suitability"]
        for level, value in suit.items():
            if level == "notes":
                continue
            unknown = set(value) - allowed
            assert not unknown, f"{path.name}: {level} has unknown modalities {unknown}"


# ----------------------------------------------------------------- machines

def test_machine_headings_are_known_ids_or_stubs():
    sections = _headed_sections(KNOWLEDGE / "machines.md")
    assert sections
    for machine, text in sections.items():
        stub = text.lstrip("\n").startswith(STUB_MARKER)
        assert machine in am.MACHINE_TO_MODALITY or stub, \
            f"machines.md: {machine!r} is neither a known machine id nor a marked stub"


def test_machine_stubs_claim_no_example_photos():
    for machine, text in _headed_sections(KNOWLEDGE / "machines.md").items():
        if text.lstrip("\n").startswith(STUB_MARKER):
            assert "Example photos:" not in text, f"stub {machine!r} cites photos"


def test_open_decision_stubs_stay_stubs():
    # machines the athlete asked to decide later: no readouts until a console
    # photo exists. Empty this set deliberately when the full entry is written.
    sections = _headed_sections(KNOWLEDGE / "machines.md")
    for machine in OPEN_DECISION_STUBS:
        text = sections[machine]
        assert text.lstrip("\n").startswith(STUB_MARKER), f"{machine}: stub marker missing"
        assert "No readouts are claimed" in text, machine
        for field in ("- Layout:", "- Units/quirks:", "Example photos:"):
            assert field not in text, f"stub {machine!r} claims {field!r}"


# --------------------------------------------------------------- modalities

def test_modalities_md_covers_vocabulary():
    sections = set(_headed_sections(KNOWLEDGE / "modalities.md"))
    assert bi.MODALITIES <= sections, f"missing: {bi.MODALITIES - sections}"
    assert sections - bi.MODALITIES == {"Across modalities"}


def test_schema_modality_vocabulary_matches_build_index():
    text = (REPO_ROOT / "docs" / "schema.md").read_text(encoding="utf-8")
    block = text.split("### Modality vocabulary", 1)[1].split("`", 2)[1]
    vocab = {m.strip() for m in block.split("|")}
    assert vocab == bi.MODALITIES


def test_machine_to_modality_targets_are_vocabulary():
    assert set(am.MACHINE_TO_MODALITY.values()) <= bi.MODALITIES


# --------------------------------------------------------- reference values

def test_reference_values_shape():
    refs = yaml.safe_load((KNOWLEDGE / "reference-values.yaml").read_text(encoding="utf-8"))
    for sex, decades in refs["percentiles"].items():
        assert sex in ("male", "female")
        for decade, pair in decades.items():
            assert re.match(r"^\d{2}-\d{2}$", decade), decade
            lo, hi = int(decade[:2]), int(decade[3:])
            assert lo % 10 == 0 and hi == lo + 9, decade  # build_dashboard's decade key
            assert len(pair) == 2 and pair[0] < pair[1], (sex, decade)
    for a in refs["athletes"]:
        assert isinstance(a["label"], str) and isinstance(a["note"], str)
        assert isinstance(a["vo2max"], (int, float))
    est = refs["estimate"]
    for key in ("p20_to_pvo2max_divisor", "acsm_slope", "acsm_intercept"):
        assert isinstance(est[key], (int, float)), key
    for key in ("power_estimate", "hr_ratio_estimate", "watch_estimate"):
        assert isinstance(refs["method_caveats"][key], str), key


# ------------------------------------------------------------------ sources

def test_sources_ledger_shape():
    data = yaml.safe_load((KNOWLEDGE / "sources.yaml").read_text(encoding="utf-8"))
    ids = [s.get("id") for s in data["sources"]]
    assert len(ids) == len(set(ids)), "duplicate source ids"
    for s in data["sources"]:
        missing = [k for k in SOURCE_KEYS if k not in s]
        assert not missing, f"{s.get('id')}: missing {missing}"
        assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", s["id"]), s["id"]
        if s["kind"] in ("paper", "meta-analysis", "review"):
            assert re.search(r"-(\d{4}|nd)$", s["id"]), f"{s['id']}: papers are author-year"
        assert s["exists"] in (None, True, False), s["id"]
        assert s["claim_checked"] in (True, False), s["id"]
        assert s["checked_on"] is None or isinstance(s["checked_on"], date), s["id"]
        for ref in s["cited_in"]:
            assert (REPO_ROOT / ref.split("#")[0]).is_file(), f"{s['id']}: cited_in {ref}"


def test_claim_checked_requires_existence_and_a_record():
    for sid, s in _sources().items():
        if s["claim_checked"]:
            assert s["exists"] is True, f"{sid}: claim_checked without exists: true"
            assert s["checked_on"] is not None and s["note"], sid
        if s["exists"] is True:
            assert s["doi"] or s["pmid"] or s["url"], f"{sid}: exists without an identifier"


def test_cited_in_lists_every_file_naming_the_id():
    # cited_in is how statements get found when a source turns out not to
    # support them, so any file naming an id must be listed there
    sources = _sources()
    for path in CITING_FILES:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT).as_posix()
        for sid, s in sources.items():
            if re.search(rf"(?<![\w-]){re.escape(sid)}(?![\w-])", text):
                cited = {c.split("#")[0] for c in s["cited_in"]}
                assert rel in cited, f"sources.yaml {sid}: cited_in should list {rel}"


def test_not_checked_figures_are_tagged_where_they_appear():
    # claim_checked: true covers only what a note names as read; a figure the
    # note quotes as "Not checked" must carry [unverified] wherever it is used
    lines = []
    for path in sorted(KNOWLEDGE.glob("**/*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if path.name == "evidence.md" and line.startswith("## Known weak claims"):
                break  # the list of weak claims names them by design
            lines.append((path.name, line))
    for sid, s in _sources().items():
        for figure in re.findall(r'Not checked:\s*"([^"]+)"', s["note"] or ""):
            hits = [(name, line) for name, line in lines if figure in line]
            assert hits, f"{sid}: not-checked figure {figure!r} appears nowhere"
            for name, line in hits:
                assert "[unverified" in line, f"{name}: {figure!r} ({sid}) is untagged"

