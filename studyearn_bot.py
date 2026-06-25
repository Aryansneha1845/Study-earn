import os
import time
import random
import string
import asyncio
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, CallbackQueryHandler, PreCheckoutQueryHandler
)
import sqlite3
from collections import defaultdict

# ================= CONFIG =================
TOKEN            = os.environ.get("BOT_TOKEN")
ADMIN_ID         = int(os.environ.get("ADMIN_ID", "0"))
BOT_USERNAME     = os.environ.get("BOT_USERNAME", "")
SERVER_URL       = os.environ.get("SERVER_URL", "")
PUBLIC_CHANNEL   = int(os.environ.get("PUBLIC_CHANNEL", "0"))
AD_LINK          = os.environ.get("AD_LINK", "")
VIDEOS_PER_TOKEN = 20
DELETE_AFTER     = 10 * 60
FREE_VIDEOS      = 20
AD_WAIT_SECONDS  = 30

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 10
user_request_times = defaultdict(list)

# ================= CATEGORIES =================
CATEGORIES = {
    "physics": {
        "name": "⚡ Competitive Programming (CP)",
        "channel": int(os.environ.get("CHANNEL_PHYSICS", "0")),
        "emoji": "⚡",
        "msg_min": 1,
        "msg_max": 1272
    },
    "chemistry": {
        "name": "🧪 Chemistry",
        "channel": int(os.environ.get("CHANNEL_CHEMISTRY", "0")),
        "emoji": "🧪",
        "msg_min": 1,
        "msg_max": 136
    },
    "maths": {
        "name": "📐 Maths",
        "channel": int(os.environ.get("CHANNEL_MATHS", "0")),
        "emoji": "📐",
        "msg_min": 1,
        "msg_max": 178
    },
    "mix": {
        "name": "🎲 Mix Studies",
        "channel": int(os.environ.get("CHANNEL_MIX", "0")),
        "emoji": "🎲",
        "msg_min": 4,
        "msg_max": 5563
    },
    "zoology": {
        "name": "🦎 Zoology",
        "channel": int(os.environ.get("CHANNEL_ZOOLOGY", "0")),
        "emoji": "🦎",
        "msg_min": 4,
        "msg_max": 2039
    },
    "astrology": {
        "name": "🔮 Astrology",
        "channel": int(os.environ.get("CHANNEL_ASTROLOGY", "0")),
        "emoji": "🔮",
        "msg_min": 5,
        "msg_max": 638
    },
    "snap": {
        "name": "📸 Snap Videos",
        "channel": int(os.environ.get("CHANNEL_SNAP", "0")),
        "emoji": "📸",
        "msg_min": 1,
        "msg_max": 207
    },
    "russian": {
        "name": "🎓 Russian Professor",
        "channel": int(os.environ.get("CHANNEL_RUSSIAN", "0")),
        "emoji": "🎓",
        "msg_min": 1,
        "msg_max": 772
    }
}

