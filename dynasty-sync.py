#!/usr/bin/env python3
"""
sleeper_sync.py  -  Originally From Ohio Dynasty League  ->  Google Sheets
 
Pulls the complete league history from the Sleeper API (walking the
previous_league_id chain back to 2019) and rewrites every derivable stat on
the "Regular Season", "Playoffs" and "Trades" tabs of the league spreadsheet.
 
It NEVER touches:
  * any schedule tab ("Updated Schedule", "Old Schedule", "* Schedule")
  * Brackets, Drafts, Polls, Survivor History
  * manual cells on the tabs it does write: Trend emoji, Dues columns,
    payout block, the 25'/26' draft-order list, historical Avg Team Age
 
Usage
-----
  python sleeper_sync.py                 # full sync (opens browser first run)
  python sleeper_sync.py --dry-run       # compute everything, write nothing,
                                         # dump payload to dry_run_payload.json
  python sleeper_sync.py --no-cache      # ignore the local API cache
 
First-time setup: see README.md (Google OAuth client + `pip install -r requirements.txt`).
"""
from __future__ import annotations
 
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
 
import requests
 
# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
SLEEPER_USERNAME = "sengi12"
LEAGUE_NAME = "Originally from Ohio Dynasty League"   # case-insensitive match
# If you'd rather pin the league, set this and LEAGUE_NAME is ignored.
CURRENT_LEAGUE_ID: str | None = None
 
SPREADSHEET_ID = "1cXokl2AEYQT3BJx4Ep4iSApAzbdLO_8H9ZztP7Hcp44"
SHEET_REG = "Regular Season"
SHEET_PO = "Playoffs"
SHEET_TRADES = "Trades"
PROTECTED_SHEET_PATTERNS = [r"schedule", r"^brackets$", r"^drafts$", r"^polls$", r"^survivor"]
 
# Google OAuth files (see README)
OAUTH_CLIENT_FILE = "credentials.json"      # downloaded from Google Cloud console
OAUTH_TOKEN_FILE = "authorized_user.json"   # created automatically on first run
 
CACHE_DIR = Path(".sleeper_cache")
SLEEPER = "https://api.sleeper.app/v1"
 
# A roster slot whose owner_id is null for a season (e.g. an orphaned team)
# is credited to whoever owned that roster_id the previous season.  Add
# explicit overrides here as {(season, roster_id): "<sleeper user_id>"} if needed.
ORPHAN_OVERRIDES: dict[tuple[int, int], str] = {}
 
# Rows on the Best Regular Seasons list
BEST_SEASONS_ROWS = 20
 
 
# ----------------------------------------------------------------------------
# Sleeper client
# ----------------------------------------------------------------------------
class Sleeper:
    def __init__(self, use_cache: bool = True):
        self.use_cache = use_cache
        CACHE_DIR.mkdir(exist_ok=True)
        self.s = requests.Session()
 
    def get(self, path: str, cacheable: bool = True):
        f = CACHE_DIR / (path.strip("/").replace("/", "_") + ".json")
        if cacheable and self.use_cache and f.exists():
            return json.loads(f.read_text())
        for attempt in range(4):
            r = self.s.get(SLEEPER + path, timeout=30)
            if r.status_code == 404:
                data = None
                break
            if r.ok:
                data = r.json()
                break
            time.sleep(1.5 * (attempt + 1))
        else:
            r.raise_for_status()
        if cacheable:
            f.write_text(json.dumps(data))
        return data
 
 
def find_league_chain(api: Sleeper) -> list[dict]:
    """Return leagues newest -> oldest."""
    if CURRENT_LEAGUE_ID:
        lid = CURRENT_LEAGUE_ID
    else:
        user = api.get(f"/user/{SLEEPER_USERNAME}", cacheable=False)
        if not user:
            sys.exit(f"Sleeper user {SLEEPER_USERNAME!r} not found")
        season = dt.date.today().year
        lid = None
        for yr in (season, season - 1):
            for lg in api.get(f"/user/{user['user_id']}/leagues/nfl/{yr}", cacheable=False) or []:
                if lg["name"].strip().lower() == LEAGUE_NAME.strip().lower():
                    lid = lg["league_id"]
                    break
            if lid:
                break
        if not lid:
            sys.exit(f"League {LEAGUE_NAME!r} not found for {SLEEPER_USERNAME}")
    chain = []
    while lid and lid != "0":
        lg = api.get(f"/league/{lid}", cacheable=False)   # status changes; never cache
        chain.append(lg)
        lid = lg.get("previous_league_id")
    return chain
 
 
