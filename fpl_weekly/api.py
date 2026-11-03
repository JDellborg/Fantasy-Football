"""Tiny client for the public Fantasy Premier League API (no login needed)."""

import json
import time
import urllib.error
import urllib.request

BASE_URL = "https://fantasy.premierleague.com/api"
CHALLENGE_URL = "https://fplchallenge.premierleague.com/api"
DRAFT_URL = "https://draft.premierleague.com/api"
USER_AGENT = "Mozilla/5.0 (compatible; office-fpl-weekly/1.0)"


class FPLError(RuntimeError):
    pass


class FPLClient:
    def __init__(self, base=BASE_URL, pause=0.25, retries=5):
        self.base = base
        self.pause = pause
        self.retries = retries
        self._cache = {}

    def get(self, path):
        if path in self._cache:
            return self._cache[path]
        url = self.base + path
        last_error = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.load(resp)
                self._cache[path] = data
                time.sleep(self.pause)
                return data
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise FPLError(f"Not found: {url}") from e
                last_error = e  # 503 = "game is being updated", 429 = slow down
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                last_error = e
            time.sleep(min(2 ** (attempt + 1), 30))
        raise FPLError(f"Failed to fetch {url}: {last_error}")

    # --- endpoints -------------------------------------------------------
    def bootstrap(self):
        return self.get("/bootstrap-static/")

    def event_status(self):
        return self.get("/event-status/")

    def fixtures(self, gw):
        return self.get(f"/fixtures/?event={gw}")

    def live(self, gw):
        return self.get(f"/event/{gw}/live/")

    def entry_history(self, entry_id):
        return self.get(f"/entry/{entry_id}/history/")

    def picks(self, entry_id, gw):
        try:
            return self.get(f"/entry/{entry_id}/event/{gw}/picks/")
        except FPLError:
            return None  # manager had no team that week

    def transfers(self, entry_id):
        return self.get(f"/entry/{entry_id}/transfers/")

    def _paged_standings(self, kind, league_id):
        results, page, league = [], 1, None
        while True:
            data = self.get(f"/leagues-{kind}/{league_id}/standings/?page_standings={page}")
            league = data["league"]
            results.extend(data["standings"]["results"])
            if not data["standings"].get("has_next"):
                break
            page += 1
        return league, results

    def classic_standings(self, league_id):
        return self._paged_standings("classic", league_id)

    def h2h_standings(self, league_id):
        return self._paged_standings("h2h", league_id)

    def draft_league(self, league_id):
        return self.get(f"/league/{league_id}/details")

    def h2h_matches(self, league_id):
        results, page = [], 1
        while True:
            data = self.get(f"/leagues-h2h-matches/league/{league_id}/?page={page}")
            results.extend(data.get("results", []))
            if not data.get("has_next"):
                break
            page += 1
        return results
