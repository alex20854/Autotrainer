import json

import yaml

import apply_merges as am
import build_index as bi
from lib import frontmatter


def _session_fm(sid, date, start, modality="bikeerg"):
    return {
        "id": sid, "date": date, "start": start, "end": None, "modality": modality,
        "machine": None, "duration_s": 1800, "hr_avg": 130, "hr_max": 145,
        "watts_avg": 180, "distance_m": 14000, "kcal": 300,
        "sources": [{"kind": "health", "ref": "data/derived/workouts/x.json",
                     "confidence": "high"}],
        "match_confidence": 1.0, "match_method": "auto", "prescription_id": None,
        "compliance": {"tier": 1, "score": 0.9, "components": {}},
        "computed": {"time_in_zone": {"z2": 1500}, "decoupling_pct": 3.0,
                     "efficiency_factor": 1.38},
    }


def test_build_index(tmp_path):
    sessions = tmp_path / "sessions"
    frontmatter.save(sessions / "2026" / "2026-08-05-bikeerg.md",
                     _session_fm("2026-08-05-bikeerg", "2026-08-05", "2026-08-05T06:00:00-04:00"))
    frontmatter.save(sessions / "2026" / "2026-08-04-rowerg.md",
                     _session_fm("2026-08-04-rowerg", "2026-08-04", "2026-08-04T06:00:00-04:00",
                                 modality="rowerg"))
    index_path = tmp_path / "index.jsonl"
    count, errors = bi.build(sessions, index_path, strict=True)
    assert count == 2 and errors == []
    lines = [json.loads(l) for l in index_path.read_text().splitlines()]
    assert [l["id"] for l in lines] == ["2026-08-04-rowerg", "2026-08-05-bikeerg"]  # date order
    assert lines[1]["tiz_z2_s"] == 1500
    assert lines[1]["compliance_score"] == 0.9
    assert lines[1]["source_kinds"] == ["health"]


def test_build_index_strict_catches_violations(tmp_path):
    sessions = tmp_path / "sessions"
    bad = _session_fm("wrong-id", "2026-08-05", "2026-08-05T06:00:00-04:00")
    bad["modality"] = "rollerblade"
    bad["match_confidence"] = 3
    frontmatter.save(sessions / "2026" / "2026-08-05-bikeerg.md", bad)
    _, errors = bi.build(sessions, tmp_path / "index.jsonl", strict=True)
    joined = "\n".join(errors)
    assert "!= filename stem" in joined
    assert "unknown modality" in joined
    assert "outside [0,1]" in joined


def test_apply_merges_pair(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "REPO_ROOT", tmp_path)
    # sidecar + derived record on disk, as after prep + vision extraction
    sidecar_path = tmp_path / "sc" / "p1.yaml"
    sidecar_path.parent.mkdir()
    sidecar_path.write_text(yaml.safe_dump({
        "photo": "data/raw/photos/p1.jpeg", "exif_time": "2026-08-05T06:33:00",
        "extracted": True, "machine": "concept2-bikeerg", "machine_confidence": "high",
        "fields": {"elapsed_time_s": {"value": 1800}, "watts_avg": {"value": 185},
                   "distance_m": {"value": 14100}, "kcal": {"value": 320}},
    }))
    rec_dir = tmp_path / "data" / "derived" / "workouts"
    rec_dir.mkdir(parents=True)
    (rec_dir / "health-a.json").write_text(json.dumps(
        {"hr": {"avg": 130, "max": 144, "series": []}}))

    case = {
        "kind": "pair",
        "workout": {"record_id": "health-a", "workout_type": "HKWorkoutActivityTypeCycling",
                    "start": "2026-08-05T06:00:00-04:00", "end": "2026-08-05T06:30:30-04:00",
                    "duration_s": 1830, "kcal": 310, "distance_m": 14200, "hr_avg": 130,
                    "ref": "data/derived/workouts/health-a.json"},
        "sidecar": "sc/p1.yaml",
        "machine": "concept2-bikeerg",
        "confidence": 1.0,
        "evidence": [],
    }
    fm, body = am.session_for_case(case)
    # monitor wins output/distance; Health wins HR
    assert fm["modality"] == "bikeerg"
    assert fm["duration_s"] == 1800 and fm["watts_avg"] == 185
    assert fm["distance_m"] == 14100 and fm["kcal"] == 320
    assert fm["hr_avg"] == 130 and fm["hr_max"] == 144
    assert {s["kind"] for s in fm["sources"]} == {"health", "photo"}

    path = am.write_session(fm, body, tmp_path / "sessions")
    assert path.name == "2026-08-05-bikeerg.md"
    # re-applying the same proposal overwrites in place, no duplicate file
    path2 = am.write_session(fm, body, tmp_path / "sessions")
    assert path2 == path
    # a different same-day same-modality session gets a -2 suffix
    fm2 = dict(fm, start="2026-08-05T18:00:00-04:00")
    path3 = am.write_session(fm2, body, tmp_path / "sessions")
    assert path3.name == "2026-08-05-bikeerg-2.md"
