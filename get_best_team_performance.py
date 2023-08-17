import requests

sleeper_api = 'https://api.sleeper.app/v1/league/'

def get_player(player_id):
    players = requests.get("https://api.sleeper.app/v1/players/nfl").json()
    return players[player_id]

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
        if(current_league['season'] != '2023'):

            print(f"Scraping Stats: {current_league['name']} < {current_league['season']} >...", end="\r")
            
            # get all trades for this season
            for week in range(1, 18):
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


league_id = "919651662468300800" # Originally From Ohio Dynasty League
# league_id = "992219213164748800" # Queen City Kings
# league_id = "990675750879559680" # It Can Be Done
# league_id = "997364941130657792" # Dirty Mikes and the Cincy Boys

get_best_team_performance(league_id)

