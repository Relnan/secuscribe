packer {
  required_plugins {
    virtualbox = {
      version = ">= 0.0.1"
      source  = "github.com/hashicorp/virtualbox"
    }
    vmware = {
      version = ">= 1.0.0"
      source  = "github.com/hashicorp/vmware"
    }
  }
}

variable "iso_path" {
  type    = string
  default = "../debian-13.4.0-amd64-DVD-1.iso" # HIER PFAD ANPASSEN, FALLS ISO WOANDERS IST
}

variable "net_type" {
    type    = string
    default = "hostonly"
}

# --- BUILDER FÜR VIRTUALBOX ---
source "virtualbox-iso" "secuscribe" {
  guest_os_type        = "Debian_64"
  iso_url              = "${var.iso_path}"
  iso_checksum         = "none" # In Prod bitte SHA512 eintragen
  ssh_username         = "root"
  ssh_password         = "P@ssw0rd"
  ssh_timeout          = "30m"
  cpus                 = 4
  memory               = 8192
  disk_size            = 45056 # 44 GB
  headless             = false
  http_directory       = "http"
  boot_wait            = "5s"
  boot_command = [
    "<esc><wait>",
    "install auto=true priority=critical ",
    "url=http://{{ .HTTPIP }}:{{ .HTTPPort }}/preseed.cfg ",
    "hostname=secuscribe-vm ",
    "domain=local ",
    "interface=auto ",
    "partman-basicfiles/no_swap=false ",
    "partman/confirm_nooverwrite=true ",
    "<enter>"
  ]
  shutdown_command     = "shutdown -P now"
  format               = "ova"
}

# --- BUILDER FÜR VMWARE ---
source "vmware-iso" "secuscribe" {
  guest_os_type        = "debian-64"
  iso_url              = "${var.iso_path}"
  iso_checksum         = "none"
  ssh_username         = "root"
  ssh_password         = "P@ssw0rd"
  ssh_timeout          = "30m"
  cpus                 = 4
  memory               = 8192
  disk_size            = 45056
  network_adapter_type = "vmxnet3" 
  headless             = false
  
# Während des Builds: NAT nutzen, um die Windows-Firewall zu umgehen
  vmx_data = {
    "ethernet0.connectionType" = "nat"
  }

  # NACH dem Build: Die fertige Maschine versiegeln und auf den gewünschten Modus setzen
  vmx_data_post = {
    "ethernet0.connectionType" = var.net_type
  }

  http_directory       = "http"
  boot_wait            = "5s"
  boot_command = [
    "<esc><wait>",
    "install auto=true priority=critical ",
    "url=http://{{ .HTTPIP }}:{{ .HTTPPort }}/preseed.cfg ",
    "hostname=secuscribe-vm ",
    "domain=local ",
    "interface=auto ",
    "partman-basicfiles/no_swap=false ",
    "partman/confirm_nooverwrite=true ",
    "<enter>"
  ]
  shutdown_command     = "shutdown -P now"
  format               = "ova"
}

build {
  sources = ["source.virtualbox-iso.secuscribe", "source.vmware-iso.secuscribe"]

  # Schritt 1: Downloader-Skripte hochladen
  provisioner "file" {
    sources     = ["download_wheels.sh", "download_models.sh", "requirements.txt", "setup_secuscribe_vm.sh"]
    destination = "/tmp/"
  }

  # Schritt 2: Skripte ausführbar machen und Build-Vorbereitung
  provisioner "shell" {
    inline = [
      "chmod +x /tmp/*.sh",
      "mkdir -p /opt/secuscribe",
      "mv /tmp/setup_secuscribe_vm.sh /opt/secuscribe/"
    ]
  }

  # 3. Ziel-Ordner erstellen (MUSS vor dem Datei-Upload passieren!)
  provisioner "shell" {
    inline = [
      "mkdir -p /opt/secuscribe/wheels"
    ]
  }

  # 4. Kompletten Ordner mit Python-Wheels direkt ins Ziel hochladen
  provisioner "file" {
    source      = "./wheels/"
    destination = "/opt/secuscribe/wheels/"
  }
}