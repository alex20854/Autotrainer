"""status.py / lib.facts — the read-only facts layer, on tiny synthetic workspaces."""

import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

import status
from lib import facts

from conftest import TEMPLATE_WORKSPACE

MACHINES = {"concept2-rowerg": "rowerg", "concept2-bikeerg": "bikeerg", "treadmill": "treadmill-run"}


# --- workspace builders ----------------------------------------------------------

def make_ws(tmp_path: Path, config: dict | None = None) -> Path:
    ws = tmp_path / "ws"
    (ws / "config").mkdir(parents=True)
    (ws / "config" / "athlete.yaml").write_text(yaml.safe_dump(config or {}), encoding="utf-8")
    return ws


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def session(day: str, modality: str = "bikeerg", duration_s: int = 1800, start: str = "07:00") -> dict:
    return {"id": f"{day}-{modality}", "date": day, "start": f"{day}T{start}:00-04:00",
            "modality": modality, "duration_s": duration_s}


def metric(day: str, name: str, value: float) -> dict:
    return {"date": day, "name": name, "value": value, "units": "x"}


def days(start: str, n: int, step: int = 1) -> list[str]:
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i * step)).isoformat() for i in range(n)]


def run(data: dict, as_of=None) -> dict:
    return facts.collect(data, as_of=as_of, machine_to_modality=MACHINES)


def cli(ws: Path, monkeypatch, capsys, *argv: str) -> str:
    monkeypatch.setenv("AUTOTRAINER_WORKSPACE", str(ws))
    assert status.main(list(argv)) == 0
    return capsys.readouterr().out


# --- reference date ----------------------------------------------------------------

def test_as_of_is_newest_data_date_and_override_wins():
    data = {"index": [session("2026-09-01")],
            "baseline": [{"week": "2026-W37", "minutes": 30}],          # Monday 2026-09-07
            "metrics": [metric("2026-09-05", "resting_heart_rate", 55)]}
    assert run(data)["as_of"] == "2026-09-07"
    data["metrics"].append(metric("2026-09-10", "vo2_max", 40))
    assert run(data)["as_of"] == "2026-09-10"
    f = run(data, as_of="2026-09-02")
    assert f["as_of"] == "2026-09-02"
    assert f["sessions"]["days_since_last"] == 1
    assert f["recovery"]["vo2_max"]["latest"] is None                   # dated after as_of
    assert f["weeks"][-1]["week"] == "2026-W36"


def test_cli_as_of_flag(tmp_path, monkeypatch, capsys):
    ws = make_ws(tmp_path)
    write_jsonl(ws / "data" / "index.jsonl", [session("2026-09-01"), session("2026-09-20")])
    assert json.loads(cli(ws, monkeypatch, capsys, "--json"))["as_of"] == "2026-09-20"
    out = json.loads(cli(ws, monkeypatch, capsys, "--json", "--as-of", "2026-09-05"))
    assert out["as_of"] == "2026-09-05"
    assert out["sessions"]["total"] == 1


# --- weeks and consistency ----------------------------------------------------------

def test_gap_zero_fills_weeks_and_resets_streak():
    # W31 and W32: 3 structured each; W33-W34 empty; W35: 3 structured
    rows = [session(d) for d in ("2026-07-27", "2026-07-28", "2026-07-29",
                                 "2026-08-03", "2026-08-04", "2026-08-05",
                                 "2026-08-24", "2026-08-25", "2026-08-26")]
    f = run({"index": rows})
    assert [w["week"] for w in f["weeks"]] == ["2026-W31", "2026-W32", "2026-W33",
                                               "2026-W34", "2026-W35"]
    assert [w["structured_sessions"] for w in f["weeks"]] == [3, 3, 0, 0, 3]
    assert f["weeks"][2] == {"week": "2026-W33", "sessions": 0, "structured_sessions": 0,
                             "structured_min": 0, "baseline_min": 0, "by_modality_min": {}}
    c = f["consistency"]
    assert (c["weeks_meeting"], c["weeks_total"]) == (3, 5)
    assert (c["current_streak_weeks"], c["longest_streak_weeks"]) == (1, 2)


