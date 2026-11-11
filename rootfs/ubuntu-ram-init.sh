#!/bin/bash
# Runs entirely from the unpacked initramfs; mounts no disk filesystems.
set -eu
export HOME=/root
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=vt100
trap '/sbin/tspi-ram-tools return now' EXIT
/sbin/tspi-ram-tools return 180 &
mount -t proc -o nosuid,noexec proc /proc
mount -t sysfs -o nosuid,nodev,noexec sysfs /sys
mount -t devtmpfs -o nosuid devtmpfs /dev
mkdir -p /dev/pts
mount -t devpts -o nosuid,noexec,mode=0620,ptmxmode=0666 devpts /dev/pts
printf '1\n' > /proc/sys/kernel/printk
sleep 4
for node in /dev/mmcblk* /dev/sd? /dev/sd?[0-9]*; do
    [ -b "$node" ] || continue
    blockdev --setro "$node"
    [ "$(blockdev --getro "$node")" = 1 ]
    printf 'UBUNTU_RAM_BLOCK_RO %s=1\n' "$node"
done
/sbin/tspi-ram-tools insmod /lib/modules/6.18.62/kernel/drivers/reset/reset-gpio.ko
/sbin/tspi-ram-tools insmod /lib/modules/6.18.62/kernel/drivers/phy/rockchip/phy-rockchip-naneng-combphy.ko
printf '\nUBUNTU_RAM_OS_RELEASE_BEGIN\n'
cat /etc/os-release
printf 'UBUNTU_RAM_OS_RELEASE_END\nKERNEL='
uname -r
printf 'ARCH='
dpkg --print-architecture
printf 'LIBC='
getconf GNU_LIBC_VERSION
cat /proc/mounts
printf '\nG5_UBUNTU_READY_20261111\n'
exec /sbin/init
