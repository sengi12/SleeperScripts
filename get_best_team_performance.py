import requests, json

sleeper_api = 'https://api.sleeper.app/v1/league/'

def download_players():
    with open('players.json', 'w') as f:
        print('Updating players.json file....')
        all_players = requests.get("https://api.sleeper.app/v1/players/nfl").json()
        json.dump(all_players, f, ensure_ascii=False, indent=4)

def get_player(player_id):
    with open('players.json', 'r') as f:
        all_players = json.load(f)
    return all_players[player_id]

def get_best_team_performance(league_id):
    highest_scores = {}
    highest_score_weeks = {}
    highest_score_players = {}
    highest_score_years = {}
    current_league_id = league_id
    while(current_league_id is not None):
        if (int(current_league_id) == 0):
            break
        current_league = requests.get(f"{sleeper_api}{current_league_id}").json()

        # change logic here to get only a specific seasons worth of data
        if(current_league['season'] in ['2025', '2024', '2023', '2022', '2021', '2020', '2019']):
        # if(current_league['season'] in ['2024']):
        # if True:

            print(f"Scraping Stats: {current_league['name']} < {current_league['season']} >...", end="\r")
            
            regular_season_length = 14 if int(current_league["season"]) >= 2021 else 13
            # regular_season_length = 18
            for week in range(1, regular_season_length):
                matchups = requests.get(f"{sleeper_api}{current_league_id}/matchups/{week}").json()
                for match in matchups:
                    roster_id = match['roster_id']
                    if roster_id not in highest_scores:
                        highest_scores[roster_id] = 0
                        highest_score_weeks[roster_id] = 0
                        highest_score_players[roster_id] = 0
                        highest_score_years[roster_id] = 0
                    if match["points"] > highest_scores[roster_id]:
                        highest_scores[roster_id] = match["points"]
                        highest_score_weeks[roster_id] = week
                        highest_score_years[roster_id] = current_league["season"]
                        mvp_score = 0
                        for player_id in match["starters"]:
                            if player_id not in match['players_points']:
                                # print(f"Error: Bad player_id [{player_id}] in matchup: [{match['matchup_id']}]")
                                pass
                            elif match["players_points"][player_id] > mvp_score:
                                mvp_score = match["players_points"][player_id]
                                player = get_player(player_id)
                                highest_score_players[roster_id] = f"{player['first_name']} {player['last_name']}: {match['players_points'][player_id]}"

        # iterate to previous season...
        current_league_id = current_league['previous_league_id']
    print()
    # get all users associated with their roster_id
    current_users = {}
    users = requests.get(f"{sleeper_api}{league_id}/users/").json()
    rosters = requests.get(f"{sleeper_api}{league_id}/rosters/").json()
    for user in users:
        for roster in rosters:
            if user["user_id"] == roster["owner_id"]:
                current_users[roster['roster_id']] = user['display_name']
    
    # print results
    for roster_id in current_users:
        print(f"{current_users[roster_id]}: \n\t{highest_scores[roster_id]} in Week {highest_score_weeks[roster_id]}, {highest_score_years[roster_id]}\n\tTeam MVP: {highest_score_players[roster_id]}")


league_id = "1180564550988939264" # Originally From Ohio Dynasty League
# league_id = "992219213164748800" # Queen City Kings
# league_id = "990675750879559680" # It Can Be Done
# league_id = "997364941130657792" # Dirty Mikes and the Cincy Boys

get_best_team_performance(league_id)

