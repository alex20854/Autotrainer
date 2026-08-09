"""End-to-end fixture flow: parsers -> proposals -> merges -> metrics -> index.

Mirrors what scripts/ingest.py does, using the pure functions with temp dirs.
The fixture set encodes spec §7's acceptance shape: the clean pair auto-merges,
the contested photo goes to review, single-source sessions are first-class.
"""

import json

import yaml

import apply_merges as am
import build_index as bi
import compute_metrics as cm
import parse_auto_export
import parse_c2
import parse_health_export
import propose_matches as pm
from conftest import FIXTURES, REPO_ROOT
from lib import records


def test_full_ingest_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "REPO_ROOT", tmp_path)
    workouts_dir = tmp_path / "data" / "derived" / "workouts"
    sessions_dir = tmp_path / "sessions"

    # 1. parsers (all sources feed the same normalizer)
    parse_health_export.parse_export(FIXTURES / "export.xml", workouts_dir)
    parse_auto_export.parse_file(FIXTURES / "auto_export.json", workouts_dir)
    parse_c2.parse_file(FIXTURES / "c2_logbook.csv", workouts_dir)
    workouts = records.load_records(workouts_dir)
    assert len(workouts) == 7  # 5 health-export + 1 auto-export + 1 c2

    # 2. photo sidecars as Claude's vision extraction would leave them
    sc_dir = tmp_path / "sc"
    sc_dir.mkdir()
    (sc_dir / "p1.yaml").write_text(yaml.safe_dump({
        "photo": "data/raw/photos/p1.jpeg", "exif_time": "2026-08-05T06:33:00",
        "extracted": True, "machine": "concept2-bikeerg", "machine_confidence": "high",
        "fields": {"elapsed_time_s": {"value": 1800}, "watts_avg": {"value": 185},
                   "distance_m": {"value": 14100}, "kcal": {"value": 320}},
    }))
    (sc_dir / "p2.yaml").write_text(yaml.safe_dump({
        "photo": "data/raw/photos/p2.jpeg", "exif_time": "2026-08-06T06:42:00",
        "extracted": True, "machine": "concept2-skierg", "machine_confidence": "high",
        "fields": {"elapsed_time_s": {"value": 1500}},
    }))

    # 3. proposals, using the repo's real matching config
    config = yaml.safe_load((REPO_ROOT / "config" / "athlete.yaml").read_text())
    proposals = pm.propose(workouts, pm.load_sidecars(sc_dir), set(), config["matching"])
    auto, ambiguous = proposals["auto_merge"], proposals["ambiguous"]
    # clean pair + 3 single-source (run, auto-export ride, c2 row); contested skierg to review
    assert [c["kind"] for c in auto].count("pair") == 1
    assert [c["kind"] for c in auto].count("single_source") == 3
    assert len([c for c in ambiguous if c["kind"] == "pair"]) == 2  # both contested pairings
    pair = next(c for c in auto if c["kind"] == "pair")
    assert pair["confidence"] >= 0.9
    # precision guard: the auto-merged pair is the true one (bikeerg photo -> cycling workout)
    assert pair["machine"] == "concept2-bikeerg"
    assert pair["workout"]["workout_type"] == "HKWorkoutActivityTypeCycling"

    # 4. apply merges
    for case in auto:
        fm, body = am.session_for_case(case)
        am.write_session(fm, body, sessions_dir)
    files = sorted(p.name for p in sessions_dir.rglob("*.md"))
    assert files == ["2026-08-04-rowerg.md", "2026-08-05-bikeerg.md",
                     "2026-08-07-run.md", "2026-08-08-bike.md"]

    # merged session: monitor wins output, Health wins HR (spec §5)
    from lib import frontmatter
    merged, _ = frontmatter.load(sessions_dir / "2026" / "2026-08-05-bikeerg.md")
    assert merged["watts_avg"] == 185 and merged["distance_m"] == 14100
    assert merged["hr_avg"] == 128 and merged["hr_max"] == 136  # mean/max of fixture series
    assert {s["kind"] for s in merged["sources"]} == {"health", "photo"}

    # 5. metrics with a configured LTHR
    test_config = dict(config, athlete={"lthr": 150, "hr_max": None})
    for path in sessions_dir.rglob("*.md"):
        cm.compute_for_session(path, test_config, workouts_dir)
    merged, _ = frontmatter.load(sessions_dir / "2026" / "2026-08-05-bikeerg.md")
    assert merged["computed"]["zones_source"] == "lthr"
    assert sum(merged["computed"]["time_in_zone"].values()) > 0
    assert merged["computed"]["efficiency_factor"] == round(185 / 128, 2)

    # 6. index build, strict
    count, errors = bi.build(sessions_dir, tmp_path / "index.jsonl", strict=True)
    assert count == 4 and errors == []
    lines = [json.loads(l) for l in (tmp_path / "index.jsonl").read_text().splitlines()]
    assert [l["date"] for l in lines] == sorted(l["date"] for l in lines)

    # 7. idempotency: re-proposing with claimed evidence yields nothing new
    claimed = pm.already_claimed(sessions_dir)
    again = pm.propose(workouts, pm.load_sidecars(sc_dir), claimed, config["matching"])
    assert again["auto_merge"] == []
