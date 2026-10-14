import asyncio
import email
import imaplib
import json
import os
import re
import sys
import winreg
from pathlib import Path

# Nastavení kořenového adresáře
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from bs4 import BeautifulSoup
from telegram import Bot
from telegram.constants import ParseMode

from core.scraper import JobsScraper
from core.analyzer import JobAnalyzer
from core.generator import CoverLetterGenerator
from integrations.email_handler import get_gmail_credentials, clean_header_text


async def run_email_test():
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
    bot_token, _ = winreg.QueryValueEx(key, "JOBS_TELEGRAM_BOT_TOKEN")
    user_id, _ = winreg.QueryValueEx(key, "TELEGRAM_USER_ID")

    bot = Bot(token=bot_token)
    scraper = JobsScraper()
    analyzer = JobAnalyzer()
    generator = CoverLetterGenerator()

    # Načtení historie pro deduplikaci (nikdy neposíláme 2x stejný inzerát)
    history_file = Path("data/history.json")
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history = set()
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = set(json.load(f))
        except Exception:
            pass

    email_user, app_pwd = get_gmail_credentials()
    print("📧 Připojuji se k IMAP pro nalezení e-mailů od Jobs.cz...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(email_user, app_pwd)
    mail.select("INBOX", readonly=True)

    # Hledáme e-maily se seznamem nabídek (např. '6 nových nabídek práce...')
    status, msg_ids = mail.search(None, '(OR FROM "jobs.cz" FROM "pomuzeme@jobs.cz")')
    if status != "OK" or not msg_ids[0]:
        print("❌ Žádný e-mail od Jobs.cz nebyl nalezen.")
        mail.logout()
        return

    id_list = msg_ids[0].split()
    
    # Vyhledáme nejnovější e-mail typu "[N] nových nabídek..."
    digest_msg_id = None
    target_subject = ""
    for msg_id in reversed(id_list):
        res, data = mail.fetch(msg_id, "(BODY[HEADER.FIELDS (SUBJECT)])")
        msg = email.message_from_bytes(data[0][1])
        subj = clean_header_text(msg.get("Subject", ""))
        if re.search(r"\d+\s+nových\s+nabídek", subj, re.IGNORECASE):
            digest_msg_id = msg_id
            target_subject = subj
            break

    if not digest_msg_id:
        print("❌ Nebyl nalezen žádný e-mail se souhrnem '[N] nových nabídek'.")
        mail.logout()
        return

    print(f"✅ Nalezen souhrnný e-mail: {target_subject}")

    res, data = mail.fetch(digest_msg_id, "(RFC822)")
    msg = email.message_from_bytes(data[0][1])
    subject = target_subject

    html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    html_body = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            html_body = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")

    mail.logout()

    extracted_links = scraper.extract_links_from_email_html(html_body)
    print(f"🔗 Nalezeno {len(extracted_links)} odkazů v e-mailu.")

    processed_count = 0
    for link in extracted_links[:10]:
        if link in history:
            print(f"⏩ Přeskakuji již viděnou nabídku (deduplikace): {link[:60]}...")
            continue

        print(f"\n🔍 Stahuji a analyzuji nabídku: {link[:80]}...")
        try:
            posting = scraper.fetch_from_url(link)

            # Tvrdý negativní filtr (např. 'Head of Back Office', 'Senior')
            negative_keywords = ["head of", "senior", "vedoucí", "ředitel", "director", "manažer"]
            is_negative = any(neg in posting.title.lower() for neg in negative_keywords)
            if is_negative and not any(ok in posting.title.lower() for ok in ["podpora", "asistent", "junior"]):
                print(f"🚫 Zahozeno negativním filtrem: {posting.title}")
                history.add(link)
                continue

            analysis = analyzer.analyze(posting)
            fit_score = analysis.get("fit_score", 0)

            # Pouze nabídky se shodou >= 70%
            if fit_score < 70:
                print(f"⚠️ Nízká shoda ({fit_score} %): {posting.title}")
                history.add(link)
                continue

            cover_letter = generator.generate_cover_letter(posting, analysis)

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
                f"📊 *Shoda s profilem:* {score_badge} `{fit_score} %`\n"
                f"📍 *Lokalita:* {posting.location} | {posting.work_type}\n\n"
                f"📝 *SHRNUTÍ:*\n{summary}\n\n"
                f"🛠️ *NÁPLŇ PRÁCE:*\n{resp_bullets}\n\n"
                f"🎯 *CO OČEKÁVAJÍ:*\n{req_bullets}\n\n"
                f"💡 *PROČ SE K TOBĚ HODÍ:*\n{why_bullets}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"✉️ *PRŮVODNÍ DOPIS:*\n\n"
                f"```text\n{cover_letter}\n```"
            )

            await bot.send_message(chat_id=int(user_id), text=card_text, parse_mode=ParseMode.MARKDOWN)
            history.add(link)
            processed_count += 1
            print(f"📤 Odesláno do Telegramu: {posting.title} (Shoda: {fit_score} %)")

        except Exception as err:
            print(f"❌ Chyba při zpracování: {err}")

    # Uložení historie
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(list(history), f, ensure_ascii=False, indent=2)

    print(f"\n✨ Hotovo! Celkem zpracováno a doručeno {processed_count} relevantních nabídek.")


if __name__ == "__main__":
    asyncio.run(run_email_test())
