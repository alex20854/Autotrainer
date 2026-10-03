import json

import apply_merges as am
import relabel_sessions as rl
from lib import frontmatter


def _record(root, rid, wtype):
    d = root / "data" / "derived" / "workouts"; d.mkdir(parents=True, exist_ok=True)
    (d / f"{rid}.json").write_text(json.dumps({"record_id": rid, "workout_type": wtype,
                                               "start": "2026-08-26T09:36:00-04:00", "end": "2026-08-26T09:51:00-04:00"}))
    return f"data/derived/workouts/{rid}.json"


def _session(sessions, start, modality, ref, **over):
    fm = {"id": None, "date": start[:10], "start": start, "end": start[:11] + "09:51:00-04:00",
          "modality": modality, "machine": None, "duration_s": 900, "hr_avg": 140, "hr_max": 150,
          "watts_avg": None, "distance_m": None, "kcal": 120,
          "sources": [{"kind": "health", "ref": ref, "confidence": "high"}],
          "match_confidence": 1.0, "match_method": "auto", "prescription_id": None,
          "compliance": None, "computed": {"decoupling_pct": 4.2}}
    fm.update(over)
    return am.write_session(fm, "_Single-source session._\n", sessions)


def test_relabel_moves_unjudged_sessions_to_the_new_label(tmp_path):
    sessions = tmp_path / "data" / "sessions"
    ref = _record(tmp_path, "health-e", "Elliptical")
    old = _session(sessions, "2026-08-26T09:36:00-04:00", "mixed", ref)
    assert old.name == "2026-08-26-mixed.md"
    changes, undecided = rl.plan(sessions, tmp_path)
    assert [(p.stem, new) for p, _, _, new in changes] == [("2026-08-26-mixed", "elliptical")] and undecided == []
    rl.run(sessions, tmp_path, dry_run=True)
    assert old.exists()                                   # dry run changes nothing
    rl.run(sessions, tmp_path, dry_run=False)
    new = sessions / "2026" / "2026-08-26-elliptical.md"
    assert new.exists() and not old.exists()
    fm, _ = frontmatter.load(new)
    assert fm["id"] == "2026-08-26-elliptical" and fm["modality"] == "elliptical"
    assert fm["computed"] == {"decoupling_pct": 4.2}      # metrics survive the rename
    assert rl.plan(sessions, tmp_path) == ([], [])        # idempotent


def test_relabel_leaves_judged_and_already_correct_sessions_alone(tmp_path):
    sessions = tmp_path / "data" / "sessions"
    ref_e = _record(tmp_path, "health-e", "Elliptical")
    ref_c = _record(tmp_path, "health-c", "HKWorkoutActivityTypeCrossTraining")
    judged = _session(sessions, "2026-08-26T09:36:00-04:00", "mixed", ref_e, compliance={"score": 0.8})
    _session(sessions, "2026-08-27T09:36:00-04:00", "mixed", ref_c)    # genuinely mixed
    assert rl.plan(sessions, tmp_path) == ([], [])
    rl.run(sessions, tmp_path, dry_run=False)
    assert judged.exists()


def test_relabel_never_touches_a_hand_set_specific_label(tmp_path):
    # a Health-only ride labelled bikeerg with no photo: someone decided that; the
    # type map alone would say "bike" — relabel must not undo the decision
    sessions = tmp_path / "data" / "sessions"
    ref = _record(tmp_path, "health-r", "Indoor Cycling")
    ride = _session(sessions, "2026-08-10T21:01:00-04:00", "bikeerg", ref)
    assert rl.plan(sessions, tmp_path) == ([], [])
    rl.run(sessions, tmp_path, dry_run=False)
    assert ride.exists()


def test_relabel_refuses_types_the_athlete_uses_for_different_machines(tmp_path):
    # this athlete logs AirDyne rides as the Watch's "Elliptical": the type alone can't name the machine
    sessions = tmp_path / "data" / "sessions"
    ref = _record(tmp_path, "health-e", "Elliptical")
    old = _session(sessions, "2026-08-26T09:36:00-04:00", "mixed", ref)
    both = {"airdyne": ["Elliptical", "Other"], "elliptical": ["Elliptical"]}
    assert rl.ambiguous_types(both) == {"Elliptical": {"airdyne", "elliptical"}}
    changes, undecided = rl.plan(sessions, tmp_path, both)
    assert changes == [] and [(p.stem, t) for p, t, _ in undecided] == [("2026-08-26-mixed", "Elliptical")]
    rl.run(sessions, tmp_path, dry_run=False, modality_map=both)
    assert old.exists()
    only = {"elliptical": ["Elliptical"], "airdyne": ["Other"]}      # unambiguous map -> relabel proceeds
    assert [new for *_, new in rl.plan(sessions, tmp_path, only)[0]] == ["elliptical"]
