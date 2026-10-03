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


EMPTY = {"auto_merge": [], "ambiguous": [], "baseline_routed": [], "too_short": []}


def test_claimed_evidence_is_skipped():
    claimed = {"data/derived/workouts/health-a.json", "p1.yaml"}
    result = pm.propose([W1], [P1], claimed, MATCHING)
    assert result == EMPTY


def test_strength_workouts_excluded():
    w = workout("health-e", "HKWorkoutActivityTypeTraditionalStrengthTraining",
                "2026-08-05T17:00:00-04:00", "2026-08-05T17:45:00-04:00", 2700)
    result = pm.propose([w], [], set(), MATCHING)
    assert result == EMPTY


def test_unextracted_photo_not_proposed():
    pending = dict(P1, extracted=False)
    result = pm.propose([], [pending], set(), MATCHING)
    assert result == EMPTY


def test_ignored_records_never_proposed():
    matching = dict(MATCHING, ignore_records=["health-a"])
    result = pm.propose([W1], [], set(), matching)
    assert result == EMPTY


CLASSIFICATION = {"baseline_types": ["Outdoor Walk", "Walking"],
                  "promote_min_duration_s": 1800}


def test_short_walk_routes_to_baseline():
    stroll = workout("health-w1", "Outdoor Walk",
                     "2026-08-05T12:00:00-04:00", "2026-08-05T12:22:00-04:00", 1320)
    result = pm.propose([stroll], [], set(), MATCHING, None, CLASSIFICATION)
    assert result["auto_merge"] == [] and result["ambiguous"] == []
    assert result["baseline_routed"] == ["health-w1"]


def test_long_walk_promotes_to_session():
    hike = workout("health-w2", "Outdoor Walk",
                   "2026-08-05T12:00:00-04:00", "2026-08-05T12:50:00-04:00", 3000)
    result = pm.propose([hike], [], set(), MATCHING, None, CLASSIFICATION)
    assert result["baseline_routed"] == []
    assert result["auto_merge"][0]["kind"] == "single_source"


def test_short_walk_with_photo_promotes():
    # a monitor photo pairing marks even a short walk as deliberate training
    stroll = workout("health-w3", "Walking",
                     "2026-08-05T12:00:00-04:00", "2026-08-05T12:22:00-04:00", 1320)
    photo = sidecar("pw.yaml", "treadmill", "2026-08-05T12:23:00", elapsed=1300)
    result = pm.propose([stroll], [photo], set(), MATCHING, None, CLASSIFICATION)
    assert result["baseline_routed"] == []
    all_cases = result["auto_merge"] + result["ambiguous"]
    assert any(c["kind"] == "pair" for c in all_cases)


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


REF1 = "data/derived/workouts/health-a.json"


def test_late_photo_upgrades_health_only_session():
    # W1 already became a Health-only session; its photo arrives on a later ingest
    result = pm.propose([W1], [P1], {REF1}, MATCHING, upgradable={REF1})
    kinds = [c["kind"] for c in result["auto_merge"]]
    assert kinds == ["pair"] and result["auto_merge"][0]["upgrades_session"] is True
    assert result["ambiguous"] == []


def test_upgradable_record_without_photo_is_not_reproposed():
    session = {"id": "2026-08-05-bike", "start": W1["start"], "end": W1["end"], "modality": "bike"}
    result = pm.propose([W1], [], {REF1}, MATCHING, sessions=[session], upgradable={REF1})
    assert result["auto_merge"] == [] and result["ambiguous"] == []


def test_judged_session_record_stays_claimed():
    result = pm.propose([W1], [P1], {REF1}, MATCHING, upgradable=set())
    assert [c["kind"] for c in result["ambiguous"]] == ["orphan_photo"]


def test_sub_two_minute_record_is_set_aside_not_proposed():
    blip = workout("health-blip", "HKWorkoutActivityTypeCycling",
                   "2026-09-06T17:02:49-04:00", "2026-09-06T17:04:17-04:00", 88)
    result = pm.propose([blip, W1], [P1], set(), MATCHING)
    assert [c["record_id"] for c in result["too_short"]] == ["health-blip"]
    assert all(c["workout"]["record_id"] != "health-blip" for c in result["auto_merge"] + result["ambiguous"])
    assert [c["kind"] for c in result["auto_merge"]] == ["pair"]   # W1 unaffected


def test_min_session_is_configurable():
    short = workout("health-s", "HKWorkoutActivityTypeRunning",
                    "2026-08-07T07:00:00-04:00", "2026-08-07T07:04:00-04:00", 240)
    assert pm.propose([short], [], set(), MATCHING, classification={"min_session_s": 300})["too_short"]
    assert not pm.propose([short], [], set(), MATCHING, classification={"min_session_s": 120})["too_short"]


def test_travel_photo_matches_on_the_absolute_instant():
    # synthetic: the Watch records in the home offset (-05:00); the photo carries the
    # offset where it was taken (-08:00), six seconds after the workout ended
    w = workout("health-travel", "Elliptical", "2026-03-02T11:20:00-05:00", "2026-03-02T11:48:30-05:00", 1710)
    aware = sidecar("travel.yaml", "elliptical", "2026-03-02T08:48:36-08:00", elapsed=1700)
    conf, notes = pm.score_pair(w, aware, MATCHING)
    assert conf >= 0.9 and any("6s after workout end" in n for n in notes), notes
    # the same clock reading without its offset is read as home time: three hours early, no match
    naive = sidecar("travel-naive.yaml", "elliptical", "2026-03-02T08:48:36", elapsed=1700)
    assert pm.score_pair(w, naive, MATCHING)[0] == 0.0


def test_aware_photo_pairs_with_offsetless_c2_record_without_crashing():
    # C2 CSV records carry no UTC offset; every iPhone photo now does
    c2 = workout("c2-row", "c2-bikeerg", "2026-07-29T18:10:36", "2026-07-29T18:35:36", 1500)
    photo = sidecar("c2photo.yaml", "concept2-bikeerg", "2026-07-29T18:36:00-04:00", elapsed=1500)
    # no TypeError; with the console's C2 type listed in modality_map it auto-merges
    matching = {**MATCHING, "modality_map": {**MATCHING["modality_map"],
                "concept2-bikeerg": [*MATCHING["modality_map"]["concept2-bikeerg"], "c2-bikeerg"]}}
    assert pm.score_pair(c2, photo, matching)[0] >= 0.9
    result = pm.propose([c2], [photo], set(), matching)
    assert [c["kind"] for c in result["auto_merge"]] == ["pair"]
    # without it the pair is still scored, just held for review as "modality unusual"
    held = pm.propose([c2], [photo], set(), MATCHING)["ambiguous"]
    assert [c["kind"] for c in held] == ["pair"] and held[0]["confidence"] == 0.75


def test_datetime_exif_time_is_normalized_and_serializable():
    import json
    from datetime import datetime
    # what yaml.safe_load returns for an unquoted ISO timestamp in a hand-edited sidecar
    sc = dict(P1, exif_time=datetime.fromisoformat("2026-08-05T06:33:00-04:00"))
    assert pm.score_pair(W1, sc, MATCHING)[0] >= 0.9
    orphan = pm.propose([], [sc], set(), MATCHING)
    json.dumps(orphan)   # the orphan_photo case must not carry a datetime through
