import requests, json, argparse, sys, csv
import texttable as tt

import os.path
import argparse
import sys
import os
import json
import logging
from datetime import datetime
import csv
import texttable as tt

from sleeper_client import SleeperClient
from sheets_client import SheetsClient
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO)

# module-level mapping from roster_id -> display name
current_users = {}


def download_players():
    sc = SleeperClient()
    sc.save_players()


def get_player(player_id: str):
    sc = SleeperClient()
    players = sc.load_players()
    return players[player_id]


def get_double_headers(args):
    if os.path.isfile(args.double_headers):
        with open(args.double_headers, 'r') as f:
            return json.load(f)
    return None


def get_stats(args, week: int):
    """Collect weekly stats and sum category totals per roster_id.

    Returns: (stats_dict, matchups)
    where stats_dict has keys: passing, receiving, rushing, touchdowns, kicking
    """
    sc = SleeperClient()
    matchups = sc.get_matchups(args.league_id, int(week))
    weekly_stats = sc.get_weekly_stats(args.current_league['season'], int(week))

    passing_yards = {}
    rushing_yards = {}
    receiving_yards = {}
    touchdowns = {}
    kicking = {}

    writer = csv.writer(open('results.csv', 'w'))
    cols_dict = {
        'user': 0, 'player': 1, 'position': 2, 'team': 3,
        'cmp/att': 4, 'pass_yd': 5, 'pass_td': 6, 'pass_int': 7,
        'rush_att': 8, 'rush_yd': 9, 'rush_td': 10,
        'rec/tgt': 11, 'rec_yd': 12, 'rec_td': 13,
        'fum': 14, 'fum_lost': 15, 'xpm/xpa': 16, 'fgm/fga': 17, '2pt': 18
    }
    top_row = ['', '', '', ''] + ['Passing'] + ['', '', ''] + ['Rushing'] + ['', ''] + ['Receiving'] + ['', ''] + ['Fumbles'] + [''] + ['Kicking'] + ['']
    label_row = ['Roster', 'Player', 'Pos', 'Team'] + ['Cmp/Att', 'Yds', 'TD', 'INT'] + ['Att', 'Yards', 'TD'] + ['Rec/Tgt', 'Yds', 'TD'] + ['Total', 'Lost'] + ['xpm/xpa', 'fgm/fga', '2pt']
    writer.writerow(top_row)
    writer.writerow(label_row)

    # initialize totals for each roster in matchups
    for m in matchups:
        rid = m['roster_id']
        passing_yards.setdefault(rid, 0.0)
        rushing_yards.setdefault(rid, 0.0)
        receiving_yards.setdefault(rid, 0.0)
        touchdowns.setdefault(rid, 0.0)
        kicking.setdefault(rid, 0.0)

    # accumulate stats for starters
    for match in matchups:
        rid = match['roster_id']
        starters = match.get('starters', [])
        players_points = match.get('players_points', {})
        for player_info in weekly_stats:
            pid = player_info.get('player_id')
            if pid not in starters:
                continue
            if pid not in players_points:
                # preserve prior behavior: skip players not present in players_points
                continue
            ps = player_info.get('stats', {})
            row = [''] * len(cols_dict)
            row[cols_dict['user']] = current_users.get(rid, '')
            p = player_info.get('player', {})
            row[cols_dict['player']] = f"{p.get('first_name','')} {p.get('last_name','')}"
            row[cols_dict['position']] = p.get('position', '')
            row[cols_dict['team']] = p.get('team', '')

            if 'pass_att' in ps:
                row[cols_dict['cmp/att']] = f"{int(ps.get('pass_cmp', 0))}/{int(ps.get('pass_att', 0))}"
            if 'pass_yd' in ps:
                row[cols_dict['pass_yd']] = int(ps['pass_yd'])
                passing_yards[rid] += float(ps['pass_yd'])
            if 'pass_int' in ps:
                row[cols_dict['pass_int']] = int(ps['pass_int'])
                passing_yards[rid] -= float(ps['pass_int'] * 20)

            if 'rush_att' in ps:
                row[cols_dict['rush_att']] = int(ps['rush_att'])
            if 'rush_yd' in ps:
                row[cols_dict['rush_yd']] = int(ps['rush_yd'])
                rushing_yards[rid] += float(ps['rush_yd'])

            if 'fum' in ps:
                row[cols_dict['fum']] = int(ps['fum'])
            if 'fum_lost' in ps:
                row[cols_dict['fum_lost']] = int(ps['fum_lost'])

            if 'rec_tgt' in ps:
                if 'rec' not in ps:
                    ps['rec'] = 0
                row[cols_dict['rec/tgt']] = f"{int(ps['rec'])}/{int(ps['rec_tgt'])}"
            if 'rec_yd' in ps:
                row[cols_dict['rec_yd']] = int(ps['rec_yd'])
                receiving_yards[rid] += float(ps['rec_yd'])

            if 'pass_td' in ps:
                row[cols_dict['pass_td']] = int(ps['pass_td'])
                touchdowns[rid] += float(ps['pass_td'])
            if 'rec_td' in ps:
                row[cols_dict['rec_td']] = int(ps['rec_td'])
                touchdowns[rid] += float(ps['rec_td'])
            if 'rush_td' in ps:
                row[cols_dict['rush_td']] = int(ps['rush_td'])
                touchdowns[rid] += float(ps['rush_td'])

            if 'pass_2pt' in ps:
                row[cols_dict['2pt']] = (row[cols_dict['2pt']] or 0) + int(ps['pass_2pt'])
                kicking[rid] += float(2 * ps['pass_2pt'])
            if 'rec_2pt' in ps:
                row[cols_dict['2pt']] = (row[cols_dict['2pt']] or 0) + int(ps['rec_2pt'])
                kicking[rid] += float(2 * ps['rec_2pt'])
            if 'rush_2pt' in ps:
                row[cols_dict['2pt']] = (row[cols_dict['2pt']] or 0) + int(ps['rush_2pt'])
                kicking[rid] += float(2 * ps['rush_2pt'])
            if 'xpm' in ps:
                kicking[rid] += float(ps['xpm'])
            if 'fgm' in ps:
                kicking[rid] += float(3 * ps['fgm'])
            if 'xpa' in ps:
                row[cols_dict['xpm/xpa']] = f"{int(ps.get('xpm',0))}/{int(ps.get('xpa',0))}"
            if 'fga' in ps:
                row[cols_dict['fgm/fga']] = f"{int(ps.get('fgm',0))}/{int(ps.get('fga',0))}"

            writer.writerow(row)

    return {
        'passing': passing_yards,
        'receiving': receiving_yards,
        'rushing': rushing_yards,
        'touchdowns': touchdowns,
        'kicking': kicking
    }, matchups


