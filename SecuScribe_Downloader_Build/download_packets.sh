#!/bin/bash
# download_packets.sh
# Lädt die benötigten Debian-Pakete (.deb) für die Offline-Installation herunter
# und legt sie direkt in das wheels-Verzeichnis ab.

DEBS_DIR="./secuscribe_debs"
ARCHIVE_NAME="secuscribe_debs.tar.gz"
NOW_DIR="$(pwd)"

set -euo pipefail

echo "==> Erstelle temporäres Verzeichnis (im wheels-Ordner)..."
mkdir -p "$DEBS_DIR"

echo "==> Lade Paketquellen neu (APT Update)..."
sudo apt-get update

echo "==> Lade python3-venv und python3-pip inkl. Abhängigkeiten (nur Download)..."
sudo apt-get install --download-only -y python3-venv python3-pip

echo "==> Kopiere .deb Dateien aus dem apt-cache..."
# Kopiert alle geladenen Paket-Dateien aus dem System-Cache in unseren Ordner
sudo cp /var/cache/apt/archives/*.deb "$DEBS_DIR/"
sudo chown -R $USER "$DEBS_DIR"

echo "==> Erstelle Archiv $ARCHIVE_NAME..."
tar -czvf "$ARCHIVE_NAME" "$DEBS_DIR"
echo "[*] Räume auf..."
rm -rf "$DEBS_DIR"
echo ""
echo "==> ERFOLG! Die .deb Dateien liegen bereit unter: $NOW_DIR/$ARCHIVE_NAME"
