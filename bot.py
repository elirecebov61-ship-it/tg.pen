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

TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 8034872992
TZ = ZoneInfo("Europe/Istanbul")
DB_FILE = "data.json"

_db: dict = {}
_db_lock  = asyncio.Lock()
_bet_lock = asyncio.Lock()
_vs_lock  = asyncio.Lock()

def _load_from_disk() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _write_file(data: str):
    with open(DB_FILE, "w") as f:
        f.write(data)

async def _save_to_disk():
    data = json.dumps(_db, indent=2, default=str)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _write_file, data)

def now_tr() -> datetime:
    return datetime.now(TZ)

def today_str() -> str:
    return now_tr().strftime("%Y-%m-%d")

def get_user(chat_id, user_id) -> dict:
    cid, uid = str(chat_id), str(user_id)
    _db.setdefault(cid, {})
    if uid not in _db[cid]:
        _db[cid][uid] = {
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
        }
    return _db[cid][uid]

def get_name(user) -> str:
    name = user.first_name or ""
    if user.last_name:
        name += " " + user.last_name
    return name.strip() or user.username or str(user.id)

def is_registered(u) -> bool:
    return u.get("registered", False)

def ensure_group(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            await update.message.reply_text("Bu komut sadece gruplarda calisir!")
            return
        return await func(update, ctx)
    return wrapper

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("KRALLIGA HOS GELDIN!\n\n/help yazarak komutlari gorebilirsin.")

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "PENISEREN BOT - KOMUT REHBERI\n\n"
        "GENEL KOMUTLAR\n"
        "/boyum - Kendi penis boyunu gosterir.\n"
        "/boyu - Yanitladigin kisinin boyunu gosterir.\n"
        "/uzat - 12 saatlik periyotta 2 hakla boyunu uzatir.\n"
        "/siralama - Grubun en buyuk 25 listesini gosterir.\n"
        "/istatistik - Bot istatistikleri. (Admin)\n"
        "/disistatistik - Detayli bot istatistikleri. (Admin)\n\n"
        "KUMARHANE\n"
        "/yt <miktar> - Yazi tura. Ya katla ya bat!\n"
        "/vs <miktar> - Yanitladigin kisiye duello at.\n"
        "all - Bahislerde tum boyunla girer. Ornek: /yt all\n\n"
        "OZEL GUCLER\n"
        "/condom - 15 dakika sans buffi verir. 2 saatte 1 kullanilir.\n"
        "/thief - Yanitladigin kisiden boy calmaya calisir.\n"
        "/yolla <miktar> - Yanitladigin kisiye boy gonderir.\n\n"
        "ETKILESIM\n"
        "/kaldir - Yanitladigin kisiye gaz verir.\n"
        "/indir - Yanitladigin kisiye caktirmadan iner.\n\n"
        "PROMOSYON\n"
        "/promo <kod> - Promosyon kodunu kullanir.\n\n"
        "@emektas - V2"
    )
    await update.message.reply_text(text)

