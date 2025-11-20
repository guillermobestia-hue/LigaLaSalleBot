# market.py
import json, os, random, math
from teams import load_players, load_teams, find_player_by_name, update_player, update_team, get_team_by_id, transfer_player_by_name, buy_player_free

BASE = os.path.dirname(__file__)
MERC_FILE = os.path.join(BASE, "mercado.json")

def read():
    if not os.path.exists(MERC_FILE):
        with open(MERC_FILE,"w",encoding="utf-8") as f:
            json.dump({"open":False,"auctions":{},"offers":[],"private_offers":{},"dueños":{}}, f, indent=2, ensure_ascii=False)
    with open(MERC_FILE,"r",encoding="utf-8") as f:
        return json.load(f)

def write(data):
    with open(MERC_FILE,"w",encoding="utf-8") as f:
        json.dump(data,f, indent=2, ensure_ascii=False)

def open_market():
    m = read()
    m["open"] = True
    write(m)
    return True

def close_market():
    m = read()
    m["open"] = False
    # resolve auctions: highest bid wins
    results = []
    for pname, auc in list(m["auctions"].items()):
        bids = auc.get("bids",[])
        if not bids:
            # no bids, return player to seller (nada)
            continue
        # find highest bid
        bids_sorted = sorted(bids, key=lambda x: x["amount"], reverse=True)
        winner = bids_sorted[0]
        buyer_role = winner["captain_role"]
        amount = winner["amount"]
        seller_team_id = auc["seller_team"]
        # perform transfer; buyer role maps to team id
        # need to get buyer team id via teams.json: captain_role -> team.id
        buyer_team = None
        for t in load_teams():
            if t["captain_role"].strip().lower() == buyer_role.strip().lower():
                buyer_team = t
                break
        if not buyer_team:
            continue
        res = transfer_player_by_name(pname, seller_team_id, buyer_team["id"], amount)
        if res == True:
            results.append({"player":pname,"buyer":buyer_team["id"],"seller":seller_team_id,"price":amount})
            # mark dueño
            m["dueños"][pname] = buyer_team["id"]
        # if limite or False, skip (no change)
    # clear auctions
    m["auctions"] = {}
    write(m)
    return results

def post_public_offer(player_id, player_name, seller_team_id, price, locked=False):
    m = read()
    # prevent selling if blind
    p = find_player_by_name(player_name)
    if not p: return False
    if p.get("blinded"): return False
    # remove existing public offers for same player
    m["offers"] = [o for o in m["offers"] if o["player_id"]!=player_id]
    m["offers"].append({"player_id":player_id,"player_name":player_name,"seller":seller_team_id,"price":float(price),"locked":bool(locked)})
    write(m)
    return True

def remove_public_offer(player_name):
    m = read()
    m["offers"] = [o for o in m["offers"] if o["player_name"].lower()!=player_name.lower()]
    write(m)

def post_private_offer(target_role, player_name, seller_role, price):
    m = read()
    lst = m.get("private_offers",{})
    if target_role not in lst:
        lst[target_role]=[]
    lst[target_role].append({"player_name":player_name,"seller_role":seller_role,"price":float(price)})
    m["private_offers"]=lst
    write(m)
    return True

def get_private_offers_for(role_name):
    return read().get("private_offers",{}).get(role_name,[])

def accept_private_offer(target_role, player_name):
    m = read()
    offers = m.get("private_offers",{}).get(target_role,[])
    chosen=None
    for o in offers:
        if o["player_name"].strip().lower() == player_name.strip().lower():
            chosen=o
            break
    if not chosen:
        return False, "No tienes esa oferta."
    # perform transfer between seller_role -> target_role teams
    seller_role = chosen["seller_role"]
    price = chosen["price"]
    # map roles to team ids
    seller_team=None
    buyer_team=None
    for t in load_teams():
        if t["captain_role"].strip().lower() == seller_role.strip().lower():
            seller_team=t
        if t["captain_role"].strip().lower() == target_role.strip().lower():
            buyer_team=t
    if not seller_team or not buyer_team:
        return False, "Equipos no encontrados."
    # transfer
    ok = transfer_player_by_name(player_name, seller_team["id"], buyer_team["id"], price)
    if ok == True:
        # remove the offer
        m["private_offers"][target_role] = [o for o in offers if o["player_name"].lower()!=player_name.lower()]
        write(m)
        m = read()
        m["dueños"][player_name] = buyer_team["id"]
        write(m)
        return True, {"player":player_name,"seller":seller_team["id"],"buyer":buyer_team["id"],"price":price}
    elif ok == "limite":
        return False, "El comprador tiene ya 3 fichajes."
    else:
        return False, "Transferencia fallida."

