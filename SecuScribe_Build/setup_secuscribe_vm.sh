#!/bin/bash
# setup_secuscribe_vm.sh
# Master-Provisionierungsskript für die secuscribe VM
# OS: Debian 13 (Bare Metal / DVD Installer Offline)

set -euo pipefail

# --- 1. Variablen und Argument-Parsing ---
ENV_MODE=""
INGRESS_MODE=""
BASE_DIR="/opt/secuscribe"

function usage() {
    echo "Usage: $0 --env [dev|prod] --ingress [web|shared]"
    exit 1
}

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --env) ENV_MODE="$2"; shift ;;
        --ingress) INGRESS_MODE="$2"; shift ;;
        *) usage ;;
    esac
    shift
done

if [[ "$ENV_MODE" != "dev" && "$ENV_MODE" != "prod" ]]; then usage; fi
if [[ "$INGRESS_MODE" != "web" && "$INGRESS_MODE" != "shared" ]]; then usage; fi

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: Dieses Skript muss als root ausgeführt werden."
    exit 1
fi

echo "Starte Provisionierung... (Env: $ENV_MODE, Ingress: $INGRESS_MODE)"

# --- 2. System-Härtung (Basis) ---
echo "[*] Deaktiviere Swap-Speicher..."
swapoff -a || true
sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab

echo "[*] Härte Kernel-Parameter (sysctl)..."
cat <<EOF > /etc/sysctl.d/99-secuscribe.conf
# Deaktiviere IPv6
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
# Restriktiere dmesg auf privilegierte User
kernel.dmesg_restrict = 1
# Verhindere Ptrace-Angriffe
kernel.yama.ptrace_scope = 2
# Deaktiviere Magic SysRq Key
kernel.sysrq = 0
EOF
sysctl --system

# --- 3. Verzeichnisstruktur erstellen ---
echo "[*] Bereite Verzeichnisstruktur vor..."
mkdir -p $BASE_DIR/{wheels,models,app,debs}
mkdir -p /mnt/secuscribe_ramdisk
mkdir -p /var/secuscribe_transfer/{queue,done}

# --- 4. Automatisches Entpacken der Archive ---
echo "[*] Prüfe auf Offline-Archive in $BASE_DIR..."