def test_in_progress_week_below_threshold_is_skipped_by_current_streak():
    rows = [session(d) for d in ("2026-08-03", "2026-08-04", "2026-08-05",
                                 "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-17")]
    c = run({"index": rows})["consistency"]
    assert c["current_streak_weeks"] == 2      # W34 (1 session so far) skipped
    rows.append(session("2026-08-24"))         # W35 also short: W34 no longer the as_of week
    assert run({"index": rows})["consistency"]["current_streak_weeks"] == 0


def test_weeks_start_at_first_session_not_at_old_baseline_history():
    # a full Health export can put years of walks in baseline.jsonl before training
    rows = [session(d) for d in ("2026-09-07", "2026-09-08", "2026-09-09",
                                 "2026-09-14", "2026-09-15", "2026-09-16")]
    baseline = [{"week": "2024-W02", "minutes": 300}, {"week": "2026-W36", "minutes": 80},
                {"week": "2026-W38", "minutes": 90}]
    f = run({"index": rows, "baseline": baseline}, as_of="2026-09-20")
    assert [w["week"] for w in f["weeks"]] == ["2026-W37", "2026-W38"]
    assert [w["baseline_min"] for w in f["weeks"]] == [0, 90]
    c = f["consistency"]
    assert (c["weeks_meeting"], c["weeks_total"], c["current_streak_weeks"]) == (2, 2, 2)
    # baseline only: the as_of week alone, and no consistency weeks
    f = run({"baseline": baseline})
    assert f["as_of"] == "2026-09-14"
    assert [(w["week"], w["baseline_min"]) for w in f["weeks"]] == [("2026-W38", 90)]
    assert (f["consistency"]["weeks_total"], f["consistency"]["weeks_meeting"]) == (0, 0)


def test_status_overrides_of_the_wrong_type_fall_back_to_defaults():
    rows = [session("2026-09-21", "walk"), session("2026-09-22", "walk"),
            session("2026-09-23", "walk"), session("2026-09-24", "rowerg")]
    # a bare string is a one-item list, not a set of characters
    f = run({"index": rows, "config": {"status": {"unstructured_modalities": "walk"}}})
    assert f["weeks"][-1]["structured_sessions"] == 1
    bad = {"status": {"unstructured_modalities": ["walk", 3], "consistency_sessions": "3",
                      "benchmark_cadence_days": "42", "resting_hr_elevated_bpm": True}}
    assert facts.thresholds(bad) == facts.DEFAULTS
    f = run({"index": rows, "config": bad})
    assert f["weeks"][-1]["structured_sessions"] == 1
    assert f["consistency"]["threshold_sessions"] == 3
    assert f["benchmarks"]["cadence_days"] == 42
    assert f["recovery"]["resting_hr"]["elevated_threshold_bpm"] == 5
    ok = {"status": {"consistency_sessions": 2, "resting_hr_elevated_bpm": 4.5}}
    assert facts.thresholds(ok)["consistency_sessions"] == 2
    assert facts.thresholds(ok)["resting_hr_elevated_bpm"] == 4.5
    facts.thresholds({"status": {"unstructured_modalities": ["walk"]}})["unstructured_modalities"].append("x")
    assert facts.DEFAULTS["unstructured_modalities"] == ["walk", "treadmill-walk"]


def test_iso_weeks_across_year_boundary():
    # 2026 has 53 ISO weeks; 2027-01-01 (Fri) is still 2026-W53
    rows = [session("2026-12-21"), session("2027-01-01"), session("2027-01-04")]
    f = run({"index": rows})
    assert [w["week"] for w in f["weeks"]] == ["2026-W52", "2026-W53", "2027-W01"]
    assert [w["sessions"] for w in f["weeks"]] == [1, 1, 1]
    assert f["plan"]["current_week"] == "2027-W01"