def get_bafl_weekly_outcome(args):
    global current_users
    sc = SleeperClient()

    if args.league_id is not None and int(args.league_id) == 0:
        print(f"Error: Bad League ID: {args.league_id}")
        return

    current_league = sc.get_league(args.league_id)
    args.current_league = current_league
    print(f"Accumulating Stats for: {current_league.get('name','')} < {current_league.get('season','')} > < Week {args.week} >...", end='\r')

    users = sc.get_users(args.league_id)
    rosters = sc.get_rosters(args.league_id)
    for user in users:
        for roster in rosters:
            if user.get('user_id') == roster.get('owner_id'):
                current_users[roster['roster_id']] = user.get('display_name','')

    stats, matchups = get_stats(args, args.week)
    passing_yards = stats['passing']
    receiving_yards = stats['receiving']
    rushing_yards = stats['rushing']
    touchdowns = stats['touchdowns']
    kicking = stats['kicking']

    sheets = SheetsClient()

    # Update header with timestamp and week
    try:
        sheets.update_range(args.spreadsheet_id, 'Scores!C1:D1', [[datetime.now().strftime('%m/%d/%Y %I:%M:%S'), f'WEEK {args.week}']])
    except Exception as e:
        print(f"Failed to update sheet header: {e}")

    matches = []
    stat_row = 3
    for match in matchups:
        if match['matchup_id'] not in matches:
            matches.append(match['matchup_id'])

    for matchup_id in matches:
        team_ids = [m['roster_id'] for m in matchups if m['matchup_id'] == matchup_id]
        tab = tt.Texttable()

        passing_results = int(2 if passing_yards[team_ids[1]] == passing_yards[team_ids[0]] else passing_yards[team_ids[1]] > passing_yards[team_ids[0]])
        receiving_results = int(2 if receiving_yards[team_ids[1]] == receiving_yards[team_ids[0]] else receiving_yards[team_ids[1]] > receiving_yards[team_ids[0]])
        rushing_results = int(2 if rushing_yards[team_ids[1]] == rushing_yards[team_ids[0]] else rushing_yards[team_ids[1]] > rushing_yards[team_ids[0]])
        touchdowns_results = int(2 if touchdowns[team_ids[1]] == touchdowns[team_ids[0]] else touchdowns[team_ids[1]] > touchdowns[team_ids[0]])
        kicking_results = int(2 if kicking[team_ids[1]] == kicking[team_ids[0]] else kicking[team_ids[1]] > kicking[team_ids[0]])

        team1_score = (1 if passing_results == 0 else 0) + (1 if receiving_results == 0 else 0) + (1 if rushing_results == 0 else 0) + (1 if touchdowns_results == 0 else 0) + (1 if kicking_results == 0 else 0)
        team2_score = (1 if passing_results == 1 else 0) + (1 if receiving_results == 1 else 0) + (1 if rushing_results == 1 else 0) + (1 if touchdowns_results == 1 else 0) + (1 if kicking_results == 1 else 0)

        team1_total_yards = passing_yards[team_ids[0]] + receiving_yards[team_ids[0]] + rushing_yards[team_ids[0]]
        team2_total_yards = passing_yards[team_ids[1]] + receiving_yards[team_ids[1]] + rushing_yards[team_ids[1]]

        team1_score = f"{team1_score}*" if team1_score == team2_score and team1_total_yards > team2_total_yards else team1_score
        team2_score = f"{team2_score}*" if team1_score == team2_score and team2_total_yards > team1_total_yards else team2_score

        headings = [team1_score, current_users.get(team_ids[0], ''), 'Categories', current_users.get(team_ids[1], ''), team2_score]
        team1_results = ['✔️' if passing_results == 0 else '', '✔️' if receiving_results == 0 else '', '✔️' if rushing_results == 0 else '', '✔️' if touchdowns_results == 0 else '', '✔️' if kicking_results == 0 else '']
        team1_stats = [passing_yards[team_ids[0]], receiving_yards[team_ids[0]], rushing_yards[team_ids[0]], touchdowns[team_ids[0]], kicking[team_ids[0]]]
        categories = ['Passing', 'Receiving', 'Rushing', 'Touchdowns', 'Kicking', 'Total Yards']
        team2_stats = [passing_yards[team_ids[1]], receiving_yards[team_ids[1]], rushing_yards[team_ids[1]], touchdowns[team_ids[1]], kicking[team_ids[1]]]
        team2_results = ['✔️' if passing_results == 1 else '', '✔️' if receiving_results == 1 else '', '✔️' if rushing_results == 1 else '', '✔️' if touchdowns_results == 1 else '', '✔️' if kicking_results == 1 else '']

        tab.header(headings)
        for row in zip(team1_results, team1_stats, categories, team2_stats, team2_results):
            tab.add_row(row)
        print(tab.draw())

        try:
            values = [
                headings,
                ['✔️' if passing_results == 0 else '', passing_yards[team_ids[0]], 'Passing', passing_yards[team_ids[1]], '✔️' if passing_results == 1 else ''],
                ['✔️' if receiving_results == 0 else '', receiving_yards[team_ids[0]], 'Receiving', receiving_yards[team_ids[1]], '✔️' if receiving_results == 1 else ''],
                ['✔️' if rushing_results == 0 else '', rushing_yards[team_ids[0]], 'Rushing', rushing_yards[team_ids[1]], '✔️' if rushing_results == 1 else ''],
                ['✔️' if touchdowns_results == 0 else '', touchdowns[team_ids[0]], 'Touchdowns', touchdowns[team_ids[1]], '✔️' if touchdowns_results == 1 else ''],
                ['✔️' if kicking_results == 0 else '', kicking[team_ids[0]], 'Kicking', kicking[team_ids[1]], '✔️' if kicking_results == 1 else ''],
                ['', team1_total_yards, 'Total Yards', team2_total_yards, '']
            ]
            data = {'range': f'Scores!B{stat_row}:F{stat_row+6}', 'values': values}
            sheets.batch_update(args.spreadsheet_id, [data])
            stat_row += 8
        except Exception as err:
            print(err)

    double_headers = get_double_headers(args)
    if double_headers is not None:
        print('Calculating Double Headers...')
        for week in double_headers:
            stats_dh, matchups_dh = get_stats(args, week)
            passing_yards = stats_dh['passing']
            receiving_yards = stats_dh['receiving']
            rushing_yards = stats_dh['rushing']
            touchdowns = stats_dh['touchdowns']
            kicking = stats_dh['kicking']
            stat_row = 3
            for match in double_headers[week]['matchups']:
                team_ids = [int(i) for i in match['roster_ids']]
                passing_results = int(2 if passing_yards[team_ids[1]] == passing_yards[team_ids[0]] else passing_yards[team_ids[1]] > passing_yards[team_ids[0]])
                receiving_results = int(2 if receiving_yards[team_ids[1]] == receiving_yards[team_ids[0]] else receiving_yards[team_ids[1]] > receiving_yards[team_ids[0]])
                rushing_results = int(2 if rushing_yards[team_ids[1]] == rushing_yards[team_ids[0]] else rushing_yards[team_ids[1]] > rushing_yards[team_ids[0]])
                touchdowns_results = int(2 if touchdowns[team_ids[1]] == touchdowns[team_ids[0]] else touchdowns[team_ids[1]] > touchdowns[team_ids[0]])
                kicking_results = int(2 if kicking[team_ids[1]] == kicking[team_ids[0]] else kicking[team_ids[1]] > kicking[team_ids[0]])

                team1_score = (1 if passing_results == 0 else 0) + (1 if receiving_results == 0 else 0) + (1 if rushing_results == 0 else 0) + (1 if touchdowns_results == 0 else 0) + (1 if kicking_results == 0 else 0)
                team2_score = (1 if passing_results == 1 else 0) + (1 if receiving_results == 1 else 0) + (1 if rushing_results == 1 else 0) + (1 if touchdowns_results == 1 else 0) + (1 if kicking_results == 1 else 0)

                team1_total_yards = passing_yards[team_ids[0]] + receiving_yards[team_ids[0]] + rushing_yards[team_ids[0]]
                team2_total_yards = passing_yards[team_ids[1]] + receiving_yards[team_ids[1]] + rushing_yards[team_ids[1]]

                team1_score_dec = team1_score + 0.5 if team1_score == team2_score and team1_total_yards > team2_total_yards else team1_score
                team2_score_dec = team2_score + 0.5 if team1_score == team2_score and team2_total_yards > team1_total_yards else team2_score
                team1_score = f"{team1_score}*" if team1_score == team2_score and team1_total_yards > team2_total_yards else team1_score
                team2_score = f"{team2_score}*" if team1_score == team2_score and team2_total_yards > team1_total_yards else team2_score

                # update standings in rosters if applicable
                if int(week) <= int(args.week):
                    for i in range(len(rosters)):
                        if rosters[i]['roster_id'] in team_ids:
                            if 'fpts_against' not in rosters[i]['settings']:
                                rosters[i]['settings']['fpts_against'] = 0
                            if rosters[i]['roster_id'] == team_ids[0]:
                                rosters[i]['settings']['wins'] = int(rosters[i]['settings']['wins']) + 1 if team1_score_dec > team2_score_dec else rosters[i]['settings']['wins']
                                rosters[i]['settings']['losses'] = int(rosters[i]['settings']['losses']) + 1 if team1_score_dec < team2_score_dec else rosters[i]['settings']['losses']
                                rosters[i]['settings']['fpts'] = int(rosters[i]['settings']['fpts']) + team1_score_dec
                                rosters[i]['settings']['fpts_against'] = int(rosters[i]['settings']['fpts_against']) + team2_score_dec
                            if rosters[i]['roster_id'] == team_ids[1]:
                                rosters[i]['settings']['wins'] = int(rosters[i]['settings']['wins']) + 1 if team2_score_dec > team1_score_dec else rosters[i]['settings']['wins']
                                rosters[i]['settings']['losses'] = int(rosters[i]['settings']['losses']) + 1 if team2_score_dec < team1_score_dec else rosters[i]['settings']['losses']
                                rosters[i]['settings']['fpts'] = int(rosters[i]['settings']['fpts']) + team2_score_dec
                                rosters[i]['settings']['fpts_against'] = int(rosters[i]['settings']['fpts_against']) + team1_score_dec

                if int(week) == int(args.week):
                    headings = [team1_score, current_users.get(team_ids[0], ''), 'Categories', current_users.get(team_ids[1], ''), team2_score]
                    dh_values = [
                        headings,
                        ['✔️' if passing_results == 0 else '', passing_yards[team_ids[0]], 'Passing', passing_yards[team_ids[1]], '✔️' if passing_results == 1 else ''],
                        ['✔️' if receiving_results == 0 else '', receiving_yards[team_ids[0]], 'Receiving', receiving_yards[team_ids[1]], '✔️' if receiving_results == 1 else ''],
                        ['✔️' if rushing_results == 0 else '', rushing_yards[team_ids[0]], 'Rushing', rushing_yards[team_ids[1]], '✔️' if rushing_results == 1 else ''],
                        ['✔️' if touchdowns_results == 0 else '', touchdowns[team_ids[0]], 'Touchdowns', touchdowns[team_ids[1]], '✔️' if touchdowns_results == 1 else ''],
                        ['✔️' if kicking_results == 0 else '', kicking[team_ids[0]], 'Kicking', kicking[team_ids[1]], '✔️' if kicking_results == 1 else ''],
                        ['', team1_total_yards, 'Total Yards', team2_total_yards, '']
                    ]
                    dh_data = {'range': f'Scores!H{stat_row}:L{stat_row+6}', 'values': dh_values}
                    sheets.batch_update(args.spreadsheet_id, [dh_data])
                    stat_row += 8
                elif args.week not in double_headers:
                    dh_values = [['', '', '', '', '']] * 7
                    dh_data = [
                        {'range': 'Scores!H3:L9', 'values': dh_values},
                        {'range': 'Scores!H11:L17', 'values': dh_values},
                        {'range': 'Scores!H19:L25', 'values': dh_values},
                        {'range': 'Scores!H27:L33', 'values': dh_values},
                        {'range': 'Scores!H35:L41', 'values': dh_values},
                    ]
                    sheets.batch_update(args.spreadsheet_id, dh_data)

    if args.standings:
        standings = sorted(rosters, key=lambda d: d['settings']['fpts'], reverse=True)
        standings = sorted(standings, key=lambda d: d['settings']['wins'], reverse=True)
        rank = 1
        values = []
        for roster in standings:
            print(f"{roster['settings']['wins']}-{roster['settings']['losses']}: {current_users[roster['roster_id']]}: {roster['settings']['fpts']}-{roster['settings']['fpts_against']}")
            values.append([rank, current_users[roster['roster_id']], f"{roster['settings']['wins']}-{roster['settings']['losses']}", roster['settings']['fpts'], roster['settings']['fpts_against']])
            rank += 1
        sheets.batch_update(args.spreadsheet_id, [{'range': 'Scores!N4:R14', 'values': values}])


