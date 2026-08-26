# BAFL Draft Guide

_Generated from the last 3 completed Sleeper drafts (2023–2025). Refresh with_
`python3 bafl_draft_analysis.py`.

League: **BAFL** (Sleeper `1389348066355609601`)

## Format (the "weird" part)
Full **redraft every year** — the `draft_rounds: 3` setting is misleading; the
real drafts are 22–25 rounds.

| Season | Type | Rounds × Teams | Picks | Scoring |
|--------|------|----------------|-------|---------|
| 2023 | snake | 22 × 10 | 220 | dynasty_2qb |
| 2024 | snake | 22 × 10 | 220 | 2qb |
| 2025 | snake | 25 × 10 | 250 | 2qb |

- 10-team, **2-QB** (start two quarterbacks), snake.
- Starting lineup: **2QB / 2RB / 2WR / 1TE / 2K**.
- **Non-PPR** (`rec: 0`); kickers score a flat 3 per FG.
- The two format quirks that drive strategy: **two starting QBs** and **two
  starting kickers**.

## Positional ADP (all 3 drafts)
| Pos | # drafted | Avg pick | Avg round | Earliest |
|-----|-----------|----------|-----------|----------|
| QB  | 139 | 91.8  | 9.2  | 1  |
| RB  | 178 | 114.1 | 11.4 | 6  |
| WR  | 193 | 116.8 | 11.7 | 10 |
| TE  | 83  | 131.7 | 13.2 | 21 |
| K   | 97  | 138.7 | 13.9 | 73 |

## QB run (2-QB league — cumulative QBs gone by end of round)
| Round | 2023 | 2024 | 2025 | Avg |
|-------|------|------|------|-----|
| 1 | 9  | 9  | 10 | 9.3  |
| 2 | 11 | 12 | 14 | 12.3 |
| 3 | 13 | 16 | 15 | 14.7 |
| 4 | 18 | 19 | 15 | 17.3 |
| 5 | 20 | 19 | 18 | 19.0 |
| 6 | 22 | 21 | 25 | 22.7 |
| 7 | 25 | 23 | 25 | 24.3 |
| 8 | 29 | 26 | 28 | 27.7 |

The #1 overall pick has been a QB all three years, and **9–10 of 10 teams take a
QB in round 1**.

## Kickers (2 K starters, but heavily deferred)
| Season | K drafted | First K | Round |
|--------|-----------|---------|-------|
| 2023 | 30 | pick 73 | 8  |
| 2024 | 33 | pick 96 | 10 |
| 2025 | 34 | pick 89 | 9  |

Nobody drafts a kicker before round 8; the run hits in **rounds 11–15**.

## What the champions did
| | 2023 ssgroveroh (slot 2) | 2024 JayZee28 (1.01) | 2025 THEDrake01 (1.10) |
|---|---|---|---|
| 1st pick | QB Burrow | QB Mahomes | QB Kyler |
| QB2 by   | R2 (Tua) | R4 (Watson) | R5–6 (McCarthy + Maye) |
| Early TE | R3 Andrews | R8 Hockenson | R4 McBride |
| **Total QBs** | **6** | **5** | **5** |
| Kickers | 4, first R12 | 3, first R10 | 3, first R12 |

**Championship signal:** the league averages ~4.6 QBs per team, but every champ
rostered **5–6**. In a 2-QB league they treated QB as the scarce resource —
QB1 in round 1, QB2 locked by round 4–5, then kept stacking QB depth.

## Draft-day rules
1. **Round 1 is basically a QB.** If you skip it you fight a shrinking pool
   (9–10 gone by end of R1).
2. **Lock both QB starters by round 4–5**, then keep drafting QBs — aim for
   **5 total**. QB depth is the clearest championship trait.
3. **RB/WR** fill rounds 2–8; non-PPR but WRs go at the same clip as RBs — take
   value, don't force RB.
4. **TE is elite-or-wait.** Grab a top guy at your R3–R4 turn (Andrews / McBride
   / LaPorta tier) or punt him to the double-digit rounds; the middle is dead.
5. **Never reach for kickers.** First K has never gone before round 8. Wait to
   ~rounds 12–14, then take 2–3 in a short window before the pool empties.

## Note for Sengi12
You're the only manager who doesn't open with a QB (avg first-QB round 1.7, you
go WR-first). That WR edge only wins if you pair it with champion-level QB
volume: open WR → **QB-QB in rounds 2–3** → build a 5-deep QB room → elite-or-late
TE → kickers last.
