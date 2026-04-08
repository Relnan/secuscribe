#!/bin/bash
# download_models.sh
set -euo pipefail

HF_TOKEN=${1:-""}

if [ -z "$HF_TOKEN" ]; then
    echo "[!] FEHLER: HuggingFace Token fehlt. Nutzung: $0 <DEIN_HF_TOKEN>"
    exit 1
fi

BASE_DIR="./secuscribe_models"
ARCHIVE_NAME="secuscribe_models.tar.gz"

echo "[*] Starte Model-Downloader für SecuScribe..."

python3 -m venv hf_env
source hf_env/bin/activate
pip install --upgrade pip huggingface_hub

mkdir -p "$BASE_DIR/whisper/large-v3"
mkdir -p "$BASE_DIR/pyannote/speaker-diarization-3.1"
mkdir -p "$BASE_DIR/pyannote/segmentation-3.0"
mkdir -p "$BASE_DIR/llm"

echo "[*] Lade Faster-Whisper Model (large-v3)..."
huggingface-cli download Systran/faster-whisper-large-v3 --local-dir "$BASE_DIR/whisper/large-v3" --local-dir-use-symlinks False

echo "[*] Lade Pyannote Segmentation Model..."
huggingface-cli download pyannote/segmentation-3.0 --local-dir "$BASE_DIR/pyannote/segmentation-3.0" --local-dir-use-symlinks False --token "$HF_TOKEN"

echo "[*] Lade Pyannote Diarization Model..."
huggingface-cli download pyannote/speaker-diarization-3.1 --local-dir "$BASE_DIR/pyannote/speaker-diarization-3.1" --local-dir-use-symlinks False --token "$HF_TOKEN"

echo "[*] Lade Llama-3-8B-Instruct..."
huggingface-cli download QuantFactory/Meta-Llama-3-8B-Instruct-GGUF Meta-Llama-3-8B-Instruct.Q4_K_M.gguf --local-dir "$BASE_DIR/llm" --local-dir-use-symlinks False

echo "[*] Erstelle Archiv $ARCHIVE_NAME..."
tar -czvf "$ARCHIVE_NAME" "$BASE_DIR"

echo "[*] Räume auf..."
deactivate
rm -rf hf_env "$BASE_DIR"

echo "[*] Erfolgreich abgeschlossen! Datei: $ARCHIVE_NAME"