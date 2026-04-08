# **Installationsanleitung: Basis-Betriebssystem Debian 13 (Bare Metal / VM)**

**Projekt:** secuscribe (secure transcription VM)  
**Klassifizierung:** VS-NFD (Verschlusssache – Nur für den Dienstgebrauch)  
**Zielsystem:** Debian 13 (Trixie) – Minimalinstallation  
Diese Anleitung beschreibt die manuelle Basis-Installation des Gastsystems sowie den sicheren Transfer der Offline-Abhängigkeiten von einem Windows-Hostsystem, bevor das automatisierte Provisionierungs-Skript (setup\_secuscribe\_vm.sh) ausgeführt wird.

## **1\. Systemvoraussetzungen und Vorbereitung**

1. **Installationsmedium:** Laden Sie das **offizielle, vollständige Debian 13 (Trixie) DVD-ISO** (Full Offline-Installationsmedium) herunter. *WICHTIG: Verwenden Sie NICHT das kleine "Netinst"-ISO. Da die VM während der Installation keinen Internetzugang hat, muss das Installationsmedium alle benötigten Pakete (insbesondere den SSH-Server) lokal bereithalten.*  
2. **Integritätsprüfung:** Verifizieren Sie zwingend die SHA512-Prüfsumme der ISO-Datei.  
3. **VM-Konfiguration (Hypervisor):** \* **RAM:** Zuweisung gemäß Profil (Minimum 8 GB (8192 MB) für Small-Profil, 24 GB (24576 MB) für Large-Profil). Das RAM-Profil ist kritisch für das tmpfs und das Laden der Whisper/Llama-Modelle.  
   * **CPU:** Mindestens 4 vCPUs.  
   * **Disk:** Mindestens 40 GB virtueller Speicherplatz.  
   * **Netzwerk:** Initiales Netzwerk-Interface anbinden (Host-Only-Adapter für den internen Transfer vom Windows-Host, kein Internetzugriff).

## **2\. Beschaffung der Abhängigkeiten (Windows Host)**

Um zwei parallel laufende VMs zu vermeiden, werden die benötigten .whl-Dateien und Machine-Learning-Modelle vorab sequenziell beschafft und auf dem Windows-Host zwischengelagert.

1. **Temporäre Download-Umgebung:** Erstellen Sie eine temporäre Debian VM (identische Version und Architektur zur SecuScribe VM) mit Internetzugang. Bei der Installation können die standard system utilities für Transferwerkzeuge (tar, curl) ausgewählt bleiben.  
2. **VM-Konfiguration (Download-Station):** 2 vCPUs und 4 GB RAM reichen aus. 30 GB Festplatte sind das Mindestmaß, empfehlenswert sind 40 GB.  
3. **Vorbereitung der Download-Station:** Loggen Sie sich als root auf der temporären VM ein und installieren Sie die Basis-Abhängigkeiten für die Skripte sowie die Build-Tools (Kompilier-Abhängigkeiten für Whisper/PyAV):  
   apt-get update && apt-get install \-y sudo python3-pip python3-venv curl build-essential cmake pkg-config libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev libswscale-dev libswresample-dev libavfilter-dev  
   usermod \-aG sudo sysadmin  
   reboot

   *Hinweis: Der Neustart ist zwingend erforderlich, damit die Gruppenzugehörigkeit für sudo in der Sitzung des Benutzers sysadmin aktiv wird.*  
   Loggen Sie sich nach dem Neustart ein und legen Sie in einem Arbeitsverzeichnis (z. B. im Home-Verzeichnis) die folgenden drei Dateien ab: requirements.txt, download\_wheels.sh und download\_models.sh. Machen Sie die Skripte ausführbar (chmod \+x \*.sh).  
4. **Python-Wheels herunterladen:** Führen Sie das Skript im vorbereiteten Verzeichnis aus. Das Skript lädt alle Dateien herunter und generiert automatisch die Datei secuscribe\_wheels.tar.gz.  
   ./download\_wheels.sh

