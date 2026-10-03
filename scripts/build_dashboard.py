#!/usr/bin/env python3
"""Render dashboard.html — a read-only view of the engine's files (spec §2).

Pure rendering, no logic or state of its own: reads index.jsonl,
baseline.jsonl, metrics.jsonl, session frontmatter, config/athlete.yaml and
benchmarks.md, writes one self-contained HTML file (inline CSS/SVG, a few
lines of inline JS for tooltips, no external requests). Deterministic: same
inputs -> same file; the "data through" stamp is the status facts' `as_of`
(scripts/lib/facts.py), the newest date in the data, never the clock.

Holds no athlete facts: anchor provenance comes from benchmarks.md (the
newest dated heading naming an LTHR or FTP test), VO2max estimates carry only
the general method caveats in knowledge/reference-values.yaml, and the
optional `athlete.anchors_note` in config/athlete.yaml is the coach's own
words, shown verbatim. A blank workspace renders plain empty states.

Usage: python3 scripts/build_dashboard.py [--artifact PATH]
"""

from __future__ import annotations

import html
import math
import re
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import facts as facts_lib
from lib import frontmatter
from lib import workspace
import compute_metrics

REFERENCE_VALUES = workspace.ENGINE_ROOT / "knowledge" / "reference-values.yaml"
# A benchmarks.md heading whose title names one of these tests is the anchor
# tiles' provenance ("benchmark <date>"): the newest such heading wins.
ANCHOR_BENCHMARK = re.compile(r"lthr|ftp", re.IGNORECASE)
# '- Result: x', '- **Result:** x' and '- **Result**: x' under a benchmark heading.
RESULT_LINE = re.compile(r"^\s*[-*]\s*(?:\*\*)?Result(?:\*\*)?:(?:\*\*)?\s*(.*?)\s*$",
                         re.IGNORECASE)

# palette: dataviz reference instance (light / dark)
ZONE_RAMP_L = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
ZONE_RAMP_D = ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"]

CSS = """
:root { color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
  --train:#2a78d6; --base:#eb6834;
  --z1:#86b6ef; --z2:#5598e7; --z3:#2a78d6; --z4:#1c5cab; --z5:#104281; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7;
  --muted:#898781; --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
  --train:#3987e5; --base:#d95926;
  --z1:#184f95; --z2:#256abf; --z3:#3987e5; --z4:#6da7ec; --z5:#9ec5f4; } }
:root[data-theme="dark"] {
  color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7;
  --muted:#898781; --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
  --train:#3987e5; --base:#d95926;
  --z1:#184f95; --z2:#256abf; --z3:#3987e5; --z4:#6da7ec; --z5:#9ec5f4; }
* { box-sizing:border-box; margin:0; }
body { background:var(--page); color:var(--ink);
  font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; padding:24px; }
.wrap { max-width:1060px; margin:0 auto; }
h1 { font-size:22px; font-weight:650; }
.sub { color:var(--ink2); margin:4px 0 20px; font-size:13.5px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:12px; margin-bottom:20px; }
.tile { background:var(--surface); border:1px solid var(--ring);
  border-radius:10px; padding:14px 16px; }
.tile .k { color:var(--ink2); font-size:12.5px; }
.tile .v { font-size:26px; font-weight:650; margin-top:2px; }
.tile .n { color:var(--muted); font-size:12px; margin-top:2px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
@media (max-width:820px){ .grid { grid-template-columns:1fr; } }
.card { background:var(--surface); border:1px solid var(--ring);
  border-radius:10px; padding:16px; overflow-x:auto; }
.card h2 { font-size:14.5px; font-weight:650; margin-bottom:2px; }
.card .d { color:var(--ink2); font-size:12.5px; margin-bottom:10px; }
.legend { display:flex; gap:14px; flex-wrap:wrap; font-size:12px;
  color:var(--ink2); margin-top:8px; }
.legend .sw { display:inline-block; width:10px; height:10px; border-radius:3px;
  margin-right:5px; vertical-align:-1px; }
svg text { font:11px system-ui,-apple-system,"Segoe UI",sans-serif;
  fill:var(--muted); font-variant-numeric:tabular-nums; }
svg .lab { fill:var(--ink2); }
table { border-collapse:collapse; width:100%; font-size:13px; margin-top:6px; }
th { text-align:left; color:var(--ink2); font-weight:600;
  border-bottom:1px solid var(--axis); padding:6px 8px; }
td { border-bottom:1px solid var(--grid); padding:6px 8px;
  font-variant-numeric:tabular-nums; }
.full { grid-column:1 / -1; }
.tip { position:absolute; background:var(--ink); color:var(--page);
  font:12px system-ui,sans-serif; padding:5px 9px; border-radius:6px;
  pointer-events:none; opacity:0; transition:opacity .12s; z-index:9;
  white-space:pre; }
.foot { color:var(--muted); font-size:12px; margin-top:20px; }
"""

