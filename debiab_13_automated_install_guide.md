# **Automatisierte Installation: SecuScribe VM (IaC-Ansatz)**

Diese Anleitung nutzt **HashiCorp Packer**, um bit-identische VMs für die Download-Station und das Produktivsystem zu erstellen. Der Prozess ist in zwei Phasen unterteilt.

## **1\. Vorbereitung auf dem Windows-Host**

1. Laden Sie die portable packer.exe von [packer.io](https://www.packer.io/downloads) herunter und legen Sie diese in Ihren Projektordner.  
2. Legen Sie das Debian 13 DVD-ISO bereit.  
3. Stellen Sie sicher, dass die preseed.cfg im Ordner ./http/ liegt.

*Tipp für Windows:* Stellen Sie im Windows Explorer unter "Ansicht" \-\> "Einblenden" sicher, dass "Dateinamenerweiterungen" aktiviert ist. Prüfen Sie, dass Ihre Datei wirklich secuscribe.pkr.hcl heißt.

## **2\. Phase 1: Erstellung der Download-Station (NAT / Internet)**

Um die Machine-Learning-Modelle und Python-Abhängigkeiten (Wheels) aus dem Internet zu laden, benötigen wir zunächst eine Basis-VM mit Internetzugang.

1. **Netzwerk prüfen:** Stellen Sie sicher, dass VMware so konfiguriert ist, dass neue VMs standardmäßig eine Internetverbindung (NAT) erhalten.  
2. Führen Sie in der PowerShell zunächst die Initialisierung und anschließend den Build-Befehl aus (wir übergeben hier explizit den Modus "nat"):

.\\packer.exe init .  
.\\packer.exe build \-var="net\_type=nat" \-only="vmware-iso.secuscribe" .

*(Hinweis: Falls Sie VirtualBox nutzen, ändern Sie den Parameter auf virtualbox-iso.secuscribe)*

3. **Daten herunterladen:**  
   * Öffnen Sie die erstellte VM (im Ordner output-secuscribe) in VMware und starten Sie diese.  
   * Loggen Sie sich als root ein.  
   * Führen Sie die Download-Skripte aus, die Packer bereits für Sie hinterlegt hat:  
     cd /tmp  
     ./download\_wheels.sh  
     ./download\_models.sh

4. **Daten sichern:** Verbinden Sie sich z. B. per WinSCP mit der VM und kopieren Sie die entstandenen Dateien secuscribe\_wheels.tar.gz und secuscribe\_models.tar.gz auf Ihren Windows-Host.  
5. Fahren Sie diese Download-VM herunter. Sie können sie nun löschen, da sie ihren Zweck erfüllt hat.

## **3\. Phase 2: Erstellung der SecuScribe-VM (Host-Only / Offline)**

Nun bauen wir die eigentliche, streng abgeriegelte Produktiv-VM.

1. **Packer neu starten (Offline-Modus):** Führen Sie den Build-Befehl nun mit dem Parameter hostonly aus. Packer überschreibt den alten Ordner und generiert Ihnen in wenigen Minuten eine brandneue, saubere und physisch vom Internet getrennte Debian-VM.

.\\packer.exe build \-only="vmware-iso.secuscribe" .

2. Starten Sie die fertige VM in VMware und loggen Sie sich als root ein.  
3. **Archive übertragen:**  
   * Erstellen Sie das Zielverzeichnis: mkdir \-p /opt/secuscribe  
   * Übertragen Sie Ihre secuscribe\_wheels.tar.gz und secuscribe\_models.tar.gz von Ihrem Windows-Host in diesen Ordner (z. B. via WinSCP).  
4. **Setup & Installation:**  
   Führen Sie das Master-Skript aus. Dieses entpackt die Archive, installiert die Python-Wheels komplett offline und zieht die Sicherheitsrichtlinien (Firewall, Swap-Deaktivierung, Root-Sperre) an:  
   cd /tmp  
   mv setup\_secuscribe\_vm.sh /opt/secuscribe/  
   cd /opt/secuscribe  
   ./setup\_secuscribe\_vm.sh \--env prod \--ingress shared

## **4\. Finalisierung**

Nach Abschluss des Setups ist das System einsatzbereit und versiegelt. Sie können die fertige .vmx (VMware) oder .ova (VirtualBox) Appliance nun an ihren finalen Bestimmungsort kopieren.