@ensure_group
async def cmd_boyum(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    async with _db_lock:
        u = get_user(update.effective_chat.id, update.effective_user.id)
        if not is_registered(u):
            await update.message.reply_text("Daha kaydin yok, once /uzat kullan!")
            return
        boy = u["boy"]
    await update.message.reply_text(f"Su anki boyun: {boy} cm")

@ensure_group
async def cmd_boyu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("Kullanim: Yanit vererek /boyu yaz.")
        return
    target = msg.reply_to_message.from_user
    async with _db_lock:
        u = get_user(update.effective_chat.id, target.id)
        if not is_registered(u):
            await msg.reply_text("Bu kullanici kayitli degil.")
            return
        boy = u["boy"]
    await msg.reply_text(f"{get_name(target)} boyu: {boy} cm")

@ensure_group
async def cmd_uzat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = now_tr()
    async with _db_lock:
        u    = get_user(update.effective_chat.id, update.effective_user.id)
        name = get_name(update.effective_user)
        if u["uzat_reset"]:
            reset_time = datetime.fromisoformat(u["uzat_reset"])
            if now >= reset_time:
                u["uzat_hak"]  = 2
                u["uzat_reset"] = None
        if u["uzat_hak"] <= 0:
            reset_time = datetime.fromisoformat(u["uzat_reset"])
            kalan      = reset_time - now
            total_sec  = int(kalan.total_seconds())
            h, rem     = divmod(total_sec, 3600)
            m, _       = divmod(rem, 60)
            await update.message.reply_text(f"Bu periyot icin 2 hakkini doldurdun. Kalan: {h}s {m}dk")
            return
        ekle            = random.randint(2, 10)
        u["boy"]       += ekle
        u["registered"] = True
        u["uzat_hak"]  -= 1
        u["name"]       = name
        if u["uzat_reset"] is None:
            u["uzat_reset"] = (now + timedelta(hours=12)).isoformat()
        suffix = "Hala 1 hakkin daha var!" if u["uzat_hak"] == 1 else "Bu periyotluk bitti."
        boy    = u["boy"]
        await _save_to_disk()
    await update.message.reply_text(f"HELAL OLSUN {name}!\nTam {ekle} cm uzattin!\nYeni boyun: {boy} cm\n{suffix}")

@ensure_group
async def cmd_siralama(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    async with _db_lock:
        group  = _db.get(cid, {})
        ranked = [(uid, dict(data)) for uid, data in group.items() if data.get("registered")]
    ranked.sort(key=lambda x: x[1]["boy"], reverse=True)
    ranked = ranked[:25]
    medals = ["1.", "2.", "3."]
    lines  = ["Grup Penis Boyu Siralaması:\n"]
    for i, (uid, data) in enumerate(ranked):
        medal = medals[i] if i < 3 else f"{i+1}."
        name  = data.get("name", f"Kullanici {uid}")
        lines.append(f"{medal} {name} - {data['boy']} cm")
    lines.append("\nKimin borusu ne kadar otti bakalim")
    await update.message.reply_text("\n".join(lines))

@ensure_group
async def cmd_yt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid  = str(update.effective_chat.id)
    uid  = str(update.effective_user.id)
    name = get_name(update.effective_user)
    if not ctx.args:
        await update.message.reply_text("Kullanim: /yt <miktar> veya /yt all")
        return
    async with _db_lock:
        u = get_user(cid, uid)
        if not is_registered(u):
            await update.message.reply_text("Daha kaydin yok, once /uzat kullan!")
            return
        arg   = ctx.args[0].lower()
        bahis = u["boy"] if arg == "all" else None
        if bahis is None:
            try:
                bahis = int(arg)
            except ValueError:
                await update.message.reply_text("Kullanim: /yt <miktar> veya /yt all")
                return
        if bahis <= 0:
            await update.message.reply_text("Bahis 0dan buyuk olmali!")
            return
        if bahis > u["boy"]:
            await update.message.reply_text(f"Yeterli boyun yok! Mevcut: {u['boy']} cm")
            return
    keyboard = [[
        InlineKeyboardButton("YAZI", callback_data=f"yt|yazi|{uid}|{bahis}"),
        InlineKeyboardButton("TURA", callback_data=f"yt|tura|{uid}|{bahis}")
    ]]
    sent = await update.message.reply_text(
        f"YAZI TURA BASLADI!\nOyuncu: {name}\nBahis: {bahis} cm\n20 saniye icinde sec!",
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
    data       = ctx.job.data
    cid, mid, name = data["cid"], data["mid"], data["name"]
    key        = f"{cid}_{mid}"
    bets       = ctx.bot_data.get("pending_bets", {})
    if key in bets and not bets[key].get("done"):
        bets[key]["done"] = True
        try:
            await ctx.bot.edit_message_text(
                chat_id=int(cid), message_id=mid,
                text=f"{name}, 20 saniye icinde secim yapmadiniz, bahis iptal!",
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
        await query.answer("Bu bahis sana ait degil!", show_alert=True)
        return
    async with _bet_lock:
        bets = ctx.bot_data.get("pending_bets", {})
        if key not in bets or bets[key].get("done"):
            await query.answer("Bu bahis suresi doldu veya zaten oynandi.", show_alert=True)
            return
        bets[key]["done"] = True
    for job in ctx.job_queue.get_jobs_by_name(f"bet_{key}"):
        job.schedule_removal()
    await query.answer()
    secim = "YAZI" if secim_raw == "yazi" else "TURA"
    await query.edit_message_text(f"Para havada...\nSeciminiz: {secim}")
    await asyncio.sleep(random.randint(2, 3))
    async with _db_lock:
        u    = get_user(cid, caller_uid)
        name = get_name(query.from_user)
        condom_active = bool(
            u.get("condom_active_until") and
            now_tr() < datetime.fromisoformat(u["condom_active_until"])
        )
        if bahis > u["boy"]:
            await query.edit_message_text(f"Oyun sirasinda boyun degisti, bahis iptal! Mevcut: {u['boy']} cm")
            return
        kazandi = random.random() < (0.65 if condom_active else 0.50)
        if kazandi:
            u["boy"] += bahis
            msg = f"KAZANDIN!\nSeciminiz: {secim}\nKazanc: +{bahis} cm\nYeni Boy: {u['boy']} cm"
        else:
            gelen    = "TURA" if secim == "YAZI" else "YAZI"
            u["boy"] = max(0, u["boy"] - bahis)
            msg = f"KAYBETTIN!\nSeciminiz: {secim}\nGelen: {gelen}\nGiden: -{bahis} cm\nYeni Boy: {u['boy']} cm"
        await _save_to_disk()
    await query.edit_message_text(msg)

@ensure_group
async def cmd_vs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("Kullanim: Birine yanit verip /vs <miktar> yaz.")
        return
    if not ctx.args:
        await msg.reply_text("Kullanim: /vs <miktar>")
        return
    target_user = msg.reply_to_message.from_user
    if target_user.id == update.effective_user.id:
        await msg.reply_text("Kendine meydan okuyamazsin!")
        return
    if target_user.is_bot:
        await msg.reply_text("Bota meydan okuyamazsin!")
        return
    cid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    tid = str(target_user.id)
    async with _db_lock:
        u   = get_user(cid, uid)
        t   = get_user(cid, tid)
        arg = ctx.args[0].lower()
        bahis = u["boy"] if arg == "all" else None
        if bahis is None:
            try:
                bahis = int(arg)
            except ValueError:
                await msg.reply_text("Gecerli bir miktar gir.")
                return
        if bahis <= 0:
            await msg.reply_text("Bahis 0dan buyuk olmali!")
            return
        if not is_registered(u):
            await msg.reply_text("Daha kaydin yok, once /uzat kullan!")
            return
        if not is_registered(t):
            await msg.reply_text("Rakip kayitli degil.")
            return
        if bahis > u["boy"]:
            await msg.reply_text(f"Yeterli boyun yok! Mevcut: {u['boy']} cm")
            return
        if bahis > t["boy"]:
            await msg.reply_text(f"Rakibin yeterli boyu yok! Mevcut: {t['boy']} cm")
            return
    challenger_name = get_name(update.effective_user)
    target_name     = get_name(target_user)
    keyboard = [[
        InlineKeyboardButton("KABUL", callback_data=f"vs|kabul|{uid}|{tid}|{bahis}"),
        InlineKeyboardButton("KAC",   callback_data=f"vs|kac|{uid}|{tid}|{bahis}")
    ]]
    sent = await msg.reply_text(
        f"VS BASLADI!\n\nMeydan okuyan: {challenger_name}\nRakip: {target_name}\nBahis: {bahis} cm\n\n20 saniye icinde cevap ver!",
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
                text=f"{target_name} cevap vermedi, VS iptal.",
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
        await query.answer("Bu davet sana degil!", show_alert=True)
        return
    async with _vs_lock:
        vs = ctx.bot_data.get("pending_vs", {})
        if key not in vs or vs[key].get("done"):
            await query.answer("Bu davet suresi doldu!", show_alert=True)
            return
        vs_data         = vs[key]
        vs_data["done"] = True
    for job in ctx.job_queue.get_jobs_by_name(f"vs_{key}"):
        job.schedule_removal()
    await query.answer()
    challenger_name = vs_data["challenger_name"]
    target_name     = vs_data["target_name"]
    if action == "kac":
        await query.edit_message_text(f"{target_name} kacti. VS iptal!")
        return
    await query.edit_message_text("Duello basladi, sonuc hesaplaniyor...")
    await asyncio.sleep(random.randint(2, 3))
    async with _db_lock:
        u = get_user(cid, challenger_uid)
        t = get_user(cid, target_uid)
        condom_u = bool(u.get("condom_active_until") and now_tr() < datetime.fromisoformat(u["condom_active_until"]))
        condom_t = bool(t.get("condom_active_until") and now_tr() < datetime.fromisoformat(t["condom_active_until"]))
        u_chance = max(0.1, min(0.9, 0.50 + (0.075 if condom_u else 0) - (0.075 if condom_t else 0)))
        if bahis > u["boy"] or bahis > t["boy"]:
            await query.message.reply_text("Duello sirasinda boy degisti, VS iptal!")
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
        await _save_to_disk()
    await query.message.reply_text(
        f"VS SONUCU!\n\nKazanan: {winner_name} (+{bahis} cm)\nKaybeden: {loser_name} (-{bahis} cm)\n\n{challenger_name}: {u_boy} cm\n{target_name}: {t_boy} cm"
    )

@ensure_group
async def cmd_condom(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = now_tr()
    async with _db_lock:
        u              = get_user(update.effective_chat.id, update.effective_user.id)
        active_until   = datetime.fromisoformat(u["condom_active_until"])   if u.get("condom_active_until")   else None
        cooldown_until = datetime.fromisoformat(u["condom_cooldown_until"]) if u.get("condom_cooldown_until") else None
        condom_active  = bool(active_until   and now < active_until)
        in_cooldown    = bool(cooldown_until and now < cooldown_until)
        if condom_active or in_cooldown:
            aktif_mi = "Evet" if condom_active else "Hayir"
            if in_cooldown:
                secs     = int((cooldown_until - now).total_seconds())
                h, rem   = divmod(secs, 3600)
                m, _     = divmod(rem, 60)
                kalan_cd = f"{h} saat {m} dakika"
            else:
                kalan_cd = "Hazir!"
            au_str = active_until.strftime("%H:%M:%S")   if active_until   else "-"
            cu_str = cooldown_until.strftime("%H:%M:%S") if cooldown_until else "-"
            await update.message.reply_text(
                f"Condom bekleme suresinde!\n\nSu an aktif mi: {aktif_mi}\nTekrar kullanim icin kalan: {kalan_cd}\nAktiflik bitisi: {au_str}\nCooldown bitisi: {cu_str}"
            )
            return
        new_active                 = now + timedelta(minutes=15)
        new_cooldown               = now + timedelta(hours=2)
        u["condom_active_until"]   = new_active.isoformat()
        u["condom_cooldown_until"] = new_cooldown.isoformat()
        au_str                     = new_active.strftime("%H:%M:%S")
        await _save_to_disk()
    await update.message.reply_text(
        f"CONDOM TAKILDI!\n\n15 dakika boyunca sansin artti.\nYT: +15% sans | VS: +7.5% avantaj\nTekrar kullanim icin: 2 saat sonra\nAktiflik bitisi: {au_str}"
    )

@ensure_group
async def cmd_thief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("Kullanim: Birine yanit verip /thief yaz.")
        return
    target_user = msg.reply_to_message.from_user
    if target_user.id == update.effective_user.id:
        await msg.reply_text("Kendinden calamazsin!")
        return
    cid   = str(update.effective_chat.id)
    uid   = str(update.effective_user.id)
    tid   = str(target_user.id)
    today = today_str()
    async with _db_lock:
        u = get_user(cid, uid)
        t = get_user(cid, tid)
        if not is_registered(u):
            await msg.reply_text("Daha kaydin yok, once /uzat kullan!")
            return
        if not is_registered(t):
            await msg.reply_text("Bu kullanici kayitli degil.")
            return
        if u.get("thief_date") != today:
            u["thief_daily"] = {}
            u["thief_date"]  = today
        count = u["thief_daily"].get(tid, 0)
        if count >= 3:
            await msg.reply_text(f"Bugun {get_name(target_user)} kisisinden zaten 3 kez calmaya calistin.")
            return
        u["thief_daily"][tid] = count + 1
        oran         = random.randint(1, 6)
        basari_sansi = random.randint(5, 30)
        kazandi      = random.randint(1, 100) <= basari_sansi
        kalan        = 3 - u["thief_daily"][tid]
        my_name      = get_name(update.effective_user)
        target_name  = get_name(target_user)
        if kazandi:
            calinan        = max(1, round(t["boy"] * oran / 100))
            eski_u, eski_t = u["boy"], t["boy"]
            u["boy"]      += calinan
            t["boy"]       = max(0, t["boy"] - calinan)
            await _save_to_disk()
            reply = (
                f"HIRSIZLIK BASARILI!\n\n{my_name}, {target_name} kisisinin boyundan caldi!\n"
                f"Calinan oran: %{oran}\nBasari sansi: %{basari_sansi}\nCalinan: +{calinan} cm\n\n"
                f"{my_name}: {eski_u} -> {u['boy']} cm\n{target_name}: {eski_t} -> {t['boy']} cm\n\nKalan deneme: {kalan}"
            )
        else:
            ceza     = max(1, round(u["boy"] * 1 / 100))
            eski_u   = u["boy"]
            u["boy"] = max(0, u["boy"] - ceza)
            await _save_to_disk()
            reply = (
                f"YAKALANDIN!\n\n{my_name}, {target_name} kisisinden calmaya calisirken enselendi!\n"
                f"Ceza: -{ceza} cm\n\n{my_name}: {eski_u} -> {u['boy']} cm\n\nKalan deneme: {kalan}"
            )
    await msg.reply_text(reply)

@ensure_group
async def cmd_yolla(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("Kullanim: Birinin mesajina yanit verip /yolla <miktar> yaz.")
        return
    if not ctx.args:
        await msg.reply_text("Kullanim: /yolla <miktar>")
        return
    try:
        miktar = int(ctx.args[0])
    except ValueError:
        await msg.reply_text("Gecerli bir miktar gir.")
        return
    if miktar <= 0:
        await msg.reply_text("Miktar 0dan buyuk olmali!")
        return
    target_user = msg.reply_to_message.from_user
    if target_user.id == update.effective_user.id:
        await msg.reply_text("Kendine gonderemezsin!")
        return
    cid   = str(update.effective_chat.id)
    uid   = str(update.effective_user.id)
    tid   = str(target_user.id)
    today = today_str()
    async with _db_lock:
        u = get_user(cid, uid)
        t = get_user(cid, tid)
        if not is_registered(u):
            await msg.reply_text("Daha kaydin yok, once /uzat kullan!")
            return
        if not is_registered(t):
            await msg.reply_text("Bu kullanici kayitli degil.")
            return
        if u.get("yolla_total_date") != today:
            u["yolla_total"] = 0
            u["yolla_daily"] = {}
            u["yolla_total_date"] = today
        if u["yolla_total"] >= 5:
            await msg.reply_text("Bugunku 5 gonderim hakkini doldurdun!")
            return
        count_to_target = u["yolla_daily"].get(tid, 0)
        if count_to_target >= 3:
            await msg.reply_text(f"Bugun {get_name(target_user)} kisisine zaten 3 kez yolladiniz.")
            return
        if miktar > u["boy"]:
            await msg.reply_text(f"Yeterli boyun yok! Mevcut: {u['boy']} cm")
            return
        eski_u, eski_t        = u["boy"], t["boy"]
        u["boy"]             -= miktar
        t["boy"]             += miktar
        u["yolla_total"]     += 1
        u["yolla_daily"][tid] = count_to_target + 1
        my_name               = get_name(update.effective_user)
        target_name           = get_name(target_user)
        toplam_kalan          = 5 - u["yolla_total"]
        kisi_kalan            = 3 - u["yolla_daily"][tid]
        u_boy, t_boy          = u["boy"], t["boy"]
        await _save_to_disk()
    await msg.reply_text(
        f"TRANSFER BASARILI!\n\nGonderen: {my_name}\nAlan: {target_name}\nYollanan: {miktar} cm\n\n"
        f"{my_name}: {eski_u} -> {u_boy} cm\n{target_name}: {eski_t} -> {t_boy} cm\n\n"
        f"Toplam kalan hakkin: {toplam_kalan}\nBu kisiye kalan: {kisi_kalan}"
    )

KALDIRMALAR = [
    "{hedef} kaval calmiyor ama {caller}in kobra sepeti deldi gecti!",
    "{caller} selam dedi, {hedef} vitesi 5e takti!",
    "{caller} mesaji atti, {hedef} kasap gibi eti masaya vurdu!",
    "{hedef} gruba girdi, {caller} aninda cadiri kurdu!",
    "{caller} oyle bir cekti ki, {hedef}in demir cubuk kitlendi!",
    "SON DAKIKA: {caller}in mesajindan sonra {hedef}in mali masaya 8.5 siddetinde vurdu!",
    "{caller} lafi koydu, {hedef} kilici kininden cekti!",
    "{caller} ortami yakti, {hedef}in hortumu basmaya hazir!",
]

INDIRMELER = [
    "{hedef} oyle bir bruh ani yasatti ki, {caller}in sistemi coktu!",
    "{caller}in yazdigini goren {hedef}in mali icine kacti!",
    "{caller} ortama girince {hedef}in her seyi dokuldu!",
    "{caller}in bos muhabbeti {hedef}in sunucusuna DDOS atti!",
    "{caller}in aurasi {hedef}in degerini sifiraldi!",
    "{caller}in vizyonsuzlugu {hedef}i tasa cevirdi!",
]

@ensure_group
async def cmd_kaldir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("Kullanim: Birine yanit verip /kaldir yaz.")
        return
    caller = get_name(update.effective_user)
    hedef  = get_name(msg.reply_to_message.from_user)
    await msg.reply_text(random.choice(KALDIRMALAR).format(caller=caller, hedef=hedef))

@ensure_group
async def cmd_indir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("Kullanim: Birine yanit verip /indir yaz.")
        return
    caller = get_name(update.effective_user)
    hedef  = get_name(msg.reply_to_message.from_user)
    await msg.reply_text(random.choice(INDIRMELER).format(caller=caller, hedef=hedef))

@ensure_group
async def cmd_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Kullanim: /promo <kod>")
        return
    kod = ctx.args[0].upper()
    async with _db_lock:
        promolar = _db.get("__promolar__", {})
        if kod not in promolar:
            await update.message.reply_text("Gecersiz kod!")
            return
        promo      = promolar[kod]
        expires_dt = datetime.fromisoformat(promo["expires"])
        if now_tr() > expires_dt:
            await update.message.reply_text("Bu kodun suresi dolmus!")
            return
        uid = str(update.effective_user.id)
        cid = str(update.effective_chat.id)
        if uid in promo.get("used_by", []):
            await update.message.reply_text("Bu kodu zaten kullandin!")
            return
        await update.message.reply_text("Kod dogrulanıyor...")
        await asyncio.sleep(random.randint(2, 3))
        u               = get_user(cid, uid)
        miktar          = promo["miktar"]
        eski            = u["boy"]
        u["boy"]       += miktar
        u["registered"] = True
        promo.setdefault("used_by", []).append(uid)
        await _save_to_disk()
    await update.message.reply_text(f"PROMO AKTIF!\n\nEklenen: +{miktar} cm\nEski: {eski} cm\nYeni: {u['boy']} cm")

async def cmd_ozelpromokod(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Bu komuta erisim izniniz yok.")
        return
    if len(ctx.args) < 3:
        await update.message.reply_text("Kullanim: /ozelpromokod <KOD> <miktar> <gun>")
        return
    try:
        kod    = ctx.args[0].upper()
        miktar = int(ctx.args[1])
        gun    = int(ctx.args[2])
    except ValueError:
        await update.message.reply_text("Miktar ve gun sayi olmali!")
        return
    expires = (now_tr() + timedelta(days=gun)).isoformat()
    async with _db_lock:
        _db.setdefault("__promolar__", {})[kod] = {"miktar": miktar, "expires": expires, "used_by": []}
        await _save_to_disk()
    await update.message.reply_text(f"PROMOKOD OLUSTURULDU!\n\nKOD: {kod}\nMIKTAR: {miktar} cm\nSURE: {gun} gun")

async def cmd_promokodolustur(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Bu komuta erisim izniniz yok.")
        return
    if len(ctx.args) < 2:
        await update.message.reply_text("Kullanim: /promokodolustur <miktar> <gun>")
        return
    try:
        miktar = int(ctx.args[0])
        gun    = int(ctx.args[1])
    except ValueError:
        await update.message.reply_text("Miktar ve gun sayi olmali!")
        return
    kod     = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    expires = (now_tr() + timedelta(days=gun)).isoformat()
    async with _db_lock:
        _db.setdefault("__promolar__", {})[kod] = {"miktar": miktar, "expires": expires, "used_by": []}
        await _save_to_disk()
    await update.message.reply_text(f"PROMOKOD OLUSTURULDU!\n\nKOD: {kod}\nMIKTAR: {miktar} cm\nSURE: {gun} gun")

async def cmd_istatistik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Bu komuta erisim izniniz yok.")
        return
    async with _db_lock:
        grup_cidler      = [k for k in _db.keys() if not k.startswith("__")]
        toplam_kullanici = 0
        toplam_boy       = 0
        for cid in grup_cidler:
            for uid, data in _db[cid].items():
                if data.get("registered"):
                    toplam_kullanici += 1
                    toplam_boy       += data.get("boy", 0)
    ort_boy      = round(toplam_boy / toplam_kullanici) if toplam_kullanici > 0 else 0
    toplam_promo = len(_db.get("__promolar__", {}))
    await update.message.reply_text(
        f"BOT ISTATISTIKLERI\n\nToplam grup: {len(grup_cidler)}\nToplam kullanici: {toplam_kullanici}\n"
        f"Toplam boy: {toplam_boy} cm\nOrtalama boy: {ort_boy} cm\nPromo kod sayisi: {toplam_promo}"
    )

async def cmd_disistatistik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Bu komuta erisim izniniz yok.")
        return
    async with _db_lock:
        snap = {k: dict(v) for k, v in _db.items() if not k.startswith("__")}
    lines = ["DETAYLI ISTATISTIKLER\n"]
    for cid, users in snap.items():
        kayitli = [(uid, d) for uid, d in users.items() if d.get("registered")]
        if not kayitli:
            continue
        kayitli.sort(key=lambda x: x[1]["boy"], reverse=True)
        lines.append(f"Grup: {cid} - {len(kayitli)} kisi")
        for i, (uid, d) in enumerate(kayitli[:5]):
            lines.append(f"  {i+1}. {d.get('name', uid)} - {d['boy']} cm")
        lines.append("")
    if len(lines) == 1:
        lines.append("Henuz veri yok.")
    await update.message.reply_text("\n".join(lines))

async def cmd_degistir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Bu komuta erisim izniniz yok.")
        return
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("Kullanim: Birine yanit verip /degistir <miktar> yaz.")
        return
    if not ctx.args:
        await msg.reply_text("Kullanim: /degistir <miktar>")
        return
    try:
        miktar = int(ctx.args[0])
    except ValueError:
        await msg.reply_text("Gecerli bir sayi gir.")
        return
    target_user = msg.reply_to_message.from_user
    cid         = str(update.effective_chat.id)
    tid         = str(target_user.id)
    async with _db_lock:
        t               = get_user(cid, tid)
        t["boy"]        = miktar
        t["registered"] = True
        name            = t.get("name") or get_name(target_user)
        t["name"]       = name
        await _save_to_disk()
    await msg.reply_text(f"{name} artik {miktar} cm!")

async def cache_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_chat.type == "private":
        return
    cid  = str(update.effective_chat.id)
    uid  = str(update.effective_user.id)
    name = get_name(update.effective_user)
    async with _db_lock:
        _db.setdefault(cid, {}).setdefault(uid, {})["name"] = name
    now_ts = now_tr().timestamp()
    if now_ts - ctx.bot_data.get("last_name_save", 0) > 60:
        ctx.bot_data["last_name_save"] = now_ts
        await _save_to_disk()

async def post_init(app: Application):
    global _db
    _db = _load_from_disk()
    commands = [
        BotCommand("start",    "Bota basla"),
        BotCommand("help",     "Komut rehberi"),
        BotCommand("boyum",    "Kendi boyunu goster"),
        BotCommand("boyu",     "Yanitladigin kisinin boyunu goster"),
        BotCommand("uzat",     "Boyunu uzat"),
        BotCommand("siralama", "Grup siralaması"),
        BotCommand("yt",       "Yazi tura oyna"),
        BotCommand("vs",       "Duello at"),
        BotCommand("condom",   "15 dk sans buffi"),
        BotCommand("thief",    "Boy calmaya calis"),
        BotCommand("hirsiz",   "Boy calmaya calis"),
        BotCommand("yolla",    "Birine boy gonder"),
        BotCommand("kaldir",   "Birini gaza getir"),
        BotCommand("indir",    "Birini gom"),
        BotCommand("promo",    "Promo kodu kullan"),
    ]
    await app.bot.set_my_commands(commands)

def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN environment variable tanimlanmamis!")
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
    print("Bot basladi...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