# ----------------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------------
class Season:
    def __init__(self, lg: dict):
        self.league = lg
        self.year = int(lg["season"])
        self.id = lg["league_id"]
        s = lg["settings"]
        self.complete = lg["status"] == "complete"
        self.in_progress = lg["status"] == "in_season"
        self.playoff_start = s.get("playoff_week_start") or 15
        self.median = bool(s.get("league_average_match"))
        self.last_scored = s.get("last_scored_leg") or 0
        self.started = False                         # any regular-season game scored yet?
        self.users: dict[str, dict] = {}
        self.rosters: list[dict] = []
        self.roster_owner: dict[int, str] = {}      # roster_id -> user_id
        self.matchups: dict[int, list] = {}
        self.trades: list[dict] = []
        self.winners: list[dict] = []
        self.losers: list[dict] = []
 
 
def load_seasons(api: Sleeper, chain: list[dict]) -> list[Season]:
    seasons = [Season(lg) for lg in reversed(chain)]   # oldest first
    prev_owner: dict[int, str] = {}
    for sn in seasons:
        L = sn.id
        fresh = not sn.complete                        # re-fetch live seasons
        sn.users = {u["user_id"]: u for u in api.get(f"/league/{L}/users", cacheable=not fresh) or []}
        sn.rosters = api.get(f"/league/{L}/rosters", cacheable=not fresh) or []
        for r in sn.rosters:
            rid = r["roster_id"]
            owner = r.get("owner_id") or ORPHAN_OVERRIDES.get((sn.year, rid)) or prev_owner.get(rid)
            if not owner:
                owner = f"roster{rid}"
            sn.roster_owner[rid] = owner
        prev_owner = dict(sn.roster_owner)
        sn.started = any((r["settings"].get("wins", 0) + r["settings"].get("losses", 0)) > 0 for r in sn.rosters)
        if not sn.complete and not sn.in_progress:
            continue                                    # pre-draft: nothing to score yet
        max_week = sn.last_scored if sn.complete else 18
        for w in range(1, max_week + 1):
            m = api.get(f"/league/{L}/matchups/{w}", cacheable=not fresh)
            if m:
                sn.matchups[w] = m
            t = api.get(f"/league/{L}/transactions/{w}", cacheable=not fresh) or []
            sn.trades += [x for x in t if x["type"] == "trade" and x["status"] == "complete"]
        if sn.complete:
            sn.winners = api.get(f"/league/{L}/winners_bracket") or []
            sn.losers = api.get(f"/league/{L}/losers_bracket") or []
    return seasons
 
 
class Team:
    def __init__(self, uid: str):
        self.uid = uid
        self.name = uid
        self.seasons: dict[int, dict] = {}   # year -> per-season dict
        self.trades: dict[int, int] = defaultdict(int)
        self.playoff_w = 0
        self.playoff_l = 0
        self.titles: list[int] = []
        self.runner_ups: list[int] = []
        self.appearances: list[int] = []
        self.byes: list[tuple[int, bool]] = []       # (year, was_1_seed)
        self.toilet: list[int] = []
        self.best_week = None    # dict(year, week, score, mvp, mvp_score)
        self.worst_week = None
        self.best_start = None   # dict(player, year, week, score)
        self.worst_start = None
        self.age_current = None
 
    @property
    def wins(self): return sum(s["w"] for s in self.seasons.values())
    @property
    def losses(self): return sum(s["l"] for s in self.seasons.values())
    @property
    def pf(self): return round(sum(s["pf"] for s in self.seasons.values()), 2)
    @property
    def pa(self): return round(sum(s["pa"] for s in self.seasons.values()), 2)
    @property
    def win_pct(self):
        g = self.wins + self.losses
        return self.wins / g if g else 0.0
 
 
def fpts(settings: dict, key: str) -> float:
    return (settings.get(key) or 0) + (settings.get(key + "_decimal") or 0) / 100.0
 
 
def ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1:'st',2:'nd',3:'rd'}.get(n % 10,'th')}"
 
 
def yr_label(year: int) -> str:
    return f"{year % 100:02d}'"
 
 
