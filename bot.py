pkill -f bot.py
cat > bot.py << 'ENDOFFILE'
import logging
import random
import json
import os
import string
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8381091059:AAGpcMgewVqs0obDpcIaiyqNrMlXeUnsmyY"
ADMIN_ID = 8034872992
TZ = ZoneInfo("Europe/Istanbul")
DB_FILE = "data.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2, default=str)

def now_tr():
    return datetime.now(TZ)

def today_str():
    return now_tr().strftime("%Y-%m-%d")

def get_user(db, chat_id, user_id):
    cid, uid = str(chat_id), str(user_id)
    db.setdefault(cid, {})
    db[cid].setdefault(uid, {
        "boy": 0,
        "registered": False,
        "uzat_hak": 2,
        "uzat_reset": None,
        "condom_active_until": None,
        "condom_cooldown_until": None,
        "thief_daily": {},
        "thief_date": None,
        "yolla_total_date": None,
        "yolla_total": 0,
        "yolla_daily": {},
    })
    return db[cid][uid]

def get_name(user):
    name = user.first_name or ""
    if user.last_name:
        name += " " + user.last_name
    return name.strip() or user.username or str(user.id)

def is_registered(u):
    return u.get("registered", False)

def ensure_group(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            await update.message.reply_text("🚫 Bu komut sadece gruplarda çalışır!")
            return
        return await func(update, ctx)
    return wrapper

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍆 *KRALLIĞA HOŞ GELDİN!*\n\n/help yazarak komutları görebilirsin.",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "╔══════ 🍆 PENİSEREN BOT 🍆 ══════╗\n"
        "           🔥 KOMUT REHBERİ 🔥\n"
        "╚══════════════════════════════════╝\n\n"
        "🏛️ *GENEL KOMUTLAR*\n"
        "📏 /boyum — Kendi penis boyunu gösterir.\n"
        "👀 /boyu — Yanıtladığın veya etiketlediğin kişinin boyunu gösterir.\n"
        "⏳ /uzat — 12 saatlik periyotta 2 hakla boyunu uzatır.\n"
        "🏆 /siralama — Grubun en büyük 25 listesini gösterir.\n"
        "📊 /istatistik — Bot istatistikleri. *(Admin)*\n"
        "📈 /disistatistik — Detaylı bot istatistikleri. *(Admin)*\n\n"
        "🎰 *KUMARHANE*\n"
        "🪙 /yt <miktar> — Yazı tura. Ya katla ya bat!\n"
        "⚔️ /vs <miktar> — Yanıtladığın kişiye düello at.\n"
        "💸 all — Bahislerde tüm boyunla girer. Örn: /yt all\n\n"
        "🛡️ *ÖZEL GÜÇLER & BONUSLAR*\n"
        "🛡️ /condom — 15 dakika şans buffı verir. 2 saatte 1 kullanılır.\n"
        "   └ YT/BK/Slot: +%15 şans, VS: +%7.5 avantaj.\n"
        "🕵️ /thief — Yanıtladığın kişiden %1-6 arası boy çalmaya çalışır.\n"
        "   └ Alternatif: /hirsiz\n"
        "💌 /yolla <miktar> — Yanıtladığın kişiye kendi boyundan gönderir.\n"
        "   └ Günlük 5 gönderim, aynı kişiye günlük 3 gönderim sınırı.\n\n"
        "🚀 *ETKİLEŞİM KOMUTLARI*\n"
        "🔥 /kaldir — Yanıtladığın kişiyi gaza getirir.\n"
        "📉 /indir — Yanıtladığın kişiyi gömer, modunu düşürür.\n\n"
        "🎁 *PROMOSYON*\n"
        "📦 /promo <kod> — Promosyon kodunu kullanır.\n\n"
        "💡 *KISA NOTLAR*\n"
        "• Reply gereken komutlar: /boyu, /vs, /thief, /yolla, /kaldir, /indir\n"
        "• Günlük sayaçlar UTC+3 saatine göre sıfırlanır.\n\n"
        "🌟 *EMEĞİ GEÇENLER* 🌟\n"
        "⚡ @emektas\n"
        "V1"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

@ensure_group
async def cmd_boyum(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    u = get_user(db, update.effective_chat.id, update.effective_user.id)
    if not is_registered(u):
        await update.message.reply_text("❗ Daha kaydın yok, önce /uzat kullan!")
        return
    await update.message.reply_text(f"🍆 Şu anki boyun: *{u['boy']} cm* 🔥", parse_mode="Markdown")

@ensure_group
async def cmd_boyu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    target = None
    if msg.reply_to_message:
        target = msg.reply_to_message.from_user
    if target is None:
        await msg.reply_text("❗ Kullanım: Yanıt vererek /boyu yaz.")
        return
    db = load_db()
    u = get_user(db, update.effective_chat.id, target.id)
    if not is_registered(u):
        await msg.reply_text("❗ Bu kullanıcı kayıtlı değil.")
        return
    await msg.reply_text(f"🍆 *{get_name(target)}* boyu: *{u['boy']} cm* 🔥", parse_mode="Markdown")

@ensure_group
async def cmd_uzat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    uid = str(update.effective_user.id)
    cid = str(update.effective_chat.id)
    u = get_user(db, cid, uid)
    name = get_name(update.effective_user)
    now = now_tr()

    if u["uzat_reset"]:
        reset_time = datetime.fromisoformat(u["uzat_reset"])
        if now >= reset_time:
            u["uzat_hak"] = 2
            u["uzat_reset"] = None

    if u["uzat_hak"] <= 0:
        reset_time = datetime.fromisoformat(u["uzat_reset"])
        kalan = reset_time - now
        total_sec = int(kalan.total_seconds())
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)
        await update.message.reply_text(
            f"⏳ Bu periyot için 2 hakkını doldurdun. Kalan: *{h}s {m}dk*",
            parse_mode="Markdown"
        )
        return

    ekle = random.randint(2, 10)
    u["boy"] += ekle
    u["registered"] = True
    u["uzat_hak"] -= 1

    if u["uzat_hak"] == 1:
        suffix = "💡 Hala 1 hakkın daha var!"
        if u["uzat_reset"] is None:
            u["uzat_reset"] = (now + timedelta(hours=12)).isoformat()
    else:
        suffix = "💤 Bu periyotluk bitti."
        if u["uzat_reset"] is None:
            u["uzat_reset"] = (now + timedelta(hours=12)).isoformat()

    u["name"] = name
    save_db(db)
    await update.message.reply_text(
        f"🔥 *HELAL OLSUN {name}!*\n"
        f"🍆 Tam *{ekle} cm* uzattın!\n"
        f"📏 Yeni boyun: *{u['boy']} cm*\n"
        f"{suffix}",
        parse_mode="Markdown"
    )

@ensure_group
async def cmd_siralama(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    cid = str(update.effective_chat.id)
    group = db.get(cid, {})
    ranked = [(uid, data) for uid, data in group.items() if data.get("registered")]
    ranked.sort(key=lambda x: x[1]["boy"], reverse=True)
    ranked = ranked[:25]
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 *Grup Penis Boyu Sıralaması:* 📊\n"]
    for i, (uid, data) in enumerate(ranked):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = data.get("name", f"Kullanıcı {uid}")
        lines.append(f"{medal} {name} — *{data['boy']} cm*")
    lines.append("\nKimin borusu ne kadar öttü bakalım 😎🍆")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

@ensure_group
async def cmd_yt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    uid = str(update.effective_user.id)
    cid = str(update.effective_chat.id)
    u = get_user(db, cid, uid)
    name = get_name(update.effective_user)

    if not is_registered(u):
        await update.message.reply_text("❗ Daha kaydın yok, önce /uzat kullan!")
        return
    if not ctx.args:
        await update.message.reply_text("❗ Kullanım: /yt <miktar> veya /yt all")
        return

    arg = ctx.args[0].lower()
    if arg == "all":
        bahis = u["boy"]
    else:
        try:
            bahis = int(arg)
        except ValueError:
            await update.message.reply_text("❗ Kullanım: /yt <miktar> veya /yt all")
            return

    if bahis <= 0:
        await update.message.reply_text("❗ Bahis 0'dan büyük olmalı!")
        return
    if bahis > u["boy"]:
        await update.message.reply_text(f"❗ Yeterli boyun yok! Mevcut: *{u['boy']} cm*", parse_mode="Markdown")
        return

    keyboard = [[
        InlineKeyboardButton("🟡 YAZI", callback_data=f"yt|yazi|{uid}|{bahis}"),
        InlineKeyboardButton("🦅 TURA", callback_data=f"yt|tura|{uid}|{bahis}")
    ]]
    sent = await update.message.reply_text(
        f"🪙 *YAZI TURA BAŞLADI!*\n"
        f"👤 {name}\n"
        f"🍆 Bahis: *{bahis} cm*\n"
        f"⏳ 20 saniye süren var!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    ctx.bot_data.setdefault("pending_bets", {})
    ctx.bot_data["pending_bets"][f"{cid}_{sent.message_id}"] = {
        "uid": uid, "cid": cid, "bahis": bahis, "name": name,
        "expires": (now_tr() + timedelta(seconds=20)).isoformat()
    }
    ctx.job_queue.run_once(
        bet_timeout, 20,
        data={"cid": cid, "mid": sent.message_id, "uid": uid, "name": name},
        chat_id=int(cid), name=f"bet_{cid}_{sent.message_id}"
    )

async def bet_timeout(ctx: ContextTypes.DEFAULT_TYPE):
    data = ctx.job.data
    cid, mid, name = data["cid"], data["mid"], data["name"]
    key = f"{cid}_{mid}"
    if key in ctx.bot_data.get("pending_bets", {}):
        del ctx.bot_data["pending_bets"][key]
        try:
            await ctx.bot.edit_message_text(
                chat_id=int(cid), message_id=mid,
                text=f"⚠️ *{name}*, 20 saniye içinde seçim yapmadığın için bahis iptal! 💤",
                parse_mode="Markdown",
                reply_markup=None
            )
        except Exception:
            pass

async def yt_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("|")
    secim_raw = parts[1]
    bet_uid = parts[2]
    bahis = int(parts[3])

    cid = str(query.message.chat_id)
    mid = query.message.message_id
    caller_uid = str(query.from_user.id)

    if caller_uid != bet_uid:
        await query.answer("Bu bahis sana ait değil!", show_alert=True)
        return

    key = f"{cid}_{mid}"
    if key not in ctx.bot_data.get("pending_bets", {}):
        await query.answer("Bu bahis süresi doldu veya zaten oynanıldı.", show_alert=True)
        return

    for job in ctx.job_queue.get_jobs_by_name(f"bet_{cid}_{mid}"):
        job.schedule_removal()
    del ctx.bot_data["pending_bets"][key]

    await query.answer()

    secim = "YAZI" if secim_raw == "yazi" else "TURA"

    await query.edit_message_text(
        f"🪙 Para havada...\nSeçimin: *{secim}*",
        parse_mode="Markdown"
    )
    await asyncio.sleep(random.randint(2, 3))

    db = load_db()
    u = get_user(db, cid, caller_uid)
    name = get_name(query.from_user)

    condom_active = False
    if u.get("condom_active_until"):
        if now_tr() < datetime.fromisoformat(u["condom_active_until"]):
            condom_active = True

    win_chance = 0.65 if condom_active else 0.50
    kazandi = random.random() < win_chance

    if kazandi:
        u["boy"] += bahis
        save_db(db)
        await query.edit_message_text(
            f"🎉 *KAZANDIN!*\n🎲 Seçimin: *{secim}*\n🎁 Kazanç: +*{bahis} cm*\n📏 Yeni Boy: *{u['boy']} cm*",
            parse_mode="Markdown"
        )
    else:
        gelen = "TURA" if secim == "YAZI" else "YAZI"
        u["boy"] = max(0, u["boy"] - bahis)
        save_db(db)
        kaybetMsg = "💀 Git kumda oyna aslanım, buralar seni aşar! 💀" if secim == "YAZI" else "💀 PUHAHAHA BU NE EZİKLİK? 💀"
        await query.edit_message_text(
            f"{kaybetMsg}\n\n❌ *KAYBETTİN!*\n✅ Seçimin: *{secim}*\n🎲 Gelen: *{gelen}*\n📉 Giden: -*{bahis} cm*\n📏 Yeni Boy: *{u['boy']} cm* 🥀",
            parse_mode="Markdown"
        )

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

    arg = ctx.args[0].lower()
    if arg == "all":
        db_temp = load_db()
        uid_temp = str(update.effective_user.id)
        cid_temp = str(update.effective_chat.id)
        u_temp = get_user(db_temp, cid_temp, uid_temp)
        bahis = u_temp["boy"]
    else:
        try:
            bahis = int(arg)
        except ValueError:
            await msg.reply_text("❗ Geçerli bir miktar gir.")
            return

    if bahis <= 0:
        await msg.reply_text("❗ Bahis 0'dan büyük olmalı!")
        return

    db = load_db()
    cid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    tid = str(target_user.id)
    u = get_user(db, cid, uid)
    t = get_user(db, cid, tid)

    if not is_registered(u):
        await msg.reply_text("❗ Daha kaydın yok, önce /uzat kullan!")
        return
    if not is_registered(t):
        await msg.reply_text("❗ Rakip kayıtlı değil.")
        return
    if bahis > u["boy"]:
        await msg.reply_text(f"❗ Yeterli boyun yok! Mevcut: *{u['boy']} cm*", parse_mode="Markdown")
        return
    if bahis > t["boy"]:
        await msg.reply_text(f"❗ Rakibin yeterli boyu yok! Mevcut: *{t['boy']} cm*", parse_mode="Markdown")
        return

    challenger_name = get_name(update.effective_user)
    target_name = get_name(target_user)

    keyboard = [[
        InlineKeyboardButton("🍌 KABUL", callback_data=f"vs|kabul|{uid}|{tid}|{bahis}"),
        InlineKeyboardButton("🙅 KAÇ", callback_data=f"vs|kac|{uid}|{tid}|{bahis}")
    ]]
    sent = await msg.reply_text(
        f"⚔️ *VS BAŞLADI!*\n\n"
        f"🗡️ Meydan okuyan: *{challenger_name}*\n"
        f"🛡️ Rakip: *{target_name}*\n"
        f"🍆 Bahis: *{bahis} cm*\n\n"
        f"⏳ 20 saniye içinde cevap ver!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    ctx.bot_data.setdefault("pending_vs", {})
    ctx.bot_data["pending_vs"][f"{cid}_{sent.message_id}"] = {
        "uid": uid, "tid": tid, "cid": cid, "bahis": bahis,
        "challenger_name": challenger_name, "target_name": target_name
    }
    ctx.job_queue.run_once(
        vs_timeout, 20,
        data={"cid": cid, "mid": sent.message_id, "target_name": target_name},
        chat_id=int(cid), name=f"vs_{cid}_{sent.message_id}"
    )

async def vs_timeout(ctx: ContextTypes.DEFAULT_TYPE):
    data = ctx.job.data
    cid, mid, target_name = data["cid"], data["mid"], data["target_name"]
    key = f"{cid}_{mid}"
    if key in ctx.bot_data.get("pending_vs", {}):
        del ctx.bot_data["pending_vs"][key]
        try:
            await ctx.bot.edit_message_text(
                chat_id=int(cid), message_id=mid,
                text=f"⚠️ *{target_name}* cevap vermedi, VS iptal. 🐔",
                parse_mode="Markdown",
                reply_markup=None
            )
        except Exception:
            pass

async def vs_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("|")
    action = parts[1]
    challenger_uid = parts[2]
    target_uid = parts[3]
    bahis = int(parts[4])

    cid = str(query.message.chat_id)
    mid = query.message.message_id
    caller_uid = str(query.from_user.id)
    key = f"{cid}_{mid}"

    pending = ctx.bot_data.get("pending_vs", {})

    if key not in pending:
        await query.answer("🚫 Bu davet süresi doldu!", show_alert=True)
        return

    vs_data = pending[key]

    if caller_uid != target_uid:
        await query.answer("🚫 Bu davet sana değil ya da süresi doldu!", show_alert=True)
        return

    for job in ctx.job_queue.get_jobs_by_name(f"vs_{cid}_{mid}"):
        job.schedule_removal()
    del pending[key]

    await query.answer()

    target_name = vs_data["target_name"]
    challenger_name = vs_data["challenger_name"]

    if action == "kac":
        await query.edit_message_text(
            f"❌ *{target_name}* kaçtı. VS iptal!",
            parse_mode="Markdown"
        )
        return

    await query.edit_message_text(
        f"⚔️ Düello başladı, sonuç hesaplanıyor...",
        parse_mode="Markdown"
    )
    await asyncio.sleep(random.randint(2, 3))

    db = load_db()
    u = get_user(db, cid, challenger_uid)
    t = get_user(db, cid, target_uid)

    condom_u = False
    condom_t = False
    if u.get("condom_active_until"):
        if now_tr() < datetime.fromisoformat(u["condom_active_until"]):
            condom_u = True
    if t.get("condom_active_until"):
        if now_tr() < datetime.fromisoformat(t["condom_active_until"]):
            condom_t = True

    u_chance = 0.50
    if condom_u:
        u_chance += 0.075
    if condom_t:
        u_chance -= 0.075
    u_chance = max(0.1, min(0.9, u_chance))

    challenger_wins = random.random() < u_chance

    if challenger_wins:
        winner_name = challenger_name
        loser_name = target_name
        u["boy"] += bahis
        t["boy"] = max(0, t["boy"] - bahis)
    else:
        winner_name = target_name
        loser_name = challenger_name
        t["boy"] += bahis
        u["boy"] = max(0, u["boy"] - bahis)

    save_db(db)

    await query.message.reply_text(
        f"💦 *VS SONUCU!*\n\n"
        f"👑 Kazanan: *{winner_name}* (+{bahis} cm)\n"
        f"🤕 Kaybeden: *{loser_name}* (-{bahis} cm)\n\n"
        f"📏 {challenger_name}: *{u['boy']} cm*\n"
        f"🤏 {target_name}: *{t['boy']} cm*",
        parse_mode="Markdown"
    )

@ensure_group
async def cmd_condom(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    uid = str(update.effective_user.id)
    cid = str(update.effective_chat.id)
    u = get_user(db, cid, uid)
    now = now_tr()

    active_until = datetime.fromisoformat(u["condom_active_until"]) if u.get("condom_active_until") else None
    cooldown_until = datetime.fromisoformat(u["condom_cooldown_until"]) if u.get("condom_cooldown_until") else None
    condom_active = active_until and now < active_until
    in_cooldown = cooldown_until and now < cooldown_until

    if condom_active or in_cooldown:
        aktif_mi = "Evet ✅" if condom_active else "Hayır ❌"
        if in_cooldown:
            secs = int((cooldown_until - now).total_seconds())
            h, rem = divmod(secs, 3600)
            m, _ = divmod(rem, 60)
            kalan_cd = f"{h} saat {m} dakika"
        else:
            kalan_cd = "Hazır!"
        au_str = active_until.strftime("%Y-%m-%d %H:%M:%S") if active_until else "-"
        cu_str = cooldown_until.strftime("%Y-%m-%d %H:%M:%S") if cooldown_until else "-"
        await update.message.reply_text(
            f"⏳ *Condom bekleme süresinde!*\n\n"
            f"🛡️ Şu an aktif mi: {aktif_mi}\n"
            f"⌛ Tekrar kullanım için kalan: {kalan_cd}\n"
            f"🕒 Aktiflik bitişi: {au_str}\n"
            f"🔁 Cooldown bitişi: {cu_str}",
            parse_mode="Markdown"
        )
        return

    active_until = now + timedelta(minutes=15)
    cooldown_until = now + timedelta(hours=2)
    u["condom_active_until"] = active_until.isoformat()
    u["condom_cooldown_until"] = cooldown_until.isoformat()
    save_db(db)
    await update.message.reply_text(
        f"🛡️ *CONDOM TAKILDI!*\n\n"
        f"🎲 15 dakika boyunca şansın arttı.\n"
        f"🪙 YT: +%15 şans | VS: +%7.5 avantaj\n"
        f"🔁 Tekrar kullanım: 2 saat sonra\n\n"
        f"🕒 Aktiflik: {now.strftime('%Y-%m-%d %H:%M:%S')} - {active_until.strftime('%Y-%m-%d %H:%M:%S')}",
        parse_mode="Markdown"
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

    db = load_db()
    cid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    tid = str(target_user.id)
    u = get_user(db, cid, uid)
    t = get_user(db, cid, tid)

    if not is_registered(u):
        await msg.reply_text("❗ Daha kaydın yok, önce /uzat kullan!")
        return
    if not is_registered(t):
        await msg.reply_text("❗ Bu kullanıcı kayıtlı değil.")
        return

    today = today_str()
    if u.get("thief_date") != today:
        u["thief_daily"] = {}
        u["thief_date"] = today

    count = u["thief_daily"].get(tid, 0)
    if count >= 3:
        await msg.reply_text(
            f"🚫 Bugün *{get_name(target_user)}* kişisinden zaten 3 kez çalmaya çalıştın.\n"
            f"🕛 UTC+3 00:00'dan sonra tekrar deneyebilirsin.",
            parse_mode="Markdown"
        )
        return

    u["thief_daily"][tid] = count + 1
    my_name = get_name(update.effective_user)
    target_name = get_name(target_user)
    oran = random.randint(1, 6)
    basari_sansi = random.randint(5, 30)
    kazandi = random.randint(1, 100) <= basari_sansi
    kalan = 3 - u["thief_daily"][tid]

    if kazandi:
        calinan = max(1, round(t["boy"] * oran / 100))
        eski_u, eski_t = u["boy"], t["boy"]
        u["boy"] += calinan
        t["boy"] = max(0, t["boy"] - calinan)
        save_db(db)
        await msg.reply_text(
            f"🕵️ *HIRSIZLIK BAŞARILI!*\n\n"
            f"😈 *{my_name}*, *{target_name}* kişisinin boyundan sinsi sinsi çaldı!\n"
            f"🎯 Çalınan oran: %{oran}\n🎲 Başarı şansı: %{basari_sansi}\n"
            f"🍆 Çalınan miktar: +*{calinan} cm*\n\n"
            f"📏 {my_name}: {eski_u} → *{u['boy']} cm*\n"
            f"🤏 {target_name}: {eski_t} → *{t['boy']} cm*\n\n"
            f"🔁 Bugün bu hedefe kalan deneme: *{kalan}*",
            parse_mode="Markdown"
        )
    else:
        ceza = max(1, round(u["boy"] * 1 / 100))
        eski_u = u["boy"]
        u["boy"] = max(0, u["boy"] - ceza)
        save_db(db)
        await msg.reply_text(
            f"🚨 *YAKALANDIN!*\n\n"
            f"👮 *{my_name}*, *{target_name}* kişisinden çalmaya çalışırken enselendi!\n"
            f"🎯 Denenen çalma oranı: %{oran}\n🎲 Başarı şansı: %{basari_sansi}\n"
            f"📉 Ceza: -*{ceza} cm*\n\n"
            f"📏 {my_name}: {eski_u} → *{u['boy']} cm*\n"
            f"🛡️ {target_name}: *{t['boy']} cm* ile sağlam kaldı.\n\n"
            f"🔁 Bugün bu hedefe kalan deneme: *{kalan}*",
            parse_mode="Markdown"
        )

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

    db = load_db()
    cid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    tid = str(target_user.id)
    u = get_user(db, cid, uid)
    t = get_user(db, cid, tid)

    if not is_registered(u):
        await msg.reply_text("❗ Daha kaydın yok, önce /uzat kullan!")
        return
    if not is_registered(t):
        await msg.reply_text("❗ Bu kullanıcı kayıtlı değil.")
        return

    today = today_str()
    if u.get("yolla_total_date") != today:
        u["yolla_total"] = 0
        u["yolla_daily"] = {}
        u["yolla_total_date"] = today

    if u["yolla_total"] >= 5:
        await msg.reply_text("🚫 Bugünkü 5 gönderim hakkını doldurdun!\n🕛 UTC+3 00:00'dan sonra yenilenir.")
        return

    count_to_target = u["yolla_daily"].get(tid, 0)
    if count_to_target >= 3:
        await msg.reply_text(
            f"🚫 Bugün *{get_name(target_user)}* kişisine zaten 3 kez yolladın.\n"
            f"🕛 UTC+3 00:00'dan sonra tekrar deneyebilirsin.",
            parse_mode="Markdown"
        )
        return

    if miktar > u["boy"]:
        await msg.reply_text(f"❗ Yeterli boyun yok! Mevcut: *{u['boy']} cm*", parse_mode="Markdown")
        return

    eski_u, eski_t = u["boy"], t["boy"]
    u["boy"] -= miktar
    t["boy"] += miktar
    u["yolla_total"] += 1
    u["yolla_daily"][tid] = count_to_target + 1
    save_db(db)

    my_name = get_name(update.effective_user)
    target_name = get_name(target_user)
    await msg.reply_text(
        f"🎁 *PENİS BOYU TRANSFERİ BAŞARILI!*\n\n"
        f"📤 Gönderen: *{my_name}*\n📥 Alan: *{target_name}*\n"
        f"🍆 Yollanan: *{miktar} cm*\n\n"
        f"📉 {my_name}: {eski_u} → *{u['boy']} cm*\n"
        f"📈 {target_name}: {eski_t} → *{t['boy']} cm*\n\n"
        f"🔁 Bugünkü toplam yollama hakkın: *{5 - u['yolla_total']}*\n"
        f"👤 Bu kişiye kalan yollama hakkın: *{3 - u['yolla_daily'][tid]}*",
        parse_mode="Markdown"
    )

KALDIRMALAR = [
    "{hedef} kaval çalmıyor ama {caller}'ın kobra sepeti deldi geçti! Zehri kime akıtacak kaçın kurtulun! 🐍",
    "{caller} 'selam' dedi, {hedef} vitesi 5'e taktı! Şanzıman dağılacak usta! 🚘",
    "{caller} mesajı attı, {hedef} kasap dükkanındaki antrikot gibi eti masaya vurdu! 🥩",
    "{hedef} gruba girdi, {caller} anında çadırı kurdu! Ateş yakıp etrafında Kızılderili dansı yapacak az kaldı. ⛺",
    "{caller} öyle bir çekti ki, {hedef}'ın demir çubuk kilitlendi kaldı! 🧲",
    "{caller} sinyali verdi, {hedef}'ın çanak anten full çekiyor! Uzaylılarla iletişime geçtik. 📡",
    "SON DAKİKA: {caller}'ın mesajından sonra {hedef}'ın malı masaya 8.5 şiddetinde vurdu! 🚨",
    "{caller} lafı koydu, {hedef} kılıcı kınından çekti! Kimi deşecek belli değil. ⚔️",
    "{caller} ortamı yaktı, {hedef}'ın itfaiye hortumu tazyikli su basmaya hazır! 🚒",
]

INDIRMELER = [
    "🐳 {hedef} öyle bir 'bruh' anı yaşattı ki, {caller}'ın Docker container'ı patladı! Sistem kendini kapattı.",
    "🥶 {caller}'ın yazdığını gören {hedef}'ın malı Erzurum soğuğu yemiş gibi içine kaçtı! Cımbızla arıyoruz şu an.",
    "🏗️ {caller} ortama girince {hedef}'ın kaçak katına belediye dozerle girdi! Temel çürüdü, bütün dekorasyon döküldü!",
    "🤡 {caller}'ın bu halleri {hedef}'ın bütün hevesini kursağında bıraktı! Balon gibi fosladı koca makine.",
    "💻 {caller}'ın boş muhabbeti {hedef}'ın VDS sunucusuna DDOS attı! Makine çöktü, ping 9999, ayağa kalkmıyor!",
    "🥀 {caller}'ın yaydığı radyasyon {hedef}'ın çınarını kuruttu! Çöle döndü buralar, serap bile göremiyoruz.",
    "📉 {caller}'ın aurası {hedef}'ın değerini sıfırladı! Bedavaya versen kimse almaz o aleti artık.",
    "🗿 {caller}'ın vizyonsuzluğu {hedef}'ı taşa çevirdi! Kan akışı durdu, organ iflas etti!",
]

@ensure_group
async def cmd_kaldir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip /kaldir yaz.")
        return
    caller = get_name(update.effective_user)
    hedef = get_name(msg.reply_to_message.from_user)
    await msg.reply_text(random.choice(KALDIRMALAR).format(caller=caller, hedef=hedef))

@ensure_group
async def cmd_indir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip /indir yaz.")
        return
    caller = get_name(update.effective_user)
    hedef = get_name(msg.reply_to_message.from_user)
    await msg.reply_text(random.choice(INDIRMELER).format(caller=caller, hedef=hedef))

@ensure_group
async def cmd_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("❗ Kullanım: /promo <kod>")
        return
    kod = ctx.args[0].upper()
    db = load_db()
    promolar = db.get("__promolar__", {})
    if kod not in promolar or now_tr() > datetime.fromisoformat(promolar[kod]["expires"]):
        await update.message.reply_text("❌ Bu kodun süresi dolmuş!")
        return
    promo = promolar[kod]
    uid = str(update.effective_user.id)
    cid = str(update.effective_chat.id)
    if uid in promo.get("used_by", []):
        await update.message.reply_text("❌ Bu kodu zaten kullandın!")
        return
    await update.message.reply_text("🎁 Kod doğrulanıyor...")
    await asyncio.sleep(random.randint(2, 3))
    u = get_user(db, cid, uid)
    miktar = promo["miktar"]
    eski = u["boy"]
    u["boy"] += miktar
    u["registered"] = True
    promo.setdefault("used_by", []).append(uid)
    save_db(db)
    await update.message.reply_text(
        f"🎉 *PROMO AKTİF!*\n\n📏 Eklenen: +*{miktar} cm*\n📊 Eski: *{eski} cm*\n🔥 Yeni: *{u['boy']} cm*",
        parse_mode="Markdown"
    )

async def cmd_ozelpromokod(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    if len(ctx.args) < 3:
        await update.message.reply_text("❗ Kullanım: /ozelpromokod <KOD> <miktar> <gün>")
        return
    try:
        kod = ctx.args[0].upper()
        miktar = int(ctx.args[1])
        gun = int(ctx.args[2])
    except ValueError:
        await update.message.reply_text("❗ Miktar ve gün sayı olmalı!")
        return
    db = load_db()
    db.setdefault("__promolar__", {})
    db["__promolar__"][kod] = {
        "miktar": miktar,
        "expires": (now_tr() + timedelta(days=gun)).isoformat(),
        "used_by": []
    }
    save_db(db)
    await update.message.reply_text(
        f"✅ *PROMOKOD OLUŞTURULDU!*\n\n🎟️ PROMOKOD: `{kod}`\n💰 MİKTAR: *{miktar} cm*\n📅 GÜN: *{gun} gün*",
        parse_mode="Markdown"
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
        gun = int(ctx.args[1])
    except ValueError:
        await update.message.reply_text("❗ Miktar ve gün sayı olmalı!")
        return
    kod = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    db = load_db()
    db.setdefault("__promolar__", {})
    db["__promolar__"][kod] = {
        "miktar": miktar,
        "expires": (now_tr() + timedelta(days=gun)).isoformat(),
        "used_by": []
    }
    save_db(db)
    await update.message.reply_text(
        f"✅ *RASTGELE PROMOKOD OLUŞTURULDU!*\n\n🎟️ PROMOKOD: `{kod}`\n💰 MİKTAR: *{miktar} cm*\n📅 GÜN: *{gun} gün*",
        parse_mode="Markdown"
    )

async def cmd_istatistik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    db = load_db()
    toplam_grup = len([k for k in db.keys() if not k.startswith("__")])
    toplam_kullanici = 0
    toplam_boy = 0
    for cid, users in db.items():
        if cid.startswith("__"):
            continue
        for uid, data in users.items():
            if data.get("registered"):
                toplam_kullanici += 1
                toplam_boy += data.get("boy", 0)
    ort_boy = round(toplam_boy / toplam_kullanici) if toplam_kullanici > 0 else 0
    toplam_promo = len(db.get("__promolar__", {}))
    await update.message.reply_text(
        f"📊 *BOT İSTATİSTİKLERİ*\n\n"
        f"👥 Toplam grup: *{toplam_grup}*\n"
        f"👤 Toplam kayıtlı kullanıcı: *{toplam_kullanici}*\n"
        f"🍆 Toplam boy: *{toplam_boy} cm*\n"
        f"📏 Ortalama boy: *{ort_boy} cm*\n"
        f"🎟️ Aktif promo kod sayısı: *{toplam_promo}*",
        parse_mode="Markdown"
    )

async def cmd_disistatistik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    db = load_db()
    lines = ["📈 *DETAYLI BOT İSTATİSTİKLERİ*\n"]
    for cid, users in db.items():
        if cid.startswith("__"):
            continue
        kayitli = [(uid, d) for uid, d in users.items() if d.get("registered")]
        if not kayitli:
            continue
        kayitli.sort(key=lambda x: x[1]["boy"], reverse=True)
        lines.append(f"🏠 Grup: `{cid}` — {len(kayitli)} kişi")
        for i, (uid, d) in enumerate(kayitli[:5]):
            name = d.get("name", uid)
            lines.append(f"  {i+1}. {name} — *{d['boy']} cm*")
        lines.append("")
    if len(lines) == 1:
        lines.append("Henüz veri yok.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

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
    db = load_db()
    cid = str(update.effective_chat.id)
    tid = str(target_user.id)
    t = get_user(db, cid, tid)
    t["boy"] = miktar
    t["registered"] = True
    name = t.get("name") or get_name(target_user)
    t["name"] = name
    save_db(db)
    await msg.reply_text(f"✅ *{name}* artık *{miktar} cm*!", parse_mode="Markdown")

async def cache_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_chat.type == "private":
        return
    db = load_db()
    cid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    db.setdefault(cid, {}).setdefault(uid, {})
    db[cid][uid]["name"] = get_name(update.effective_user)
    save_db(db)

async def post_init(app: Application):
    commands = [
        BotCommand("start",    "Bota başla"),
        BotCommand("help",     "Komut rehberi"),
        BotCommand("boyum",    "Kendi boyunu göster"),
        BotCommand("boyu",     "Yanıtladığın kişinin boyunu göster"),
        BotCommand("uzat",     "Boyunu uzat (12s / 2 hak)"),
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
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("boyum", cmd_boyum))
    app.add_handler(CommandHandler("boyu", cmd_boyu))
    app.add_handler(CommandHandler("uzat", cmd_uzat))
    app.add_handler(CommandHandler("siralama", cmd_siralama))
    app.add_handler(CommandHandler("yt", cmd_yt))
    app.add_handler(CommandHandler("vs", cmd_vs))
    app.add_handler(CommandHandler("condom", cmd_condom))
    app.add_handler(CommandHandler("thief", cmd_thief))
    app.add_handler(CommandHandler("hirsiz", cmd_thief))
    app.add_handler(CommandHandler("yolla", cmd_yolla))
    app.add_handler(CommandHandler("kaldir", cmd_kaldir))
    app.add_handler(CommandHandler("indir", cmd_indir))
    app.add_handler(CommandHandler("promo", cmd_promo))
    app.add_handler(CommandHandler("ozelpromokod", cmd_ozelpromokod))
    app.add_handler(CommandHandler("promokodolustur", cmd_promokodolustur))
    app.add_handler(CommandHandler("istatistik", cmd_istatistik))
    app.add_handler(CommandHandler("disistatistik", cmd_disistatistik))
    app.add_handler(CommandHandler("degistir", cmd_degistir))
    app.add_handler(CallbackQueryHandler(yt_callback, pattern=r"^yt\|"))
    app.add_handler(CallbackQueryHandler(vs_callback, pattern=r"^vs\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cache_name))
    print("Bot başladı...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
ENDOFFILE
python bot.py
