import requests, json, argparse, sys

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

def get_eliminated_teams(args):
    lowest_scores = {}
    lowest_score_users = {}
    lowest_score_players = {}
    current_league_id = args.league_id
    while(current_league_id is not None):
        if (int(current_league_id) == 0):
            break
        current_league = requests.get(f"{sleeper_api}{current_league_id}").json()

        # change logic here to get only a specific seasons worth of data
        # if(current_league['season'] in ['2024']):

        print(f"Scraping Stats: {current_league['name']} < {current_league['season']} >...", end="\r")
        
        # get all matchups for this season
        for week in range(1, 18):
            matchups = requests.get(f"{sleeper_api}{current_league_id}/matchups/{week}").json()
            for match in matchups:
                roster_id = match['roster_id']
                if week not in lowest_scores:
                    lowest_scores[week] = 300
                    lowest_score_players[week] = 0
                    lowest_score_users[week] = 0
                if match["points"] < lowest_scores[week] and match["points"] != 0:
                    lowest_scores[week] = match["points"]
                    lowest_score_users[week] = roster_id
                    mvp_score = 100
                    for player_id in match["starters"]:
                        if player_id not in match['players_points']:
                            # print(f"Error: Bad player_id [{player_id}] in matchup: [{match['matchup_id']}]")
                            pass
                        elif match["players_points"][player_id] < mvp_score:
                            mvp_score = match["players_points"][player_id]
                            player = get_player(player_id)
                            lowest_score_players[week] = f"{player['first_name']} {player['last_name']}: {match['players_points'][player_id]}"

        # iterate to previous season...
        # current_league_id = current_league['previous_league_id']
        current_league_id = None
    print()
    # get all users associated with their roster_id
    current_users = {}
    users = requests.get(f"{sleeper_api}{args.league_id}/users/").json()
    rosters = requests.get(f"{sleeper_api}{args.league_id}/rosters/").json()
    for user in users:
        for roster in rosters:
            if user["user_id"] == roster["owner_id"]:
                current_users[roster['roster_id']] = user['display_name']
    
    # print results
    for week in range(1,int(args.week)+1):
        print(f"Week {week}:\n      {lowest_scores[week]}: @{current_users[lowest_score_users[week]]}\n      {lowest_score_players[week]}")


if __name__ == "__main__":

    # league_id = "919651662468300800" # Originally From Ohio Dynasty League
    # league_id = "992219213164748800" # Queen City Kings
    # league_id = "990675750879559680" # It Can Be Done
    # league_id = "997364941130657792" # Dirty Mikes and the Cincy Boys
    # league_id = "992432295334187008" # Last Man Standing League


    title = "Survivor League"
    description = "Grab each weeks eliminated team"
    parser = argparse.ArgumentParser(description=f"{title}\n\t{description}", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-id', '--league_id', help='League ID for the league you wish to work with', default="992432295334187008", required=False) # Default: Last Man Standing League 2023
    parser.add_argument('-w', '--week', help='Week to run the results', required=True)
    args = parser.parse_args()

    sys.exit(get_eliminated_teams(args))

