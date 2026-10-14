# 🎯 Jobs.cz AI Career & Application Agent

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Powered by Gemini](https://img.shields.io/badge/LLM-Google%20Gemini-orange.svg)](https://ai.google.dev/)
[![Telegram Forum Topics](https://img.shields.io/badge/Platform-Telegram%20Bot-2CA5E0.svg)](https://telegram.org/)
[![Browser Automation](https://img.shields.io/badge/Automation-Playwright%20Chromium-45ba4b.svg)](https://playwright.dev/)

**The autonomous AI career scout, application drafter & approval pipeline for Jobs.cz.** Continuously monitors openings, analyzes job requirements against your candidate profile, generates personalized Czech cover letters, and lets you review, refine, and dispatch applications directly from Telegram.

---

| Capability | What's Covered |
| :--- | :--- |
| **🎯 Career Fit Scoring (0–100%)** | Evaluates job descriptions against seniority criteria (Junior/Trainee), contract preferences, commute constraints, and skill stack via Google Gemini. |
| **✍️ Grammatically Flawless Letters** | Strictly complies with Czech 5th case (vocative) for recruiters, matches tone of voice, and highlights relevant skills and past projects. |
| **📱 Telegram Interactive Pipeline** | Formatted job summary cards with direct action buttons (`Approve & Send`, `Open Job`, `Refine Letter`). |
| **🗣️ Conversational Refinement** | Refine cover letters or interview replies on the fly: send a text or voice prompt in Telegram to rewrite the letter before sending. |
| **🌐 Playwright Application Flow** | Automated browser flow that logs into Jobs.cz, uploads your PDF resume and certificates, fills form fields, and verifies submission. |
| **📬 IMAP Recruiter Monitor** | Listens on IMAP for recruiter replies or interview invites, categorizes responses, and prepares polite draft acceptances. |
| **🔒 Air-Gapped Local Profile** | All personal resumes, credentials, and application history stay strictly on your local machine in `.gitignore`. |

---

## 🏗 System Architecture

```
                             [ Ingestion Sources ]
                       ┌───────────────┴───────────────┐
                       ▼                               ▼
            [ Direct Jobs.cz Scraper ]       [ IMAP Gmail Alerts ]
                       │                               │
                       └───────────────┬───────────────┘
                                       ▼
                       [ Gemini Career Fit Analyzer ]
                      (0–100% Fit Score vs. Your Profile)
                                       │
                                       ▼
                     [ Dynamic Cover Letter Generator ]
                   (Tone of Voice, Vocative Case, Pitches)
                                       │
                                       ▼
                     [ Telegram Bot Interactive Loop ]
                   ┌───────────────────┼───────────────────┐
                   ▼                   ▼                   ▼
           [ ✍️ Refine Letter ]  [ 🚀 Approve Apply ]  [ ❌ Discard ]
                   │                   │
                   │                   ▼
                   │        [ Playwright Automation / Email ]
                   │         (Uploads CV + fills form safely)
                   │                   │
                   └───────────────────┘
```

---

## ⚡ Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Molyn597/jobs-agent.git
cd jobs-agent

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# 3. Install dependencies & Playwright browsers
pip install -r requirements.txt
playwright install chromium

# 4. Copy configuration templates
cp config/profile.example.json config/profile.json
cp config/search_filter.example.json config/search_filter.json
cp .env.example .env

# 5. Run demo simulation
python app.py --demo
```

---

## ⚙️ Configuration Reference

Edit `config/profile.json` to define your candidate identity:
- Fill in your name, contact information, education, and language proficiencies.
- Place your PDF resume in `data/` and set `cv_path`.
- Define strategic pitch points under `strategy_by_role`.

Edit `.env`:
| Variable | Description | Required | Example |
| :--- | :--- | :---: | :--- |
| `GEMINI_API_KEY` | Google Gemini API Key | Yes | `AIzaSy...` |
| `JOBS_TELEGRAM_BOT_TOKEN` | Telegram Bot token from @BotFather | Yes | `123456789:ABC...` |
| `TELEGRAM_USER_ID` | Your numeric Telegram user ID | Yes | `12345678` |
| `JOBS_GROUP_CHAT_ID` | Supergroup ID for forum topics | Optional | `-100xxxxxxxxxx` |
| `JOBS_THREAD_ID` | Specific topic / thread ID | Optional | `1` |
| `GMAIL_USER_EMAIL` | Gmail account for recruiter replies | Optional | `user@gmail.com` |
| `GMAIL_APP_PASSWORD` | Google App Password (16 chars) | Optional | `abcd efgh ijkl mnop` |

---

## 🕹 CLI Usage

| Command | Action |
| :--- | :--- |
| `python app.py --demo` | Parses a real sample junior ad, evaluates fit score, and drafts a letter. |
| `python app.py --url <jobs_url>` | Scrapes a specific Jobs.cz posting URL and generates application package. |
| `python app.py --text "Inzerat..."` | Analyzes raw pasted job description text. |
| `python integrations/telegram_bot.py` | Starts the interactive 24/7 Telegram review and approval bot. |

---

## ☁️ 24/7 Cloud Deployment (Ubuntu Systemd)

Run the Telegram agent 24/7 on an Ubuntu VPS:

```bash
chmod +x deploy/setup_server.sh
./deploy/setup_server.sh
sudo systemctl status jobs_agent
```

---

## 🛡️ Privacy & Security

- **Zero Secret Leaks**: Tokens and passwords load strictly from environment variables or local git-ignored `.env`.
- **Private Data Protection**: Your real resume, personal contacts, and application database reside solely on your local host and are prevented by `.gitignore` from being pushed remotely.

---

## 📄 License
MIT License — see [LICENSE](LICENSE) for details. Built by [Molyn597](https://github.com/Molyn597).
