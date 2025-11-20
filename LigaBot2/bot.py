# bot.py
import discord, json, asyncio, os
from discord.ext import commands, tasks
from pathlib import Path
import market, teams, utils

BASE = Path(__file__).parent
with open(BASE/"config.json", "r", encoding="utf-8") as f:
    CFG = json.load(f)

PREFIX = CFG.get("PREFIX","!")
ADMIN_ROLE = CFG.get("ADMIN_ROLE","AdminLiga")
FICH_CHANNEL = CFG.get("FICHAJES_CHANNEL","fichajes")
AUTO_ADD = CFG.get("AUTO_DAILY_ADD", True)
DAILY_ADD_COUNT = CFG.get("DAILY_ADD_COUNT", 10)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

def user_roles_names(member):
    return [r.name for r in member.roles]

def get_captain_role_of_user(member):
    # returns the captain role name if found
    for r in member.roles:
        if r.name.startswith("Capitán de "):
            return r.name
    return None

async def announce_channel():
    guilds = bot.guilds
    if not guilds: return None
    guild = guilds[0]
    ch = discord.utils.get(guild.text_channels, name=FICH_CHANNEL)
    return ch

@bot.event
async def on_ready():
    print(f"Bot listo: {bot.user}")
    if AUTO_ADD:
        if not daily_add_task.is_running():
            daily_add_task.start()

# -----------------------
# DAILY ADD TASK
# -----------------------
@tasks.loop(hours=24)
async def daily_add_task():
    await bot.wait_until_ready()
    names = market.daily_add_random(DAILY_ADD_COUNT)
    if not names:
        return
    ch = await announce_channel()
    if ch:
        await ch.send(f"🌟 **Mercado diario**: se han añadido {len(names)} jugadores al mercado (subasta):\n" + ", ".join(names))

# -----------------------
# ADMIN: open/close market
# -----------------------
@bot.command()
async def openmarket(ctx):
    if ADMIN_ROLE not in user_roles_names(ctx.author):
        return await ctx.send("❌ Solo admins.")
    market.open_market()
    await ctx.send("🟢 Mercado abierto.")
    ch = await announce_channel()
    if ch:
        await ch.send("🟢 El mercado ha sido abierto por la organización.")

@bot.command()
async def closemarket(ctx):
    if ADMIN_ROLE not in user_roles_names(ctx.author):
        return await ctx.send("❌ Solo admins.")
    results = market.close_market()
    await ctx.send("🔴 Mercado cerrado.")
    ch = await announce_channel()
    if ch:
        for r in results:
            await ch.send(f"💰 **FICHAJE**: {r['buyer']} ha fichado a **{r['player']}** por {r['price']}M (vendedor: {r['seller']})")
            utils.save_hist({"player":r['player'],"seller":r['seller'],"buyer":r['buyer'],"price":r['price']})

# -----------------------
# Capitán: poner en venta (public)
# -----------------------
@bot.command()
async def ponerventa(ctx, *, args: str):
    # usage: !ponerventa NombreJugador precio [locked=yes/no]
    # only captain role allowed
    cap_role = get_captain_role_of_user(ctx.author)
    if not cap_role:
        return await ctx.send("❌ Tienes que tener rol de capitán para poner jugadores en venta.")
    try:
        parts = args.rsplit(" ",2)
        name = parts[0].strip()
        price = float(parts[1])
        locked = False
        if len(parts)==3:
            locked = parts[2].lower() in ("yes","si","true","1")
    except:
        return await ctx.send("Uso: !ponerventa NombreJugador precio [locked=yes]")

    # find player's id and check belongs to team
    t = teams.get_team_by_captain_role(cap_role)
    if not t:
        return await ctx.send("No se ha encontrado tu equipo.")
    p = teams.find_player_by_name(name)
    if not p:
        return await ctx.send("Jugador no encontrado.")
    if p["team"] != t["id"]:
        return await ctx.send("Ese jugador no es de tu equipo.")
    if p.get("blinded"):
        return await ctx.send("Jugador blindado. No puede ponerse a la venta.")
    ok = market.post_public_offer(p["id"], p["name"], t["id"], price, locked)
    if ok:
        await ctx.send(f"✅ {p['name']} puesto en venta por {price}M (locked={locked}).")
    else:
        await ctx.send("❌ Error al publicar oferta.")