def place_auction(player_name, seller_team_id, start_price):
    m = read()
    # do not add if blind or captain
    p = find_player_by_name(player_name)
    if not p: return False
    if p.get("blinded"): return False
    auctions = m.get("auctions",{})
    auctions[player_name] = {"seller_team":seller_team_id,"start_price":float(start_price),"bids":[]}
    m["auctions"]=auctions
    write(m)
    return True

def pujar(player_name, captain_role, amount):
    m = read()
    auc = m.get("auctions",{}).get(player_name)
    if not auc:
        return False, "No hay subasta para ese jugador."
    # prevent bidding by seller
    seller = auc["seller_team"]
    # map captain_role to team id quickly
    buyer_team = None
    for t in load_teams():
        if t["captain_role"].strip().lower() == captain_role.strip().lower():
            buyer_team=t
            break
    if not buyer_team:
        return False, "Tu equipo no encontrado."
    if buyer_team["id"] == seller:
        return False, "No puedes pujar contra tu propio jugador."
    # add bid
    bids = auc.get("bids",[])
    bids.append({"captain_role":captain_role,"amount":float(amount)})
    auc["bids"]=bids
    m["auctions"][player_name]=auc
    write(m)
    return True, "Puja registrada."

def pay_clause_and_transfer(player_name, buyer_role):
    m = read()
    p = find_player_by_name(player_name)
    if not p:
        return False, "Jugador no existe."
    clause = float(p.get("clause",0))
    if clause<=0:
        return False, "Jugador no tiene cláusula."
    # owner team
    owner_team_id = m.get("dueños",{}).get(player_name)
    if not owner_team_id:
        return False, "Jugador no tiene dueño claro (uso compra normal)."
    # get buyer team
    buyer_team=None
    for t in load_teams():
        if t["captain_role"].strip().lower() == buyer_role.strip().lower():
            buyer_team=t
            break
    if not buyer_team:
        return False, "Equipo comprador no encontrado."
    # check budget
    if buyer_team.get("budget",0) < clause:
        return False, "No tienes presupuesto para pagar la cláusula."
    # transfer (ignores auctions/offers)
    res = transfer_player_by_name(player_name, owner_team_id, buyer_team["id"], clause)
    if res == True:
        # update dueños
        m["dueños"][player_name]=buyer_team["id"]
        write(m)
        return True, {"player":player_name,"buyer":buyer_team["id"],"seller":owner_team_id,"price":clause}
    elif res == "limite":
        return False, "Has alcanzado 3 fichajes."
    else:
        return False, "Transferencia fallida."

def daily_add_random(n=10):
    # add n random players (not blind, not captain) to auctions with start price = their value (must be >0)
    players = load_players()
    pool = [p for p in players if not p.get("blinded") and not p.get("captain")]
    random.shuffle(pool)
    selected = []
    for p in pool:
        if len(selected)>=n:
            break
        if p.get("value",0) and p.get("value",0)>0:
            selected.append(p)
    if not selected:
        return []
    m = read()
    for p in selected:
        # choose seller as current owner team if any (if owned by team list in equipos.json)
        seller_team_id = p.get("team")
        # if seller_team_id missing, treat as free and set seller_team_id None
        start_price = p.get("value")
        # place auction
        auctions = m.get("auctions",{})
        auctions[p["name"]] = {"seller_team":seller_team_id,"start_price":float(start_price),"bids":[]}
        m["auctions"]=auctions
    write(m)
    return [p["name"] for p in selected]
