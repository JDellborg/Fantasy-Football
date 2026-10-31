"""Crunches FPL data into a list of report sections (renderer-agnostic)."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .banter import Banter

CHIP_NAMES = {
    "wildcard": "Wildcard",
    "freehit": "Free Hit",
    "bboost": "Bench Boost",
    "3xc": "Triple Captain",
    "manager": "Assistant Manager",
}
FORM_WEEKS = 4


@dataclass
class Section:
    title: str
    lines: list = field(default_factory=list)   # short paragraphs (light markdown)
    facts: list = field(default_factory=list)   # (label, value) rows


@dataclass
class Report:
    title: str
    subtitle: str
    gameweek: int
    sections: list


@dataclass
class Manager:
    entry: int
    team: str
    player: str
    name: str = ""
    history: dict = field(default_factory=dict)
    picks: dict = None
    transfers: list = field(default_factory=list)

    def net(self, gw):
        row = self.history.get(gw)
        return None if row is None else row["points"] - row["event_transfers_cost"]


# --- small helpers ---------------------------------------------------------

def latest_final_gameweek(events):
    done = [e["id"] for e in events if e.get("finished") and e.get("data_checked")]
    return max(done) if done else None


def join_names(names):
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " & " + names[-1]


def ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def arrow(move):
    if move is None or move == 0:
        return "➖"
    return f"🔺{move}" if move > 0 else f"🔻{-move}"


def competition_rank(items, key):
    """items -> {item_id: rank}, ties share a rank (1, 2, 2, 4)."""
    ordered = sorted(items, key=key)
    ranks, prev, prev_rank = {}, object(), 0
    for i, (item_id, *_rest) in enumerate(ordered, start=1):
        k = key((item_id, *_rest))
        if k != prev:
            prev_rank, prev = i, k
        ranks[item_id] = prev_rank
    return ranks


def make_display_names(player_names, nicknames):
    """First names, unless two people share one (then full names)."""
    firsts = Counter(n.split()[0] for n in player_names.values() if n.strip())
    out = {}
    for entry, full in player_names.items():
        first = full.split()[0] if full.strip() else full
        out[entry] = nicknames.get(str(entry)) or (first if firsts[first] == 1 else full)
    return out


# --- the report ----------------------------------------------------------------

class ReportBuilder:
    def __init__(self, client, config, gameweek=None):
        self.client = client
        self.config = config
        boot = client.bootstrap()
        self.events = {e["id"]: e for e in boot["events"]}
        self.gw = gameweek or latest_final_gameweek(boot["events"])
        if not self.gw:
            raise SystemExit("No finished gameweek yet - nothing to report.")
        self.players = {p["id"]: p for p in boot["elements"]}
        self.banter = Banter(seed=f"{config['classic_league_id']}-{self.gw}")

    def pname(self, element_id):
        p = self.players.get(element_id)
        return p["web_name"] if p else f"Player {element_id}"

    # -- data loading --
    def load(self):
        cfg = self.config
        self.league, standings = self.client.classic_standings(cfg["classic_league_id"])
        self.managers = [Manager(r["entry"], r["entry_name"], r["player_name"]) for r in standings]

        self.h2h = []
        for lg in cfg.get("h2h_leagues", []):
            league, table = self.client.h2h_standings(lg["id"])
            matches = self.client.h2h_matches(lg["id"])
            self.h2h.append((lg, league, table, matches))

        player_names = {m.entry: m.player for m in self.managers}
        for _lg, _league, table, _matches in self.h2h:
            for r in table:
                player_names.setdefault(r["entry"], r["player_name"])
        self.names = make_display_names(player_names, cfg.get("nicknames", {}))
        for m in self.managers:
            m.name = self.names[m.entry]

        gw = self.gw
        for m in self.managers:
            hist = self.client.entry_history(m.entry)
            m.history = {row["event"]: row for row in hist.get("current", [])}
        self.active = [m for m in self.managers if gw in m.history]
        if not self.active:
            raise SystemExit(f"Nobody in the league has a score for gameweek {gw}.")

        self.live = {el["id"]: el["stats"] for el in self.client.live(gw)["elements"]}
        for m in self.active:
            m.picks = self.client.picks(m.entry, gw)
            if m.history[gw].get("event_transfers"):
                m.transfers = [t for t in self.client.transfers(m.entry) if t["event"] == gw]

    def pts(self, element_id):
        return self.live.get(element_id, {}).get("total_points", 0)

    def mins(self, element_id):
        return self.live.get(element_id, {}).get("minutes", 0)

    # -- build --
    def build(self):
        self.load()
        gw = self.gw
        scores = {m.entry: m.net(gw) for m in self.active}
        self.top = max(scores.values())
        self.bottom = min(scores.values())
        self.motw = [m for m in self.active if scores[m.entry] == self.top]
        self.spoon = [m for m in self.active if scores[m.entry] == self.bottom]
        self.league_avg = round(sum(scores.values()) / len(scores), 1)

        sections = [self.headline_section(), self.table_section(), self.form_section(),
                    self.captain_section(), self.transfer_section(), self.chip_section(),
                    self.bench_and_differential_section()]
        sections += [self.h2h_section(*h) for h in self.h2h]
        sections.append(self.season_section())
        sections = [s for s in sections if s and (s.lines or s.facts)]
        sections.append(Section("👋 Until next week", [self.banter.line(
            "outro",
            motw=join_names(m.name for m in self.motw),
            spoon=join_names(m.name for m in self.spoon))]))

        title = self.config.get("title") or self.league["name"]
        return Report(
            title=f"⚽ {title} - Gameweek {gw} Roundup",
            subtitle=self.banter.line("intro"),
            gameweek=gw,
            sections=sections,
        )

    def headline_section(self):
        gw, ev = self.gw, self.events.get(self.gw, {})
        motw_names = join_names(f"**{m.name}** ({m.team})" for m in self.motw)
        spoon_names = join_names(f"**{m.name}** ({m.team})" for m in self.spoon)
        s = Section("🏆 Manager of the Week")
        s.lines.append(self.banter.line("motw", name=motw_names, pts=self.top))
        s.lines.append("🥄 **Wooden Spoon**")
        s.lines.append(self.banter.line("spoon", name=spoon_names, pts=self.bottom))
        s.facts = [
            ("League average", f"{self.league_avg}"),
            ("FPL global average", f"{ev.get('average_entry_score', '-')}"),
            ("Highest score in the world", f"{ev.get('highest_score', '-')}"),
        ]
        ranked = [m for m in self.active if m.history[gw].get("overall_rank")]
        if ranked:
            best = min(ranked, key=lambda m: m.history[gw]["overall_rank"])
            s.facts.append(("Best world rank", f"{best.name} (#{best.history[gw]['overall_rank']:,})"))
        return s

    def table_section(self):
        gw = self.gw
        now = competition_rank([(m.entry, m.history[gw]["total_points"]) for m in self.active],
                               key=lambda x: -x[1])
        prev_pool = [m for m in self.active if gw - 1 in m.history]
        prev = competition_rank([(m.entry, m.history[gw - 1]["total_points"]) for m in prev_pool],
                                key=lambda x: -x[1]) if prev_pool else {}
        moves = {m.entry: (prev[m.entry] - now[m.entry]) if m.entry in prev else None
                 for m in self.active}

        ordered = sorted(self.active, key=lambda m: (now[m.entry], m.name))
        if len(ordered) > 12:
            shown = ordered[:6] + [None] + ordered[-3:]
        else:
            shown = ordered
        s = Section("📋 Classic League Table")
        for m in shown:
            if m is None:
                s.facts.append(("…", "…"))
                continue
            label = f"{now[m.entry]}. {m.name} - {m.team}"
            s.facts.append((label, f"{m.history[gw]['total_points']} pts ({m.net(gw)} this GW) {arrow(moves[m.entry])}"))

        real_moves = {e: mv for e, mv in moves.items() if mv}
        if real_moves:
            by_entry = {m.entry: m for m in self.active}
            up = max(real_moves.values())
            down = min(real_moves.values())
            if up > 0:
                who = join_names(by_entry[e].name for e, mv in real_moves.items() if mv == up)
                s.lines.append("📈 " + self.banter.line("climber", name=who, n=up, places="place" if up == 1 else "places"))
            if down < 0:
                who = join_names(by_entry[e].name for e, mv in real_moves.items() if mv == down)
                s.lines.append("📉 " + self.banter.line("faller", name=who, n=-down, places="place" if down == -1 else "places"))
        return s

    def form_section(self):
        gw = self.gw
        weeks = [g for g in range(gw - FORM_WEEKS + 1, gw + 1) if g >= 1]
        if len(weeks) < 2:
            return None
        form = {m.entry: sum(m.net(g) or 0 for g in weeks) for m in self.active
                if all(g in m.history for g in weeks)}
        if len(form) < 2:
            return None
        by_entry = {m.entry: m for m in self.active}
        ordered = sorted(form.items(), key=lambda kv: -kv[1])
        s = Section(f"🔥 Form Guide (last {len(weeks)} GWs)")
        hot_e, hot_p = ordered[0]
        cold_e, cold_p = ordered[-1]
        s.lines.append("🔥 " + self.banter.line("hot", name=by_entry[hot_e].name, pts=hot_p, weeks=len(weeks)))
        s.lines.append("🥶 " + self.banter.line("cold", name=by_entry[cold_e].name, pts=cold_p, weeks=len(weeks)))
        for e, p in ordered[:3]:
            s.facts.append((f"🔥 {by_entry[e].name}", f"{p} pts"))
        for e, p in ordered[-3:][::-1] if len(ordered) > 3 else []:
            s.facts.append((f"🥶 {by_entry[e].name}", f"{p} pts"))

        # streaks of beating / missing the league average
        avgs = {}
        for g in range(1, gw + 1):
            vals = [m.net(g) for m in self.managers if g in m.history]
            if vals:
                avgs[g] = sum(vals) / len(vals)
        streaks = {}
        for m in self.active:
            above = m.net(gw) > avgs[gw]
            n = 0
            for g in range(gw, 0, -1):
                if g not in m.history or g not in avgs or (m.net(g) > avgs[g]) != above:
                    break
                n += 1
            streaks[m.entry] = n if above else -n
        best = max(streaks.values())
        worst = min(streaks.values())
        if best >= 3:
            who = join_names(by_entry[e].name for e, v in streaks.items() if v == best)
            s.lines.append(f"📈 {who} beat the league average **{best} weeks running**.")
        if worst <= -3:
            who = join_names(by_entry[e].name for e, v in streaks.items() if v == worst)
            s.lines.append(f"📉 {who} {'has' if '&' not in who else 'have'} been below average "
                           f"**{-worst} weeks running**. Concerning.")
        return s

    def captain_of(self, m):
        picks = (m.picks or {}).get("picks", [])
        cap = next((p for p in picks if p.get("is_captain")), None)
        vice = next((p for p in picks if p.get("is_vice_captain")), None)
        if not cap:
            return None
        mult = 3 if (m.picks or {}).get("active_chip") == "3xc" else 2
        chosen, swapped = cap, False
        if self.mins(cap["element"]) == 0 and vice and self.mins(vice["element"]) > 0:
            chosen, swapped = vice, True
        return chosen["element"], self.pts(chosen["element"]) * mult, swapped, cap["element"]

    def captain_section(self):
        caps = {m.entry: self.captain_of(m) for m in self.active}
        caps = {e: c for e, c in caps.items() if c}
        if not caps:
            return None
        by_entry = {m.entry: m for m in self.active}
        s = Section("©️ Captaincy Corner")
        picked = Counter(c[3] for c in caps.values())
        fav, n = picked.most_common(1)[0]
        s.facts.append(("Most popular captain", f"{self.pname(fav)} ({n}/{len(caps)}) - {self.pts(fav)} pts"))
        best = max(c[1] for c in caps.values())
        worst = min(c[1] for c in caps.values())
        best_e = [e for e, c in caps.items() if c[1] == best]
        worst_e = [e for e, c in caps.items() if c[1] == worst]
        s.lines.append("👑 " + self.banter.line(
            "best_captain", name=join_names(by_entry[e].name for e in best_e),
            player=self.pname(caps[best_e[0]][0]), pts=best))
        if worst < best:
            s.lines.append("🤦 " + self.banter.line(
                "worst_captain", name=join_names(by_entry[e].name for e in worst_e),
                player=self.pname(caps[worst_e[0]][0]), pts=worst))
        saved = [e for e, c in caps.items() if c[2]]
        if saved:
            s.lines.append(f"🙏 Saved by the vice-captain: {join_names(by_entry[e].name for e in saved)}.")
        return s

    def transfer_section(self):
        gw = self.gw
        s = Section("🔄 Transfers & Hits")
        singles, hits = [], []
        for m in self.active:
            chip = (m.picks or {}).get("active_chip")
            if chip in ("wildcard", "freehit"):
                continue
            delta_total = 0
            for t in m.transfers:
                d = self.pts(t["element_in"]) - self.pts(t["element_out"])
                delta_total += d
                singles.append((d, m, t))
            cost = m.history[gw].get("event_transfers_cost", 0)
            if cost and m.transfers:
                hits.append((delta_total - cost, cost, m))
        if singles:
            d, m, t = max(singles, key=lambda x: x[0])
            if d > 0:
                s.facts.append(("✅ Best transfer", f"{m.name}: {self.pname(t['element_out'])} ➡️ "
                                f"{self.pname(t['element_in'])} ({d:+d})"))
            d, m, t = min(singles, key=lambda x: x[0])
            if d < 0:
                s.facts.append(("❌ Worst transfer", f"{m.name}: {self.pname(t['element_out'])} ➡️ "
                                f"{self.pname(t['element_in'])} ({d:+d})"))
        hits.sort(key=lambda x: -x[0])
        if len(hits) > 3:  # keep it readable: best two and the worst one
            hits = hits[:2] + hits[-1:]
        for net, cost, m in hits:
            key = "hit_good" if net > 0 else "hit_bad"
            s.lines.append("💸 " + self.banter.line(key, name=m.name, cost=cost, net=net))
        total_moves = sum(m.history[gw].get("event_transfers", 0) for m in self.active)
        if total_moves:
            busiest = max(self.active, key=lambda m: m.history[gw].get("event_transfers", 0))
            s.facts.append(("Transfers made in the league", str(total_moves)))
            s.facts.append(("Busiest in the market", f"{busiest.name} "
                            f"({busiest.history[gw].get('event_transfers', 0)})"))
        return s

    def chip_section(self):
        s = Section("🃏 Chips Played")
        for m in self.active:
            chip = (m.picks or {}).get("active_chip")
            if not chip:
                continue
            label = CHIP_NAMES.get(chip, chip)
            net = m.net(self.gw)
            if chip == "3xc":
                cap = self.captain_of(m)
                extra = f"{self.pname(cap[0])} returned **{cap[1]}**" if cap else ""
                verdict = "Inspired." if cap and cap[1] >= 24 else "Oof." if cap and cap[1] <= 9 else ""
                s.lines.append(f"🃏 **{m.name}** went Triple Captain: {extra}. {verdict}".strip())
            elif chip == "bboost":
                bench = [p for p in m.picks["picks"] if p.get("position", 0) > 11]
                bench_pts = sum(self.pts(p["element"]) for p in bench)
                verdict = "Worth it." if bench_pts >= 15 else "Might as well have saved it." if bench_pts < 8 else ""
                s.lines.append(f"🃏 **{m.name}** Bench Boosted for **{bench_pts}** bench points. {verdict}".strip())
            else:
                vs = "above" if net > self.league_avg else "below"
                s.lines.append(f"🃏 **{m.name}** played the {label} and scored **{net}** "
                               f"({vs} the league average of {self.league_avg}).")
        return s

    def bench_and_differential_section(self):
        gw = self.gw
        s = Section("🪑 Bench Regret & 🎯 Differentials")
        benches = [(m.history[gw].get("points_on_bench", 0), m) for m in self.active
                   if (m.picks or {}).get("active_chip") != "bboost"]
        if benches:
            top = max(b for b, _ in benches)
            if top >= 5:
                who = join_names(m.name for b, m in benches if b == top)
                s.lines.append("🪑 " + self.banter.line("bench", name=who, pts=top))
            s.facts.append(("Total points benched by the league", str(sum(b for b, _ in benches))))

        squads, xis = {}, {}
        for m in self.active:
            picks = (m.picks or {}).get("picks", [])
            if not picks:
                continue
            squads[m.entry] = {p["element"] for p in picks}
            xi = {p["element"] for p in picks if p.get("position", 0) <= 11}
            for sub in (m.picks or {}).get("automatic_subs", []):
                xi.discard(sub["element_out"])
                xi.add(sub["element_in"])
            if m.picks.get("active_chip") == "bboost":
                xi = set(squads[m.entry])
            xis[m.entry] = xi
        if squads:
            owners = Counter(el for sq in squads.values() for el in sq)
            by_entry = {m.entry: m for m in self.active}
            diffs = [(self.pts(el), el, e) for e, xi in xis.items() for el in xi if owners[el] == 1]
            if diffs and len(squads) > 2:
                pts, el, e = max(diffs)
                if pts >= 6:
                    s.lines.append("🎯 " + self.banter.line("differential", name=by_entry[e].name,
                                                           player=self.pname(el), pts=pts))
            template, count = owners.most_common(1)[0]
            s.facts.append(("Most-owned player in the league",
                            f"{self.pname(template)} ({count}/{len(squads)} squads) - {self.pts(template)} pts"))
        return s

    # -- head to head --
    def h2h_table(self, matches, upto):
        rows = defaultdict(lambda: {"pts": 0, "w": 0, "d": 0, "l": 0, "pf": 0})
        for mt in matches:
            if mt["event"] > upto or mt.get("is_knockout"):
                continue
            for side, other in (("1", "2"), ("2", "1")):
                e = mt[f"entry_{side}_entry"]
                if e is None:
                    continue
                r = rows[e]
                mine, theirs = mt[f"entry_{side}_points"], mt[f"entry_{other}_points"]
                r["pf"] += mine
                if mine > theirs:
                    r["w"] += 1; r["pts"] += 3
                elif mine == theirs:
                    r["d"] += 1; r["pts"] += 1
                else:
                    r["l"] += 1
        ranks = competition_rank([(e, r["pts"], r["pf"]) for e, r in rows.items()],
                                 key=lambda x: (-x[1], -x[2]))
        return rows, ranks

    def side_name(self, mt, side):
        e = mt[f"entry_{side}_entry"]
        if e is None:
            return "League Average"
        return self.names.get(e) or mt.get(f"entry_{side}_player_name") or mt.get(f"entry_{side}_name")

    def h2h_section(self, lg, league, _table, matches):
        gw = self.gw
        label = lg.get("label") or league.get("name")
        s = Section(f"⚔️ {label}")
        this_week = [mt for mt in matches if mt["event"] == gw]
        if not this_week:
            return None
        _, prev_ranks = self.h2h_table(matches, gw - 1)
        rows, ranks = self.h2h_table(matches, gw)

        decided = []
        for mt in this_week:
            n1, n2 = self.side_name(mt, "1"), self.side_name(mt, "2")
            p1, p2 = mt["entry_1_points"], mt["entry_2_points"]
            ko = " (KO)" if mt.get("is_knockout") else ""
            s.facts.append((f"{n1} vs {n2}{ko}", f"{p1} - {p2}"))
            if p1 != p2:
                w, l = ("1", "2") if p1 > p2 else ("2", "1")
                decided.append({
                    "winner": self.side_name(mt, w), "loser": self.side_name(mt, l),
                    "wpts": mt[f"entry_{w}_points"], "lpts": mt[f"entry_{l}_points"],
                    "went": mt[f"entry_{w}_entry"], "lent": mt[f"entry_{l}_entry"],
                    "margin": abs(p1 - p2),
                })
        if decided:
            big = max(decided, key=lambda d: d["margin"])
            s.lines.append("💥 " + self.banter.line("h2h_thrashing", winner=f"**{big['winner']}**",
                                                    loser=big["loser"], margin=big["margin"]))
            small = min(decided, key=lambda d: d["margin"])
            if small is not big and small["margin"] <= 10:
                s.lines.append("😬 " + self.banter.line("h2h_narrow", winner=f"**{small['winner']}**",
                                                       loser=small["loser"], margin=small["margin"],
                                                       points="point" if small["margin"] == 1 else "points"))
            robbed = max(decided, key=lambda d: d["lpts"])
            if robbed["lpts"] > self.league_avg + 10:
                s.lines.append("😭 " + self.banter.line("h2h_robbed", name=robbed["loser"], pts=robbed["lpts"]))
            jammy = min(decided, key=lambda d: d["wpts"])
            if jammy["wpts"] < self.league_avg - 5:
                s.lines.append("🍀 " + self.banter.line("h2h_jammy", name=jammy["winner"], pts=jammy["wpts"]))
            upsets = [d for d in decided if d["went"] in prev_ranks and d["lent"] in prev_ranks
                      and prev_ranks[d["went"]] - prev_ranks[d["lent"]] >= 3]
            if upsets and gw > 1:
                u = max(upsets, key=lambda d: prev_ranks[d["went"]] - prev_ranks[d["lent"]])
                s.lines.append("🚨 " + self.banter.line(
                    "h2h_upset", winner=f"**{u['winner']}**", loser=u["loser"],
                    wrank=ordinal(prev_ranks[u["went"]]), lrank=ordinal(prev_ranks[u["lent"]])))

        # current streaks
        results = defaultdict(list)
        for mt in sorted(matches, key=lambda m: m["event"]):
            if mt["event"] > gw:
                continue
            for side, other in (("1", "2"), ("2", "1")):
                e = mt[f"entry_{side}_entry"]
                if e is None:
                    continue
                a, b = mt[f"entry_{side}_points"], mt[f"entry_{other}_points"]
                results[e].append("W" if a > b else "D" if a == b else "L")
        def streak(seq, ok):
            n = 0
            for r in reversed(seq):
                if r not in ok:
                    break
                n += 1
            return n
        wins = {e: streak(r, "W") for e, r in results.items()}
        losses = {e: streak(r, "L") for e, r in results.items()}
        if wins and max(wins.values()) >= 3:
            top = max(wins.values())
            s.lines.append(f"🔥 {join_names(self.names.get(e, '?') for e, v in wins.items() if v == top)}: "
                           f"**{top} wins on the bounce**.")
        if losses and max(losses.values()) >= 3:
            top = max(losses.values())
            s.lines.append(f"🧊 {join_names(self.names.get(e, '?') for e, v in losses.items() if v == top)}: "
                           f"**{top} defeats in a row**. Someone check on them.")

        if ranks:
            ordered = sorted(ranks, key=lambda e: ranks[e])
            leader = ordered[0]
            r = rows[leader]
            s.lines.append(f"👑 Top of the table: **{self.names.get(leader, '?')}** "
                           f"({r['pts']} pts, W{r['w']} D{r['d']} L{r['l']}). "
                           f"Propping it up: {self.names.get(ordered[-1], '?')} "
                           f"({rows[ordered[-1]]['pts']} pts).")
        return s

    def season_section(self):
        gw = self.gw
        s = Section("📜 Season So Far")
        motw_count, spoon_count = Counter(), Counter()
        best = worst = None
        for g in range(1, gw + 1):
            sc = {m.entry: m.net(g) for m in self.managers if g in m.history}
            if len(sc) < 2:
                continue
            hi, lo = max(sc.values()), min(sc.values())
            for e, v in sc.items():
                if v == hi:
                    motw_count[e] += 1
                if v == lo:
                    spoon_count[e] += 1
                if best is None or v > best[0]:
                    best = (v, e, g)
                if worst is None or v < worst[0]:
                    worst = (v, e, g)
        by_entry = {m.entry: m for m in self.managers}
        if best:
            s.facts.append(("Highest GW score", f"{best[0]} - {by_entry[best[1]].name} (GW{best[2]})"))
            s.facts.append(("Lowest GW score", f"{worst[0]} - {by_entry[worst[1]].name} (GW{worst[2]})"))
        if motw_count:
            top = max(motw_count.values())
            s.facts.append(("Most Manager of the Week wins",
                            f"{join_names(by_entry[e].name for e, c in motw_count.items() if c == top)} ({top})"))
        if spoon_count:
            top = max(spoon_count.values())
            s.facts.append(("Most Wooden Spoons",
                            f"{join_names(by_entry[e].name for e, c in spoon_count.items() if c == top)} ({top})"))
        hits = {m.entry: sum(r.get("event_transfers_cost", 0) for g, r in m.history.items() if g <= gw)
                for m in self.active}
        if hits and max(hits.values()) > 0:
            top = max(hits.values())
            s.facts.append(("Most points spent on hits",
                            f"{join_names(by_entry[e].name for e, v in hits.items() if v == top)} (-{top})"))
        rich = max(self.active, key=lambda m: m.history[gw].get("value", 0))
        if rich.history[gw].get("value"):
            s.facts.append(("Most valuable squad", f"{rich.name} (£{rich.history[gw]['value'] / 10:.1f}m)"))
        return s


def build_report(client, config, gameweek=None):
    return ReportBuilder(client, config, gameweek).build()