def test_structured_vs_unstructured_split():
    rows = [session("2026-09-14", "rowerg", 2400), session("2026-09-15", "walk", 3600),
            session("2026-09-16", "treadmill-walk", 1200), session("2026-09-16", "bikeerg", 1800, "18:00")]
    baseline = [{"week": "2026-W38", "minutes": 95}]
    f = run({"index": rows, "baseline": baseline})
    w = f["weeks"][-1]
    assert (w["sessions"], w["structured_sessions"], w["structured_min"]) == (4, 2, 70)
    assert w["baseline_min"] == 95
    assert w["by_modality_min"] == {"bikeerg": 30, "rowerg": 40, "treadmill-walk": 20, "walk": 60}
    assert f["sessions"]["last"] == {"date": "2026-09-16", "modality": "bikeerg"}
    rows.append(session("2026-09-18", "walk"))
    s = run({"index": rows})["sessions"]
    assert s["last"]["modality"] == "walk" and s["days_since_last"] == 0
    assert s["last_structured"] == {"date": "2026-09-16", "modality": "bikeerg"}
    assert s["days_since_last_structured"] == 2
    # the unstructured list is configurable
    cfg = {"status": {"unstructured_modalities": ["walk", "treadmill-walk", "bikeerg"],
                      "consistency_sessions": 1}}
    f = run({"index": rows, "config": cfg})
    assert f["weeks"][-1]["structured_sessions"] == 1
    assert f["consistency"]["threshold_sessions"] == 1


# --- benchmarks --------------------------------------------------------------------

@pytest.mark.parametrize("dash", ["-", "–", "—"])
def test_benchmark_heading_dash_variants(dash):
    md = (f"# Benchmarks\n\n## Results\n\n### 2026-08-14 {dash} 2k row (concept2-rowerg)\n- Result: x\n\n"
          f"### 2026-07-01 {dash} LTHR test\n\n```\n### 2026-09-30 {dash} <test> in a fence\n```\n")
    f = run({"benchmarks_md": md, "index": [session("2026-09-25")]})["benchmarks"]
    assert f["count"] == 2
    assert f["latest"] == {"date": "2026-08-14", "title": "2k row (concept2-rowerg)"}
    assert f["age_days"] == 42 and f["cadence_days"] == 42
    assert f["past_cadence"] is False
    assert run({"benchmarks_md": md, "index": [session("2026-09-26")]})["benchmarks"]["past_cadence"] is True


def test_no_benchmarks_template_and_missing_file():
    template = (TEMPLATE_WORKSPACE / "benchmarks.md").read_text(encoding="utf-8")
    for md in (template, None):
        f = run({"benchmarks_md": md, "index": [session("2026-09-25")]})["benchmarks"]
        assert f == {"count": 0, "latest": None, "age_days": None,
                     "cadence_days": 42, "past_cadence": None}


# --- anchors, goal, plan ------------------------------------------------------------

def test_anchors_missing_for_equipment_with_null_power_slots():
    config = {"athlete": {"hr_max": 185, "lthr": None, "hr_resting": None},
              "power": {"bikeerg": {"ftp": 200, "z2_watts_ceiling": None},
                        "rowerg": {"ftp": None, "z2_watts_ceiling": None},
                        "skierg": {"ftp": None, "z2_watts_ceiling": None}},
              "equipment": ["concept2-rowerg", "concept2-bikeerg", "treadmill"]}
    a = run({"config": config})["anchors"]
    assert a["missing"] == ["lthr", "hr_resting", "power.bikeerg.z2_watts_ceiling",
                            "power.rowerg.ftp", "power.rowerg.z2_watts_ceiling"]
    assert a["hr_max"] == 185 and a["power"]["bikeerg"]["ftp"] == 200


def test_goal_inactive_for_template_active_when_track_filled():
    template = (TEMPLATE_WORKSPACE / "goals.md").read_text(encoding="utf-8")
    assert run({"goals_md": template})["goal"] == {"active": False, "track": None}
    assert run({"goals_md": None})["goal"] == {"active": False, "track": None}
    filled = ("# Goals\n\n## Active goal\n\n- Track: general-cv-health\n- Started: 2026-09-01\n\n"
              "## History\n\n- Track: hyrox\n")
    assert run({"goals_md": filled})["goal"] == {"active": True, "track": "general-cv-health"}
    blank = "# Goals\n\n## Active goal\n\n- Track:\n\n## History\n\n- Track: hyrox\n"
    assert run({"goals_md": blank})["goal"]["active"] is False