# ================= DB =================
conn = sqlite3.connect("studyearn.db", check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id         INTEGER PRIMARY KEY,
    username        TEXT,
    joined          INTEGER,
    tokens          INTEGER DEFAULT 0,
    last_earn       INTEGER DEFAULT 0,
    daily_earn      INTEGER DEFAULT 0,
    last_daily      INTEGER DEFAULT 0,
    last_spin       INTEGER DEFAULT 0,
    streak          INTEGER DEFAULT 0,
    last_streak     INTEGER DEFAULT 0,
    videos_left     INTEGER DEFAULT 0,
    ref_by          INTEGER,
    agreed_tnc      INTEGER DEFAULT 0,
    free_used       INTEGER DEFAULT 0,
    banned          INTEGER DEFAULT 0,
    last_request    INTEGER DEFAULT 0,
    request_count   INTEGER DEFAULT 0,
    warnings        INTEGER DEFAULT 0,
    ref_claimed     INTEGER DEFAULT 0,
    total_videos    INTEGER DEFAULT 0,
    challenge_count INTEGER DEFAULT 0
)
""")

# Migrate columns
for col_def in [
    "ALTER TABLE users ADD COLUMN ref_claimed INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN total_videos INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN challenge_count INTEGER DEFAULT 0",
]:
    try:
        c.execute(col_def)
        conn.commit()
    except Exception:
        pass

c.execute("""
CREATE TABLE IF NOT EXISTS withdrawals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    amount      INTEGER,
    address     TEXT,
    status      TEXT DEFAULT 'pending'
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS sent_videos (
    user_id     INTEGER,
    category    TEXT,
    message_id  INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS ad_clicks (
    user_id     INTEGER PRIMARY KEY,
    clicked_at  INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS verify_codes (
    user_id     INTEGER PRIMARY KEY,
    correct     TEXT,
    attempts    INTEGER DEFAULT 0,
    created_at  INTEGER
)
""")

conn.commit()

# ================= UI =================
main_keyboard = [
    ["📚 Watch Videos", "💰 Balance"],
    ["🎁 Spin", "🔥 Streak"],
    ["👥 Refer", "💸 Withdraw"],
    ["🏆 Leaderboard", "📅 Daily Bonus"],
    ["🏅 Group Challenge"]
]
reply_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

def category_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ CP", callback_data="cat_physics"),
            InlineKeyboardButton("🧪 Chemistry", callback_data="cat_chemistry"),
        ],
        [
            InlineKeyboardButton("📐 Maths", callback_data="cat_maths"),
            InlineKeyboardButton("🎲 Mix", callback_data="cat_mix"),
        ],
        [
            InlineKeyboardButton("🦎 Zoology", callback_data="cat_zoology"),
            InlineKeyboardButton("🔮 Astrology", callback_data="cat_astrology"),
        ],
        [
            InlineKeyboardButton("📸 Snap Videos", callback_data="cat_snap"),
            InlineKeyboardButton("🎓 Russian Professor", callback_data="cat_russian"),
        ]
    ])

# ================= HELPERS =================
def get_user(uid):
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return c.fetchone()

def ensure_user(uid, username=None, ref=None):
    c.execute("INSERT OR IGNORE INTO users (user_id, username, joined, ref_by) VALUES (?,?,?,?)",
              (uid, username, int(time.time()), ref))
    conn.commit()

def has_agreed(uid):
    user = get_user(uid)
    return user and user[12] == 1

def is_new_user(uid):
    user = get_user(uid)
    return user and user[13] == 0

def is_banned(uid):
    user = get_user(uid)
    return user and user[14] == 1

def record_ad_click(uid):
    c.execute("INSERT OR REPLACE INTO ad_clicks (user_id, clicked_at) VALUES (?,?)",
              (uid, int(time.time())))
    conn.commit()

def get_ad_click_time(uid):
    c.execute("SELECT clicked_at FROM ad_clicks WHERE user_id=?", (uid,))
    row = c.fetchone()
    return row[0] if row else 0

# ================= RATE LIMITER =================
def is_rate_limited(uid):
    now   = time.time()
    times = user_request_times[uid]
    # Keep only last 60 seconds
    user_request_times[uid] = [t for t in times if now - t < 60]
    if len(user_request_times[uid]) >= MAX_REQUESTS_PER_MINUTE:
        return True
    user_request_times[uid].append(now)
    return False

# ================= EMOJI CAPTCHA SYSTEM =================
EMOJI_SETS = [
    {"target": "🐱", "pool": ["🐱", "🐶", "🐸", "🦊", "🐻", "🐼", "🐨", "🐯"]},
    {"target": "🍕", "pool": ["🍕", "🍔", "🌮", "🍣", "🍜", "🍩", "🍦", "🍇"]},
    {"target": "⚽", "pool": ["⚽", "🏀", "🏈", "🎾", "🏐", "🎱", "🏓", "🏸"]},
    {"target": "🚀", "pool": ["🚀", "✈️", "🚁", "🛸", "🛩️", "🚂", "🚀", "⛵"]},
    {"target": "🌟", "pool": ["🌟", "☀️", "🌙", "⭐", "🌈", "❄️", "🔥", "💫"]},
    {"target": "🎮", "pool": ["🎮", "🎲", "🎯", "🎸", "🎺", "🎻", "🥁", "🎹"]},
]

emoji_challenges = {}  # uid -> {"target": emoji, "created": timestamp}

def send_emoji_captcha_sync(uid):
    """Returns markup and message text for emoji captcha"""
    challenge = random.choice(EMOJI_SETS)
    target    = challenge["target"]
    pool      = challenge["pool"].copy()
    random.shuffle(pool)
    # Make sure target is in pool
    if target not in pool:
        pool[0] = target
        random.shuffle(pool)

    emoji_challenges[uid] = {"target": target, "created": int(time.time())}

    buttons = []
    row = []
    for i, emoji in enumerate(pool):
        row.append(InlineKeyboardButton(emoji, callback_data=f"emoji_{emoji}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    text = (
        f"🔐 <b>Security Check!</b>\n\n"
        f"Neeche emojis mein se <b>{target}</b> dhundho aur tap karo!\n\n"
        f"👇 Sahi emoji select karo:"
    )
    return text, InlineKeyboardMarkup(buttons)

async def send_emoji_challenge(bot, uid):
    text, markup = send_emoji_captcha_sync(uid)
    await bot.send_message(uid, text, reply_markup=markup, parse_mode="HTML")


# ================= TELEGRAM STARS PAYMENT =================
STARS_PRICE      = 50
VIDEOS_PER_STARS = 50

async def send_stars_payment(bot, uid):
    await bot.send_invoice(
        chat_id=uid,
        title="🎬 50 More Videos",
        description=f"Unlock {VIDEOS_PER_STARS} more study videos across all categories!",
        payload=f"videos_{uid}",
        currency="XTR",
        prices=[LabeledPrice("50 Videos Pack", STARS_PRICE)],
        provider_token="",
    )

async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    c.execute("UPDATE users SET videos_left=videos_left+? WHERE user_id=?", (VIDEOS_PER_STARS, uid))
    conn.commit()
    await update.message.reply_text(
        f"🎉 <b>Payment successful! ⭐</b>\n\n"
        f"{VIDEOS_PER_STARS} videos unlock ho gayi!\n"
        f"Tap 📚 Watch Videos to enjoy! 🚀",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


# ================= GROUP CHALLENGE =================
GROUP_CHALLENGE_REFS = 5      # 5 dost invite karo
GROUP_CHALLENGE_REWARD = 100  # 100 bonus videos

async def group_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    uid  = update.effective_user.id
    user = get_user(uid)

    # Count referrals
    c.execute("SELECT COUNT(*) FROM users WHERE ref_by=?", (uid,))
    ref_count = c.fetchone()[0]
    remaining = max(0, GROUP_CHALLENGE_REFS - ref_count)

    link = f"https://t.me/{BOT_USERNAME}?start={uid}"

    if ref_count >= GROUP_CHALLENGE_REFS:
        # Check if already claimed
        c.execute("SELECT challenge_count FROM users WHERE user_id=?", (uid,))
        claimed = c.fetchone()[0]
        if claimed == 0:
            c.execute("UPDATE users SET videos_left=videos_left+?, challenge_count=1 WHERE user_id=?",
                      (GROUP_CHALLENGE_REWARD, uid))
            conn.commit()
            await update.message.reply_text(
                f"🎉 <b>Challenge Complete!</b>\n\n"
                f"✅ {GROUP_CHALLENGE_REFS} dosto ne join kiya!\n"
                f"🎬 <b>+{GROUP_CHALLENGE_REWARD} videos</b> unlock ho gayi!\n\n"
                f"Tap 📚 Watch Videos to enjoy! 🚀",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                f"✅ <b>Challenge already complete!</b>\n\n"
                f"Aapne {GROUP_CHALLENGE_REFS} dosto ko invite kiya tha aur {GROUP_CHALLENGE_REWARD} videos mile the!\n\n"
                f"Aur features jaldi aa rahe hain! 🚀",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
    else:
        await update.message.reply_text(
            f"🏆 <b>Group Challenge!</b>\n\n"
            f"5 dosto ko invite karo → <b>100 FREE videos</b> pao!\n\n"
            f"📊 Progress: <b>{ref_count}/{GROUP_CHALLENGE_REFS}</b> dost joined\n"
            f"{'🟢' * ref_count}{'⚪' * remaining}\n\n"
            f"🔗 <b>Apna invite link:</b>\n"
            f"<code>{link}</code>\n\n"
            f"Share karo aur 100 videos kamao! 🎬",
            parse_mode="HTML",
            reply_markup=reply_markup
        )

# ================= AUTO DELETE =================
async def delete_after_delay(bot, chat_id, message_ids, warning_message_id, delay=DELETE_AFTER):
    await asyncio.sleep(delay - 60)
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=warning_message_id,
            text="⚠️ Videos 1 minute mein delete ho jayengi!\nAbhi dekh lo! 👆"
        )
    except:
        pass

    await asyncio.sleep(60)

    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
            await asyncio.sleep(0.3)
        except:
            pass
    try:
        await bot.delete_message(chat_id=chat_id, message_id=warning_message_id)
    except:
        pass
    try:
        await bot.send_message(
            chat_id=chat_id,
            text="🗑️ Videos delete ho gayi!\n\nAur videos ke liye 📚 Watch Videos dabao.",
            reply_markup=reply_markup
        )
    except:
        pass

# ================= AUTO NOTIFY =================
async def notify_public_channel(bot, caption="", category="mix"):
    try:
        cat      = CATEGORIES.get(category, CATEGORIES["mix"])
        bot_link = f"https://t.me/{BOT_USERNAME}"
        topic    = caption.strip()[:50] if caption else "Naya Study Video"

        await bot.send_message(
            chat_id=PUBLIC_CHANNEL,
            text=(
                f"🔥 NEW VIDEO ADDED!\n\n"
                f"{cat['emoji']} Category: {cat['name']}\n"
                f"📚 {topic}\n\n"
                f"⚠️ Videos sirf 10 minute available hongi!\n"
                f"🎁 Watch karo aur tokens kamao!\n\n"
                f"👇 FREE mein dekho!\n➡️ {bot_link}"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📚 Watch Now — FREE!", url=bot_link)]
            ])
        )
    except Exception as e:
        print(f"Notify error: {e}")

# ================= SEND 20 VIDEOS =================
async def send_20_videos(bot, uid, category, is_free=False):
    cat        = CATEGORIES.get(category, CATEGORIES["mix"])
    channel_id = cat["channel"]
    msg_min    = cat["msg_min"]
    msg_max    = cat["msg_max"]

    c.execute("SELECT message_id FROM sent_videos WHERE user_id=? AND category=?", (uid, category))
    seen = set(row[0] for row in c.fetchall())

    all_ids   = list(range(msg_min, msg_max + 1))
    available = [mid for mid in all_ids if mid not in seen]

    if not available:
        c.execute("DELETE FROM sent_videos WHERE user_id=? AND category=?", (uid, category))
        conn.commit()
        available = all_ids
        await bot.send_message(uid, "🔄 Sab videos dekh li! Fresh start ho raha hai!")

    random.shuffle(available)

    mode = random.choice(["rapid", "slow"])
    await bot.send_message(
        uid,
        f"{cat['emoji']} {cat['name']} videos aa rahi hain...\n"
        f"{'⚡ Rapid Fire Mode!' if mode == 'rapid' else '📚 Loading...'}"
    )

    sent_ids   = []
    sent_count = 0

    for msg_id in available:
        if sent_count >= 20:
            break
        try:
            fwd = await bot.forward_message(
                chat_id=uid,
                from_chat_id=channel_id,
                message_id=msg_id
            )
            sent_ids.append(fwd.message_id)
            c.execute("INSERT INTO sent_videos (user_id, category, message_id) VALUES (?,?,?)",
                      (uid, category, msg_id))
            conn.commit()
            sent_count += 1

            if mode == "slow":
                await asyncio.sleep(random.uniform(0.8, 1.5))
            else:
                await asyncio.sleep(random.uniform(0.1, 0.3))
        except Exception:
            continue

    if sent_count == 0:
        await bot.send_message(
            uid,
            f"⚠️ {cat['name']} mein videos nahi mili. Doosri category try karo! 👇",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Doosri Category", callback_data="choose_category")]
            ])
        )
        return

    tokens_earned = sent_count * 3
    if is_free:
        c.execute("UPDATE users SET free_used=1, tokens=tokens+?, total_videos=total_videos+? WHERE user_id=?", (tokens_earned, sent_count, uid))
    else:
        c.execute("UPDATE users SET videos_left=0, tokens=tokens+?, total_videos=total_videos+? WHERE user_id=?", (tokens_earned, sent_count, uid))
    conn.commit()

    # Check 50-video milestone — Stars payment prompt
    c.execute("SELECT total_videos FROM users WHERE user_id=?", (uid,))
    total_vids = c.fetchone()[0]
    prev_total  = total_vids - sent_count
    crossed_50  = (prev_total // 50) < (total_vids // 50)
    if crossed_50 and total_vids >= 50:
        await asyncio.sleep(1)
        await bot.send_message(
            uid,
            f"🎬 <b>Aapne {(total_vids // 50) * 50} videos dekh li!</b>\n\n"
            f"Aur videos ke liye sirf <b>50 ⭐ Stars</b> pay karo!\n"
            f"50 Stars ≈ ₹10 — aur 50 videos turant unlock!\n\n"
            f"👇 Neeche pay karo:",
            parse_mode="HTML"
        )
        await send_stars_payment(bot, uid)
        return

    mins = DELETE_AFTER // 60
    warning_msg = await bot.send_message(
        uid,
        f"✅ {sent_count} videos mil gayi!\n"
        f"💰 +{tokens_earned} tokens earned!\n"
        f"⏱️ Ye videos {mins} minute mein delete ho jayengi!\n\n"
        f"Aur videos ke liye 📚 Watch Videos dabao!",
        reply_markup=reply_markup
    )

    asyncio.ensure_future(
        delete_after_delay(bot, uid, sent_ids, warning_msg.message_id)
    )

    # After sending — show emoji security challenge for next batch
    await asyncio.sleep(2)
    await send_emoji_challenge(bot, uid)

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    uid      = update.effective_user.id
    username = update.effective_user.username

    if is_banned(uid):
        return await update.message.reply_text("🚫 You are banned.")

    ref = None
    if context.args:
        try:
            ref = int(context.args[0])
        except ValueError:
            pass

    ensure_user(uid, username, ref)

    if ref and ref != uid:
        user = get_user(uid)
        # Use ref_claimed flag (index 18) to prevent double referral rewards
        if user and user[18] == 0 and user[11] == ref:
            c.execute("UPDATE users SET tokens=tokens+25 WHERE user_id=?", (ref,))
            c.execute("UPDATE users SET ref_claimed=1 WHERE user_id=?", (uid,))
            conn.commit()

    c.execute("UPDATE users SET agreed_tnc=1 WHERE user_id=?", (uid,))
    conn.commit()

    user = get_user(uid)
    await update.message.reply_text(
        f"👋 Welcome to Study & Earn Bot!\n\n"
        f"💰 Balance: {user[3]} tokens\n\n"
        f"📚 Category chuno aur videos dekho!\n"
        f"🎁 Naye user ko 20 FREE videos milti hain!\n\n"
        f"Tap 📚 Watch Videos to begin! 🚀",
        reply_markup=reply_markup
    )

# ================= WATCH VIDEOS =================
async def watch_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    uid = update.effective_user.id

    if is_banned(uid):
        return await update.message.reply_text("🚫 You are banned.")

    if is_rate_limited(uid):
        return await update.message.reply_text("⚠️ Thoda slow karo! Ek minute mein zyada requests mat bhejo.")

    user = get_user(uid)
    if not user:
        return await update.message.reply_text("Please /start first.")

    # Check if pending emoji challenge
    chall = emoji_challenges.get(uid)
    if chall and int(time.time()) - chall["created"] < 120:
        return await update.message.reply_text(
            "🔐 Pehle emoji security check complete karo! Upar wala emoji tap karo 👆"
        )

    if is_new_user(uid):
        await update.message.reply_text(
            "🎁 20 FREE videos — Kaunsi category chahiye? 👇",
            reply_markup=category_keyboard()
        )
        return

    if user[10] > 0:
        await update.message.reply_text(
            "🎬 20 videos — Kaunsi category chahiye? 👇",
            reply_markup=category_keyboard()
        )
        return

    record_ad_click(uid)

    # Adsterra Mini App Ad System
    await update.message.reply_text(
        f"📺 <b>Ek short ad dekho, phir videos pao!</b>\n\n"
        f"👇 Neeche button dabao — 5 second ka ad dekho aur category chuno:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📺 Watch Ad & Get Videos",
                web_app={"url": f"https://{SERVER_URL}/welcome"}
            )],
            [InlineKeyboardButton("✅ Ad Dekh Li! Videos Do", callback_data="claim_token_then_cat")]
        ]),
        parse_mode="HTML"
    )

# ================= CALLBACK HANDLER =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid   = query.from_user.id
    data  = query.data

    if is_banned(uid):
        await query.answer("🚫 You are banned.", show_alert=True)
        return

    await query.answer()

    if data == "choose_category":
        await query.edit_message_text(
            "🎬 Kaunsi category chahiye? 👇",
            reply_markup=category_keyboard()
        )

    elif data == "claim_token_then_cat":
        clicked_at = get_ad_click_time(uid)
        waited     = int(time.time()) - clicked_at

        if waited < AD_WAIT_SECONDS:
            remaining = AD_WAIT_SECONDS - waited
            await query.answer(
                f"⏳ {remaining} second aur ruko! Ad poori dekho!",
                show_alert=True
            )
            return

        c.execute("UPDATE users SET videos_left=? WHERE user_id=?", (VIDEOS_PER_TOKEN, uid))
        conn.commit()
        await query.edit_message_text(
            "🎉 Token mil gaya! Kaunsi category chahiye? 👇",
            reply_markup=category_keyboard()
        )

    elif data.startswith("emoji_"):
        chosen  = data[6:]
        chall   = emoji_challenges.get(uid)

        if not chall:
            await query.answer("⏰ Challenge expire ho gaya! Dubara try karo.", show_alert=True)
            return

        if int(time.time()) - chall["created"] > 120:
            emoji_challenges.pop(uid, None)
            await query.answer("⏰ Time out! Dubara try karo.", show_alert=True)
            return

        if chosen == chall["target"]:
            emoji_challenges.pop(uid, None)
            await query.edit_message_text(
                "✅ <b>Sahi! Security check passed! 🎉</b>\n\nAb videos dekh sakte ho! 👇",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📚 Watch Videos", callback_data="choose_category")]
                ]),
                parse_mode="HTML"
            )
        else:
            await query.answer(f"❌ Galat! {chall['target']} dhundo!", show_alert=True)

    elif data.startswith("cat_"):
        category = data[4:]
        # Snapshot free status BEFORE editing message to avoid race condition
        user    = get_user(uid)
        is_free = user and user[13] == 0  # free_used == 0
        cat     = CATEGORIES.get(category, CATEGORIES["mix"])

        await query.edit_message_text(
            f"{cat['emoji']} {cat['name']} select kiya!\nVideos aa rahi hain... 🎬"
        )
        await send_20_videos(context.bot, uid, category, is_free=is_free)

    # ===== ADMIN DASHBOARD CALLBACKS =====
    elif uid == ADMIN_ID:
        if data in ("adm_home", "adm_refresh"):
            await send_dashboard(query, context, edit=True)

        elif data == "adm_users" or data.startswith("adm_users_p"):
            page = 0
            if data.startswith("adm_users_p"):
                try:
                    page = int(data.split("adm_users_p")[1])
                except:
                    page = 0
            await adm_show_users(query, page)

        elif data == "adm_withdrawals":
            await adm_show_withdrawals(query, "pending")

        elif data == "adm_w_approved":
            await adm_show_withdrawals(query, "approved")

        elif data.startswith("adm_approve_"):
            wid = int(data.split("adm_approve_")[1])
            c.execute("SELECT user_id, amount FROM withdrawals WHERE id=?", (wid,))
            row = c.fetchone()
            if row:
                c.execute("UPDATE withdrawals SET status='approved' WHERE id=?", (wid,))
                conn.commit()
                try:
                    await context.bot.send_message(
                        row[0],
                        f"✅ Aapka withdrawal approve ho gaya!\n💸 Amount: {row[1]} tokens\n⏳ 24-48 hrs mein UPI pe aayega!"
                    )
                except:
                    pass
            await adm_show_withdrawals(query, "pending")

        elif data.startswith("adm_reject_"):
            wid = int(data.split("adm_reject_")[1])
            c.execute("SELECT user_id, amount FROM withdrawals WHERE id=?", (wid,))
            row = c.fetchone()
            if row:
                c.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
                c.execute("UPDATE users SET tokens=tokens+? WHERE user_id=?", (row[1], row[0]))
                conn.commit()
                try:
                    await context.bot.send_message(
                        row[0],
                        f"❌ Aapka withdrawal reject ho gaya.\n💰 {row[1]} tokens wapas aa gaye!"
                    )
                except:
                    pass
            await adm_show_withdrawals(query, "pending")

        elif data.startswith("adm_unban_"):
            target = int(data.split("adm_unban_")[1])
            c.execute("UPDATE users SET banned=0, warnings=0 WHERE user_id=?", (target,))
            conn.commit()
            try:
                await context.bot.send_message(target, "✅ Aapka ban hat gaya! Bot use kar sakte ho.")
            except:
                pass
            await adm_show_banned(query)

        elif data == "adm_categories":
            await adm_show_categories(query)

        elif data == "adm_leaderboard":
            await adm_show_leaderboard(query)

        elif data == "adm_banned":
            await adm_show_banned(query)

        elif data == "adm_broadcast":
            await query.edit_message_text(
                "📢 *Broadcast*\n\nSend karo:\n`/broadcast Aapka message yahan`",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Dashboard", callback_data="adm_home")]
                ]),
                parse_mode="Markdown"
            )

        elif data == "adm_notify":
            cats = "\n".join([f"`/notify {k} Topic`" for k in CATEGORIES.keys()])
            await query.edit_message_text(
                f"🔔 *Notify Channel*\n\nCommands:\n{cats}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Dashboard", callback_data="adm_home")]
                ]),
                parse_mode="Markdown"
            )

        elif data.startswith("adm_ban_"):
            target = int(data.split("adm_ban_")[1])
            c.execute("UPDATE users SET banned=1 WHERE user_id=?", (target,))
            conn.commit()
            try:
                await context.bot.send_message(target, "🚫 Aapko ban kar diya gaya hai.")
            except:
                pass
            await query.answer("✅ User banned!", show_alert=True)
            await send_dashboard(query, context, edit=True)

# ================= BALANCE =================
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    uid  = update.effective_user.id
    user = get_user(uid)
    if not user:
        return await update.message.reply_text("Use /start first.")
    await update.message.reply_text(
        f"💰 Balance: {user[3]} tokens\n"
        f"🎬 Videos left in token: {user[10]}"
    )

# ================= DAILY BONUS =================
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    uid        = update.effective_user.id
    user       = get_user(uid)
    now        = int(time.time())
    last_daily = user[6] or 0

    if now - last_daily < 86400:
        remaining = 86400 - (now - last_daily)
        hours = remaining // 3600
        mins  = (remaining % 3600) // 60
        return await update.message.reply_text(f"⏳ Daily bonus resets in {hours}h {mins}m.")

    last_streak_ts = user[9] or 0
    new_streak = (user[8] + 1) if (last_streak_ts and now - last_streak_ts < 172800) else 1

    c.execute("""
        UPDATE users SET tokens=tokens+10, last_daily=?, streak=?, last_streak=?
        WHERE user_id=?
    """, (now, new_streak, now, uid))
    conn.commit()

    await update.message.reply_text(
        f"🎁 Daily bonus!\n+10 tokens\n🔥 Streak: {new_streak} day{'s' if new_streak > 1 else ''}"
    )

# ================= STREAK =================
async def streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    uid            = update.effective_user.id
    user           = get_user(uid)
    now            = int(time.time())
    last_streak_ts = user[9] or 0
    current_streak = user[8]

    status = "❌ Streak broken!" if (last_streak_ts and now - last_streak_ts >= 172800) else "✅ Active!"
    await update.message.reply_text(
        f"🔥 Streak: {current_streak} day{'s' if current_streak != 1 else ''}\n{status}"
    )

# ================= SPIN =================
async def spin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    uid  = update.effective_user.id
    user = get_user(uid)
    now  = int(time.time())

    if user[7] and now - user[7] < 43200:
        remaining = 43200 - (now - user[7])
        hours = remaining // 3600
        mins  = (remaining % 3600) // 60
        return await update.message.reply_text(f"🎡 Next spin in {hours}h {mins}m.")

    reward = random.choice([0, 2, 3, 5, 10, 20])
    c.execute("UPDATE users SET tokens=tokens+?, last_spin=? WHERE user_id=?", (reward, now, uid))
    conn.commit()

    msg = "🎡 No luck! Try again in 12 hours." if reward == 0 else f"🎡 You won {reward} tokens!"
    await update.message.reply_text(msg)

# ================= REFER =================
async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    uid  = update.effective_user.id
    link = f"https://t.me/{BOT_USERNAME}?start={uid}"
    await update.message.reply_text(
        f"👥 Invite friends, earn 25 tokens per join!\n\n🔗 Your link:\n{link}"
    )

# ================= LEADERBOARD =================
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    c.execute("SELECT user_id, tokens FROM users ORDER BY tokens DESC LIMIT 10")
    rows   = c.fetchall()
    msg    = "🏆 Top 10 Users:\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, tokens) in enumerate(rows, 1):
        icon   = medals[i-1] if i <= 3 else f"{i}."
        masked = f"...{str(uid)[-4:]}"
        msg   += f"{icon} User {masked} — {tokens} tokens\n"
    await update.message.reply_text(msg)

# ================= WITHDRAW =================
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    uid  = update.effective_user.id
    user = get_user(uid)

    if user[3] < 500:
        return await update.message.reply_text(
            f"❌ Minimum 500 tokens needed.\nYour balance: {user[3]} tokens."
        )

    await update.message.reply_text(
        f"💸 Withdrawal: {user[3]} tokens\n\nReply with your UPI ID.\nType /cancel to abort."
    )
    context.user_data["awaiting_upi"] = True

# ================= ADMIN DASHBOARD =================
def admin_check(update):
    return update.effective_user and update.effective_user.id == ADMIN_ID

def get_dashboard_stats():
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE banned=0 AND agreed_tnc=1")
    active_users = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(tokens),0) FROM users")
    total_tokens = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'")
    pending_withdrawals = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='pending'")
    pending_tokens = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE banned=1")
    banned_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE joined > ?", (int(time.time()) - 86400,))
    new_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='approved'")
    approved_withdrawals = c.fetchone()[0]
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_tokens": total_tokens,
        "pending_withdrawals": pending_withdrawals,
        "pending_tokens": pending_tokens,
        "banned_count": banned_count,
        "new_today": new_today,
        "approved_withdrawals": approved_withdrawals,
    }

def dashboard_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 Users",         callback_data="adm_users"),
            InlineKeyboardButton("💸 Withdrawals",   callback_data="adm_withdrawals"),
        ],
        [
            InlineKeyboardButton("📊 Categories",    callback_data="adm_categories"),
            InlineKeyboardButton("🏆 Leaderboard",   callback_data="adm_leaderboard"),
        ],
        [
            InlineKeyboardButton("🚫 Banned Users",  callback_data="adm_banned"),
            InlineKeyboardButton("📢 Broadcast",     callback_data="adm_broadcast"),
        ],
        [
            InlineKeyboardButton("🔔 Notify Channel",callback_data="adm_notify"),
            InlineKeyboardButton("🔄 Refresh",       callback_data="adm_refresh"),
        ],
    ])

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_check(update):
        return
    await send_dashboard(update.message, context)

async def send_dashboard(message, context, edit=False):
    s   = get_dashboard_stats()
    now = time.strftime("%d %b %Y, %I:%M %p", time.localtime())
    # Extra analytics
    c.execute("SELECT COALESCE(SUM(total_videos),0) FROM users")
    total_vids_watched = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE total_videos >= 50")
    paid_eligible = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE challenge_count=1")
    challenge_completed = c.fetchone()[0]

    text = (
        f"╔══════════════════════╗\n"
        f"║   🔥 ADMIN DASHBOARD  ║\n"
        f"╚══════════════════════╝\n\n"
        f"🕐 Updated: {now}\n\n"
        f"━━━━━ 👥 USERS ━━━━━\n"
        f"  Total Users    : {s['total_users']}\n"
        f"  Active Users   : {s['active_users']}\n"
        f"  New Today      : {s['new_today']} 🆕\n"
        f"  Banned         : {s['banned_count']} 🚫\n\n"
        f"━━━━━ 🎬 VIDEOS ━━━━━\n"
        f"  Total Watched  : {total_vids_watched:,}\n"
        f"  Stars Eligible : {paid_eligible} users\n"
        f"  Challenge Done : {challenge_completed} users\n\n"
        f"━━━━━ 💰 TOKENS ━━━━━\n"
        f"  Total in Bot   : {s['total_tokens']:,}\n\n"
        f"━━━━━ 💸 WITHDRAWALS ━━━━━\n"
        f"  Pending        : {s['pending_withdrawals']} ({s['pending_tokens']:,} tokens)\n"
        f"  Approved       : {s['approved_withdrawals']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Select an option below 👇"
    )
    if edit:
        await message.edit_text(text, reply_markup=dashboard_keyboard())
    else:
        await message.reply_text(text, reply_markup=dashboard_keyboard())

# ---- Admin Callback Sections ----

async def adm_show_users(query, page=0):
    limit  = 10
    offset = page * limit
    c.execute("SELECT user_id, username, tokens, banned, joined FROM users ORDER BY joined DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    pages = (total + limit - 1) // limit

    msg = f"👥 *Users — Page {page+1}/{pages}*\n\n"
    for uid, uname, tokens, banned, joined in rows:
        status  = "🚫" if banned else "✅"
        name    = f"@{uname}" if uname else f"`{uid}`"
        date    = time.strftime("%d/%m", time.localtime(joined)) if joined else "—"
        msg    += f"{status} {name}\n   💰 {tokens} tokens | 📅 {date}\n\n"

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"adm_users_p{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_users_p{page+1}"))

    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔍 Search User", callback_data="adm_search_user")])
    keyboard.append([InlineKeyboardButton("🏠 Dashboard",   callback_data="adm_home")])

    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def adm_show_withdrawals(query, filter_status="pending"):
    c.execute("SELECT id, user_id, amount, address, status FROM withdrawals WHERE status=? ORDER BY id DESC LIMIT 10", (filter_status,))
    rows = c.fetchall()

    msg = f"💸 *Withdrawals — {filter_status.upper()}*\n\n"
    buttons = []

    if not rows:
        msg += "Koi withdrawal nahi hai!"
    for wid, uid, amount, address, status in rows:
        msg += (
            f"🔹 *#{wid}*\n"
            f"   User: `{uid}`\n"
            f"   Amount: {amount} tokens\n"
            f"   UPI: `{address}`\n"
            f"   Status: {status}\n\n"
        )
        if filter_status == "pending":
            buttons.append([
                InlineKeyboardButton(f"✅ Approve #{wid}", callback_data=f"adm_approve_{wid}"),
                InlineKeyboardButton(f"❌ Reject #{wid}",  callback_data=f"adm_reject_{wid}"),
            ])

    nav = [
        InlineKeyboardButton("🟡 Pending",  callback_data="adm_withdrawals"),
        InlineKeyboardButton("✅ Approved", callback_data="adm_w_approved"),
    ]
    buttons.append(nav)
    buttons.append([InlineKeyboardButton("🏠 Dashboard", callback_data="adm_home")])

    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def adm_show_categories(query):
    msg = "📊 *Category Stats*\n\n"
    for key, cat in CATEGORIES.items():
        total_vids = cat["msg_max"] - cat["msg_min"] + 1
        msg += (
            f"{cat['emoji']} *{cat['name']}*\n"
            f"   Range: {cat['msg_min']} → {cat['msg_max']}\n"
            f"   Total Videos: {total_vids}\n\n"
        )
    await query.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Dashboard", callback_data="adm_home")]
        ]),
        parse_mode="Markdown"
    )

async def adm_show_leaderboard(query):
    c.execute("SELECT user_id, username, tokens FROM users ORDER BY tokens DESC LIMIT 10")
    rows   = c.fetchall()
    medals = ["🥇", "🥈", "🥉"]
    msg    = "🏆 *Top 10 Users*\n\n"
    for i, (uid, uname, tokens) in enumerate(rows, 1):
        icon = medals[i-1] if i <= 3 else f"{i}."
        name = f"@{uname}" if uname else f"...{str(uid)[-4:]}"
        msg += f"{icon} {name} — *{tokens:,}* tokens\n"
    await query.edit_message_text(
        msg,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Dashboard", callback_data="adm_home")]
        ]),
        parse_mode="Markdown"
    )

async def adm_show_banned(query):
    c.execute("SELECT user_id, username, warnings FROM users WHERE banned=1 ORDER BY user_id DESC LIMIT 15")
    rows = c.fetchall()
    msg  = "🚫 *Banned Users*\n\n"
    btns = []
    if not rows:
        msg += "Koi banned user nahi hai!"
    for uid, uname, warns in rows:
        name  = f"@{uname}" if uname else f"`{uid}`"
        msg  += f"🚫 {name} — ⚠️ {warns} warnings\n"
        btns.append([InlineKeyboardButton(f"🔓 Unban {uid}", callback_data=f"adm_unban_{uid}")])
    btns.append([InlineKeyboardButton("🏠 Dashboard", callback_data="adm_home")])
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown")

# ================= USERINFO =================
async def userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: /userinfo USER_ID")
    try:
        target = int(context.args[0])
        user   = get_user(target)
        if not user:
            return await update.message.reply_text("❌ User not found.")
        joined = time.strftime("%d %b %Y", time.localtime(user[2])) if user[2] else "—"
        await update.message.reply_text(
            f"👤 *User Info*\n\n"
            f"ID       : `{user[0]}`\n"
            f"Username : @{user[1] or '—'}\n"
            f"Joined   : {joined}\n"
            f"Tokens   : {user[3]:,}\n"
            f"Streak   : {user[8]} days\n"
            f"Warnings : {user[17]}\n"
            f"Banned   : {'Yes 🚫' if user[14] else 'No ✅'}\n"
            f"Free Used: {'Yes' if user[13] else 'No'}\n"
            f"Ref By   : {user[11] or '—'}",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🚫 Ban",   callback_data=f"adm_ban_{target}"),
                    InlineKeyboardButton("✅ Unban", callback_data=f"adm_unban_{target}"),
                ]
            ]),
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ Invalid user ID.")
async def setrange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) != 3:
        return await update.message.reply_text("Usage: /setrange CATEGORY MIN MAX")
    try:
        cat_key = context.args[0].lower()
        if cat_key not in CATEGORIES:
            return await update.message.reply_text(f"❌ Valid: {', '.join(CATEGORIES.keys())}")
        CATEGORIES[cat_key]["msg_min"] = int(context.args[1])
        CATEGORIES[cat_key]["msg_max"] = int(context.args[2])
        await update.message.reply_text(
            f"✅ {CATEGORIES[cat_key]['name']} updated!\n"
            f"Range: {CATEGORIES[cat_key]['msg_min']} to {CATEGORIES[cat_key]['msg_max']}"
        )
    except:
        await update.message.reply_text("❌ Invalid input.")

# ================= NOTIFY =================
async def notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: /notify physics Topic")
    cat_key = context.args[0].lower()
    topic   = " ".join(context.args[1:]) if len(context.args) > 1 else "Naya Study Video"
    await notify_public_channel(context.bot, topic, cat_key)
    await update.message.reply_text("✅ Notification sent!")

# ================= BROADCAST =================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: /broadcast Message")
    msg   = " ".join(context.args)
    c.execute("SELECT user_id FROM users WHERE agreed_tnc=1 AND banned=0")
    users = c.fetchall()
    sent  = 0
    for (user_id,) in users:
        try:
            await context.bot.send_message(user_id, msg)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await update.message.reply_text(f"✅ Sent to {sent}/{len(users)} users.")

# ================= BAN / UNBAN =================
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: /ban USER_ID")
    try:
        target = int(context.args[0])
        c.execute("UPDATE users SET banned=1 WHERE user_id=?", (target,))
        conn.commit()
        await update.message.reply_text(f"✅ User {target} banned.")
    except:
        await update.message.reply_text("❌ Invalid user ID.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: /unban USER_ID")
    try:
        target = int(context.args[0])
        c.execute("UPDATE users SET banned=0, warnings=0 WHERE user_id=?", (target,))
        conn.commit()
        await update.message.reply_text(f"✅ User {target} unbanned.")
    except:
        await update.message.reply_text("❌ Invalid user ID.")

# ================= USERS LIST =================
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.id != ADMIN_ID:
        return
    c.execute("SELECT user_id, username, tokens, banned FROM users ORDER BY joined DESC LIMIT 20")
    rows = c.fetchall()
    msg  = "👥 Recent 20 Users:\n\n"
    for uid, uname, tokens, banned in rows:
        status = "🚫" if banned else "✅"
        name   = f"@{uname}" if uname else f"ID:{uid}"
        msg   += f"{status} {name} — {tokens} tokens\n"
    await update.message.reply_text(msg)

# ================= HANDLE TEXT =================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    uid  = update.effective_user.id
    text = update.message.text

    if is_banned(uid):
        return

    if context.user_data.get("awaiting_upi"):
        context.user_data.pop("awaiting_upi")
        user = get_user(uid)
        if not user or user[3] < 500:
            return await update.message.reply_text("❌ Balance changed. Cancelled.")

        c.execute("INSERT INTO withdrawals (user_id, amount, address) VALUES (?,?,?)",
                  (uid, user[3], text.strip()))
        c.execute("UPDATE users SET tokens=0 WHERE user_id=?", (uid,))
        conn.commit()

        await update.message.reply_text(
            "✅ Withdrawal submitted!\nAdmin will process in 24-48 hours.",
            reply_markup=reply_markup
        )
        if ADMIN_ID:
            await context.bot.send_message(
                ADMIN_ID,
                f"💸 WITHDRAWAL\nUser: {uid}\nAmount: {user[3]} tokens\nUPI: {text.strip()}"
            )
        return

    if text == "📚 Watch Videos":   await watch_video(update, context)
    elif text == "💰 Balance":      await balance(update, context)
    elif text == "🎁 Spin":         await spin(update, context)
    elif text == "🔥 Streak":       await streak(update, context)
    elif text == "👥 Refer":        await refer(update, context)
    elif text == "💸 Withdraw":     await withdraw_start(update, context)
    elif text == "🏆 Leaderboard":  await leaderboard(update, context)
    elif text == "📅 Daily Bonus":  await daily(update, context)
    elif text == "🏅 Group Challenge": await group_challenge(update, context)

# ================= CANCEL =================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    context.user_data.pop("awaiting_upi", None)
    await update.message.reply_text("❌ Cancelled.", reply_markup=reply_markup)

# ================= ERROR HANDLER =================
async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    import traceback
    err = context.error
    print(f"[ERROR] {err}")
    traceback.print_exc()
    # Don't crash on network errors — just log and continue
    from telegram.error import NetworkError, TimedOut, RetryAfter
    if isinstance(err, RetryAfter):
        await asyncio.sleep(err.retry_after)
    elif isinstance(err, (NetworkError, TimedOut)):
        await asyncio.sleep(3)

# ================= RUN =================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CommandHandler("daily", daily))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(CommandHandler("withdraw", withdraw_start))
app.add_handler(CommandHandler("setrange", setrange))
app.add_handler(CommandHandler("notify", notify))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(CommandHandler("users", users))
app.add_handler(CommandHandler("userinfo", userinfo))
app.add_handler(CallbackQueryHandler(callback_handler))
app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_error_handler(error_handler)

print("🔥 STUDY & EARN BOT RUNNING")
app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query", "pre_checkout_query"])
