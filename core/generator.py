import json
import os
import sys
from pathlib import Path
from typing import Any, Dict
from google import genai
from google.genai import types

from core.scraper import JobPosting

# TOON shared serializer
try:
    _COMMON_DIR = Path(__file__).resolve().parent.parent.parent / "common"
    if str(_COMMON_DIR) not in sys.path:
        sys.path.insert(0, str(_COMMON_DIR))
    from toon_serializer import (  # noqa: E402
        encode_toon,
        record_savings,
        format_savings_footer,
    )
except ImportError:
    encode_toon = None
    record_savings = lambda *args: {}
    format_savings_footer = lambda *args: ""

AGENT_NAME = "jobs_agent"


class CoverLetterGenerator:
    def __init__(self, profile_path: str = "config/profile.json", model_name: str = "gemini-3.7-flash"):
        self.profile_path = Path(profile_path)
        self.profile_data = self._load_profile()
        self.model_name = model_name

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
                api_key, _ = winreg.QueryValueEx(key, "GEMINI_API_KEY")
                os.environ["GEMINI_API_KEY"] = api_key
            except Exception:
                pass

        if not api_key:
            raise ValueError("Chybí proměnná prostředí GEMINI_API_KEY.")
        self.client = genai.Client(api_key=api_key)

    def _load_profile(self) -> Dict[str, Any]:
        if not self.profile_path.exists():
            example_path = self.profile_path.parent / "profile.example.json"
            if example_path.exists():
                with open(example_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            raise FileNotFoundError(
                f"Profil nenalezen na cestě: {self.profile_path}. "
                f"Zkopírujte config/profile.example.json do config/profile.json a vyplňte své údaje."
            )
        with open(self.profile_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def generate_cover_letter(self, job: JobPosting, analysis: Dict[str, Any]) -> str:
        """Vygeneruje personalizovaný průvodní dopis v přesném stylu kandidáta."""
        cand = self.profile_data.get("candidate", {})
        cand_name = cand.get("name", "Uchazeč")
        cand_edu = cand.get("education", {})
        edu_summary = "; ".join(f"{k}: {v}" for k, v in cand_edu.items() if v)
        work_pref = cand.get("work_preferences", {})
        pref_summary = f"Úvazek: {', '.join(work_pref.get('commitment', []))}, Kapacita: {work_pref.get('capacity', '')}"
        skills = cand.get("skills_and_strengths", {})
        lang_summary = ", ".join(skills.get("languages", []))
        tool_summary = ", ".join(skills.get("tools", []))
        strategies = cand.get("strategy_by_role", {})
        # TOON-encode the strategy block (smaller token footprint for the prompt)
        strat_baseline_json = json.dumps(strategies, ensure_ascii=False, indent=2)
        if encode_toon:
            strat_summary = encode_toon(strategies)
            savings = record_savings(AGENT_NAME, self.model_name, strat_baseline_json, strat_summary)
        else:
            strat_summary = strat_baseline_json
            savings = {}

        prompt = f"""
Jsi expert na tvorbu personalizovaných průvodních dopisů a osobní zástupce kandidáta. Tvým úkolem je napsat úderný, profesionální a autentický průvodní dopis přesně na míru pracovní nabídce z Jobs.cz.

### INFORMACE O KANDIDÁTOVI (Z JEHO PROFILU):
- **Jméno:** {cand_name}
- **Vzdělání:** {edu_summary or "Dle životopisu"}
- **Preference úvazku:** {pref_summary or "Dle domluvy"}
- **Jazyky:** {lang_summary or "Dle životopisu"}
- **Nástroje & Dovednosti:** {tool_summary or "Dle životopisu"}
- **Strategie pro role (TOON format - mensi token footprint):**
{strat_summary}

### ANALÝZA INZERÁTU:
- **Pozice:** {job.title}
- **Firma:** {job.company}
- **Kategorie pozice:** {analysis.get('category')}
- **Klíčové silné stránky ke zdůraznění:** {', '.join(analysis.get('key_strengths_to_highlight', []))}
- **Kontaktní osoba:** {job.contact_person or "neuvedena"}

### CELÝ TEXT INZERÁTU:
{job.raw_text}

---

### PRAVIDLA A TÓN KOMUNIKACE (Tone of Voice):
1. **Oslovení (ZÁSADNÍ PRAVIDLO & SPRÁVNÉ SKLOŇOVÁNÍ V ČEŠTINĚ):**
   - **Pokud je známo jméno kontaktní osoby / personalisty (např. 'Tereza Šindelář' nebo 'Jana Malá' nebo 'Petr Novák'):**
     * VŽDY správně urči pohlaví (žena vs. muž) a použij spisovný 5. pád (vokativ).
     * Pro nesklonná či specifická ženská příjmení (např. 'Tereza Šindelář'): použij "Vážená paní Šindelář," (nepřidávej uměle -ová, pokud se tak nejmenuje!).
     * Pro běžná ženská příjmení: "Vážená paní Malá,", "Vážená paní Dvorská,".
     * Pro mužská příjmení: "Vážený pane Nováku,", "Vážený pane Dvořáku,", "Vážený pane Václavů,".
   - **Pokud jméno kontaktní osoby NENÍ známo, ale známe firmu (např. 'Ukázková Média, a.s.'):**
     * Vždy oslov přímo firemní tým dané společnosti: např. "Vážený týme Ukázková Média," nebo "Vážený týme [Název firmy],".
     * NIKDY v takovém případě nepoužívej pouhé holé "Dobrý den,"!
   - **Pouze pokud by nebyla známa ani firma ani osoba:** Použij "Dobrý den,".
2. **Struktura dopisu:**
   - **1. odstavec:** Jasná reakce na konkrétní pozici ve firmě, propojení se studiem/zkušenostmi z profilu a vysvětlení motivace pro danou pozici a typ úvazku.
   - **2. odstavec:** Propojení požadavků inzerátu s reálným profilem kandidáta (klíčové dovednosti, nástroje, jazyky nebo relevantní praxe).
   - **3. odstavec:** Přidaná hodnota kandidáta: technologická gramotnost, samostatnost, schopnost rychle se učit a efektivně využívat moderní digitální a AI nástroje.
   - **4. odstavec (Závěr):** Připravenost k nástupu, zmínka o přiloženém strukturovaném životopisu, poděkování za čas a těšení se na osobní setkání/pohovor.
   - **Podpis:**
     Hezký den,
     {cand_name}
3. **Autentičnost:** Žádná přehnaná klišé. Text musí působit sebevědomě, věcně, kultivovaně a přirozeně.

Vrať POUZE samotný text dopisu (žádné uvozovky, žádné úvodní komentáře).
"""

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
            ),
        )

        letter = response.text.strip()
        self.last_savings = savings
        return letter

    def refine_cover_letter(self, job: JobPosting, current_letter: str, feedback: str) -> str:
        """Přepracuje stávající průvodní dopis na základě zpětné vazby uživatele."""
        cand = self.profile_data.get("candidate", {})
        cand_name = cand.get("name", "Uchazeč")

        prompt = f"""
Jsi osobní zástupce kandidáta ({cand_name}). Kandidát si přečetl navržený průvodní dopis na pozici {job.title} ({job.company}) a má k němu tuto zpětnou vazbu / požadavek na úpravu:

### ZPĚTNÁ VAZBA OD KANDIDÁTA:
"{feedback}"

### PŮVODNÍ NÁVRH DOPISU:
{current_letter}

### INZERÁT:
{job.raw_text}

---

### POKYNY PRO ÚPRAVU:
1. Zapracuj přesně požadavky a připomínky od kandidáta (např. zmírnit tón, ubrat/přidat důraz na konkrétní dovednost, zkrátit, upravit styl).
2. Zachovej fakta o kandidátovi z jeho profilu.
3. Dodrž správné oslovení a podpis ({cand_name}).

Vrať POUZE upravený text dopisu (žádné komentáře navíc).
"""

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.4,
            ),
        )

        return response.text.strip()