5. **Offline-Modelle herunterladen:** Führen Sie das zweite Skript aus. Es generiert automatisch die Datei secuscribe\_models.tar.gz.  
   ./download\_models.sh \<DEIN\_HF\_TOKEN\>

   * **Hinweis zur Beschaffung des HF Tokens:** Für den Download der Pyannote-Modelle ist eine Authentifizierung erforderlich. Registrieren Sie sich auf [huggingface.co](https://huggingface.co) und akzeptieren Sie dort die Lizenzbedingungen auf den Seiten von pyannote/segmentation-3.0 und pyannote/speaker-diarization-3.1. Erstellen Sie anschließend in Ihren Account-Einstellungen unter "Access Tokens" einen neuen Token (Berechtigung: Read) und übergeben Sie diesen an das Skript.  
6. **Sicherung auf Windows:** Übertragen Sie die generierten Archive secuscribe\_wheels.tar.gz und secuscribe\_models.tar.gz via SFTP/SCP auf Ihr Windows-Hostsystem.  
7. **Zerstörung:** Löschen Sie die temporäre Download-VM vollständig.

## **3\. Basissystem-Installation (SecuScribe VM)**

Starten Sie die neue Maschine vom Debian 13 Installationsmedium (DVD-ISO) und wählen Sie im Boot-Menü **"Install"** (Textmodus).

### **3.1 Lokalisierung und Netzwerkkonfiguration**

* **Sprache/Tastatur:** Englisch (empfohlen für System-Logs) oder Deutsch / Tastaturlayout Deutsch.  
* **Hostname:** secuscribe-vm  
* **IP-Konfiguration:** Richten Sie eine statische IP-Adresse für das isolierte Host-Only-Netzwerk ein (z. B. 192.168.56.10), um den Transfer vom Windows-Host zu ermöglichen. Vergeben Sie kein Standardgateway (Default Route), um Internetzugriff physisch auf Kernel-Ebene auszuschließen.

### **3.2 Benutzer und Passwörter**

* **Root-Passwort:** Vergeben Sie ein kryptografisch starkes Passwort (mindestens 16 Zeichen).  
* **Lokaler Administrator:** Legen Sie einen initialen Benutzer an (z. B. sysadmin).

## **4\. Festplattenpartitionierung**

Wählen Sie im Dialog "Festplatten partitionieren" als Methode **"Manuell"** aus. Dies ist zwingend erforderlich, um die Erstellung einer Swap-Partition zu verhindern.  
**HINWEIS ZUR HÄRTUNG (VS-NFD): Datenpersistenz auf Festspeichern. Das System darf unter keinen Umständen über eine Swap-Partition oder eine Swap-Datei verfügen. Bei Verwendung von Swap könnten unverschlüsselte RAM-Fragmente, die sensible VS-NFD-Audiodaten oder unverschlüsselte Texte enthalten, auf den persistenten Speicher geschrieben werden.**  
Führen Sie die folgenden Schritte exakt aus:

1. **Partitionstabelle erstellen:**  
   * Wählen Sie Ihre virtuelle Festplatte aus der Liste aus (z. B. SCSI... (sda) \- 42.9 GB...) und drücken Sie Enter.  
   * Bestätigen Sie die Frage, ob eine neue, leere Partitionstabelle auf diesem Gerät erstellt werden soll, mit **"Ja"**.  
2. **Die /boot Partition anlegen:**  
   * Wählen Sie den neu entstandenen Eintrag **"FREIER SPEICHER"** unterhalb Ihrer Festplatte an.  
   * Wählen Sie **"Eine neue Partition erstellen"**.  
   * Geben Sie als Größe **1 GB** ein.  
   * Art der Partition: **Primär** (oder Logisch).  
   * Position: **Anfang**.  
   * Stellen Sie sicher, dass bei **Einbindungspunkt** /boot steht.  
   * Das Dateisystem (Benutzung als) muss auf **Ext4-Journaling-Dateisystem** stehen.  
   * Wählen Sie **"Partitionierung beenden und diese Einstellungen übernehmen"**.  
3. **Die Root-Partition (/) anlegen:**  
   * Wählen Sie erneut den nun verkleinerten Eintrag **"FREIER SPEICHER"** (restlicher Speicherplatz).  
   * Wählen Sie **"Eine neue Partition erstellen"**.  
   * Bei der Größe belassen Sie den vorgegebenen, kompletten restlichen Wert und bestätigen Sie.  
   * Art der Partition: **Primär** (oder Logisch).  
   * Stellen Sie sicher, dass der **Einbindungspunkt** auf das Wurzelverzeichnis **/** gesetzt ist.  
   * Das Dateisystem (Benutzung als) muss ebenfalls auf **Ext4-Journaling-Dateisystem** stehen.  
   * Wählen Sie **"Partitionierung beenden und diese Einstellungen übernehmen"**.  
4. **Abschluss ohne Swap:**  
   * Scrollen Sie im Hauptmenü ganz nach unten auf **"Partitionierung beenden und Änderungen übernehmen"**.  
   * Der Installer wird eine Warnung ausgeben ("Weiter ohne Swap-Speicher?"). Bestätigen Sie diese explizit mit **"Ja"**.  
   * Bestätigen Sie die abschließende Frage "Änderungen auf die Festplatten schreiben?" ebenfalls mit **"Ja"**.

## **5\. Softwareauswahl (Tasksel)**

Bei der Auswahl der Komponenten ist das System auf das absolute Minimum zu reduzieren (Principle of Least Privilege).

1. **Abwählen:** Debian desktop environment  
2. **Abwählen:** GNOME, Xfce, KDE etc.  
3. **Abwählen:** web server / print server.  
4. **Abwählen:** standard system utilities.  
5. **Auswählen:** SSH server (Wird ausschließlich für den Transfer vom Windows-Host benötigt und durch das Setup-Skript im PROD-Modus dauerhaft deaktiviert).

Installieren Sie den GRUB-Bootloader und starten Sie das System neu.

## **6\. Transfer der Abhängigkeiten vom Windows-Host**

Nach dem Neustart loggen Sie sich als root über die Konsole oder per SSH (vom Windows-Host via PowerShell oder WinSCP) in das frische System ein.

1. Erstellen Sie die Zielverzeichnisse auf der SecuScribe VM:  
   mkdir \-p /opt/secuscribe/wheels  
   mkdir \-p /opt/secuscribe/models/llm  
   mkdir \-p /opt/secuscribe/models/pyannote  
   mkdir \-p /opt/secuscribe/models/whisper

2. Nutzen Sie ein SFTP-Programm (z. B. WinSCP) auf dem Windows-Host, um sich mit der IP der VM zu verbinden (User: root).  
3. Übertragen Sie die zwischengelagerten Dateien:  
   * Entpacken Sie das secuscribe\_wheels.tar.gz Archiv und kopieren Sie alle .whl Dateien sowie die requirements.txt nach /opt/secuscribe/wheels/.  
   * Entpacken Sie das secuscribe\_models.tar.gz Archiv und kopieren Sie die Machine-Learning-Modelle in die entsprechenden /opt/secuscribe/models/ Unterverzeichnisse.  
   * Kopieren Sie das Bash-Skript setup\_secuscribe\_vm.sh nach /root/.

Sobald diese Dateien auf der Debian 13 Instanz vorliegen, kann das automatisierte Provisionierungs-Skript gestartet werden.