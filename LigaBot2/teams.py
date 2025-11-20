# teams.py
import json, os

BASE = os.path.dirname(__file__)
JUG_FILE = os.path.join(BASE, "jugadores.json")
TEAMS_FILE = os.path.join(BASE, "equipos.json")

def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_players():
    return read_json(JUG_FILE)

def save_players(data):
    write_json(JUG_FILE, data)

def load_teams():
    return read_json(TEAMS_FILE)

def save_teams(data):
    write_json(TEAMS_FILE, data)

def find_player_by_name(name):
    for p in load_players():
        if p["name"].strip().lower() == name.strip().lower():
            return p
    return None

def find_player_by_id(pid):
    for p in load_players():
        if p["id"].lower() == pid.lower():
            return p
    return None

def get_team_by_captain_role(role_name):
    for t in load_teams():
        if t["captain_role"].strip().lower() == role_name.strip().lower():
            return t
    return None

def get_team_by_id(team_id):
    for t in load_teams():
        if t["id"] == team_id or t["id"].strip().lower() == team_id.strip().lower():
            return t
    return None

def update_player(player):
    players = load_players()
    for i,p in enumerate(players):
        if p["id"] == player["id"]:
            players[i] = player
            save_players(players)
            return True
    return False

def update_team(updated):
    teams = load_teams()
    for i,t in enumerate(teams):
        if t["id"] == updated["id"]:
            teams[i] = updated
            save_teams(teams)
            return True
    return False

def transfer_player_by_name(player_name, seller_team_id, buyer_team_id, price):
    # returns True on success, "limite" if buyer reached 3 fichajes, or False on error
    player = find_player_by_name(player_name)
    if not player:
        return False
    if player.get("blinded"):
        return False
    teams = load_teams()
    seller = get_team_by_id(seller_team_id)
    buyer = get_team_by_id(buyer_team_id)
    if not seller or not buyer:
        return False
    # buyer fichajes limit
    if buyer.get("fichajes_hechos",0) >= 3:
        return "limite"
    # check player in seller
    if player["name"] not in seller["players"]:
        return False
    # transfer money
    seller["budget"] = round(seller.get("budget",0) + price, 2)
    buyer["budget"] = round(buyer.get("budget",0) - price, 2)
    # move player
    seller["players"].remove(player["name"])
    buyer["players"].append(player["name"])
    # update player
    player["team"] = buyer["id"]
    # increment fichajes
    buyer["fichajes_hechos"] = buyer.get("fichajes_hechos",0) + 1
    # save
    update_player(player)
    update_team(seller)
    update_team(buyer)
    return True

def buy_player_free(player_name, buyer_team_id, price):
    # if player was free (no seller) – same as transfer but seller is None
    player = find_player_by_name(player_name)
    if not player or player.get("blinded"):
        return False
    buyer = get_team_by_id(buyer_team_id)
    if not buyer:
        return False
    if buyer.get("fichajes_hechos",0) >= 3:
        return "limite"
    # pay price (no seller)
    buyer["budget"] = round(buyer.get("budget",0) - price,2)
    buyer["players"].append(player["name"])
    player["team"] = buyer["id"]
    buyer["fichajes_hechos"] = buyer.get("fichajes_hechos",0) + 1
    update_player(player)
    update_team(buyer)
    return True
