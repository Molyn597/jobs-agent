import json
import re
from dataclasses import dataclass
from typing import List, Optional
import requests
from bs4 import BeautifulSoup


@dataclass
class JobPosting:
    url: Optional[str]
    title: str
    company: str
    location: str
    work_type: str
    contact_person: Optional[str]
    raw_text: str
    full_html: str = ""


class JobsScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
        }

    def fetch_from_url(self, url: str) -> JobPosting:
        """Stáhne a vyparsuje inzerát z URL na Jobs.cz nebo Prace.cz."""
        resp = requests.get(url, headers=self.headers, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        posting = self.parse_html(resp.text, url=url)

        # Pokud jde o Jobs.cz, zkontrolujeme i /jof/{id}/ formulář pro zjištění pole 'Komu:'
        job_id_match = re.search(r"/rpd/(\d+)", url)
        if job_id_match and not posting.contact_person:
            job_id = job_id_match.group(1)
            jof_url = f"https://www.jobs.cz/jof/{job_id}/"
            try:
                jof_resp = requests.get(jof_url, headers=self.headers, timeout=10)
                if jof_resp.status_code == 200:
                    jof_soup = BeautifulSoup(jof_resp.text, "html.parser")
                    jof_text = jof_soup.get_text(separator=" ", strip=True)
                    match = re.search(r"Komu:\s*([A-ZÁ-Ž][a-zá-ž]+\s+[A-ZÁ-Ž][a-zá-ž]+)", jof_text)
                    if match:
                        posting.contact_person = match.group(1).strip()
            except Exception:
                pass

        return posting

    def parse_html(self, html_content: str, url: Optional[str] = None) -> JobPosting:
        """Vyparsuje strukturované informace z HTML kódu inzerátu."""
        soup = BeautifulSoup(html_content, "html.parser")

        title = ""
        company = ""
        location = ""
        work_type = ""
        contact_person = None

        # 1. Zkusíme vytáhnout strukturovaná metadata Schema.org JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = data[0]
                if isinstance(data, dict) and data.get("@type") in ("JobPosting", "http://schema.org/JobPosting"):
                    if not title and data.get("title"):
                        title = data["title"]
                    org = data.get("hiringOrganization")
                    if isinstance(org, dict) and org.get("name"):
                        company = org["name"]
                    elif isinstance(org, str):
                        company = org
                    loc = data.get("jobLocation")
                    if isinstance(loc, dict):
                        addr = loc.get("address")
                        if isinstance(addr, dict):
                            location = addr.get("addressLocality") or addr.get("streetAddress") or ""
                        elif isinstance(addr, str):
                            location = addr
                    if data.get("employmentType"):
                        work_type = str(data["employmentType"])
            except Exception:
                pass

        # 2. Fallback pro název pozice
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
            elif soup.title:
                title = soup.title.get_text(strip=True).split("|")[0].strip()

        # 3. Fallback pro firmu
        if not company:
            company_tag = soup.find(class_=re.compile(r"company|employer|brand|header__company", re.I))
            if company_tag:
                company = company_tag.get_text(strip=True)
            else:
                meta_author = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="og:author")
                if meta_author and meta_author.get("content"):
                    company = meta_author["content"].strip()

        # 4. Fallback pro lokalitu
        if not location:
            loc_tag = soup.find(class_=re.compile(r"locality|location|place|address", re.I))
            if loc_tag:
                location = loc_tag.get_text(strip=True)

        # 5. Fallback pro typ úvazku
        if not work_type:
            wt_tag = soup.find(class_=re.compile(r"contract|employment|workload", re.I))
            if wt_tag:
                work_type = wt_tag.get_text(strip=True)

        # 6. Hledání kontaktní osoby / personalisty
        contact_section = soup.find(class_=re.compile(r"contact|recruiter|person|author", re.I))
        if contact_section:
            c_text = contact_section.get_text(separator=" ", strip=True)
            name_match = re.search(
                r"(?:kontaktní osoba|kontakt|napsat|kontaktujte|komu)[:\s]+([A-ZÁ-Ž][a-zá-ž]+\s+[A-ZÁ-Ž][a-zá-ž]+)",
                c_text,
                re.IGNORECASE,
            )
            if name_match:
                contact_person = name_match.group(1).strip()

        # 7. Text inzerátu (odstranění zbytečností)
        for s in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
            s.decompose()

        main_content = soup.find("main") or soup.find("article") or soup.find(class_=re.compile(r"content|detail|body", re.I))
        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        cleaned_text = re.sub(r"\n\s*\n+", "\n\n", text).strip()

        return JobPosting(
            url=url,
            title=title or "Nespecifikovaná pozice",
            company=company or "Neuvedená společnost",
            location=location or "Praha",
            work_type=work_type or "Zkrácený úvazek / DPP / DPČ",
            contact_person=contact_person,
            raw_text=cleaned_text,
            full_html=html_content,
        )

    def extract_job_urls_from_search_page(self, html_content: str) -> List[str]:
        """Vytáhne jednotlivé odkazy na konkrétní pozice (/rpd/) ze stránky vyhledávání."""
        soup = BeautifulSoup(html_content, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/rpd/" in href:
                clean = href.split("?")[0]
                if clean.startswith("/"):
                    clean = "https://www.jobs.cz" + clean
                if clean not in links and not clean.endswith("/rpd/"):
                    links.append(clean)
        return links

    def fetch_live_search_jobs(self, keywords: List[str] = None, location: str = "praha") -> List[str]:
        """Prohledá přímo Jobs.cz a vrátí seznam všech aktuálních inzerátů splňujících filtry."""
        if not keywords:
            keywords = ["marketing", "analytik", "ekonomika"]

        params = [f"q%5B%5D={kw.lower()}" for kw in keywords]
        params.append("contract_type%5B%5D=part_time")
        params.append("contract_type%5B%5D=temporary")
        query_str = "&".join(params)

        search_url = f"https://www.jobs.cz/prace/{location}/?{query_str}"
        try:
            resp = requests.get(search_url, headers=self.headers, timeout=15)
            resp.raise_for_status()
            return self.extract_job_urls_from_search_page(resp.text)
        except Exception as e:
            print(f"Chyba při stahování vyhledávání z Jobs.cz: {e}")
            return []

    def extract_links_from_email_html(self, html_content: str) -> List[str]:
        """Vytáhne všechny relevantní odkazy na nabídky práce a tlačítko 'Zobrazit všechny'."""
        soup = BeautifulSoup(html_content, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            # Odkazy na konkrétní pozice nebo tlačítko zobrazit všechny
            if "jobs.cz" in href or "prace.cz" in href or "lmc" in href:
                if any(x in href for x in ["/rpd/", "/fp/", "/redirect", "/track", "/prace/"]):
                    if href not in links:
                        links.append(href)
                elif "zobrazit všechny" in text.lower():
                    if href not in links:
                        links.append(href)
        return links

    def parse_raw_text(
        self,
        text: str,
        title: str = "",
        company: str = "",
        contact_person: Optional[str] = None,
        location: str = "Praha",
        work_type: str = "Zkrácený úvazek / DPP",
    ) -> JobPosting:
        """Vytvoří JobPosting přímo z vloženého textu inzerátu."""
        return JobPosting(
            url=None,
            title=title or "Pozice z textu",
            company=company or "Společnost",
            location=location,
            work_type=work_type,
            contact_person=contact_person,
            raw_text=text.strip(),
        )
