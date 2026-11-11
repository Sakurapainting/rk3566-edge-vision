#!/bin/sh
# BusyBox udhcpc hook. All changes stay in the temporary RAM system.
set -eu
[ "${interface:-}" = wlan0 ] || exit 1
case "${1:-}" in
    deconfig)
        ip -4 address flush dev "$interface"
        ;;
    bound|renew)
        ip -4 address flush dev "$interface"
        busybox ifconfig "$interface" "$ip" netmask "${subnet:-255.255.255.0}"
        for gateway in ${router:-}; do
            ip route replace default via "$gateway" dev "$interface"
            break
        done
        : > /etc/resolv.conf
        for server in ${dns:-}; do
            printf 'nameserver %s\n' "$server" >> /etc/resolv.conf
        done
        printf 'WIFI_DHCP_BOUND ip=%s subnet=%s\n' "$ip" "${subnet:-}"
        ;;
esac