# -----------------------
# Capitán: post private offer
# -----------------------
@bot.command()
async def ofertaprivada(ctx, target_rol: str, player_name: str, price: float):
    cap_role = get_captain_role_of_user(ctx.author)
    if not cap_role:
        return await ctx.send("❌ Solo capitanes pueden enviar ofertas privadas.")
    # target_rol should match exact role name; e.g. "Capitán de Betis FC"
    p = teams.find_player_by_name(player_name)
    if not p:
        return await ctx.send("Jugador no encontrado.")
    if p.get("blinded"):
        return await ctx.send("Jugador blindado.")
    # post private offer
    market.post_private_offer(target_rol, p["name"], cap_role, price)
    # DM the target (if member exists)
    # find member with that role in server
    guild = ctx.guild
    members = [m for m in guild.members if any(r.name==target_rol for r in m.roles)]
    for m in members:
        try:
            await m.send(f"📩 Oferta privada: {ctx.author.display_name} ofrece {price}M por **{p['name']}**. Para aceptar escribe: `!aceptar_privada \"{p['name']}\"`")
        except:
            pass
    await ctx.send("✅ Oferta privada enviada (si el capitán está en el servidor le llegará por DM).")

# -----------------------
# Capitán: accept private offer
# -----------------------
@bot.command()
async def aceptar_privada(ctx, *, player_name: str):
    cap_role = get_captain_role_of_user(ctx.author)
    if not cap_role:
        return await ctx.send("❌ Solo capitanes pueden aceptar ofertas.")
    ok, res = market.accept_private_offer(cap_role, player_name)
    if not ok:
        return await ctx.send(f"❌ {res}")
    # announce and save history
    ch = await announce_channel()
    if ch:
        await ch.send(f"💰 **FICHAJE PRIVADO**: {res['buyer']} compra a **{res['player']}** por {res['price']}M (vendedor: {res['seller']})")
    utils.save_hist(res)
    await ctx.send("✅ Oferta privada aceptada y fichaje realizado.")

# -----------------------
# Capitán: pujar en auction
# -----------------------
@bot.command()
async def pujar(ctx, player_name: str, amount: float):
    cap_role = get_captain_role_of_user(ctx.author)
    if not cap_role:
        return await ctx.send("❌ Solo capitanes pueden pujar.")
    ok,msg = market.pujar(player_name, cap_role, amount)
    if not ok:
        return await ctx.send(f"❌ {msg}")
    await ctx.send("✅ Puja registrada.")

# -----------------------
# Capitán: clausulazo (paga 1.5x valor)
# -----------------------
@bot.command()
async def clausulazo(ctx, *, player_name: str):
    cap_role = get_captain_role_of_user(ctx.author)
    if not cap_role:
        return await ctx.send("❌ Solo capitanes.")
    ok, res = market.pay_clause_and_transfer(player_name, cap_role)
    if not ok:
        return await ctx.send(f"❌ {res}")
    # announce
    ch = await announce_channel()
    if ch:
        await ch.send(f"💥 **CLAUSULA PAGADA**: {res['buyer']} ha pagado {res['price']}M y fichado a **{res['player']}** (vendedor: {res['seller']})")
    utils.save_hist(res)
    await ctx.send("✅ Clausula pagada, jugador transferido.")

