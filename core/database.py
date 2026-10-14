import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.scraper import JobPosting


class JobsDatabase:
    def __init__(self, db_path: str = "data/jobs_database.json"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jobs = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self.jobs, f, ensure_ascii=False, indent=2)

    def add_or_update_job(
        self,
        posting: JobPosting,
        analysis: Dict[str, Any],
        cover_letter: Optional[str] = None,
        status: str = "Nalezeno",
    ) -> str:
        job_key = posting.url or f"{posting.company}_{posting.title}"

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        existing = self.jobs.get(job_key, {})

        fit_score = analysis.get("fit_score", 0)
        category = analysis.get("category", "Nespecifikováno")
        summary = analysis.get("summary", "")
        responsibilities = analysis.get("responsibilities", [])
        requirements = analysis.get("requirements", [])
        why_it_fits = analysis.get("why_it_fits", [])

        if fit_score >= 80:
            badge = "🟢 Vhodné"
        elif fit_score >= 50:
            badge = "🟡 Méně vhodné"
        else:
            badge = "🔴 Seniorní / Nevhodné"

        record = {
            "key": job_key,
            "url": posting.url or "",
            "title": posting.title,
            "company": posting.company,
            "location": posting.location,
            "work_type": posting.work_type,
            "contact_person": posting.contact_person or "Neuvedena",
            "fit_score": fit_score,
            "category": category,
            "badge": badge,
            "summary": summary,
            "responsibilities": responsibilities,
            "requirements": requirements,
            "why_it_fits": why_it_fits,
            "cover_letter": cover_letter or existing.get("cover_letter", ""),
            "status": status if status != "Nalezeno" else existing.get("status", badge),
            "created_at": existing.get("created_at", now_str),
            "updated_at": now_str,
        }

        self.jobs[job_key] = record
        self._save()
        return job_key

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        jobs_list = list(self.jobs.values())
        jobs_list.sort(key=lambda x: x.get("fit_score", 0), reverse=True)
        return jobs_list

    def get_stats(self) -> Dict[str, Any]:
        jobs = list(self.jobs.values())
        total = len(jobs)
        high_fit = sum(1 for j in jobs if j.get("fit_score", 0) >= 80)
        medium_fit = sum(1 for j in jobs if 50 <= j.get("fit_score", 0) < 80)
        low_fit = sum(1 for j in jobs if j.get("fit_score", 0) < 50)
        applied = sum(1 for j in jobs if "Odesláno" in j.get("status", ""))

        categories = {}
        for j in jobs:
            cat = j.get("category", "Ostatní")
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total": total,
            "high_fit": high_fit,
            "medium_fit": medium_fit,
            "low_fit": low_fit,
            "applied": applied,
            "categories": categories,
        }

    def generate_html_dashboard(self, output_path: str = "dashboard.html") -> str:
        jobs = self.get_all_jobs()
        stats = self.get_stats()
        jobs_json = json.dumps(jobs, ensure_ascii=False)

        html_content = f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Jobs.cz AI Kariérní Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --border: #1f2937;
      --text-main: #f9fafb;
      --text-muted: #9ca3af;
      --accent: #3b82f6;
      --green: #10b981;
      --yellow: #f59e0b;
      --red: #ef4444;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      background: var(--bg);
      color: var(--text-main);
      padding: 30px;
      line-height: 1.5;
    }}
    .container {{ max-width: 1300px; margin: 0 auto; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 30px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 20px;
    }}
    .logo-title h1 {{ font-size: 24px; font-weight: 800; display: flex; align-items: center; gap: 10px; }}
    .logo-title p {{ color: var(--text-muted); font-size: 14px; margin-top: 4px; }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 30px;
    }}
    .metric-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      padding: 20px;
      border-radius: 14px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .metric-label {{ font-size: 13px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
    .metric-val {{ font-size: 32px; font-weight: 800; }}
    .metric-val.green {{ color: var(--green); }}
    .metric-val.yellow {{ color: var(--yellow); }}
    .metric-val.blue {{ color: var(--accent); }}
    
    .toolbar {{
      display: flex;
      gap: 12px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }}
    .search-box {{
      flex: 1;
      min-width: 280px;
      position: relative;
    }}
    .search-box input {{
      width: 100%;
      background: var(--card-bg);
      border: 1px solid var(--border);
      padding: 12px 16px;
      border-radius: 10px;
      color: #fff;
      font-size: 14px;
      outline: none;
    }}
    .filter-btn {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 10px 16px;
      border-radius: 10px;
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
      transition: all 0.2s;
    }}
    .filter-btn.active, .filter-btn:hover {{
      background: var(--border);
      color: #fff;
    }}

    .table-container {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
    }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; }}
    th {{
      background: #161f30;
      padding: 14px 18px;
      font-weight: 700;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      font-size: 12px;
      text-transform: uppercase;
    }}
    td {{
      padding: 16px 18px;
      border-bottom: 1px solid var(--border);
      vertical-align: middle;
    }}
    tr:hover td {{ background: rgba(255,255,255,0.02); }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 700;
    }}
    .badge.green {{ background: rgba(16, 185, 129, 0.15); color: var(--green); }}
    .badge.yellow {{ background: rgba(245, 158, 11, 0.15); color: var(--yellow); }}
    .badge.red {{ background: rgba(239, 68, 68, 0.15); color: var(--red); }}
    
    .btn {{
      background: var(--accent);
      color: #fff;
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: none;
      cursor: pointer;
    }}
    .btn.outline {{
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-main);
    }}
    .btn.outline:hover {{ background: var(--border); }}

    /* Modal */
    .modal {{
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.75);
      backdrop-filter: blur(4px);
      z-index: 1000;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }}
    .modal.active {{ display: flex; }}
    .modal-content {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 16px;
      width: 100%;
      max-width: 800px;
      max-height: 90vh;
      overflow-y: auto;
      padding: 30px;
    }}
    .modal-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 15px;
    }}
    .close-btn {{ background: none; border: none; color: var(--text-muted); font-size: 24px; cursor: pointer; }}
    .letter-box {{
      background: #0b0f19;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px;
      font-family: monospace;
      font-size: 13px;
      white-space: pre-wrap;
      margin-top: 15px;
      line-height: 1.6;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo-title">
        <h1>🎯 Jobs.cz AI Kariérní Hub</h1>
        <p>Automatizovaný přehled a analýza pracovních příležitostí</p>
      </div>
      <div>
        <span class="badge green">● Aktivní (24/7 Cloud)</span>
      </div>
    </header>

    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">Celkem zanalyzováno</div>
        <div class="metric-val blue">{stats['total']}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Vhodné pozice (80–100 %)</div>
        <div class="metric-val green">{stats['high_fit']}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Vyšší nároky (50–79 %)</div>
        <div class="metric-val yellow">{stats['medium_fit']}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Odeslané přihlášky</div>
        <div class="metric-val blue">{stats['applied']}</div>
      </div>
    </div>

    <div class="toolbar">
      <div class="search-box">
        <input type="text" id="searchInput" placeholder="🔍 Hledat podle pozice, firmy, lokality nebo dovednosti (např. Canva, Excel)..." onkeyup="filterJobs()">
      </div>
      <button class="filter-btn active" onclick="setFilter('all', this)">Všechny ({stats['total']})</button>
      <button class="filter-btn" onclick="setFilter('green', this)">🟢 Pouze vhodné ({stats['high_fit']})</button>
      <button class="filter-btn" onclick="setFilter('marketing', this)">Marketing</button>
      <button class="filter-btn" onclick="setFilter('data', this)">Analytika / Data</button>
    </div>

    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Shoda</th>
            <th>Pozice a Společnost</th>
            <th>Lokalita & Úvazek</th>
            <th>Kategorie</th>
            <th>Datum</th>
            <th style="text-align: right;">Akce</th>
          </tr>
        </thead>
        <tbody id="jobsTableBody">
          <!-- Dynamicky renderováno -->
        </tbody>
      </table>
    </div>
  </div>

  <!-- Detail Modal -->
  <div class="modal" id="jobModal">
    <div class="modal-content">
      <div class="modal-header">
        <div>
          <h2 id="modalTitle" style="font-size: 20px;">Název pozice</h2>
          <p id="modalCompany" style="color: var(--accent); font-weight: 600; margin-top: 4px;">Firma</p>
        </div>
        <button class="close-btn" onclick="closeModal()">&times;</button>
      </div>

      <div style="margin-bottom: 20px;">
        <h4 style="font-size: 14px; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">📝 Manažerské shrnutí:</h4>
        <p id="modalSummary" style="font-size: 14px; color: #e5e7eb;"></p>
      </div>

      <div style="margin-bottom: 20px;">
        <h4 style="font-size: 14px; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">💡 Proč se hodí:</h4>
        <ul id="modalWhyFits" style="padding-left: 20px; font-size: 14px; color: #e5e7eb;"></ul>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 25px;">
        <h4 style="font-size: 14px; text-transform: uppercase; color: var(--text-muted);">✉️ Vygenerovaný průvodní dopis:</h4>
        <button class="btn outline" onclick="copyLetter()">📋 Zkopírovat dopis</button>
      </div>
      <div class="letter-box" id="modalLetter"></div>

      <div style="margin-top: 25px; display: flex; justify-content: flex-end; gap: 10px;">
        <a id="modalJobsLink" href="#" target="_blank" class="btn">🌐 Otevřít inzerát na Jobs.cz</a>
        <button class="btn outline" onclick="closeModal()">Zavřít</button>
      </div>
    </div>
  </div>

  <script>
    const allJobs = {jobs_json};
    let currentFilter = 'all';

    function renderTable(jobs) {{
      const tbody = document.getElementById('jobsTableBody');
      if (jobs.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 40px; color: var(--text-muted);">Žádné inzeráty neodpovídají zadanému filtru.</td></tr>';
        return;
      }}

      tbody.innerHTML = jobs.map(j => {{
        const badgeClass = j.fit_score >= 80 ? 'green' : (j.fit_score >= 50 ? 'yellow' : 'red');
        return `
          <tr>
            <td><span class="badge ${{badgeClass}}">${{j.fit_score}} %</span></td>
            <td>
              <div style="font-weight: 700; color: #fff;">${{j.title}}</div>
              <div style="color: var(--text-muted); font-size: 13px;">${{j.company}}</div>
            </td>
            <td>
              <div>${{j.location}}</div>
              <div style="color: var(--text-muted); font-size: 12px;">${{j.work_type}}</div>
            </td>
            <td><span style="font-size: 13px; color: var(--text-muted);">${{j.category}}</span></td>
            <td style="color: var(--text-muted); font-size: 13px;">${{j.created_at || 'Dnes'}}</td>
            <td style="text-align: right;">
              <button class="btn outline" onclick="openDetail('${{j.key}}')">📄 Detail & Dopis</button>
            </td>
          </tr>
        `;
      }}).join('');
    }}

    function filterJobs() {{
      const query = document.getElementById('searchInput').value.toLowerCase();
      let filtered = allJobs.filter(j => {{
        const matchesQuery = j.title.toLowerCase().includes(query) ||
                             j.company.toLowerCase().includes(query) ||
                             j.summary.toLowerCase().includes(query) ||
                             j.location.toLowerCase().includes(query);

        if (!matchesQuery) return false;

        if (currentFilter === 'green') return j.fit_score >= 80;
        if (currentFilter === 'marketing') return j.category.toLowerCase().includes('marketing');
        if (currentFilter === 'data') return j.category.toLowerCase().includes('analytik') || j.category.toLowerCase().includes('data');
        return true;
      }});

      renderTable(filtered);
    }}

    function setFilter(filter, el) {{
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      el.classList.add('active');
      currentFilter = filter;
      filterJobs();
    }}

    function openDetail(key) {{
      const job = allJobs.find(j => j.key === key);
      if (!job) return;

      document.getElementById('modalTitle').textContent = job.title;
      document.getElementById('modalCompany').textContent = job.company + ' | ' + job.location;
      document.getElementById('modalSummary').textContent = job.summary;
      
      const whyList = document.getElementById('modalWhyFits');
      whyList.innerHTML = (job.why_it_fits || []).map(w => `<li>${{w}}</li>`).join('');

      document.getElementById('modalLetter').textContent = job.cover_letter || 'Dopis nebyl zatím vygenerován.';
      
      const link = document.getElementById('modalJobsLink');
      if (job.url) {{
        link.href = job.url;
        link.style.display = 'inline-flex';
      }} else {{
        link.style.display = 'none';
      }}

      document.getElementById('jobModal').classList.add('active');
    }}

    function closeModal() {{
      document.getElementById('jobModal').classList.remove('active');
    }}

    function copyLetter() {{
      const text = document.getElementById('modalLetter').textContent;
      navigator.clipboard.writeText(text).then(() => {{
        alert('✅ Průvodní dopis byl zkopírován do schránky!');
      }});
    }}

    // Výchozí render
    renderTable(allJobs);
  </script>
</body>
</html>"""
        out_file = Path(output_path)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"📊 Dashboard vygenerován: {out_file.resolve()}")
        return str(out_file.resolve())
