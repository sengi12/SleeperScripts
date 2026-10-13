#!/usr/bin/env python3
"""
Weekly high scores: walk a league week by week, name the team that scored the most each
week, then tally the season — who took the most weeks, with the weeks they took.

    python get_weekly_high_scores.py                       # the default league, this season
    python get_weekly_high_scores.py -id 1312146993191096320
    python get_weekly_high_scores.py -w 5                  # through week 5 only
    python get_weekly_high_scores.py --playoffs            # the playoff weeks too
    python get_weekly_high_scores.py --all-seasons         # every season back through previous_league_id

A week nobody has scored in yet (the week in progress before kickoff, or the weeks ahead) is
skipped, so the script can run any day of the season and stop where the season has. A tie at
the top counts for every team tied.
"""
import argparse
import sys
from collections import defaultdict

from sleeper_client import SleeperClient


def roster_names(client, league_id):
    """roster_id -> '@owner (Team Name)' for the league as it stands now."""
    users = {u['user_id']: u for u in client.get_users(league_id)}
    names = {}
    for r in client.get_rosters(league_id):
        u = users.get(r.get('owner_id')) or {}
        handle = u.get('display_name') or f"roster {r['roster_id']}"
        team = (u.get('metadata') or {}).get('team_name')
        names[r['roster_id']] = f"@{handle}" + (f" ({team})" if team else '')
    return names


def regular_season_weeks(league):
    """1 .. the week before the playoffs start (the league's own setting; 14 if it has none)."""
    start = (league.get('settings') or {}).get('playoff_week_start') or 15
    return list(range(1, int(start)))


def last_week(league):
    """The last week the league plays, playoffs included (Sleeper's leagues end at 17 or 18)."""
    settings = league.get('settings') or {}
    start = int(settings.get('playoff_week_start') or 15)
    rounds = {4: 2, 6: 3, 8: 3, 12: 4, 16: 4}.get(int(settings.get('playoff_teams') or 6), 3)
    return min(18, start + rounds - 1)


def walk_season(client, league, names, through_week=None, playoffs=False):
    """Yield (week, [(roster_id, points) sorted high → low]) for every week with a score in it."""
    weeks = regular_season_weeks(league)
    if playoffs:
        weeks = list(range(1, last_week(league) + 1))
    if through_week:
        weeks = [w for w in weeks if w <= int(through_week)]
    for week in weeks:
        matchups = client.get_matchups(league['league_id'], week) or []
        scores = [(m['roster_id'], float(m.get('points') or 0)) for m in matchups if m.get('roster_id') in names]
        if not scores or all(p == 0 for _, p in scores):
            break   # the season has not reached this week
        scores.sort(key=lambda x: -x[1])
        yield week, scores


def report_season(client, league, names, through_week=None, playoffs=False):
    print(f"\n{league['name']} — {league['season']}")
    print('=' * 60)
    tally = defaultdict(list)
    points_for = defaultdict(float)
    weeks_seen = 0
    for week, scores in walk_season(client, league, names, through_week, playoffs):
        weeks_seen += 1
        top = scores[0][1]
        winners = [rid for rid, p in scores if p == top]
        runner = next(((rid, p) for rid, p in scores if p < top), None)
        label = 'Week %2d' % week
        if week >= int((league.get('settings') or {}).get('playoff_week_start') or 99):
            label += ' (playoffs)'
        who = ' & '.join(names[r] for r in winners)
        margin = f"  ·  next {names[runner[0]]} {runner[1]:.2f} (by {top - runner[1]:.2f})" if runner else ''
        print(f"{label}: {who} — {top:.2f}{margin}")
        for rid in winners:
            tally[rid].append(week)
        for rid, p in scores:
            points_for[rid] += p
    if not weeks_seen:
        print('No scores yet this season.')
        return
    print('-' * 60)
    print(f"Season tally after {weeks_seen} week{'s' if weeks_seen != 1 else ''}: weeks as the top scorer")
    order = sorted(names, key=lambda r: (-len(tally[r]), -points_for[r]))
    width = max(len(names[r]) for r in names)
    for rid in order:
        n = len(tally[rid])
        if not n and points_for[rid] == 0:
            continue
        wks = ', '.join(str(w) for w in tally[rid]) if n else '—'
        print(f"  {names[rid]:<{width}}  {n:>2}  {wks:<24}  {points_for[rid]:>8.2f} pts total")


def main():
    parser = argparse.ArgumentParser(
        description="Weekly high scores\n\tWho scored the most each week, and the season's tally",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # league_id = "1312146993191096320" # Originally From Ohio Dynasty League (2026)
    # league_id = "1389348066355609601" # BAFL 2026
    # league_id = "1391085624445906944" # Last Man Standing Eliminator (2026)
    parser.add_argument('-id', '--league_id', default="1312146993191096320", required=False,
                        help='League ID (default: Originally From Ohio Dynasty League, 2026)')
    parser.add_argument('-w', '--week', type=int, help='Only through this week', required=False)
    parser.add_argument('--playoffs', action='store_true', help='Include the playoff weeks (regular season only by default)')
    parser.add_argument('--all-seasons', action='store_true', help="Walk every season back through the league's history")
    args = parser.parse_args()

    client = SleeperClient()
    league_id = args.league_id
    while league_id and str(league_id) != '0':
        league = client.get_league(league_id)
        if not league or 'season' not in league:
            print(f"No league found for id {league_id}", file=sys.stderr)
            return 1
        names = roster_names(client, league_id)
        report_season(client, league, names, args.week, args.playoffs)
        if not args.all_seasons:
            break
        league_id = league.get('previous_league_id')
    return 0


if __name__ == '__main__':
    sys.exit(main())
