#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root: sudo ./install.sh" >&2
    exit 1
fi

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

echo "[1/5] Installing DKMS kernel module (honer-v700-lights 0.1)..."
mkdir -p /usr/src/honer-v700-lights-0.1
install -m 0644 "$REPO_DIR/dkms/honer_v700_lights.c" /usr/src/honer-v700-lights-0.1/honer_v700_lights.c
install -m 0644 "$REPO_DIR/dkms/Makefile" /usr/src/honer-v700-lights-0.1/Makefile
install -m 0644 "$REPO_DIR/dkms/dkms.conf" /usr/src/honer-v700-lights-0.1/dkms.conf

modprobe -r honer_v700_lights 2>/dev/null || true
dkms remove -m honer-v700-lights -v 0.1 --all 2>/dev/null || true
dkms add -m honer-v700-lights -v 0.1
dkms build -m honer-v700-lights -v 0.1
dkms install -m honer-v700-lights -v 0.1

echo "[2/5] Installing application and helper scripts..."
mkdir -p /usr/local/lib/honer-v700-lights
install -m 0644 "$REPO_DIR/src/v700-lights.py" /usr/local/lib/honer-v700-lights/v700-lights.py
install -m 0644 "$REPO_DIR/src/light-control-app.py" /usr/local/lib/honer-v700-lights/light-control-app.py
install -m 0644 "$REPO_DIR/tests/test_v700_lights.py" /usr/local/lib/honer-v700-lights/test_v700_lights.py
install -m 0644 "$REPO_DIR/tests/test_light_control.py" /usr/local/lib/honer-v700-lights/test_light_control.py
install -m 0755 "$REPO_DIR/src/honer-lights-gui-helper" /usr/local/sbin/honer-lights-gui-helper
install -m 0755 "$REPO_DIR/src/honer-lights" /usr/local/sbin/honer-lights

echo "[3/5] Installing Polkit policy and systemd service..."
install -m 0644 "$REPO_DIR/polkit/local.honer.lights.policy" /usr/share/polkit-1/actions/local.honer.lights.policy
install -m 0644 "$REPO_DIR/systemd/honer-v700-lights.service" /etc/systemd/system/honer-v700-lights.service
systemctl daemon-reload

echo "[4/5] Ensuring factory lighting backups exist in /var/lib/honer-v700-lights..."
mkdir -p /var/lib/honer-v700-lights
chmod 0700 /var/lib/honer-v700-lights
modprobe honer_v700_lights
for zone in logo b0 d0; do
    if [ "$zone" = "logo" ]; then
        bfile="/var/lib/honer-v700-lights/original-lighting.json"
    else
        bfile="/var/lib/honer-v700-lights/original-lighting-${zone}.json"
    fi
    if [ ! -f "$bfile" ]; then
        /usr/bin/python3 /usr/local/lib/honer-v700-lights/v700-lights.py backup --zone "$zone" || true
    fi
done
modprobe -r honer_v700_lights 2>/dev/null || true

echo "[5/5] Installing desktop launcher..."
install -m 0644 "$REPO_DIR/desktop/local.honer.LightControl.desktop" /usr/share/applications/local.honer.LightControl.desktop

echo "Installation complete!"
