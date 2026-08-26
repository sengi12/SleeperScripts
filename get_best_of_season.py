import sys, json, requests, argparse

league_api = 'https://api.sleeper.app/v1/league/'
player_api = 'https://api.sleeper.app/v1/players/nfl/'

def get_players():
    players = requests.get(player_api).json()
    with open('players.json', 'w') as f:
        json.dump(players, f, indent=4)
    print("Wrote players.json")

def get_league(league_id):
    league = requests.get(f"{league_api}{league_id}").json()
    with open('league.json', 'w') as f:
        json.dump(league, f, indent=4)
    print("Wrote league.json")
    return league

def main():
    try:
        # get_league("1180564550988939264")
        get_players()
    except Exception as e:
        print(e)
        exit(1)

if __name__ == "__main__":
    sys.exit(main())