# ----------------------------------------------------------------------------
# Stats engine
# ----------------------------------------------------------------------------
def compute(seasons: list[Season], players: dict) -> tuple[dict[str, Team], list[Season]]:
    teams: dict[str, Team] = {}
    scored = [s for s in seasons if s.matchups or s.started or (s.in_progress and s.trades)]
 
    def team(uid: str) -> Team:
        if uid not in teams:
            teams[uid] = Team(uid)
        return teams[uid]
 
    # canonical display names = most recent season the user appears in
    for sn in seasons:
        for rid, uid in sn.roster_owner.items():
            u = sn.users.get(uid)
            if u:
                team(uid).name = u.get("display_name") or u.get("username") or uid
 
    for sn in scored:
        # ---- regular season record: from roster settings (already includes median games)
        for r in sn.rosters:
            uid = sn.roster_owner[r["roster_id"]]
            st = r["settings"]
            t = team(uid)
            t.seasons[sn.year] = dict(
                w=st.get("wins", 0), l=st.get("losses", 0), t=st.get("ties", 0),
                pf=fpts(st, "fpts"), pa=fpts(st, "fpts_against"),
                roster_id=r["roster_id"], champ=False, runner_up=False,
                result="-", score_rank=None, standing=None,
            )
        # ---- scoring rank / regular-season standing (wins, then PF)
        yr_teams = [(uid, t.seasons[sn.year]) for uid, t in teams.items() if sn.year in t.seasons] if sn.started else []
        for i, (uid, s) in enumerate(sorted(yr_teams, key=lambda x: -x[1]["pf"]), 1):
            s["score_rank"] = i
        for i, (uid, s) in enumerate(sorted(yr_teams, key=lambda x: (-x[1]["w"], -x[1]["pf"])), 1):
            s["standing"] = i
        # ---- weekly performances (all scored weeks, incl. playoffs, like the sheet)
        for w, ms in sn.matchups.items():
            if sn.complete and w > sn.last_scored:
                continue
            for m in ms:
                pts = m.get("points") or 0
                if not pts:
                    continue
                uid = sn.roster_owner[m["roster_id"]]
                t = team(uid)
                starters = [p for p in (m.get("starters") or []) if p and p != "0"]
                spts = m.get("starters_points") or []
                pairs = list(zip(starters, spts))
                if pairs:
                    top = max(pairs, key=lambda x: x[1])
                    low = min(pairs, key=lambda x: x[1])
                else:
                    top = low = (None, 0.0)
                rec = dict(year=sn.year, week=w, score=round(pts, 2),
                           mvp=pname(players, top[0]), mvp_score=top[1],
                           lvp=pname(players, low[0]), lvp_score=low[1])
                if t.best_week is None or pts > t.best_week["score"]:
                    t.best_week = rec
                if t.worst_week is None or pts < t.worst_week["score"]:
                    t.worst_week = rec
                for pid, p in pairs:
                    cand = dict(player=pname(players, pid), year=sn.year, week=w, score=p)
                    if t.best_start is None or p > t.best_start["score"]:
                        t.best_start = cand
                    if t.worst_start is None or p < t.worst_start["score"]:
                        t.worst_start = cand
        # ---- trades
        for tr in sn.trades:
            for rid in tr.get("roster_ids") or []:
                team(sn.roster_owner[rid]).trades[sn.year] += 1
        # ---- playoffs
        if sn.complete and sn.winners:
            in_playoffs = {g[k] for g in sn.winners for k in ("t1", "t2") if isinstance(g.get(k), int)}
            r1 = {g[k] for g in sn.winners if g["r"] == 1 for k in ("t1", "t2") if isinstance(g.get(k), int)}
            byes = in_playoffs - r1
            top_seed = None
            # 1-seed = bye team with best standing
            for rid in byes:
                s = teams[sn.roster_owner[rid]].seasons[sn.year]
                if top_seed is None or s["standing"] < teams[sn.roster_owner[top_seed]].seasons[sn.year]["standing"]:
                    top_seed = rid
            for rid in in_playoffs:
                t = team(sn.roster_owner[rid])
                t.appearances.append(sn.year)
                t.seasons[sn.year]["result"] = "Rd 1"
            for rid in byes:
                team(sn.roster_owner[rid]).byes.append((sn.year, rid == top_seed))
            for g in sn.winners:
                if g.get("w") is None:
                    continue
                if g.get("p") in (3, 5):               # 3rd/5th-place games don't count (matches the sheet)
                    continue
                team(sn.roster_owner[g["w"]]).playoff_w += 1
                team(sn.roster_owner[g["l"]]).playoff_l += 1
                if "p" not in g:                       # advancing game: both teams reached this round
                    for k in ("w", "l"):
                        team(sn.roster_owner[g[k]]).seasons[sn.year]["result"] = f"Rd {g['r']}"
                if g.get("p") == 1:
                    tw, tl = team(sn.roster_owner[g["w"]]), team(sn.roster_owner[g["l"]])
                    tw.titles.append(sn.year); tw.seasons[sn.year].update(champ=True, result="🏆")
                    tl.runner_ups.append(sn.year); tl.seasons[sn.year].update(runner_up=True, result="🥈")
            for g in sn.losers:
                if g.get("p") == 1 and g.get("w") is not None:   # toilet bowl game
                    for k in ("t1", "t2"):
                        team(sn.roster_owner[g[k]]).toilet.append(sn.year)
 
    # ---- current-season average roster age
    cur = seasons[-1]
    for r in cur.rosters:
        ages = [players.get(p, {}).get("age") for p in (r.get("players") or [])]
        ages = [a for a in ages if a]
        if ages:
            team(cur.roster_owner[r["roster_id"]]).age_current = round(sum(ages) / len(ages), 1)
    return teams, scored
 
 
def pname(players: dict, pid) -> str:
    if not pid:
        return ""
    p = players.get(str(pid))
    if not p:
        return str(pid)
    return f"{p.get('first_name','')} {p.get('last_name','')}".strip() or str(pid)
 
 