@pytest.mark.parametrize("md", [
    # the template's fenced block filled in place
    "## Active goal\n\nTemplate the coach fills in:\n\n```\n- Track: hyrox\n- Started: 2026-10-01\n```\n",
    "## Active goal\n\n- **Track**: hyrox\n",
    "## Active goal\n\n- **Track:** hyrox\n",
    "## Active goal: Hyrox spring race\n\n- Track: hyrox\n",
    "## Active goal\n\n* track: hyrox\n\n## History\n\n- Track: custom\n",
])
def test_goal_active_for_common_markdown_forms(md):
    assert goal_of(md) == {"active": True, "track": "hyrox"}


@pytest.mark.parametrize("md", [
    "## Active goal\n\n```\n- Track: general-cv-health | metabolic-health | hyrox | custom\n```\n",
    "## Active goal\n\n- Track: <track>\n",
    "## History\n\n```\n- Track: hyrox\n```\n",
    # a fenced heading does not open the section
    "## Notes\n\n```\n## Active goal\n- Track: hyrox\n```\n",
])
def test_goal_inactive_for_placeholders_and_other_sections(md):
    assert goal_of(md) == {"active": False, "track": None}


def goal_of(md: str) -> dict:
    return run({"goals_md": md})["goal"]


def test_plan_and_review_files(tmp_path):
    ws = make_ws(tmp_path)
    write_jsonl(ws / "data" / "index.jsonl", [session("2026-10-01")])          # 2026-W40
    f = facts.collect(facts.load(ws), machine_to_modality=MACHINES)
    assert f["plan"] == {"current_week": "2026-W40", "exists": False, "latest": None}
    assert f["review"] == {"latest": None}
    for d, name in (("plans", "2026-W38"), ("plans", "2026-W40"), ("reports", "2026-W39")):
        (ws / d).mkdir(exist_ok=True)
        (ws / d / f"{name}.md").write_text("x\n", encoding="utf-8")
    f = facts.collect(facts.load(ws), machine_to_modality=MACHINES)
    assert f["plan"] == {"current_week": "2026-W40", "exists": True, "latest": "2026-W40"}
    assert f["review"] == {"latest": "2026-W39"}
    (ws / "plans" / "2026-W40.md").unlink()
    f = facts.collect(facts.load(ws), machine_to_modality=MACHINES)
    assert f["plan"] == {"current_week": "2026-W40", "exists": False, "latest": "2026-W38"}


# --- recovery ----------------------------------------------------------------------

def test_recovery_medians_with_missing_days():
    # resting HR every other day, 2026-09-01 .. 09-27: 14 points, all within the
    # 28 days ending 2026-09-28
    rhr = [metric(d, "resting_heart_rate", 50 + i % 3) for i, d in enumerate(days("2026-09-01", 14, 2))]
    hrv = [metric(d, "heart_rate_variability", v) for d, v in
           (("2026-09-24", 40.0), ("2026-09-26", 50.0), ("2026-09-30", 45.5))]
    f = run({"metrics": rhr + hrv}, as_of="2026-09-28")
    r = f["recovery"]["resting_hr"]
    assert r["n_28d"] == 14 and r["n_7d"] == 3                # 09-23, 25, 27
    assert (r["median_28d"], r["median_7d"]) == (51.0, 51.0)
    assert r["latest"] == {"date": "2026-09-27", "value": 51.0}
    assert r["delta_vs_28d"] == 0.0
    # a point dated after as_of is excluded
    h = f["recovery"]["hrv"]
    assert h["latest"] == {"date": "2026-09-26", "value": 50.0}
    assert (h["n_7d"], h["median_7d"], h["delta_vs_28d"]) == (2, 45.0, 5.0)
    # without the override, as_of is the newest point
    assert run({"metrics": rhr + hrv})["as_of"] == "2026-09-30"


