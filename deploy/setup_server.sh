#!/bin/bash
set -e

echo "========================================================"
echo "🚀 Automatická instalace a spuštění Jobs AI Agenta na Linuxu"
echo "========================================================"

# 1. Aktualizace balíčků a instalace Pythonu + Playwright závislostí
echo "📦 Instaluji systémové balíčky..."
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl

# 2. Vytvoření virtuálního prostředí
echo "🐍 Vytvářím Python virtuální prostředí..."
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalace Python knihoven
echo "📥 Instaluji Python závislosti..."
pip install --upgrade pip
pip install -r requirements.txt
playwright install-deps chromium
playwright install chromium

# 4. Nastavení systemd služby pro 24/7 běh
echo "⚙️ Nastavuji automatický 24/7 běh (systemd)..."
sudo cp deploy/jobs_agent.service /etc/systemd/system/jobs_agent.service
sudo systemctl daemon-reload
sudo systemctl enable jobs_agent
sudo systemctl restart jobs_agent

echo "========================================================"
echo "✅ HOTOVO! Jobs AI Asistent běží 24/7 na pozadí."
echo "Stav služby zkontroluješ příkazem: sudo systemctl status jobs_agent"
echo "========================================================"