# ----------------------------------------------------------------------------
# Sheet payload builders   (return {sheet: [(a1_range, values)]})
# ----------------------------------------------------------------------------
def read_grid(ws) -> list[list[str]]:
    """All values as strings, every row padded to the same width (+ slack)."""
    grid = [list(r) for r in ws.get_all_values()]
    w = max((len(r) for r in grid), default=0) + 10
    for r in grid:
        r.extend([""] * (w - len(r)))
    return grid
 
 
def col_letter(i: int) -> str:          # 1-based
    s = ""
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s
 
 
def col_index(letter: str) -> int:
    n = 0
    for ch in letter:
        n = n * 26 + ord(ch) - 64
    return n
 
 
def rec_str(s: dict) -> str:
    r = f"{s['w']}-{s['l']}" + (f"-{s['t']}" if s.get("t") else "")
    return r + ("*" if s.get("champ") else "")
 
 
class Layout:
    """Finds the row/column anchors on the sheet by reading headers, so the
    script keeps working if you move blocks around a little."""
 
    def __init__(self, grid: list[list[str]]):
        self.grid = grid
 
    def find(self, text: str, row: int | None = None, exact: bool = True):
        for ri, row_vals in enumerate(self.grid):
            if row is not None and ri != row:
                continue
            for ci, v in enumerate(row_vals):
                if (v == text) if exact else (text.lower() in str(v).lower()):
                    return ri, ci
        return None
 
    def year_block(self, header_row: int, first_col: int) -> list[int]:
        """Contiguous run of "19'" style headers starting at first_col -> list of cols."""
        cols = []
        c = first_col
        row = self.grid[header_row]
        last = -1
        while c < len(row) and re.fullmatch(r"\d\d'", str(row[c]).strip()):
            y = int(str(row[c]).strip()[:2])
            if y <= last:            # a second, adjacent year block starts here
                break
            cols.append(c); last = y
            c += 1
        return cols
 
 
