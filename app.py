import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Načtení .env pokud existuje
load_dotenv()

from core.scraper import JobsScraper
from core.analyzer import JobAnalyzer
from core.generator import CoverLetterGenerator


def process_job(posting, output_file: str = None):
    print("=" * 70)
    print(f"📌 ZPRACOVÁNÍ NABÍDKY: {posting.title} ({posting.company})")
    print("=" * 70)

    analyzer = JobAnalyzer()
    generator = CoverLetterGenerator()

    print("\n🔍 Provádím analýzu inzerátu vůči tvému profilu...")
    analysis = analyzer.analyze(posting)

    fit_score = analysis.get("fit_score", 0)
    category = analysis.get("category", "Nespecifikováno")
    summary = analysis.get("summary", "")
    responsibilities = analysis.get("responsibilities", [])
    requirements = analysis.get("requirements", [])
    why_it_fits = analysis.get("why_it_fits", [])
    strengths = analysis.get("key_strengths_to_highlight", [])
    risks = analysis.get("potential_risks_or_notes", "")

    print(f"\n📊 SHODA S PROFILEM (FIT SCORE): {fit_score} %")
    print(f"🏷️ KATEGORIE: {category}")
    print(f"📍 LOKALITA & ÚVAZEK: {posting.location} | {posting.work_type}")

    print("\n📝 MANAŽERSKÉ SHRNUTÍ INZERÁTU:")
    print(f"   {summary}")

    if responsibilities:
        print("\n🛠️ CO BUDE TVÁ NÁPLŇ PRÁCE:")
        for r in responsibilities:
            print(f"   • {r}")

    if requirements:
        print("\n🎯 CO OD TEBE OČEKÁVAJÍ:")
        for req in requirements:
            print(f"   • {req}")

    print("\n💡 PROČ SE K TOBĚ NABÍDKA HODÍ:")
    for point in why_it_fits:
        print(f"   • {point}")

    if strengths:
        print("\n⭐ KLÍČOVÉ BODY KE ZDŮRAZNĚNÍ:")
        for s in strengths:
            print(f"   ✓ {s}")

    if risks:
        print(f"\n⚠️ POZNÁMKA / UPOZORNĚNÍ: {risks}")

    print("\n✍️ Generuji personalizovaný průvodní dopis na míru...")
    cover_letter = generator.generate_cover_letter(posting, analysis)

    print("\n" + "=" * 70)
    print("✉️ NÁVRH PRŮVODNÍHO DOPISU:")
    print("=" * 70)
    print(cover_letter)
    print("=" * 70)

    if output_file:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"POZICE: {posting.title} - {posting.company}\n")
            f.write(f"URL: {posting.url or 'Neuvedeno'}\n")
            f.write(f"FIT SCORE: {fit_score}%\n\n")
            f.write("--- SHRNUTÍ ---\n")
            f.write(f"{summary}\n\n")
            f.write("--- PRŮVODNÍ DOPIS ---\n")
            f.write(cover_letter)
        print(f"\n💾 Výsledek byl uložen do: {out_path.resolve()}")

    return analysis, cover_letter


def run_demo():
    print("🚀 Spouštím demonstrační test na reálném vzoru inzerátu (Junior Marketing Coordinator)...")
    scraper = JobsScraper()

    sample_text = """
    Společnost Ukázkové Reality hledá do svého pražského týmu posilu na pozici Junior Marketing Coordinator.
    Lokalita: Praha – Nové Město.
    Úvazek: Zkrácený úvazek / DPP / DPČ (cca 20 hod/týdně), vhodné pro studenty VŠ.
    
    Náplň práce:
    - Příprava marketingových materiálů, vizuálů a prezentací (práce v Canvě, Photoshopu).
    - Správa firemních sociálních sítí a pomoc s tvorbou obsahu.
    - Koordinace e-mailingových kampaní a reporting výsledků.
    - Komunikace s mezinárodními pobočkami v angličtině.
    
    Požadavky:
    - Student VŠ (ideálně marketingového nebo ekonomického směru).
    - Výborná znalost angličtiny (B2/C1) slovem i písmem.
    - Zkušenost s grafickými nástroji (Canva / Adobe) a MS Office.
    - Samostatnost, kreativita a chuť učit se novým věcem.
    
    Kontaktní osoba: Mgr. Lenka Dvořáková (HR Specialist)
    """

    posting = scraper.parse_raw_text(
        text=sample_text,
        title="Junior Marketing Coordinator",
        company="Ukázkové Reality, s.r.o.",
    )
    posting.contact_person = "Mgr. Lenka Dvořáková"
    posting.location = "Praha – Nové Město"
    posting.work_type = "Zkrácený úvazek / DPP (20 h/týdně)"

    process_job(posting)


def main():
    parser = argparse.ArgumentParser(description="Jobs.cz AI Career & Application Agent")
    parser.add_argument("--url", type=str, help="URL inzerátu na Jobs.cz")
    parser.add_argument("--text", type=str, help="Vložený text inzerátu")
    parser.add_argument("--file", type=str, help="Cesta k textovému souboru s inzerátem")
    parser.add_argument("--demo", action="store_true", help="Spustit demonstrační ukázku")
    parser.add_argument("--contact", type=str, help="Jméno kontaktní osoby / personalisty (např. 'Jana Malá')")
    parser.add_argument("--company", type=str, help="Název firmy (např. 'BOHEMIA INTERACTIVE a.s.')")
    parser.add_argument("--title", type=str, help="Název pozice")
    parser.add_argument("--output", type=str, help="Cesta pro uložení vygenerovaného dopisu")

    args = parser.parse_args()

    scraper = JobsScraper()

    if args.demo:
        run_demo()
    elif args.url:
        print(f"🌐 Stahuji inzerát z URL: {args.url}")
        posting = scraper.fetch_from_url(args.url)
        if args.contact:
            posting.contact_person = args.contact
        if args.company:
            posting.company = args.company
        if args.title:
            posting.title = args.title
        process_job(posting, output_file=args.output)
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
        posting = scraper.parse_raw_text(
            text=text,
            title=args.title or "Pracovní pozice",
            company=args.company or "Společnost",
            contact_person=args.contact,
        )
        process_job(posting, output_file=args.output)
    elif args.text:
        posting = scraper.parse_raw_text(
            text=args.text,
            title=args.title or "Pracovní pozice",
            company=args.company or "Společnost",
            contact_person=args.contact,
        )
        process_job(posting, output_file=args.output)
    else:
        print("💡 Použití: python app.py --demo | --url <jobs_url> [--contact 'Jméno'] [--company 'Firma']")
        print("Spouštím demo jako ukázku...")
        run_demo()


if __name__ == "__main__":
    main()
