#!/usr/bin/env python3
"""
Sleeper league draft analyzer (works with ANY league).

Pulls every completed draft in a Sleeper league's history (following the
previous_league_id chain), then reports position-by-round trends, positional
ADP, positional scarcity, per-manager tendencies, and how the title winners
(auto-detected from each season's playoff bracket) built their rosters.

Roster construction, scoring, positions (superflex / IDP / DEF), and bench size
are all read from the league object, so no format is hard-coded.

Usage:
    python3 draft_analysis.py [LEAGUE_ID] [MAX_SEASONS]

By default it analyzes ALL completed seasons. Pass MAX_SEASONS to keep only the
most recent N (e.g. `python3 draft_analysis.py 12345 3`).

Only depends on the standard library (urllib). No API key required; Sleeper's
read API is public.
"""
import json
import sys
import urllib.request
from collections import Counter, defaultdict

API = "https://api.sleeper.app/v1"

# Canonical display order; positions not listed here are appended alphabetically.
CANON_POS = ["QB", "RB", "WR", "TE", "K", "DEF",
             "DL", "LB", "DB", "CB", "S", "SS", "FS", "IDP"]

# Sleeper roster slot labels that map to more than one real position.
FLEX_SLOTS = {
    "FLEX": "RB/WR/TE",
    "WRRB_FLEX": "RB/WR",
    "WRRB": "RB/WR",
    "REC_FLEX": "WR/TE",
    "SUPER_FLEX": "QB/RB/WR/TE",
    "IDP_FLEX": "IDP",
}
BENCH_SLOTS = {"BN", "IR", "TAXI"}


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def league_chain(current_id, prev_szns=None):
    """Walk previous_league_id and return completed seasons (oldest first).
    By default returns ALL completed seasons; if `prev_szns` is given, keeps only the
    most recent `prev_szns`."""
    chain = []
    lid = current_id
    while lid:
        lg = get(f"{API}/league/{lid}")
        chain.append(lg)
        lid = lg.get("previous_league_id")
    completed = [lg for lg in chain if lg.get("status") == "complete"]
    completed.sort(key=lambda lg: int(lg["season"]))
    return completed[-prev_szns:] if prev_szns else completed


def find_champion(lg, users):
    """Return (display_name, user_id) of the season champion by reading the
    winners bracket (the match with placement p == 1). Returns (None, None) if
    the bracket isn't available."""
    try:
        bracket = get(f"{API}/league/{lg['league_id']}/winners_bracket")
        rosters = get(f"{API}/league/{lg['league_id']}/rosters")
    except Exception:
        return None, None
    final = next((m for m in bracket if m.get("p") == 1), None)
    if not final or not final.get("w"):
        return None, None
    owner = next((r.get("owner_id") for r in rosters
                  if r.get("roster_id") == final["w"]), None)
    return users.get(owner, owner), owner


def load_season(lg):
    season = lg["season"]
    draft_id = lg["draft_id"]
    draft = get(f"{API}/draft/{draft_id}")
    picks = get(f"{API}/draft/{draft_id}/picks")
    users = {u["user_id"]: (u.get("display_name") or u.get("user_id"))
             for u in get(f"{API}/league/{lg['league_id']}/users")}
    champ_name, champ_id = find_champion(lg, users)
    for p in picks:
        p["_pos"] = (p.get("metadata") or {}).get("position") or "?"
        p["_name"] = "{} {}".format(
            (p.get("metadata") or {}).get("first_name", ""),
            (p.get("metadata") or {}).get("last_name", "")).strip()
        p["_mgr"] = users.get(p.get("picked_by"), f"slot{p.get('draft_slot')}")
    return {
        "season": season,
        "league_name": lg.get("name"),
        "rounds": draft["settings"].get("rounds"),
        "teams": draft["settings"].get("teams"),
        "type": draft.get("type"),
        "scoring": (draft.get("metadata") or {}).get("scoring_type"),
        "roster_positions": lg.get("roster_positions"),
        "scoring_settings": lg.get("scoring_settings"),
        "champion": champ_name,
        "champion_id": champ_id,
        "picks": sorted(picks, key=lambda p: p["pick_no"]),
    }


def ordinal(n):
    return f"{n}{'tsnrhtdd'[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10::4]}"


def hbar(n, scale=1):
    return "\u2588" * int(round(n * scale))


