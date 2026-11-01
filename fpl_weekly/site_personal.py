"""HTML for the 'Your personal report' drop-down on the web page."""

import html

CSS = """
.me-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px}
.me-head h2{margin:0}
.me-select{appearance:none;-webkit-appearance:none;background:var(--surface-2);color:var(--ink);
  border:1px solid var(--line);border-radius:999px;padding:10px 40px 10px 16px;font:inherit;font-weight:700;
  min-width:min(100%,260px);cursor:pointer;
  background-image:linear-gradient(45deg,transparent 50%,var(--accent) 50%),linear-gradient(135deg,var(--accent) 50%,transparent 50%);
  background-position:calc(100% - 20px) 50%,calc(100% - 14px) 50%;background-size:6px 6px;background-repeat:no-repeat}
.me-select:focus{outline:2px solid var(--accent);outline-offset:2px}
.me-empty{color:var(--muted);margin-top:12px}
.me-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:14px;margin-top:16px}
.me-card{background:var(--surface-2);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}
.me-card h3{margin:0 0 10px;font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.me-wide{grid-column:1/-1}
.arrow{display:flex;align-items:center;gap:14px}
.arrow .dot{flex:none;width:52px;height:52px;border-radius:50%;display:grid;place-items:center;font-size:22px;font-weight:900}
.arrow.up .dot{background:var(--up);color:#06110a}.arrow.down .dot{background:var(--down);color:#16060a}
.arrow.flat .dot{background:var(--line);color:var(--ink)}
.arrow .big{font-size:1.35rem;font-weight:800;line-height:1.2}
.arrow.up .big{color:var(--up)}.arrow.down .big{color:var(--down)}
.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px}
.kpi .v{font-size:1.5rem;font-weight:800;line-height:1.1}.kpi .k{font-size:12px;color:var(--muted)}
.cbar{display:grid;grid-template-columns:minmax(90px,42%) 1fr 2.6em;gap:8px;align-items:center;font-size:13.5px;margin:6px 0}
.cbar .t{height:10px;background:var(--bar);border-radius:6px;overflow:hidden}
.cbar .f{height:100%;background:var(--muted)}.cbar.you .f{background:var(--accent)}
.cbar .n{line-height:1.25}.cbar .v{text-align:right;font-weight:700}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.pchip{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:8px 10px;min-width:96px}
.pchip .pn{font-weight:700;font-size:14px}.pchip .pp{font-size:1.15rem;font-weight:800}
.pchip .ps{font-size:12px;color:var(--muted)}
.pchip.good .pp{color:var(--up)}.pchip.bad .pp{color:var(--down)}
.me-list{list-style:none;padding:0;margin:0}.me-list li{padding:6px 0;border-bottom:1px solid var(--line);font-size:14.5px}
.me-list li:last-child{border-bottom:0}
.spark{display:flex;align-items:flex-end;gap:4px;height:110px;margin-top:6px;position:relative}
.spark .col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;min-width:0}
.spark .bw{flex:1;width:100%;max-width:26px;position:relative;display:flex;align-items:flex-end}
.spark .b{width:100%;background:var(--bar);border-radius:4px 4px 0 0}
.spark .b.above{background:var(--accent)}
.spark .bw i{position:absolute;left:-3px;right:-3px;border-top:2px dashed var(--ink);opacity:.6}
.spark .g{font-size:10.5px;color:var(--muted);margin-top:4px}
.me-note{font-size:12.5px;color:var(--muted);margin-top:8px}
"""

