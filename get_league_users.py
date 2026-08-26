import requests, json

sleeper_api = 'https://api.sleeper.app/v1/league/'

def get_league_users(league_id):
    league_rosters = requests.get(f"{sleeper_api}{league_id}/rosters").json()
    league_users = requests.get(f"{sleeper_api}{league_id}/users").json()
    # print(json.dumps(league_users, indent=4))
    # print(json.dumps(league_rosters, indent=4))
    users = {
        1:"",
        2:"",
        3:"",
        4:"",
        5:"",
        6:"",
        7:"",
        8:"",
        9:"",
        10:""
    }
    for user in league_users:
        for roster in league_rosters:
            if user["user_id"] == roster["owner_id"]:
                # print(f"{user['display_name']}: {roster['roster_id']}")
                for id in users:
                    if id == roster['roster_id']:
                        users[id] = user['display_name']
    for id in users:
        print(f"{id}: {users[id]}")
    return league_users

# league_id = "919651662468300800" # Originally From Ohio Dynasty League: Current
# league_id = "650354323162763264" # Originally From Ohio Dynasty League: 2021
# league_id = "992219213164748800" # Queen City Kings
# league_id = "990675750879559680" # It Can Be Done
# league_id = "997364941130657792" # Dirty Mikes and the Cincy Boys
league_id = "1389348066355609601" # BAFL 2026

get_league_users(league_id)