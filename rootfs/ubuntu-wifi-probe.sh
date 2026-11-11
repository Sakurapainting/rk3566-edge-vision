#!/bin/bash
# Driver/scan probe only. Network credentials are supplied separately in RAM.
set -eu
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
mkdir -p /run
printf '\nWIFI_PROBE_BEGIN\n'
modprobe brcmfmac-wcc
iw reg set CN
for attempt in $(seq 1 30); do
    [ ! -d /sys/class/net/wlan0 ] || break
    sleep 1
done
if [ ! -d /sys/class/net/wlan0 ]; then
    printf 'WIFI_NO_WLAN0\n'
    dmesg | tail -n 90
    exit 1
fi
# Preserve this board's MAC observed in its original Android, not the template
# address in the vendor NVRAM. Both values are stored in the input evidence.
if [ -f /etc/tspi-wifi-mac ]; then
    ip link set dev wlan0 address "$(cat /etc/tspi-wifi-mac)"
fi
ip link set wlan0 up
printf 'WIFI_INTERFACE\n'
ip -brief link show wlan0
iw dev
printf 'WIFI_REGULATORY\n'
iw reg get
printf 'WIFI_SCAN_BEGIN\n'
if timeout 30 iw dev wlan0 scan > /run/tspi-wifi-scan.txt 2>/run/tspi-wifi-scan.stderr; then
    printf 'WIFI_SCAN_RC=0\n'
    # Only print matching target records; keep the full scan in ephemeral RAM.
    awk -v target="$(cat /etc/tspi-wifi-ssid)" '
        function emit() { if (match_target) printf "%s", block }
        /^BSS / { emit(); block=""; match_target=0 }
        { block=block $0 "\n" }
        /^[[:space:]]*SSID: / {
            name=$0; sub(/^[[:space:]]*SSID: /,"",name)
            if (name==target) match_target=1
        }
        END { emit() }
    ' /run/tspi-wifi-scan.txt
    printf 'WIFI_BSS_COUNT=%s\n' "$(grep -c '^BSS ' /run/tspi-wifi-scan.txt)"
else
    rc=$?
    printf 'WIFI_SCAN_RC=%s\n' "$rc"
    cat /run/tspi-wifi-scan.stderr
fi
printf 'WIFI_PROBE_DONE\n'
