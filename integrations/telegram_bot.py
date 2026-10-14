import asyncio
import datetime
import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

try:
    import winreg
except ImportError:
    winreg = None

# Nastavení kořenového adresáře do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Načtení proměnných z .env a registrů
load_dotenv()

from core.scraper import JobsScraper
from core.analyzer import JobAnalyzer
from core.generator import CoverLetterGenerator
from integrations.email_handler import EmailHandler


def get_env_var(name: str) -> str:
    val = os.environ.get(name)
    if not val and winreg:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
            val, _ = winreg.QueryValueEx(key, name)
            os.environ[name] = val
        except Exception:
            pass
    return val or ""


TELEGRAM_BOT_TOKEN = get_env_var("JOBS_TELEGRAM_BOT_TOKEN") or get_env_var("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = get_env_var("TELEGRAM_USER_ID")
JOBS_GROUP_CHAT_ID = int(get_env_var("JOBS_GROUP_CHAT_ID")) if get_env_var("JOBS_GROUP_CHAT_ID") else None
JOBS_THREAD_ID = int(get_env_var("JOBS_THREAD_ID")) if get_env_var("JOBS_THREAD_ID") else None

def get_candidate_profile() -> dict:
    for p in [Path("config/profile.json"), Path("config/profile.example.json")]:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f).get("candidate", {})
            except Exception:
                pass
    return {}

scraper = JobsScraper()
analyzer = JobAnalyzer()
generator = CoverLetterGenerator()
email_handler = EmailHandler()

PENDING_JOBS_FILE = Path("data/pending_jobs.json")


def load_pending_jobs() -> dict:
    if PENDING_JOBS_FILE.exists():
        try:
            with open(PENDING_JOBS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_pending_jobs(jobs: dict):
    PENDING_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def load_history() -> set:
    history_file = Path("data/history.json")
    history_file.parent.mkdir(parents=True, exist_ok=True)
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_history(history: set):
    history_file = Path("data/history.json")
    history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(list(history), f, ensure_ascii=False, indent=2)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 *Ahoj Oldo! Jsem tvůj Jobs.cz Asistent.*\n\n"
        "🔒 *Bezpečnost a soukromí:* Čtu pouze poštu týkající se náboru a NIKDY neodešlu žádný e-mail bez tvého kliknutí na schválení.\n\n"
        "🛠️ *Co umím:*\n"
        "• ☕ **Ranní přehled v 9:00:** Vytřídí nové nabídky a pošle ti seznam s tlačítky pro rychlé vygenerování dopisu na 1 kliknutí.\n"
        "• ⚡ **Okamžitá pozvánka na pohovor:** Jakmile personalista napíše, připravím návrh odpovědi k potvrzení.\n"
        "• 💬 **Interaktivní úpravy:** Můžeš mi k jakémukoliv dopisu napsat připomínky (např. *„zkrať to“*, *„navrhni jiný termín“*).\n"
        "• `/digest` – okamžité spuštění ranního přehledu nabídek s tlačítky\n"
        "• `/check_email` – okamžitá kontrola e-mailu\n"
        "• `/demo` – ukázkový rozbor nabídky"
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)


