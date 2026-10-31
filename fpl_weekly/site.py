"""Builds the designed web page (GitHub Pages) from a Report.

Output layout (inside site/):
    index.html          latest gameweek
    gw/<n>.html         one page per gameweek (the archive)
    fonts/              put the New Hero .woff2 files here (see README)
"""

import html
import re
from datetime import datetime, timezone
from pathlib import Path

FONT_FILES = [  # (file name, weight, style) - any that exist in site/fonts are used
    ("NewHero-Regular.woff2", 400, "normal"),
    ("NewHero-Medium.woff2", 500, "normal"),
    ("NewHero-Bold.woff2", 700, "normal"),
    ("NewHero-ExtraBold.woff2", 800, "normal"),
    ("NewHero-Black.woff2", 900, "normal"),
]

CSS = """
:root{
  --paper:#f4f3ee; --surface:#ffffff; --ink:#0f1118; --muted:#6b6f7b; --line:#e4e2da;
  --accent:#c8f03c; --accent-ink:#0f1118; --up:#0f8a4f; --down:#c2412d; --bar:#d9d7cf;
  --font:"New Hero","Montserrat",system-ui,-apple-system,"Segoe UI",sans-serif;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#0d0f15; --surface:#161922; --ink:#eeede8; --muted:#9a9eaa; --line:#262a35;
    --accent:#c8f03c; --accent-ink:#0f1118; --up:#4cc98a; --down:#ff7a63; --bar:#2b303c;
  }
}
:root[data-theme="dark"]{
  --paper:#0d0f15; --surface:#161922; --ink:#eeede8; --muted:#9a9eaa; --line:#262a35;
  --accent:#c8f03c; --accent-ink:#0f1118; --up:#4cc98a; --down:#ff7a63; --bar:#2b303c;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--font);
  font-size:16px;line-height:1.55;font-feature-settings:"tnum" 1}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
header.top{border-bottom:1px solid var(--line)}
header.top .wrap{display:flex;justify-content:space-between;align-items:center;gap:12px;
  padding-top:14px;padding-bottom:14px;font-size:13px;font-weight:700;letter-spacing:.12em;
  text-transform:uppercase}
header.top .gw{background:var(--ink);color:var(--paper);padding:4px 10px;border-radius:999px;
  letter-spacing:.08em;white-space:nowrap}
.hero{padding:48px 0 28px}
.hero h1{font-size:clamp(2.1rem,6.2vw,4.4rem);line-height:1.02;letter-spacing:-.025em;
  font-weight:800;margin:0 0 20px;max-width:16ch;text-wrap:balance}
.hero p{font-size:clamp(1.05rem,2.2vw,1.25rem);max-width:60ch;margin:0;color:var(--ink);opacity:.86}
.hero .date{margin-top:18px;font-size:13px;color:var(--muted);font-weight:500}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:16px;overflow:hidden;margin:8px 0 40px}
.tile{background:var(--surface);padding:18px 20px}
.tile .k{font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.tile .v{font-size:1.35rem;font-weight:800;margin-top:4px;line-height:1.25}
.tile:first-child{background:var(--accent);color:var(--accent-ink)}
.tile:first-child .k{color:var(--accent-ink);opacity:.7}
section.block{background:var(--surface);border:1px solid var(--line);border-radius:16px;
  padding:22px 22px 18px;margin-bottom:20px;min-width:0}
section.block h2{font-size:1.3rem;font-weight:800;letter-spacing:-.01em;margin:0 0 6px}
section.block p{margin:6px 0 0;color:var(--ink);opacity:.86}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:20px;margin-bottom:20px}
.grid section.block{margin-bottom:0}
.table{width:100%;border-collapse:collapse;margin-top:14px;font-size:15px}
.table th{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);
  text-align:left;padding:0 8px 8px;border-bottom:2px solid var(--ink)}
.table td{padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
.table tr:last-child td{border-bottom:0}
.table .r{text-align:right}.table .c{text-align:center}
.table td.pos{font-weight:800;width:2.5em}
.table tr.lead td{background:color-mix(in srgb,var(--accent) 35%,transparent)}
.table .mv{font-size:13px;font-weight:700;white-space:nowrap}
.mv.up{color:var(--up)}.mv.down{color:var(--down)}.mv.same{color:var(--muted)}
.team{color:var(--muted);font-size:14px}
.score{display:inline-block;background:var(--ink);color:var(--paper);font-weight:800;border-radius:8px;
  padding:3px 10px;font-size:14px;white-space:nowrap}
.scroll{overflow-x:auto}
.chart{margin-top:16px;position:relative}
.bar-row{display:grid;grid-template-columns:minmax(80px,140px) 1fr 2.6em;align-items:center;gap:10px;
  font-size:14px;margin:5px 0}
.bar-row .n{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar-track{position:relative;height:14px}
.bar{height:100%;background:var(--bar);border-radius:0 7px 7px 0}
.bar-row.top .bar{background:var(--accent)}
.bar-row.bottom .bar{background:var(--down);opacity:.7}
.bar-row.top .n,.bar-row.top .val{font-weight:800}
.bar-row .val{text-align:right;font-weight:600}
.bar-track[style]::after{content:"";position:absolute;left:var(--avg);top:-4px;bottom:-4px;
  border-left:2px dashed var(--muted)}
.avg-label{font-size:12px;color:var(--muted);margin-top:8px}
ol.notes{list-style:none;counter-reset:n;padding:0;margin:14px 0 0}
ol.notes li{counter-increment:n;display:grid;grid-template-columns:2.2em 1fr;gap:8px;padding:10px 0;
  border-bottom:1px solid var(--line)}
ol.notes li:last-child{border-bottom:0}
ol.notes li::before{content:counter(n,decimal-leading-zero);font-weight:800;color:var(--muted)}
footer{padding:28px 0 48px;color:var(--muted);font-size:14px}
.archive{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 18px}
.archive a{color:var(--ink);text-decoration:none;border:1px solid var(--line);background:var(--surface);
  padding:5px 12px;border-radius:999px;font-weight:700;font-size:13px}
.archive a.cur{background:var(--ink);color:var(--paper);border-color:var(--ink)}
@media (max-width:560px){
  .hero{padding:32px 0 20px}
  section.block{padding:18px 14px 12px}
  .table{font-size:14px}.table td,.table th{padding-left:5px;padding-right:5px}
  .hide-sm{display:none}
}
"""


