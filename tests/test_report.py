"""Runs the whole report against a fake, made-up league (no internet needed).

    python -m unittest discover tests
"""

import json
import random
import unittest

from fpl_weekly.render import to_markdown, to_teams_payload
from fpl_weekly.stats import build_report

GW = 6
N_PLAYERS = 60


class FakeClient:
    """Mimics the shape of the real FPL API responses with random data."""

    def __init__(self, n_managers=8, seed=1):
        rng = random.Random(seed)
        self.rng = rng
        self.entries = [1000 + i for i in range(n_managers)]
        firsts = ["Alex", "Sam", "Jo", "Chris", "Pat", "Sam", "Robin", "Kim", "Lee", "Max", "Ali", "Ash",
                  "Dev", "Eli", "Fin", "Gus"]
        self.people = {e: f"{firsts[i % len(firsts)]} Tester{i}" for i, e in enumerate(self.entries)}
        self.teams = {e: f"FC Fake {i}" for i, e in enumerate(self.entries)}
        self.live_pts = {g: {p: rng.choice([0, 1, 2, 2, 2, 3, 5, 6, 8, 12, 15]) for p in range(1, N_PLAYERS + 1)}
                         for g in range(1, GW + 1)}
        self.squads = {(e, g): rng.sample(range(1, N_PLAYERS + 1), 15) for e in self.entries
                       for g in range(1, GW + 1)}
        self.chips = {(self.entries[0], GW): "3xc", (self.entries[1], GW): "bboost",
                      (self.entries[2], GW): "wildcard"}
        self.history = {}
        for e in self.entries:
            total, rows = 0, []
            start = 1 if e != self.entries[-1] else 3  # one late joiner
            for g in range(start, GW + 1):
                sq = self.squads[(e, g)]
                pts = sum(self.live_pts[g][p] for p in sq[:11]) + self.live_pts[g][sq[0]]
                cost = rng.choice([0, 0, 0, 4, 8])
                total += pts - cost
                rows.append({"event": g, "points": pts, "total_points": total, "rank": 1,
                             "overall_rank": rng.randint(1000, 9_000_000), "bank": 5,
                             "value": rng.randint(1000, 1050),
                             "event_transfers": rng.choice([0, 1, 2, 3]), "event_transfers_cost": cost,
                             "points_on_bench": sum(self.live_pts[g][p] for p in sq[11:])})
            self.history[e] = rows

    def bootstrap(self):
        return {
            "events": [{"id": g, "finished": g <= GW, "data_checked": g <= GW,
                        "average_entry_score": 50, "highest_score": 120} for g in range(1, 39)],
            "elements": [{"id": p, "web_name": f"Player{p}"} for p in range(1, N_PLAYERS + 1)],
        }

    def live(self, gw):
        return {"elements": [{"id": p, "stats": {"total_points": v, "minutes": 90 if v else 0}}
                             for p, v in self.live_pts[gw].items()]}

    def entry_history(self, e):
        return {"current": self.history[e], "chips": []}

    def picks(self, e, gw):
        if (e, gw) not in self.squads or not any(r["event"] == gw for r in self.history[e]):
            return None
        sq = self.squads[(e, gw)]
        return {
            "active_chip": self.chips.get((e, gw)),
            "automatic_subs": [{"element_in": sq[11], "element_out": sq[10]}],
            "picks": [{"element": p, "position": i + 1, "multiplier": 1,
                       "is_captain": i == 0, "is_vice_captain": i == 1} for i, p in enumerate(sq)],
        }

    def transfers(self, e):
        return [{"event": GW, "element_in": self.squads[(e, GW)][2], "element_out": 59},
                {"event": GW - 1, "element_in": 1, "element_out": 2}]

    def classic_standings(self, league_id):
        return {"name": "Fake Office League"}, [
            {"entry": e, "entry_name": self.teams[e], "player_name": self.people[e]} for e in self.entries]

    def h2h_standings(self, league_id):
        return {"name": f"H2H {league_id}"}, [
            {"entry": e, "entry_name": self.teams[e], "player_name": self.people[e]} for e in self.entries]

    def h2h_matches(self, league_id):
        out = []
        pool = self.entries + [None] if len(self.entries) % 2 else list(self.entries)
        for g in range(1, GW + 1):
            order = pool[:]
            random.Random(g * league_id).shuffle(order)
            for a, b in zip(order[::2], order[1::2]):
                if a is None:
                    a, b = b, a
                out.append({"event": g, "is_knockout": False,
                            "entry_1_entry": a, "entry_1_name": self.teams[a],
                            "entry_1_player_name": self.people[a],
                            "entry_1_points": self.rng.randint(20, 110),
                            "entry_2_entry": b, "entry_2_name": self.teams.get(b, "AVERAGE"),
                            "entry_2_player_name": self.people.get(b, "AVERAGE"),
                            "entry_2_points": self.rng.randint(20, 110)})
        return out


CONFIG = {"classic_league_id": 1, "h2h_leagues": [{"id": 2, "label": "Main H2H"},
                                                   {"id": 3, "label": "Champions H2H"}],
          "title": None, "nicknames": {}}


