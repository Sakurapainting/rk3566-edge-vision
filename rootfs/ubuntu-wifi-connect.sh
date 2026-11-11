#!/bin/bash
# The private wpa_supplicant file is delivered separately to /run in RAM.
set -eu
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
config=/run/tspi-wpa.conf
test -s "$config"
chmod 600 "$config"
ip link set wlan0 up
wpa_supplicant -B -i wlan0 -c "$config" -P /run/tspi-wpa.pid -f /run/tspi-wpa.log
connected=0
for attempt in $(seq 1 45); do
    if wpa_cli -i wlan0 status | grep -q '^wpa_state=COMPLETED$'; then
        connected=1
        break
    fi
    sleep 1
done
wpa_cli -i wlan0 status
[ "$connected" = 1 ] || exit 1
busybox udhcpc -i wlan0 -n -q -t 5 -T 3 -s /usr/sbin/tspi-wifi-dhcp
printf 'WIFI_IPV4\n'
ip -brief addr show wlan0
ip route show
printf 'WIFI_ASSOCIATION\n'
iw dev wlan0 link
gateway=$(ip route show default dev wlan0 | awk 'NR==1 {print $3}')
if [ -n "$gateway" ]; then
    busybox ping -c 3 -W 3 "$gateway" || printf 'WIFI_GATEWAY_PING_FAILED=%s\n' "$?"
fi
printf 'WIFI_DNS_CHECK\n'
busybox nslookup ports.ubuntu.com || printf 'WIFI_DNS_FAILED=%s\n' "$?"
printf 'WIFI_CONNECT_DONE\n'
