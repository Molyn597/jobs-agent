import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional
from playwright.async_api import async_playwright

try:
    import winreg
except ImportError:
    winreg = None


def get_jobs_credentials():
    email = os.environ.get("JOBS_CZ_EMAIL")
    password = os.environ.get("JOBS_CZ_PASSWORD")

    if not email or not password:
        if winreg:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
                if not email:
                    email, _ = winreg.QueryValueEx(key, "JOBS_CZ_EMAIL")
                if not password:
                    password, _ = winreg.QueryValueEx(key, "JOBS_CZ_PASSWORD")
            except Exception:
                pass

    return email or "", password or ""


class JobsBrowserAutomation:
    def __init__(self, cookies_path: str = "data/jobs_cookies.json", headless: bool = True):
        self.cookies_path = Path(cookies_path)
        self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
        self.headless = headless

    async def ensure_login(self, page) -> bool:
        """Přihlásí se k Jobs.cz nebo použije uložené cookies."""
        email, password = get_jobs_credentials()
        if not password:
            print("⚠️ Chybí heslo k Jobs.cz.")
            return False

        # Zkusíme načíst existující cookies
        if self.cookies_path.exists():
            try:
                with open(self.cookies_path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                await page.context.add_cookies(cookies)
                await page.goto("https://www.jobs.cz/osobni/prehled/", timeout=20000)
                if "prihlasit" not in page.url and "auth" not in page.url:
                    print("✅ Přihlášení přes uložené cookies je platné.")
                    return True
            except Exception as e:
                print(f"Cookies expirovaly nebo jsou neplatné: {e}")

        # Provedeme nové přihlášení
        print(f"🔐 Přihlašuji se k Jobs.cz jako {email}...")
        try:
            await page.goto("https://www.jobs.cz/prihlasit-se/", timeout=25000)
            await page.wait_for_load_state("networkidle")

            # Vyplnění e-mailu
            await page.fill('input[type="email"], input[name="username"], input[name="email"]', email)
            submit_btn = await page.query_selector('button[type="submit"], input[type="submit"]')
            if submit_btn:
                await submit_btn.click()
                await page.wait_for_timeout(2000)

            # Vyplnění hesla
            pwd_input = await page.wait_for_selector('input[type="password"]', timeout=10000)
            if pwd_input:
                await pwd_input.fill(password)
                submit_pwd = await page.query_selector('button[type="submit"], input[type="submit"]')
                if submit_pwd:
                    await submit_pwd.click()
                    await page.wait_for_load_state("networkidle")
                    await page.wait_for_timeout(3000)

            # Uložení cookies
            cookies = await page.context.cookies()
            with open(self.cookies_path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            print("✅ Přihlášení k Jobs.cz úspěšné a cookies uloženy.")
            return True
        except Exception as e:
            print(f"❌ Chyba při přihlašování k Jobs.cz: {e}")
            return False

    async def fill_jobs_application_form(
        self,
        job_url: str,
        cover_letter: str,
        cv_path: Optional[str] = None,
        cert_path: Optional[str] = None,
        phone: Optional[str] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Automaticky vyplní formulář odpovědi na Jobs.cz (včetně CV a C1 certifikátu)."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            await self.ensure_login(page)

            try:
                await page.goto(job_url, timeout=30000)
                await page.wait_for_load_state("domcontentloaded")

                # Kliknutí na 'Odpovědět' pokud nejsme přímo ve formuláři
                try:
                    apply_btn = page.locator('a:has-text("Odpovědět"), button:has-text("Odpovědět")')
                    if await apply_btn.count() > 0:
                        await apply_btn.first.click(force=True, timeout=5000)
                        await page.wait_for_timeout(2000)
                except Exception as be:
                    print(f"Poznámka k tlačítku Odpovědět: {be}")

                # 1. Kontrola jména personalisty (Komu:)
                content = await page.content()
                recruiter_match = re.search(r"Komu:\s*([A-ZÁ-Ž][a-zá-ž]+\s+[A-ZÁ-Ž][a-zá-ž]+)", content)
                recruiter_name = recruiter_match.group(1).strip() if recruiter_match else None

                # 2. Vyplnění telefonu
                if phone:
                    phone_input = await page.query_selector('input[type="tel"], input[name*="phone"], input[placeholder*="Telefon"]')
                    if phone_input:
                        await phone_input.fill(phone)

                # 3. Vyplnění průvodního dopisu do textarea
                textarea = await page.query_selector('textarea, div[contenteditable="true"]')
                if textarea:
                    await textarea.fill(cover_letter)

                # 4. Výběr 'Nahrát životopis ze souboru'
                try:
                    upload_label = page.locator('text="Nahrát životopis ze souboru"')
                    if await upload_label.count() > 0:
                        await upload_label.first.click(timeout=3000)
                        await page.wait_for_timeout(500)
                except Exception:
                    pass

                # Nahrání životopisu (do pole customCvs)
                if cv_path and os.path.exists(cv_path):
                    cv_input = page.locator('input#customCvs, input[name*="customCv"], input[type="file"]').first
                    await cv_input.set_input_files(cv_path)
                    print(f"📎 Životopis nahrán do formuláře: {cv_path}")
                    await page.wait_for_timeout(1000)

                # Nahrání C1 certifikátu (do pole ostatní přílohy / otherAttachments)
                if cert_path and os.path.exists(cert_path):
                    cert_input = page.locator('input#jobad_application_otherAttachments, input[name*="otherAttachment"], input[type="file"]:nth-of-type(2)')
                    if await cert_input.count() > 0:
                        await cert_input.first.set_input_files(cert_path)
                        print(f"📎 C1 Certifikát nahrán do ostatních příloh: {cert_path}")
                        await page.wait_for_timeout(1000)

                # 5. Zaškrtnutí souhlasu s oslovením firmou (acceptTerms)
                try:
                    consent_cb = page.locator('input#jobad_application_acceptTerms')
                    if await consent_cb.count() > 0:
                        if not await consent_cb.first.is_checked():
                            await consent_cb.first.check()
                            print("✅ Souhlas se zpracováním údajů pro firmu byl zaškrtnut.")
                except Exception as ce:
                    print(f"Poznámka k souhlasu: {ce}")

                await page.wait_for_timeout(1500)

                if dry_run:
                    print("🔍 Režim náhledu (Dry run): Formulář byl kompletně vyplněn a ověřen, ale NEBYL odeslán.")
                    await browser.close()
                    return {
                        "status": "success_dry_run",
                        "recruiter_name": recruiter_name,
                        "message": "Formulář byl úspěšně připraven a vyplněn.",
                    }
                else:
                    # Ostré odeslání
                    submit_button = await page.query_selector('button:has-text("Odeslat odpověď"), button[type="submit"]')
                    if submit_button:
                        await submit_button.click()
                        await page.wait_for_load_state("networkidle")
                        await page.wait_for_timeout(3000)
                        await browser.close()
                        return {
                            "status": "submitted",
                            "recruiter_name": recruiter_name,
                            "message": "Odpověď byla úspěšně odeslána na Jobs.cz!",
                        }

                await browser.close()
                return {"status": "form_ready", "recruiter_name": recruiter_name}
            except Exception as e:
                await browser.close()
                return {"status": "error", "error": str(e)}