def get_league_leaders(args):
    global current_users
    print('Calculating League Leaders...')
    passing_leaders = {}
    rushing_leaders = {}
    receiving_leaders = {}
    touchdown_leaders = {}
    kicking_leaders = {}
    yardage_leaders = {}

    sc = SleeperClient()
    users = sc.get_users(args.league_id)
    rosters = sc.get_rosters(args.league_id)
    for user in users:
        for roster in rosters:
            if user.get('user_id') == roster.get('owner_id'):
                current_users[roster['roster_id']] = user.get('display_name','')

    for week in range(1, 16):
        stats, matchups = get_stats(args, week)
        passing_yards = stats['passing']
        receiving_yards = stats['receiving']
        rushing_yards = stats['rushing']
        touchdowns = stats['touchdowns']
        kicking = stats['kicking']
        for rid in current_users:
            passing_leaders.setdefault(rid, 0)
            receiving_leaders.setdefault(rid, 0)
            rushing_leaders.setdefault(rid, 0)
            touchdown_leaders.setdefault(rid, 0)
            kicking_leaders.setdefault(rid, 0)
            yardage_leaders.setdefault(rid, 0)
            passing_leaders[rid] += passing_yards.get(rid, 0)
            receiving_leaders[rid] += receiving_yards.get(rid, 0)
            rushing_leaders[rid] += rushing_yards.get(rid, 0)
            touchdown_leaders[rid] += touchdowns.get(rid, 0)
            kicking_leaders[rid] += kicking.get(rid, 0)
            yardage_leaders[rid] += passing_yards.get(rid, 0) + receiving_yards.get(rid, 0) + rushing_yards.get(rid, 0)

    def write_top(range_name, leaders):
        rank = 1
        values = []
        for rid, val in list(leaders.items()):
            values.append([rank, current_users.get(rid, ''), str(int(val))])
            rank += 1
            if rank == 6:
                break
        SheetsClient().batch_update(args.spreadsheet_id, [{'range': range_name, 'values': values}])

    passing_leaders = dict(sorted(passing_leaders.items(), key=lambda x: x[1], reverse=True))
    receiving_leaders = dict(sorted(receiving_leaders.items(), key=lambda x: x[1], reverse=True))
    rushing_leaders = dict(sorted(rushing_leaders.items(), key=lambda x: x[1], reverse=True))
    touchdown_leaders = dict(sorted(touchdown_leaders.items(), key=lambda x: x[1], reverse=True))
    kicking_leaders = dict(sorted(kicking_leaders.items(), key=lambda x: x[1], reverse=True))
    yardage_leaders = dict(sorted(yardage_leaders.items(), key=lambda x: x[1], reverse=True))

    write_top('Scores!N18:P22', passing_leaders)
    write_top('Scores!N27:P31', receiving_leaders)
    write_top('Scores!N36:P40', rushing_leaders)
    write_top('Scores!S18:U22', touchdown_leaders)
    write_top('Scores!S27:U31', kicking_leaders)
    write_top('Scores!S36:U40', yardage_leaders)