JS = """
const tip=document.createElement('div');tip.className='tip';document.body.appendChild(tip);
for(const el of document.querySelectorAll('[data-tip]')){
  el.addEventListener('mousemove',e=>{tip.textContent=el.dataset.tip;
    tip.style.left=(e.pageX+14)+'px';tip.style.top=(e.pageY-12)+'px';tip.style.opacity=1;});
  el.addEventListener('mouseleave',()=>{tip.style.opacity=0;});
}
"""


# ---------------------------------------------------------------- data loading

def load_data(root: Path) -> dict:
    """Everything the page renders, read from the workspace at `root`.

    facts_lib.load does the file reading (a missing or unreadable file is an
    empty value, so a blank workspace renders); this adds per-session
    time-in-zone from session frontmatter, the benchmark table rows and the
    status facts (as_of, anchors) computed over the same data."""
    root = Path(root)
    data = facts_lib.load(root)
    tiz = {}
    for s in data["index"]:
        path = root / (s.get("file") or "")
        if not s.get("file") or not path.is_file():
            continue
        fm, _ = frontmatter.load(path)
        z = (fm.get("computed") or {}).get("time_in_zone")
        if z:
            tiz[s["id"]] = z
    return {**data, "tiz": tiz, "bench": benchmark_rows(data["benchmarks_md"]),
            "facts": facts_lib.collect(data)}


def benchmark_rows(benchmarks_md: str | None) -> list[dict]:
    """One Benchmarks-table row per dated heading, by the same rule as
    facts_lib.parse_benchmarks (hyphen, en or em dash; valid date; outside
    code fences) so the table never disagrees with the anchor provenance or
    the status facts. `result` is the section's first '- Result:' line, or
    '' when it has none."""
    rows, current, fenced = [], None, False
    for line in (benchmarks_md or "").splitlines():
        if facts_lib.FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = facts_lib.BENCHMARK_HEADING.match(line)
        if m or line.startswith("#"):
            current = None
            if m and _is_date(m.group(1)):
                current = {"date": m.group(1), "test": m.group(2), "result": ""}
                rows.append(current)
        elif current is not None and not current["result"]:
            r = RESULT_LINE.match(line)
            if r:
                current["result"] = re.sub(r"[*`]", "", r.group(1))
    return rows


def _is_date(text: str) -> bool:
    try:
        date.fromisoformat(text)
        return True
    except ValueError:
        return False


def anchor_benchmark(benchmarks_md: str | None) -> dict | None:
    """Newest dated benchmarks.md heading whose title mentions LTHR or FTP
    (first in file order on a tie), or None."""
    latest = None
    for b in facts_lib.parse_benchmarks(benchmarks_md):
        if ANCHOR_BENCHMARK.search(b["title"]) and (latest is None or b["date"] > latest["date"]):
            latest = b
    return latest


def iso_week(date: str) -> str:
    from datetime import date as d
    iso = d.fromisoformat(date).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


# ---------------------------------------------------------------- svg helpers

def _scale(vmin, vmax, lo, hi):
    span = (vmax - vmin) or 1
    return lambda v: lo + (v - vmin) / span * (hi - lo)


def _y_ticks(vmin, vmax, n=4):
    span = (vmax - vmin) or 1
    raw = span / n
    step = max(round(raw / 5) * 5, 1) if raw > 2 else max(round(raw, 1), 0.05)
    t, out = vmin - (vmin % step if step else 0), []
    while t <= vmax + 1e-9:
        if t >= vmin - 1e-9:
            out.append(round(t, 2))
        t += step
    return out or [vmin, vmax]


