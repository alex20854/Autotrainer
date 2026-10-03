#!/usr/bin/env python3
"""Render dashboard.html — a read-only view of the engine's files (spec §2).

Pure rendering, no logic or state of its own: reads index.jsonl,
baseline.jsonl, metrics.jsonl, session frontmatter, config/athlete.yaml and
benchmarks.md, writes one self-contained HTML file (inline CSS/SVG, a few
lines of inline JS for tooltips, no external requests). Deterministic: same
inputs -> same file; the "data through" stamp is the status facts' `as_of`
(scripts/lib/facts.py), the newest date in the data, never the clock.

The status band at the top restates status facts verbatim (dates, counts,
presence) with no advice. Training totals count structured sessions only;
the facts' unstructured modalities (walks by default) appear only in the
Baseline card. Per-session charts sit on a linear date axis ending at
`as_of`, so a layoff shows as empty space; weekly charts use contiguous,
zero-filled weeks through the as-of week (the Baseline chart reaching back to
the earliest baseline.jsonl week). The recovery strip (resting HR, HRV) renders
only with `dashboard: {show_recovery: true}` in config/athlete.yaml: the
hosted page can be shared, and those numbers are more sensitive than
workout totals.

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
from datetime import date, timedelta
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

# Short text labels for index.jsonl `source_kinds` (Recent sessions table):
# where a row's data came from, in words rather than colour.
SOURCE_LABELS = {"health": "Health", "photo": "Photo", "c2": "C2", "user": "Manual"}
# Display defaults (layout, not judgment): candidate date-tick steps in days,
# the gap after which a per-session line is not drawn through empty time,
# and how many of the facts' weeks the weekly charts show.
TICK_STEPS_DAYS = (1, 2, 3, 7, 14, 28, 56, 91, 182, 364)
GAP_BREAK_DAYS = 21
MAX_WEEKS = 26

# palette: dataviz reference instance (light / dark)
ZONE_RAMP_L = ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]
ZONE_RAMP_D = ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"]

CSS = """
:root { color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#6f6d68; --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
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
.sub { color:var(--ink2); margin:4px 0 14px; font-size:13.5px; }
.status { background:var(--surface); border:1px solid var(--ring);
  border-radius:10px; padding:10px 16px; margin-bottom:14px; }
.status h2 { font-size:12.5px; font-weight:650; color:var(--ink2); margin-bottom:4px; }
.status ul { list-style:none; padding:0; display:flex; flex-wrap:wrap;
  gap:4px 18px; font-size:13px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:12px; margin-bottom:20px; }
.tile { background:var(--surface); border:1px solid var(--ring);
  border-radius:10px; padding:14px 16px; }
.tile .k { color:var(--ink2); font-size:12.5px; }
.tile .v { font-size:26px; font-weight:650; margin-top:2px; }
.tile .n { color:var(--muted); font-size:12px; margin-top:2px; }
.grid { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:16px; }
@media (max-width:820px){ .grid { grid-template-columns:minmax(0,1fr); } }
.card { background:var(--surface); border:1px solid var(--ring);
  border-radius:10px; padding:16px; overflow-x:auto; min-width:0; }
.card h2 { font-size:14.5px; font-weight:650; margin-bottom:2px; }
.card .d { color:var(--ink2); font-size:12.5px; margin-bottom:10px; }
.legend { display:flex; gap:14px; flex-wrap:wrap; font-size:12px;
  color:var(--ink2); margin-top:8px; }
.legend .sw { display:inline-block; width:10px; height:10px; border-radius:3px;
  margin-right:5px; vertical-align:-1px; }
svg text { font:11px system-ui,-apple-system,"Segoe UI",sans-serif;
  fill:var(--muted); font-variant-numeric:tabular-nums; }
svg .lab { fill:var(--ink2); }
svg .ref { paint-order:stroke; stroke:var(--surface); stroke-width:4px; stroke-linejoin:round; }
table { border-collapse:collapse; width:100%; font-size:13px; margin-top:6px; }
th { text-align:left; color:var(--ink2); font-weight:600;
  border-bottom:1px solid var(--axis); padding:6px 8px; white-space:nowrap; }
td { border-bottom:1px solid var(--grid); padding:6px 8px;
  font-variant-numeric:tabular-nums; }
.scroll { overflow-x:auto; }
.nowrap td { white-space:nowrap; }
.scroll th:first-child, .scroll td:first-child { position:sticky; left:0;
  background:var(--surface); white-space:nowrap; }
.full { grid-column:1 / -1; }
.tip { position:fixed; left:0; top:0; background:var(--ink); color:var(--page);
  font:12px system-ui,sans-serif; padding:5px 9px; border-radius:6px;
  pointer-events:none; opacity:0; transition:opacity .12s; z-index:9;
  white-space:pre-line; max-width:min(320px, calc(100vw - 16px)); }
[data-tip]:focus { outline:none; }
[data-tip]:focus-visible { outline:2px solid var(--ink); outline-offset:1px;
  stroke:var(--ink); stroke-width:2; }
.foot { color:var(--muted); font-size:12px; margin-top:20px; }
/* chart text scales with each SVG's 470-unit viewBox; raised wherever the
   chart is narrower than that so it renders at about 11px or more:
   single column 521-820px (chart >= 439px wide: 12 units ~ 11.2px), two
   columns 821-1079px (chart >= 344px: 16 units ~ 11.7px) */
@media (min-width:521px) and (max-width:820px) { svg text { font-size:12px; } }
@media (min-width:821px) and (max-width:1079px) { svg text { font-size:16px; } }
/* phone: 16px gutter; chart text raised so the scaled-down SVGs stay legible
   (a 470-unit viewBox in a ~317px card is x0.67: 17 units ~ 11.5px) */
@media (max-width:520px) {
  body { padding:16px; }
  .card { padding:12px; }
  .tiles { grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
  .tile { padding:12px; }
  .tile .v { font-size:22px; }
  svg text { font-size:17px; }
}
"""

JS = """
const tip=document.createElement('div');tip.className='tip';tip.setAttribute('role','tooltip');
document.body.appendChild(tip);
let cur=null;
function show(el,x,y){cur=el;tip.textContent=el.dataset.tip;tip.style.opacity=1;
  const w=tip.offsetWidth,h=tip.offsetHeight;
  tip.style.left=Math.max(8,Math.min(x+12,innerWidth-w-8))+'px';
  tip.style.top=(y-h-10<8?y+18:y-h-10)+'px';}
function near(el){const r=el.getBoundingClientRect();show(el,r.left+r.width/2,r.top);}
function hide(){cur=null;tip.style.opacity=0;}
for(const el of document.querySelectorAll('[data-tip]')){
  el.addEventListener('mousemove',e=>show(el,e.clientX,e.clientY));
  el.addEventListener('mouseleave',hide);
  el.addEventListener('focus',()=>near(el));
  el.addEventListener('blur',hide);
  el.addEventListener('click',e=>{e.stopPropagation();near(el);});
}
document.addEventListener('click',hide);
document.addEventListener('keydown',e=>{if(e.key==='Escape')hide();});
// focusing an off-screen point scrolls it into view: follow the focused
// target while it is on screen instead of hiding its tooltip
addEventListener('scroll',()=>{const r=cur&&cur===document.activeElement&&cur.getBoundingClientRect();
  if(r&&r.bottom>0&&r.top<innerHeight)near(cur);else hide();},{passive:true});
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
    """Round ticks inside [vmin, vmax]: a 1/2/5 x 10^k step giving about n
    intervals. The bounds may come in either order."""
    vmin, vmax = min(vmin, vmax), max(vmin, vmax)
    span = (vmax - vmin) or abs(vmax) or 1
    raw = span / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw - 1e-12)
    t, out = math.ceil(vmin / step - 1e-9) * step, []
    while t <= vmax + 1e-9:
        out.append(round(t, 10))
        t += step
    return out or [vmin, vmax]


def _tick_labels(ticks) -> list[str]:
    """Labels with just enough decimals for the step, so no two read alike."""
    step = (ticks[1] - ticks[0]) if len(ticks) > 1 else 1
    decimals = 0 if step >= 1 else math.ceil(-math.log10(step) - 1e-9)
    return [f"{t:.{decimals}f}" for t in ticks]


def _tip(text: str) -> str:
    """Attributes for a tooltip target: the same text as data-tip and
    aria-label, and a tab stop so focus (and tap) shows it, not only hover."""
    e = html.escape(text)
    return f' tabindex="0" data-tip="{e}" aria-label="{e}"'


def date_axis(first: str, as_of: str, lo: float, hi: float, max_ticks: int = 4):
    """A linear time axis from `first` to `as_of` mapped onto [lo, hi].

    Returns (x, ticks): x(iso_date) -> coordinate, ticks [(iso_date, x,
    label)] stepped back from `as_of` (always the last tick) by the smallest
    step in TICK_STEPS_DAYS that keeps at most `max_ticks` labels, so labels
    never collide. A single-day range widens to the week ending at `as_of`."""
    d0, d1 = date.fromisoformat(first), date.fromisoformat(as_of)
    if d1 <= d0:
        d0 = d1 - timedelta(days=7)
    span = (d1 - d0).days

    def x(day: str) -> float:
        return lo + (date.fromisoformat(day) - d0).days / span * (hi - lo)

    step = next((s for s in TICK_STEPS_DAYS if span // s + 1 <= max_ticks),
                math.ceil(span / max(max_ticks - 1, 1)))
    fmt = "%m-%d" if span <= 300 else "%Y-%m"
    ticks, d = [], d1
    while d >= d0:
        ticks.append((d.isoformat(), x(d.isoformat()), d.strftime(fmt)))
        d -= timedelta(days=step)
    return x, ticks[::-1]


def _aria(label: str, extra: str) -> str:
    return html.escape(f"{label}: {extra}" if extra else label)


def _chart_role(aria: str) -> str:
    """A chart SVG's role and summary label. role="group", not "img": an img's
    children are presentational, which would hide the focusable, labelled
    tooltip targets inside it from assistive technology."""
    return f' role="group" aria-label="{aria}"'


def dot_line_chart(points, *, as_of=None, label="", unit="", w=470, h=210, refs=(),
                   color="var(--train)"):
    """points: [(iso_date, value, tiptext)] oldest first, placed by date on a
    linear axis that ends at `as_of`. refs: [(value, name)]. The line is not
    drawn across gaps longer than GAP_BREAK_DAYS: a layoff is empty space."""
    if not points:
        return "<p class='d'>no data yet</p>"
    points = sorted(points, key=lambda p: p[0])
    as_of = max(as_of or points[-1][0], points[-1][0])
    pad_l, pad_r, pad_t, pad_b = 48, 38, 24, 28
    values = [v for _, v, _ in points] + [r[0] for r in refs]
    vmin, vmax = min(values), max(values)
    # equal values (one point, or a flat run, possibly negative): pad by 10%
    # of their size either side so the range never inverts
    vpad = (vmax - vmin) * 0.15 or abs(vmax) * 0.1 or 1
    ys = _scale(vmin - vpad, vmax + vpad, h - pad_b, pad_t)
    y_ticks = _y_ticks(vmin - vpad, vmax + vpad)
    xs, ticks = date_axis(points[0][0], as_of, pad_l, w - pad_r)
    aria = _aria(label, f"{len(points)} sessions from {points[0][0]} to {points[-1][0]}, "
                        f"plotted by date through {as_of}")
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%"{_chart_role(aria)}>']
    if unit:
        parts.append(f'<text x="{pad_l}" y="13" class="lab">{html.escape(unit)}</text>')
    for t, text in zip(y_ticks, _tick_labels(y_ticks)):
        y = ys(t)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-6}" y="{y+3.5:.1f}" text-anchor="end">{text}</text>')
    labels, above = [], None  # ref labels go on top of the data; y of the last one above its line
    for rv, rname in sorted(refs, key=lambda r: -r[0]):
        y = ys(rv)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="var(--axis)" stroke-width="1" stroke-dasharray="5 4"/>')
        # two close reference lines: the lower label goes under its line
        ty = y + 16 if above is not None and y - above < 22 else y - 4
        above = y if ty < y else None
        labels.append(f'<text x="{w-pad_r}" y="{ty:.1f}" text-anchor="end" class="lab ref">{html.escape(rname)}</text>')
    for day, tx, text in ticks:
        parts.append(f'<line x1="{tx:.1f}" y1="{h-pad_b}" x2="{tx:.1f}" y2="{h-pad_b+4}" stroke="var(--axis)" stroke-width="1"/>')
        parts.append(f'<text class="xt" data-date="{day}" x="{tx:.1f}" y="{h-6}" text-anchor="middle">{text}</text>')
    runs, prev = [], None
    for day, v, _ in points:
        gap = prev is not None and (date.fromisoformat(day) - date.fromisoformat(prev)).days > GAP_BREAK_DAYS
        if not runs or gap:
            runs.append([])
        runs[-1].append(f"{xs(day):.1f},{ys(v):.1f}")
        prev = day
    for run in runs:
        if len(run) > 1:
            parts.append(f'<polyline points="{" ".join(run)}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
    for day, v, tiptext in points:
        x, y = xs(day), ys(v)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}" stroke="var(--surface)" stroke-width="2"/>')
        parts.append(f'<circle class="hit" cx="{x:.1f}" cy="{y:.1f}" r="11" fill="transparent"{_tip(tiptext)}/>')
    parts.append(f'<line x1="{pad_l}" y1="{h-pad_b}" x2="{w-pad_r}" y2="{h-pad_b}" stroke="var(--axis)" stroke-width="1"/>')
    parts += labels
    parts.append("</svg>")
    return "".join(parts)


def stacked_bar_chart(rows, series, colors, *, label="", unit="min", w=470, h=210):
    """rows: [(iso_week, {series: value}, tip)], contiguous weeks oldest first
    (zero weeks included, so a week off shows as an empty slot); series:
    ordered keys. Each week is one tooltip target, zero weeks too. Week
    labels are thinned back from the newest so they never collide."""
    if not rows:
        return "<p class='d'>no data yet</p>"
    pad_l, pad_r, pad_t, pad_b = 48, 12, 24, 28
    totals = [sum(vals.values()) for _, vals, _ in rows]
    vmax = max(totals) or 1
    ys = _scale(0, vmax * 1.08, h - pad_b, pad_t)
    slot = (w - pad_l - pad_r) / len(rows)
    bw = min(slot * 0.62, 46)
    every = max(1, math.ceil(60 / slot))  # ~60 units per label at phone text size
    aria = _aria(label, f"{len(rows)} weeks, {rows[0][0]} to {rows[-1][0]}")
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%"{_chart_role(aria)}>']
    if unit:
        parts.append(f'<text x="{pad_l}" y="13" class="lab">{html.escape(unit)}</text>')
    y_ticks = _y_ticks(0, vmax)
    for t, text in zip(y_ticks, _tick_labels(y_ticks)):
        y = ys(t)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-pad_r}" y2="{y:.1f}" stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-6}" y="{y+3.5:.1f}" text-anchor="end">{text}</text>')
    baseline_y = h - pad_b
    for i, (week, vals, tiptext) in enumerate(rows):
        x = pad_l + slot * i + (slot - bw) / 2
        cur = baseline_y
        segs = [(k, vals.get(k, 0)) for k in series if vals.get(k, 0) > 0]
        for j, (k, v) in enumerate(segs):
            hgt = baseline_y - ys(v)
            cur -= hgt
            rx = 4 if j == len(segs) - 1 else 0
            parts.append(
                f'<rect x="{x:.1f}" y="{cur:.1f}" width="{bw:.1f}" height="{max(hgt,1):.1f}" '
                f'rx="{rx}" fill="{colors[k]}" stroke="var(--surface)" stroke-width="2"/>')
        parts.append(f'<rect class="hit" data-week="{week}" x="{pad_l + slot * i:.1f}" y="{pad_t}" '
                     f'width="{slot:.1f}" height="{baseline_y - pad_t}" fill="transparent"{_tip(tiptext)}/>')
        if (len(rows) - 1 - i) % every == 0:
            parts.append(f'<text x="{x+bw/2:.1f}" y="{h-6}" text-anchor="middle">{html.escape(week[5:])}</text>')
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

    w, row_h, pad_l, pad_r = 470, 44, 10, 56  # room for phone-size labels
    h = len(rows) * row_h + 30
    vmax = max(r[1] for r in rows) * 1.12
    xs = _scale(0, vmax, pad_l, w - pad_r)
    aria = _aria("VO2max estimates and reference values, ml/kg/min",
                 "; ".join(f"{r[0]} {r[1]:g}" for r in rows))
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%"{_chart_role(aria)}>']
    for t in _y_ticks(0, vmax, 4):
        x = xs(t)
        parts.append(f'<line x1="{x:.1f}" y1="6" x2="{x:.1f}" y2="{h-26}" stroke="var(--grid)" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{h-8}" text-anchor="middle">{t:g}</text>')
    for i, (label, v, note, kind) in enumerate(rows):
        y = i * row_h + 30
        color = "var(--train)" if kind == "you" else "var(--muted)"
        weight = "650" if kind == "you" else "400"
        parts.append(f'<line x1="{xs(0):.1f}" y1="{y}" x2="{xs(v):.1f}" y2="{y}" stroke="{color}" stroke-width="2" opacity="0.45"/>')
        parts.append(f'<circle cx="{xs(v):.1f}" cy="{y}" r="5" fill="{color}" stroke="var(--surface)" stroke-width="2"/>')
        parts.append(f'<circle cx="{xs(v):.1f}" cy="{y}" r="12" fill="transparent"{_tip(label + chr(10) + str(v) + " ml/kg/min — " + note)}/>')
        parts.append(f'<text x="{xs(0):.1f}" y="{y-13}" class="lab" style="font-weight:{weight}">{html.escape(label)}</text>')
        parts.append(f'<text x="{xs(v)+10:.1f}" y="{y+5:.1f}" style="font-weight:{weight}">{v:g}</text>')
    parts.append("</svg>")
    missing = ""
    if you is None:
        missing = ("<p class='d'>Add <code>age</code>, <code>sex</code> and "
                   "<code>weight_kg</code> to config/athlete.yaml to place "
                   "yourself (and your age-group lines) on this scale.</p>")
    return f"""<div class="card"><h2>VO&#8322;max in context</h2>
<div class="d">ml/kg/min — estimates and literature values, not lab tests;
tap, focus or hover a point for its method and caveat</div>
{"".join(parts)}{missing}</div>"""


