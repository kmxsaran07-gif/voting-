import os, threading, time, csv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from flask import Flask
from datetime import datetime
import pandas as pd

# ============ CONFIG ============
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
ADMINS = [int(x) for x in os.getenv("ADMINS").split(",")]

# ============ WEB ============
app = Flask(__name__)
@app.route("/")
def home():
    return "Voting Bot Running"

def run_web():
    app.run(host="0.0.0.0", port=10000)

threading.Thread(target=run_web).start()

# ============ DB ============
mongo = MongoClient(MONGO_URL)
db = mongo["voting"]
users = db.users
candidates = db.candidates
payments = db.payments
settings = db.settings

# Defaults
if not settings.find_one({"_id": "config"}):
    settings.insert_one({
        "_id": "config",
        "multi_vote": False,
        "vote_open": True,
        "rate_inr": 1,
        "rate_star": 1
    })

# ============ BOT ============
bot = Client("votingbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ============ HELPERS ============
def is_admin(uid): return uid in ADMINS

def cfg(): return settings.find_one({"_id": "config"})

# ============ START ============
@bot.on_message(filters.command("start"))
async def start(_, m):
    await m.reply(
        "🗳️ **Advanced Voting Bot**\n\n"
        "/vote\n/votes\n/myvote\n/leaderboard\n/help"
    )

# ============ ADD CANDIDATE ============
@bot.on_message(filters.command("addcandidate") & filters.user(ADMINS))
async def add_c(_, m):
    try:
        name = m.text.split(None,1)[1]
        candidates.insert_one({"name": name, "votes": 0})
        await m.reply(f"✅ Added {name}")
    except:
        await m.reply("Use: /addcandidate Name")

# ============ VOTE ============
@bot.on_message(filters.command("vote"))
async def vote(_, m):
    if not cfg()["vote_open"]:
        return await m.reply("❌ Voting closed")

    if users.find_one({"uid": m.from_user.id}) and not cfg()["multi_vote"]:
        return await m.reply("❌ Already voted")

    btn = [[InlineKeyboardButton(c["name"], callback_data=f"v_{c['name']}")]
           for c in candidates.find()]
    await m.reply("Select candidate:", reply_markup=InlineKeyboardMarkup(btn))

@bot.on_callback_query(filters.regex("^v_"))
async def do_vote(_, q):
    uid = q.from_user.id
    name = q.data[2:]

    if users.find_one({"uid": uid}) and not cfg()["multi_vote"]:
        return await q.answer("Already voted", True)

    candidates.update_one({"name": name}, {"$inc": {"votes": 1}})
    users.insert_one({"uid": uid, "vote": name})
    await q.message.edit_text(f"✅ Vote cast for **{name}**")

# ============ LIVE VOTES ============
@bot.on_message(filters.command("votes"))
async def live(_, m):
    txt = "📊 Live Votes\n\n"
    for c in candidates.find():
        txt += f"{c['name']} : {c['votes']}\n"
    await m.reply(txt)

# ============ MY VOTE ============
@bot.on_message(filters.command("myvote"))
async def myvote(_, m):
    v = users.find_one({"uid": m.from_user.id})
    await m.reply("❌ No vote" if not v else f"🗳️ You voted: {v['vote']}")

# ============ LEADERBOARD ============
@bot.on_message(filters.command("leaderboard"))
async def lb(_, m):
    txt = "🏆 Leaderboard\n\n"
    for c in candidates.find().sort("votes",-1):
        txt += f"{c['name']} : {c['votes']}\n"
    await m.reply(txt)

# ============ ADMIN ============
@bot.on_message(filters.command("setrate") & filters.user(ADMINS))
async def rate(_, m):
    r = m.text.split()
    settings.update_one({"_id":"config"}, {"$set":{
        "rate_inr": int(r[1]),
        "rate_star": int(r[2])
    }})
    await m.reply("💰 Rates updated")

@bot.on_message(filters.command("endvote") & filters.user(ADMINS))
async def end(_, m):
    settings.update_one({"_id":"config"}, {"$set":{"vote_open": False}})
    await m.reply("🔒 Voting closed")

@bot.on_message(filters.command("resetvotes") & filters.user(ADMINS))
async def reset(_, m):
    users.delete_many({})
    candidates.update_many({}, {"$set":{"votes":0}})
    await m.reply("🔄 Reset done")

@bot.on_message(filters.command("winner") & filters.user(ADMINS))
async def win(_, m):
    c = candidates.find().sort("votes",-1).limit(1)
    for x in c:
        await m.reply(f"🏆 Winner: {x['name']} ({x['votes']})")

@bot.on_message(filters.command("export") & filters.user(ADMINS))
async def export(_, m):
    df = pd.DataFrame(list(candidates.find({},{"_id":0})))
    df.to_csv("result.csv", index=False)
    await m.reply_document("result.csv")

# ============ RUN ============
bot.run()
