import logging
import random
import os
import string
import asyncio
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import psycopg2
import psycopg2.extras
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN        = os.environ["BOT_TOKEN"]
ADMIN_ID     = 8034872992
TZ           = ZoneInfo("Europe/Istanbul")
DATABASE_URL = os.environ["DATABASE_URL"]

_db_lock  = asyncio.Lock()
_bet_lock = asyncio.Lock()
_vs_lock  = asyncio.Lock()
_bk_lock  = asyncio.Lock()

def get_conn():
    for attempt in range(10):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False
            return conn
        except Exception as e:
            print(f"DB bağlantı xətası (cəhd {attempt+1}/10): {e}")
            time.sleep(3)
    raise Exception("DB-yə qoşulmaq mümkün olmadı!")

def init_db():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id               TEXT NOT NULL,
                user_id               TEXT NOT NULL,
                name                  TEXT DEFAULT '',
                boy                   NUMERIC DEFAULT 0,
                registered            INTEGER DEFAULT 0,
                uzat_hak              INTEGER DEFAULT 2,
                uzat_reset            TEXT DEFAULT NULL,
                condom_active_until   TEXT DEFAULT NULL,
                condom_cooldown_until TEXT DEFAULT NULL,
                thief_date            TEXT DEFAULT NULL,
                yolla_total_date      TEXT DEFAULT NULL,
                yolla_total           INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS thief_daily (
                chat_id   TEXT NOT NULL,
                user_id   TEXT NOT NULL,
                target_id TEXT NOT NULL,
                count     INTEGER DEFAULT 0,
                date      TEXT NOT NULL,
                PRIMARY KEY (chat_id, user_id, target_id)
            );
            CREATE TABLE IF NOT EXISTS yolla_daily (
                chat_id   TEXT NOT NULL,
                user_id   TEXT NOT NULL,
                target_id TEXT NOT NULL,
                count     INTEGER DEFAULT 0,
                date      TEXT NOT NULL,
                PRIMARY KEY (chat_id, user_id, target_id)
            );
            CREATE TABLE IF NOT EXISTS promos (
                kod     TEXT PRIMARY KEY,
                miktar  INTEGER NOT NULL,
                expires TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS promo_used (
                kod     TEXT NOT NULL,
                user_id TEXT NOT NULL,
                chat_id TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (kod, user_id, chat_id)
            );
            CREATE TABLE IF NOT EXISTS prohere_users (
                user_id TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                title   TEXT DEFAULT ''
            );
        """)
        conn.commit()
        cur.close()
    finally:
        conn.close()

def get_user_row(cur, chat_id, user_id):
    cid, uid = str(chat_id), str(user_id)
    cur.execute("SELECT * FROM users WHERE chat_id=%s AND user_id=%s", (cid, uid))
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO users (chat_id, user_id) VALUES (%s,%s)", (cid, uid))
        cur.execute("SELECT * FROM users WHERE chat_id=%s AND user_id=%s", (cid, uid))
        row = cur.fetchone()
    return dict(row)

def save_user(cur, u: dict):
    cur.execute("""
        UPDATE users SET
            name=%s, boy=%s, registered=%s,
            uzat_hak=%s, uzat_reset=%s,
            condom_active_until=%s,
            condom_cooldown_until=%s,
            thief_date=%s,
            yolla_total_date=%s,
            yolla_total=%s
        WHERE chat_id=%s AND user_id=%s
    """, (
        u.get("name"), u.get("boy"), u.get("registered"),
        u.get("uzat_hak"), u.get("uzat_reset"),
        u.get("condom_active_until"),
        u.get("condom_cooldown_until"),
        u.get("thief_date"),
        u.get("yolla_total_date"),
        u.get("yolla_total"),
        u.get("chat_id"), u.get("user_id")
    ))

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

def ensure_group(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == "private":
            await update.message.reply_text("🚫 Bu komut sadece gruplarda çalışır!")
            return
        return await func(update, ctx)
    return wrapper

KAYBETTI_MESAJLAR = [
    "💀 Zort! Patladın aslan parçası, silin şunu gruptan.",
    "💀 PUHAHAHA BU NE EZİKLİK?",
    "💀 Git kumda oyna aslanım, buralar seni aşar!",
    "💀 Annen görse ağlardı bu hali.",
    "💀 Silah tutmayı bırak, kazma kürek daha uygun sana.",
    "💀 Bu ne rezalet? Utanmıyor musun?",
    "💀 Efsane eziklik, tarihe geçti bu an.",
    "💀 Bunu gören dedeni de ağlatırsın.",
    "💀 Hoppp! Düşük seviyeli oyuncu tespit edildi.",
    "💀 Grup sohbetinde bundan sonra sus, konuşma hakkın yok.",
]

BK_KAZANDI_MESAJLAR = [
    "💎 Kral sahalara döndü! Büyüdü de serpildi mübarek!",
    "🍆 Maşallah! Bu gidişle gruba sığmayacaksın, devam!",
    "🎯 Eller titredi ama göz yanıltmadı! Şampiyon bu!",
    "👑 Tanrı vardır ve senden yanadır bu gün!",
    "🚀 Roket gibi fırladı! Durduran yok!",
    "🎪 Sihirbaz mısın sen ya! Nasıl buldun öyle!",
    "💥 PATLADI! Ama iyi anlamda, boy patladı!",
    "🦁 Aslan gibi seçti, aslan gibi kazandı!",
]

BK_KAYBETTI_MESAJLAR = [
    "🏦 İflas bayrağını çektin! Haciz memurları kalan o 3-5 santimi de alıp gidecek birazdan.",
    "🔭 NASA bile en güçlü teleskopla aradı ama bulamadı! Nereye kayboldu o koca alet? Aaa minnacık.",
    "🤡 Senin o elindekiyle anca çay karıştırılır aslanım! Çık git masadan, vizyonumuzu bozuyorsun.",
    "📉 Borsa çöktü, ekonomi battı, sen de battın. Tebrikler!",
    "🥄 Kaşıkla kazısan bu kadar çıkar artık, devam etme!",
    "😂 Arkadaşların bunu duysa seni gruptan atar, sus kimseye söyleme.",
    "🪦 Buraya bir mezar taşı dikelim: 'Burada bir boy yatar, 2024-2024'",
    "🐌 Salyangoz bile senden hızlı karar verirdi, yine de yanlış seçtin!",
]

SLOT_SEMBOLLER = ["🍒", "🍋", "🍇", "🔔", "⭐", "💎", "7️⃣"]

SLOT_JACKPOT_MESAJLAR = [
    "🚒 İtfaiye çağırın, makine alev alev yanıyor! Motor soğumuyor usta!",
    "👑 Efsane! Bu makine seni tanrı olarak kabul etti, saygıyla eğiliyoruz!",
    "💥 JACKPOT! Grubun elektriği gitti şok dalgasından!",
    "🎰 Makine ağlıyor! Bu kadar mı olur ya, tüm kasayı boşalttın!",
    "🤑 Para sayma makinesi bile senin yanında ezik kaldı! JACKPOT KRALI!",
    "🦁 Aslan avlandı! Makine senin önünde diz çöktü!",
]

SLOT_X2_MESAJLAR = [
    "🪈 Boruyu öyle bir döşedin ki grubun altyapısı çöktü! Helal olsun!",
    "😎 Fena değil, fena değil! Makine sana ufak bir jest yaptı.",
    "🎯 İki eşleşti! Adam gibi kazanç, adam gibi boy!",
    "🔥 Yarı yolda değil tam yolda! İki eşleşince iş değişiyor!",
    "💪 Güzel seçim! Makine direnç gösterdi ama sen kazandın!",
    "🚀 İkili komboda! Devam et, jackpot uzak değil!",
]

SLOT_KAYBETTI_MESAJLAR = [
    "🥶 Erzurum soğuğu yemiş gibi içine kaçtı! Cımbız ve büyüteç seti kargoluyoruz, anca bulursun.",
    "🤡 Makine sana baktı, güldü ve paranı aldı. Saygılar.",
    "📉 Ekonomik kriz geldi, boy gitti. Devam et bakalım daha ne kadar dayanırsın!",
    "💀 Makine 1 - Sen 0. Matematik bu, değişmiyor.",
    "🗿 Taş gibi dondu makine. Çünkü senden almak çok kolaydı.",
    "😂 Arkadaşların bu anı görseydi, seni gruptan atarlardı. Sus kimseye söyleme.",
    "🪦 Boyun burada yatıyor. Mezar taşına ne yazsın? 'Bir daha oynama'",
    "🐌 Salyangoz bile daha iyi şans getirir senden!",
]

def random_spin() -> list:
    return [random.choice(SLOT_SEMBOLLER) for _ in range(3)]

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍆 KRALLIĞA HOŞ GELDİN!\n\n`/help` yazarak komutları görebilirsin.",
        parse_mode="Markdown"
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "╔══════ 🍆 PENİSCAN BOT 🍆 ══════╗\n"
        "        🔥 KOMUT REHBERİ 🔥\n"
        "╚══════════════════════════╝\n\n"
        "🏛️ GENEL KOMUTLAR\n"
        "📏 `/boyum` — Kendi penis boyunu gösterir.\n"
        "👀 `/boyu` — Yanıtladığın veya etiketlediğin kişinin boyunu gösterir.\n"
        "⏳ `/uzat` — 12 saatlik periyotta 2 hakla boyunu uzatır.\n"
        "🏆 `/siralama` — Grubun en büyük 25 listesini gösterir.\n"
        "📊 `/istatistik` — Bot istatistikleri. _(Admin)_\n"
        "📈 `/disistatistik` — Detaylı bot istatistikleri. _(Admin)_\n\n"
        "🎰 KUMARHANE\n"
        "🪙 `/yt <miktar>` — Yazı tura. Ya katla ya bat!\n"
        "🃏 `/bk <miktar>` — Bul karayı, 3 katını kap.\n"
        "🎰 `/slot <miktar>` — Slot çevir, jackpot kovala.\n"
        "⚔️ `/vs <miktar>` — Yanıtladığın kişiye düello at.\n"
        "💸 `all` — Bahislerde tüm boyunla girer. Örn: `/yt all`\n\n"
        "🛡️ ÖZEL GÜÇLER & BONUSLAR\n"
        "🛡️ `/condom` — 15 dakika şans buffı verir. 2 saatte 1 kullanılır.\n"
        "   └ YT/BK/Slot: +%15 şans, VS: +%7.5 avantaj.\n"
        "🕵️ `/thief` — Yanıtladığın kişiden %1-6 arası boy çalmaya çalışır.\n"
        "   └ Alternatif: `/hirsiz`\n"
        "💌 `/yolla <miktar>` — Yanıtladığın kişiye kendi boyundan gönderir.\n"
        "   └ Günlük 5 gönderim, aynı kişiye günlük 3 gönderim sınırı.\n\n"
        "🚀 ETKİLEŞİM KOMUTLARI\n"
        "🔥 `/kaldir` — Yanıtladığın kişiyi gaza getirir.\n"
        "📉 `/indir` — Yanıtladığın kişiyi gömer, modunu düşürür.\n\n"
        "🎁 PROMOSYON\n"
        "📦 `/promo <kod>` — Promosyon kodunu kullanır.\n"
        "🎫 `/promokodolustur <miktar> <gün>` — Rastgele promo kod üretir. _(Admin)_\n"
        "🎟️ `/ozelpromokod <KOD> <miktar> <gün>` — Özel promo kod üretir. _(Admin)_\n\n"
        "💡 KISA NOTLAR\n"
        "• Reply gereken komutlar: `/boyu`, `/vs`, `/thief`, `/yolla`, `/kaldir`, `/indir`\n"
        "• Günlük sayaçlar UTC+3 saatine göre sıfırlanır.\n\n"
        "🌟 EMEĞİ GEÇENLER 🌟\n"
        "⚡ @emektas  &  @xArchDev\n"
        "V2"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

@ensure_group
async def cmd_boyum(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, update.effective_chat.id, update.effective_user.id)
        finally:
            conn.close()
    if not is_registered(u):
        await update.message.reply_text("❗ Daha kaydın yok, önce `/uzat` kullan!", parse_mode="Markdown")
        return
    await update.message.reply_text(
        f"🍆 Şu anki boyun: *{u['boy']} cm* 🔥",
        parse_mode="Markdown"
    )

@ensure_group
async def cmd_boyu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text(
            "❗ Kullanım: Yanıt vererek `/boyu` veya `/boyu @kullanici`",
            parse_mode="Markdown"
        )
        return
    target = msg.reply_to_message.from_user
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, update.effective_chat.id, target.id)
        finally:
            conn.close()
    if not is_registered(u):
        await msg.reply_text("❗ Bu kullanıcı kayıtlı değil.")
        return
    name = get_name(target)
    await msg.reply_text(
        f"🍆 *{name}* boyu: *{u['boy']} cm* 🔥",
        parse_mode="Markdown"
    )

@ensure_group
async def cmd_uzat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now  = now_tr()
    name = get_name(update.effective_user)
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, update.effective_chat.id, update.effective_user.id)
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
                        f"⏳ Bu periyot için *2* hakkını doldurdun.\nKalan: *{h} saat {m} dk*",
                        parse_mode="Markdown"
                    )
                    return
                ekle            = random.randint(2, 10)
                u["boy"]       += ekle
                u["registered"] = 1
                u["uzat_hak"]  -= 1
                u["name"]       = name
                if u["uzat_reset"] is None:
                    u["uzat_reset"] = (now + timedelta(hours=12)).isoformat()
                if u["uzat_hak"] == 1:
                    suffix = "💤 *Hala 1 hakkın daha var!*"
                else:
                    suffix = "💤 *Bu periyotluk bitti.*"
                boy = u["boy"]
                save_user(cur, u)
            conn.commit()
        finally:
            conn.close()
    await update.message.reply_text(
        f"🔥 *HELAL OLSUN {name}!*\n"
        f"🍆 Tam *{ekle} cm* uzattın!\n"
        f"📏 Yeni boyun: *{boy} cm*\n"
        f"{suffix}",
        parse_mode="Markdown"
    )

@ensure_group
async def cmd_siralama(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT name, boy FROM users WHERE chat_id=%s AND registered=1 ORDER BY boy DESC LIMIT 25",
                    (cid,)
                )
                rows = cur.fetchall()
        finally:
            conn.close()
    medals = ["🥇", "🥈", "🥉"]
    lines  = ["🏆 *Grup Penis Boyu Sıralaması:* 📊\n"]
    for i, row in enumerate(rows):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {row['name'] or 'Bilinmeyen'} — {row['boy']} cm")
    lines.append("\nKimin borusu ne kadar öttü bakalım 😎🍆")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

@ensure_group
async def cmd_yt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid  = str(update.effective_chat.id)
    uid  = str(update.effective_user.id)
    name = get_name(update.effective_user)
    if not ctx.args:
        await update.message.reply_text("❗ Kullanım: `/yt <miktar>` veya `/yt all`", parse_mode="Markdown")
        return
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, cid, uid)
        finally:
            conn.close()
    if not is_registered(u):
        await update.message.reply_text("❗ Daha kaydın yok, önce `/uzat` kullan!", parse_mode="Markdown")
        return
    arg = ctx.args[0].lower()
    if arg == "all":
        bahis = u["boy"]
    else:
        try:
            bahis = int(arg)
        except ValueError:
            await update.message.reply_text("❗ Kullanım: `/yt <miktar>` veya `/yt all`", parse_mode="Markdown")
            return
    if bahis <= 0 or bahis > u["boy"]:
        await update.message.reply_text(
            f"❗ Yetersiz/geçersiz bahis. Boyun: *{u['boy']} cm*", parse_mode="Markdown"
        )
        return
    keyboard = [[
        InlineKeyboardButton("🟡 YAZI", callback_data=f"yt|yazi|{uid}|{bahis}"),
        InlineKeyboardButton("🦅 TURA", callback_data=f"yt|tura|{uid}|{bahis}")
    ]]
    sent = await update.message.reply_text(
        f"🪙 *YAZI TURA BAŞLADI!*\n"
        f"👤 *{name}*\n"
        f"🍆 Bahis: *{bahis} cm*\n"
        f"⏳ 20 saniye içinde seç!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
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
            await ctx.bot.delete_message(chat_id=int(cid), message_id=mid)
        except Exception:
            pass
        try:
            await ctx.bot.send_message(
                chat_id=int(cid),
                text=f"⚠️ *{name}*, seçim yapmadığın için bahis iptal! 💤",
                parse_mode="Markdown"
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
    await query.edit_message_text(
        f"🪙 Para havada...\nSeçimin: *{secim}*",
        parse_mode="Markdown"
    )
    await asyncio.sleep(random.randint(2, 3))
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, cid, caller_uid)
                condom_active = bool(
                    u.get("condom_active_until") and
                    now_tr() < datetime.fromisoformat(u["condom_active_until"])
                )
                if bahis > u["boy"]:
                    await query.edit_message_text("❗ Oyun sırasında boyun değişti, bahis iptal!")
                    return
                sans    = 0.65 if condom_active else 0.50
                kazandi = random.random() < sans
                if kazandi:
                    kazanc   = bahis * 2
                    u["boy"] += kazanc
                    condom_str = f"\n🛡️ Condom etkisi: şans *%{int(sans*100)}*" if condom_active else ""
                    msg = (
                        f"🎉 *KAZANDIN!*\n"
                        f"🎲 Gelen: *{secim}*\n"
                        f"🎁 Kazanç: *+{kazanc} cm*\n"
                        f"📏 Yeni Boy: *{u['boy']} cm*"
                        f"{condom_str}"
                    )
                else:
                    gelen    = "TURA" if secim == "YAZI" else "YAZI"
                    u["boy"] = max(0, u["boy"] - bahis)
                    alay     = random.choice(KAYBETTI_MESAJLAR)
                    msg = (
                        f"{alay}\n\n"
                        f"❌ *KAYBETTİN!*\n"
                        f"✅ Seçimin: *{secim}*\n"
                        f"🎲 Gelen: *{gelen}*\n"
                        f"📉 Giden: *-{bahis} cm*\n"
                        f"📏 Yeni Boy: *{u['boy']} cm* 🥀"
                    )
                save_user(cur, u)
            conn.commit()
        finally:
            conn.close()
    await query.edit_message_text(msg, parse_mode="Markdown")

@ensure_group
async def cmd_vs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: `/vs <miktar>` veya `/vs @kullanici <miktar>`", parse_mode="Markdown")
        return
    if not ctx.args:
        await msg.reply_text("❗ Kullanım: `/vs <miktar>` veya `/vs @kullanici <miktar>`", parse_mode="Markdown")
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
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, cid, uid)
                t = get_user_row(cur, cid, tid)
        finally:
            conn.close()
    arg = ctx.args[0].lower()
    if arg == "all":
        bahis = u["boy"]
    else:
        try:
            bahis = int(arg)
        except ValueError:
            await msg.reply_text("❗ Kullanım: `/vs <miktar>` veya `/vs @kullanici <miktar>`", parse_mode="Markdown")
            return
    if not is_registered(u):
        await msg.reply_text("❗ Daha kaydın yok, önce `/uzat` kullan!", parse_mode="Markdown")
        return
    if not is_registered(t):
        await msg.reply_text("❗ Rakip kayıtlı değil.")
        return
    if bahis <= 0 or bahis > u["boy"]:
        await msg.reply_text(f"❗ Yetersiz/geçersiz bahis. Boyun: *{u['boy']} cm*", parse_mode="Markdown")
        return
    if bahis > t["boy"]:
        await msg.reply_text(f"❗ Rakibin yeterli boyu yok! Mevcut: *{t['boy']} cm*", parse_mode="Markdown")
        return
    challenger_name = get_name(update.effective_user)
    target_name     = get_name(target_user)
    keyboard = [[
        InlineKeyboardButton("🍌 KABUL", callback_data=f"vs|kabul|{uid}|{tid}|{bahis}"),
        InlineKeyboardButton("🙅 KAÇ",   callback_data=f"vs|kac|{uid}|{tid}|{bahis}")
    ]]
    sent = await msg.reply_text(
        f"⚔️ *VS BAŞLADI!*\n\n"
        f"🗡️ Meydan okuyan: *{challenger_name}*\n"
        f"🛡️ Rakip: *{target_name}*\n"
        f"🍆 Bahis: *{bahis} cm*\n\n"
        f"⏳ 20 saniye içinde cevap ver!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
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
            await ctx.bot.delete_message(chat_id=int(cid), message_id=mid)
        except Exception:
            pass
        try:
            await ctx.bot.send_message(
                chat_id=int(cid),
                text=f"⚠️ *{target_name}* cevap vermedi, VS iptal. 🐔",
                parse_mode="Markdown"
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
        try:
            await query.edit_message_text(
                f"❌ *{target_name}* kaçtı. VS iptal!",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        return
    try:
        await query.edit_message_text(
            "✅ *VS kabul edildi!* Sonuç hesaplanıyor...",
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await asyncio.sleep(random.randint(2, 3))
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, cid, challenger_uid)
                t = get_user_row(cur, cid, target_uid)
                condom_u = bool(u.get("condom_active_until") and now_tr() < datetime.fromisoformat(u["condom_active_until"]))
                condom_t = bool(t.get("condom_active_until") and now_tr() < datetime.fromisoformat(t["condom_active_until"]))
                u_chance = max(0.1, min(0.9, 0.50 + (0.075 if condom_u else 0) - (0.075 if condom_t else 0)))
                t_chance = 1 - u_chance
                if bahis > u["boy"] or bahis > t["boy"]:
                    await ctx.bot.send_message(chat_id=int(cid), text="❗ Düello sırasında boy değişti, VS iptal!")
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
                save_user(cur, u)
                save_user(cur, t)
            conn.commit()
        finally:
            conn.close()
    condom_line = ""
    if condom_u or condom_t:
        u_pct = int(u_chance * 100)
        t_pct = int(t_chance * 100)
        condom_line = f"\n🛡️ Condom etkisi: meydan okuyan şansı *%{u_pct}* — rakip şansı *%{t_pct}*"
    await ctx.bot.send_message(
        chat_id=int(cid),
        text=(
            f"💦 *VS SONUCU!*\n\n"
            f"👑 Kazanan: *{winner_name}* (+{bahis} cm)\n"
            f"🤕 Kaybeden: *{loser_name}* (-{bahis} cm)\n\n"
            f"📏 {challenger_name}: *{u_boy} cm*\n"
            f"🤏 {target_name}: *{t_boy} cm*"
            f"{condom_line}"
        ),
        parse_mode="Markdown"
    )

@ensure_group
async def cmd_condom(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = now_tr()
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u              = get_user_row(cur, update.effective_chat.id, update.effective_user.id)
                active_until   = datetime.fromisoformat(u["condom_active_until"])   if u.get("condom_active_until")   else None
                cooldown_until = datetime.fromisoformat(u["condom_cooldown_until"]) if u.get("condom_cooldown_until") else None
                condom_active  = bool(active_until   and now < active_until)
                in_cooldown    = bool(cooldown_until and now < cooldown_until)
                if condom_active or in_cooldown:
                    aktif_str = "Evet ✅" if condom_active else "Hayır ❌"
                    def fmt_remain(dt):
                        if dt is None or now >= dt:
                            return "Bitti"
                        secs = int((dt - now).total_seconds())
                        y,  rem = divmod(secs, 365*24*3600)
                        mo, rem = divmod(rem,  30*24*3600)
                        d,  rem = divmod(rem,  24*3600)
                        h,  rem = divmod(rem,  3600)
                        m,  s   = divmod(rem,  60)
                        parts = []
                        if y:  parts.append(f"{y} yıl")
                        if mo: parts.append(f"{mo} ay")
                        if d:  parts.append(f"{d} gün")
                        if h:  parts.append(f"{h} saat")
                        if m:  parts.append(f"{m} dakika")
                        if s:  parts.append(f"{s} saniye")
                        return " ".join(parts) if parts else "0 saniye"
                    au_mono = active_until.strftime("`%Y-%m-%d %H:%M:%S`")   if active_until   else "`-`"
                    cu_mono = cooldown_until.strftime("`%Y-%m-%d %H:%M:%S`") if cooldown_until else "`-`"
                    await update.message.reply_text(
                        f"*⏳ Condom bekleme süresinde!*\n\n"
                        f"🛡️ Şu an aktif mi: *{aktif_str}*\n"
                        f"⌛ Tekrar kullanım için kalan: *{fmt_remain(cooldown_until)}*\n"
                        f"🕒 Aktiflik bitişi: {au_mono}\n"
                        f"🔁 Cooldown bitişi: {cu_mono}",
                        parse_mode="Markdown"
                    )
                    return
                new_active                 = now + timedelta(minutes=15)
                new_cooldown               = now + timedelta(hours=2)
                u["condom_active_until"]   = new_active.isoformat()
                u["condom_cooldown_until"] = new_cooldown.isoformat()
                save_user(cur, u)
            conn.commit()
        finally:
            conn.close()
    active_end_str = (now + timedelta(minutes=15)).strftime("`%Y-%m-%d %H:%M:%S`")
    await update.message.reply_text(
        f"*🛡️ CONDOM TAKILDI!*\n\n"
        f"🎲 15 dakika boyunca şansın arttı.\n"
        f"🪙 YT: *+%15.0 şans*\n"
        f"⚔️ VS: *+%7.5 avantaj*\n"
        f"🃏 BK: *+%15 şans*\n"
        f"🎰 Slot: *+%15 şans*\n"
        f"🔁 Tekrar kullanım: *2 saat sonra*\n"
        f"🕒 Aktiflik bitişi: {active_end_str}",
        parse_mode="Markdown"
    )

@ensure_group
async def cmd_bk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid  = str(update.effective_chat.id)
    uid  = str(update.effective_user.id)
    name = get_name(update.effective_user)
    if not ctx.args:
        await update.message.reply_text("❗ Kullanım: `/bk <miktar>` veya `/bk all`", parse_mode="Markdown")
        return
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, cid, uid)
        finally:
            conn.close()
    if not is_registered(u):
        await update.message.reply_text("❗ Daha kaydın yok, önce `/uzat` kullan!", parse_mode="Markdown")
        return
    arg = ctx.args[0].lower()
    if arg == "all":
        bahis = u["boy"]
    else:
        try:
            bahis = int(arg)
        except ValueError:
            await update.message.reply_text("❗ Kullanım: `/bk <miktar>` veya `/bk all`", parse_mode="Markdown")
            return
    if bahis <= 0 or bahis > u["boy"]:
        await update.message.reply_text(
            f"❗ Yetersiz/geçersiz bahis. Boyun: *{u['boy']} cm*", parse_mode="Markdown"
        )
        return
    keyboard = [[
        InlineKeyboardButton("1🥤", callback_data=f"bk|1|{uid}|{bahis}"),
        InlineKeyboardButton("2🥤", callback_data=f"bk|2|{uid}|{bahis}"),
        InlineKeyboardButton("3🥤", callback_data=f"bk|3|{uid}|{bahis}"),
    ]]
    sent = await update.message.reply_text(
        f"🃏 *BUL KARAYI BAŞLADI!*\n"
        f"👤 *{name}*\n"
        f"🍆 Bahis: *{bahis} cm*\n"
        f"⏳ 20 saniye süren var!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    key = f"{cid}_{sent.message_id}"
    ctx.bot_data.setdefault("pending_bk", {})[key] = {
        "uid": uid, "cid": cid, "bahis": bahis, "name": name, "done": False
    }
    ctx.job_queue.run_once(
        bk_timeout, 20,
        data={"cid": cid, "mid": sent.message_id, "name": name},
        chat_id=int(cid), name=f"bk_{key}"
    )

async def bk_timeout(ctx: ContextTypes.DEFAULT_TYPE):
    data           = ctx.job.data
    cid, mid, name = data["cid"], data["mid"], data["name"]
    key            = f"{cid}_{mid}"
    bks            = ctx.bot_data.get("pending_bk", {})
    if key in bks and not bks[key].get("done"):
        bks[key]["done"] = True
        try:
            await ctx.bot.delete_message(chat_id=int(cid), message_id=mid)
        except Exception:
            pass
        try:
            await ctx.bot.send_message(
                chat_id=int(cid),
                text=f"⚠️ *{name}*, 20 saniye içinde seçim yapmadığın için bahis iptal! 💤",
                parse_mode="Markdown"
            )
        except Exception:
            pass

async def bk_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query      = update.callback_query
    parts      = query.data.split("|")
    secim      = int(parts[1])
    bet_uid    = parts[2]
    bahis      = int(parts[3])
    cid        = str(query.message.chat_id)
    mid        = query.message.message_id
    caller_uid = str(query.from_user.id)
    key        = f"{cid}_{mid}"
    if caller_uid != bet_uid:
        await query.answer("🚫 Bu bahis sana ait değil!", show_alert=True)
        return
    async with _bk_lock:
        bks = ctx.bot_data.get("pending_bk", {})
        if key not in bks or bks[key].get("done"):
            await query.answer("⚠️ Bu bahis süresi doldu veya zaten oynandı.", show_alert=True)
            return
        bks[key]["done"] = True
    for job in ctx.job_queue.get_jobs_by_name(f"bk_{key}"):
        job.schedule_removal()
    await query.answer()
    await query.edit_message_text(
        f"🃏 Bardaklar karışıyor...\nSeçimin: *{secim}🥤*",
        parse_mode="Markdown"
    )
    await asyncio.sleep(random.randint(2, 3))
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, cid, caller_uid)
                condom_active = bool(
                    u.get("condom_active_until") and
                    now_tr() < datetime.fromisoformat(u["condom_active_until"])
                )
                if bahis > u["boy"]:
                    await query.edit_message_text("❗ Oyun sırasında boyun değişti, bahis iptal!")
                    return
                sans    = 0.483 if condom_active else 0.333
                kazandi = random.random() < sans
                if kazandi:
                    kart_pos = secim
                else:
                    diger    = [x for x in [1, 2, 3] if x != secim]
                    kart_pos = random.choice(diger)

                def bardak_str(pos):
                    return "| " + " | ".join("🃏" if i == pos else "🥤" for i in [1, 2, 3]) + " |"

                gosterim = bardak_str(kart_pos)
                if kazandi:
                    kazanc   = bahis * 3
                    u["boy"] += kazanc
                    alay      = random.choice(BK_KAZANDI_MESAJLAR)
                    condom_str = f"\n🛡️ Condom etkisi: şans *%{int(sans*100)}*" if condom_active else ""
                    msg = (
                        f"🎉 *TEBRİKLER!*\n"
                        f"{gosterim}\n\n"
                        f"🎁 Kazanç: *+{kazanc} cm*\n"
                        f"📏 Yeni Boy: *{u['boy']} cm*\n\n"
                        f"💬 {alay}"
                        f"{condom_str}"
                    )
                else:
                    u["boy"] = max(0, u["boy"] - bahis)
                    alay     = random.choice(BK_KAYBETTI_MESAJLAR)
                    msg = (
                        f"❌ *YANLIŞ BARDAK!*\n"
                        f"{gosterim}\n\n"
                        f"📉 Giden: *-{bahis} cm*\n"
                        f"📏 Yeni Boy: *{u['boy']} cm*\n\n"
                        f"💬 {alay}"
                    )
                save_user(cur, u)
            conn.commit()
        finally:
            conn.close()
    await query.edit_message_text(msg, parse_mode="Markdown")

@ensure_group
async def cmd_slot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cid  = str(update.effective_chat.id)
    uid  = str(update.effective_user.id)
    name = get_name(update.effective_user)
    if not ctx.args:
        await update.message.reply_text("❗ Kullanım: `/slot <miktar>` veya `/slot all`", parse_mode="Markdown")
        return
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, cid, uid)
        finally:
            conn.close()
    if not is_registered(u):
        await update.message.reply_text("❗ Daha kaydın yok, önce `/uzat` kullan!", parse_mode="Markdown")
        return
    arg = ctx.args[0].lower()
    if arg == "all":
        bahis = int(u["boy"])
    else:
        try:
            bahis = int(arg)
        except ValueError:
            await update.message.reply_text("❗ Kullanım: `/slot <miktar>` veya `/slot all`", parse_mode="Markdown")
            return
    if bahis <= 0 or bahis > u["boy"]:
        await update.message.reply_text(
            f"❗ Yetersiz/geçersiz bahis. Boyun: *{u['boy']} cm*", parse_mode="Markdown"
        )
        return
    sent = await update.message.reply_text(
        f"🎰 *SLOT BAŞLIYOR...*\n"
        f"👤 {name}\n"
        f"💰 Bahis: *{bahis} cm*",
        parse_mode="Markdown"
    )
    for i in range(6):
        frame = random_spin()
        try:
            await sent.edit_text(
                f"🎰 *SLOT ÇEVİRİLİYOR...*\n\n"
                f"| {frame[0]} | {frame[1]} | {frame[2]} |\n\n"
                f"👤 {name}\n"
                f"💰 Bahis: *{bahis} cm*",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        await asyncio.sleep(0.4)
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, cid, uid)
                condom_active = bool(
                    u.get("condom_active_until") and
                    now_tr() < datetime.fromisoformat(u["condom_active_until"])
                )
                if bahis > u["boy"]:
                    try:
                        await sent.edit_text("❗ Oyun sırasında boyun değişti, slot iptal!")
                    except Exception:
                        pass
                    return
                r = random.random()
                if condom_active:
                    if r < 0.08:
                        sonuc = "jackpot"
                    elif r < 0.43:
                        sonuc = "x2"
                    else:
                        sonuc = "kayip"
                else:
                    if r < 0.03:
                        sonuc = "jackpot"
                    elif r < 0.23:
                        sonuc = "x2"
                    else:
                        sonuc = "kayip"
                if sonuc == "jackpot":
                    sembol   = random.choice(SLOT_SEMBOLLER)
                    reels    = [sembol, sembol, sembol]
                    kazanc   = bahis * 3
                    u["boy"] += kazanc
                    durum    = "JACKPOT! 🤑 (x4)"
                    degisim  = f"+{kazanc}"
                    alay     = random.choice(SLOT_JACKPOT_MESAJLAR)
                    condom_str = True
                elif sonuc == "x2":
                    sembol   = random.choice(SLOT_SEMBOLLER)
                    diger    = [s for s in SLOT_SEMBOLLER if s != sembol]
                    tek_fark = random.choice(diger)
                    pos      = random.randint(0, 2)
                    reels    = [sembol, sembol, sembol]
                    reels[pos] = tek_fark
                    kazanc   = bahis
                    u["boy"] += kazanc
                    durum    = "GÜZEL! 😎 (x2)"
                    degisim  = f"+{kazanc}"
                    alay     = random.choice(SLOT_X2_MESAJLAR)
                    condom_str = True
                else:
                    s        = random.sample(SLOT_SEMBOLLER, 3)
                    reels    = s
                    ceza     = bahis
                    u["boy"] = max(0, int(u["boy"]) - ceza)
                    durum    = "KAYBETTİN! 🤡"
                    degisim  = f"-{ceza}"
                    alay     = random.choice(SLOT_KAYBETTI_MESAJLAR)
                    condom_str = False
                yeni_boy = u["boy"]
                save_user(cur, u)
            conn.commit()
        finally:
            conn.close()
    reel_str    = f"| {reels[0]} | {reels[1]} | {reels[2]} |"
    condom_line = f"\n🛡️ *Condom etkisi aktifti*" if (condom_active and condom_str) else ""
    result_text = (
        f"🎰 *SLOT SONUCU*\n\n"
        f"👉 {reel_str} 👈\n\n"
        f"🔔 Durum: *{durum}*\n"
        f"📉 Değişim: *{degisim} cm*\n"
        f"📏 Yeni Boy: *{yeni_boy} cm*"
        f"{condom_line}\n\n"
        f"💬 {alay}"
    )
    try:
        await sent.edit_text(result_text, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(result_text, parse_mode="Markdown")

@ensure_group
async def cmd_thief(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text(
            "❗ Kullanım: Birine yanıt verip `/thief` yaz veya `/thief @kullanici` kullan.",
            parse_mode="Markdown"
        )
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
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, cid, uid)
                t = get_user_row(cur, cid, tid)
                if not is_registered(u):
                    await msg.reply_text("❗ Daha kaydın yok, önce `/uzat` kullan!", parse_mode="Markdown")
                    return
                if not is_registered(t):
                    await msg.reply_text("❗ Bu kullanıcı kayıtlı değil.")
                    return
                cur.execute(
                    "SELECT count FROM thief_daily WHERE chat_id=%s AND user_id=%s AND target_id=%s AND date=%s",
                    (cid, uid, tid, today)
                )
                td_row = cur.fetchone()
                count  = td_row["count"] if td_row else 0
                if count >= 3:
                    await msg.reply_text(
                        f"🚫 Bugün bu kişiden zaten *3* *kez* çalmaya çalıştın.\n"
                        f"🕛 UTC+3 saatine göre 00:00'dan sonra tekrar deneyebilirsin.",
                        parse_mode="Markdown"
                    )
                    return
                new_count = count + 1
                cur.execute("""
                    INSERT INTO thief_daily (chat_id, user_id, target_id, count, date)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT(chat_id,user_id,target_id) DO UPDATE SET count=EXCLUDED.count, date=EXCLUDED.date
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
                    save_user(cur, u)
                    save_user(cur, t)
                    reply = (
                        f"🕵️ *HIRSIZLIK BAŞARILI!*\n\n"
                        f"😈 *{my_name}*, {target_name} kişisinin boyundan çaldı!\n"
                        f"🎯 Çalınan oran: *%{oran}*\n"
                        f"🎲 Başarı şansı: *%{basari_sansi}*\n"
                        f"🍆 Çalınan: *+{calinan} cm*\n\n"
                        f"📏 {my_name}: *{eski_u}* → *{u['boy']} cm*\n"
                        f"🤏 {target_name}: *{eski_t}* → *{t['boy']} cm*\n\n"
                        f"🔁 Kalan deneme: *{kalan}*"
                    )
                else:
                    ceza     = max(1, round(u["boy"] * 1 / 100))
                    eski_u   = u["boy"]
                    u["boy"] = max(0, u["boy"] - ceza)
                    save_user(cur, u)
                    reply = (
                        f"🚨 *YAKALANDIN!*\n\n"
                        f"👮 *{my_name}*, {target_name} kişisinden çalmaya çalışırken enselendi!\n"
                        f"🎯 Denenen oran: *%{oran}*\n"
                        f"🎲 Başarı şansı: *%{basari_sansi}*\n"
                        f"📉 Ceza: *-{ceza} cm*\n\n"
                        f"📏 {my_name}: *{eski_u}* → *{u['boy']} cm*\n"
                        f"🛡️ {target_name}: *{t['boy']} cm* ile sağlam kaldı.\n\n"
                        f"🔁 Kalan deneme: *{kalan}*"
                    )
            conn.commit()
        finally:
            conn.close()
    await msg.reply_text(reply, parse_mode="Markdown")

@ensure_group
async def cmd_yolla(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text(
            "❗ Kullanım: Birinin mesajına yanıt verip `/yolla <miktar>` yaz.\nÖrnek: `/yolla 1000`",
            parse_mode="Markdown"
        )
        return
    if not ctx.args:
        await msg.reply_text(
            "❗ Kullanım: Birinin mesajına yanıt verip `/yolla <miktar>` yaz.\nÖrnek: `/yolla 1000`",
            parse_mode="Markdown"
        )
        return
    try:
        miktar = int(ctx.args[0])
    except ValueError:
        await msg.reply_text("❗ Geçerli bir miktar gir.")
        return
    if miktar <= 0:
        await msg.reply_text("❗ En az *1 cm* yollamalısın.", parse_mode="Markdown")
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
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u = get_user_row(cur, cid, uid)
                t = get_user_row(cur, cid, tid)
                if not is_registered(u):
                    await msg.reply_text("❗ Daha kaydın yok, önce `/uzat` kullan!", parse_mode="Markdown")
                    return
                if not is_registered(t):
                    await msg.reply_text("❗ Bu kullanıcı kayıtlı değil.")
                    return
                if u.get("yolla_total_date") != today:
                    u["yolla_total"]      = 0
                    u["yolla_total_date"] = today
                    cur.execute("DELETE FROM yolla_daily WHERE chat_id=%s AND user_id=%s", (cid, uid))
                if u["yolla_total"] >= 5:
                    await msg.reply_text("🚫 Bugünkü 5 gönderim hakkını doldurdun!")
                    return
                cur.execute(
                    "SELECT count FROM yolla_daily WHERE chat_id=%s AND user_id=%s AND target_id=%s AND date=%s",
                    (cid, uid, tid, today)
                )
                yd_row          = cur.fetchone()
                count_to_target = yd_row["count"] if yd_row else 0
                if count_to_target >= 3:
                    await msg.reply_text(
                        f"🚫 Bugün *{get_name(target_user)}* kişisine zaten 3 kez yolladın.",
                        parse_mode="Markdown"
                    )
                    return
                if miktar > u["boy"]:
                    await msg.reply_text(
                        f"❗ Yeterli boyun yok! Mevcut: *{u['boy']} cm*", parse_mode="Markdown"
                    )
                    return
                eski_u, eski_t        = u["boy"], t["boy"]
                u["boy"]             -= miktar
                t["boy"]             += miktar
                u["yolla_total"]     += 1
                new_yd_count          = count_to_target + 1
                cur.execute("""
                    INSERT INTO yolla_daily (chat_id, user_id, target_id, count, date)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT(chat_id,user_id,target_id) DO UPDATE SET count=EXCLUDED.count, date=EXCLUDED.date
                """, (cid, uid, tid, new_yd_count, today))
                my_name      = get_name(update.effective_user)
                target_name  = get_name(target_user)
                toplam_kalan = 5 - u["yolla_total"]
                kisi_kalan   = 3 - new_yd_count
                u_boy, t_boy = u["boy"], t["boy"]
                save_user(cur, u)
                save_user(cur, t)
            conn.commit()
        finally:
            conn.close()
    await msg.reply_text(
        f"🎁 *PENİS BOYU TRANSFERİ BAŞARILI!*\n\n"
        f"📤 Gönderen: *{my_name}*\n"
        f"📥 Alan: *{target_name}*\n"
        f"🍆 Yollanan: *{miktar} cm*\n\n"
        f"📉 {my_name}: *{eski_u}* → *{u_boy} cm*\n"
        f"📈 {target_name}: *{eski_t}* → *{t_boy} cm*\n\n"
        f"🔁 Bugünkü toplam yollama hakkın: *{toplam_kalan}*\n"
        f"👤 Bu kişiye kalan yollama hakkın: *{kisi_kalan}*",
        parse_mode="Markdown"
    )

KALDIRMALAR = [
    "{hedef} kaval çalmıyor ama {caller}'ın kobra sepeti deldi geçti! 🐍",
    "{caller} 'selam' dedi, {hedef} vitesi 5'e taktı! 🚘",
    "{caller} mesajı attı, {hedef} eti masaya vurdu! 🥩",
    "{hedef} gruba girdi, {caller} çadırı kurdu! ⛺",
    "{caller} öyle bir çekti ki, {hedef}'ın demir çubuk kilitlendi! 🧲",
    "SON DAKİKA: {caller}'ın mesajından sonra {hedef}'ın malı 8.5 şiddetinde vurdu! 🚨",
    "{caller} lafı koydu, {hedef} kılıcı çekti! ⚔️",
    "{caller} ortamı yaktı, {hedef}'ın hortumu basmaya hazır! 🚒",
]

INDIRMELER = [
    "🐳 {hedef} öyle bir bruh anı yaşattı ki, {caller}'ın container'ı patladı!",
    "🥶 {caller}'ın yazdığını gören {hedef}'ın malı içine kaçtı!",
    "🏗️ {caller} ortama girince {hedef}'ın her şeyi döküldü!",
    "🤡 {caller}'ın bu halleri {hedef}'ın hevesini kursağında bıraktı!",
    "💻 {caller}'ın boş muhabbeti {hedef}'ın sunucusuna DDOS attı!",
    "📉 {caller}'ın aurası {hedef}'ın değerini sıfırladı!",
    "🗿 {caller}'ın vizyonsuzluğu {hedef}'ı taşa çevirdi!",
]

@ensure_group
async def cmd_kaldir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip `/kaldir` yaz.", parse_mode="Markdown")
        return
    caller = get_name(update.effective_user)
    hedef  = get_name(msg.reply_to_message.from_user)
    await msg.reply_text(random.choice(KALDIRMALAR).format(caller=caller, hedef=hedef))

@ensure_group
async def cmd_indir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip `/indir` yaz.", parse_mode="Markdown")
        return
    caller = get_name(update.effective_user)
    hedef  = get_name(msg.reply_to_message.from_user)
    await msg.reply_text(random.choice(INDIRMELER).format(caller=caller, hedef=hedef))

@ensure_group
async def cmd_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("❗ Kullanım: `/promo <kod>`", parse_mode="Markdown")
        return
    kod = ctx.args[0].upper()
    uid = str(update.effective_user.id)
    cid = str(update.effective_chat.id)
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM promos WHERE kod=%s", (kod,))
                promo = cur.fetchone()
                if not promo:
                    await update.message.reply_text("❌ Geçersiz kod!")
                    return
                promo = dict(promo)
                if now_tr() > datetime.fromisoformat(promo["expires"]):
                    await update.message.reply_text("❌ Bu kodun süresi dolmuş!")
                    return
                # Bu grupta bu kullanıcı daha önce kullandı mı?
                cur.execute(
                    "SELECT 1 FROM promo_used WHERE kod=%s AND user_id=%s AND chat_id=%s",
                    (kod, uid, cid)
                )
                if cur.fetchone():
                    await update.message.reply_text("❌ Bu kodu bu grupta zaten kullandın!")
                    return
                u               = get_user_row(cur, cid, uid)
                miktar          = promo["miktar"]
                eski            = u["boy"]
                u["boy"]       += miktar
                u["registered"] = 1
                save_user(cur, u)
                cur.execute(
                    "INSERT INTO promo_used (kod, user_id, chat_id) VALUES (%s,%s,%s)",
                    (kod, uid, cid)
                )
            conn.commit()
        finally:
            conn.close()
    await update.message.reply_text(
        f"🎉 *PROMO AKTİF!*\n\n"
        f"📏 Eklenen: *+{miktar} cm*\n"
        f"📊 Eski: *{eski} cm*\n"
        f"🔥 Yeni: *{u['boy']} cm*",
        parse_mode="Markdown"
    )

async def cmd_ozelpromokod(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    if len(ctx.args) < 3:
        await update.message.reply_text("❗ Kullanım: `/ozelpromokod <KOD> <miktar> <gün>`", parse_mode="Markdown")
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
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO promos (kod, miktar, expires) VALUES (%s,%s,%s) ON CONFLICT(kod) DO UPDATE SET miktar=EXCLUDED.miktar, expires=EXCLUDED.expires",
                    (kod, miktar, expires)
                )
            conn.commit()
        finally:
            conn.close()
    await update.message.reply_text(
        f"✅ *PROMOKOD OLUŞTURULDU!*\n\n"
        f"🎟️ KOD: `{kod}`\n"
        f"💰 MİKTAR: *{miktar} cm*\n"
        f"📅 SÜRE: *{gun} gün*",
        parse_mode="Markdown"
    )

async def cmd_promokodolustur(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    if len(ctx.args) < 2:
        await update.message.reply_text("❗ Kullanım: `/promokodolustur <miktar> <gün>`", parse_mode="Markdown")
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
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO promos (kod, miktar, expires) VALUES (%s,%s,%s) ON CONFLICT(kod) DO UPDATE SET miktar=EXCLUDED.miktar, expires=EXCLUDED.expires",
                    (kod, miktar, expires)
                )
            conn.commit()
        finally:
            conn.close()
    await update.message.reply_text(
        f"✅ *RASTGELE PROMOKOD OLUŞTURULDU!*\n\n"
        f"🎟️ KOD: `{kod}`\n"
        f"💰 MİKTAR: *{miktar} cm*\n"
        f"📅 SÜRE: *{gun} gün*",
        parse_mode="Markdown"
    )

async def cmd_istatistik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT COUNT(DISTINCT chat_id) as grups, COUNT(*) as users, SUM(boy) as total_boy FROM users WHERE registered=1")
                row = cur.fetchone()
                cur.execute("SELECT COUNT(*) as c FROM promos")
                promo_count = cur.fetchone()["c"]
        finally:
            conn.close()
    total   = row["total_boy"] or 0
    users   = row["users"]     or 0
    grups   = row["grups"]     or 0
    ort_boy = round(total / users) if users > 0 else 0
    await update.message.reply_text(
        f"📊 *BOT İSTATİSTİKLERİ*\n\n"
        f"👥 Toplam grup: *{grups}*\n"
        f"👤 Toplam kayıtlı kullanıcı: *{users}*\n"
        f"🍆 Toplam boy: *{total} cm*\n"
        f"📏 Ortalama boy: *{ort_boy} cm*\n"
        f"🎟️ Promo kod sayısı: *{promo_count}*",
        parse_mode="Markdown"
    )

async def cmd_disistatistik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT chat_id, name, boy FROM users WHERE registered=1 ORDER BY chat_id, boy DESC")
                rows = cur.fetchall()
        finally:
            conn.close()
    groups = {}
    for row in rows:
        groups.setdefault(row["chat_id"], []).append(row)
    lines = ["📈 *DETAYLI İSTATİSTİKLER*\n"]
    for cid, users in groups.items():
        lines.append(f"🏠 Grup: `{cid}` — *{len(users)} kişi*")
        for i, u in enumerate(users[:5]):
            lines.append(f"  {i+1}. {u['name'] or 'Bilinmeyen'} — *{u['boy']} cm*")
        lines.append("")
    if len(lines) == 1:
        lines.append("Henüz veri yok.")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_degistir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid_caller = str(update.effective_user.id)
    is_admin   = (update.effective_user.id == ADMIN_ID)
    if not is_admin:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM prohere_users WHERE user_id=%s", (uid_caller,))
                allowed = cur.fetchone() is not None
        finally:
            conn.close()
        if not allowed:
            await update.message.reply_text("🚫 Bu komutu kullanmaya erişimin yok.")
            return
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip `/degistir <miktar>` yaz.", parse_mode="Markdown")
        return
    if not ctx.args:
        await msg.reply_text("❗ Kullanım: `/degistir <miktar>`", parse_mode="Markdown")
        return
    val       = ctx.args[0]
    check_val = val.lstrip("-")
    if not check_val.isdigit():
        await msg.reply_text("❗ Geçerli bir sayı gir.")
        return
    if len(check_val) > 25:
        await msg.reply_text("❗ En fazla 25 basamaklı sayı girebilirsin.")
        return
    try:
        miktar = int(val)
    except ValueError:
        await msg.reply_text("❗ Geçerli bir sayı gir.")
        return
    target_user = msg.reply_to_message.from_user
    cid         = str(update.effective_chat.id)
    tid         = str(target_user.id)
    name        = get_name(target_user)
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                u               = get_user_row(cur, cid, tid)
                u["boy"]        = miktar
                u["registered"] = 1
                u["name"]       = name
                save_user(cur, u)
            conn.commit()
        finally:
            conn.close()
    await msg.reply_text(f"✅ *{name}* artık *{miktar} cm*!", parse_mode="Markdown")

async def cmd_prohere(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip `/prohere` yaz.", parse_mode="Markdown")
        return
    target_user = msg.reply_to_message.from_user
    tid         = str(target_user.id)
    name        = get_name(target_user)
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO prohere_users (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (tid,)
                )
            conn.commit()
        finally:
            conn.close()
    await msg.reply_text(
        f"✅ *{name}* artık bu grupta yetkili!\n"
        f"🛡️ Artık `/degistir` komutunu kullanabilir.",
        parse_mode="Markdown"
    )

async def cmd_unprohere(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text("❗ Kullanım: Birine yanıt verip `/unprohere` yaz.", parse_mode="Markdown")
        return
    target_user = msg.reply_to_message.from_user
    tid         = str(target_user.id)
    name        = get_name(target_user)
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM prohere_users WHERE user_id=%s", (tid,))
                deleted = cur.rowcount
            conn.commit()
        finally:
            conn.close()
    if deleted:
        await msg.reply_text(f"🚫 *{name}* artık yetkili değil!", parse_mode="Markdown")
    else:
        await msg.reply_text(f"⚠️ *{name}* zaten yetkili değildi!", parse_mode="Markdown")

async def cmd_gruplar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT u.chat_id, COALESCE(NULLIF(c.title, ''), '?') as title
                    FROM (SELECT DISTINCT chat_id FROM users) u
                    LEFT JOIN chats c ON c.chat_id = u.chat_id
                    ORDER BY u.chat_id
                """)
                rows = cur.fetchall()
        finally:
            conn.close()
    if not rows:
        await update.message.reply_text("📭 Henüz hiçbir gruba eklenmemişim.")
        return
    lines = [f"📋 *Bot'un bulunduğu gruplar:* ({len(rows)} grup)\n"]
    for i, row in enumerate(rows, 1):
        lines.append(f"{i}. *{row['title']}*\n   `{row['chat_id']}`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_duyuru(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Bu komuta erişim izniniz yok.")
        return
    if not ctx.args:
        await update.message.reply_text("❗ Kullanım: `/duyuru <mesaj>`", parse_mode="Markdown")
        return
    mesaj = " ".join(ctx.args)
    async with _db_lock:
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT DISTINCT chat_id FROM users")
                rows = cur.fetchall()
        finally:
            conn.close()
    if not rows:
        await update.message.reply_text("📭 Henüz hiçbir gruba eklenmemişim.")
        return
    basarili  = 0
    basarisiz = 0
    for row in rows:
        try:
            await ctx.bot.send_message(
                chat_id=int(row["chat_id"]),
                text=f"📢 *DUYURU*\n\n{mesaj}",
                parse_mode="Markdown"
            )
            basarili += 1
        except Exception:
            basarisiz += 1
    await update.message.reply_text(
        f"✅ Duyuru gönderildi!\n\n"
        f"📨 Başarılı: *{basarili}* grup\n"
        f"❌ Başarısız: *{basarisiz}* grup",
        parse_mode="Markdown"
    )

async def cache_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_chat.type == "private":
        return
    cid   = str(update.effective_chat.id)
    uid   = str(update.effective_user.id)
    name  = get_name(update.effective_user)
    title = update.effective_chat.title or ""
    now_ts = now_tr().timestamp()
    if now_ts - ctx.bot_data.get("last_name_save", 0) > 60:
        ctx.bot_data["last_name_save"] = now_ts
        async with _db_lock:
            conn = get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (chat_id, user_id, name) VALUES (%s,%s,%s)
                        ON CONFLICT(chat_id,user_id) DO UPDATE SET name=EXCLUDED.name
                    """, (cid, uid, name))
                    cur.execute("""
                        INSERT INTO chats (chat_id, title) VALUES (%s,%s)
                        ON CONFLICT(chat_id) DO UPDATE SET title=EXCLUDED.title
                    """, (cid, title))
                conn.commit()
            finally:
                conn.close()

async def post_init(app: Application):
    init_db()
    commands = [
        BotCommand("uzat",      "Penis boyunu uzat"),
        BotCommand("siralama",  "Grup Penis Sıralaması"),
        BotCommand("boyum",     "Penis Boyun"),
        BotCommand("condom",    "Şans Arttırıcı Condom"),
        BotCommand("boyu",      "Seçilen Kişinin Penis boyu"),
        BotCommand("help",      "Yardım Komutu"),
        BotCommand("yt",        "Yazı Tura Oyunu"),
        BotCommand("bk",        "Bul Karayı Oyunu"),
        BotCommand("slot",      "Slot Makinesi Oyunu"),
        BotCommand("thief",     "Seçilen Kişiden Penis Çal"),
        BotCommand("promo",     "Promo Kodu Kullan"),
        BotCommand("kaldir",    "Seçilen Kişiye Penis Kaldır"),
        BotCommand("indir",     "Seçilen Kişiye Penis İndir"),
        BotCommand("yolla",     "Boy gönder"),
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
    app.add_handler(CommandHandler("bk",              cmd_bk))
    app.add_handler(CommandHandler("slot",            cmd_slot))
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
    app.add_handler(CommandHandler("prohere",         cmd_prohere))
    app.add_handler(CommandHandler("unprohere",       cmd_unprohere))
    app.add_handler(CommandHandler("gruplar",         cmd_gruplar))
    app.add_handler(CommandHandler("duyuru",          cmd_duyuru))
    app.add_handler(CallbackQueryHandler(yt_callback, pattern=r"^yt\|"))
    app.add_handler(CallbackQueryHandler(vs_callback, pattern=r"^vs\|"))
    app.add_handler(CallbackQueryHandler(bk_callback, pattern=r"^bk\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, cache_name))
    print("Bot başladı...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