# ---------------------------------------------------------------- assembly

UNIT = "<span style='font-size:14px'> {}</span>"


def tile(k, v, n=""):
    return (f'<div class="tile"><div class="k">{html.escape(k)}</div>'
            f'<div class="v">{v}</div><div class="n">{html.escape(n)}</div></div>')


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def status_items(facts: dict) -> list[str]:
    """The status band's lines, plain text, restated from the status facts:
    dates, counts and presence only — no advice, no verdicts."""
    items = [f"data through {facts['as_of']}" if facts["as_of"] else "no dated data yet"]
    last = facts["sessions"]["last_structured"]
    if last:
        items.append(f"last structured session: {last['date']}, {last['modality']}, "
                     f"{_plural(facts['sessions']['days_since_last_structured'], 'day')} "
                     "before the as-of date")
    else:
        items.append("last structured session: none")
    c = facts["consistency"]
    if c["weeks_total"]:
        items.append(f"weeks with at least {_plural(c['threshold_sessions'], 'structured session')}: "
                     f"{c['weeks_meeting']} of {c['weeks_total']}, "
                     f"current streak {c['current_streak_weeks']}")
    b = facts["benchmarks"]
    if b["latest"]:
        items.append(f"newest benchmark: {b['latest']['date']} "
                     f"({_plural(b['age_days'], 'day')}; configured cadence {b['cadence_days']} days)")
    else:
        items.append("no benchmarks yet")
    items.append(f"goal: {facts['goal']['track']}" if facts["goal"]["active"] else "goal: none set")
    week = facts["plan"]["current_week"]
    present = "present" if facts["plan"]["exists"] else "none"
    items.append(f"plan for {week}: {present}" if week else "plan: none")
    return items