JS = """
<script>
(function(){
  var sel=document.getElementById('me-select'); if(!sel) return;
  function show(id){
    document.querySelectorAll('.me-report').forEach(function(el){el.hidden = el.dataset.entry!==id;});
    var empty=document.querySelector('.me-empty'); if(empty) empty.hidden = !!id;
    sel.value=id||'';
  }
  sel.addEventListener('change',function(){
    show(sel.value);
    try{localStorage.setItem('fpl-me',sel.value);}catch(e){}
    try{history.replaceState(null,'',sel.value?('#me-'+sel.value):location.pathname);}catch(e){}
  });
  var start='';
  var m=location.hash.match(/^#me-(\\d+)/); if(m) start=m[1];
  if(!start){try{start=localStorage.getItem('fpl-me')||'';}catch(e){}}
  if(start && document.querySelector('.me-report[data-entry="'+start+'"]')) show(start);
})();
</script>
"""


def _e(x):
    return html.escape(str(x))


def _pct(x):
    return f"{x * 100:.0f}%"


def _arrow(r):
    if not (r.overall_rank and r.overall_prev):
        return ""
    moved = r.overall_prev - r.overall_rank
    pct = moved / r.overall_prev * 100 if r.overall_prev else 0
    cls, sym, word = (("up", "▲", "GREEN ARROW") if moved > 0 else
                      ("down", "▼", "RED ARROW") if moved < 0 else ("flat", "–", "NO CHANGE"))
    detail = (f"World rank {r.overall_rank:,} ({'+' if moved > 0 else '−'}{abs(moved):,}, "
              f"{'+' if pct > 0 else '−'}{abs(pct):.1f}%)" if moved else f"World rank {r.overall_rank:,}")
    return (f'<div class="arrow {cls}"><div class="dot">{sym}</div><div><div class="big">{word}</div>'
            f'<div>{_e(detail)}</div></div></div>')


def _kpis(r):
    move = (f"▲{r.league_move}" if r.league_move > 0 else f"▼{-r.league_move}" if r.league_move < 0 else "–")
    items = [(r.points, f"GW{r.gw} points"),
             (f"{r.league_pos}<span style='font-size:.9rem;color:var(--muted)'> {move}</span>",
              f"League position of {r.league_size}"),
             (f"{r.rating:g}" if r.rating is not None else "-",
              f"MOTW rating ({_ordinal(r.rating_pos)})" if r.rating_pos else "MOTW rating")]
    avg = f"League average {r.league_avg}" + (f" · FPL average {r.global_avg}" if r.global_avg else "")
    return ('<div class="kpis">' + "".join(f'<div class="kpi"><div class="v">{v}</div><div class="k">{_e(k)}</div></div>'
                                           for v, k in items) + f'</div><div class="me-note">{_e(avg)}</div>')


def _ordinal(n):
    if not n:
        return ""
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _captain(r):
    c = r.captain
    if not c:
        return ""
    top = max([v for _l, v in c["compare"]] + [1])
    bars = "".join(
        f'<div class="cbar{" you" if i == 0 else ""}"><span class="n">{_e(l)}</span>'
        f'<div class="t"><div class="f" style="width:{max(v, 0) / top * 100:.0f}%"></div></div>'
        f'<span class="v">{v:g}</span></div>' for i, (l, v) in enumerate(c["compare"]))
    vice = " (vice-captain stepped in)" if c.get("vice") else ""
    return (f'<div class="me-card"><h3>Captain</h3><div><strong>{_e(c["name"])}</strong> · '
            f'{c["points"]} points{_e(vice)}</div>{bars}</div>')


def _chips(players, good=True, empty="None this week."):
    if not players:
        return f'<div class="me-note">{_e(empty)}</div>'
    out = []
    for p in players:
        g = f" · {p.global_share:g}% of FPL" if p.global_share is not None else ""
        out.append(f'<div class="pchip {"good" if good else "bad"}"><div class="pn">{_e(p.name)} {_e(p.note)}</div>'
                   f'<div class="pp">{p.points}</div><div class="ps">{_pct(p.league_share)} of league{_e(g)}</div></div>')
    return '<div class="chips">' + "".join(out) + "</div>"


