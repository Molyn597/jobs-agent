import asyncio
import os
import re
import sys
import winreg
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from playwright.async_api import async_playwright
from core.analyzer import JobAnalyzer
from core.generator import CoverLetterGenerator
from core.jobs_browser import get_jobs_credentials
from core.scraper import JobsScraper


async def run_visual_check():
    print("=" * 65)
    print("👀 VIZUÁLNÍ KONTROLA VYPLNĚNÍ FORMULÁŘE JOBS.CZ NA TVÉ OBRAZOVCE")
    print("=" * 65)
    print(
        "Tento test otevře skutečné okno prohlížeče, přihlásí se k tvému Jobs.cz,"
    )
    print(
        "vyplní formulář, nahraje PDF CV a C1 certifikát a nechá ho otevřený."
    )
    print("🛡️ BEZPEČNOST: Tlačítko 'Odeslat odpověď' NEBUDE stisknuto!\n")

    email, password = get_jobs_credentials()
    scraper = JobsScraper()
    analyzer = JobAnalyzer()
    generator = CoverLetterGenerator()

    test_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("JOBS_TEST_URL")
    if not test_url:
        print("❌ Zadej URL inzerátu: python visual_form_check.py https://www.jobs.cz/rpd/<id>/")
        return
    print(f"1. Stahuji a analyzuji inzerát: {test_url}...")
    posting = scraper.fetch_from_url(test_url)
    analysis = analyzer.analyze(posting)
    cover_letter = generator.generate_cover_letter(posting, analysis)

    cv_path = str(Path("data/sample_cv.pdf").resolve())
    cert_path = str(Path("data/sample_certificate.pdf").resolve())

    print("\n2. Otevírám viditelné okno Chrome prohlížeče v plynulém režimu...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, slow_mo=800
        )  # Plynulé zpomalení pro sledování každého kroku
        page = await browser.new_page()

        # Přihlášení
        print(f"🔐 Přihlašuji k Jobs.cz pod účtem {email}...")
        await page.goto("https://www.jobs.cz/prihlasit-se/", timeout=25000)
        await page.fill(
            'input[type="email"], input[name="username"], input[name="email"]',
            email,
        )
        submit_btn = await page.query_selector(
            'button[type="submit"], input[type="submit"]'
        )
        if submit_btn:
            await submit_btn.click()
            await page.wait_for_timeout(1500)

        pwd_input = await page.wait_for_selector(
            'input[type="password"]', timeout=10000
        )
        if pwd_input:
            await pwd_input.fill(password)
            submit_pwd = await page.query_selector(
                'button[type="submit"], input[type="submit"]'
            )
            if submit_pwd:
                await submit_pwd.click()
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(2000)

        # Otevření inzerátu a formuláře
        job_id_match = re.search(r"/rpd/(\d+)", test_url)
        if job_id_match:
            jof_url = f"https://www.jobs.cz/jof/{job_id_match.group(1)}/"
        else:
            jof_url = test_url

        print(f"🌐 Otevírám formulář odpovědi: {jof_url}...")
        await page.goto(jof_url, timeout=25000)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)

        print(
            "✍️ Vyplňuji telefon, nahrávám PDF životopis a C1 certifikát,"
            " vkládám dopis..."
        )

        # Telefon
        phone_input = page.locator(
            'input[type="tel"], input[name*="phone"],'
            ' input[placeholder*="Telefon"]'
        )
        if await phone_input.count() > 0:
            await phone_input.first.fill("+420 123 456 789")

        # Průvodní dopis
        textarea = page.locator('textarea, div[contenteditable="true"]')
        if await textarea.count() > 0:
            await textarea.first.fill(cover_letter)

        # 4. Výběr 'Nahrát životopis ze souboru'
        try:
            upload_label = page.locator('text="Nahrát životopis ze souboru"')
            if await upload_label.count() > 0:
                await upload_label.first.click(timeout=3000)
                await page.wait_for_timeout(500)
        except Exception:
            pass

        # Nahrání životopisu (do pole customCvs)
        if os.path.exists(cv_path):
            cv_input = page.locator('input#customCvs, input[name*="customCv"], input[type="file"]').first
            await cv_input.set_input_files(cv_path)
            print(f"  📎 Životopis nahrán do formuláře: {cv_path}")
            await page.wait_for_timeout(1000)

        # Nahrání C1 certifikátu (do pole ostatní přílohy / otherAttachments)
        if os.path.exists(cert_path):
            cert_input = page.locator('input#jobad_application_otherAttachments, input[name*="otherAttachment"], input[type="file"]:nth-of-type(2)')
            if await cert_input.count() > 0:
                await cert_input.first.set_input_files(cert_path)
                print(f"  📎 C1 Certifikát nahrán do ostatních příloh: {cert_path}")
                await page.wait_for_timeout(1000)

        # 5. Zaškrtnutí souhlasu s oslovením firmou (acceptTerms)
        try:
            consent_cb = page.locator('input#jobad_application_acceptTerms')
            if await consent_cb.count() > 0:
                if not await consent_cb.first.is_checked():
                    await consent_cb.first.check()
                    print("  ✅ Souhlas se zpracováním údajů pro firmu byl zaškrtnut.")
        except Exception as ce:
            print(f"Poznámka k souhlasu: {ce}")

        await page.wait_for_timeout(1500)
        print(
            "⏳ Okno nechávám 20 vteřin otevřené, abys vše mohl v klidu"
            " zkontrolovat..."
        )
        await page.wait_for_timeout(20000)
        await browser.close()
        print("🔒 Prohlížeč bezpečně zavřen bez odeslání.")


if __name__ == "__main__":
    asyncio.run(run_visual_check())
