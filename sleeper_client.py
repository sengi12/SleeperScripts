import requests
import json
from typing import Dict, Any


class SleeperClient:
    """Simple wrapper around commonly-used Sleeper API calls."""
    BASE = 'https://api.sleeper.app/v1'

    def __init__(self):
        self.session = requests.Session()

    def get_players(self) -> Dict[str, Any]:
        return self.session.get(f"{self.BASE}/players/nfl").json()

    def save_players(self, path: str = 'players.json') -> None:
        data = self.get_players()
        with open(path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def load_players(self, path: str = 'players.json') -> Dict[str, Any]:
        with open(path, 'r') as f:
            return json.load(f)

    def get_league(self, league_id: str) -> Dict[str, Any]:
        return self.session.get(f"{self.BASE}/league/{league_id}").json()

    def get_users(self, league_id: str):
        return self.session.get(f"{self.BASE}/league/{league_id}/users/").json()

    def get_rosters(self, league_id: str):
        return self.session.get(f"{self.BASE}/league/{league_id}/rosters/").json()

    def get_matchups(self, league_id: str, week: int):
        return self.session.get(f"{self.BASE}/league/{league_id}/matchups/{week}").json()

    def get_weekly_stats(self, season: str, week: int):
        # Note: this endpoint differs from the "players" base
        return self.session.get(f"https://api.sleeper.com/stats/nfl/{season}/{week}?season_type=regular").json()
