#!/usr/bin/env bash
# ===============================================================
#   TürkAnime Yerel Arşiv Portalı - Başlatma Betiği (Linux / macOS)
# ===============================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Renksiz

echo "==================================================="
echo "  Arsivanime  ~  https://github.com/Slimsigara/arsivanime ..."
echo "  Adres: http://localhost:8000"
echo "==================================================="

# Python 3 kontrolü
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo -e "\033[0;31mHATA: Sistemde Python bulunamadı! Lütfen Python 3 kurun.\033[0m"
    exit 1
fi

# Sunucuyu başlat (Zip açma ve DB kontrolleri server.py tarafından otomatik yapılır)
exec $PYTHON_CMD server.py
