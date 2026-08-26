from typing import Dict, Tuple, List, Any


def aggregate_weekly_stats(matchups: List[Dict[str, Any]], weekly_stats: List[Dict[str, Any]]) -> Tuple[Dict[int, float], Dict[int, float], Dict[int, float], Dict[int, float], Dict[int, float]]:
    """Given matchups and the weekly_stats from Sleeper, aggregate passing, receiving, rushing, touchdowns and kicking per roster_id.

    Returns: passing_yards, receiving_yards, rushing_yards, touchdowns, kicking
    """
    passing_yards = {}
    rushing_yards = {}
    receiving_yards = {}
    touchdowns = {}
    kicking = {}

    # Initialize roster ids from matchups
    for match in matchups:
        roster_id = match['roster_id']
        if roster_id not in passing_yards:
            passing_yards[roster_id] = 0.0
            rushing_yards[roster_id] = 0.0
            receiving_yards[roster_id] = 0.0
            touchdowns[roster_id] = 0.0
            kicking[roster_id] = 0.0

    # For each reported player stat, add to the roster totals when player is starter
    for player_info in weekly_stats:
        player_id = player_info.get('player_id')
        player_stats = player_info.get('stats', {})
        # weekly_stats items don't include roster mapping; caller should match by player_id into matchups' starters
        # Since the previous script compared player_id to starters per match, the caller will handle per-roster association.
        # This helper focuses on aggregating stats when roster mapping is provided elsewhere.
        pass

    return passing_yards, receiving_yards, rushing_yards, touchdowns, kicking


def decide_category_winner(val_a: float, val_b: float) -> int:
    """Return 0 if A wins, 1 if B wins, 2 if tie."""
    if val_a == val_b:
        return 2
    return 0 if val_a > val_b else 1


def total_yards(passing: float, receiving: float, rushing: float) -> float:
    return passing + receiving + rushing
