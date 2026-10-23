#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root: sudo ./uninstall.sh" >&2
    exit 1
fi

/usr/local/sbin/honer-lights-gui-helper stop-effect 2>/dev/null || true
systemctl disable --now honer-v700-lights.service 2>/dev/null || true
modprobe -r honer_v700_lights 2>/dev/null || true
dkms remove -m honer-v700-lights -v 0.1 --all 2>/dev/null || true

rm -rf /usr/src/honer-v700-lights-0.1
rm -rf /usr/local/lib/honer-v700-lights
rm -f /usr/local/sbin/honer-lights-gui-helper /usr/local/sbin/honer-lights
rm -f /usr/share/polkit-1/actions/local.honer.lights.policy
rm -f /etc/systemd/system/honer-v700-lights.service
rm -f /usr/share/applications/local.honer.LightControl.desktop
systemctl daemon-reload

echo "Uninstalled honer-v700-lights (lighting backups in /var/lib/honer-v700-lights were preserved)."
