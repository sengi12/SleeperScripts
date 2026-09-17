#!/usr/bin/env python3
"""
Player exposure / diversity profile across ALL of a Sleeper user's leagues.

Walks every league the user is in for a season, collects their roster in each,
and reports:

  * MOST OWNED   - players held in the most leagues (with how often they start)
  * LEAST OWNED  - players held in only one league (the unique holdings), by position
  * POSITION MIX - roster spots per position, and how many unique players fill them
  * TEAM MIX     - which NFL teams the user is most concentrated in
  * PER LEAGUE   - how much of each roster is unique to that league

Usage:
    python3 get_player_exposure.py Sengi12
    python3 get_player_exposure.py Sengi12 --season 2025 --top 25
    python3 get_player_exposure.py Sengi12 --all-leagues      # include pre-draft / complete
    python3 get_player_exposure.py Sengi12 --csv exposure.csv

Only needs `requests`.  Colour is automatic on a terminal (--no-color to disable).
players.json is cached next to the script and refreshed when older than a day.
"""
import argparse
import csv
import json
import os
import shutil
import sys
import textwrap
import time
from collections import Counter, defaultdict

import requests

SLEEPER = "https://api.sleeper.app/v1"
PLAYERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "players.json")
POS_ORDER = ["QB", "RB", "WR", "TE", "K", "DEF"]


def get(path):
    r = requests.get(f"{SLEEPER}/{path}", timeout=60)
    r.raise_for_status()
    return r.json()


def load_players(refresh=False):
    fresh = os.path.exists(PLAYERS_PATH) and time.time() - os.path.getmtime(PLAYERS_PATH) < 86400
    if fresh and not refresh:
        with open(PLAYERS_PATH) as f:
            return json.load(f)
    print("Downloading players.json ...", file=sys.stderr)
    players = get("players/nfl")
    with open(PLAYERS_PATH, "w") as f:
        json.dump(players, f, ensure_ascii=False)
    return players


def player_label(pid, players):
    p = players.get(pid)
    if not p:
        return pid, "?", ""
    if p.get("position") == "DEF":
        return f"{p.get('last_name') or pid} D/ST", "DEF", pid
    pos = p.get("position") or "?"
    if pos not in POS_ORDER:  # e.g. Travis Hunter is DB with WR eligibility: prefer the fantasy position
        pos = next((fp for fp in p.get("fantasy_positions") or [] if fp in POS_ORDER), pos)
    return p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(), pos, p.get("team") or "FA"


class Style:
    """ANSI styling; every code becomes '' when colour is off."""
    on = True
    codes = {"bold": "\033[1m", "dim": "\033[2m", "reset": "\033[0m", "cyan": "\033[36m", "green": "\033[32m",
             "yellow": "\033[33m", "red": "\033[31m", "magenta": "\033[35m", "blue": "\033[34m"}

    def __getattr__(self, name):
        return self.codes[name] if self.on else ""


S = Style()
WIDTH = max(96, min(140, shutil.get_terminal_size((120, 40)).columns))


def bar(frac, width=10, color=None):
    frac = max(0.0, min(1.0, frac))
    full = int(round(frac * width))
    col = color or (S.green if frac >= 0.66 else S.yellow if frac >= 0.33 else S.red)
    return f"{col}{'█' * full}{S.dim}{'░' * (width - full)}{S.reset}"


def rule(ch="─", color=None):
    return f"{color or S.dim}{ch * WIDTH}{S.reset}"


def section(title, note=""):
    print()
    print(f"{S.bold}{S.cyan} {title}{S.reset}" + (f"  {S.dim}{note}{S.reset}" if note else ""))
    print(rule())


def header_row(cols):
    print(f"{S.dim} {cols}{S.reset}")


def clip(text, n):
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


def wrap(items, indent, width=None):
    """Comma-join a list and wrap it under a hanging indent."""
    return textwrap.fill(", ".join(items), width=width or WIDTH, initial_indent=" " * indent,
                         subsequent_indent=" " * indent, break_long_words=False, break_on_hyphens=False)