def order_positions(present):
    ordered = [p for p in CANON_POS if p in present]
    ordered += sorted(p for p in present if p not in CANON_POS)
    return ordered


def pos_chars(positions):
    """Assign a unique single character to each position for ASCII bars."""
    chars, used = {}, set()
    for pos in positions:
        for c in [pos[0].upper(), pos[-1].upper(), *pos.upper(), *"0123456789"]:
            if c not in used:
                chars[pos] = c
                used.add(c)
                break
    return chars


def parse_roster(roster_positions):
    """Return (starters Counter, flex Counter, bench count) from roster slots."""
    starters, flex, bench = Counter(), Counter(), 0
    for slot in roster_positions or []:
        if slot in BENCH_SLOTS:
            bench += 1
        elif slot in FLEX_SLOTS:
            flex[slot] += 1
        else:
            starters[slot] += 1
    return starters, flex, bench


def describe_scoring(scoring):
    rec = (scoring or {}).get("rec", 0) or 0
    if rec >= 1:
        ppr = "Full PPR"
    elif rec >= 0.5:
        ppr = "Half-PPR"
    elif rec > 0:
        ppr = f"{rec:g}-PPR"
    else:
        ppr = "Standard (non-PPR)"
    ptd = (scoring or {}).get("pass_td", 4)
    return f"{ppr}, {ptd:g}pt pass TD"


def lineup_string(starters, flex):
    ordered = order_positions(set(starters))
    parts = [f"{starters[p]}{p}" for p in ordered]
    parts += [f"{flex[s]}{s}" for s in flex]
    return ", ".join(parts)