def _inline(text):
    """Escape, then allow **bold** from the report text."""
    text = html.escape(str(text))
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _cell_class(i, align):
    a = (align or [])[i] if align and i < len(align) else "left"
    return {"right": "r", "center": "c"}.get(a, "")


def _movement(text):
    cls = "up" if text.startswith("▲") else "down" if text.startswith("▼") else "same"
    return f'<span class="mv {cls}">{html.escape(text)}</span>'


def _table(t, kind=""):
    head = ""
    if t.headers:
        cells = []
        for i, h in enumerate(t.headers):
            extra = " hide-sm" if h == "Team" else ""
            cells.append(f'<th class="{_cell_class(i, t.align)}{extra}">{html.escape(h)}</th>')
        head = "<thead><tr>" + "".join(cells) + "</tr></thead>"
    rows = []
    for r_i, row in enumerate(t.rows):
        cells = []
        for i, cell in enumerate(row):
            header = t.headers[i] if t.headers and i < len(t.headers) else ""
            cls = _cell_class(i, t.align)
            if header == "+/-":
                inner = _movement(cell)
            elif header == "Score":
                inner = f'<span class="score">{html.escape(cell)}</span>'
            elif header == "Team":
                inner = f'<span class="team">{_inline(cell)}</span>'
                cls += " hide-sm"
            else:
                inner = _inline(cell)
            if header == "Pos":
                cls += " pos"
            cells.append(f'<td class="{cls.strip()}">{inner}</td>')
        lead = ' class="lead"' if t.headers and t.headers[0] == "Pos" and row[0] == "1" else ""
        rows.append(f"<tr{lead}>" + "".join(cells) + "</tr>")
    return f'<div class="scroll"><table class="table">{head}<tbody>{"".join(rows)}</tbody></table></div>'


def _chart(section):
    data = section.chart
    hi = max(max(v for _n, v, _t in data), 1)
    lo = min(0, min(v for _n, v, _t in data))
    span = hi - lo or 1
    avg_pos = ""
    if section.chart_avg is not None:
        avg_pos = f' style="--avg:{(section.chart_avg - lo) / span * 100:.1f}%"'
    rows = []
    for name, value, tag in data:
        width = (value - lo) / span * 100
        rows.append(f'<div class="bar-row {tag}"><span class="n">{html.escape(name)}</span>'
                    f'<div class="bar-track"{avg_pos}><div class="bar" style="width:{width:.1f}%"></div></div>'
                    f'<span class="val">{value}</span></div>')
    avg = ""
    if section.chart_avg is not None:
        avg = f'<div class="avg-label">Dashed line: league average ({section.chart_avg})</div>'
    return f'<div class="chart">{"".join(rows)}</div>{avg}'