def status_band(facts: dict) -> str:
    lis = "".join(f"<li>{html.escape(t)}</li>" for t in status_items(facts))
    return (f'<section class="status" aria-labelledby="status-h">'
            f'<h2 id="status-h">Status</h2><ul>{lis}</ul></section>')


def subtitle(has_sessions: bool, lthr, ftp, anchors_note) -> str:
    """'no sessions yet' when the ledger is empty, and the configured
    anchors with the coach's optional anchors_note verbatim. 'Data through'
    lives in the status band."""
    parts = ["Read-only rendering of the training ledger"]
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


def show_recovery(config: dict) -> bool:
    """config/athlete.yaml `dashboard: {show_recovery: true}`; anything else
    (absent, a string, a number) keeps the strip off."""
    block = config.get("dashboard")
    return isinstance(block, dict) and block.get("show_recovery") is True


def recovery_section(recovery: dict) -> str:
    """Resting HR and HRV numbers from the status facts; opt-in (see
    show_recovery). Numbers only: the facts' medians and counts, no reading."""
    def num(v, signed=False):
        if v is None:
            return "—"
        text = f"{v:+.1f}" if signed else f"{v:g}"
        return text

    rhr, hrv = recovery["resting_hr"], recovery["hrv"]
    if not rhr["latest"] and not hrv["latest"]:
        return ('<div class="card full"><h2>Recovery</h2>\n'
                "<p class='d'>no resting HR or HRV data yet</p></div>")
    rows = []
    for name, unit, s, elevated in (("Resting HR", "bpm", rhr, rhr["days_elevated"]),
                                    ("HRV", "ms", hrv, None)):
        latest = (f"{num(s['latest']['value'])} ({s['latest']['date']})"
                  if s["latest"] else "—")
        rows.append(f"<tr><td>{name} ({unit})</td><td>{latest}</td>"
                    f"<td>{num(s['median_7d'])} (n={s['n_7d']})</td>"
                    f"<td>{num(s['median_28d'])} (n={s['n_28d']})</td>"
                    f"<td>{num(s['delta_vs_28d'], signed=True)}</td>"
                    f"<td>{'—' if elevated is None else elevated}</td></tr>")
    thr = rhr["elevated_threshold_bpm"]
    return f"""<div class="card full"><h2>Recovery</h2>
<div class="d">medians over the 7 and 28 days ending at the as-of date; days elevated = consecutive
most-recent resting-HR days at or above the 28-day median + {thr} bpm</div>
<div class="scroll"><table><tr><th>metric</th><th>latest</th><th>7-day median</th>
<th>28-day median</th><th>latest − 28-day</th><th>days elevated</th></tr>{"".join(rows)}</table></div></div>"""


