# SecuScribe

> **Sichere Offline-Transkription für VS-NfD-Umgebungen**  
> **Secure Offline Transcription for Classified Environments (VS-NfD)**

---

## Inhalt / Table of Contents

1. [Übersicht / Overview](#übersicht--overview)  
2. [Anforderungen / Requirements](#anforderungen--requirements)  
3. [Installation (BSI-gehärtet / BSI-hardened)](#installation-bsi-gehärtet--bsi-hardened)  
4. [Konfiguration / Configuration](#konfiguration--configuration)  
5. [Verwendung / Usage](#verwendung--usage)  
6. [Architektur / Architecture](#architektur--architecture)  
7. [Sicherheitshinweise / Security Notes](#sicherheitshinweise--security-notes)  
8. [Lizenz / Licence](#lizenz--licence)

---

## Übersicht / Overview

**DE:**  
SecuScribe ist ein vollständig offline betriebenes Transkriptionssystem, das für den Einsatz in VS-NfD-geprüften (Verschlusssache – Nur für den Dienstgebrauch) Umgebungen konzipiert wurde. Es verwendet `faster-whisper` für die ressourceneffiziente Spracherkennung, optionale Sprecherdiarisierung über `pyannote.audio` sowie ein unscharfes Glossarsystem (Fuzzy-Matching) für technische Fachbegriffe.

**EN:**  
SecuScribe is a fully offline transcription system designed for classified (VS-NfD) environments. It uses `faster-whisper` for resource-efficient speech recognition, optional speaker diarisation via `pyannote.audio`, and a fuzzy-logic glossary system for domain-specific technical terms.

---

## Anforderungen / Requirements

| Komponente | Mindest | Empfohlen |
|---|---|---|
| OS | Debian 12 | Debian 13 |
| Python | 3.11 | 3.12 |
| RAM | 8 GB | 24 GB |
| CPU | 4 Kerne | 8+ Kerne |
| Disk | 10 GB | 50 GB |
| GnuPG | 2.2+ | 2.4+ |

---

## Installation (BSI-gehärtet / BSI-hardened)

### 1. Systemvorbereitung / System preparation

```bash
# DE: Betriebssystem absichern / EN: Harden the base OS
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y gnupg python3 python3-pip python3-venv ffmpeg

# DE: AppArmor aktivieren / EN: Enable AppArmor
sudo systemctl enable apparmor --now
```

### 2. Virtuelle Umgebung / Virtual environment

```bash
git clone <repo-url> secuscribe
cd secuscribe
python3 -m venv .venv
source .venv/bin/activate
pip install --no-index --find-links /path/to/offline-packages -r requirements.txt
```

> **Hinweis (DE):** Alle Python-Pakete müssen *vor* der Luftspaltung (Air-Gapping) auf einem Transfermedium gespeichert werden:  
> **Note (EN):** All Python packages must be downloaded *before* air-gapping and stored on transfer media:
>
> ```bash
> pip download -r requirements.txt -d /media/usbstick/secuscribe-packages/
> ```

### 3. Whisper-Modell herunterladen / Download Whisper model

```bash
# DE: Vor der Luftspaltung ausführen / EN: Run before air-gapping
python3 -c "
from faster_whisper import WhisperModel
WhisperModel('small')   # 8-GB-Profil
# WhisperModel('large-v3')  # 24-GB-Profil
"
```

### 4. Diarisierungs-Modell (optional) / Diarisation model (optional)

```bash
# DE: pyannote-Modell vorher herunterladen (erfordert HuggingFace-Konto)
# EN: Download pyannote model beforehand (requires a HuggingFace account)
python3 -c "
from pyannote.audio import Pipeline
Pipeline.from_pretrained('pyannote/speaker-diarization-3.1',
                          use_auth_token='<HF_TOKEN>')
"
```

### 5. GPG-Schlüssel einrichten / Set up GPG key

```bash
# DE: Empfängerschlüssel importieren / EN: Import recipient key
gpg --import /media/usbstick/recipient-pubkey.asc
gpg --fingerprint <KEY-ID>
```

---

## Konfiguration / Configuration

Einstellungen werden über Umgebungsvariablen gesteuert / Settings are controlled via environment variables:

| Variable | Standard / Default | Beschreibung / Description |
|---|---|---|
| `SECUSCRIBE_PROFILE` | `8GB` | RAM-Profil: `8GB` oder `24GB` |
| `SECUSCRIBE_WATCH_DIR` | `./input` | Eingabeverzeichnis (Local Mode) |
| `SECUSCRIBE_OUTPUT_DIR` | `./output` | Ausgabeverzeichnis |
| `SECUSCRIBE_GLOSSARY` | `./glossary.json` | Pfad zur Glossardatei |
| `SECUSCRIBE_GPG_RECIPIENT` | *(leer)* | GPG-Schlüssel-ID des Empfängers |
| `SECUSCRIBE_LANG` | *(auto)* | Sprachcode, z. B. `de`, `en` |
| `SECUSCRIBE_FUZZY_THRESHOLD` | `85` | Fuzzy-Match-Schwellenwert (0–100) |
| `SECUSCRIBE_CONSENT_WINDOW` | `10` | Länge des Einwilligungsfensters (s) |
| `SECUSCRIBE_WEB_HOST` | `127.0.0.1` | Bind-Adresse des Webservers |
| `SECUSCRIBE_WEB_PORT` | `8000` | Port des Webservers |

### Glossar-Datei / Glossary file

Die Datei `glossary.json` enthält ein JSON-Objekt, das kanonische Begriffe auf phonetische Varianten abbildet / The `glossary.json` file maps canonical terms to phonetic variants:

```json
{
  "Verschlüsselung": ["Verschluesselung", "Verschlüssellung"],
  "BSI": ["B.S.I.", "B SI", "Besi"],
  "VS-NfD": ["VS NfD", "Fesnefde", "V.S. N.f.D."]
}
```

---

## Verwendung / Usage

### Local Mode (Freigegebener Ordner / Shared Folder)

```bash
export SECUSCRIBE_PROFILE=8GB
export SECUSCRIBE_GPG_RECIPIENT="security@behoerde.de"

python main.py watch
# DE: Audiodateien in ./input ablegen — werden automatisch verarbeitet.
# EN: Drop audio files into ./input — they will be processed automatically.
```

### Web Mode (FastAPI)

```bash
export SECUSCRIBE_PROFILE=24GB
python main.py serve
# DE: Erreichbar unter http://127.0.0.1:8000/docs
# EN: Available at http://127.0.0.1:8000/docs
```

```bash
# DE: Datei hochladen / EN: Upload a file
curl -X POST http://127.0.0.1:8000/upload \
     -F "file=@recording.wav" | python3 -m json.tool
```

### Einzel-Transkription / Single-file transcription

```bash
python main.py transcribe recording.wav --delete
# --delete: DSGVO-konforme Löschung der Audiodatei nach der Verarbeitung
#           GDPR-compliant deletion of the audio file after processing
```

---

## Architektur / Architecture

```
secuscribe/
├── main.py                  # CLI entry point
├── config.py                # Resource profiles & settings
├── requirements.txt         # Dependencies (MIT / Apache 2.0)
├── glossary.json            # Domain-specific glossary (example)
├── input/                   # Watch directory (Local Mode)
├── output/                  # Transcript output directory
└── secuscribe/
    ├── transcription.py     # Core: faster-whisper + diarisation + fuzzy glossary
    ├── cleanup.py           # GDPR: secure 3-pass overwrite + unlink
    ├── encryption.py        # GnuPG wrapper for output files
    ├── consent.py           # Verbal consent verification
    ├── watcher.py           # Local Mode: watchdog folder monitor
    └── web_server.py        # Web Mode: FastAPI upload endpoint
```

### Datenfluss / Data flow

```
Audio-Datei (input/)
      │
      ▼
[1] Verbal-Consent-Prüfung          ← consent.py
      │ (fehlgeschlagen → sofortiges Löschen)
      ▼
[2] Transkription                    ← transcription.py
      │   faster-whisper (offline)
      │   Sprecherdiarisierung (optional)
      │   Fuzzy-Glossar-Korrektur
      ▼
[3] Ausgabe schreiben               ← output/*.json, output/*.txt
      ▼
[4] GPG-Verschlüsselung (optional)  ← encryption.py
      ▼
[5] Sichere DSGVO-Löschung          ← cleanup.py (3-pass overwrite)
```

---

## Sicherheitshinweise / Security Notes

### BSI-Härtung / BSI Hardening

**DE:**
- Der Webserver bindet standardmäßig nur an `127.0.0.1`. Für netzwerkzugängliche Deployments ist ein mTLS-Reverse-Proxy (z. B. nginx) vorgeschrieben.
- Transkriptions-Ausgabedateien werden mit dem GPG-Schlüssel des Empfängers verschlüsselt, bevor sie das Ausgabeverzeichnis verlassen.
- Audiodateien werden nach der Verarbeitung mit 3 Überschreibungsdurchläufen gelöscht (BSI TR-02102-konform).
- Es werden keine externen API-Aufrufe durchgeführt. Das System ist vollständig luftlückenkompatibel.

**EN:**
- The web server binds to `127.0.0.1` by default. A mandatory mTLS reverse proxy (e.g. nginx) is required for network-accessible deployments.
- Transcript output files are encrypted with the recipient's GPG public key before leaving the output directory.
- Audio files are securely deleted using 3 overwrite passes after processing (BSI TR-02102 compliant).
- No external API calls are made. The system is fully air-gap compatible.

### DSGVO / GDPR

- **Art. 17 (Recht auf Löschung):** Audiodaten werden unmittelbar nach der Verarbeitung sicher gelöscht.
- **Art. 6 (Rechtmäßigkeit):** Die Verarbeitungseinwilligung wird durch das Voice-Consent-Modul zu Beginn jeder Aufnahme geprüft.
- **Art. 25 (Privacy by Design):** Minimale Datenspeicherung; keine Cloud-Dienste; vollständige Offline-Verarbeitung.

---

## Lizenz / Licence

MIT License — see `LICENSE` for details.

All bundled dependencies use enterprise-friendly open-source licences  
(MIT, Apache 2.0, or BSD-3-Clause). See `requirements.txt` for the  
complete list with licence annotations.
