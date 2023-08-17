import requests

sleeper_api = 'https://api.sleeper.app/v1/league/'

def get_all_trades(current_league_id):
    trade_totals = {}
    while(current_league_id is not None):
        if (int(current_league_id) == 0):
            break
        trades = []
        current_users = {}
        trades_per_year = {}
        current_league = requests.get(f"{sleeper_api}{current_league_id}").json()

        users = requests.get(f"{sleeper_api}{current_league_id}/users/").json()
        rosters = requests.get(f"{sleeper_api}{current_league_id}/rosters/").json()

        print(f"{current_league['name']}: {current_league['season']}")
        
        # get all trades for this season
        for week in range(1, 17):
            trans = requests.get(f"{sleeper_api}{current_league_id}/transactions/{week}").json()
            for tran in trans:
                if tran["type"] == "trade":
                    trades.append(tran)

        # get all users associated with their roster_id
        for user in users:
            for roster in rosters:
                if user["user_id"] == roster["owner_id"]:
                    current_users[roster['roster_id']] = user['display_name']
                    trades_per_year[roster['roster_id']] = 0
                if roster["roster_id"] not in trade_totals:
                    trade_totals[roster['roster_id']] = 0

        # thanks to Ethan...
        for i in range(1,12):
            if i not in current_users:
                current_users[i] = f'Team {i}'
                trades_per_year[i] = 0

        # calculate trade totals for each team
        for trade in trades:
            for id in trade["roster_ids"]:
                trades_per_year[id] = trades_per_year[id] + 1
                trade_totals[id] = trade_totals[id] + 1

        for roster_id in current_users:
            print(f"\t{current_users[roster_id]}: {trades_per_year[roster_id]}")

        # iterate to previous season...
        current_league_id = current_league['previous_league_id']
    print(f"{current_league['name']} All-Time Trade Totals:")
    for roster_id in current_users:
            print(f"\t{current_users[roster_id]}: {trade_totals[roster_id]}")


league_id = "919651662468300800" # Originally From Ohio Dynasty League
# league_id = "992219213164748800" # Queen City Kings
# league_id = "990675750879559680" # It Can Be Done
# league_id = "997364941130657792" # Dirty Mikes and the Cincy Boys

get_all_trades(league_id)