def _why(r):
    d = sum(p.points for p in r.differentials)
    t = sum(p.points for p in r.threats)
    verdict = ("Your differentials outscored the threats." if d > t else
               "The threats you didn't own outscored your differentials." if t > d else
               "Differentials and threats cancelled out.")
    return (f'<div class="me-card me-wide"><h3>Why this happened</h3><p style="margin:0 0 10px">{_e(verdict)}</p>'
            f'<div style="font-weight:700;margin-bottom:6px">Differentials (your players, owned by ≤25% of the league)</div>'
            f'{_chips(r.differentials, True)}'
            f'<div style="font-weight:700;margin:14px 0 6px">Threats (owned by ≥40% of the league, not by you)</div>'
            f'{_chips(r.threats, False)}</div>')


def _moves(r):
    items = []
    for out, inn, d in r.transfers:
        items.append(f"<li>{_e(out)} ➜ <strong>{_e(inn)}</strong> <span style='color:var({'--up' if d >= 0 else '--down'})'>"
                     f"({d:+d})</span></li>")
    if r.hit:
        items.append(f"<li>Points hit: −{r.hit}</li>")
    if r.chip:
        items.append(f"<li>Chip played: <strong>{_e(r.chip)}</strong></li>")
    for out, inn, p in r.autosubs:
        items.append(f"<li>Auto-sub: {_e(inn)} on for {_e(out)} ({p} pts)</li>")
    items.append(f"<li>Points left on the bench: {r.bench_points}</li>")
    if r.what_if_gain is not None:
        items.append(f"<li>Changes since your Gameweek 1 team: <strong>{r.what_if_gain:+d}</strong> points (What if?)</li>")
    top = ", ".join(f"{p.name}{(' ' + p.note) if p.note else ''} {p.points}" for p in r.top_players)
    if top:
        items.insert(0, f"<li>Top scorers for you: {_e(top)}</li>")
    return f'<div class="me-card"><h3>Your moves</h3><ul class="me-list">{"".join(items)}</ul></div>'


def _season(r):
    if len(r.season) < 2:
        return ""
    top = max(max(p, a) for _g, p, a in r.season) or 1
    cols = []
    for g, p, a in r.season:
        h = max(p, 0) / top * 100
        cols.append(f'<div class="col" title="GW{g}: {p} (league avg {a})"><div class="bw">'
                    f'<div class="b{" above" if p >= a else ""}" style="height:{h:.0f}%"></div>'
                    f'<i style="bottom:{a / top * 100:.0f}%"></i></div><div class="g">{g}</div></div>')
    best = max(r.season, key=lambda x: x[1])
    above = sum(1 for _g, p, a in r.season if p >= a)
    return (f'<div class="me-card"><h3>Your season</h3><div class="spark">{"".join(cols)}</div>'
            f'<div class="me-note">Orange bars beat the league average (dashed line). Above average in {above} of '
            f'{len(r.season)} gameweeks; best was GW{best[0]} with {best[1]}.</div></div>')


def render_personal(reports):
    if not reports:
        return ""
    options = "".join(f'<option value="{r.entry}">{_e(r.name)}</option>' for r in reports)
    blocks = []
    for r in reports:
        blocks.append(
            f'<div class="me-report" data-entry="{r.entry}" hidden>'
            f'<p style="margin:12px 0 0"><strong>{_e(r.name)}</strong> · {_e(r.team)} — {_e(r.summary)}</p>'
            f'<div class="me-grid">'
            f'<div class="me-card">{_arrow(r)}{_kpis(r)}</div>'
            f'{_captain(r)}{_why(r)}{_moves(r)}{_season(r)}'
            f'</div></div>')
    return (f'<section class="block" id="me"><div class="me-head"><h2>Your personal report</h2>'
            f'<label class="sr" for="me-select" style="position:absolute;left:-9999px">Choose a manager</label>'
            f'<select id="me-select" class="me-select"><option value="">Choose your name…</option>{options}</select></div>'
            f'<div class="me-empty">Pick your name to see your gameweek in detail: rank arrow, captain, '
            f'differentials and threats, transfers and your season so far.</div>'
            f'{"".join(blocks)}</section>{JS}')
