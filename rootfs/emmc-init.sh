#!/bin/sh
export PATH=/bin:/sbin
export HOME=/root TERM=vt100
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts /run /newroot /media
mount -t devpts devpts /dev/pts
mount -t tmpfs tmpfs /run
exec </dev/console >/dev/console 2>&1
printf '\nG7_EMMC_INIT_20261111\n'
uname -a
insmod /modules/reset-gpio.ko || true
insmod /modules/phy-rockchip-naneng-combphy.ko || true
sleep 3
if [ "$(cat /sys/class/block/mmcblk1/size)" = 30535680 ] &&
   [ "$(cat /sys/class/block/mmcblk1p14/start)" = 8310784 ] &&
   [ "$(cat /sys/class/block/mmcblk1p14/size)" = 22224832 ] &&
   mount -t ext4 -o ro,noload /dev/mmcblk1p14 /newroot; then
    if grep -q '2026-11-11/emmc-deploy-01' /newroot/etc/tspi-build-info; then
        umount /newroot
        if mount -t ext4 -o rw /dev/mmcblk1p14 /newroot; then
            mkdir -p /newroot/dev /newroot/proc /newroot/sys /newroot/run
            printf 'G7_SWITCH_ROOT_20261111\n'
            mount --move /proc /newroot/proc
            mount --move /sys /newroot/sys
            mount --move /run /newroot/run
            mount --move /dev /newroot/dev
            exec switch_root /newroot /sbin/init
        fi
    else
        umount /newroot
    fi
fi
printf '\nG7_RESCUE_READY: rootfs unavailable; no automatic formatting or reboot.\n'
export PS1='TSPI_EMMC_RESCUE# '
exec /bin/sh -i