def _section(s, wide=False):
    parts = [f"<h2>{html.escape(s.title)}</h2>"]
    parts += [f"<p>{_inline(p)}</p>" for p in s.paragraphs]
    if s.chart:
        parts.append(_chart(s))
    if s.table and s.table.headers and "Score" in s.table.headers and s.full_table:
        parts.append(_table(s.table))     # results first, then the standings
    table = s.full_table or s.table
    if table and table.headers:
        parts.append(_table(table))
    if s.bullets:
        parts.append('<ol class="notes">' + "".join(f"<li><span>{_inline(b)}</span></li>"
                                                     for b in s.bullets) + "</ol>")
    return f'<section class="block">{"".join(parts)}</section>'


def _font_css(site_dir, prefix):
    rules = []
    for name, weight, style in FONT_FILES:
        if (site_dir / "fonts" / name).exists():
            rules.append(f'@font-face{{font-family:"New Hero";src:url("{prefix}fonts/{name}") format("woff2");'
                         f"font-weight:{weight};font-style:{style};font-display:swap}}")
    return "\n".join(rules)


def render_page(report, site_dir, prefix, archive):
    week = report.sections[0] if report.sections else None
    tiles = ""
    if week and week.table and not week.table.headers:
        tiles = '<div class="tiles">' + "".join(
            f'<div class="tile"><div class="k">{html.escape(k)}</div><div class="v">{_inline(v)}</div></div>'
            for k, v in week.table.rows) + "</div>"
    rest = report.sections[1:] if tiles else report.sections

    blocks = []
    pair = []
    for s in rest:
        if s.chart or (s.full_table and len(s.full_table.rows) > 8) or s.bullets:
            if pair:
                blocks.append('<div class="grid">' + "".join(pair) + "</div>")
                pair = []
            blocks.append(_section(s))
        else:
            pair.append(_section(s))
    if pair:
        blocks.append('<div class="grid">' + "".join(pair) + "</div>")
    if week and week.chart:
        chart_section = type(week)(f"Gameweek {report.gameweek} scores", chart=week.chart,
                                   chart_avg=week.chart_avg)
        blocks.insert(0, _section(chart_section))

    links = "".join(
        f'<a class="{"cur" if gw == report.gameweek else ""}" href="{prefix}gw/{gw}.html">GW{gw}</a>'
        for gw in sorted(archive, reverse=True))
    date = datetime.now(timezone.utc).strftime("%-d %B %Y")
    title = f"{report.league_name}: Gameweek {report.gameweek}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(report.headline)}">
<meta property="og:title" content="{html.escape(report.headline)}">
<meta property="og:description" content="{html.escape(report.standfirst)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
{_font_css(site_dir, prefix)}
{CSS}
</style>
</head>
<body>
<header class="top"><div class="wrap"><span>{html.escape(report.league_name)}</span>
<span class="gw">Gameweek {report.gameweek}</span></div></header>
<main class="wrap">
<div class="hero">
<h1>{html.escape(report.headline)}</h1>
<p>{_inline(report.standfirst)}</p>
<div class="date">Published {date}</div>
</div>
{tiles}
{"".join(blocks)}
</main>
<footer><div class="wrap">
<strong>Previous weeks</strong>
<div class="archive">{links}</div>
Data from the official Fantasy Premier League game. Updated automatically after each gameweek.
</div></footer>
</body>
</html>
"""


def write_site(report, site_dir):
    site_dir = Path(site_dir)
    (site_dir / "gw").mkdir(parents=True, exist_ok=True)
    (site_dir / "fonts").mkdir(exist_ok=True)
    (site_dir / ".nojekyll").write_text("")
    archive = {int(p.stem) for p in (site_dir / "gw").glob("*.html") if p.stem.isdigit()}
    archive.add(report.gameweek)
    (site_dir / "gw" / f"{report.gameweek}.html").write_text(
        render_page(report, site_dir, "../", archive), encoding="utf-8")
    if report.gameweek >= max(archive):
        (site_dir / "index.html").write_text(render_page(report, site_dir, "", archive), encoding="utf-8")
    return site_dir / "gw" / f"{report.gameweek}.html"