def build_regular_season(ws, teams: dict[str, Team], scored: list[Season], years: list[int]):
    grid = read_grid(ws)
    lay = Layout(grid)
    hdr_r, _ = lay.find("Overall Ranking")
    first_row = hdr_r + 1
    hdr = grid[hdr_r]
    c_rank = hdr.index("Overall Ranking"); c_team = hdr.index("Team"); c_trend = hdr.index("Trend")
    c_w = hdr.index("Wins"); c_l = hdr.index("Losses"); c_pf = hdr.index("Overall PF"); c_pa = hdr.index("Overall PA")
    rec_cols = lay.year_block(hdr_r, c_pf + 4)            # after PF/PA/% /diff
    trade_cols = lay.year_block(hdr_r, rec_cols[-1] + 1)
    c_trades_total = hdr.index("Total Trades")
    c_best = hdr.index("Year")                              # first "Year" = best perf block
    rec_years = [int("20" + hdr[c][:2]) for c in rec_cols]
    # ensure header years cover every scored season
    missing = [y for y in years if y not in rec_years]
    updates = []
    if missing:
        # add columns at the end of both year blocks (right-most first so indexes stay valid)
        for c in sorted([trade_cols[-1] + 1, rec_cols[-1] + 1], reverse=True):
            for _ in missing:
                ws.insert_cols([[]], col=c + 1, inherit_from_before=True)
        grid = read_grid(ws); lay = Layout(grid); hdr = grid[hdr_r]
        # write the new header labels
        new_hdr_cells = []
        for i, y in enumerate(missing):
            new_hdr_cells.append((rec_cols[-1] + 1 + i, yr_label(y)))
            new_hdr_cells.append((trade_cols[-1] + 1 + len(missing) + i, yr_label(y)))
        for c, lab in new_hdr_cells:
            updates.append((f"{col_letter(c+1)}{hdr_r+1}", [[lab]]))
        rec_cols = rec_cols + [rec_cols[-1] + 1 + i for i in range(len(missing))]
        shift = len(missing)
        trade_cols = [c + shift for c in trade_cols] + [trade_cols[-1] + shift + 1 + i for i in range(len(missing))]
        c_trades_total += 2 * shift; c_best += 2 * shift
        rec_years += missing
 
    # existing team rows -> remember manual Trend column
    existing_rows = []
    r = first_row
    while r < len(grid) and grid[r][c_team].strip():
        existing_rows.append(grid[r]); r += 1
    last_team_row = r - 1
    trend_by_name = {row[c_team].strip().lower(): row[c_trend] for row in existing_rows}
    name_case = {row[c_team].strip().lower(): row[c_team].strip() for row in existing_rows}
 
    ordered = sorted(teams.values(), key=lambda t: (-t.win_pct, -t.wins, -t.pf))
    n_needed = len(ordered); n_have = len(existing_rows)
    if n_needed > n_have:
        ws.insert_rows([[]] * (n_needed - n_have), row=last_team_row + 2, inherit_from_before=True)
 
    width = c_best + 18
    rows = []
    for i, t in enumerate(ordered, 1):
        key = t.name.lower()
        disp = name_case.get(key, t.name)
        row = [""] * width
        row[c_rank] = i; row[c_team] = disp; row[c_trend] = trend_by_name.get(key, "")
        row[c_w] = t.wins; row[c_l] = t.losses; row[c_pf] = t.pf; row[c_pa] = t.pa
        for c, y in zip(rec_cols, rec_years):
            s = t.seasons.get(y)
            row[c] = rec_str(s) if s and (s["w"] + s["l"]) else ""
        for c, y in zip(trade_cols, rec_years):
            row[c] = t.trades.get(y, 0) if y in t.seasons else ""
        row[c_trades_total] = sum(t.trades.values())
        b, wk, bs, ws_ = t.best_week, t.worst_week, t.best_start, t.worst_start
        vals = [b["year"], b["week"], b["score"], b["mvp"], b["mvp_score"],
                wk["year"], wk["week"], wk["score"], wk["lvp"], wk["lvp_score"],
                bs["player"], bs["year"], bs["week"], bs["score"],
                ws_["player"], ws_["year"], ws_["week"], ws_["score"]] if b else [""] * 18
        row[c_best:c_best + 18] = vals
        rows.append(row)
    # Only write the columns we own (skip formula columns D, I, J by writing per-block)
    def block(c0, c1):  # inclusive 0-based cols
        return (f"{col_letter(c0+1)}{first_row+1}:{col_letter(c1+1)}{first_row+len(rows)}",
                [r[c0:c1 + 1] for r in rows])
    updates.append(block(c_rank, c_trend))
    updates.append(block(c_w, c_pa))
    updates.append(block(rec_cols[0], c_trades_total))
    updates.append(block(c_best, c_best + 17))
    # totals row under the trade columns (first non-empty row below the teams)
    tr = first_row + len(rows)
    while tr < len(grid) and not str(grid[tr][trade_cols[0]]).strip():
        tr += 1
    if tr < len(grid):
        r0, r1 = first_row + 1, first_row + len(rows)
        sums = [f"=SUM({col_letter(c+1)}{r0}:{col_letter(c+1)}{r1})" for c in trade_cols + [c_trades_total]]
        updates.append((f"{col_letter(trade_cols[0]+1)}{tr+1}:{col_letter(c_trades_total+1)}{tr+1}", [sums]))
 
    # ---- Best regular seasons of all-time (Avg PPG)
    pos = lay.find("Best Regular Seasons of All-Time", exact=False)
    if pos:
        hr = pos[0] + 1                       # header row with Rank/Team/Year/...
        hdr2 = grid[hr]
        c_r = hdr2.index("Rank"); c_pts = hdr2.index("Total Points"); c_ppg = hdr2.index("Avg PPG")
        c_rec = hdr2.index("Record"); c_res = hdr2.index("Result")
        allseasons = []
        for t in teams.values():
            for y, s in t.seasons.items():
                games = s["w"] + s["l"] + s.get("t", 0)
                if games and any(sn.year == y and sn.complete for sn in scored):
                    allseasons.append((s["pf"] / (games if not is_median_year(scored, y) else games / 2), t, y, s))
        allseasons.sort(key=lambda x: -x[0])
        out, formulas = [], []
        for i, (ppg, t, y, s) in enumerate(allseasons[:BEST_SEASONS_ROWS], 1):
            rr = hr + 1 + i
            out.append([i, name_case.get(t.name.lower(), t.name), y, round(s["pf"], 2),
                        None, rec_str(s).rstrip("*"), s["result"]])
            formulas.append([f"=round(if({col_letter(c_pts)}{rr}>=2021,{col_letter(c_pts+1)}{rr}/14,{col_letter(c_pts+1)}{rr}/13), 2)"])
        updates.append((f"{col_letter(c_r+1)}{hr+2}:{col_letter(c_pts+1)}{hr+1+len(out)}", [r[:4] for r in out]))
        updates.append((f"{col_letter(c_ppg+1)}{hr+2}:{col_letter(c_ppg+1)}{hr+1+len(out)}", formulas))
        updates.append((f"{col_letter(c_rec+1)}{hr+2}:{col_letter(c_res+1)}{hr+1+len(out)}", [r[5:] for r in out]))
 
    pos = lay.find("Last Updated", exact=False)
    if pos:
        updates.append((f"{col_letter(pos[1]+1)}{pos[0]+1}", [[f"Last Updated: {dt.date.today():%B %d, %Y}"]]))
    return updates
 
 
def is_median_year(scored: list[Season], year: int) -> bool:
    return any(s.year == year and s.median for s in scored)
 
 