def report(seasons):
    teams = seasons[-1]["teams"]
    years = [s["season"] for s in seasons]
    present = set()
    for s in seasons:
        present.update(p["_pos"] for p in s["picks"] if p["_pos"] != "?")
    positions = order_positions(present)
    charmap = pos_chars(positions)
    starters, flex, bench = parse_roster(seasons[-1].get("roster_positions"))
    superflex = flex.get("SUPER_FLEX", 0)
    qb_premium = superflex > 0 or starters.get("QB", 0) >= 2
    lname = seasons[-1].get("league_name") or "LEAGUE"

    print("=" * 70)
    print(f"  {lname.upper()} DRAFT GUIDE  \u2014  seasons {', '.join(years)}")
    print("=" * 70)
    for s in seasons:
        print(f"  {s['season']}: {s['type']} draft, {s['rounds']} rounds x "
              f"{s['teams']} teams = {len(s['picks'])} picks  "
              f"(scoring: {s['scoring']})")
    if seasons[-1].get("roster_positions"):
        tags = f"{teams}-team"
        if qb_premium:
            tags += ", SUPERFLEX/2QB"
        print(f"  Format: {tags}, "
              f"{describe_scoring(seasons[-1].get('scoring_settings'))}")
        print(f"  Starters: {lineup_string(starters, flex)}  |  bench: {bench}")

    # ---- 1. Position by round (averaged across seasons) ----
    print("\n" + "-" * 70)
    print("  POSITIONS DRAFTED PER ROUND  (avg per season, bar = players)")
    print("-" * 70)
    maxr = max(s["rounds"] for s in seasons)
    by_round = defaultdict(lambda: defaultdict(list))  # round -> pos -> [counts]
    for s in seasons:
        c = defaultdict(Counter)
        for p in s["picks"]:
            c[p["round"]][p["_pos"]] += 1
        for rnd in range(1, s["rounds"] + 1):
            for pos in positions:
                by_round[rnd][pos].append(c[rnd][pos])
    legend = " ".join(f"{pos}={charmap[pos]}" for pos in positions)
    print("Rd  " + "".join(f"{p:>5}" for p in positions) + "   picture")
    print("    (" + legend + ")")
    for rnd in range(1, maxr + 1):
        avgs = {}
        for pos in positions:
            vals = by_round[rnd][pos]
            avgs[pos] = sum(vals) / len(vals) if vals else 0
        line = f"{rnd:>2}  " + "".join(
            (f"{avgs[p]:>5.1f}" if avgs[p] else "    .") for p in positions)
        pic = "".join(charmap[pos] * int(round(avgs[pos])) for pos in positions)
        print(f"{line}   {pic}")

    # ---- 2. Positional ADP ----
    print("\n" + "-" * 70)
    print(f"  POSITIONAL ADP  (across all {len(seasons)} drafts)")
    print("-" * 70)
    pos_picks = defaultdict(list)
    for s in seasons:
        for p in s["picks"]:
            pos_picks[p["_pos"]].append(p["pick_no"])
    print(f"{'Pos':<5}{'#drafted':>9}{'avg pick':>10}{'avg rd':>8}"
          f"{'earliest':>10}{'latest':>8}")
    for pos in positions:
        v = sorted(pos_picks.get(pos, []))
        if not v:
            continue
        avg = sum(v) / len(v)
        print(f"{pos:<5}{len(v):>9}{avg:>10.1f}{avg / teams:>8.1f}"
              f"{v[0]:>10}{v[-1]:>8}")

    # ---- 3. Positional scarcity: cumulative gone by round ----
    print("\n" + "-" * 70)
    print("  CUMULATIVE PLAYERS GONE BY END OF ROUND  (avg across seasons)")
    print("-" * 70)
    scarce = [p for p in positions if p in starters] or positions
    print("Rd  " + "".join(f"{p:>5}" for p in scarce))
    cum = defaultdict(lambda: defaultdict(list))  # round -> pos -> [cum/season]
    for s in seasons:
        per = defaultdict(Counter)  # round -> pos -> count
        for p in s["picks"]:
            per[p["round"]][p["_pos"]] += 1
        run = Counter()
        for rnd in range(1, s["rounds"] + 1):
            for pos in scarce:
                run[pos] += per[rnd][pos]
                cum[rnd][pos].append(run[pos])
    for rnd in range(1, min(10, maxr) + 1):
        cells = ""
        for pos in scarce:
            vals = cum[rnd][pos]
            cells += f"{(sum(vals)/len(vals)):>5.0f}" if vals else "    ."
        print(f"{rnd:>2}  {cells}")

    # ---- 4. Starter-pool exhaustion ----
    print("\n" + "-" * 70)
    print("  STARTER-POOL EXHAUSTION  (when the last leaguewide starter goes)")
    print("-" * 70)
    print("  pool = teams x starting slots at that position"
          + (" (QB incl. superflex)" if superflex else ""))
    for pos in scarce:
        slots = starters.get(pos, 0) + (superflex if pos == "QB" else 0)
        if slots <= 0:
            continue
        pool = teams * slots
        exhausted, firsts = [], []
        for s in seasons:
            v = sorted(p["pick_no"] for p in s["picks"] if p["_pos"] == pos)
            if v:
                firsts.append(v[0])
            if len(v) >= pool:
                exhausted.append(v[pool - 1])
        if firsts:
            af = sum(firsts) / len(firsts)
            tail = ""
            if exhausted:
                ae = sum(exhausted) / len(exhausted)
                tail = (f" | pool ({pool}) empty ~pick {ae:>4.0f} "
                        f"(rd {ae/teams:>3.1f})")
            print(f"  {pos:<4} first off board ~pick {af:>4.0f} "
                  f"(rd {af/teams:>3.1f}){tail}")

    # ---- 5. First player taken at each position, per year ----
    print("\n" + "-" * 70)
    print("  FIRST OFF THE BOARD AT EACH POSITION")
    print("-" * 70)
    for s in seasons:
        print(f"  {s['season']}:")
        for pos in positions:
            first = next((p for p in s["picks"] if p["_pos"] == pos), None)
            if first:
                print(f"     {pos:<4} pick {first['pick_no']:>3} (rd "
                      f"{first['round']}): {first['_name']}  -> {first['_mgr']}")

    # ---- 6. Position runs ----
    print("\n" + "-" * 70)
    print("  BIGGEST POSITION RUNS  (longest consecutive same-position streaks)")
    print("-" * 70)
    for s in seasons:
        best = {}
        cur_pos, cur_len, cur_start = None, 0, 0
        runs = []
        for p in s["picks"]:
            if p["_pos"] == cur_pos:
                cur_len += 1
            else:
                if cur_len >= 3:
                    runs.append((cur_pos, cur_len, cur_start))
                cur_pos, cur_len, cur_start = p["_pos"], 1, p["pick_no"]
        if cur_len >= 3:
            runs.append((cur_pos, cur_len, cur_start))
        runs.sort(key=lambda r: -r[1])
        top = ", ".join(f"{n}x{pos}@{start}" for pos, n, start in runs[:4])
        print(f"  {s['season']}: {top}")

    # ---- 7. Manager tendencies ----
    print("\n" + "-" * 70)
    print("  MANAGER TENDENCIES  (avg round each manager first takes a position)")
    print("-" * 70)
    mgr_first = defaultdict(lambda: defaultdict(list))  # mgr -> pos -> [rounds]
    mgr_count = defaultdict(lambda: defaultdict(int))
    for s in seasons:
        seen = set()
        for p in s["picks"]:
            key = (s["season"], p["_mgr"], p["_pos"])
            mgr_count[p["_mgr"]][p["_pos"]] += 1
            if key not in seen:
                mgr_first[p["_mgr"]][p["_pos"]].append(p["round"])
                seen.add(key)
    main_pos = [p for p in positions if p in starters] or positions
    print(f"{'Manager':<18}" + "".join(f"{p+' 1st':>8}" for p in main_pos))
    for mgr in sorted(mgr_first):
        cells = ""
        for pos in main_pos:
            v = mgr_first[mgr][pos]
            cells += f"{(sum(v)/len(v)):>8.1f}" if v else f"{'-':>8}"
        print(f"{mgr:<18}{cells}")
    print("  (lower = takes that position earlier on average)")

    # ---- 8. Champion drafts ----
    print("\n" + "-" * 70)
    print("  CHAMPION DRAFTS  (how the title winners built their rosters)")
    print("-" * 70)
    for s in seasons:
        champ = s.get("champion")
        if not champ:
            print(f"  {s['season']}: champion unavailable (no playoff bracket)")
            continue
        cp = [p for p in s["picks"] if p["_mgr"] == champ]
        cp.sort(key=lambda p: p["pick_no"])
        totals = Counter(p["_pos"] for p in cp)
        tstr = " ".join(f"{pos}:{totals[pos]}" for pos in positions if totals[pos])
        slot = cp[0]["draft_slot"] if cp else "?"
        print(f"\n  {s['season']} \u2014 {champ} (slot {slot}) | roster: {tstr}")
        for p in cp[:14]:
            print(f"     R{p['round']:>2} (p{p['pick_no']:>3}) {p['_pos']:<3} {p['_name']}")

    # ---- 9. Champion roster construction vs field ----
    print("\n" + "-" * 70)
    print("  CHAMPION ROSTER EDGE  (avg players rostered: champion vs league)")
    print("-" * 70)
    print(f"{'Pos':<5}{'league avg':>12}{'champ avg':>11}{'edge':>8}")
    edges = []
    for pos in positions:
        league_vals, champ_vals = [], []
        for s in seasons:
            per_mgr = Counter(p["_mgr"] for p in s["picks"] if p["_pos"] == pos)
            for mgr in {p["_mgr"] for p in s["picks"]}:
                league_vals.append(per_mgr.get(mgr, 0))
            if s.get("champion"):
                champ_vals.append(per_mgr.get(s["champion"], 0))
        if not league_vals or not champ_vals:
            continue
        la = sum(league_vals) / len(league_vals)
        ca = sum(champ_vals) / len(champ_vals)
        edges.append((ca - la, pos, la, ca))
        print(f"{pos:<5}{la:>12.1f}{ca:>11.1f}{ca - la:>+8.1f}")
    if edges:
        edges.sort(reverse=True)
        d, pos, la, ca = edges[0]
        print(f"\n  Biggest champion edge: {pos} "
              f"(champs roster {ca:.1f} vs league {la:.1f}, {d:+.1f}).")
        print("  In this format, stockpiling that position has tracked with "
              "titles.")

def main():
    import argparse
    title = 'Sleeper League Draft Analyzer'
    description = 'Determine draft trends of any leaguemate as well as champ team trends.'
    parser = argparse.ArgumentParser(description=f"{title}\n\t{description}", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-i', '--league_id', help='League ID for the league you wish to work with', required=True)
    parser.add_argument('-p', '--prev_szns', help='If provided, look back to only x number of previous seasons.', default=None, required=False)
    args = parser.parse_args()
    chain = league_chain(args.league_id, prev_szns=args.prev_szns)
    if not chain:
        print("No completed drafts found for this league.")
        return
    seasons = [load_season(lg) for lg in chain]
    report(seasons)


if __name__ == "__main__":
    sys.exit(main())
