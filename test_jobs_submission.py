import asyncio
import os
import sys
import winreg
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from core.analyzer import JobAnalyzer
from core.generator import CoverLetterGenerator
from core.scraper import JobsScraper


async def test_full_card():
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
    bot_token, _ = winreg.QueryValueEx(key, "JOBS_TELEGRAM_BOT_TOKEN")
    user_id, _ = winreg.QueryValueEx(key, "TELEGRAM_USER_ID")

    bot = Bot(token=bot_token)
    scraper = JobsScraper()
    analyzer = JobAnalyzer()
    generator = CoverLetterGenerator()

    # Vzor inzerátu s kontaktní osobou Tereza Šindelář (Ukázková Média)
    sample_text = """
    Společnost Ukázková Média, a.s. hledá posilu na pozici Group Marketing Specialista.
    Lokalita: Praha – Karlín.
    Úvazek: Zkrácený úvazek / DPP / DPČ.
    Náplň práce: Tvorba marketingových kampaní, správa obsahu, Canva, Photoshop, reporting výsledků, mezinárodní komunikace.
    Požadavky: VŠ student, plynulá angličtina, kreativita, samostatnost.
    """
    posting = scraper.parse_raw_text(
        text=sample_text,
        title="Group Marketing Specialista",
        company="Ukázková Média, a.s.",
        contact_person="Tereza Šindelář",
        location="Praha – Karlín",
    )
    posting.url = "https://www.jobs.cz/rpd/0000000000/"

    analysis = analyzer.analyze(posting)
    cover_letter = generator.generate_cover_letter(posting, analysis)

    score = analysis.get("fit_score", 92)
    summary = analysis.get("summary", "")
    responsibilities = analysis.get("responsibilities", [])
    requirements = analysis.get("requirements", [])
    why_it_fits = analysis.get("why_it_fits", [])

    resp_bullets = (
        "\n".join([f"  • {r}" for r in responsibilities[:3]])
        if responsibilities
        else "  • Neuvedeno"
    )
    req_bullets = (
        "\n".join([f"  • {r}" for r in requirements[:3]])
        if requirements
        else "  • Neuvedeno"
    )
    why_bullets = (
        "\n".join([f"  • {w}" for w in why_it_fits[:3]])
        if why_it_fits
        else "  • Neuvedeno"
    )

    card_text = (
        f"🎯 *{posting.title}*\n"
        f"🏢 *Firma:* `{posting.company}`\n"
        f"📊 *Shoda:* 🟢 `{score} %` (Vhodné pro tebe)\n"
        f"📍 *Lokalita:* {posting.location} | {posting.work_type}\n\n"
        f"📝 *SHRNUTÍ:*\n{summary}\n\n"
        f"🛠️ *NÁPLŇ PRÁCE:*\n{resp_bullets}\n\n"
        f"🎯 *CO OČEKÁVAJÍ:*\n{req_bullets}\n\n"
        f"💡 *PROČ SE K TOBĚ HODÍ:*\n{why_bullets}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"✉️ *PRŮVODNÍ DOPIS (připraven pro Jobs.cz):*\n\n"
        f"```text\n{cover_letter}\n```"
    )

    buttons = [
        [
            InlineKeyboardButton(
                "🚀 Odeslat přihlášku a životopis",
                callback_data="confirm_apply_sample",
            )
        ],
        [
            InlineKeyboardButton(
                "🌐 Otevřít inzerát na Jobs.cz", url=posting.url
            )
        ],
    ]

    await bot.send_message(
        chat_id=int(user_id),
        text=card_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    print("Karta s tlačítky a správným oslovením odeslána do Telegramu!")


if __name__ == "__main__":
    asyncio.run(test_full_card())