def test_recovery_with_fewer_than_seven_points_and_none():
    pts = [metric(d, "resting_heart_rate", v) for d, v in (("2026-09-10", 60), ("2026-09-12", 56))]
    r = run({"metrics": pts})["recovery"]
    assert r["resting_hr"]["n_7d"] == 2 and r["resting_hr"]["median_7d"] == 58.0
    assert r["resting_hr"]["median_28d"] == 58.0 and r["resting_hr"]["delta_vs_28d"] == -2.0
    assert r["hrv"] == {"latest": None, "median_7d": None, "median_28d": None,
                        "delta_vs_28d": None, "n_7d": 0, "n_28d": 0}
    assert r["vo2_max"] == {"latest": None}
    assert run({"index": [session("2026-09-12")]})["recovery"]["resting_hr"]["days_elevated"] is None


def test_brief_shows_unmeasured_days_elevated_as_na(tmp_path, monkeypatch, capsys):
    ws = make_ws(tmp_path)
    write_jsonl(ws / "data" / "index.jsonl", [session("2026-09-20")])
    write_jsonl(ws / "data" / "derived" / "metrics.jsonl", [metric("2026-08-01", "resting_heart_rate", 55)])
    out = cli(ws, monkeypatch, capsys)
    line = next(l for l in out.splitlines() if l.startswith("resting HR:"))
    assert line.endswith("days at or above +5: n/a (no 28-day median)")
    assert "0 days" not in line


def test_days_elevated_counts_consecutive_recent_points():
    base = [metric(d, "resting_heart_rate", 50) for d in days("2026-09-01", 20)]
    tail = [metric(d, "resting_heart_rate", v) for d, v in
            (("2026-09-21", 56), ("2026-09-22", 50), ("2026-09-23", 55), ("2026-09-25", 57))]
    r = run({"metrics": base + tail})["recovery"]["resting_hr"]
    assert r["median_28d"] == 50.0 and r["elevated_threshold_bpm"] == 5
    assert r["days_elevated"] == 2            # 09-25 and 09-23 (a missing day does not break it)
    cfg = {"status": {"resting_hr_elevated_bpm": 6}}
    r = run({"metrics": base + tail, "config": cfg})["recovery"]["resting_hr"]
    assert (r["elevated_threshold_bpm"], r["days_elevated"]) == (6, 1)


# --- pipeline ----------------------------------------------------------------------

def test_pipeline_counts_with_and_without_optional_files(tmp_path):
    ws = make_ws(tmp_path)
    f = facts.collect(facts.load(ws), machine_to_modality=MACHINES)
    assert f["pipeline"] == {"newest_workout_end": None, "photos_pending": 0,
                             "photos_inbox": 0, "ambiguous_cases": None}
    wdir = ws / "data" / "derived" / "workouts"
    wdir.mkdir(parents=True)
    # same wall time, different offsets: the -07:00 one is the later instant
    for name, end in (("a", "2026-09-29T10:00:00-04:00"), ("b", "2026-09-29T09:00:00-07:00"),
                      ("c", "2026-09-28T23:00:00-04:00")):
        (wdir / f"{name}.json").write_text(json.dumps({"end": end, "hr": {"series": []}}))
    (ws / "data" / "derived" / "photo_finder.json").write_text(
        json.dumps({"scanned_through": None, "promoted": ["u1"], "rejected": [], "pending": ["u2", "u3"]}))
    (ws / "data" / "derived" / "proposals.json").write_text(
        json.dumps({"auto_merge": [{}], "ambiguous": [{}, {}, {}]}))
    inbox = ws / "data" / "inbox" / "photos"
    inbox.mkdir(parents=True)
    for name in ("IMG_1.jpeg", "IMG_2.heic", ".DS_Store"):
        (inbox / name).write_bytes(b"x")
    f = facts.collect(facts.load(ws), machine_to_modality=MACHINES)
    assert f["pipeline"] == {"newest_workout_end": "2026-09-29T09:00:00-07:00",
                             "photos_pending": 2, "photos_inbox": 2, "ambiguous_cases": 3}


