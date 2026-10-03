"""Privacy guard tests — including a live audit of the actual repo content,
so `pytest` itself fails if a location/identity leak ever lands in tracked
files or photos."""

import gzip
import os
import re
import subprocess
import sys
from pathlib import Path

from conftest import WORKSPACE, requires_workspace

import privacy_check as pc


# Positive-case PII samples are assembled at runtime (never literal in this
# file) so the repo-wide audit below stays clean without excluding this file.
PHONE = "555" + "-555-" + "0142"
PHONE_PARENS = "(555)" + " 555-" + "0142"
ADDRESS = "4501 Sam" + "ple Rd"
ADDRESS2 = "12 Oak " + "Street"
EMAIL = "j.doe@" + "corp.com"
CORP_EMAIL = "someone@" + "example-corp.com"


def test_phone_matches_real_numbers_not_dois():
    assert pc.PHONE_RE.search(f"call {PHONE} tonight")
    assert pc.PHONE_RE.search(PHONE_PARENS)
    # DOI / article-number fragments must not match (real case: evidence.md)
    assert not pc.PHONE_RE.search("s41746-025-02238-1")
    assert not pc.PHONE_RE.search("Med Sci Sports Exerc 39(4):665-671")


def test_address_matches_street_not_prose():
    assert pc.ADDRESS_RE.search(f"meet at {ADDRESS} for the run")
    assert not pc.ADDRESS_RE.search("progress by 10 watts per week")
    assert not pc.ADDRESS_RE.search("180 - age formula")


def test_email_allowlist():
    assert pc.EMAIL_ALLOWLIST.search("12345+user@" + "users.noreply.github.com")
    assert pc.EMAIL_ALLOWLIST.search("noreply@" + "anthropic.com")
    assert not pc.EMAIL_ALLOWLIST.search(CORP_EMAIL)


def test_text_check_flags_and_passes(tmp_path):
    dirty = tmp_path / "dirty.md"
    dirty.write_text(f"Contact John at {EMAIL} or {PHONE}, he lives at {ADDRESS2}.")
    findings = pc.check_text(dirty, personal=[re.compile("John Doe", re.I)])
    kinds = " ".join(findings)
    assert "email" in kinds and "phone" in kinds and "street address" in kinds

    clean = tmp_path / "clean.md"
    clean.write_text("Zone 2 ride, 45 min at 138 W, decoupling 3.1%")
    assert pc.check_text(clean, personal=[]) == []


@requires_workspace
def test_workspace_photos_have_no_gps_or_owner_exif():
    photos = [p for p in (WORKSPACE / "data" / "raw" / "photos").iterdir()
              if p.suffix.lower() in pc.PHOTO_EXTS]
    assert photos, "expected photos in the workspace's data/raw/photos"
    for photo in photos:
        assert pc.check_photo(photo) == [], f"identifying EXIF in {photo.name}"


# ---------------------------------------------------------------- location-bearing files

# Obviously fake coordinates (Null Island neighbourhood), assembled at runtime.
LAT, LON = "0." + "123", "-0." + "456"


def test_newly_scanned_text_types(tmp_path):
    for ext in (".html", ".htm", ".svg", ".js", ".tsv", ".toml"):
        f = tmp_path / f"notes{ext}"
        f.write_text(f"call {PHONE}")
        assert any("phone" in x for x in pc.check_file(f, [], set())), ext


def test_location_formats_fail_outright(tmp_path):
    for ext in (".gpx", ".kml", ".kmz", ".geojson"):
        f = tmp_path / f"ride{ext}"
        f.write_bytes(b"anything")
        [finding] = pc.check_file(f, [], {f"ride{ext}", str(f)})   # allow_files does not apply
        assert "location format" in finding


def test_tcx_fails_only_with_trackpoint_positions(tmp_path):
    point = "<Trackpoint><Time>2026-01-01T00:00:00Z</Time><HeartRateBpm><Value>120</Value></HeartRateBpm>"
    pos = "<Posi" + f"tion><LatitudeDegrees>{LAT}</LatitudeDegrees><LongitudeDegrees>{LON}</LongitudeDegrees></Position>"
    indoor = tmp_path / "indoor.tcx"
    indoor.write_text(f"<Activity>{point}</Trackpoint></Activity>")
    assert pc.check_file(indoor, [], set()) == []
    outdoor = tmp_path / "outdoor.tcx"
    outdoor.write_text(f"<Activity>{point}{pos}</Trackpoint></Activity>")
    assert any("GPS route" in x for x in pc.check_file(outdoor, [], set()))
    lone = tmp_path / "ns.tcx"                                  # namespaced, no <Position> wrapper
    lone.write_text("<ns:Latitude" + f"Degrees>{LAT}</ns:LatitudeDegrees>")
    assert pc.check_file(lone, [], set())