def build_playoffs(ws, teams: dict[str, Team], scored: list[Season], years: list[int]):
    grid = read_grid(ws)
    lay = Layout(grid)
    hdr_r, _ = lay.find("Overall Ranking")
    hdr = grid[hdr_r]
    first_row = hdr_r + 1
    c_rank = hdr.index("Overall Ranking"); c_champ = hdr.index("Championships"); c_team = hdr.index("Team")
    c_rec = hdr.index("Playoff Record")
    c_app0 = hdr.index("Playoff Appearances (1st & 2nd)")
    bye_start = next(c for c in range(c_app0 + 1, len(hdr)) if re.fullmatch(r"\d\d'", hdr[c].strip()))
    app_cols = list(range(c_app0, bye_start))
    bye_cols = lay.year_block(hdr_r, bye_start)
    sl_cols = lay.year_block(hdr_r, bye_cols[-1] + 1)
    c_toilet = hdr.index("Toilet Bowl Appearances")
    age_cols = lay.year_block(hdr_r, c_toilet + 1)
    age_years = [int("20" + hdr[c][:2]) for c in age_cols]
    block_years = [int("20" + hdr[c][:2]) for c in bye_cols]
    dues_cols = [i for i, v in enumerate(hdr) if re.fullmatch(r"\d{4} Dues", v.strip())]
 
    updates = []
    missing = [y for y in years if y not in block_years]
    if missing:
        # insert new year columns at the end of each of the four year blocks (right-most first)
        ends = sorted([age_cols[-1] + 1, sl_cols[-1] + 1, bye_cols[-1] + 1, app_cols[-1] + 1], reverse=True)
        for c in ends:
            for _ in missing:
                ws.insert_cols([[]], col=c + 1, inherit_from_before=True)
        grid = read_grid(ws); lay = Layout(grid); hdr = grid[hdr_r]
        k = len(missing)
        app_cols = app_cols + [app_cols[-1] + 1 + i for i in range(k)]
        bye_cols = [c + k for c in bye_cols]; bye_cols += [bye_cols[-1] + 1 + i for i in range(k)]
        sl_cols = [c + 2 * k for c in sl_cols]; sl_cols += [sl_cols[-1] + 1 + i for i in range(k)]
        c_toilet += 3 * k
        age_cols = [c + 3 * k for c in age_cols]; age_cols += [age_cols[-1] + 1 + i for i in range(k)]
        dues_cols = [c + 4 * k for c in dues_cols]
        for i, y in enumerate(missing):
            for c in (app_cols[-k + i], bye_cols[-k + i], sl_cols[-k + i], age_cols[-k + i]):
                updates.append((f"{col_letter(c+1)}{hdr_r+1}", [[yr_label(y)]]))
        block_years += missing; age_years += missing
 
    existing = []
    r = first_row
    while r < len(grid) and grid[r][c_team].strip():
        existing.append(grid[r]); r += 1
    last_team_row = r - 1
    by_name = {row[c_team].strip().lower(): row for row in existing}
    name_case = {k: v[c_team].strip() for k, v in by_name.items()}
 
    def po_pct(t):
        g = t.playoff_w + t.playoff_l
        return t.playoff_w / g if g else 0
    ordered = sorted(teams.values(), key=lambda t: (-len(t.titles), -t.playoff_w, -len(t.runner_ups),
                                                    -po_pct(t), -(t.playoff_w + t.playoff_l)))
    if len(ordered) > len(existing):
        ws.insert_rows([[]] * (len(ordered) - len(existing)), row=last_team_row + 2, inherit_from_before=True)
 
    width = max(dues_cols + [age_cols[-1]]) + 1
    rows = []
    cur_year = years[-1]
    for i, t in enumerate(ordered, 1):
        key = t.name.lower()
        old = by_name.get(key)
        row = [""] * width
        row[c_rank] = i
        row[c_champ] = ("🏆" * len(t.titles) + "🥈" * len(t.runner_ups)) or "-"
        row[c_team] = name_case.get(key, t.name)
        row[c_rec] = f"{t.playoff_w}-{t.playoff_l}"
        for c, y in zip(app_cols, block_years):
            if y in t.seasons and season_complete(scored, y):
                row[c] = yr_label(y) if y in t.appearances else "-"
        for c, y in zip(bye_cols, block_years):
            if y in t.seasons and season_complete(scored, y):
                b = next((b for b in t.byes if b[0] == y), None)
                row[c] = (yr_label(y) + ("*" if b[1] else "")) if b else "-"
        for c, y in zip(sl_cols, block_years):
            s = t.seasons.get(y)
            row[c] = ordinal(s["score_rank"]) if s and s["score_rank"] else ""
        row[c_toilet] = ", ".join(yr_label(y) for y in t.toilet) or "-"
        for c, y in zip(age_cols, age_years):
            if y == cur_year and t.age_current is not None:
                row[c] = t.age_current
            elif old is not None and c < len(old):
                row[c] = num(old[c])               # keep historical (manual) ages
        for c in dues_cols:                          # manual -> travels with the team
            row[c] = old[c] if old is not None and c < len(old) else ""
        rows.append(row)
 
    def block(c0, c1):
        return (f"{col_letter(c0+1)}{first_row+1}:{col_letter(c1+1)}{first_row+len(rows)}",
                [r[c0:c1 + 1] for r in rows])
    updates.append(block(c_rank, c_rec))
    updates.append(block(app_cols[0], age_cols[-1]))
    if dues_cols:
        updates.append(block(min(dues_cols), max(dues_cols)))
 
    # ---- Scoring Leaders Trends  (teams across, years down)
    pos = lay.find("Scoring Leaders Trends")
    if pos:
        hr = pos[0] + 1
        c_year = pos[1]
        names = [name_case.get(t.name.lower(), t.name) for t in ordered]
        out = [[""] + names]
        for y in years:
            line = [y]
            for t in ordered:
                s = t.seasons.get(y)
                line.append(s["score_rank"] if s and s["score_rank"] else "")
            out.append(line)
        out = [line + [""] * 4 for line in out]
        updates.append((f"{col_letter(c_year+1)}{hr+1}:{col_letter(c_year+len(out[0]))}{hr+len(out)}", out))
 
    # ---- Scoring leader -> following-year scoring finish (matches how the sheet was kept)
    pos = lay.find("Following Year Finish")
    if pos:
        hr = pos[0]                       # header row with 1st..12th
        c_lab = pos[1] + 1                # year labels column (E)
        c_first = hr_index(grid[hr], "1st")
        n = max(len(sn.rosters) for sn in scored)
        PAD = 4
        updates.append((f"{col_letter(c_first+1)}{hr+1}:{col_letter(c_first+n+PAD)}{hr+1}",
                        [[ordinal(i) for i in range(1, n + 1)] + [""] * PAD]))
        complete_years = [y for y in years if season_complete(scored, y)]
        pairs = [(y, y + 1) for y in complete_years if (y + 1) in complete_years]
        out = []
        for y, y2 in pairs:
            line = [yr_label(y)] + [""] * (n + PAD)
            for t in teams.values():
                s, s2 = t.seasons.get(y), t.seasons.get(y2)
                if s and s2 and s["score_rank"] and s["score_rank"] <= n:
                    line[s["score_rank"]] = s2["score_rank"]
            out.append(line)
        # how many data rows exist now (until "AVG Finish")
        avg_pos = lay.find("AVG Finish")
        have = (avg_pos[0] - hr - 1) if avg_pos else len(out)
        if len(out) > have:
            ws.insert_rows([[]] * (len(out) - have), row=hr + 1 + have + 1, inherit_from_before=True)
        updates.append((f"{col_letter(c_lab+1)}{hr+2}:{col_letter(c_first+n+PAD)}{hr+1+len(out)}", out))
        # rewrite the summary formulas so they cover every data row
        r0, r1 = hr + 2, hr + 1 + len(out)
        stats = [("AVG Finish", "average"), ("Median", "MEDIAN"), ("STDEV", "STDEV.S"), ("Best", "min"), ("Worst", "MAX")]
        srow = r1 + 1
        for label, fn in stats:
            line = [label] + [f"={fn}({col_letter(c_first+1+i)}{r0}:{col_letter(c_first+1+i)}{r1})" for i in range(n)] + [""] * PAD
            updates.append((f"{col_letter(c_lab+1)}{srow}:{col_letter(c_first+n+PAD)}{srow}", [line]))
            srow += 1
 
    pos = lay.find("Last Updated", exact=False)
    if pos:
        updates.append((f"{col_letter(pos[1]+1)}{pos[0]+1}", [[f"Last Updated: {dt.date.today():%B %d, %Y}"]]))
    return updates
 
 
