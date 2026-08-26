# Sleeper → Google Sheets sync (Originally From Ohio Dynasty League)
 
`sleeper_sync.py` pulls the whole league history from the Sleeper API (2019 → current,
following `previous_league_id`) and rewrites every stat it can derive on the
**Regular Season**, **Playoffs** and **Trades** tabs. It never writes to any
schedule tab, Brackets, Drafts, Polls or Survivor History, and it refuses to
(there is a hard-coded block list).
 
## One-time setup (≈10 minutes)
 
1. Python 3.10+ and the two libraries:
   ```
   pip install -r requirements.txt
   ```
2. Google OAuth client (this is the "Google OAuth" part — it runs as *you*, no
   service account / sheet sharing needed):
   1. Go to https://console.cloud.google.com → create a project (any name).
   2. **APIs & Services → Library** → enable **Google Sheets API**.
   3. **APIs & Services → OAuth consent screen** → External → fill in the app
      name + your email → add yourself (sengi1212@gmail.com) as a *test user*.
   4. **APIs & Services → Credentials → Create credentials → OAuth client ID**
      → Application type **Desktop app** → Download JSON.
   5. Save that file as `credentials.json` next to `sleeper_sync.py`.
3. First run:
   ```
   python sleeper_sync.py
   ```
   A browser window opens, you approve access to Sheets, and
   `authorized_user.json` is written. Every later run is silent.
## Running it
 
| Command | What it does |
|---|---|
| `python sleeper_sync.py` | Full sync. Re-computes 2019→now and rewrites the three tabs. |
| `python sleeper_sync.py --dry-run` | Computes everything, writes **nothing**, saves the exact cells it *would* write to `dry_run_payload.json`. Run this first. |
| `python sleeper_sync.py --no-cache` | Ignore `.sleeper_cache/` and re-download completed seasons. |
 
Completed seasons are cached in `.sleeper_cache/` so a run takes a few seconds;
the current season is always re-fetched. Run it whenever you like during the
season (Tuesday mornings are a good habit) and once after the championship.
 
If your sheet isn't link-viewable, `--dry-run` needs a local copy:
`DRY_RUN_XLSX=league.xlsx python sleeper_sync.py --dry-run`
(File → Download → Microsoft Excel).
 
## What gets written
 
**Regular Season tab**
- Rows re-sorted by all-time win % (Rank, Team, Wins, Losses, Overall PF / PA).
  Your Trend emoji travels with the team; the Win % / PF-PA formula columns are left alone.
- Records by year (champion's year gets a `*`, per the header) and trades by year + total.
  A new year column is inserted automatically at the end of each block the first
  time the script sees a new season, with the SUM row extended.
- All-time best / worst team week with MVP / LVP, best / worst single start
  (all scored weeks, playoffs and consolation included — same as you've done it).
- Best Regular Seasons of All-Time: top 20 by avg PPG, with record and result
  (🏆 / 🥈 / Rd 2 / Rd 1).
- "Last Updated" date.
**Playoffs tab**
- Rows re-sorted: championships, then playoff wins, runner-ups, playoff win %.
  Championships emoji (🏆 per title, 🥈 per runner-up), playoff record
  (3rd- and 5th-place games excluded — this reproduces your 6-2, 5-3, 4-4 … exactly),
  appearances, byes (`*` = 1 seed), scoring rank per year, toilet-bowl years
  (the two teams in the last-place game of the consolation bracket).
- Avg Team Age: **only the current season's column** is computed (from today's
  rosters — Sleeper can't give historical ages); older columns are carried over
  as-is. Dues columns are carried over with each team.
- Scoring Leaders Trends table and the "Scoring leader → following-year
  finish" table (following-year *scoring* rank, which is how it was being kept),
  with the AVG / Median / STDEV / Best / Worst formulas re-extended.
- Payouts block and the 25'/26' draft-order list are untouched.
**Trades tab** — fully regenerated: trades per team per year (newest first)
and all-time totals.
 
## Things to know
 
- **Team identity** is by Sleeper user, so `tomeidens14 → thomaseidens` and
  `blainehunkins → bhunk3` are merged automatically (the script uses the
  spelling already on your sheet, e.g. `WillyOrq`).
- **Orphaned 2022 team (roster 11)** had no owner in Sleeper. The script credits
  a roster with no owner to whoever owned that slot the previous season — here
  that's `eferns14`, which is how your sheet already shows the 19-9 record.
  That also makes his all-time PF include 2022 (your manual PF didn't).
  To change it, set `ORPHAN_OVERRIDES = {(2022, 11): "<sleeper user_id>"}` at the top of the script.
- Records like `10-3` are written as text (RAW) so Google Sheets stops turning
  them into dates — several of the old manual cells on the sheet are actually dates.
- A few manual cells differ from what the script computes (e.g. some LVP picks
  where a 0.0 starter was skipped, a couple of best-week rows that were never
  updated, tie-break order in the playoffs ranking). The script's numbers come
  straight from the API, so treat the first run as the correction pass.
- When a new year column is inserted, merged header cells ("Records By Year",
  "Playoff Byes", …) don't stretch automatically — just re-merge them once a year.
- Adding a 15th manager inserts a new row automatically.
## Automating it
 
Windows Task Scheduler / macOS `launchd` / cron — e.g. every Tuesday at 9 am:
```
0 9 * * 2  cd /path/to/folder && python sleeper_sync.py >> sync.log 2>&1
```