def test_fit_needs_an_allow_files_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pc, "LOCAL_CONFIG", tmp_path / "config" / "privacy.local.yaml")
    fit = tmp_path / "data" / "raw" / "erg.fit"
    fit.parent.mkdir(parents=True)
    fit.write_bytes(b"\x0e\x10binary")
    assert pc.load_allow_files() == set()                       # no local config at all
    assert "allow_files" in pc.check_file(fit, [], pc.load_allow_files())[0]
    pc.LOCAL_CONFIG.parent.mkdir()
    pc.LOCAL_CONFIG.write_text("never_commit: []\nallow_files:\n  - data/raw/erg.fit\n")
    assert pc.load_allow_files() == {"data/raw/erg.fit"}
    assert pc.check_file(fit, [], pc.load_allow_files()) == []
    assert pc.audit([fit], [], pc.load_allow_files()) == []
    other = fit.with_name("other.fit"); other.write_bytes(b"x")
    assert pc.check_file(other, [], pc.load_allow_files())    # the entry is per path


def test_json_coordinate_pairs_fail(tmp_path):
    q = '"'
    for key, val in (("lat", LAT), ("Longitude", LON), ("start_lat", LAT), ("endLng", LON),
                     ("lon", f"{q}{LON}{q}")):
        f = tmp_path / "w.json"
        f.write_text("{" + f"{q}{key}{q}: {val}, {q}hr{q}: 120" + "}")
        assert any("coordinate" in x for x in pc.check_file(f, [], set())), key
    jsonl = tmp_path / "w.jsonl"
    jsonl.write_text("{" + f"{q}id{q}: 1}}\n{{{q}la" + f"titude{q}:{LAT}" + "}\n")
    assert pc.check_file(jsonl, [], set())
    page = tmp_path / "dash.html"                               # JSON inlined in a page
    page.write_text("<script>const D = [{" + f"{q}lng{q}: {LON}" + "}];</script>")
    assert pc.check_file(page, [], set())


def test_json_non_coordinates_pass(tmp_path):
    f = tmp_path / "w.json"
    f.write_text('{"flat": 1.5, "latency_ms": 120, "long": 30, "lat": null, "plateau_w": 140,'
                 ' "lon_note": "none", "relative": 0.8, "lat_count": 1234}')
    assert pc.check_file(f, [], set()) == []


def test_coordinate_arrays_pairs_and_semicircles_fail(tmp_path):
    # Shapes the scalar-only pattern missed: Strava summaries and streams,
    # GeoJSON saved as .json, columnar per-second streams, FIT records decoded
    # to JSON (semicircle integers), JS object literals, escaped inline JSON.
    q, semi = '"', "1468" + "0064"
    samples = {
        "strava.json": "{" + f"{q}start_latlng{q}: [{LAT}, {LON}]" + "}",
        "streams.json": "{" + f"{q}latlng{q}: {{{q}data{q}: [[{LAT},{LON}]]}}" + "}",
        "geo.json": "{" + f"{q}type{q}:{q}LineString{q},{q}coordinates{q}:[[{LON},{LAT}]]" + "}",
        "point.json": "{" + f"{q}coordinates{q}: [{LON}, {LAT}]" + "}",
        "columns.json": "{" + f"{q}lat{q}: [{LAT}, {LAT}1], {q}lon{q}: [{LON}]" + "}",
        "fit.jsonl": "{" + f"{q}position_lat{q}: {semi}" + "}\n",
        "fit2.json": "{" + f"{q}start_position_long{q}: {q}-{semi}{q}" + "}",
        "map.js": "const p = {" + f"lat: {LAT}, lng: {LON}" + "};",
        "page.html": "<script>JSON.parse(\"{" + f"\\{q}lat\\{q}:{LAT}" + "}\")</script>",
    }
    for name, text in samples.items():
        f = tmp_path / name
        f.write_text(text)
        assert any("coordinate" in x for x in pc.check_file(f, [], set())), name


def test_coordinate_near_misses_pass(tmp_path):
    f = tmp_path / "w.json"
    f.write_text('{"coordinates": "see notes", "grid": {"coordinates": [3, 4]}, "latlng": null,'
                 ' "latlng_source": [1.2], "position_latency": 12345, "long": 1234567}')
    assert pc.check_file(f, [], set()) == []
    js = tmp_path / "app.js"
    js.write_text("const flat = 3; const o = {plat: 4, latency: 12};")
    assert pc.check_file(js, [], set()) == []


def test_tcx_content_saved_as_xml_fails(tmp_path):
    xml = tmp_path / "activity.xml"
    xml.write_text("<Trackpoint><Position><Latitude" + f"Degrees>{LAT}</LatitudeDegrees>")
    assert any("GPS route" in x for x in pc.check_file(xml, [], set()))
    plain = tmp_path / "layout.xml"                             # <Position> alone is not TCX
    plain.write_text("<Widget><Position>top</Position></Widget>")
    assert pc.check_file(plain, [], set()) == []


