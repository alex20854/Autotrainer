#!/usr/bin/env python3
"""Render dashboard.html — a read-only view of the engine's files (spec §2).

Pure rendering, no logic or state of its own: reads index.jsonl,
baseline.jsonl, session frontmatter, config/athlete.yaml and benchmarks.md,
writes one self-contained HTML file (inline CSS/SVG, a few lines of inline JS
for tooltips, no external requests). Deterministic: same inputs -> same file;
the "data through" stamp derives from the data, not the clock.

Usage: python3 scripts/build_dashboard.py
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import frontmatter, records

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = REPO_ROOT / "dashboard.html"

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

def load_data():
    index = [json.loads(l) for l in (REPO_ROOT / "data" / "index.jsonl").open()] \
        if (REPO_ROOT / "data" / "index.jsonl").exists() else []
    baseline = [json.loads(l) for l in (REPO_ROOT / "data" / "baseline.jsonl").open()] \
        if (REPO_ROOT / "data" / "baseline.jsonl").exists() else []
    config = yaml.safe_load((REPO_ROOT / "config" / "athlete.yaml").read_text())
    tiz = {}
    for s in index:
        fm, _ = frontmatter.load(REPO_ROOT / s["file"])
        z = (fm.get("computed") or {}).get("time_in_zone")
        if z:
            tiz[s["id"]] = z
    bench = []
    btext = (REPO_ROOT / "benchmarks.md").read_text() if (REPO_ROOT / "benchmarks.md").exists() else ""
    for m in re.finditer(r"^### (\d{4}-\d{2}-\d{2}) — (.+)$\n- Result: (.+)$",
                         btext, re.MULTILINE):
        bench.append({"date": m.group(1), "test": m.group(2),
                      "result": re.sub(r"[*`]", "", m.group(3))})
    return index, baseline, config, tiz, bench


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


# ---------------------------------------------------------------- assembly

def tile(k, v, n=""):
    return (f'<div class="tile"><div class="k">{html.escape(k)}</div>'
            f'<div class="v">{v}</div><div class="n">{html.escape(n)}</div></div>')


def build() -> str:
    index, baseline, config, tiz, bench = load_data()
    athlete = config.get("athlete") or {}
    power = (config.get("power") or {}).get("bikeerg") or {}
    lthr, ftp = athlete.get("lthr"), power.get("ftp")
    ceiling = power.get("z2_watts_ceiling")
    z2 = f"{round(lthr*0.85)}–{round(lthr*0.89)}" if lthr else "—"
    data_through = max((s["date"] for s in index), default="—")

    last7 = [s for s in index if s["date"] > _shift(data_through, -7)]
    train_min = round(sum(s["duration_s"] or 0 for s in last7) / 60)
    this_week = iso_week(data_through) if index else ""
    base_week = next((b for b in baseline if b["week"] == this_week), None)

    tiles = "".join([
        tile("FTP (BikeErg)", f"{ftp or '—'}<span style='font-size:14px'> W</span>", "conservative floor"),
        tile("LTHR", f"{lthr or '—'}<span style='font-size:14px'> bpm</span>", "field test 08-11"),
        tile("Zone 2", f"{z2}<span style='font-size:14px'> bpm</span>", f"≤{ceiling} W on the BikeErg"),
        tile("Training, last 7 days", f"{train_min}<span style='font-size:14px'> min</span>",
             f"{len(last7)} sessions"),
        tile("Baseline this week", f"{(base_week or {}).get('minutes','—')}<span style='font-size:14px'> min</span>",
             f"{base_week['count']} walks" if base_week else "no short walks this week"),
    ])

    rides = [s for s in index if s["modality"] == "bikeerg" and s.get("efficiency_factor")]
    ef_pts = [(s["date"][5:], s["efficiency_factor"],
               f"{s['date']}  EF {s['efficiency_factor']}\n{s['watts_avg']} W @ {s['hr_avg']} bpm")
              for s in rides]
    watt_pts = [(s["date"][5:], s["watts_avg"],
                 f"{s['date']}  {s['watts_avg']} W avg\n{round((s['duration_s'] or 0)/60)} min")
                for s in index if s["modality"] == "bikeerg" and s.get("watts_avg")]
    dec_pts = [(s["date"][5:], s["decoupling_pct"],
                f"{s['date']}  {s['decoupling_pct']}% decoupling\n{s['modality']}, "
                f"{round((s['duration_s'] or 0)/60)} min")
               for s in index if s.get("decoupling_pct") is not None
               and s["modality"] not in ("walk",)]

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

    base_rows = [(b["week"][5:], {"m": b["minutes"]},
                  f"{b['week']}  {b['minutes']} min, {b['count']} walks")
                 for b in baseline]

    sess_rows = "".join(
        f"<tr><td>{s['date']}</td><td>{s['modality']}</td>"
        f"<td>{round((s['duration_s'] or 0)/60)} min</td>"
        f"<td>{s['hr_avg'] or '—'}</td><td>{s['watts_avg'] or '—'}</td>"
        f"<td>{s['efficiency_factor'] or '—'}</td>"
        f"<td>{s['decoupling_pct'] if s['decoupling_pct'] is not None else '—'}</td>"
        f"<td>{s['compliance_score'] if s['compliance_score'] is not None else '—'}</td></tr>"
        for s in sorted(index, key=lambda s: s["date"], reverse=True)[:12])
    def _clip(text, n=100):
        return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"

    bench_rows = "".join(
        f"<tr><td>{b['date']}</td><td>{html.escape(b['test'])}</td>"
        f"<td>{html.escape(_clip(b['result']))}</td></tr>" for b in bench)

    return f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cardio Coach</title>
<style>{CSS}</style>
<div class="wrap">
<h1>Cardio Coach</h1>
<p class="sub">Read-only rendering of the training ledger · data through {data_through}
 · anchors: LTHR {lthr or '—'}, FTP {ftp or '—'} W (floors, re-test pending)</p>
<div class="tiles">{tiles}</div>
<div class="grid">
<div class="card"><h2>Efficiency factor — BikeErg</h2>
<div class="d">avg watts ÷ avg HR per ride; rising = same effort, more output</div>
{dot_line_chart(ef_pts, y_label="Efficiency factor")}</div>
<div class="card"><h2>Avg watts per ride — BikeErg</h2>
<div class="d">against the Zone 2 ceiling and current FTP floor</div>
{dot_line_chart(watt_pts, fmt="{:.0f}", refs=[(ceiling, f"z2 ceiling {ceiling}W"), (ftp, f"FTP {ftp}W")] if ftp else [])}</div>
<div class="card"><h2>Weekly minutes in zone</h2>
<div class="d">HR time-in-zone across training sessions (zones from LTHR {lthr or "—"})</div>
{stacked_bar_chart(zone_rows, zones, zone_colors)}
<div class="legend">{zone_legend}</div></div>
<div class="card"><h2>Aerobic decoupling per session</h2>
<div class="d">under 5% = solid aerobic durability for that duration</div>
{dot_line_chart(dec_pts, fmt="{:.0f}", refs=[(5, "5%")])}</div>
<div class="card"><h2>Baseline activity</h2>
<div class="d">unstructured movement (walks) — tracked, never scored</div>
{stacked_bar_chart(base_rows, ["m"], {"m": "var(--base)"})}</div>
<div class="card"><h2>Benchmarks</h2>
<table><tr><th>date</th><th>test</th><th>result</th></tr>{bench_rows}</table></div>
<div class="card full"><h2>Recent sessions</h2>
<table><tr><th>date</th><th>modality</th><th>dur</th><th>HR</th><th>watts</th>
<th>EF</th><th>dec %</th><th>score</th></tr>{sess_rows}</table></div>
</div>
<p class="foot">Generated by scripts/build_dashboard.py — a pure rendering of
data/index.jsonl, data/baseline.jsonl, config/athlete.yaml and benchmarks.md.
Regenerated on every ingest; edit those files, never this one.</p>
</div>
<script>{JS}</script>
"""


def _shift(date: str, days: int) -> str:
    from datetime import date as d, timedelta
    return (d.fromisoformat(date) + timedelta(days=days)).isoformat() if date != "—" else date


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", type=Path, default=None,
                    help="also write an artifact-ready copy (no doctype — the "
                         "claude.ai artifact wrapper supplies the document shell)")
    args = ap.parse_args()
    doc = build()
    OUT_PATH.write_text(doc, encoding="utf-8")
    print(f"dashboard.html rendered ({OUT_PATH.stat().st_size // 1024} KB)")
    if args.artifact:
        args.artifact.write_text(doc.replace("<!doctype html>\n", "", 1), encoding="utf-8")
        print(f"artifact copy -> {args.artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
