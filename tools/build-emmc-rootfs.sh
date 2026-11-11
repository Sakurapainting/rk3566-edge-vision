#!/bin/sh
# Native Debian container with proot, qemu-user-static, apt, e2fsprogs, Python.
# Build inputs: verified Actions 42811216799 Ubuntu rootfs and prior signed Wi-Fi packages.
set -eu
cd /project
out=${TSPI_EMMC_BUILD_OUT:-/project/build/emmc-deploy-20261111-01}
stage=$out/rootfs
deps=$out/dependencies
[ ! -e "$stage" ] || { echo "Refusing to overwrite an existing rootfs stage" >&2; exit 1; }
mkdir -p "$stage" "$deps/apt/lists/partial" "$deps/apt/cache/archives/partial" "$deps/keyrings"
printf '%s  %s\n' 686df670cdebbefb69c4836c7109dc10c3843070652cf8f4ce664cbf061975ba build/archive/tspi-linux-42811216799/extracted/ubuntu-base-24.04.5-tspi-arm64.tar.gz | sha256sum -c -
tar -xpf build/archive/tspi-linux-42811216799/extracted/ubuntu-base-24.04.5-tspi-arm64.tar.gz -C "$stage"
cp build/ubuntu-wifi-inputs-20261111-01/cloud-dpkg-status "$deps/cloud-dpkg-status"
cp build/ubuntu-wifi-inputs-20261111-01/keyrings/* "$deps/keyrings/"
sed "s|/work/|$deps/|g" build/ubuntu-wifi-inputs-20261111-01/apt.conf > "$deps/apt.conf"
sed "s|/work/|$deps/|g" build/ubuntu-wifi-inputs-20261111-01/ubuntu.sources.list > "$deps/ubuntu.sources.list"
export APT_CONFIG=$deps/apt.conf
apt-get update
apt-get --download-only -y --no-install-recommends install systemd-sysv udev dbus systemd-resolved iw wpasupplicant iproute2 kmod wireless-regdb ca-certificates busybox-static iputils-ping
unset APT_CONFIG
mkdir -p "$stage/tmp/install-debs"
cp "$deps/apt/cache/archives/"*.deb "$stage/tmp/install-debs/"
printf '#!/bin/sh\nexit 101\n' > "$stage/usr/sbin/policy-rc.d"
chmod 755 "$stage/usr/sbin/policy-rc.d"
rm -f "$stage/etc/apt/sources.list.d/ubuntu.sources"
sed 's|signed-by=[^]]*||' "$deps/ubuntu.sources.list" > "$stage/etc/apt/sources.list"
proot -0 -r "$stage" -b /dev -b /proc -b /sys -w / -q /usr/bin/qemu-aarch64-static /bin/sh -ec '
for p in /tmp/install-debs/*.deb; do case "$p" in */systemd-sysv_*) continue;; esac; dpkg --unpack "$p"; done
'
# systemd 255 filesystem helpers need /proc/self/fd semantics that proot cannot supply.
# Run the same ARM64 binaries offline with --root, then configure packages in proot.
rmdir "$stage/proc" "$stage/sys"
qemu-aarch64-static -L "$stage" "$stage/usr/bin/systemd-sysusers" --root="$stage"
mkdir -p "$stage/proc" "$stage/sys"
mv "$stage/usr/bin/systemd-sysusers" "$stage/usr/bin/systemd-sysusers.tspi-real"
printf '#!/bin/sh\n# Users already created offline by the image builder.\nexit 0\n' > "$stage/usr/bin/systemd-sysusers"
chmod 755 "$stage/usr/bin/systemd-sysusers"
restore_helper() { mv "$stage/usr/bin/systemd-sysusers.tspi-real" "$stage/usr/bin/systemd-sysusers"; }
trap restore_helper EXIT
proot -0 -r "$stage" -b /dev -b /proc -b /sys -w / -q /usr/bin/qemu-aarch64-static /usr/bin/env DEBIAN_FRONTEND=noninteractive /bin/sh -ec '
dpkg --configure -a
dpkg -i /tmp/install-debs/systemd-sysv_*.deb
dpkg --audit
'
restore_helper
trap - EXIT
# Optional helper failures inside proot are repaired offline with the genuine helpers.
rmdir "$stage/proc" "$stage/sys"
qemu-aarch64-static -L "$stage" "$stage/usr/bin/systemd-tmpfiles" --root="$stage" --create
qemu-aarch64-static -L "$stage" "$stage/usr/bin/systemd-hwdb" --root="$stage" --usr update
qemu-aarch64-static -L "$stage" "$stage/usr/bin/systemctl" --root="$stage" enable systemd-networkd.service systemd-resolved.service
mkdir -p "$stage/proc" "$stage/sys"
rm -f "$stage/usr/sbin/policy-rc.d" "$stage/etc/apt/apt.conf.d/99tspi-build" "$stage/tmp/host-ca.crt"
# No credentials from build/private enter this filesystem.
mkdir -p "$stage/etc/modules-load.d" "$stage/etc/systemd/system/serial-getty@ttyS2.service.d" "$stage/etc/systemd/network" "$stage/etc/systemd/system/multi-user.target.wants"
printf 'reset_gpio\nphy_rockchip_naneng_combphy\nbrcmfmac\n' > "$stage/etc/modules-load.d/tspi.conf"
cat > "$stage/etc/systemd/system/serial-getty@ttyS2.service.d/override.conf" <<'GETTY'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear --keep-baud 1500000 %I vt100
GETTY
ln -sf /usr/lib/systemd/system/serial-getty@.service "$stage/etc/systemd/system/multi-user.target.wants/serial-getty@ttyS2.service"
ln -sf /usr/lib/systemd/system/multi-user.target "$stage/etc/systemd/system/default.target"
# The base image refers to an optional PAM module absent from the packaged rootfs.
if [ ! -f "$stage/usr/lib/aarch64-linux-gnu/security/pam_lastlog.so" ]; then
    sed -i '/^[[:space:]]*session[[:space:]]*optional[[:space:]]*pam_lastlog\.so[[:space:]]*$/d' "$stage/etc/pam.d/login"