def source_label(kinds) -> str:
    """'Health + Photo' from index.jsonl source_kinds: known kinds in a fixed
    order, unknown kinds as written, duplicates once."""
    kinds = [k for k in (kinds or []) if isinstance(k, str)]
    known = [SOURCE_LABELS[k] for k in SOURCE_LABELS if k in kinds]
    other = sorted({k for k in kinds if k not in SOURCE_LABELS})
    return " + ".join(known + other) or "—"


def sessions_table(index: list[dict], n: int = 12) -> str:
    """The newest `n` index rows. Columns empty ('—') on every listed row are
    dropped; the date column stays visible while the table scrolls sideways."""
    def dec(s):
        if s.get("decoupling_pct") is None:
            return "—"
        return f"{s['decoupling_pct']}" + ("" if s.get("decoupling_method") == "pw_hr" else " (HR)")

    def val(v):
        return "—" if v is None or v == "" else html.escape(str(v))

    columns = [
        ("date", lambda s: s["date"]),
        ("modality", lambda s: html.escape(str(s.get("modality")))),
        ("dur", lambda s: f"{round((s.get('duration_s') or 0) / 60)} min"),
        ("HR", lambda s: val(s.get("hr_avg") or None)),
        ("watts", lambda s: val(s.get("watts_avg") or None)),
        ("EF", lambda s: val(s.get("efficiency_factor") or None)),
        ("dec %", dec),
        ("score", lambda s: val(s.get("compliance_score"))),
        ("source", lambda s: source_label(s.get("source_kinds"))),
    ]
    rows = sorted(index, key=lambda s: (s["date"], str(s.get("start") or "")), reverse=True)[:n]
    cells = [[fn(s) for _, fn in columns] for s in rows]
    keep = [i for i in range(len(columns)) if any(c[i] != "—" for c in cells)]
    head = "".join(f"<th>{columns[i][0]}</th>" for i in keep)
    body = "".join("<tr>" + "".join(f"<td>{c[i]}</td>" for i in keep) + "</tr>" for c in cells)
    notes = ["newest first; source = where the row's data came from"]
    if "dec %" in [columns[i][0] for i in keep]:
        notes.append("dec % = power:HR decoupling, (HR) = heart-rate drift with no power trace")
    return (f'<div class="d">{"; ".join(notes)}</div>\n'
            f'<div class="scroll nowrap" role="region" aria-label="Recent sessions table" tabindex="0">'
            f"<table><tr>{head}</tr>{body}</table></div>")


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
    unstructured = list(facts_lib.thresholds(config)["unstructured_modalities"] or [])
    bands, zones_source = compute_metrics.zone_bounds(config)
    z2 = None
    if zones_source == "lthr" and "z2" in bands:
        # whole bpm inside [lo, hi): the resolved, contiguous band
        z2_lo, z2_hi = bands["z2"]
        z2 = f"{math.ceil(z2_lo)}–{math.ceil(z2_hi) - 1}"
    as_of = facts["as_of"]  # newest date in the data, never the clock
    weeks = facts["weeks"][-MAX_WEEKS:]  # contiguous, zero-filled, oldest first

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
        # metrics usually run ahead of workout exports. Structured sessions
        # only; unstructured modalities count toward Baseline instead.
        last_session = max(s["date"] for s in index)
        last7 = [s for s in index if s["date"] > _shift(last_session, -7)
                 and s.get("modality") not in unstructured]
        train_min = round(sum(s.get("duration_s") or 0 for s in last7) / 60)
        tiles.append(tile("Training, last 7 days", f"{train_min}{UNIT.format('min')}",
                          f"{_plural(len(last7), 'structured session')}, 7 days to {last_session}"))
        # the as-of week, the Baseline chart's last bar: baseline minutes come
        # from the same health export as the daily metrics, so they keep pace
        # with as_of even when workout exports lag
        this_week = iso_week(as_of)
        base_rows_wk = [b for b in baseline if b.get("week") == this_week]
        logged = [s for s in index if s.get("modality") in unstructured
                  and iso_week(s["date"]) == this_week]
        base_min = round(sum(b.get("minutes") or 0 for b in base_rows_wk)) + round(
            sum(s.get("duration_s") or 0 for s in logged) / 60)
        count = sum(b.get("count") or 0 for b in base_rows_wk) + len(logged)
        tiles.append(tile("Baseline this week", f"{base_min}{UNIT.format('min')}",
                          f"{count} {'activity' if count == 1 else 'activities'}, "
                          f"week {this_week}" if count
                          else f"no baseline activity in week {this_week}"))
    tiles_html = f'<div class="tiles">{"".join(tiles)}</div>' if tiles else ""

    session_cards = session_charts(index, tiz, weeks, as_of, unstructured, lthr, ftp,
                                   ceiling, zones_source, athlete.get("hr_max")) if index else ""

    # Baseline: the short-walk rollup plus logged unstructured sessions, per
    # week; the only place walks appear.
    base_rows = []
    for wk in baseline_weeks(facts, baseline):
        logged = sum(wk["by_modality_min"].get(m, 0) for m in unstructured)
        total = wk["baseline_min"] + logged
        base_rows.append((wk["week"], {"m": total},
                          f"{wk['week']}  {total} min\nrollup {wk['baseline_min']} min, "
                          f"logged {logged} min"))
    if any(r[1]["m"] for r in base_rows):
        base_chart = stacked_bar_chart(base_rows, ["m"], {"m": "var(--base)"},
                                       label="Baseline minutes per ISO week")
    elif any(b.get("minutes") for b in baseline) or any(
            s.get("modality") in unstructured for s in index):
        # activity exists, all of it older than the weeks shown
        base_chart = (f"<p class='d'>no baseline activity in the {len(base_rows)} weeks "
                      f"to {base_rows[-1][0]}</p>" if base_rows
                      else "<p class='d'>no baseline activity yet</p>")
    else:
        base_chart = "<p class='d'>no baseline activity yet</p>"
    unstructured_text = ", ".join(unstructured) or "none configured"

    def _clip(text, n=100):
        return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"

    bench_rows = "".join(
        f"<tr><td>{b['date']}</td><td>{html.escape(b['test'])}</td>"
        f"<td>{html.escape(_clip(b['result'])) or '—'}</td></tr>" for b in bench)
    bench_html = (f"<div class='scroll'><table><tr><th>date</th><th>test</th><th>result</th></tr>"
                  f"{bench_rows}</table></div>"
                  if bench else "<p class='d'>no benchmarks yet</p>")
    sessions_html = sessions_table(index) if index else "<p class='d'>no sessions yet</p>"
    recovery_html = recovery_section(facts["recovery"]) if show_recovery(config) else ""

    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cardio Coach</title>
