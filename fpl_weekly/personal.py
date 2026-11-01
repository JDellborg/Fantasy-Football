"""Personal reports: one per manager, picked from a drop-down on the web page.

Inspired by the kind of indicators rank-tracking sites show (rank arrow, captain comparison,
differentials and threats, transfer gains), built only from the official FPL data.
"""

from collections import Counter
from dataclasses import dataclass, field

DIFFERENTIAL_MAX_SHARE = 0.25   # owned by at most a quarter of the league
THREAT_MIN_SHARE = 0.40         # owned by at least 40% of the league (but not by you)


@dataclass
class PlayerLine:
    name: str
    points: int
    league_share: float          # 0-1, share of league squads that own the player
    global_share: float = None   # % of all FPL managers
    note: str = ""


@dataclass
class PersonalReport:
    entry: int
    name: str
    team: str
    gw: int
    points: int
    league_pos: int = None
    league_move: int = 0
    league_size: int = 0
    league_avg: float = 0
    global_avg: float = None
    overall_rank: int = None
    overall_prev: int = None
    rating: float = None
    rating_pos: int = None
    captain: dict = None            # name, points, compare: [(label, value)]
    differentials: list = field(default_factory=list)
    threats: list = field(default_factory=list)
    top_players: list = field(default_factory=list)
    transfers: list = field(default_factory=list)   # (out, in, delta)
    hit: int = 0
    bench_points: int = 0
    autosubs: list = field(default_factory=list)
    chip: str = None
    season: list = field(default_factory=list)      # [(gw, points, league_avg)]
    what_if_gain: int = None
    summary: str = ""


CHIPS = {"wildcard": "Wildcard", "freehit": "Free Hit", "bboost": "Bench Boost", "3xc": "Triple Captain",
         "manager": "Assistant Manager"}


def build_personal_reports(builder):
    gw = builder.gw
    squads = builder.squads
    n = len(squads) or 1
    owners = Counter(el for sq in squads.values() for el in sq)
    ev = builder.events.get(gw, {})
    global_avg = ev.get("average_entry_score")

    # captain comparisons
    caps = builder.caps
    league_cap_avg = round(sum(c[1] for c in caps.values()) / len(caps), 1) if caps else None
    fav_league = Counter(c[3] for c in caps.values()).most_common(1)[0][0] if caps else None
    fav_global = ev.get("most_captained")

    # season league averages
    avgs = {}
    for g in range(1, gw + 1):
        vals = [m.net(g) for m in builder.managers if g in m.history]
        if vals:
            avgs[g] = sum(vals) / len(vals)

    ratings = {r.manager.entry: (i, r) for i, r in enumerate(builder.motw_ratings, 1)}
    what_if = {r[0].entry: r[3] for r in builder.what_if_results}

    reports = []
    for m in sorted(builder.active, key=lambda m: m.name.lower()):
        row = m.history[gw]
        rep = PersonalReport(entry=m.entry, name=m.name, team=m.team, gw=gw, points=m.net(gw),
                             league_size=len(builder.active), league_avg=builder.league_avg,
                             global_avg=global_avg)
        rep.league_pos = builder.classic_now.get(m.entry)
        if m.entry in builder.classic_prev:
            rep.league_move = builder.classic_prev[m.entry] - rep.league_pos
        rep.overall_rank = row.get("overall_rank")
        if gw - 1 in m.history:
            rep.overall_prev = m.history[gw - 1].get("overall_rank")
        if m.entry in ratings:
            rep.rating_pos, r = ratings[m.entry]
            rep.rating = r.rating
        rep.chip = CHIPS.get((m.picks or {}).get("active_chip"))
        rep.hit = row.get("event_transfers_cost", 0)
        rep.bench_points = row.get("points_on_bench", 0)
        rep.what_if_gain = what_if.get(m.entry)
        rep.season = [(g, m.net(g), round(avgs[g], 1)) for g in sorted(m.history) if g <= gw and g in avgs]

        # captain
        cap = caps.get(m.entry)
        if cap:
            compare = [("You", cap[1])]
            if league_cap_avg is not None:
                compare.append(("League average", league_cap_avg))
            if fav_league:
                mult = 2
                compare.append((f"League favourite ({builder.pname(fav_league)})", builder.pts(fav_league) * mult))
            if fav_global:
                compare.append((f"FPL favourite ({builder.pname(fav_global)})", builder.pts(fav_global) * 2))
            rep.captain = {"name": builder.pname(cap[0]), "points": cap[1], "vice": cap[2], "compare": compare}

        # contributions, differentials, threats
        xi = builder.xis.get(m.entry, set())
        mine = squads.get(m.entry, set())
        contrib = {el: builder.pts(el) for el in xi}
        if cap and cap[0] in contrib:
            contrib[cap[0]] = cap[1]

        def share(el):
            return owners[el] / n

        def gshare(el):
            try:
                return float(builder.players.get(el, {}).get("selected_by_percent"))
            except (TypeError, ValueError):
                return None

        rep.top_players = [PlayerLine(builder.pname(el), p, share(el), gshare(el),
                                      "(C)" if cap and el == cap[0] else "")
                           for el, p in sorted(contrib.items(), key=lambda kv: -kv[1])[:3]]
        rep.differentials = [PlayerLine(builder.pname(el), contrib[el], share(el), gshare(el))
                             for el in sorted(xi, key=lambda el: -contrib[el])
                             if share(el) <= DIFFERENTIAL_MAX_SHARE][:5]
        threat_pool = [el for el, c in owners.items() if el not in mine and c / n >= THREAT_MIN_SHARE]
        rep.threats = [PlayerLine(builder.pname(el), builder.pts(el), share(el), gshare(el))
                       for el in sorted(threat_pool, key=lambda el: -builder.pts(el))
                       if builder.pts(el) > 0][:4]

        # transfers and autosubs
        if (m.picks or {}).get("active_chip") not in ("wildcard", "freehit"):
            rep.transfers = [(builder.pname(t["element_out"]), builder.pname(t["element_in"]),
                              builder.pts(t["element_in"]) - builder.pts(t["element_out"]))
                             for t in m.transfers]
        rep.autosubs = [(builder.pname(a["element_out"]), builder.pname(a["element_in"]),
                         builder.pts(a["element_in"]))
                        for a in (m.picks or {}).get("automatic_subs", [])]
        rep.summary = _summary(rep)
        reports.append(rep)
    return reports


def _summary(rep):
    bits = []
    diff = rep.points - rep.league_avg
    bits.append(f"{rep.points} points, {abs(diff):.0f} {'above' if diff >= 0 else 'below'} the league average")
    if rep.overall_rank and rep.overall_prev:
        moved = rep.overall_prev - rep.overall_rank
        bits.append(f"{'up' if moved > 0 else 'down'} {abs(moved):,} places in the world" if moved else
                    "no change in world rank")
    d_pts = sum(p.points for p in rep.differentials)
    t_pts = sum(p.points for p in rep.threats)
    if rep.differentials or rep.threats:
        bits.append(f"differentials brought {d_pts}, threats you didn't own scored {t_pts}")
    return "; ".join(bits).capitalize() + "."
