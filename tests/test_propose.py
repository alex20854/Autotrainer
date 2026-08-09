import propose_matches as pm

MATCHING = {
    "photo_window_after_end_s": 600,
    "duration_tolerance_s": 90,
    "modality_map": {
        "concept2-bikeerg": ["HKWorkoutActivityTypeCycling", "HKWorkoutActivityTypeOther"],
        "concept2-skierg": ["HKWorkoutActivityTypeRowing", "HKWorkoutActivityTypeOther"],
    },
}


def workout(rid, wtype, start, end, duration_s):
    return {"record_id": rid, "source_kind": rid.split("-")[0],
            "workout_type": wtype, "start": start, "end": end,
            "duration_s": duration_s, "kcal": 300, "distance_m": None, "hr": {"avg": 130}}


def sidecar(path, machine, exif, elapsed=None):
    fields = {"elapsed_time_s": {"value": elapsed, "confidence": "high"}} if elapsed else {}
    return {"_sidecar_path": path, "photo": path.replace(".yaml", ".jpeg"),
            "extracted": True, "machine": machine, "exif_time": exif, "fields": fields}


W1 = workout("health-a", "HKWorkoutActivityTypeCycling",
             "2026-08-05T06:00:00-04:00", "2026-08-05T06:30:30-04:00", 1830)
P1 = sidecar("p1.yaml", "concept2-bikeerg", "2026-08-05T06:33:00", elapsed=1800)


def test_clean_pair_auto_merges():
    result = pm.propose([W1], [P1], set(), MATCHING)
    assert len(result["auto_merge"]) == 1
    case = result["auto_merge"][0]
    assert case["kind"] == "pair" and case["confidence"] >= 0.9
    assert result["ambiguous"] == []


def test_contested_evidence_goes_to_claude():
    w2 = workout("health-b", "HKWorkoutActivityTypeRowing",
                 "2026-08-06T06:10:00-04:00", "2026-08-06T06:36:00-04:00", 1560)
    w3 = workout("health-c", "HKWorkoutActivityTypeOther",
                 "2026-08-06T06:40:00-04:00", "2026-08-06T07:06:00-04:00", 1560)
    p2 = sidecar("p2.yaml", "concept2-skierg", "2026-08-06T06:42:00", elapsed=1500)
    result = pm.propose([w2, w3], [p2], set(), MATCHING)
    # photo fits both windows -> nothing auto-merges as a pair
    assert all(c["kind"] != "pair" for c in result["auto_merge"])
    contested = [c for c in result["ambiguous"] if c["kind"] == "pair"]
    assert contested and "contested" in contested[0]["reason"]


def test_unmatched_workout_is_single_source():
    w4 = workout("health-d", "HKWorkoutActivityTypeRunning",
                 "2026-08-07T07:00:00-04:00", "2026-08-07T07:40:00-04:00", 2400)
    result = pm.propose([w4], [], set(), MATCHING)
    assert result["auto_merge"][0]["kind"] == "single_source"


def test_orphan_photo_is_ambiguous():
    result = pm.propose([], [P1], set(), MATCHING)
    assert result["ambiguous"][0]["kind"] == "orphan_photo"


def test_duration_mismatch_blocks_auto_merge():
    p_bad = sidecar("p3.yaml", "concept2-bikeerg", "2026-08-05T06:33:00", elapsed=1200)
    result = pm.propose([W1], [p_bad], set(), MATCHING)
    assert all(c["kind"] != "pair" for c in result["auto_merge"])


def test_modality_mismatch_lowers_but_never_hard_fails():
    p_odd = sidecar("p4.yaml", "concept2-skierg", "2026-08-05T06:33:00", elapsed=1800)
    conf, notes = pm.score_pair(W1, p_odd, MATCHING)
    assert 0 < conf < 0.9
    assert any("modality unusual" in n for n in notes)


def test_claimed_evidence_is_skipped():
    claimed = {"data/derived/workouts/health-a.json", "p1.yaml"}
    result = pm.propose([W1], [P1], claimed, MATCHING)
    assert result == {"auto_merge": [], "ambiguous": []}