def num(v):
    """'30.0' -> 30.0 so carried-over cells stay numeric."""
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return float(s) if "." in s else int(s)
    return v
 
 
def hr_index(row, text):
    return row.index(text)
 
 
def years_on_sheet(hdr, bye_start):
    c = bye_start; out = []
    while c < len(hdr) and re.fullmatch(r"\d\d'", hdr[c].strip()):
        out.append(c); c += 1
    return out
 
 
def season_complete(scored, year):
    return any(s.year == year and s.complete for s in scored)
 
 
def build_trades(ws, teams: dict[str, Team], years: list[int]):
    grid = read_grid(ws)
    names = {}
    for row in grid:
        for v in row:
            if v.strip():
                names[v.strip().lower()] = v.strip()
    def disp(t): return names.get(t.name.lower(), t.name)
    per_year = []
    for y in sorted(years, reverse=True):
        entries = [(t.trades.get(y, 0), disp(t)) for t in teams.values() if y in t.seasons]
        for n, nm in sorted(entries, key=lambda x: (-x[0], x[1].lower())):
            per_year.append([y, n, nm])
    totals = sorted(((sum(t.trades.values()), disp(t)) for t in teams.values()), key=lambda x: (-x[0], x[1].lower()))
    updates = [
        ("A1:C1", [["Year", "Trades", "Teams"]]),
        (f"A2:C{1+len(per_year)}", per_year),
        ("E2:F2", [["Total Trades", "Teams"]]),
        (f"E3:F{2+len(totals)}", [[n, nm] for n, nm in totals]),
    ]
    # clear anything left over below
    old_n = sum(1 for r in grid[1:] if r and str(r[0]).strip())
    if old_n > len(per_year):
        updates.append((f"A{2+len(per_year)}:C{1+old_n}", [["", "", ""]] * (old_n - len(per_year))))
    return updates
 
 
