#!/bin/sh
# Explicitly invoked from the FIT rescue shell after the host has checked identity.
set -eu
export PATH=/bin:/sbin
test "$(uname -r)" = 6.18.62
test "$(cat /sys/class/block/mmcblk1/size)" = 30535680
test "$(cat /sys/class/block/mmcblk1p7/start)" = 51200
test "$(cat /sys/class/block/mmcblk1p7/size)" = 81920
test "$(cat /sys/class/block/mmcblk1p14/start)" = 8310784
test "$(cat /sys/class/block/mmcblk1p14/size)" = 22224832
test "$(/sbin/blkid -s PARTUUID -o value /dev/mmcblk1p14)" = 153f0000-0000-4c04-8000-6fb500005626
test "$(/sbin/blkid -s UUID -o value /dev/sda1)" = 3074-0F41
test "$(cat /sys/bus/usb/devices/*/serial | grep -c '^0022CFF6BDFCC7706324C568$')" = 1
if grep -qE 'mmcblk1p14| /newroot ' /proc/mounts; then
    echo 'Refusing: rootfs target is already mounted.'
    exit 1
fi
cd "${0%/*}"
sha256sum -c SHA256SUMS
test "$(sha256sum /dev/mmcblk1p7 | cut -d ' ' -f 1)" = 0edf6e9967cafae5e6970abde398135347ab8c10b6cd9832514f1671a34714b2
printf '\nG7_INSTALL_ROOTFS_BEGIN: mmcblk1p14 only\n'
/sbin/mke2fs -F -t ext4 -L tspi-root -m 0 -U 2cce377d-b731-4de2-ac51-e8ad1d44f466 -E nodiscard,lazy_itable_init=0,lazy_journal_init=0 /dev/mmcblk1p14
mount -t ext4 -o rw /dev/mmcblk1p14 /newroot
tar -xzpf ubuntu-rootfs.tar.gz -C /newroot
grep -q '2026-11-11/emmc-deploy-01' /newroot/etc/tspi-build-info
test -x /newroot/usr/lib/systemd/systemd
test -L /newroot/sbin/init
test -f /newroot/etc/systemd/system/serial-getty@ttyS2.service.d/override.conf
sync
umount /newroot
/sbin/e2fsck -fn /dev/mmcblk1p14
printf '\nG7_INSTALL_ROOTFS_COMPLETE: boot partition still original\n'
