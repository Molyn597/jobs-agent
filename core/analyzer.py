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


class JobAnalyzer:
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
                f"Profil nenalezen: {self.profile_path}. "
                f"Zkopírujte config/profile.example.json do config/profile.json a vyplňte své údaje."
            )
        with open(self.profile_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def analyze(self, job: JobPosting) -> Dict[str, Any]:
        """Analyzuje inzerát vůči profilu kandidáta a vrátí strukturované hodnocení."""
        # TOON-encode the candidate profile (smaller token footprint for the prompt)
        baseline_json = json.dumps(self.profile_data, ensure_ascii=False, indent=2)
        if encode_toon:
            profile_toon = encode_toon(self.profile_data)
            savings = record_savings(AGENT_NAME, self.model_name, baseline_json, profile_toon)
        else:
            profile_toon = baseline_json
            savings = {}
        prompt = f"""
Jsi manažerský AI analytik a kariérní poradce. Tvým úkolem je zanalyzovat pracovní inzerát a vyhodnotit shodu s kandidátem.

### PROFIL KANDIDÁTA (TOON format - mensi token footprint):
{profile_toon}

### PRAVIDLA PRO HODNOCENÍ SHODY (FIT SCORE 0-100 %):
- **ZÁSADNÍ PRAVIDLO SENIORITY:** Kandidát hledá pozice odpovídající preferencím a senioritě uvedeným v profilu (např. Junior, Trainee, Asistent, Stáž či zkrácený úvazek dle profilu).
- **80–100 % (🟢 Perfektní match):** Pozice odpovídá dovednostem, preferovaným oborům a časové kapacitě kandidáta.
- **0–49 % (🔴 NEVHODNÉ / VYŘADIT):** 
  * Pozice vyžadující výrazně vyšší senioritu (např. Senior, Lead, Head of, Ředitel) v rozporu s preferencemi.
  * Pozice vyžadující plný úvazek, pokud kandidát v profilu požaduje flexibilní / zkrácený úvazek.
  * Zcela jiný obor v rozporu se zaměřením kandidáta.

Pokud je v názvu či požadavcích slovo 'Specialista', 'Specialist', 'Manažer', 'Manager', 'Senior', 'Lead' (a není to např. 'Junior specialista' nebo 'Asistent manažera'), MUSÍŠ udělit skóre POD 50 % a v "potential_risks_or_notes" uvést: "⚠️ Pozice je na úrovni specialisty/manažera, což neodpovídá požadovanému juniornímu profilu."

### INZERÁT K ANALÝZE:
- **Název pozice:** {job.title}
- **Společnost:** {job.company}
- **Lokalita:** {job.location}
- **Typ úvazku / Poznámky:** {job.work_type}
- **Kontaktní osoba:** {job.contact_person or "Neuvedena"}
- **Celý text inzerátu:**
{job.raw_text}

---

### POŽADAVKY NA VÝSTUP (JSON formát):
Vrať POUZE validní JSON objekt s touto strukturou:
{{
  "fit_score": <číslo 0-100 vyjadřující celkovou shodu s profilem a preferencemi>,
  "category": "<jedna z: 'Marketing & Content' | 'Analytika & Reporting' | 'Administrativa & Podpora' | 'Jiné'>",
  "summary": "<stručné shrnutí pozice, náplně práce a hlavních požadavků ve 2-3 větách>",
  "responsibilities": [
    "<bod 1: konkrétní činnost a náplň práce, co bude kandidát dělat>",
    "<bod 2: další činnost>",
    "<bod 3: další činnost>"
  ],
  "requirements": [
    "<bod 1: co od kandidáta firma požaduje / očekává>",
    "<bod 2: další požadavek / předpoklad>"
  ],
  "why_it_fits": [
    "<bod 1: konkrétní důvod, proč se pozice ke kandidátovi skvěle hodí>",
    "<bod 2: souvislost s jeho studiem, praxí nebo dovednostmi>",
    "<bod 3: jazyková / technologická shoda>"
  ],
  "key_strengths_to_highlight": [
    "<konkrétní schopnost či zkušenost, kterou je nutné zdůraznit v průvodním dopise>"
  ],
  "potential_risks_or_notes": "<poznámka k úvazku, požadavkům na zkušenosti nebo směru, pokud existuje>"
}}
"""

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        try:
            result = json.loads(response.text)
            result["_toon_savings"] = savings
            return result
        except json.JSONDecodeError:
            return {
                "fit_score": 50,
                "category": "Nerozpoznáno",
                "summary": response.text[:200],
                "responsibilities": [],
                "requirements": [],
                "why_it_fits": ["Chyba při parsování JSON odpovědi."],
                "key_strengths_to_highlight": [],
                "potential_risks_or_notes": "",
                "_toon_savings": savings,
            }