# --- CLI contract ------------------------------------------------------------------

def full_ws(tmp_path: Path) -> Path:
    config = {"athlete": {"hr_max": 180, "lthr": None, "hr_resting": 55},
              "power": {"rowerg": {"ftp": None, "z2_watts_ceiling": None}},
              "equipment": ["concept2-rowerg"]}
    ws = make_ws(tmp_path, config)
    write_jsonl(ws / "data" / "index.jsonl",
                [session(d, m) for d, m in (("2026-09-01", "rowerg"), ("2026-09-03", "walk"),
                                            ("2026-09-08", "rowerg"), ("2026-09-19", "bikeerg"),
                                            ("2026-09-28", "walk"))])
    write_jsonl(ws / "data" / "baseline.jsonl", [{"week": "2026-W40", "minutes": 52}])
    write_jsonl(ws / "data" / "derived" / "metrics.jsonl",
                [metric(d, "resting_heart_rate", 55 + i % 4) for i, d in enumerate(days("2026-09-05", 28))]
                + [metric("2026-09-29", "vo2_max", 41.5), metric("2026-10-02", "heart_rate_variability", 48.1)])
    (ws / "benchmarks.md").write_text("## Results\n\n### 2026-08-14 — 2k row\n", encoding="utf-8")
    (ws / "goals.md").write_text((TEMPLATE_WORKSPACE / "goals.md").read_text(encoding="utf-8"),
                                 encoding="utf-8")
    return ws


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def test_json_output_is_byte_identical_across_runs(tmp_path, monkeypatch, capsys):
    ws = full_ws(tmp_path)
    first = cli(ws, monkeypatch, capsys, "--json")
    assert first == cli(ws, monkeypatch, capsys, "--json")
    out = json.loads(first)
    assert out["as_of"] == "2026-10-02"
    assert list(out) == sorted(out)


def test_cli_writes_nothing(tmp_path, monkeypatch, capsys):
    ws = full_ws(tmp_path)
    before = tree_digest(ws)
    cli(ws, monkeypatch, capsys)
    cli(ws, monkeypatch, capsys, "--json")
    cli(ws, monkeypatch, capsys, "--as-of", "2026-09-10")
    assert tree_digest(ws) == before


def test_cli_with_only_a_config_exits_zero(tmp_path, monkeypatch, capsys):
    ws = make_ws(tmp_path)
    out = json.loads(cli(ws, monkeypatch, capsys, "--json"))
    assert out["as_of"] is None and out["weeks"] == []
    assert cli(ws, monkeypatch, capsys).strip()


def test_cli_refuses_a_non_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOTRAINER_WORKSPACE", str(tmp_path))
    with pytest.raises(SystemExit) as exc:
        status.main([])
    assert "not an Autotrainer workspace" in str(exc.value)


BANNED = ["should", "must", "need", "recommend", "try", "good", "bad", "great", "poor",
          "too", "overdue", "behind", "lazy", "warning"]


def test_brief_is_facts_only(tmp_path, monkeypatch, capsys):
    ws = full_ws(tmp_path)
    out = cli(ws, monkeypatch, capsys)
    lines = out.strip().splitlines()
    assert 0 < len(lines) <= 15
    assert lines[0] == "as of 2026-10-02"
    assert "last structured session: 13 days ago (bikeerg, 2026-09-19)" in lines
    assert "newest benchmark: 2026-08-14 (49 days; configured cadence 42); 1 recorded" in lines
    assert "goal: none" in lines
    assert "anchors missing: lthr, power.rowerg.ftp, power.rowerg.z2_watts_ceiling" in lines
    for text in (out, cli(make_ws(tmp_path / "empty"), monkeypatch, capsys)):
        for word in BANNED:
            assert not re.search(rf"\b{word}\b", text, re.IGNORECASE), word
