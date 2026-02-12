import os, time, threading
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from flask import Flask
import pandas as pd
from datetime import datetime

# ---------- CONFIG ----------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMINS = [int(x) for x in os.getenv("ADMINS").split(",")]
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL")  # @channelusername

# ---------- WEB (Render keep-alive) ----------
app = Flask(__name__)
@app.route("/")
def home():
    return "Voting bot running"

def web():
    app.run(host="0.0.0.0", port=10000)

threading.Thread(target=web).start()

# ---------- DB ----------
mongo = MongoClient(MONGO_URL)
db = mongo.votingbot
users = db.users
candidates = db.candidates
settings = db.settings

if not settings.find_one({"_id": "cfg"}):
    settings.insert_one({
        "_id": "cfg",
        "multi_vote": False,
        "vote_open": True
    })

def cfg():
    return settings.find_one({"_id": "cfg"})

# ---------- BOT ----------
bot = Client(
    "votingbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ---------- HELPERS ----------
async def joined(client, user_id):
    try:
        m = await client.get_chat_member(FORCE_CHANNEL, user_id)
        return m.status not in ("left", "kicked")
    except:
        return False

# ---------- START ----------
@bot.on_message(filters.command("start"))
async def start(_, m):
    await m.reply(
        "🗳️ **Voting Bot**\n\n"
        "/vote – Vote\n"
        "/votes – Live votes\n"
        "/myvote – Your vote\n"
        "/leaderboard – Ranking"
    )

# ---------- ADD CANDIDATE ----------
@bot.on_message(filters.command("addcandidate") & filters.user(ADMINS))
async def add_c(_, m):
    try:
        name = m.text.split(None,1)[1]
        candidates.insert_one({"name": name, "votes": 0})
        await m.reply(f"✅ Added: {name}")
    except:
        await m.reply("Use: /addcandidate Name")

# ---------- REMOVE CANDIDATE ----------
@bot.on_message(filters.command("removecandidate") & filters.user(ADMINS))
async def rem_c(_, m):
    name = m.text.split(None,1)[1]
    candidates.delete_one({"name": name})
    await m.reply("🗑️ Removed")

# ---------- VOTE ----------
@bot.on_message(filters.command("vote"))
async def vote(_, m):
    if not cfg()["vote_open"]:
        return await m.reply("❌ Voting closed")

    if not await joined(bot, m.from_user.id):
        return await m.reply(f"❌ Join {FORCE_CHANNEL} first")

    if users.find_one({"uid": m.from_user.id}) and not cfg()["multi_vote"]:
        return await m.reply("❌ You already voted")

    buttons = [[InlineKeyboardButton(c["name"], callback_data=f"v_{c['name']}")]
               for c in candidates.find()]
    await m.reply("Choose candidate:", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query(filters.regex("^v_"))
async def do_vote(_, q):
    uid = q.from_user.id
    name = q.data[2:]

    if users.find_one({"uid": uid}) and not cfg()["multi_vote"]:
        return await q.answer("Already voted", True)

    candidates.update_one({"name": name}, {"$inc": {"votes": 1}})
    users.insert_one({"uid": uid, "vote": name})
    await q.message.edit_text(f"✅ Vote cast for **{name}**")

# ---------- LIVE VOTES ----------
@bot.on_message(filters.command("votes"))
async def votes(_, m):
    txt = "📊 **Live Votes**\n\n"
    for c in candidates.find():
        txt += f"{c['name']} : {c['votes']}\n"
    await m.reply(txt)

# ---------- MY VOTE ----------
@bot.on_message(filters.command("myvote"))
async def myvote(_, m):
    v = users.find_one({"uid": m.from_user.id})
    await m.reply("❌ No vote" if not v else f"🗳️ You voted: {v['vote']}")

# ---------- LEADERBOARD ----------
@bot.on_message(filters.command("leaderboard"))
async def lb(_, m):
    txt = "🏆 **Leaderboard**\n\n"
    for c in candidates.find().sort("votes",-1):
        txt += f"{c['name']} : {c['votes']}\n"
    await m.reply(txt)

# ---------- ADMIN ----------
@bot.on_message(filters.command("multivote") & filters.user(ADMINS))
async def mv(_, m):
    state = m.text.split()[1].lower() == "on"
    settings.update_one({"_id":"cfg"}, {"$set":{"multi_vote": state}})
    await m.reply(f"Multi-vote {'ON' if state else 'OFF'}")

@bot.on_message(filters.command("endvote") & filters.user(ADMINS))
async def end(_, m):
    settings.update_one({"_id":"cfg"}, {"$set":{"vote_open": False}})
    await m.reply("🔒 Voting closed")

@bot.on_message(filters.command("resetvotes") & filters.user(ADMINS))
async def reset(_, m):
    users.delete_many({})
    candidates.update_many({}, {"$set":{"votes":0}})
    await m.reply("🔄 Votes reset")

@bot.on_message(filters.command("broadcast") & filters.user(ADMINS))
async def bc(_, m):
    msg = m.text.split(None,1)[1]
    for u in users.find():
        try: await bot.send_message(u["uid"], msg)
        except: pass
    await m.reply("📢 Broadcast sent")

@bot.on_message(filters.command("export") & filters.user(ADMINS))
async def export(_, m):
    df = pd.DataFrame(list(candidates.find({},{"_id":0})))
    df.to_csv("results.csv", index=False)
    await m.reply_document("results.csv")

@bot.on_message(filters.command("winner") & filters.user(ADMINS))
async def win(_, m):
    c = candidates.find().sort("votes",-1).limit(1)
    for x in c:
        await m.reply(f"🏆 Winner: {x['name']} ({x['votes']})")

# ---------- RUN ----------
bot.run()