def dot_line_chart(points, *, w=470, h=200, y_label="", refs=(), fmt="{:.2f}",
                   color="var(--train)"):
    """points: [(label, value, tiptext)] in order. refs: [(value, name)]."""
    if not points:
        return "<p class='d'>no data yet</p>"
    pad_l, pad_r, pad_t, pad_b = 40, 26, 14, 26
    values = [v for _, v, _ in points] + [r[0] for r in refs]
    vmin, vmax = min(values), max(values)
    vpad = (vmax - vmin) * 0.15 or vmax * 0.1 or 1
    ys = _scale(vmin - vpad, vmax + vpad, h - pad_b, pad_t)
    xs = _scale(0, max(len(points) - 1, 1), pad_l, w - pad_r)
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{html.escape(y_label)}">']
    for t in _y_ticks(vmin, vmax):
        y = ys(t)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-6}" y="{y+3.5:.1f}" text-anchor="end">{fmt.format(t)}</text>')
    for rv, rname in refs:
        y = ys(rv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="var(--axis)" stroke-width="1" stroke-dasharray="5 4"/>')
        parts.append(f'<text x="{w-pad_r}" y="{y-4:.1f}" text-anchor="end" class="lab">{html.escape(rname)}</text>')
    line = " ".join(f"{xs(i):.1f},{ys(v):.1f}" for i, (_, v, _) in enumerate(points))
    parts.append(f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
    step = max(1, len(points) // 6)
    for i, (label, v, tiptext) in enumerate(points):
        x, y = xs(i), ys(v)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" stroke="var(--surface)" stroke-width="2"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="transparent" data-tip="{html.escape(tiptext)}"/>')
        if i % step == 0 or i == len(points) - 1:
            parts.append(f'<text x="{x:.1f}" y="{h-8}" text-anchor="middle">{html.escape(label)}</text>')
    parts.append(f'<line x1="{pad_l}" y1="{h-pad_b}" x2="{w-pad_r}" y2="{h-pad_b}" stroke="var(--axis)" stroke-width="1"/>')
    parts.append("</svg>")
    return "".join(parts)


def stacked_bar_chart(rows, series, colors, *, w=470, h=200, unit="min"):
    """rows: [(label, {series: value}, tip)]; series: ordered keys."""
    if not rows:
        return "<p class='d'>no data yet</p>"
    pad_l, pad_r, pad_t, pad_b = 40, 12, 12, 26
    totals = [sum(vals.values()) for _, vals, _ in rows]
    vmax = max(totals) or 1
    ys = _scale(0, vmax * 1.08, h - pad_b, pad_t)
    slot = (w - pad_l - pad_r) / len(rows)
    bw = min(slot * 0.62, 46)
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    for t in _y_ticks(0, vmax):
        y = ys(t)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-6}" y="{y+3.5:.1f}" text-anchor="end">{t:g}</text>')
    baseline_y = h - pad_b
    for i, (label, vals, tiptext) in enumerate(rows):
        x = pad_l + slot * i + (slot - bw) / 2
        cur = baseline_y
        segs = [(k, vals.get(k, 0)) for k in series if vals.get(k, 0) > 0]
        for j, (k, v) in enumerate(segs):
            hgt = baseline_y - ys(v)
            cur -= hgt
            rx = 4 if j == len(segs) - 1 else 0
            parts.append(
                f'<rect x="{x:.1f}" y="{cur:.1f}" width="{bw:.1f}" height="{max(hgt,1):.1f}" '
                f'rx="{rx}" fill="{colors[k]}" stroke="var(--surface)" stroke-width="2" '
                f'data-tip="{html.escape(tiptext)}"/>')
        parts.append(f'<text x="{x+bw/2:.1f}" y="{h-8}" text-anchor="middle">{html.escape(label)}</text>')
    parts.append(f'<line x1="{pad_l}" y1="{h-pad_b}" x2="{w-pad_r}" y2="{h-pad_b}" stroke="var(--axis)" stroke-width="1"/>')
    parts.append("</svg>")
    return "".join(parts)


def comparison_section(data: dict) -> str:
    """VO2max dot plot: the athlete vs reference points, one shared axis.
    Each of the athlete's estimates carries only its method's general caveat
    (reference-values.yaml `method_caveats`); what the numbers mean for this
    athlete belongs in their benchmarks.md, not here."""
    if not REFERENCE_VALUES.exists():
        return ""
    refs = yaml.safe_load(REFERENCE_VALUES.read_text(encoding="utf-8")) or {}
    caveats = refs.get("method_caveats") or {}
    config = data["config"]
    athlete = config.get("athlete") or {}
    power = (config.get("power") or {}).get("bikeerg") or {}
    age, sex, kg = athlete.get("age"), athlete.get("sex"), athlete.get("weight_kg")
    ftp = power.get("ftp")

    rows = [(a["label"], a["vo2max"], a["note"], "ref") for a in refs.get("athletes") or []]
    percentiles = refs.get("percentiles") or {}
    if age and sex and percentiles.get(sex):
        decade = f"{age//10*10}-{age//10*10+9}"
        pair = percentiles[sex].get(decade)
        if pair:
            rows.append((f"Top 10%, {sex} {decade}", pair[1], "FRIEND registry (approx.)", "ref"))
            rows.append((f"Average, {sex} {decade}", pair[0], "FRIEND registry (approx.)", "ref"))

    def estimate(label, value, detail, method):
        caveat = caveats.get(method)
        rows.append((label, value, f"{detail} — {caveat}" if caveat else detail, "you"))

    you = None
    est = refs.get("estimate")
    if kg and ftp and est:
        p20 = ftp / 0.95
        you = round((est["acsm_slope"] * (p20 / est["p20_to_pvo2max_divisor"]) / kg
                     + est["acsm_intercept"]), 1)
        estimate("You — power estimate", you,
                 f"from FTP {ftp} W (20-min power ≈ {round(p20)} W), {kg} kg", "power_estimate")
    vo2_points = [m for m in data["metrics"]
                  if m.get("name") == "vo2_max" and isinstance(m.get("value"), (int, float))]
    if vo2_points:
        latest = max(vo2_points, key=lambda p: p["date"])
        estimate("You — watch estimate", latest["value"],
                 f"wearable estimate {latest['date']}", "watch_estimate")
    hr_rest = athlete.get("hr_resting")
    hr_max = athlete.get("hr_max")
    if hr_rest and hr_max:
        estimate("You — HR-ratio estimate", round(15.3 * hr_max / hr_rest, 1),
                 f"15.3 × {hr_max} ÷ {hr_rest}", "hr_ratio_estimate")
    if not rows:
        return ""
    rows.sort(key=lambda r: -r[1])

    w, row_h, pad_l, pad_r = 470, 34, 10, 56
    h = len(rows) * row_h + 34
    vmax = max(r[1] for r in rows) * 1.12
    xs = _scale(0, vmax, pad_l, w - pad_r)
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    for t in _y_ticks(0, vmax, 4):
        x = xs(t)
        parts.append(f'<line x1="{x:.1f}" y1="6" x2="{x:.1f}" y2="{h-26}" stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{h-12}" text-anchor="middle">{t:g}</text>')
    for i, (label, v, note, kind) in enumerate(rows):
        y = i * row_h + 24
        color = "var(--train)" if kind == "you" else "var(--muted)"
        weight = "650" if kind == "you" else "400"
        parts.append(f'<line x1="{xs(0):.1f}" y1="{y}" x2="{xs(v):.1f}" y2="{y}" stroke="{color}" stroke-width="2" opacity="0.45"/>')
        parts.append(f'<circle cx="{xs(v):.1f}" cy="{y}" r="5" fill="{color}" stroke="var(--surface)" stroke-width="2"/>')
        parts.append(f'<circle cx="{xs(v):.1f}" cy="{y}" r="12" fill="transparent" data-tip="{html.escape(label + chr(10) + str(v) + " ml/kg/min — " + note)}"/>')
        parts.append(f'<text x="{xs(0):.1f}" y="{y-8}" class="lab" style="font-weight:{weight}">{html.escape(label)}</text>')
        parts.append(f'<text x="{xs(v)+10:.1f}" y="{y+4:.1f}" style="font-weight:{weight}">{v:g}</text>')
    parts.append("</svg>")
    missing = ""
    if you is None:
        missing = ("<p class='d'>Add <code>age</code>, <code>sex</code> and "
                   "<code>weight_kg</code> to config/athlete.yaml to place "
                   "yourself (and your age-group lines) on this scale.</p>")
    return f"""<div class="card"><h2>VO&#8322;max in context</h2>
<div class="d">ml/kg/min — estimates and literature values, not lab tests;
hover a point for its method and caveat</div>
{"".join(parts)}{missing}</div>"""


# ---------------------------------------------------------------- assembly

UNIT = "<span style='font-size:14px'> {}</span>"


def tile(k, v, n=""):
    return (f'<div class="tile"><div class="k">{html.escape(k)}</div>'
            f'<div class="v">{v}</div><div class="n">{html.escape(n)}</div></div>')


def subtitle(as_of, has_sessions: bool, lthr, ftp, anchors_note) -> str:
    """'data through <as_of>' (or 'no sessions yet') and the configured
    anchors, with the coach's optional anchors_note verbatim."""
    parts = ["Read-only rendering of the training ledger"]
    if as_of:
        parts.append(f"data through {as_of}")
    if not has_sessions:
        parts.append("no sessions yet")
    out = " · ".join(html.escape(p) for p in parts)
    anchors = [a for a in (f"LTHR {lthr}" if lthr is not None else None,
                           f"FTP {ftp} W" if ftp is not None else None) if a]
    note = anchors_note.strip() if isinstance(anchors_note, str) else ""
    if anchors or note:
        text = ", ".join(anchors)
        text = f"{text} ({note})" if text and note else text or note
        out += "\n · " + html.escape(f"anchors: {text}")
    return out


def build(root: Path | None = None) -> str:
    """The full dashboard document for the workspace at `root` (default:
    workspace.root()). Reads files only; writes nothing."""
    root = Path(root) if root is not None else workspace.root()
    data = load_data(root)
    index, baseline, config = data["index"], data["baseline"], data["config"]
    tiz, bench, facts = data["tiz"], data["bench"], data["facts"]
    athlete = config.get("athlete") or {}
    power = (config.get("power") or {}).get("bikeerg") or {}
    lthr, ftp = athlete.get("lthr"), power.get("ftp")
    ceiling = power.get("z2_watts_ceiling")
    bands, zones_source = compute_metrics.zone_bounds(config)
    z2 = None
    if zones_source == "lthr" and "z2" in bands:
        # whole bpm inside [lo, hi): the resolved, contiguous band
        z2_lo, z2_hi = bands["z2"]
        z2 = f"{math.ceil(z2_lo)}–{math.ceil(z2_hi) - 1}"
    as_of = facts["as_of"]  # newest date in the data, never the clock

    # anchor tiles: only for anchors that are set; provenance from benchmarks.md
    anchor_bench = anchor_benchmark(data["benchmarks_md"])
    provenance = f"benchmark {anchor_bench['date']}" if anchor_bench else ""
    tiles = []
    if ftp is not None:
        tiles.append(tile("FTP (BikeErg)", f"{ftp}{UNIT.format('W')}", provenance))
    if lthr is not None:
        tiles.append(tile("LTHR", f"{lthr}{UNIT.format('bpm')}", provenance))
    if z2:
        tiles.append(tile("Zone 2", f"{z2}{UNIT.format('bpm')}",
                          f"≤{ceiling} W on the BikeErg" if ceiling is not None else ""))
    if index:
        # counted back from the newest session, not as_of: daily health
        # metrics usually run ahead of workout exports
        last_session = max(s["date"] for s in index)
        last7 = [s for s in index if s["date"] > _shift(last_session, -7)]
        train_min = round(sum(s.get("duration_s") or 0 for s in last7) / 60)
        tiles.append(tile("Training, last 7 days", f"{train_min}{UNIT.format('min')}",
                          f"{len(last7)} sessions"))
        this_week = iso_week(last_session)
        base_week = next((b for b in baseline if b.get("week") == this_week), None)
        tiles.append(tile("Baseline this week",
                          f"{(base_week or {}).get('minutes', 0)}{UNIT.format('min')}",
                          f"{base_week['count']} walks" if base_week else "no short walks this week"))
    tiles_html = f'<div class="tiles">{"".join(tiles)}</div>' if tiles else ""

    session_cards = session_charts(index, tiz, lthr, ftp, ceiling, zones_source,
                                   athlete.get("hr_max")) if index else ""

    base_rows = [(b["week"][5:], {"m": b["minutes"]},
                  f"{b['week']}  {b['minutes']} min, {b['count']} walks")
                 for b in baseline]
    base_chart = (stacked_bar_chart(base_rows, ["m"], {"m": "var(--base)"}) if base_rows
                  else "<p class='d'>no baseline activity yet</p>")

    def _dec_cell(s):
        if s.get("decoupling_pct") is None:
            return "—"
        return f"{s['decoupling_pct']}" + ("" if s.get("decoupling_method") == "pw_hr" else " (HR)")

    sess_rows = "".join(
        f"<tr><td>{s['date']}</td><td>{s['modality']}</td>"
        f"<td>{round((s.get('duration_s') or 0)/60)} min</td>"
        f"<td>{s.get('hr_avg') or '—'}</td><td>{s.get('watts_avg') or '—'}</td>"
        f"<td>{s.get('efficiency_factor') or '—'}</td>"
        f"<td>{_dec_cell(s)}</td>"
        f"<td>{s['compliance_score'] if s.get('compliance_score') is not None else '—'}</td></tr>"
        for s in sorted(index, key=lambda s: s["date"], reverse=True)[:12])
    sessions_html = (
        '<table><tr><th>date</th><th>modality</th><th>dur</th><th>HR</th><th>watts</th>\n'
        '<th>EF</th><th title="power:HR decoupling; (HR) = heart-rate drift, no power trace">'
        f'dec %</th><th>score</th></tr>{sess_rows}</table>'
        if index else "<p class='d'>no sessions yet</p>")

    def _clip(text, n=100):
        return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"

    bench_rows = "".join(
        f"<tr><td>{b['date']}</td><td>{html.escape(b['test'])}</td>"
        f"<td>{html.escape(_clip(b['result'])) or '—'}</td></tr>" for b in bench)
    bench_html = (f"<table><tr><th>date</th><th>test</th><th>result</th></tr>{bench_rows}</table>"
                  if bench else "<p class='d'>no benchmarks yet</p>")

    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cardio Coach</title>
<style>{CSS}</style>
<div class="wrap">
<h1>Cardio Coach</h1>
<p class="sub">{subtitle(as_of, bool(index), lthr, ftp, athlete.get("anchors_note"))}</p>
{tiles_html}
<div class="grid">
{session_cards}
<div class="card"><h2>Baseline activity</h2>
<div class="d">unstructured movement (walks) — tracked, never scored</div>
{base_chart}</div>
{comparison_section(data)}
<div class="card"><h2>Benchmarks</h2>
{bench_html}</div>
<div class="card full"><h2>Recent sessions</h2>
{sessions_html}</div>
</div>
<p class="foot">Generated by scripts/build_dashboard.py — a pure rendering of
data/index.jsonl, data/baseline.jsonl, config/athlete.yaml and benchmarks.md.
Regenerated on every ingest; edit those files, never this one.</p>
</div>
<script>{JS}</script>
"""


def session_charts(index, tiz, lthr, ftp, ceiling, zones_source, hr_max) -> str:
    """The per-session chart cards (efficiency, watts, zones, decoupling);
    only rendered when the ledger has sessions."""
    rides = [s for s in index if s["modality"] == "bikeerg" and s.get("efficiency_factor")]
    ef_pts = [(s["date"][5:], s["efficiency_factor"],
               f"{s['date']}  EF {s['efficiency_factor']}\n{s['watts_avg']} W @ {s['hr_avg']} bpm")
              for s in rides]
    watt_pts = [(s["date"][5:], s["watts_avg"],
                 f"{s['date']}  {s['watts_avg']} W avg\n{round((s['duration_s'] or 0)/60)} min")
                for s in index if s["modality"] == "bikeerg" and s.get("watts_avg")]
    watt_refs = [r for r in ((ceiling, f"z2 ceiling {ceiling}W"), (ftp, f"FTP {ftp}W"))
                 if r[0] is not None]
    against = [n for v, n in ((ceiling, "the Zone 2 ceiling"), (ftp, "current FTP"))
               if v is not None]
    watt_desc = ("against " + " and ".join(against)) if against else "average power per ride"
    # power:HR decoupling and HR drift never share a chart: only pw_hr points
    # are read against the 5% line; HR drift gets its own unreferenced card
    def _dec_pts(power: bool):
        return [(s["date"][5:], s["decoupling_pct"],
                 f"{s['date']}  {s['decoupling_pct']}% {'decoupling' if power else 'HR drift'}\n"
                 f"{s['modality']}, {round((s['duration_s'] or 0)/60)} min")
                for s in index if s.get("decoupling_pct") is not None
                and (s.get("decoupling_method") == "pw_hr") == power]
    pw_pts, drift_pts = _dec_pts(True), _dec_pts(False)
    dec_cards = ""
    if pw_pts:
        dec_cards += ('<div class="card"><h2>Aerobic decoupling per session</h2>\n'
                      '<div class="d">power:HR, after the warm-up; under 5% = solid aerobic '
                      'durability for that duration</div>\n'
                      + dot_line_chart(pw_pts, fmt="{:.0f}", refs=[(5, "5%")]) + "</div>")
    if drift_pts or not pw_pts:
        dec_cards += ('<div class="card"><h2>HR drift per session</h2>\n'
                      '<div class="d">second-half vs first-half heart rate after the warm-up — '
                      'true power:HR decoupling needs a power trace</div>\n'
                      + dot_line_chart(drift_pts, fmt="{:.0f}") + "</div>")

    zones = ["z1", "z2", "z3", "z4", "z5"]
    weeks: dict[str, dict] = {}
    for s in index:
        z = tiz.get(s["id"])
        if not z:
            continue
        wk = weeks.setdefault(iso_week(s["date"]), {k: 0 for k in zones})
        for k in zones:
            wk[k] += (z.get(k) or 0) / 60
    zone_rows = [(wk[5:], {k: round(v) for k, v in vals.items()},
                  wk + "  " + "  ".join(f"{k} {round(vals[k])}m" for k in zones if vals[k] >= 1))
                 for wk, vals in sorted(weeks.items())]
    zone_colors = {z: f"var(--{z})" for z in zones}
    zone_legend = "".join(
        f'<span><span class="sw" style="background:var(--{z})"></span>{z}</span>' for z in zones)
    zone_legend = f'\n<div class="legend">{zone_legend}</div>' if zone_rows else ""
    zones_from = {"lthr": f" (zones from LTHR {lthr})",
                  "bootstrap": f" (bootstrap zones from HRmax {hr_max})"}.get(zones_source, "")

    return f"""<div class="card"><h2>Efficiency factor — BikeErg</h2>
<div class="d">avg watts ÷ avg HR per ride; rising = same effort, more output</div>
{dot_line_chart(ef_pts, y_label="Efficiency factor")}</div>
<div class="card"><h2>Avg watts per ride — BikeErg</h2>
<div class="d">{watt_desc}</div>
{dot_line_chart(watt_pts, fmt="{:.0f}", refs=watt_refs)}</div>
<div class="card"><h2>Weekly minutes in zone</h2>
<div class="d">HR time-in-zone across training sessions{zones_from}</div>
{stacked_bar_chart(zone_rows, zones, zone_colors)}{zone_legend}</div>
{dec_cards}"""


def _shift(date: str, days: int) -> str:
    from datetime import date as d, timedelta
    return (d.fromisoformat(date) + timedelta(days=days)).isoformat()


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", type=Path, default=None,
                    help="also write an artifact-ready copy (no doctype — the "
                         "claude.ai artifact wrapper supplies the document shell)")
    args = ap.parse_args()
    root = workspace.root()
    workspace.require(root)
    out_path = root / "dashboard.html"
    doc = build(root)
    out_path.write_text(doc, encoding="utf-8")
    print(f"dashboard.html rendered ({out_path.stat().st_size // 1024} KB)")
    if args.artifact:
        args.artifact.write_text(doc.replace("<!doctype html>\n", "", 1), encoding="utf-8")
        print(f"artifact copy -> {args.artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