def test_compressed_and_archived_files(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "REPO_ROOT", tmp_path)
    track = ("<gpx><trk><trkseg><trkpt la" + f't="{LAT}" lon="{LON}"/></trkseg></trk></gpx>').encode()
    gpx_gz = tmp_path / "ride.gpx.gz"
    gpx_gz.write_bytes(gzip.compress(track))
    # a compressed location format fails outright, even when allow-listed
    [finding] = pc.check_file(gpx_gz, [], {"ride.gpx.gz"})
    assert "location format" in finding
    assert "location format" in pc.check_file(tmp_path / "Ride.KML.GZ", [], set())[0]
    for name in ("ride.fit.gz", "ride.tcx.gz", "notes.csv.bz2", "export.zip", "bulk.tar.gz"):
        f = tmp_path / name
        f.write_bytes(gzip.compress(track))
        [finding] = pc.check_file(f, [], set())
        assert "allow_files" in finding, name
        assert pc.check_file(f, [], {name}) == [], name          # reviewed and allowed


def test_name_based_findings_do_not_need_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "REPO_ROOT", tmp_path)
    gone = [tmp_path / "gone.gpx", tmp_path / "gone.fit", tmp_path / "gone.tcx.gz"]
    assert len(pc.audit(gone, [], set())) == 3


# ---------------------------------------------------------------- the CLI in a scratch repo

def _scratch_repo(tmp_path: Path) -> tuple[Path, dict]:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               AUTOTRAINER_WORKSPACE=str(tmp_path / "nowhere"))
    subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "ci@" + "users.noreply.github.com"],
                   cwd=repo, env=env, check=True)
    return repo, env


def _run_guard(repo: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    script = Path(pc.__file__).resolve()
    return subprocess.run([sys.executable, str(script), *args], cwd=repo, env=env,
                          capture_output=True, text=True)


def test_cli_sees_non_ascii_file_names(tmp_path):
    # git C-quotes non-ASCII paths by default; the guard must still find them.
    repo, env = _scratch_repo(tmp_path)
    (repo / "notes.md").write_text("clean")
    (repo / "Morning Run \u2013 Lake.gpx").write_text("<gpx/>")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    for args in (("--staged",), ()):
        res = _run_guard(repo, env, *args)
        assert res.returncode == 1, (args, res.stdout, res.stderr)
        assert "Lake.gpx" in res.stderr and "location format" in res.stderr


def test_cli_staged_judges_the_index_not_the_working_tree(tmp_path):
    repo, env = _scratch_repo(tmp_path)
    gone = repo / "gone.gpx"
    gone.write_text("<gpx/>")
    tcx = repo / "ride.tcx"
    tcx.write_text("<Trackpoint><Posi" + f"tion><LatitudeDegrees>{LAT}</LatitudeDegrees></Position>")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    gone.unlink()                                               # staged, then deleted on disk
    tcx.write_text("<Trackpoint></Trackpoint>")                  # staged, then cleaned on disk
    res = _run_guard(repo, env, "--staged")
    assert res.returncode == 1, res.stdout
    assert "gone.gpx" in res.stderr and "ride.tcx: TCX with trackpoint" in res.stderr
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)   # stage the fixes
    res = _run_guard(repo, env, "--staged")
    assert res.returncode == 0, res.stderr


def test_generated_dashboard_html_passes(tmp_path):
    # Shapes build_dashboard.py emits: viewBox, polylines, rects, ISO dates and
    # week labels. The path below has plotted numbers that read as a phone
    # number (3-3-4 digits) unless SVG geometry is exempted; assembled at
    # runtime so this file itself stays clean.
    tricky = "M40 94 L" + "103.825 " + "1371.2 L" + "125.1 94.0"
    assert pc.PHONE_RE.search(tricky)
    svg = ('<svg viewBox="0 0 470 200" width="100%" role="img" aria-label="Efficiency factor">'
           '<line x1="40" y1="130.9" x2="444" y2="130.9" stroke="var(--grid)" stroke-width="1"/>'
           '<polyline points="40.0,94.0 61.3,100.2 82.5,87.8 103.8,137.1" fill="none"/>'
           f'<path d="{tricky}" fill="none"/>'
           '<circle cx="40.0" cy="94.0" r="4.5" fill="var(--train)"/>'
           '<rect x="47.2" y="159.0" width="23.6" height="15.0" rx="0" data-tip="2026-W29  z1 21m  z3 1m"/>'
           '<text x="34" y="134.4" text-anchor="end">2026-09-03</text></svg>')
    page = tmp_path / "dashboard.html"
    page.write_text(f"<!doctype html><html><body><h2>Trends</h2>{svg}"
                    "<table><tr><td>2026-09-03</td><td>45:00</td><td>138 W</td><td>1.42</td></tr></table>"
                    "</body></html>")
    assert pc.check_file(page, [], set()) == []
    standalone = tmp_path / "chart.svg"
    standalone.write_text(svg)
    assert pc.check_file(standalone, [], set()) == []
    # the exemption covers numeric geometry only: text content is still scanned
    leaky = tmp_path / "leaky.html"
    leaky.write_text(f'{svg}<p>call {PHONE}</p><rect data-tip="{ADDRESS}" width="3"/>')
    kinds = " ".join(pc.check_file(leaky, [], set()))
    assert "phone" in kinds and "street address" in kinds


def test_tracked_files_are_clean():
    # Same dispatch as the CLI: text, photos and location-bearing formats.
    findings = pc.audit(pc.tracked_files(), pc.load_personal_patterns(), pc.load_allow_files())
    assert findings == [], f"privacy findings in tracked files: {findings}"