def main(args):
    if args.update:
        download_players()

    max_attempts = 2
    attempt = 0
    while attempt < max_attempts:
        try:
            get_bafl_weekly_outcome(args)
            if args.leaders:
                get_league_leaders(args)
            break
        except Exception as e:
            is_auth_error = False
            if isinstance(e, RefreshError):
                is_auth_error = True
            elif isinstance(e, HttpError):
                try:
                    status = int(getattr(e, 'resp', {}).get('status', 0))
                except Exception:
                    status = 0
                if status in (401, 403):
                    is_auth_error = True

            if is_auth_error and os.path.exists('token.json'):
                logging.info('Detected auth error; removing token.json and retrying auth flow...')
                try:
                    os.remove('token.json')
                except OSError:
                    pass
                attempt += 1
                continue
            print(e)
            exit(1)


if __name__ == '__main__':
    title = 'BAFL'
    description = 'Determine Weekly Matchup Outcomes'
    parser = argparse.ArgumentParser(description=f"{title}\n\t{description}", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-id', '--league_id', help='League ID for the league you wish to work with', default='1124833534347849728', required=False)
    parser.add_argument('--current_league', help=argparse.SUPPRESS, required=False)
    parser.add_argument('--spreadsheet_id', help=argparse.SUPPRESS, required=False, default='1r-kT5LKsVc_TIxEzCML2sjD_XdexTobQQoEbKPq04Xo')
    parser.add_argument('-w', '--week', help='Week to run the results')
    parser.add_argument('-d', '--double_headers', help='Provide a json file which describes the double headers for this league year', default='double_headers.json')
    parser.add_argument('-s', '--standings', help='Calculate the standings with double headers included', action='store_true')
    parser.add_argument('-l', '--leaders', help='Calculate the league leaders in all major categories', action='store_true')
    parser.add_argument('-u', '--update', help='Update the players.json file', action='store_true', required=False)

    args = parser.parse_args()
    sys.exit(main(args))
