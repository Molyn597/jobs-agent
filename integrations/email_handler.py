import email
import imaplib
import json
import os
import re
import smtplib
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import winreg
except ImportError:
    winreg = None

from google import genai
from google.genai import types


def get_gmail_credentials():
    email_user = os.environ.get("GMAIL_USER_EMAIL")
    app_pwd = os.environ.get("GMAIL_APP_PASSWORD")

    if not email_user or not app_pwd:
        if winreg:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
                if not email_user:
                    email_user, _ = winreg.QueryValueEx(key, "GMAIL_USER_EMAIL")
                    os.environ["GMAIL_USER_EMAIL"] = email_user
                if not app_pwd:
                    app_pwd, _ = winreg.QueryValueEx(key, "GMAIL_APP_PASSWORD")
                    os.environ["GMAIL_APP_PASSWORD"] = app_pwd
            except Exception:
                pass

    return email_user, app_pwd


def clean_header_text(header_val: str) -> str:
    if not header_val:
        return ""
    decoded_parts = decode_header(header_val)
    res = []
    for part, enc in decoded_parts:
        if isinstance(part, bytes):
            try:
                res.append(part.decode(enc or "utf-8", errors="ignore"))
            except Exception:
                res.append(part.decode("latin-1", errors="ignore"))
        else:
            res.append(str(part))
    return "".join(res)


class EmailHandler:
    def __init__(self, model_name: str = "gemini-3.7-flash"):
        self.model_name = model_name
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
                api_key, _ = winreg.QueryValueEx(key, "GEMINI_API_KEY")
                os.environ["GEMINI_API_KEY"] = api_key
            except Exception:
                pass
        self.ai_client = genai.Client(api_key=api_key) if api_key else None

    def check_new_recruitment_emails(self) -> List[Dict[str, Any]]:
        """Zkontroluje nepřečtené e-maily související VÝHRADNĚ s náborem a Jobs.cz."""
        email_user, app_pwd = get_gmail_credentials()
        if not email_user or not app_pwd:
            print("⚠️ Chybí přihlašovací údaje k Gmailu.")
            return []

        results = []
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", port=993)
            mail.login(email_user, app_pwd)
            mail.select("INBOX", readonly=False)

            # Striktní vyhledávací dotaz (ochrana soukromí)
            # Hledáme nepřečtené zprávy od Jobs.cz nebo s klíčovými slovy v předmětu
            search_criteria = '(UNSEEN)'
            status, msg_ids = mail.search(None, search_criteria)

            if status != "OK" or not msg_ids[0]:
                mail.logout()
                return []

            id_list = msg_ids[0].split()
            # Omezíme kontrolu na posledních 10 nepřečtených pro rychlost
            for msg_id in id_list[-10:]:
                res, data = mail.fetch(msg_id, "(RFC822)")
                if res != "OK":
                    continue

                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                sender = clean_header_text(msg.get("From", ""))
                subject = clean_header_text(msg.get("Subject", ""))
                date_str = msg.get("Date", "")

                # Získání těla zprávy
                body_text = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                                break
                        elif content_type == "text/html" and not body_text:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")

                # Kontrola, zda e-mail souvisí s náborem
                is_jobs_digest = bool(re.search(r"\d+\s+nových\s+nabídek", subject, re.IGNORECASE))
                is_recruitment_reply = any(kw in subject.lower() or kw in body_text.lower() for kw in [
                    "výběrové řízení", "pohovor", "životopis", "odpověď na pozici", "reakce na inzerát",
                    "pozvání", "interview", "nabídka práce"
                ])

                # Ignorujeme "Vaše příležitost ..." a nesouvisející e-maily
                if not (is_jobs_digest or is_recruitment_reply):
                    continue

                # Analýza záměru zprávy pomocí AI
                classified = self.classify_email(sender, subject, body_text)
                if classified and classified.get("intent") != "unrelated":
                    classified["sender"] = sender
                    classified["subject"] = subject
                    classified["raw_body"] = body_text[:2000]
                    classified["date"] = date_str
                    results.append(classified)

            mail.logout()
        except Exception as e:
            print(f"Chyba při kontrole e-mailu: {e}")

        return results

    def classify_email(self, sender: str, subject: str, body: str) -> Dict[str, Any]:
        """Sémanticky zařadí e-mail a navrhne případnou odpověď."""
        if not self.ai_client:
            return {"intent": "unrelated"}

        prompt = f"""
Jsi AI asistent kandidáta. Zanalyzuj následující e-mail týkající se hledání práce / výběrových řízení.

### E-MAIL K ANALÝZE:
- **Od:** {sender}
- **Předmět:** {subject}
- **Obsah e-mailu:**
{body[:3000]}

---

### KLASIFIKACE A VÝSTUP (JSON):
Urči typ e-mailu do jedné z kategorií:
1. `job_alert` – notifikace z Jobs.cz s novými nabídkami práce. Vytáhni seznam URL odkazů na nabídky.
2. `interview_invite` – personalista/firma zve kandidáta na pohovor (online Teams/Meet nebo osobně) a navrhuje termín(y).
3. `task_request` – firma posílá zadání úkolu nebo dotazník před pohovorem.
4. `rejection` – oznámení o nepostoupení / zamítnutí přihlášky.
5. `submission_confirmation` – automatické potvrzení o doručení odpovědi firmě.
6. `unrelated` – jiný nesouvisející e-mail.

Vrať POUZE validní JSON:
{{
  "intent": "interview_invite | job_alert | task_request | rejection | submission_confirmation | unrelated",
  "company_name": "<název firmy>",
  "position_title": "<název pozice>",
  "recruiter_name": "<jméno personalisty, pokud je v podpisu/textu>",
  "summary": "<stručný 1-2 větý výtah sdělení>",
  "proposed_dates": ["<termín 1, např. Úterý 22.3. v 10:00>", "<termín 2, např. Čtvrtek 24.3. ve 14:00>"],
  "job_urls": ["<extrahované URL odkazy na inzeráty, pokud jde o job_alert>"],
  "suggested_reply": "<profesionální a zdvořilý návrh odpovědi v češtině od kandidáta, pokud jde o interview_invite nebo task_request. Pokud navrhují termíny, přijmi první z nich. Pokud termíny nenavrhují, poděkuj a projev zájem.>"
}}
"""
        try:
            response = self.ai_client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            return json.loads(response.text)
        except Exception:
            return {"intent": "unrelated"}

    def send_approved_email(self, to_email: str, subject: str, body_text: str, attachment_path: Optional[str] = None, sender_name: Optional[str] = None) -> bool:
        """Odešle e-mail ze schránky uživatele POUZE po schválení uživatelem (s volitelnou přílohou CV)."""
        email_user, app_pwd = get_gmail_credentials()
        if not email_user or not app_pwd:
            raise ValueError("Chybí přihlašovací údaje k Gmailu.")

        msg = MIMEMultipart()
        display_name = sender_name or "Uchazeč"
        msg["From"] = f"{display_name} <{email_user}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Přiložení životopisu (CV) v PDF, pokud existuje
        if attachment_path and os.path.exists(attachment_path):
            from email.mime.base import MIMEBase
            from email import encoders
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "pdf")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            filename = os.path.basename(attachment_path)
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)

        # Odeslání přes zabezpečený SMTP Gmail server
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_user, app_pwd)
            server.send_message(msg)

        return True
