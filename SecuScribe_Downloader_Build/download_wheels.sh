#!/bin/bash
# download_wheels.sh
set -euo pipefail

REQUIREMENTS_FILE="requirements.txt"
OUTPUT_DIR="./secuscribe_wheels"
ARCHIVE_NAME="secuscribe_wheels.tar.gz"

# Workaround für /tmp tmpfs Limitierung:
export TMPDIR="$(pwd)/pip_temp"
mkdir -p "$TMPDIR"

echo "[*] Starte SecuScribe Wheel-Downloader..."

if ! command -v python3 &> /dev/null; then
    echo "[!] Fehler: python3 ist nicht installiert."
    exit 1
fi

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "[!] Fehler: $REQUIREMENTS_FILE nicht im aktuellen Verzeichnis gefunden."
    exit 1
fi

echo "[*] Erstelle temporäre virtuelle Umgebung..."
python3 -m venv download_env
source download_env/bin/activate
pip install --upgrade pip

mkdir -p "$OUTPUT_DIR"
echo "[*] Lade Pakete in den Cache (Nutze $TMPDIR als Temp-Speicher)..."
pip download -r "$REQUIREMENTS_FILE" -d "$OUTPUT_DIR"

cp "$REQUIREMENTS_FILE" "$OUTPUT_DIR/"

echo "[*] Erstelle Archiv $ARCHIVE_NAME..."
tar -czvf "$ARCHIVE_NAME" "$OUTPUT_DIR"

echo "[*] Räume auf..."
deactivate
rm -rf download_env "$OUTPUT_DIR" "$TMPDIR"

echo "[*] Erfolgreich abgeschlossen! Datei: $ARCHIVE_NAME"