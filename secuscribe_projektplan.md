# Projektbeschreibung und Projektplan: secuscribe

**Repository:** `secuscribe` (secure transcription VM)
**Plattform:** Bare Metal Debian 13 (Trixie)
**Sicherheitsklassifizierung:** VS-NFD (Verschlusssache – Nur für den Dienstgebrauch)
**Architektur-Typ:** Kiosk / Blackbox Appliance (Immutable Infrastructure)

---

## 1. Projektbeschreibung

Das Projekt **secuscribe** umfasst die Konzeption und Implementierung einer hochsicheren, ressourceneffizienten und vollständig offline-fähigen (Air-Gapped) Transkriptions-Umgebung. Das System verarbeitet lokal bereitgestellte Audio- und Videodateien, extrahiert Transkripte und Sprecherzuordnungen (Diarization), korrigiert Fachbegriffe und generiert Zusammenfassungen. 

Die VM wird als statische Appliance ("Zero-Touch-Setup") über ein parametrisierbares Bash-Skript provisioniert und kennt zwei Lebenszyklen (`--env dev` oder `--env prod`) sowie zwei exklusive Daten-Ingress-Methoden (`--ingress web` oder `--ingress shared`). Ein Wechsel von einer Development- zu einer Production-Instanz ist untersagt; die Systeme werden als "Wegwerf-Ressourcen" behandelt.

### 1.1 Kernfunktionen und Pipeline-Logik
1. **Ingest & Validation:** Temporäre Übernahme der Rohdaten via lokalem Web-Upload (`secuscribe-web.service`) oder überwachtem Shared Folder (`/mnt/hypervisor_share/queue`) in eine flüchtige RAM-Disk (`tmpfs`).
2. **Preprocessing:** Normalisierung der Audiospuren (16kHz, Mono) mittels FFmpeg.
3. **Consent Check:** Verifikation der Zustimmung (Metadaten oder Audio-Intro). Hard-Stop bei fehlender Zustimmung.
4. **Serielle Inferenz:**
   - Text-Transkription via `faster-whisper`.
   - Sprechererkennung via `pyannote.audio`.
   - Striktes Laden und Entladen der Modelle zur Vermeidung von OOM-Fehlern.
5. **Post-Processing:** Timestamp-Merging und Glossar-Korrektur via `thefuzz`.
6. **LLM Integration:** Ein quantisiertes lokales LLM (`llama-cpp-python`) übernimmt das Gegenlesen und die strukturierte Zusammenfassung mittels Jinja2-Templates.
7. **Export & Verschlüsselung:** Erstellung der Zieldokumente (DOCX, PDF, MD) in `/done`. Optionale GnuPG-Verschlüsselung (Public Key: `Daniel_Potschka_Testkey_1`).
8. **Secure Wipe:** Vollständige Vernichtung der Dateien durch `shred -u -z` und Cleanup der RAM-Disk.

### 1.2 BSI IT-Grundschutz & VS-NFD Härtung

**HINWEIS ZUR HÄRTUNG (VS-NFD): Persistenzvermeidung und Read-Only Root.** Das Dateisystem (Root) der VM wird nach dem Setup für den Worker-Prozess als `ProtectSystem=strict` (Read-Only) gemountet. Alle Schreibzugriffe für die Datenverarbeitung erfolgen in einem Swap-freien `tmpfs`. 

**HINWEIS ZUR HÄRTUNG (VS-NFD): Ingress und Rechte-Trennung.** Es existieren zwei dedizierte Service-User ohne Login-Shell. `secu_transfer` verwaltet den Ingress (Web-Upload TLS 1.3 oder Shared Folder Queue). `secu_worker` führt die Verarbeitung mit eingeschränkten Kernel Capabilities und Netzwerk-Isolation (`PrivateNetwork=yes`) aus. 

**HINWEIS ZUR HÄRTUNG (VS-NFD): Ingress Shared Folder.** Bei Nutzung von `--ingress shared` wird der Hypervisor-Mount zwingend mit den Parametern `noexec`, `nosuid` und `nodev` konfiguriert, um die Ausführung eingeschleusten Schadcodes auf Kernel-Ebene zu blockieren.

---

## 2. Projektplan (Meilensteine & Phasen)

### Phase 1: Provisionierung, System-Härtung und Ingress-Routing (`setup_secuscribe_vm.sh`)
* **1.1** Skript-Ausführung mit Parametrisierung (z.B. `--env prod --ingress web`).
* **1.2** User-Anlage (`secu_transfer`, `secu_worker`) und Basis-Härtung (Swap off, `nftables` Drop All).
* **1.3** Konfiguration von `/etc/fstab` für RAM-Disk und optionalen Shared Folder (`noexec`).
* **1.4** Optional: Installation FastAPI/Uvicorn und TLS-Zertifikatserstellung für den lokalen Web-Ingress.

### Phase 2: Offline-Bereitstellung der Applikation
* **2.1** Anlage der Verzeichnisse (`/opt/secuscribe/`) gemäß Vorgaben.
* **2.2** Aufbau des Python `.venv` und Installation der Packages aus lokalen `.whl` Dateien.
* **2.3** Transfer der vorab verifizierten Modelle (Whisper, Pyannote, Llama) in das Offline-Verzeichnis.
* **2.4** Import des `Daniel_Potschka_Testkey_1` in den GnuPG-Keyring.

### Phase 3: Backend-Entwicklung (Core Pipeline)
* **3.1** `web_ingress.py` (FastAPI für `--ingress web`) oder `folder_poller.py` (für `--ingress shared`).
* **3.2** `audio_processor.py` (FFmpeg) und `consent_validator.py`.
* **3.3** `transcription_engine.py` (Serielles Memory-Management für Whisper/Pyannote).
* **3.4** `llm_service.py` (Llama-cpp Integration & Jinja2 Templates).
* **3.5** `export_service.py` (GnuPG, PDF, DOCX) und `secure_cleanup.py` (`shred` Aufrufe).

### Phase 4: Systemd Service-Design und Final Lockdown
* **4.1** Erstellung `secuscribe.service` (Worker) und ggf. `secuscribe-web.service` (Web).
* **4.2** Einbindung von Systemd Sandboxing (NoNewPrivileges, ProtectSystem).
* **4.3** Ausführung der Shutdown-Routinen für den Prod-Modus (Deaktivierung von SSH, Kernel Lockdown).

### Phase 5: Testing (Wegwerf-VMs)
* **5.1** Instanziierung einer VM mit `--env dev`. Funktionstest, Lasttest, Audit.
* **5.2** Zerstörung der Dev-VM.
* **5.3** Instanziierung einer neuen VM mit `--env prod`. Finale Abnahme.