def test_strength_workouts_excluded():
    w = workout("health-e", "HKWorkoutActivityTypeTraditionalStrengthTraining",
                "2026-08-05T17:00:00-04:00", "2026-08-05T17:45:00-04:00", 2700)
    result = pm.propose([w], [], set(), MATCHING)
    assert result == {"auto_merge": [], "ambiguous": []}


def test_unextracted_photo_not_proposed():
    pending = dict(P1, extracted=False)
    result = pm.propose([], [pending], set(), MATCHING)
    assert result == {"auto_merge": [], "ambiguous": []}


def test_late_arriving_record_attaches_to_existing_session():
    # photo-only session already exists; the Health export arrives later and
    # overlaps it -> attach case for Claude, never a duplicate single_source
    sessions = [{"id": "2026-08-05-bikeerg", "start": "2026-08-05T06:01:00-04:00",
                 "end": "2026-08-05T06:31:00-04:00", "modality": "bikeerg"}]
    result = pm.propose([W1], [], set(), MATCHING, sessions)
    assert result["auto_merge"] == []
    case = result["ambiguous"][0]
    assert case["kind"] == "attach_to_session"
    assert case["session_id"] == "2026-08-05-bikeerg"


def test_non_overlapping_session_does_not_block_single_source():
    sessions = [{"id": "2026-08-04-rowerg", "start": "2026-08-04T06:00:00-04:00",
                 "end": "2026-08-04T06:30:00-04:00", "modality": "rowerg"}]
    result = pm.propose([W1], [], set(), MATCHING, sessions)
    assert result["auto_merge"][0]["kind"] == "single_source"


def test_duplicate_health_captures_collapse_to_one_session():
    # same ride in export.xml and Auto Export: different type spellings,
    # timestamps seconds apart — must become ONE session, richest record primary
    thin = workout("health-a1", "HKWorkoutActivityTypeCycling",
                   "2026-08-05T06:00:00-04:00", "2026-08-05T06:30:30-04:00", 1830)
    rich = workout("health-a2", "Indoor Cycling",
                   "2026-08-05T06:00:12-04:00", "2026-08-05T06:31:00-04:00", 1848)
    rich["hr"] = {"avg": 131, "max": 146, "series": [[i * 60, 130] for i in range(30)]}
    result = pm.propose([thin, rich], [], set(), MATCHING)
    assert len(result["auto_merge"]) == 1 and result["ambiguous"] == []
    w = result["auto_merge"][0]["workout"]
    assert w["record_id"] == "health-a2"  # HR series wins primacy
    assert w["co_refs"] == [{"kind": "health", "role": "duplicate",
                             "ref": "data/derived/workouts/health-a1.json"}]


def test_c2_and_health_records_merge_as_complements():
    c2 = workout("c2-b1", "c2-rowerg",
                 "2026-08-04T06:05:00-04:00", "2026-08-04T06:35:00-04:00", 1800)
    c2["hr"] = None
    health = workout("health-b2", "HKWorkoutActivityTypeRowing",
                     "2026-08-04T06:04:30-04:00", "2026-08-04T06:36:00-04:00", 1890)
    health["hr"] = {"avg": 128, "max": 141, "series": [[i * 60, 128] for i in range(31)]}
    result = pm.propose([c2, health], [], set(), MATCHING)
    assert len(result["auto_merge"]) == 1
    w = result["auto_merge"][0]["workout"]
    assert w["record_id"] == "c2-b1"          # machine record is primary
    assert w["duration_s"] == 1800            # machine wins duration
    assert w["start"] == "2026-08-04T06:04:30-04:00"  # Health anchors timing
    assert w["hr_avg"] == 128                 # Health wins HR
    assert w["co_refs"][0]["role"] == "complement"


def test_back_to_back_workouts_do_not_collapse():
    first = workout("health-c1", "HKWorkoutActivityTypeRowing",
                    "2026-08-06T06:00:00-04:00", "2026-08-06T06:25:00-04:00", 1500)
    second = workout("health-c2", "HKWorkoutActivityTypeCycling",
                     "2026-08-06T06:26:00-04:00", "2026-08-06T06:50:00-04:00", 1440)
    result = pm.propose([first, second], [], set(), MATCHING)
    assert len(result["auto_merge"]) == 2