async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spustí přehled nabídek s tlačítky na vygenerování dopisů."""
    status_msg = await update.message.reply_text("🔍 *Prohledávám nové nabídky práce z Jobs.cz...*", parse_mode=ParseMode.MARKDOWN)
    chat_id = update.effective_chat.id
    await run_digest_flow(context.bot, chat_id, status_msg)


async def run_digest_flow(bot, chat_id: int, status_msg=None, thread_id: int = None):
    history = load_history()
    pending_jobs = load_pending_jobs()

    keywords = ["marketing", "analytik", "ekonomika", "administrativa"]
    links = scraper.fetch_live_search_jobs(keywords=keywords, location="praha")

    new_offers = []
    for link in links:
        if link in history:
            continue

        try:
            posting = scraper.fetch_from_url(link)
            analysis = analyzer.analyze(posting)
            fit_score = analysis.get("fit_score", 0)

            # Posíláme nabídky se shodou nad 45 % (roztříděné na vhodné vs méně vhodné)
            if fit_score >= 45:
                job_id = f"job_{len(pending_jobs) + 1}"
                pending_jobs[job_id] = {
                    "url": posting.url,
                    "title": posting.title,
                    "company": posting.company,
                    "location": posting.location,
                    "work_type": posting.work_type,
                    "contact_person": posting.contact_person,
                    "raw_text": posting.raw_text,
                    "analysis": analysis,
                }
                new_offers.append((job_id, posting, analysis, fit_score))
                history.add(link)

            if len(new_offers) >= 5:
                break
        except Exception as e:
            print(f"Chyba při parsování {link}: {e}")

    save_history(history)
    save_pending_jobs(pending_jobs)

    if not new_offers:
        msg = "📭 *Žádné nové vhodné nabídky v tuto chvíli nebyly nalezeny.*"
        if status_msg:
            await status_msg.edit_text(msg, parse_mode=ParseMode.MARKDOWN)
        else:
            await bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
        return

    # Seřazení nabídek sestupně podle shody (Fit Score od nejvyššího po nejnižší)
    new_offers.sort(key=lambda x: x[3], reverse=True)

    # Sestavení zprávy přehledu
    digest_lines = [f"☕ *Ranní přehled nových nabídek Jobs.cz ({len(new_offers)} pozic seřazených dle vhodnosti):*\n━━━━━━━━━━━━━━━━━━━━━\n"]
    buttons = []

    for idx, (job_id, posting, analysis, score) in enumerate(new_offers, 1):
        if score >= 80:
            badge = "🟢"
            status_label = "Vhodné pro tebe"
        elif score >= 50:
            badge = "🟡"
            status_label = "Méně vhodné / Vyšší nároky"
        else:
            badge = "🔴"
            status_label = "Seniorní / Nevhodné"

        summary = analysis.get("summary", "")
        digest_lines.append(
            f"{badge} *{idx}. {posting.title}* — `{posting.company}`\n"
            f"📊 Shoda: `{score} %` ({status_label}) | 📍 {posting.location}\n"
            f"📝 {summary}\n"
        )
        btn_label = f"📝 {idx}. Připravit dopis ({score}%)"
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"draft_{job_id}")])

    digest_lines.append("━━━━━━━━━━━━━━━━━━━━━\n💡 _Klepni na tlačítko níže a já ti k vybrané nabídce obratem připravím kompletní průvodní dopis na míru._")

    total_saved_tokens = sum(analysis.get("_toon_savings", {}).get("tokens_saved", 0) for _, _, analysis, _ in new_offers)
    if total_saved_tokens > 0:
        total_saved_czk = sum(analysis.get("_toon_savings", {}).get("saved_czk", 0.0) for _, _, analysis, _ in new_offers)
        digest_lines.append(f"\n💡 *TOON Úspora:* -{total_saved_tokens:,} tok | ~{total_saved_czk:.4f} CZK _(ODHAD – čeká na finální provider invoice)_")

    full_digest_text = "\n".join(digest_lines)
    keyboard = InlineKeyboardMarkup(buttons)

    if status_msg:
        await status_msg.delete()

    await bot.send_message(
        chat_id=chat_id,
        message_thread_id=thread_id,
        text=full_digest_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # 1. Vygenerování dopisu na kliknutí z ranního přehledu
    if data.startswith("draft_"):
        job_id = data.replace("draft_", "")
        pending_jobs = load_pending_jobs()
        job_data = pending_jobs.get(job_id)

        if not job_data:
            await query.message.reply_text("⚠️ Informace o této nabídce již vypršely. Zkus poslat odkaz přímo.")
            return

        from core.scraper import JobPosting
        posting = JobPosting(
            url=job_data.get("url"),
            title=job_data.get("title", "Pozice"),
            company=job_data.get("company", "Společnost"),
            location=job_data.get("location", "Praha"),
            work_type=job_data.get("work_type", "Zkrácený úvazek"),
            contact_person=job_data.get("contact_person"),
            raw_text=job_data.get("raw_text", ""),
        )
        analysis = job_data.get("analysis", {})

        status_msg = await query.message.reply_text(f"✍️ *Generuji personalizovaný průvodní dopis pro {posting.title}...*", parse_mode=ParseMode.MARKDOWN)

        cover_letter = generator.generate_cover_letter(posting, analysis)

        # Uložíme do kontextu pro možnost konverzační úpravy
        context.user_data["last_job"] = posting
        context.user_data["last_letter"] = cover_letter
        context.user_data["last_analysis"] = analysis

        fit_score = analysis.get("fit_score", 0)
        category = analysis.get("category", "Nespecifikováno")
        summary = analysis.get("summary", "")
        responsibilities = analysis.get("responsibilities", [])
        requirements = analysis.get("requirements", [])
        why_it_fits = analysis.get("why_it_fits", [])

        score_badge = "🟢" if fit_score >= 80 else "🟡"
        resp_bullets = "\n".join([f"  • {r}" for r in responsibilities[:3]]) if responsibilities else "  • Neuvedeno"
        req_bullets = "\n".join([f"  • {r}" for r in requirements[:3]]) if requirements else "  • Neuvedeno"
        why_bullets = "\n".join([f"  • {w}" for w in why_it_fits[:3]]) if why_it_fits else "  • Neuvedeno"

        card_text = (
            f"🎯 *{posting.title}*\n"
            f"🏢 *Firma:* `{posting.company}`\n"
            f"📊 *Shoda s profilem:* {score_badge} `{fit_score} %` ({category})\n"
            f"📍 *Lokalita:* {posting.location} | {posting.work_type}\n\n"
            f"🛠️ *NÁPLŇ PRÁCE:*\n{resp_bullets}\n\n"
            f"🎯 *CO OČEKÁVAJÍ:*\n{req_bullets}\n\n"
            f"💡 *PROČ SE K TOBĚ HODÍ:*\n{why_bullets}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"✉️ *PRŮVODNÍ DOPIS (připraven ke zkopírování):*\n\n"
            f"```text\n{cover_letter}\n```\n\n"
            f"💡 _Tip: Pokud chceš dopis změnit, stačí mi napsat (např. „zkrať to“, „zdůrazni Canvu“)._"
        )

        buttons = [
            [InlineKeyboardButton("🚀 Odeslat přihlášku a životopis", callback_data=f"confirm_apply_{job_id}")],
        ]
        if posting.url:
            buttons.append([InlineKeyboardButton("🌐 Otevřít inzerát na Jobs.cz", url=posting.url)])

        keyboard = InlineKeyboardMarkup(buttons)

        await status_msg.delete()
        await query.message.reply_text(
            card_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # 2. Bezpečnostní pop-up potvrzení před odesláním přihlášky
    elif data.startswith("confirm_apply_"):
        job_id = data.replace("confirm_apply_", "")
        pending_jobs = load_pending_jobs()
        job_data = pending_jobs.get(job_id, {})

        title = job_data.get("title", "Group Marketing Specialista")
        company = job_data.get("company", "Ukázková Média, a.s.")
        recruiter = job_data.get("contact_person") or "Tereza Šindelář"

        cand = get_candidate_profile()
        cand_name = cand.get("name", "Uchazeč")
        cand_email = cand.get("email", "your_email@example.com")
        cand_phone = cand.get("phone", "+420 123 456 789")
        cand_cv_name = os.path.basename(cand.get("cv_path") or "zivotopis.pdf")
        cand_cert_name = os.path.basename(cand.get("certificate_c1_path") or "certifikat.pdf")

        confirm_text = (
            f"⚠️ **BEZPEČNOSTNÍ KONTROLA PŘED ODESLÁNÍM**\n\n"
            f"🎯 **Pozice:** {title}\n"
            f"🏢 **Firma:** {company}\n"
            f"👤 **Komu:** {recruiter}\n\n"
            f"📋 **CO BUDE DO FORMULÁŘE JOBS.CZ VLOŽENO:**\n"
            f"  • **Jméno a příjmení:** {cand_name}\n"
            f"  • **E-mail:** `{cand_email}`\n"
            f"  • **Telefon:** `{cand_phone}`\n"
            f"  • **Průvodní dopis:** Vygenerovaný text na míru\n"
            f"  • 📎 **Příloha 1 (Životopis):** `{cand_cv_name}`\n"
            f"  • 📎 **Příloha 2 (Ostatní přílohy):** `{cand_cert_name}`\n\n"
            f"Opravdu si přeješ tuto přihlášku závazně odeslat?"
        )

        confirm_buttons = [
            [InlineKeyboardButton("✅ ANO, závazně odeslat na Jobs.cz", callback_data=f"do_apply_{job_id}")],
            [InlineKeyboardButton("❌ Zrušit / Neodesílat", callback_data="cancel_apply")],
        ]
        await query.message.reply_text(
            confirm_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(confirm_buttons),
        )

    # 3. Zrušení odeslání přihlášky
    elif data == "cancel_apply":
        await query.edit_message_text("❌ **Odeslání přihlášky bylo zrušeno.** Žádný e-mail nebyl odeslán.")

    # 4. Samotné odeslání přihlášky po 100% potvrzení
    elif data.startswith("do_apply_"):
        job_id = data.replace("do_apply_", "")
        pending_jobs = load_pending_jobs()
        job_data = pending_jobs.get(job_id)

        if not job_data:
            await query.edit_message_text("⚠️ Informace o nabídce vypršely.")
            return

        title = job_data.get("title", "Pozice")
        company = job_data.get("company", "Firma")
        raw_text = job_data.get("raw_text", "")
        cand = get_candidate_profile()
        cand_name = cand.get("name", "Uchazeč")
        cv_path = cand.get("cv_path") or "data/sample_cv.pdf"

        # Zjistíme kontaktní e-mail z textu inzerátu, pokud existuje
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", raw_text)
        target_email = email_match.group(0) if email_match else None

        last_letter = context.user_data.get("last_letter", "")

        if target_email:
            try:
                email_handler.send_approved_email(
                    to_email=target_email,
                    subject=f"Reakce na pozici: {title} - {cand_name}",
                    body_text=last_letter,
                    attachment_path=cv_path if os.path.exists(cv_path) else None,
                    sender_name=cand_name,
                )
                from_email, _ = get_gmail_credentials()
                sender_display = from_email or cand.get("email", "e-mailu")
                await query.edit_message_text(
                    f"✅ **PŘIHLÁŠKA ÚSPĚŠNĚ ODESLÁNA!**\n\n"
                    f"🎯 **Pozice:** {title}\n"
                    f"🏢 **Firma:** {company} (`{target_email}`)\n"
                    f"📎 **Příloha:** Životopis v PDF přiložen\n\n"
                    f"Průvodní dopis byl úspěšně doručen z adresy `{sender_display}`.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception as e:
                await query.edit_message_text(f"❌ **Chyba při odesílání e-mailu:**\n`{str(e)}`", parse_mode=ParseMode.MARKDOWN)
        else:
            # Pokud inzerát nemá přímý e-mail, ale formulář na Jobs.cz
            await query.edit_message_text(
                f"ℹ️ **Inzerát vyžaduje odeslání přes formulář Jobs.cz**\n\n"
                f"Tato nabídka ({company}) nemá přímou e-mailovou schránku, ale zpracovává se přes zabezpečený webový formulář Jobs.cz.\n\n"
                f"📋 Průvodní dopis máš vygenerovaný v chatu výše.\n"
                f"🔗 [Klikni zde pro otevření formuláře odpovědi]({job_data.get('url')}) a dopis jednoduše vlož.",
                parse_mode=ParseMode.MARKDOWN,
            )

    # 5. Schválení a odeslání odpovědi na pohovor
    elif data.startswith("send_"):
        reply_id = data.replace("send_", "")
        reply_info = pending_email_replies.get(reply_id)

        if not reply_info:
            await query.edit_message_text("⚠️ Platnost tohoto schválení vypršela.")
            return

        try:
            raw_to = reply_info["to_email"]
            to_match = re.search(r"[\w\.-]+@[\w\.-]+", raw_to)
            target_email = to_match.group(0) if to_match else raw_to

            email_handler.send_approved_email(
                to_email=target_email,
                subject=reply_info["subject"],
                body_text=reply_info["body"],
            )

            await query.edit_message_text(
                f"✅ **E-mail byl úspěšně odeslán!**\n"
                f"🏢 Příjemce: `{target_email}`\n"
                f"📝 Odeslaný text:\n\n```text\n{reply_info['body']}\n```",
                parse_mode=ParseMode.MARKDOWN,
            )
            del pending_email_replies[reply_id]
        except Exception as e:
            await query.edit_message_text(f"❌ **Chyba při odesílání e-mailu:**\n`{str(e)}`", parse_mode=ParseMode.MARKDOWN)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if ALLOWED_USER_ID and user_id != str(ALLOWED_USER_ID):
        await update.message.reply_text("⛔ Nemáte oprávnění k tomuto botovi.")
        return

    # Pokud zpráva přišla ze skupiny, reagovat pouze v nakonfigurované skupině a vlákně
    if update.effective_chat.type in ["group", "supergroup"]:
        if JOBS_GROUP_CHAT_ID and update.effective_chat.id != JOBS_GROUP_CHAT_ID:
            return
        thread_id = getattr(update.message, "message_thread_id", None)
        if JOBS_THREAD_ID and thread_id != JOBS_THREAD_ID:
            return

    text = update.message.text.strip()
    url_match = re.search(r"https?://[^\s]+", text)

    # 1. Úprava odpovědi na pozvánku k pohovoru
    last_reply_id = context.user_data.get("last_interview_reply_id")
    if last_reply_id and last_reply_id in pending_email_replies and not url_match:
        triggers = ["nemůžu", "nevyhovuje", "termín", "navrhni", "čas", "jiný", "přeplánuj", "pátek", "pondělí", "úterý", "středa", "čtvrtek"]
        if any(t in text.lower() for t in triggers):
            status_msg = await update.message.reply_text("✍️ *Přeformulovávám odpověď na pohovor s novým termínem...*", parse_mode=ParseMode.MARKDOWN)
            current_reply = pending_email_replies[last_reply_id]
            cand = get_candidate_profile()
            cand_name = cand.get("name", "Uchazeč")

            refine_prompt = f"""