# NEU: Offline-Installation der Systempakete (venv, pip)
if [ -f "$BASE_DIR/secuscribe_debs.tar.gz" ]; then
    echo "[->] Entpacke Debian-Systempakete..."
    tar -xzf "$BASE_DIR/secuscribe_debs.tar.gz" -C "$BASE_DIR/debs" --strip-components=1
    echo "[*] Installiere Debian-Pakete offline..."
    apt-get install -y --no-install-recommends $BASE_DIR/debs/*.deb
else
    echo "[!] WARNUNG: secuscribe_debs.tar.gz nicht gefunden. Python VENV könnte fehlen!"
fi

if [ -f "$BASE_DIR/secuscribe_wheels.tar.gz" ]; then
    echo "[->] Entpacke Python Wheels..."
    tar -xzf "$BASE_DIR/secuscribe_wheels.tar.gz" -C "$BASE_DIR/wheels" --strip-components=1
fi

if [ -f "$BASE_DIR/secuscribe_models.tar.gz" ]; then
    echo "[->] Entpacke ML-Modelle..."
    tar -xzf "$BASE_DIR/secuscribe_models.tar.gz" -C "$BASE_DIR/models" --strip-components=1
fi

# --- 5. User-Management & Berechtigungen ---
echo "[*] Konfiguriere User und Berechtigungen..."
if ! id "secu_transfer" &>/dev/null; then
    useradd -r -s /usr/sbin/nologin -d /var/secuscribe_transfer secu_transfer
fi
if ! id "secu_worker" &>/dev/null; then
    useradd -r -s /usr/sbin/nologin -d $BASE_DIR secu_worker
fi

chown -R secu_worker:secu_worker $BASE_DIR
chmod 750 $BASE_DIR

chown secu_transfer:secu_transfer /var/secuscribe_transfer/queue
chown secu_worker:secu_worker /var/secuscribe_transfer/done
chmod 770 /var/secuscribe_transfer/queue
chmod 770 /var/secuscribe_transfer/done

echo "[*] Setze ACLs..."
apt-get install -y acl || true
setfacl -m u:secu_worker:rx /var/secuscribe_transfer/queue
setfacl -m u:secu_transfer:rx /var/secuscribe_transfer/done

# --- 6. Mounts (/etc/fstab) ---
echo "[*] Konfiguriere fstab..."
if ! grep -q "/mnt/secuscribe_ramdisk" /etc/fstab; then
    echo "tmpfs /mnt/secuscribe_ramdisk tmpfs rw,nodev,nosuid,noexec,size=4G,mode=0700,uid=$(id -u secu_worker),gid=$(id -g secu_worker) 0 0" >> /etc/fstab
fi

if [[ "$INGRESS_MODE" == "shared" ]]; then
    if ! grep -q "/var/secuscribe_transfer" /etc/fstab; then
        echo "secuscribe_share /var/secuscribe_transfer virtiofs rw,noexec,nosuid,nodev 0 0" >> /etc/fstab
    fi
fi
mount -a

# --- 7. Python Environment Setup ---
echo "[*] Richte Python Virtual Environment ein (Offline)..."
if [ ! -d "$BASE_DIR/.venv" ]; then
    sudo -u secu_worker python3 -m venv $BASE_DIR/.venv
fi

if [ -f "$BASE_DIR/wheels/requirements.txt" ]; then
    echo "[*] Installiere Python-Pakete aus lokalem Cache..."
    sudo -u secu_worker $BASE_DIR/.venv/bin/pip install --no-index --find-links=$BASE_DIR/wheels/ -r $BASE_DIR/wheels/requirements.txt
fi

# --- 8. Firewall (nftables) ---
echo "[*] Konfiguriere Netzwerk-Isolation (nftables)..."
# ... (nftables Konfiguration bleibt identisch) ...
cat <<EOF > /etc/nftables.conf
#!/usr/sbin/nft -f
flush ruleset

table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        iif "lo" accept
        ct state established,related accept
EOF

if [[ "$ENV_MODE" == "dev" ]]; then
    echo "        tcp dport 22 accept # SSH im Dev-Modus" >> /etc/nftables.conf
fi

if [[ "$INGRESS_MODE" == "web" ]]; then
    echo "        tcp dport 443 accept # HTTPS Web-Ingress" >> /etc/nftables.conf
fi

cat <<EOF >> /etc/nftables.conf
    }
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
    chain output {
        type filter hook output priority 0; policy drop;
        oif "lo" accept
        ct state established,related accept
EOF

if [[ "$ENV_MODE" == "dev" ]]; then
    echo "        # Erlaube Ping und Updates lokal im Dev-Mode" >> /etc/nftables.conf
    echo "        ip daddr 10.0.0.0/8 accept" >> /etc/nftables.conf
    echo "        ip daddr 192.168.0.0/16 accept" >> /etc/nftables.conf
    echo "        ip daddr 172.16.0.0/12 accept" >> /etc/nftables.conf
fi

cat <<EOF >> /etc/nftables.conf
    }
}
EOF

systemctl enable --now nftables

# --- 9. Finaler Lockdown (Prod) ---
if [[ "$ENV_MODE" == "prod" ]]; then
    echo "[*] PROD-MODUS: Aktiviere harten Lockdown..."
    if systemctl is-active --quiet ssh || systemctl is-active --quiet sshd; then
        systemctl disable --now ssh || true
        systemctl disable --now sshd || true
    fi
    passwd -d root
    passwd -l root
fi

echo "[*] Provisionierung abgeschlossen. Systemeinsatzbereit."