fi
printf 'tspi-vision\n' > "$stage/etc/hostname"
printf '127.0.0.1 localhost\n127.0.1.1 tspi-vision\n::1 localhost ip6-localhost\n' > "$stage/etc/hosts"
cat > "$stage/etc/fstab" <<'FSTAB'
LABEL=tspi-root / ext4 defaults,noatime 0 1
tmpfs /tmp tmpfs defaults,nosuid,nodev,mode=1777 0 0
FSTAB
cat > "$stage/etc/systemd/network/10-wlan0.link" <<'LINK'
[Match]
OriginalName=wlan0
[Link]
MACAddress=54:78:c9:99:74:f4
LINK
cat > "$stage/etc/systemd/network/20-wlan0.network" <<'NETWORK'
[Match]
Name=wlan0
[Network]
DHCP=yes
[DHCPv4]
UseDomains=yes
NETWORK
mkdir -p "$stage/usr/lib/firmware/brcm"
cp build/ubuntu-wifi-inputs-20261111-01/overlay/usr/lib/firmware/brcm/* "$stage/usr/lib/firmware/brcm/"
# Generate unique machine-id at first real boot.
: > "$stage/etc/machine-id"
rm -f "$stage/var/lib/dbus/machine-id"
ln -s /etc/machine-id "$stage/var/lib/dbus/machine-id"
rm -f "$stage/etc/resolv.conf"
ln -s /run/systemd/resolve/stub-resolv.conf "$stage/etc/resolv.conf"
rm -f "$stage/var/lib/systemd/random-seed"
rm -f "$stage/root/.bash_history" "$stage"/qemu_*.core
cat > "$stage/etc/tspi-build-info" <<'INFO'
Ubuntu 24.04.5 ARM64 permanent eMMC bring-up
Kernel: 6.18.62 (Actions 42811216799)
Board: LCKFB Taishan Pi RK3566, serial 86b2acaf11e3305
Build: 2026-11-11/emmc-deploy-01
INFO
# Remove caches and package build residue, retaining installed package metadata.
rm -f "$stage/var/cache/apt/archives/"*.deb
rm -rf "$stage/var/lib/apt/lists/"*
find "$stage/tmp" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
proot -0 -r "$stage" -b /dev -b /proc -w / -q /usr/bin/qemu-aarch64-static /bin/sh -ec '
/usr/lib/systemd/systemd --version
dpkg-query -W systemd-sysv systemd udev systemd-resolved iw wpasupplicant # systemd-sysv systemd udev systemd-resolved iw wpasupplicant
'
tar --numeric-owner -cpf - -C "$stage" . | gzip -n -1 > "$out/ubuntu-rootfs.tar.gz"
sha256sum "$out/ubuntu-rootfs.tar.gz" > "$out/rootfs.sha256"
