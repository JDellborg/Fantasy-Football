"""Manager of the Week: a rounded assessment, not just the highest score.

Rating = gameweek points (after hits)
         - chip boost          Triple Captain: the extra captain points; Bench Boost: the bench
                               points; Wildcard / Free Hit: 10% of the score
         - concentration       if the top 3 players' share of the points is more than 5 percentage
                               points above the league's typical share that week (and above 60%):
                               0.5 for every percentage point over that line
         + underdog credit     0.5 for every league place below 1st going into the week (max 10)
         + above own average   a quarter of the points above their own season average (max 10)
"""

from dataclasses import dataclass, field

CHIP_FH_WC_DISCOUNT = 0.10
CONCENTRATION_FLOOR = 0.60    # never penalise below this share
CONCENTRATION_MARGIN = 0.05   # allowance above the league's median share that week
CONCENTRATION_RATE = 0.5      # rating points per percentage point above the start
UNDERDOG_PER_PLACE = 0.5
UNDERDOG_CAP = 10
FORM_RATE = 0.25
FORM_CAP = 10
SHOW = 5


@dataclass
class Rating:
    manager: object
    points: int
    rating: float = 0.0
    parts: list = field(default_factory=list)   # (short label, value) adjustments
    top3_share: float = 0.0
    prev_rank: int = None
    chip: str = None


def _effective_xi(builder, m):
    picks = (m.picks or {}).get("picks", [])
    xi = {p["element"] for p in picks if p.get("position", 0) <= 11}
    for sub in (m.picks or {}).get("automatic_subs", []):
        xi.discard(sub["element_out"])
        xi.add(sub["element_in"])
    if (m.picks or {}).get("active_chip") == "bboost":
        xi = {p["element"] for p in picks}
    return xi, picks


def _prev_ranks(builder):
    gw = builder.gw
    pool = [m for m in builder.active if gw - 1 in m.history]
    ordered = sorted(pool, key=lambda m: -m.history[gw - 1]["total_points"])
    ranks, last_total, last_rank = {}, None, 0
    for i, m in enumerate(ordered, 1):
        t = m.history[gw - 1]["total_points"]
        if t != last_total:
            last_rank, last_total = i, t
        ranks[m.entry] = last_rank
    return ranks


def rate_managers(builder):
    gw = builder.gw
    prev = _prev_ranks(builder) if gw > 1 else {}
    ratings = []
    for m in builder.active:
        net = m.net(gw)
        r = Rating(m, net, rating=float(net))
        chip = (m.picks or {}).get("active_chip")
        r.chip = chip
        xi, picks = _effective_xi(builder, m)

        # chip boost
        cap = builder.captain_of(m)
        if chip == "3xc" and cap:
            boost = builder.pts(cap[0])                 # the third 'copy' of the captain
            r.parts.append(("Triple Captain", -boost))
        elif chip == "bboost":
            boost = sum(builder.pts(p["element"]) for p in picks if p.get("position", 0) > 11)
            r.parts.append(("Bench Boost", -boost))
        elif chip in ("wildcard", "freehit"):
            label = "Wildcard" if chip == "wildcard" else "Free Hit"
            r.parts.append((label, -round(max(net, 0) * CHIP_FH_WC_DISCOUNT, 1)))

        # concentration in the top three players (captain counted with the armband);
        # the penalty is applied below, once the league's typical share is known
        contrib = {el: builder.pts(el) for el in xi}
        if cap and cap[0] in contrib:
            contrib[cap[0]] = cap[1]
        positive = sum(v for v in contrib.values() if v > 0)
        if positive > 0:
            top3 = sum(sorted((v for v in contrib.values() if v > 0), reverse=True)[:3])
            r.top3_share = top3 / positive

        # underdog credit
        if m.entry in prev:
            r.prev_rank = prev[m.entry]
            credit = min((prev[m.entry] - 1) * UNDERDOG_PER_PLACE, UNDERDOG_CAP)
            if credit > 0:
                r.parts.append((f"From {_ordinal(prev[m.entry])}", round(credit, 1)))

        # above their own average (other weeks)
        others = [m.net(g) for g in m.history if g < gw]
        if others:
            above = net - sum(others) / len(others)
            if above > 0:
                r.parts.append(("Above own avg", round(min(above * FORM_RATE, FORM_CAP), 1)))

        ratings.append(r)

    shares = sorted(r.top3_share for r in ratings if r.top3_share)
    typical = shares[len(shares) // 2] if shares else 0
    line = max(CONCENTRATION_FLOOR, typical + CONCENTRATION_MARGIN)
    builder.motw_concentration_line = (typical, line)
    for r in ratings:
        over = (r.top3_share - line) * 100
        if over > 0:
            r.parts.insert(1 if r.chip else 0,
                           (f"Top 3 = {r.top3_share:.0%}", -round(over * CONCENTRATION_RATE, 1)))
        r.rating = round(r.points + sum(v for _l, v in r.parts), 1)
    return sorted(ratings, key=lambda r: (-r.rating, -r.points))


def _ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _fmt(v):
    return f"{v:+.1f}".replace(".0", "")


def manager_of_the_week(builder, Section, Table):
    ratings = rate_managers(builder)
    if not ratings:
        return None
    builder.motw_ratings = ratings
    win = ratings[0]
    top_scorer = max(ratings, key=lambda r: r.points)
    s = Section("Manager of the Week")

    reasons = []
    if win.chip is None:
        reasons.append("no chip")
    typical, line = getattr(builder, "motw_concentration_line", (0, CONCENTRATION_FLOOR))
    if win.top3_share and win.top3_share <= line:
        reasons.append(f"points spread across the team (top three players {win.top3_share:.0%})")
    if win.prev_rank and win.prev_rank > 1:
        reasons.append(f"started the week {_ordinal(win.prev_rank)}")
    above = next((v for l, v in win.parts if l == "Above own avg"), 0)
    if above >= 3:
        reasons.append("well above his usual score")
    text = f"**{win.manager.name}** is Manager of the Week with a rating of {win.rating:g} from {win.points} points"
    text += (": " + ", ".join(reasons) + ".") if reasons else "."
    if top_scorer is not win:
        text += (f" {top_scorer.manager.name} had the highest score ({top_scorer.points}) but rated "
                 f"{top_scorer.rating:g} after adjustments.")
    s.paragraphs.append(text)

    rows = []
    for i, r in enumerate(ratings[:SHOW], 1):
        adj = ", ".join(f"{l} {_fmt(v)}" for l, v in r.parts) or "-"
        rows.append([str(i), r.manager.name, str(r.points), adj, f"{r.rating:g}"])
    s.table = Table(["Pos", "Manager", "GW", "Adjustments", "Rating"], rows,
                    align=["left", "left", "right", "left", "right"],
                    widths=["auto", "auto", "auto", "stretch", "auto"])
    s.paragraphs.append(f"How it works: gameweek points, minus any boost from a chip, minus a deduction "
                        f"if the top three players made up more than {line:.0%} of the points (this week's "
                        f"typical share was {typical:.0%}), plus credit for starting the week lower in the "
                        f"table and for beating his own average.")
    return s