class ReportTest(unittest.TestCase):
    def check(self, client, gameweek=None):
        report = build_report(client, CONFIG, gameweek)
        md = to_markdown(report)
        payload = to_teams_payload(report)
        size = len(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
        self.assertLess(size, 28_000, "Teams cards must stay under ~28KB")
        self.assertIn("Manager of the Week", md)
        self.assertNotIn("| |", md)  # no blank table headers
        self.assertLess(len(report.headline), 90)
        self.assertEqual(payload["attachments"][0]["content"]["type"], "AdaptiveCard")
        return report, md

    def test_latest_gameweek(self):
        report, md = self.check(FakeClient())
        self.assertEqual(report.gameweek, GW)
        for heading in ("Fake Office League", "Main H2H", "Champions H2H", "Also this week",
                        "| Pos | Manager | GW | Total | +/- |", "| Home | Score | Away |"):
            self.assertIn(heading, md)
        self.assertNotIn("Season So Far", md)
        # duplicate first names fall back to full names
        self.assertIn("Sam Tester1", md)

    def test_odd_numbered_league_and_big_league(self):
        self.check(FakeClient(n_managers=7, seed=3))
        self.check(FakeClient(n_managers=16, seed=4))

    def test_first_gameweek(self):
        self.check(FakeClient(seed=5), gameweek=1)

    def test_nicknames(self):
        client = FakeClient()
        cfg = dict(CONFIG, nicknames={str(client.entries[0]): "The Gaffer"})
        report = build_report(client, cfg)
        self.assertIn("The Gaffer", to_markdown(report))


if __name__ == "__main__":
    unittest.main()


class FakeChallenge:
    def classic_standings(self, league_id):
        return {"name": "Fake Challenge"}, [
            {"rank": 1, "last_rank": 2, "player_name": "Alex Tester0", "event_total": 61, "total": 481},
            {"rank": 2, "last_rank": 1, "player_name": "Outsider Person", "event_total": 40, "total": 470},
        ]


class FakeDraft:
    def draft_league(self, league_id):
        return {
            "league": {"name": "Fake Draft", "scoring": "h"},
            "league_entries": [{"id": i, "player_first_name": f, "player_last_name": "Tester"}
                               for i, f in enumerate(["Dee", "Em", "Gee", "Aitch"], start=1)],
            "matches": [{"event": GW, "finished": True, "league_entry_1": 1, "league_entry_1_points": 50,
                         "league_entry_2": 2, "league_entry_2_points": 41},
                        {"event": GW, "finished": True, "league_entry_1": 3, "league_entry_1_points": 30,
                         "league_entry_2": 4, "league_entry_2_points": 30}],
            "standings": [{"rank": i, "league_entry": i, "total": 20 - i, "matches_won": 5,
                           "matches_drawn": 1, "matches_lost": 1} for i in range(1, 5)],
        }


EXTRA_CONFIG = dict(CONFIG, extra_leagues=[{"game": "challenge", "id": 9, "label": "FPL Challenge"},
                                           {"game": "draft", "id": 8, "label": "FPL Draft"},
                                           {"game": "draft", "id": None, "label": "Not set up"}],
                    site_url="https://example.github.io/ff/")
EXTRAS = {"challenge": FakeChallenge(), "draft": FakeDraft()}


class ExtraLeaguesAndSiteTest(unittest.TestCase):
    def test_extra_leagues_and_site(self):
        import tempfile
        from pathlib import Path
        from fpl_weekly.render import to_teams_payload
        from fpl_weekly.site import write_site

        report = build_report(FakeClient(), EXTRA_CONFIG, extra_clients=EXTRAS)
        md = to_markdown(report)
        self.assertIn("## FPL Challenge", md)
        self.assertIn("## FPL Draft", md)
        self.assertNotIn("Not set up", md)
        self.assertIn("Alex leads on 481", md)   # same person -> same display name

        payload = to_teams_payload(report, "https://example.github.io/ff/gw/6.html")
        card = payload["attachments"][0]["content"]
        self.assertEqual(card["actions"][0]["url"], "https://example.github.io/ff/gw/6.html")

        with tempfile.TemporaryDirectory() as d:
            page = write_site(report, d).read_text()
            self.assertIn("<h1>", page)
            self.assertIn("FPL Draft", page)
            self.assertIn('class="score"', page)
            self.assertTrue((Path(d) / "index.html").exists())

    def test_broken_extra_league_is_skipped(self):
        class Broken:
            def classic_standings(self, league_id):
                raise RuntimeError("boom")
        report = build_report(FakeClient(), EXTRA_CONFIG, extra_clients={"challenge": Broken(), "draft": FakeDraft()})
        self.assertNotIn("FPL Challenge", to_markdown(report))


class InsightsTest(unittest.TestCase):
    def test_insights_present_and_varied(self):
        report = build_report(FakeClient(n_managers=21), EXTRA_CONFIG, extra_clients=EXTRAS)
        section = next(s for s in report.sections if s.title == "Behind the numbers")
        kinds = [i.kind or i.label for i in section.insights]
        self.assertEqual(len(kinds), len(set(kinds)))
        self.assertLessEqual(len(section.insights), 6)
        self.assertTrue(report.card_insight)