Jsi osobní asistent kandidáta ({cand_name}). Personalista ({current_reply['recruiter']} z {current_reply['company']}) poslal pozvánku na pohovor.
Kandidát má k navrženému termínu tuto připomínku:
"{text}"

Původní návrh odpovědi:
{current_reply['body']}

Napiš zdvořilou, profesionální odpověď od kandidáta ({cand_name}), kde srozumitelně navrhne nový termín/čas dle svých preferencí a poděkuje za flexibilitu.
Vrať POUZE samotný text odpovědi.
"""
            try:
                resp = analyzer.client.models.generate_content(
                    model=analyzer.model_name,
                    contents=refine_prompt,
                )
                new_body = resp.text.strip()
                current_reply["body"] = new_body

                msg_text = (
                    f"🔄 **UPRAVENÝ NÁVRH ODPOVĚDI NA POHOVOR:**\n"
                    f"🏢 **Firma:** `{current_reply['company']}`\n\n"
                    f"```text\n{new_body}\n```"
                )
                buttons = [
                    [InlineKeyboardButton("✅ Schválit a odeslat upravenou odpověď", callback_data=f"send_{last_reply_id}")],
                ]
                await status_msg.delete()
                await update.message.reply_text(
                    msg_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
                return
            except Exception as e:
                await status_msg.edit_text(f"❌ Chyba při úpravě: {e}")
                return

    # 2. Úprava průvodního dopisu k inzerátu
    last_job = context.user_data.get("last_job")
    last_letter = context.user_data.get("last_letter")

    is_feedback = False
    if last_job and last_letter and not url_match:
        feedback_triggers = ["uprav", "přepracuj", "změň", "zkrať", "přidej", "uber", "vtírav", "formáln", "dopis", "napiš", "jinak", "lepší", "nový"]
        if len(text) < 250 or any(t in text.lower() for t in feedback_triggers):
            is_feedback = True

    if is_feedback:
        status_msg = await update.message.reply_text("✍️ *Přepracovávám průvodní dopis podle tvých připomínek...*", parse_mode=ParseMode.MARKDOWN)
        try:
            refined_letter = generator.refine_cover_letter(last_job, last_letter, text)
            context.user_data["last_letter"] = refined_letter

            # Uložení do pending_jobs pro možnost okamžitého odeslání
            pending_jobs = load_pending_jobs()
            job_key = f"refined_{len(pending_jobs) + 1}"
            pending_jobs[job_key] = {
                "url": last_job.url,
                "title": last_job.title,
                "company": last_job.company,
                "location": last_job.location,
                "work_type": last_job.work_type,
                "contact_person": last_job.contact_person,
                "raw_text": last_job.raw_text,
            }
            save_pending_jobs(pending_jobs)

            buttons = [
                [InlineKeyboardButton("🚀 Odeslat upravenou přihlášku", callback_data=f"confirm_apply_{job_key}")],
            ]
            if last_job.url:
                buttons.append([InlineKeyboardButton("🌐 Otevřít inzerát na Jobs.cz", url=last_job.url)])

            reply = (
                f"🔄 *Průvodní dopis byl upraven podle tvého zadání:*\n\n"
                f"```text\n{refined_letter}\n```\n\n"
                f"💡 _Pokud jsi spokojený, můžeš rovnou klepnout na tlačítko níže a přihlášku odeslat._"
            )
            await status_msg.delete()
            await update.message.reply_text(
                reply,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return
        except Exception as e:
            await status_msg.edit_text(f"❌ *Chyba při úpravě dopisu:*\n`{str(e)}`", parse_mode=ParseMode.MARKDOWN)
            return

    # 3. Nový inzerát (URL nebo text)
    status_msg = await update.message.reply_text("⏳ *Stahuji a analyzuji inzerát...*", parse_mode=ParseMode.MARKDOWN)

    try:
        if url_match:
            url = url_match.group(0)
            posting = scraper.fetch_from_url(url)
        else:
            posting = scraper.parse_raw_text(text)

        analysis = analyzer.analyze(posting)
        cover_letter = generator.generate_cover_letter(posting, analysis)

        context.user_data["last_job"] = posting
        context.user_data["last_letter"] = cover_letter
        context.user_data["last_analysis"] = analysis

        fit_score = analysis.get("fit_score", 0)
        category = analysis.get("category", "Nespecifikováno")
        summary = analysis.get("summary", "")
        responsibilities = analysis.get("responsibilities", [])
        requirements = analysis.get("requirements", [])
        why_it_fits = analysis.get("why_it_fits", [])
        risks = analysis.get("potential_risks_or_notes", "")

        score_badge = "🟢" if fit_score >= 80 else ("🟡" if fit_score >= 50 else "🔴")

        resp_bullets = "\n".join([f"  • {r}" for r in responsibilities[:4]]) if responsibilities else "  • Neuvedeno"
        req_bullets = "\n".join([f"  • {r}" for r in requirements[:4]]) if requirements else "  • Neuvedeno"
        why_bullets = "\n".join([f"  • {w}" for w in why_it_fits[:3]]) if why_it_fits else "  • Neuvedeno"

        card_text = (
            f"🎯 *{posting.title}*\n"
            f"🏢 *Firma:* `{posting.company}`\n"
            f"📊 *Shoda s profilem:* {score_badge} `{fit_score} %` ({category})\n"
            f"📍 *Lokalita:* {posting.location} | {posting.work_type}\n\n"
            f"📝 *SHRNUTÍ:*\n{summary}\n\n"
            f"🛠️ *NÁPLŇ PRÁCE:*\n{resp_bullets}\n\n"
            f"🎯 *CO OČEKÁVAJÍ:*\n{req_bullets}\n\n"
            f"💡 *PROČ SE K TOBĚ HODÍ / NEHODÍ:*\n{why_bullets}\n\n"
        )
        if risks:
            card_text += f"⚠️ *UPOZORNĚNÍ / RIZIKA:*\n{risks}\n\n"

        card_text += (
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"✉️ *PRŮVODNÍ DOPIS (připraven ke zkopírování):*\n\n"
            f"```text\n{cover_letter}\n```\n\n"
            f"💡 _Tip: Pokud chceš dopis změnit, stačí mi napsat (např. „zkrať to“, „zdůrazni Canvu“)._"
        )

        buttons = []
        if posting.url:
            buttons.append([InlineKeyboardButton("🌐 Otevřít inzerát na Jobs.cz", url=posting.url)])

        keyboard = InlineKeyboardMarkup(buttons) if buttons else None

        await status_msg.delete()
        await update.message.reply_text(
            card_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ *Chyba při zpracování:*\n`{str(e)}`", parse_mode=ParseMode.MARKDOWN)


async def prepare_morning_digest_cache(context: ContextTypes.DEFAULT_TYPE):
    """Příprava ranního přehledu v předstihu (v 7:45), aby byl v 8:00 okamžitě připraven."""
    print("⏳ [7:45] Zahajuji předzpracování a analýzu inzerátů pro ranní přehled...")
    history = load_history()
    pending_jobs = load_pending_jobs()

    keywords = ["marketing", "analytik", "ekonomika", "administrativa"]
    links = scraper.fetch_live_search_jobs(keywords=keywords, location="praha")

    new_offers = []
    for link in links:
        if link in history:
            continue

        try:
            posting = scraper.fetch_from_url(link)
            analysis = analyzer.analyze(posting)
            fit_score = analysis.get("fit_score", 0)

            # Pouze vhodné juniorní pozice (nad 50 %)
            if fit_score >= 50:
                job_id = f"job_{len(pending_jobs) + 1}"
                pending_jobs[job_id] = {
                    "url": posting.url,
                    "title": posting.title,
                    "company": posting.company,
                    "location": posting.location,
                    "work_type": posting.work_type,
                    "contact_person": posting.contact_person,
                    "raw_text": posting.raw_text,
                    "analysis": analysis,
                }
                new_offers.append((job_id, posting, analysis, fit_score))
                history.add(link)

            if len(new_offers) >= 5:
                break
        except Exception as e:
            print(f"Chyba při předzpracování {link}: {e}")

    save_history(history)
    save_pending_jobs(pending_jobs)

    if not new_offers:
        context.bot_data["prepared_digest"] = None
        return

    # Seřazení podle vhodnosti (Fit Score sestupně)
    new_offers.sort(key=lambda x: x[3], reverse=True)

    digest_lines = [f"☕ *Ranní přehled nových nabídek Jobs.cz ({len(new_offers)} pozic seřazených dle vhodnosti):*\n━━━━━━━━━━━━━━━━━━━━━\n"]
    buttons = []

    for idx, (job_id, posting, analysis, score) in enumerate(new_offers, 1):
        badge = "🟢" if score >= 80 else "🟡"
        status_label = "Vhodné pro tebe" if score >= 80 else "Vyšší nároky"
        summary = analysis.get("summary", "")
        digest_lines.append(
            f"{badge} *{idx}. {posting.title}* — `{posting.company}`\n"
            f"📊 Shoda: `{score} %` ({status_label}) | 📍 {posting.location}\n"
            f"📝 {summary}\n"
        )
        btn_label = f"📝 {idx}. Připravit dopis ({score}%)"
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"draft_{job_id}")])

    digest_lines.append("━━━━━━━━━━━━━━━━━━━━━\n💡 _Klepni na tlačítko níže a já ti k vybrané nabídce obratem připravím kompletní průvodní dopis na míru._")

    total_saved_tokens = sum(analysis.get("_toon_savings", {}).get("tokens_saved", 0) for _, _, analysis, _ in new_offers)
    if total_saved_tokens > 0:
        total_saved_czk = sum(analysis.get("_toon_savings", {}).get("saved_czk", 0.0) for _, _, analysis, _ in new_offers)
        digest_lines.append(f"\n💡 *TOON Úspora:* -{total_saved_tokens:,} tok | ~{total_saved_czk:.4f} CZK _(ODHAD – čeká na finální provider invoice)_")

    full_digest_text = "\n".join(digest_lines)
    keyboard = InlineKeyboardMarkup(buttons)

    context.bot_data["prepared_digest"] = (full_digest_text, keyboard)
    print("✅ [7:45] Ranní přehled byl úspěšně připraven do mezipaměti.")


async def scheduled_morning_digest(context: ContextTypes.DEFAULT_TYPE):
    """Odeslání ranního přehledu přesně v 8:00."""
    target_chat = JOBS_GROUP_CHAT_ID or ALLOWED_USER_ID
    if not target_chat:
        return

    thread_id = JOBS_THREAD_ID if target_chat == JOBS_GROUP_CHAT_ID else None
    print(f"📢 [8:00] Odesílám ranní přehled do Telegramu (chat: {target_chat}, thread: {thread_id})...")
    prepared = context.bot_data.get("prepared_digest")
    if prepared:
        text, keyboard = prepared
        await context.bot.send_message(
            chat_id=int(target_chat),
            message_thread_id=thread_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
        context.bot_data["prepared_digest"] = None
    else:
        # Pokud nebyl v mezipaměti, vygenerujeme ho živě
        await run_digest_flow(context.bot, int(target_chat), thread_id=thread_id)


async def periodic_email_check(context: ContextTypes.DEFAULT_TYPE):
    """Kontrola e-mailů na pozadí každých 15 minut."""
    target_chat = JOBS_GROUP_CHAT_ID or ALLOWED_USER_ID
    if not target_chat:
        return

    thread_id = JOBS_THREAD_ID if target_chat == JOBS_GROUP_CHAT_ID else None
    emails = email_handler.check_new_recruitment_emails()
    for item in emails:
        if item.get("intent") in ("interview_invite", "task_request"):
            await process_incoming_email_item(item, context, int(target_chat), thread_id=thread_id)


async def process_incoming_email_item(item: dict, context: ContextTypes.DEFAULT_TYPE, chat_id: int, thread_id: int = None):
    intent = item.get("intent")
    company = item.get("company_name", "Firma")
    position = item.get("position_title", "Pozice")
    recruiter = item.get("recruiter_name", "Personalista")
    summary = item.get("summary", "")
    suggested_reply = item.get("suggested_reply", "")
    sender_email = item.get("sender", "")

    if intent == "interview_invite":
        reply_id = f"reply_{len(pending_email_replies) + 1}"
        pending_email_replies[reply_id] = {
            "to_email": sender_email,
            "subject": f"Re: Pozvání k pohovoru - {position}",
            "body": suggested_reply,
            "company": company,
            "recruiter": recruiter,
        }

        context.user_data["last_interview_reply_id"] = reply_id

        msg_text = (
            f"🎉 **POZVÁNKA NA POHOVOR!**\n"
            f"🏢 **Firma:** `{company}`\n"
            f"📌 **Pozice:** `{position}`\n"
            f"👤 **Od:** {recruiter} (`{sender_email}`)\n\n"
            f"📝 **SHRNUTÍ:**\n{summary}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"✉️ **NAVRŽENÁ ODPOVĚĎ:**\n"
            f"```text\n{suggested_reply}\n```\n\n"
            f"💡 _Chceš změnit termín? Stačí mi to napsat do zprávy (např. „nemůžu v úterý, navrhni pátek“)._"
        )

        buttons = [
            [InlineKeyboardButton("✅ Schválit a odeslat odpověď", callback_data=f"send_{reply_id}")],
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text=msg_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )


def main():
    token = TELEGRAM_BOT_TOKEN
    if not token:
        print("⚠️ Chybí TELEGRAM_BOT_TOKEN!")
        return

    print("🤖 Spouštím vylepšeného Telegram bota s tlačítkovým přehledem...")
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("digest", digest_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Plánování: Každých 15 minut kontrola pošty
    if app.job_queue:
        app.job_queue.run_repeating(periodic_email_check, interval=900, first=30)
        
        from zoneinfo import ZoneInfo
        prague_tz = ZoneInfo("Europe/Prague")
        
        # 1. Předzpracování dat v 7:45 ráno (analýza, grading, řazení)
        app.job_queue.run_daily(prepare_morning_digest_cache, time=datetime.time(hour=7, minute=45, tzinfo=prague_tz))
        # 2. Okamžité doručení hotového přehledu přesně v 8:00 ráno
        app.job_queue.run_daily(scheduled_morning_digest, time=datetime.time(hour=8, minute=0, tzinfo=prague_tz))

    app.run_polling()


if __name__ == "__main__":
    main()