<style>{CSS}</style>
<div class="wrap">
<h1>Cardio Coach</h1>
<p class="sub">{subtitle(bool(index), lthr, ftp, athlete.get("anchors_note"))}</p>
{status_band(facts)}
{tiles_html}
<div class="grid">
{recovery_html}
{session_cards}
<div class="card"><h2>Baseline activity</h2>
<div class="d">unstructured movement — the short-walk rollup plus logged sessions of
{html.escape(unstructured_text)}; minutes per ISO week, tracked, never scored</div>
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


def baseline_weeks(facts: dict, baseline: list[dict], n: int = MAX_WEEKS) -> list[dict]:
    """The Baseline chart's weeks: contiguous and zero-filled, ending at the
    as-of week, the most recent `n`. They start at the earlier of the facts'
    first week (the first session) and the earliest baseline.jsonl week, so
    walks from before the first session (a Health export with months of
    history) still show. Facts weeks are used as they are; earlier weeks get
    their baseline minutes by the facts' rule (rollup weeks whose Monday is
    <= as_of) and no logged sessions."""
    if not facts["as_of"]:
        return []
    as_of = date.fromisoformat(facts["as_of"])
    rollup: dict[str, float] = {}
    for b in baseline:
        monday = facts_lib.week_monday(b.get("week"))
        if monday and monday <= as_of:
            rollup[b["week"]] = rollup.get(b["week"], 0) + (b.get("minutes") or 0)
    by_week = {w["week"]: w for w in facts["weeks"]}
    mondays = [facts_lib.week_monday(w) for w in list(rollup) + list(by_week)]
    d = max(min(mondays, default=as_of), as_of - timedelta(weeks=n - 1))
    d -= timedelta(days=d.weekday())
    out = []
    while d <= as_of:
        week = facts_lib.iso_week(d)
        out.append(by_week.get(week) or {"week": week, "baseline_min": round(rollup.get(week, 0)),
                                         "by_modality_min": {}})
        d += timedelta(days=7)
    return out[-n:]