def scan(user, season, all_leagues):
    leagues = get(f"user/{user['user_id']}/leagues/nfl/{season}") or []
    if not all_leagues:
        leagues = [l for l in leagues if l.get("status") in ("in_season", "drafting", "post_season")] or leagues
    holdings = []  # (league, roster)
    for lg in leagues:
        rosters = get(f"league/{lg['league_id']}/rosters") or []
        mine = next((r for r in rosters if r.get("owner_id") == user["user_id"]
                     or user["user_id"] in (r.get("co_owners") or [])), None)
        if mine:
            holdings.append((lg, mine))
        else:
            print(f"  (no roster in {lg['name']} - skipped)", file=sys.stderr)
    return holdings


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("user", help="Sleeper username or user_id")
    ap.add_argument("--season", help="NFL season (default: Sleeper's current season)")
    ap.add_argument("--top", type=int, default=20, help="rows in the MOST OWNED table (default 20)")
    ap.add_argument("--all-leagues", action="store_true", help="include pre-draft and completed leagues")
    ap.add_argument("--refresh-players", action="store_true", help="re-download players.json")
    ap.add_argument("--csv", help="write the full exposure table (every player) to this CSV")
    ap.add_argument("--no-color", action="store_true", help="plain text output")
    args = ap.parse_args(argv)
    S.on = (not args.no_color and sys.stdout.isatty() and not os.environ.get("NO_COLOR")) or bool(os.environ.get("FORCE_COLOR"))

    user = get(f"user/{args.user}")
    if not user:
        sys.exit(f"user {args.user!r} not found")
    season = args.season or get("state/nfl")["season"]
    players = load_players(args.refresh_players)
    holdings = scan(user, season, args.all_leagues)
    if not holdings:
        sys.exit("no rosters found")
    n = len(holdings)

    owned = defaultdict(list)      # pid -> [league names]
    started = Counter()            # pid -> leagues where starting
    spots = 0
    per_league = {}
    for lg, r in holdings:
        pids = [p for p in (r.get("players") or [])]
        spots += len(pids)
        per_league[lg["name"]] = set(pids)
        for pid in pids:
            owned[pid].append(lg["name"])
        for pid in r.get("starters") or []:
            if pid and pid != "0":
                started[pid] += 1

    rows_all = []
    for pid, lgs in owned.items():
        name, pos, team = player_label(pid, players)
        rows_all.append({"player": name, "pos": pos, "team": team, "leagues": len(lgs),
                         "pct": round(100 * len(lgs) / n, 1), "started": started[pid], "league_names": sorted(lgs)})
    rows_all.sort(key=lambda x: (-x["leagues"], -x["started"], POS_ORDER.index(x["pos"]) if x["pos"] in POS_ORDER else 9, x["player"]))

    unique = len(owned)
    diversity = unique / spots if spots else 0
    pos_of = {r["player"]: r["pos"] for r in rows_all}

    print()
    print(rule("═", S.bold))
    print(f"{S.bold} {user['display_name'].upper()}{S.reset} · {season} · {n} leagues · {spots} roster spots · {unique} unique players")
    print(f" diversity {bar(diversity, 24)} {S.bold}{diversity:.0%}{S.reset}   "
          f"{S.dim}(100% = no overlap · {100 / n:.0f}% = identical rosters){S.reset}")
    print(rule("═", S.bold))
    print(wrap([f"{i + 1}. {lg['name'].strip()}" for i, (lg, _) in enumerate(holdings)], 1))
    short = {lg["name"]: str(i + 1) for i, (lg, _) in enumerate(holdings)}   # league -> number, for compact "where" columns

    section("MOST OWNED", f"top {args.top} · one block per league held · starts = leagues where he is in the lineup")
    header_row(f"{'#':<3} {'PLAYER':<24}{'POS':<5}{'TEAM':<5}{'HELD':<{n + 2}}{'':<7}{'STARTS':<8}WHERE (league #)")
    shown = [r for r in rows_all[:args.top] if r["leagues"] > 1]
    for i, r in enumerate(shown, 1):
        frac = r["leagues"] / n
        held = f"{S.green if frac >= 0.5 else S.yellow}{'█' * r['leagues']}{S.dim}{'░' * (n - r['leagues'])}{S.reset}"
        scol = S.green if r["started"] == r["leagues"] else S.yellow if r["started"] else S.dim
        starts = f"{scol}{r['started']}/{r['leagues']:<{6}}{S.reset}"
        where = " ".join(sorted((short[x] for x in r["league_names"]), key=int))
        print(f" {i:<3} {clip(r['player'], 23):<24}{r['pos']:<5}{r['team']:<5}{held}  {r['pct']:>4.0f}%  {starts}{S.dim}{where}{S.reset}")
    if not shown:
        print(f" {S.dim}no player is held in more than one league{S.reset}")

    counts = Counter(r["leagues"] for r in rows_all)
    section("EXPOSURE SPREAD", "how many players you hold in exactly k leagues")
    biggest = max(counts.values())
    for k in sorted(counts, reverse=True):
        label = f"{k} league{'s' if k > 1 else ''}"
        print(f" {label:<11}{bar(counts[k] / biggest, 30, S.blue)} {counts[k]:>3}")

    section("LEAST OWNED", f"held in only 1 of {n} leagues · ★ = starting there")
    singles = [r for r in rows_all if r["leagues"] == 1]
    by_pos = defaultdict(list)
    for r in singles:
        by_pos[r["pos"]].append(f"{'★ ' if r['started'] else ''}{r['player']} ({r['team']}) [{short[r['league_names'][0]]}]")
    for pos in POS_ORDER + sorted(set(by_pos) - set(POS_ORDER)):
        if by_pos.get(pos):
            print(f" {S.bold}{pos:<4}{S.reset}{S.dim}{len(by_pos[pos]):>3}{S.reset}")
            print(wrap(by_pos[pos], 8))

    section("POSITION MIX", "share of all roster spots · diversity = unique players / spots at that position")
    pos_spots, pos_unique = Counter(), Counter()
    for r in rows_all:
        pos_spots[r["pos"]] += r["leagues"]
        pos_unique[r["pos"]] += 1
    header_row(f"{'POS':<5}{'SPOTS':>6}  {'OF ROSTER':<26}{'UNIQUE':>7}  DIVERSITY")
    for pos in POS_ORDER + sorted(set(pos_spots) - set(POS_ORDER)):
        if not pos_spots[pos]:
            continue
        share = pos_spots[pos] / spots
        div = pos_unique[pos] / pos_spots[pos]
        print(f" {pos:<5}{pos_spots[pos]:>6}  {bar(share, 20, S.blue)} {share:>4.0%} {pos_unique[pos]:>7}  {bar(div, 10)} {div:.0%}")

    section("TEAM MIX", "NFL teams you are most invested in (roster spots across all leagues)")
    team_spots, team_players = Counter(), defaultdict(set)
    for r in rows_all:
        team_spots[r["team"]] += r["leagues"]
        team_players[r["team"]].add(r["player"])
    top_team = team_spots.most_common(1)[0][1]
    header_row(f"{'TEAM':<5}{'SPOTS':>6}  {'':<23}PLAYERS")
    for team, cnt in team_spots.most_common(12):
        names = sorted(team_players[team], key=lambda p: (POS_ORDER.index(pos_of.get(p, "?")) if pos_of.get(p) in POS_ORDER else 9, p))
        print(f" {team:<5}{cnt:>6}  {bar(cnt / top_team, 16, S.magenta)} {100 * cnt / spots:>3.0f}%  {S.dim}{clip(', '.join(names), WIDTH - 36)}{S.reset}")

    heavy = max(3, n // 2)
    section("PER LEAGUE", f"how much of each roster is unique to that league · right column = players held in {heavy}+ leagues")
    header_row(f"{'#':<3} {'LEAGUE':<30}{'ROSTER':>7}{'UNIQUE':>8}  {'':<17}SHARED CORE")
    for i, (lg, r) in enumerate(holdings, 1):
        pids = per_league[lg["name"]]
        uniq = sum(1 for p in pids if len(owned[p]) == 1)
        frac = uniq / len(pids) if pids else 0
        shared = sorted((player_label(p, players)[0] for p in pids if len(owned[p]) >= heavy), key=str)
        print(f" {i:<3} {clip(lg['name'].strip(), 29):<30}{len(pids):>7}{uniq:>8}  {bar(frac, 10)} {frac:>4.0%}  {S.dim}{clip(', '.join(shared), WIDTH - 70)}{S.reset}")
    print(rule("═", S.bold))

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["player", "pos", "team", "leagues", "share_pct", "starting_in", "league_names"])
            for r in rows_all:
                w.writerow([r["player"], r["pos"], r["team"], r["leagues"], r["pct"], r["started"], "; ".join(r["league_names"])])
        print(f"\nCSV written: {args.csv}")


if __name__ == "__main__":
    main()
