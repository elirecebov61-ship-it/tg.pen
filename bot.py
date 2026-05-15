import logging
import random
import os
import string
import asyncio
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN    = os.environ["BOT_TOKEN"]
ADMIN_ID = 8034872992
TZ       = ZoneInfo("Europe/Istanbul")
DB_FILE  = os.environ.get("DB_PATH", "data.db")

_db_lock  = asyncio.Lock()
_bet_lock = asyncio.Lock()
_vs_lock  = asyncio.Lock()

# ─── SQLite helpers ───────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id             TEXT NOT NULL,
            user_id             TEXT NOT NULL,
            name                TEXT DEFAULT '',
            boy                 INTEGER DEFAULT 0,
            registered          INTEGER DEFAULT 0,
            uzat_hak            INTEGER DEFAULT 2,
            uzat_reset          TEXT DEFAULT NULL,
            condom_active_until TEXT DEFAULT NULL,
            condom_cooldown_until TEXT DEFAULT NULL,
            thief_date          TEXT DEFAULT NULL,
            yolla_total_date    TEXT DEFAULT NULL,
            yolla_total         INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS thief_daily (
            chat_id    TEXT NOT NULL,
            user_id    TEXT NOT NULL,
            target_id  TEXT NOT NULL,
            count      INTEGER DEFAULT 0,
            date       TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id, target_id)
        );
        CREATE TABLE IF NOT EXISTS yolla_daily (
            chat_id    TEXT NOT NULL,
            user_id    TEXT NOT NULL,
            target_id  TEXT NOT NULL,
            count      INTEGER DEFAULT 0,
            date       TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id, target_id)
        );
        CREATE TABLE IF NOT EXISTS promos (
            kod       TEXT PRIMARY KEY,
            miktar    INTEGER NOT NULL,
            expires   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS promo_used (
            kod     TEXT NOT NULL,
            user_id TEXT NOT NULL,
            PRIMARY KEY (kod, user_id)
        );
        """)

def row_to_dict(row):
    return dict(row) if row else None

def get_user_row(conn, chat_id, user_id):
    cid, uid = str(chat_id), str(user_id)
    row = conn.execute(
        "SELECT * FROM users WHERE chat_id=? AND user_id=?", (cid, uid)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users (chat_id, user_id) VALUES (?,?)", (cid, uid)
        )
        row = conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND user_id=?", (cid, uid)
        ).fetchone()
    return dict(row)

def save_user(conn, u: dict):
    conn.execute("""
        UPDATE users SET
            name=:name, boy=:boy, registered=:registered,
            uzat_hak=:uzat_hak, uzat_reset=:uzat_reset,
            condom_active_until=:condom_active_until,
            condom_cooldown_until=:condom_cooldown_until,
            thief_date=:thief_date,
            yolla_total_date=:yolla_total_date,
            yolla_total=:yolla_total
        WHERE chat_id=:chat_id AND user_id=:user_id
    """, u)

# ─── Time helpers ─────────────────────────────────────────────────────────────

def now_tr() -> datetime:
    return datetime.now(TZ)

def today_str() -> str:
    return now_tr().strftime("%Y-%m-%d")

def get_name(user) -> str:
    name = user.first_name or ""
    if user.last_name:
        name += " " + user.last_name
    return name.strip() or user.username or str(user.id)

def is_registered(u: dict) -> bool:
    return bool(u.get("registered"))

# ─── Decorator ────────────────────────────────────────────────────────────────

def ensure_group(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            await update.message.reply_text("🚫 Bu komut sadece gruplarda çalışır!")
            return
        return await func(update, ctx)
    return wrapper

# ─── Commands ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍆 KRALLIĞA HOŞ GELDİN!\n\n/help yazarak komutları görebilirsin."
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "╔══════ 🍆 PENİSEREN BOT 🍆 ══════╗\n"
        "           🔥 KOMUT REHBERİ 🔥\n"
        "╚══════════════════════════════════╝\n\n"
        "🏛️ GENEL KOMUTLAR\n"
        "📏 /boyum — Kendi penis boyunu gösterir.\n"
        "👀 /boyu — Yanıtladığın kişinin boyunu gösterir.\n"
        "⏳ /uzat — 12 saatlik periyotta 2 hakla boyunu uzatır.\n"
        "🏆 /siralama — Grubun en büyük 25 listesini gösterir.\n\n"
        "🎰 KUMARHANE\n"
        "🪙 /yt <miktar> — Yazı tura. Ya katla ya bat!\n"
        "⚔️ /vs <miktar> — Yanıtladığın kişiye düello at.\n"
        "💸 all — Tüm boyunla girer. Örn: /yt all\n\n"
        "🛡️ ÖZEL GÜÇLER\n"
        "🛡️ /condom — 15 dakika şans buffı. 2 saatte 1 kullanılır.\n"
        "🕵️ /thief — Yanıtladığın kişiden boy çalmaya çalışır.\n"
        "💌 /yolla <miktar> — Yanıtladığın kişiye boy gönderir.\n\n"
        "🚀 ETKİLEŞİM\n"
        "🔥 /kaldir — Yanıtladığın kişiyi gaza getirir.\n"
        "📉 /indir — Yanıtladığın kişiyi gömer.\n\n"
        "🎁 PROMOSYON\n"
        "📦 /promo <kod> — Promosyon kodunu kullanır.\n\n"
        "🌟 EMEĞİ GEÇENLER 🌟\n"
        "⚡ @emektas\n"
        "V2"
    )
    await update.message.reply_text(text)

@ensure_group
async def cmd_boyum(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    async with _db_lock:
        with get_conn() as conn:
            u = get_user_row(conn, update.effective_chat.id, update.effective_user.id)
    if not is_registered(u):
        await update.message.reply_text("❗ Daha kaydın yok, önce /uzat kullan!")
        return
    await update.message.reply_text(f"🍆 Şu anki boyun: {u['boy']} cm 🔥")

@ensure_group
async def cmd_boyu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Yanıt vererek /boyu yaz.")
        return
    target = msg.reply_to_message.from_user
    async with _db_lock:
        with get_conn() as conn:
            u = get_user_row(conn, update.effective_chat.id, target.id)
    if not is_registered(u):
        await msg.reply_text("❗ Bu kullanıcı kayıtlı değil.")
        return
    await msg.reply_text(f"🍆 {get_name(target)} boyu: {u['boy']} cm 🔥")

@ensure_group
async def cmd_uzat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now  = now_tr()
    name = get_name(update.effective_user)
    async with _db_lock:
        with get_conn() as conn:
            u = get_user_row(conn, update.effective_chat.id, update.effective_user.id)
            if u["uzat_reset"]:
                reset_time = datetime.fromisoformat(u["uzat_reset"])
                if now >= reset_time:
                    u["uzat_hak"]   = 2
                    u["uzat_reset"] = None
            if u["uzat_hak"] <= 0:
                reset_time = datetime.fromisoformat(u["uzat_reset"])
                kalan      = reset_time - now
                total_sec  = int(kalan.total_seconds())
                h, rem     = divmod(total_sec, 3600)
                m, _       = divmod(rem, 60)
                await update.message.reply_text(
                    f"⏳ Bu periyot için 2 hakkını doldurdun. Kalan: {h}s {m}dk"
                )
                return
            ekle           = random.randint(2, 10)
            u["boy"]      += ekle
            u["registered"] = 1
            u["uzat_hak"] -= 1
            u["name"]      = name
            if u["uzat_reset"] is None:
                u["uzat_reset"] = (now + timedelta(hours=12)).isoformat()
            suffix = "💡 Hala 1 hakkın daha var!" if u["uzat_hak"] == 1 else "💤 Bu periyotluk bitti."
            boy = u["boy"]
            save_user(conn, u)
    await update.message.reply_text(
        f"🔥 HELAL OLSUN {name}!\n"
        f"🍆 Tam {ekle} cm uzattın!\n"
        f"📏 Yeni boyun: {boy} cm\n"
        f"{suffix}"
    )

@ensure_group
async def cmd_siralama(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    async with _db_lock:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT name, boy FROM users WHERE chat_id=? AND registered=1 ORDER BY boy DESC LIMIT 25",
                (cid,)
            ).fetchall()
    medals = ["🥇", "🥈", "🥉"]
    lines  = ["🏆 Grup Penis Boyu Sıralaması:\n"]
    for i, row in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {row['name'] or 'Bilinmeyen'} — {row['boy']} cm")
    lines.append("\nKimin borusu ne kadar öttü bakalım 😎🍆")
    await update.message.reply_text("\n".join(lines))

@ensure_group
async def cmd_yt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid  = str(update.effective_chat.id)
    uid  = str(update.effective_user.id)
    name = get_name(update.effective_user)
    if not ctx.args:
        await update.message.reply_text("❗ Kullanım: /yt <miktar> veya /yt all")
        return
    async with _db_lock:
        with get_conn() as conn:
            u = get_user_row(conn, cid, uid)
        if not is_registered(u):
            await update.message.reply_text("❗ Daha kaydın yok, önce /uzat kullan!")
            return
        arg   = ctx.args[0].lower()
        bahis = u["boy"] if arg == "all" else None
        if bahis is None:
            try:
                bahis = int(arg)
            except ValueError:
                await update.message.reply_text("❗ Kullanım: /yt <miktar> veya /yt all")
                return
        if bahis <= 0:
            await update.message.reply_text("❗ Bahis 0'dan büyük olmalı!")
            return
        if bahis > u["boy"]:
            await update.message.reply_text(f"❗ Yeterli boyun yok! Mevcut: {u['boy']} cm")
            return
    keyboard = [[
        InlineKeyboardButton("🟡 YAZI", callback_data=f"yt|yazi|{uid}|{bahis}"),
        InlineKeyboardButton("🦅 TURA", callback_data=f"yt|tura|{uid}|{bahis}")
    ]]
    sent = await update.message.reply_text(
        f"🪙 YAZI TURA BAŞLADI!\n"
        f"👤 Oyuncu: {name}\n"
        f"🍆 Bahis: {bahis} cm\n"
        f"⏳ 20 saniye içinde seç!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    key = f"{cid}_{sent.message_id}"
    ctx.bot_data.setdefault("pending_bets", {})[key] = {
        "uid": uid, "cid": cid, "bahis": bahis, "name": name, "done": False
    }
    ctx.job_queue.run_once(
        bet_timeout, 20,
        data={"cid": cid, "mid": sent.message_id, "name": name},
        chat_id=int(cid), name=f"bet_{key}"
    )

async def bet_timeout(ctx: ContextTypes.DEFAULT_TYPE):
    data           = ctx.job.data
    cid, mid, name = data["cid"], data["mid"], data["name"]
    key            = f"{cid}_{mid}"
    bets           = ctx.bot_data.get("pending_bets", {})
    if key in bets and not bets[key].get("done"):
        bets[key]["done"] = True
        try:
            await ctx.bot.edit_message_text(
                chat_id=int(cid), message_id=mid,
                text=f"⚠️ {name}, 20 saniye içinde seçim yapmadın, bahis iptal! 💤",
                reply_markup=None
            )
        except Exception:
            pass

async def yt_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    parts      = query.data.split("|")
    secim_raw  = parts[1]
    bet_uid    = parts[2]
    bahis      = int(parts[3])
    cid        = str(query.message.chat_id)
    mid        = query.message.message_id
    caller_uid = str(query.from_user.id)
    key        = f"{cid}_{mid}"
    if caller_uid != bet_uid:
        await query.answer("🚫 Bu bahis sana ait değil!", show_alert=True)
        return
    async with _bet_lock:
        bets = ctx.bot_data.get("pending_bets", {})
        if key not in bets or bets[key].get("done"):
            await query.answer("⚠️ Bu bahis süresi doldu veya zaten oynandı.", show_alert=True)
            return
        bets[key]["done"] = True
    for job in ctx.job_queue.get_jobs_by_name(f"bet_{key}"):
        job.schedule_removal()
    await query.answer()
    secim = "YAZI" if secim_raw == "yazi" else "TURA"
    await query.edit_message_text(f"🪙 Para havada...\nSeçimin: {secim}")
    await asyncio.sleep(random.randint(2, 3))
    async with _db_lock:
        with get_conn() as conn:
            u = get_user_row(conn, cid, caller_uid)
            condom_active = bool(
                u.get("condom_active_until") and
                now_tr() < datetime.fromisoformat(u["condom_active_until"])
            )
            if bahis > u["boy"]:
                await query.edit_message_text(f"❗ Oyun sırasında boyun değişti, bahis iptal! Mevcut: {u['boy']} cm")
                return
            kazandi = random.random() < (0.65 if condom_active else 0.50)
            if kazandi:
                u["boy"] += bahis
                msg = (
                    f"🎉 KAZANDIN!\n"
                    f"🎲 Seçimin: {secim}\n"
                    f"🎁 Kazanç: +{bahis} cm\n"
                    f"📏 Yeni Boy: {u['boy']} cm"
                )
            else:
                gelen    = "TURA" if secim == "YAZI" else "YAZI"
                u["boy"] = max(0, u["boy"] - bahis)
                msg = (
                    f"❌ KAYBETTİN!\n"
                    f"✅ Seçimin: {secim}\n"
                    f"🎲 Gelen: {gelen}\n"
                    f"📉 Giden: -{bahis} cm\n"
                    f"📏 Yeni Boy: {u['boy']} cm"
                )
            save_user(conn, u)
    await query.edit_message_text(msg)

@ensure_group
async def cmd_vs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip /vs <miktar> yaz.")
        return
    if not ctx.args:
        await msg.reply_text("❗ Kullanım: /vs <miktar>")
        return
    target_user = msg.reply_to_message.from_user
    if target_user.id == update.effective_user.id:
        await msg.reply_text("❗ Kendine meydan okuyamazsın!")
        return
    if target_user.is_bot:
        await msg.reply_text("❗ Bota meydan okuyamazsın!")
        return
    cid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    tid = str(target_user.id)
    async with _db_lock:
        with get_conn() as conn:
            u   = get_user_row(conn, cid, uid)
            t   = get_user_row(conn, cid, tid)
        arg   = ctx.args[0].lower()
        bahis = u["boy"] if arg == "all" else None
        if bahis is None:
            try:
                bahis = int(arg)
            except ValueError:
                await msg.reply_text("❗ Geçerli bir miktar gir.")
                return
        if bahis <= 0:
            await msg.reply_text("❗ Bahis 0'dan büyük olmalı!")
            return
        if not is_registered(u):
            await msg.reply_text("❗ Daha kaydın yok, önce /uzat kullan!")
            return
        if not is_registered(t):
            await msg.reply_text("❗ Rakip kayıtlı değil.")
            return
        if bahis > u["boy"]:
            await msg.reply_text(f"❗ Yeterli boyun yok! Mevcut: {u['boy']} cm")
            return
        if bahis > t["boy"]:
            await msg.reply_text(f"❗ Rakibin yeterli boyu yok! Mevcut: {t['boy']} cm")
            return
    challenger_name = get_name(update.effective_user)
    target_name     = get_name(target_user)
    keyboard = [[
        InlineKeyboardButton("🍌 KABUL", callback_data=f"vs|kabul|{uid}|{tid}|{bahis}"),
        InlineKeyboardButton("🙅 KAÇ",   callback_data=f"vs|kac|{uid}|{tid}|{bahis}")
    ]]
    sent = await msg.reply_text(
        f"⚔️ VS BAŞLADI!\n\n"
        f"🗡️ Meydan okuyan: {challenger_name}\n"
        f"🛡️ Rakip: {target_name}\n"
        f"🍆 Bahis: {bahis} cm\n\n"
        f"⏳ 20 saniye içinde cevap ver!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    key = f"{cid}_{sent.message_id}"
    ctx.bot_data.setdefault("pending_vs", {})[key] = {
        "uid": uid, "tid": tid, "cid": cid, "bahis": bahis,
        "challenger_name": challenger_name, "target_name": target_name,
        "done": False
    }
    ctx.job_queue.run_once(
        vs_timeout, 20,
        data={"cid": cid, "mid": sent.message_id, "target_name": target_name},
        chat_id=int(cid), name=f"vs_{key}"
    )

async def vs_timeout(ctx: ContextTypes.DEFAULT_TYPE):
    data                  = ctx.job.data
    cid, mid, target_name = data["cid"], data["mid"], data["target_name"]
    key                   = f"{cid}_{mid}"
    vs                    = ctx.bot_data.get("pending_vs", {})
    if key in vs and not vs[key].get("done"):
        vs[key]["done"] = True
        try:
            await ctx.bot.edit_message_text(
                chat_id=int(cid), message_id=mid,
                text=f"⚠️ {target_name} cevap vermedi, VS iptal. 🐔",
                reply_markup=None
            )
        except Exception:
            pass

async def vs_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query          = update.callback_query
    parts          = query.data.split("|")
    action         = parts[1]
    challenger_uid = parts[2]
    target_uid     = parts[3]
    bahis          = int(parts[4])
    cid            = str(query.message.chat_id)
    mid            = query.message.message_id
    caller_uid     = str(query.from_user.id)
    key            = f"{cid}_{mid}"
    if caller_uid != target_uid:
        await query.answer("🚫 Bu davet sana değil!", show_alert=True)
        return
    async with _vs_lock:
        vs = ctx.bot_data.get("pending_vs", {})
        if key not in vs or vs[key].get("done"):
            await query.answer("🚫 Bu davet süresi doldu!", show_alert=True)
            return
        vs_data         = vs[key]
        vs_data["done"] = True
    for job in ctx.job_queue.get_jobs_by_name(f"vs_{key}"):
        job.schedule_removal()
    await query.answer()
    challenger_name = vs_data["challenger_name"]
    target_name     = vs_data["target_name"]
    if action == "kac":
        await query.edit_message_text(f"❌ {target_name} kaçtı. VS iptal!")
        return
    await query.edit_message_text("⚔️ Düello başladı, sonuç hesaplanıyor...")
    await asyncio.sleep(random.randint(2, 3))
    async with _db_lock:
        with get_conn() as conn:
            u = get_user_row(conn, cid, challenger_uid)
            t = get_user_row(conn, cid, target_uid)
            condom_u = bool(u.get("condom_active_until") and now_tr() < datetime.fromisoformat(u["condom_active_until"]))
            condom_t = bool(t.get("condom_active_until") and now_tr() < datetime.fromisoformat(t["condom_active_until"]))
            u_chance = max(0.1, min(0.9, 0.50 + (0.075 if condom_u else 0) - (0.075 if condom_t else 0)))
            if bahis > u["boy"] or bahis > t["boy"]:
                await query.message.reply_text("❗ Düello sırasında boy değişti, VS iptal!")
                return
            if random.random() < u_chance:
                winner_name, loser_name = challenger_name, target_name
                u["boy"] += bahis
                t["boy"]  = max(0, t["boy"] - bahis)
            else:
                winner_name, loser_name = target_name, challenger_name
                t["boy"] += bahis
                u["boy"]  = max(0, u["boy"] - bahis)
            u_boy, t_boy = u["boy"], t["boy"]
            save_user(conn, u)
            save_user(conn, t)
    await query.message.reply_text(
        f"💦 VS SONUCU!\n\n"
        f"👑 Kazanan: {winner_name} (+{bahis} cm)\n"
        f"🤕 Kaybeden: {loser_name} (-{bahis} cm)\n\n"
        f"📏 {challenger_name}: {u_boy} cm\n"
        f"🤏 {target_name}: {t_boy} cm"
    )

@ensure_group
async def cmd_condom(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = now_tr()
    async with _db_lock:
        with get_conn() as conn:
            u              = get_user_row(conn, update.effective_chat.id, update.effective_user.id)
            active_until   = datetime.fromisoformat(u["condom_active_until"])   if u.get("condom_active_until")   else None
            cooldown_until = datetime.fromisoformat(u["condom_cooldown_until"]) if u.get("condom_cooldown_until") else None
            condom_active  = bool(active_until   and now < active_until)
            in_cooldown    = bool(cooldown_until and now < cooldown_until)
            if condom_active or in_cooldown:
                aktif_mi = "Evet ✅" if condom_active else "Hayır ❌"
                if in_cooldown:
                    secs     = int((cooldown_until - now).total_seconds())
                    h, rem   = divmod(secs, 3600)
                    m, _     = divmod(rem, 60)
                    kalan_cd = f"{h} saat {m} dakika"
                else:
                    kalan_cd = "Hazır!"
                au_str = active_until.strftime("%H:%M:%S")   if active_until   else "-"
                cu_str = cooldown_until.strftime("%H:%M:%S") if cooldown_until else "-"
                await update.message.reply_text(
                    f"⏳ Condom bekleme süresinde!\n\n"
                    f"🛡️ Şu an aktif mi: {aktif_mi}\n"
                    f"⌛ Tekrar kullanım için kalan: {kalan_cd}\n"
                    f"🕒 Aktiflik bitişi: {au_str}\n"
                    f"🔁 Cooldown bitişi: {cu_str}"
                )
                return
            new_active                   = now + timedelta(minutes=15)
            new_cooldown                 = now + timedelta(hours=2)
            u["condom_active_until"]   = new_active.isoformat()
            u["condom_cooldown_until"] = new_cooldown.isoformat()
            au_str                       = new_active.strftime("%H:%M:%S")
            save_user(conn, u)
    await update.message.reply_text(
        f"🛡️ CONDOM TAKILDI!\n\n"
        f"🎲 15 dakika boyunca şansın arttı.\n"
        f"🪙 YT: +%15 şans | VS: +%7.5 avantaj\n"
        f"🔁 Tekrar kullanım: 2 saat sonra\n"
        f"🕒 Aktiflik bitişi: {au_str}"
    )

@ensure_group
async def cmd_thief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip /thief yaz.")
        return
    target_user = msg.reply_to_message.from_user
    if target_user.id == update.effective_user.id:
        await msg.reply_text("❗ Kendinden çalamazsın!")
        return
    cid   = str(update.effective_chat.id)
    uid   = str(update.effective_user.id)
    tid   = str(target_user.id)
    today = today_str()
    async with _db_lock:
        with get_conn() as conn:
            u = get_user_row(conn, cid, uid)
            t = get_user_row(conn, cid, tid)
            if not is_registered(u):
                await msg.reply_text("❗ Daha kaydın yok, önce /uzat kullan!")
                return
            if not is_registered(t):
                await msg.reply_text("❗ Bu kullanıcı kayıtlı değil.")
                return
            # thief daily count
            td_row = conn.execute(
                "SELECT count FROM thief_daily WHERE chat_id=? AND user_id=? AND target_id=? AND date=?",
                (cid, uid, tid, today)
            ).fetchone()
            count = td_row["count"] if td_row else 0
            if count >= 3:
                await msg.reply_text(f"🚫 Bugün {get_name(target_user)} kişisinden zaten 3 kez çalmaya çalıştın.")
                return
            new_count = count + 1
            conn.execute("""
                INSERT INTO thief_daily (chat_id, user_id, target_id, count, date)
                VALUES (?,?,?,?,?)
                ON CONFLICT(chat_id,user_id,target_id) DO UPDATE SET count=excluded.count, date=excluded.date
            """, (cid, uid, tid, new_count, today))
            oran         = random.randint(1, 6)
            basari_sansi = random.randint(5, 30)
            kazandi      = random.randint(1, 100) <= basari_sansi
            kalan        = 3 - new_count
            my_name      = get_name(update.effective_user)
            target_name  = get_name(target_user)
            if kazandi:
                calinan        = max(1, round(t["boy"] * oran / 100))
                eski_u, eski_t = u["boy"], t["boy"]
                u["boy"]      += calinan
                t["boy"]       = max(0, t["boy"] - calinan)
                save_user(conn, u)
                save_user(conn, t)
                reply = (
                    f"🕵️ HIRSIZLIK BAŞARILI!\n\n"
                    f"😈 {my_name}, {target_name} kişisinin boyundan çaldı!\n"
                    f"🎯 Çalınan oran: %{oran}\n"
                    f"🎲 Başarı şansı: %{basari_sansi}\n"
                    f"🍆 Çalınan: +{calinan} cm\n\n"
                    f"📏 {my_name}: {eski_u} → {u['boy']} cm\n"
                    f"🤏 {target_name}: {eski_t} → {t['boy']} cm\n\n"
                    f"🔁 Kalan deneme: {kalan}"
                )
            else:
                ceza     = max(1, round(u["boy"] * 1 / 100))
                eski_u   = u["boy"]
                u["boy"] = max(0, u["boy"] - ceza)
                save_user(conn, u)
                reply = (
                    f"🚨 YAKALANDIN!\n\n"
                    f"👮 {my_name}, {target_name} kişisinden çalmaya çalışırken enselendi!\n"
                    f"🎯 Denenen oran: %{oran}\n"
                    f"🎲 Başarı şansı: %{basari_sansi}\n"
                    f"📉 Ceza: -{ceza} cm\n\n"
                    f"📏 {my_name}: {eski_u} → {u['boy']} cm\n"
                    f"🛡️ {target_name}: {t['boy']} cm ile sağlam kaldı.\n\n"
                    f"🔁 Kalan deneme: {kalan}"
                )
    await msg.reply_text(reply)

@ensure_group
async def cmd_yolla(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birinin mesajına yanıt verip /yolla <miktar> yaz.")
        return
    if not ctx.args:
        await msg.reply_text("❗ Kullanım: /yolla <miktar>")
        return
    try:
        miktar = int(ctx.args[0])
    except ValueError:
        await msg.reply_text("❗ Geçerli bir miktar gir.")
        return
    if miktar <= 0:
        await msg.reply_text("❗ Miktar 0'dan büyük olmalı!")
        return
    target_user = msg.reply_to_message.from_user
    if target_user.id == update.effective_user.id:
        await msg.reply_text("❗ Kendine gönderemezsin!")
        return
    cid   = str(update.effective_chat.id)
    uid   = str(update.effective_user.id)
    tid   = str(target_user.id)
    today = today_str()
    async with _db_lock:
        with get_conn() as conn:
            u = get_user_row(conn, cid, uid)
            t = get_user_row(conn, cid, tid)
            if not is_registered(u):
                await msg.reply_text("❗ Daha kaydın yok, önce /uzat kullan!")
                return
            if not is_registered(t):
                await msg.reply_text("❗ Bu kullanıcı kayıtlı değil.")
                return
            # reset daily totals if needed
            if u.get("yolla_total_date") != today:
                u["yolla_total"]      = 0
                u["yolla_total_date"] = today
                conn.execute(
                    "DELETE FROM yolla_daily WHERE chat_id=? AND user_id=?", (cid, uid)
                )
            if u["yolla_total"] >= 5:
                await msg.reply_text("🚫 Bugünkü 5 gönderim hakkını doldurdun!")
                return
            yd_row = conn.execute(
                "SELECT count FROM yolla_daily WHERE chat_id=? AND user_id=? AND target_id=? AND date=?",
                (cid, uid, tid, today)
            ).fetchone()
            count_to_target = yd_row["count"] if yd_row else 0
            if count_to_target >= 3:
                await msg.reply_text(f"🚫 Bugün {get_name(target_user)} kişisine zaten 3 kez yolladın.")
                return
            if miktar > u["boy"]:
                await msg.reply_text(f"❗ Yeterli boyun yok! Mevcut: {u['boy']} cm")
                return
            eski_u, eski_t        = u["boy"], t["boy"]
            u["boy"]             -= miktar
            t["boy"]             += miktar
            u["yolla_total"]     += 1
            new_yd_count          = count_to_target + 1
            conn.execute("""
                INSERT INTO yolla_daily (chat_id, user_id, target_id, count, date)
                VALUES (?,?,?,?,?)
                ON CONFLICT(chat_id,user_id,target_id) DO UPDATE SET count=excluded.count, date=excluded.date
            """, (cid, uid, tid, new_yd_count, today))
            my_name      = get_name(update.effective_user)
            target_name  = get_name(target_user)
            toplam_kalan = 5 - u["yolla_total"]
            kisi_kalan   = 3 - new_yd_count
            u_boy, t_boy = u["boy"], t["boy"]
            save_user(conn, u)
            save_user(conn, t)
    await msg.reply_text(
        f"🎁 TRANSFERİ BAŞARILI!\n\n"
        f"📤 Gönderen: {my_name}\n"
        f"📥 Alan: {target_name}\n"
        f"🍆 Yollanan: {miktar} cm\n\n"
        f"📉 {my_name}: {eski_u} → {u_boy} cm\n"
        f"📈 {target_name}: {eski_t} → {t_boy} cm\n\n"
        f"🔁 Toplam kalan hakkın: {toplam_kalan}\n"
        f"👤 Bu kişiye kalan: {kisi_kalan}"
    )

KALDIRMALAR = [
    "{hedef} kaval çalmıyor ama {caller}'ın kobra sepeti deldi geçti! Zehri kime akıtacak kaçın kurtulun! 🐍",
    "{caller} 'selam' dedi, {hedef} vitesi 5'e taktı! Şanzıman dağılacak usta! 🚘",
    "{caller} mesajı attı, {hedef} kasap dükkanındaki antrikot gibi eti masaya vurdu! 🥩",
    "{hedef} gruba girdi, {caller} anında çadırı kurdu! Ateş yakıp etrafında dans yapacak az kaldı. ⛺",
    "{caller} öyle bir çekti ki, {hedef}'ın demir çubuk kilitlendi kaldı! 🧲",
    "SON DAKİKA: {caller}'ın mesajından sonra {hedef}'ın malı masaya 8.5 şiddetinde vurdu! 🚨",
    "{caller} lafı koydu, {hedef} kılıcı kınından çekti! ⚔️",
    "{caller} ortamı yaktı, {hedef}'ın itfaiye hortumu tazyikli su basmaya hazır! 🚒",
]

INDIRMELER = [
    "🐳 {hedef} öyle bir bruh anı yaşattı ki, {caller}'ın Docker container'ı patladı!",
    "🥶 {caller}'ın yazdığını gören {hedef}'ın malı Erzurum soğuğu yemiş gibi içine kaçtı!",
    "🏗️ {caller} ortama girince {hedef}'ın her şeyi döküldü!",
    "🤡 {caller}'ın bu halleri {hedef}'ın bütün hevesini kursağında bıraktı!",
    "💻 {caller}'ın boş muhabbeti {hedef}'ın sunucusuna DDOS attı! Makine çöktü.",
    "📉 {caller}'ın aurası {hedef}'ın değerini sıfırladı!",
    "🗿 {caller}'ın vizyonsuzluğu {hedef}'ı taşa çevirdi!",
]

@ensure_group
async def cmd_kaldir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip /kaldir yaz.")
        return
    caller = get_name(update.effective_user)
    hedef  = get_name(msg.reply_to_message.from_user)
    await msg.reply_text(random.choice(KALDIRMALAR).format(caller=caller, hedef=hedef))

@ensure_group
async def cmd_indir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip /indir yaz.")
        return
    caller = get_name(update.effective_user)
    hedef  = get_name(msg.reply_to_message.from_user)
    await msg.reply_text(random.choice(INDIRMELER).format(caller=caller, hedef=hedef))

@ensure_group
async def cmd_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("❗ Kullanım: /promo <kod>")
        return
    kod = ctx.args[0].upper()
    async with _db_lock:
        with get_conn() as conn:
            promo = conn.execute("SELECT * FROM promos WHERE kod=?", (kod,)).fetchone()
            if not promo:
                await update.message.reply_text("❌ Geçersiz kod!")
                return
            promo = dict(promo)
            if now_tr() > datetime.fromisoformat(promo["expires"]):
                await update.message.reply_text("❌ Bu kodun süresi dolmuş!")
                return
            uid = str(update.effective_user.id)
            cid = str(update.effective_chat.id)
            used = conn.execute(
                "SELECT 1 FROM promo_used WHERE kod=? AND user_id=?", (kod, uid)
            ).fetchone()
            if used:
                await update.message.reply_text("❌ Bu kodu zaten kullandın!")
                return
            await update.message.reply_text("🎁 Kod doğrulanıyor...")
            await asyncio.sleep(random.randint(2, 3))
            u               = get_user_row(conn, cid, uid)
            miktar          = promo["miktar"]
            eski            = u["boy"]
            u["boy"]       += miktar
            u["registered"] = 1
            save_user(conn, u)
            conn.execute("INSERT INTO promo_used (kod, user_id) VALUES (?,?)", (kod, uid))
    await update.message.reply_text(
        f"🎉 PROMO AKTİF!\n\n"
        f"📏 Eklenen: +{miktar} cm\n"
        f"📊 Eski: {eski} cm\n"
        f"🔥 Yeni: {u['boy']} cm"
    )

async def cmd_ozelpromokod(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    if len(ctx.args) < 3:
        await update.message.reply_text("❗ Kullanım: /ozelpromokod <KOD> <miktar> <gün>")
        return
    try:
        kod    = ctx.args[0].upper()
        miktar = int(ctx.args[1])
        gun    = int(ctx.args[2])
    except ValueError:
        await update.message.reply_text("❗ Miktar ve gün sayı olmalı!")
        return
    expires = (now_tr() + timedelta(days=gun)).isoformat()
    async with _db_lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO promos (kod, miktar, expires) VALUES (?,?,?)",
                (kod, miktar, expires)
            )
    await update.message.reply_text(
        f"✅ PROMOKOD OLUŞTURULDU!\n\n"
        f"🎟️ KOD: {kod}\n"
        f"💰 MİKTAR: {miktar} cm\n"
        f"📅 SÜRE: {gun} gün"
    )

async def cmd_promokodolustur(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    if len(ctx.args) < 2:
        await update.message.reply_text("❗ Kullanım: /promokodolustur <miktar> <gün>")
        return
    try:
        miktar = int(ctx.args[0])
        gun    = int(ctx.args[1])
    except ValueError:
        await update.message.reply_text("❗ Miktar ve gün sayı olmalı!")
        return
    kod     = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    expires = (now_tr() + timedelta(days=gun)).isoformat()
    async with _db_lock:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO promos (kod, miktar, expires) VALUES (?,?,?)",
                (kod, miktar, expires)
            )
    await update.message.reply_text(
        f"✅ RASTGELE PROMOKOD OLUŞTURULDU!\n\n"
        f"🎟️ KOD: {kod}\n"
        f"💰 MİKTAR: {miktar} cm\n"
        f"📅 SÜRE: {gun} gün"
    )

async def cmd_istatistik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    async with _db_lock:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(DISTINCT chat_id) as grups, COUNT(*) as users, SUM(boy) as total_boy "
                "FROM users WHERE registered=1"
            ).fetchone()
            promo_count = conn.execute("SELECT COUNT(*) as c FROM promos").fetchone()["c"]
    total   = row["total_boy"] or 0
    users   = row["users"]     or 0
    grups   = row["grups"]     or 0
    ort_boy = round(total / users) if users > 0 else 0
    await update.message.reply_text(
        f"📊 BOT İSTATİSTİKLERİ\n\n"
        f"👥 Toplam grup: {grups}\n"
        f"👤 Toplam kayıtlı kullanıcı: {users}\n"
        f"🍆 Toplam boy: {total} cm\n"
        f"📏 Ortalama boy: {ort_boy} cm\n"
        f"🎟️ Promo kod sayısı: {promo_count}"
    )

async def cmd_disistatistik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    async with _db_lock:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT chat_id, name, boy FROM users WHERE registered=1 ORDER BY chat_id, boy DESC"
            ).fetchall()
    groups = {}
    for row in rows:
        groups.setdefault(row["chat_id"], []).append(row)
    lines = ["📈 DETAYLI İSTATİSTİKLER\n"]
    for cid, users in groups.items():
        lines.append(f"🏠 Grup: {cid} — {len(users)} kişi")
        for i, u in enumerate(users[:5]):
            lines.append(f"  {i+1}. {u['name'] or 'Bilinmeyen'} — {u['boy']} cm")
        lines.append("")
    if len(lines) == 1:
        lines.append("Henüz veri yok.")
    await update.message.reply_text("\n".join(lines))

async def cmd_degistir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip /degistir <miktar> yaz.")
        return
    if not ctx.args:
        await msg.reply_text("❗ Kullanım: /degistir <miktar>")
        return
    try:
        miktar = int(ctx.args[0])
    except ValueError:
        await msg.reply_text("❗ Geçerli bir sayı gir.")
        return
    target_user = msg.reply_to_message.from_user
    cid         = str(update.effective_chat.id)
    tid         = str(target_user.id)
    name        = get_name(target_user)
    async with _db_lock:
        with get_conn() as conn:
            u               = get_user_row(conn, cid, tid)
            u["boy"]        = miktar
            u["registered"] = 1
            u["name"]       = name
            save_user(conn, u)
    await msg.reply_text(f"✅ {name} artık {miktar} cm!")

async def cache_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_chat.type == "private":
        return
    cid  = str(update.effective_chat.id)
    uid  = str(update.effective_user.id)
    name = get_name(update.effective_user)
    now_ts = now_tr().timestamp()
    if now_ts - ctx.bot_data.get("last_name_save", 0) > 60:
        ctx.bot_data["last_name_save"] = now_ts
        async with _db_lock:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO users (chat_id, user_id, name) VALUES (?,?,?) "
                    "ON CONFLICT(chat_id,user_id) DO UPDATE SET name=excluded.name",
                    (cid, uid, name)
                )

async def post_init(app: Application):
    init_db()
    commands = [
        BotCommand("start",    "Bota başla"),
        BotCommand("help",     "Komut rehberi"),
        BotCommand("boyum",    "Kendi boyunu göster"),
        BotCommand("boyu",     "Yanıtladığın kişinin boyunu göster"),
        BotCommand("uzat",     "Boyunu uzat"),
        BotCommand("siralama", "Grup sıralaması"),
        BotCommand("yt",       "Yazı tura oyna"),
        BotCommand("vs",       "Düello at"),
        BotCommand("condom",   "15 dk şans buffı"),
        BotCommand("thief",    "Boy çalmaya çalış"),
        BotCommand("hirsiz",   "Boy çalmaya çalış"),
        BotCommand("yolla",    "Birine boy gönder"),
        BotCommand("kaldir",   "Birini gaza getir"),
        BotCommand("indir",    "Birini göm"),
        BotCommand("promo",    "Promo kodu kullan"),
    ]
    await app.bot.set_my_commands(commands)

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",           cmd_start))
    app.add_handler(CommandHandler("help",            cmd_help))
    app.add_handler(CommandHandler("boyum",           cmd_boyum))
    app.add_handler(CommandHandler("boyu",            cmd_boyu))
    app.add_handler(CommandHandler("uzat",            cmd_uzat))
    app.add_handler(CommandHandler("siralama",        cmd_siralama))
    app.add_handler(CommandHandler("yt",              cmd_yt))
    app.add_handler(CommandHandler("vs",              cmd_vs))
    app.add_handler(CommandHandler("condom",          cmd_condom))
    app.add_handler(CommandHandler("thief",           cmd_thief))
    app.add_handler(CommandHandler("hirsiz",          cmd_thief))
    app.add_handler(CommandHandler("yolla",           cmd_yolla))
    app.add_handler(CommandHandler("kaldir",          cmd_kaldir))
    app.add_handler(CommandHandler("indir",           cmd_indir))
    app.add_handler(CommandHandler("promo",           cmd_promo))
    app.add_handler(CommandHandler("ozelpromokod",    cmd_ozelpromokod))
    app.add_handler(CommandHandler("promokodolustur", cmd_promokodolustur))
    app.add_handler(CommandHandler("istatistik",      cmd_istatistik))
    app.add_handler(CommandHandler("disistatistik",   cmd_disistatistik))
    app.add_handler(CommandHandler("degistir",        cmd_degistir))
    app.add_handler(CallbackQueryHandler(yt_callback, pattern=r"^yt\|"))
    app.add_handler(CallbackQueryHandler(vs_callback, pattern=r"^vs\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cache_name))
    print("Bot başladı...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