# ----------------------------------------------------------------------------
# Google Sheets
# ----------------------------------------------------------------------------
def open_spreadsheet():
    import gspread
    gc = gspread.oauth(credentials_filename=OAUTH_CLIENT_FILE, authorized_user_filename=OAUTH_TOKEN_FILE,
                       scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gc.open_by_key(SPREADSHEET_ID)
 
 
def assert_not_protected(title: str):
    for pat in PROTECTED_SHEET_PATTERNS:
        if re.search(pat, title, re.I):
            raise RuntimeError(f"Refusing to write protected sheet {title!r}")
 
 
def apply(ws, updates, dry: bool, payload: dict):
    assert_not_protected(ws.title)
    payload[ws.title] = [{"range": a1, "values": vals} for a1, vals in updates]
    if dry:
        return
    # RAW keeps "10-3" as text (USER_ENTERED would turn it into a date); formulas need USER_ENTERED.
    raw, formulas = [], []
    for a1, vals in updates:
        has_formula = any(isinstance(v, str) and v.startswith("=") for row in vals for v in row)
        if has_formula:
            assert not any(isinstance(v, str) and re.fullmatch(r"\d+-\d+\*?", v) for row in vals for v in row), a1
            formulas.append({"range": a1, "values": vals})
        else:
            raw.append({"range": a1, "values": vals})
    if raw:
        ws.batch_update(raw, value_input_option="RAW")
    if formulas:
        ws.batch_update(formulas, value_input_option="USER_ENTERED")
 
 
class DryWorksheet:
    """Stand-in for gspread Worksheet in --dry-run: reads from an xlsx export."""
    def __init__(self, title, grid):
        self.title = title; self._grid = grid
    def get_all_values(self): return self._grid
    def insert_cols(self, values, col=1, **k):
        print(f"  [dry] would insert column at {col_letter(col)} on {self.title}")
        for row in self._grid:
            row.insert(col - 1, "")
    def insert_rows(self, values, row=1, **k):
        print(f"  [dry] would insert {len(values)} row(s) at row {row} on {self.title}")
        w = max(len(r) for r in self._grid)
        for _ in values:
            self._grid.insert(row - 1, [""] * w)
 
 
def dry_spreadsheet():
    import io, openpyxl
    local = os.environ.get("DRY_RUN_XLSX")          # optional: path to a File > Download > .xlsx copy
    if local:
        wb = openpyxl.load_workbook(local, data_only=False)
    else:
        url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=xlsx"
        r = requests.get(url, timeout=60)
        if not r.ok or not r.content.startswith(b"PK"):
            sys.exit("Could not export the sheet (is it link-shareable?). Download it as .xlsx and set DRY_RUN_XLSX=path")
        wb = openpyxl.load_workbook(io.BytesIO(r.content), data_only=False)
    sheets = {}
    for ws in wb.worksheets:
        grid = []
        for row in ws.iter_rows(values_only=True):
            grid.append(["" if v is None else (v if isinstance(v, str) else str(v)) for v in row])
        sheets[ws.title] = grid
    class SS:
        def worksheet(self, t): return DryWorksheet(t, sheets[t])
    return SS()
 
 
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
 
    api = Sleeper(use_cache=not args.no_cache)
    chain = find_league_chain(api)
    print("League seasons:", ", ".join(f"{lg['season']}({lg['status']})" for lg in reversed(chain)))
    seasons = load_seasons(api, chain)
    players = api.get("/players/nfl")
    teams, scored = compute(seasons, players)
    years = [s.year for s in scored]
    print(f"{len(teams)} managers, scored seasons {years[0]}-{years[-1]}")
 
    ss = dry_spreadsheet() if args.dry_run else open_spreadsheet()
    payload = {}
    apply(ss.worksheet(SHEET_REG), build_regular_season(ss.worksheet(SHEET_REG), teams, scored, years), args.dry_run, payload)
    apply(ss.worksheet(SHEET_PO), build_playoffs(ss.worksheet(SHEET_PO), teams, scored, years), args.dry_run, payload)
    apply(ss.worksheet(SHEET_TRADES), build_trades(ss.worksheet(SHEET_TRADES), teams, years), args.dry_run, payload)
    if args.dry_run:
        Path("dry_run_payload.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str))
        print("Dry run complete -> dry_run_payload.json")
    else:
        print("Sheet updated.")
 
 
if __name__ == "__main__":
    main()
 