def session_charts(index, tiz, weeks, as_of, unstructured, lthr, ftp, ceiling,
                   zones_source, hr_max) -> str:
    """The per-session chart cards (efficiency, watts, zones, decoupling);
    only rendered when the ledger has sessions. Per-session charts are placed
    by date through `as_of`; the zone chart uses the facts' `weeks`."""
    rides = [s for s in index if s["modality"] == "bikeerg" and s.get("efficiency_factor")]
    ef_pts = [(s["date"], s["efficiency_factor"],
               f"{s['date']}  EF {s['efficiency_factor']}\n{s['watts_avg']} W @ {s['hr_avg']} bpm")
              for s in rides]
    watt_pts = [(s["date"], s["watts_avg"],
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
        return [(s["date"], s["decoupling_pct"],
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
                      + dot_line_chart(pw_pts, as_of=as_of, unit="%",
                                       label="Power:HR decoupling per session, percent",
                                       refs=[(5, "5%")]) + "</div>")
    if drift_pts or not pw_pts:
        dec_cards += ('<div class="card"><h2>HR drift per session</h2>\n'
                      '<div class="d">second-half vs first-half heart rate after the warm-up — '
                      'true power:HR decoupling needs a power trace</div>\n'
                      + dot_line_chart(drift_pts, as_of=as_of, unit="%",
                                       label="Heart-rate drift per session, percent")
                      + "</div>")

    # weekly zone minutes: structured sessions only, on the facts' weeks
    zones = ["z1", "z2", "z3", "z4", "z5"]
    by_week: dict[str, dict] = {}
    for s in index:
        z = tiz.get(s["id"])
        if not z or s.get("modality") in unstructured:
            continue
        wk = by_week.setdefault(iso_week(s["date"]), {k: 0 for k in zones})
        for k in zones:
            wk[k] += (z.get(k) or 0) / 60
    zone_rows = []
    for w in weeks:
        vals = by_week.get(w["week"], {k: 0 for k in zones})
        parts = "  ".join(f"{k} {round(vals[k])}m" for k in zones if vals[k] >= 1)
        zone_rows.append((w["week"], {k: round(v) for k, v in vals.items()},
                          f"{w['week']}  {parts or 'no zone minutes'}"))
    has_zones = any(sum(r[1].values()) for r in zone_rows)
    zone_colors = {z: f"var(--{z})" for z in zones}
    zone_legend = "".join(
        f'<span><span class="sw" style="background:var(--{z})"></span>{z}</span>' for z in zones)
    zone_legend = f'\n<div class="legend">{zone_legend}</div>' if has_zones else ""
    if has_zones:
        zone_chart = stacked_bar_chart(zone_rows, zones, zone_colors,
                                       label="HR minutes in zone per ISO week, structured sessions")
    elif by_week and zone_rows:  # zone data exists, all of it older than the weeks shown
        zone_chart = (f"<p class='d'>no zone minutes in the {len(zone_rows)} weeks "
                      f"to {zone_rows[-1][0]}</p>")
    else:
        zone_chart = "<p class='d'>no data yet</p>"
    zones_from = {"lthr": f" (zones from LTHR {lthr})",
                  "bootstrap": f" (bootstrap zones from HRmax {hr_max})"}.get(zones_source, "")
    excluded = ", ".join(unstructured)
    excluded = f"; {excluded} minutes are in Baseline" if excluded else ""

    return f"""<div class="card"><h2>Efficiency factor — BikeErg</h2>
<div class="d">avg watts ÷ avg HR per ride; rising = same effort, more output</div>
{dot_line_chart(ef_pts, as_of=as_of, unit="W/bpm", label="Efficiency factor per BikeErg ride")}</div>
<div class="card"><h2>Avg watts per ride — BikeErg</h2>
<div class="d">{watt_desc}</div>
{dot_line_chart(watt_pts, as_of=as_of, unit="W", refs=watt_refs,
                label="Average watts per BikeErg ride")}</div>
<div class="card"><h2>Weekly minutes in zone</h2>
<div class="d">HR time-in-zone, structured sessions only{excluded}{zones_from}</div>
{zone_chart}{zone_legend}</div>
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