# -----------------------
# Capitán: asignar valores a 3 jugadores (max 60M)
# -----------------------
@bot.command()
async def asignar_valores(ctx, *pairs):
    # usage: !asignar_valores "Jugador1" 20 "Jugador2" 25 "Jugador3" 15
    cap_role = get_captain_role_of_user(ctx.author)
    if not cap_role:
        return await ctx.send("❌ Solo capitanes.")
    # parse pairs: expecting even number of args: name value name value ...
    if len(pairs) % 2 != 0 or len(pairs) == 0 or len(pairs) > 6:
        return await ctx.send("Uso: !asignar_valores \"Jugador1\" 20 \"Jugador2\" 20 \"Jugador3\" 20  (max 3 jugadores; total ≤60)")
    items = []
    total = 0
    for i in range(0,len(pairs),2):
        name = pairs[i]
        try:
            val = float(pairs[i+1])
        except:
            return await ctx.send("Error en los valores. Usa números.")
        items.append((name,val))
        total += val
    if total > 60:
        return await ctx.send("❌ El total supera 60M.")
    if len(items)>3:
        return await ctx.send("❌ Máximo 3 jugadores.")
    # apply values: only players that are NOT captains and not blind
    changed = []
    players = teams.load_players()
    for name,val in items:
        p = teams.find_player_by_name(name)
        if not p:
            return await ctx.send(f"Jugador {name} no encontrado.")
        if p.get("captain"):
            return await ctx.send(f"No puedes asignar valor a un capitán: {name}")
        if p.get("blinded"):
            return await ctx.send(f"No puedes asignar valor a blindado: {name}")
        p["value"] = float(val)
        p["clause"] = round(float(val)*1.5,2)
        teams.update_player(p)
        changed.append(f"{name} -> {val}M (cláusula {p['clause']}M)")
    await ctx.send("✅ Valores asignados:\n" + "\n".join(changed))

# -----------------------
# Comandos info
# -----------------------
@bot.command()
async def ofertas(ctx):
    m = market.read()
    res = []
    for o in m.get("offers",[]):
        res.append(f"{o['player_name']} | vendedor: {o['seller']} | price: {o['price']}M | locked:{o.get('locked',False)}")
    if not res:
        return await ctx.send("No hay ofertas públicas.")
    await ctx.send("```" + "\n".join(res) + "```")

@bot.command()
async def auctions(ctx):
    m = market.read()
    if not m.get("auctions"):
        return await ctx.send("No hay subastas activas.")
    out=[]
    for pname,auc in m["auctions"].items():
        bids = auc.get("bids",[])
        top = max([b["amount"] for b in bids]) if bids else auc["start_price"]
        out.append(f"{pname} | vendedor: {auc['seller_team']} | top: {top}M")
    await ctx.send("```" + "\n".join(out) + "```")

@bot.command()
async def private_offers(ctx):
    cap_role = get_captain_role_of_user(ctx.author)
    if not cap_role:
        return await ctx.send("❌ Solo capitanes.")
    lst = market.get_private_offers_for(cap_role)
    if not lst:
        return await ctx.send("No tienes ofertas privadas.")
    s = "\n".join([f"{o['seller_role']} ofrece {o['price']}M por {o['player_name']}" for o in lst])
    await ctx.author.send("Tus ofertas privadas:\n" + s)
    await ctx.send("✅ Te he enviado tus ofertas privadas por DM.")

@bot.command()
async def history(ctx):
    hist = utils.read_hist()
    if not hist:
        return await ctx.send("No hay fichajes aún.")
    lines = []
    for h in hist:
        lines.append(f"{h['buyer']} fichó a {h['player']} por {h['price']}M (v: {h.get('seller')})")
    await ctx.send("```" + "\n".join(lines) + "```")

# -----------------------
# Run bot
# -----------------------
if __name__ == "__main__":
    token = CFG.get("TOKEN")
    if not token or token=="YOUR_DISCORD_BOT_TOKEN_HERE":
        print("PON TU TOKEN EN config.json")
    else:
        bot.run(token)

