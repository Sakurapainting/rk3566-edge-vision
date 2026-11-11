#!/usr/bin/env python3
"""Build a Rockchip external-data FIT and a small serial rescue initramfs."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import subprocess
import zlib

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--rootfs', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--board-dtb',type=Path,help='Prepared mainline DTB with permanent bootargs')
a = p.parse_args()
root = Path(__file__).resolve().parent.parent
stage, out = a.rootfs.resolve(), a.output.resolve()
out.mkdir(exist_ok=True)
cloud = root / 'build/archive/tspi-linux-42811216799/extracted'
kernel = (cloud / 'Image').read_bytes()
assert hashlib.sha256(kernel).hexdigest() == 'e101ffe37fd6d3b92a1d9c2a01ce1a35654e44c5abb9689b53d31469707f1de8'
(out / 'Image.gz').write_bytes(gzip.compress(kernel, compresslevel=9, mtime=0))
dtb = (root / 'build/ram-boot-20261111-02/tspi-ram/rk3566-lckfb-tspi-ram.dtb').read_bytes()
assert hashlib.sha256(dtb).hexdigest() == 'b1ed572d98a9f8a695086a6cca4a23ff9f39b910a3de4ccf73f2ddd5884a73ac'
if a.board_dtb:
    dtb = a.board_dtb.read_bytes()
    assert b'clk_ignore_unused' in dtb and b'console=ttyS2,1500000n8' in dtb
(out / 'board.dtb').write_bytes(dtb)

entries = {}
def put(name, data=b'', mode=stat.S_IFREG | 0o755, major=0, minor=0):
    entries[name] = (mode, data, major, minor)
    parent = Path(name).parent
    while str(parent) != '.':
        entries.setdefault(str(parent), (stat.S_IFDIR | 0o755, b'', 0, 0))
        parent = parent.parent

for d in ['bin', 'sbin', 'dev', 'proc', 'sys', 'run', 'newroot', 'media', 'root', 'tmp']:
    put(d, mode=stat.S_IFDIR | (0o1777 if d == 'tmp' else 0o755))
put('init', (root / 'rootfs/emmc-init.sh').read_bytes())
busybox = (stage / 'usr/bin/busybox').read_bytes()
put('bin/busybox', busybox)
commands = ['sh', 'mount', 'umount', 'mkdir', 'sleep', 'cat', 'grep', 'readlink', 'switch_root',
            'uname', 'insmod', 'ls', 'blockdev', 'sha256sum', 'dd', 'tar', 'sync',
            'reboot', 'poweroff', 'dmesg', 'find', 'sed', 'awk', 'head', 'tail', 'ps',
            'cut', 'hexdump', 'wc', 'echo', 'stat', 'chmod', 'chown', 'cp', 'mv', 'rm', 'rmdir']
for c in commands:
    put('bin/' + c, b'busybox', stat.S_IFLNK | 0o777)
put('dev/console', mode=stat.S_IFCHR | 0o600, major=5, minor=1)
put('dev/null', mode=stat.S_IFCHR | 0o666, major=1, minor=3)
for mod in ['drivers/reset/reset-gpio.ko', 'drivers/phy/rockchip/phy-rockchip-naneng-combphy.ko']:
    put('modules/' + Path(mod).name, (stage / 'usr/lib/modules/6.18.62/kernel' / mod).read_bytes(), stat.S_IFREG | 0o644)

# Resolve merged-/usr symlinks inside the target root, never against the host.
def target_resolve(name):
    parts = list(Path(name).parts)
    done = []
    while parts:
        part = parts.pop(0)
        if part in ('', '.', '/'):
            continue
        if part == '..':
            done.pop()
            continue
        candidate = stage.joinpath(*done, part)
        if candidate.is_symlink():
            link = candidate.readlink()
            if link.is_absolute():
                done = []
            parts = list(link.parts) + parts
        else:
            done.append(part)
    return stage.joinpath(*done)

seen = set()
def add_elf(name):
    if name in seen:
        return
    seen.add(name)
    src = target_resolve(name)
    data = src.read_bytes()
    put(name, data)
    details = subprocess.check_output(['readelf', '-ld', str(src)], text=True)
    interp = re.search(r'Requesting program interpreter: ([^\]]+)', details)
    if interp:
        add_elf(interp[1].lstrip('/'))
    for dep in re.findall(r'\(NEEDED\).*?\[([^]]+)\]', details):
        candidates = ['lib/aarch64-linux-gnu/' + dep, 'usr/lib/aarch64-linux-gnu/' + dep]
        add_elf(next(x for x in candidates if target_resolve(x).is_file()))

for command in ['mke2fs', 'e2fsck', 'blkid']:
    add_elf('sbin/' + command)
put('etc/mke2fs.conf', (stage / 'etc/mke2fs.conf').read_bytes(), stat.S_IFREG | 0o644)
buf = bytearray()
records = []
for index, name in enumerate(sorted(entries), 1):
    mode, data, major, minor = entries[name]
    fields = [index, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(name.encode()) + 1, 0]
    buf.extend(b'070701' + b''.join(f'{x:08x}'.encode() for x in fields))
    buf.extend(name.encode() + b'\0')
    buf.extend(b'\0' * (-len(buf) % 4))
    buf.extend(data)
    buf.extend(b'\0' * (-len(buf) % 4))
    records.append({'name': name, 'mode': oct(mode), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
fields = [len(entries) + 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 11, 0]
buf.extend(b'070701' + b''.join(f'{x:08x}'.encode() for x in fields) + b'TRAILER!!!\0')
buf.extend(b'\0' * (-len(buf) % 512))
(out / 'rescue-initramfs.cpio.gz').write_bytes(gzip.compress(buf, compresslevel=9, mtime=0))
(out / 'initramfs-records.json').write_text(json.dumps(records, indent=2) + '\n')

# Keep the board's logos, replacing only its kernel DTB in a standard resource image.
original = (root / 'backups/android-original-20261110-01/boot.img').read_bytes()
assert hashlib.sha256(original).hexdigest() == '0edf6e9967cafae5e6970abde398135347ab8c10b6cd9832514f1671a34714b2'
k, _, r, _, size, _, _, page = struct.unpack_from('<8I', original, 8)
align = lambda n: (n + 511) // 512 * 512
offset = page + (k + page - 1) // page * page + (r + page - 1) // page * page
resc = original[offset:offset + size]
assert resc[:4] == b'RSCE'
count = struct.unpack_from('<I', resc, 12)[0]
output = bytearray(resc[:512] + b'\0' * (count * 512))
for i in range(count):
    entry = bytearray(resc[512 * (i + 1):512 * (i + 2)])
    name = bytes(entry[4:224]).split(b'\0')[0].decode()
    old_block, old_size = struct.unpack_from('<II', entry, 260)
    data = dtb if name == 'rk-kernel.dtb' else resc[old_block * 512:old_block * 512 + old_size]
    assert data
    entry[224:256] = hashlib.sha256(data).digest()
    struct.pack_into('<III', entry, 256, 32, len(output) // 512, len(data))
    output[512 * (i + 1):512 * (i + 2)] = entry
    output.extend(data + b'\0' * (align(len(data)) - len(data)))
(out / 'resource.img').write_bytes(output)
its = '''/dts-v1/;
/ {
 description = "Taishan Pi Ubuntu 24.04.5 Linux 6.18.62 eMMC";
 #address-cells = <1>;
 images {
  fdt { data = /incbin/("board.dtb"); type = "flat_dt"; arch = "arm64"; compression = "none"; load = <0x20000000>; hash { algo = "sha256"; }; };
  kernel { data = /incbin/("Image.gz"); type = "kernel"; arch = "arm64"; os = "linux"; compression = "gzip"; load = <0x00200000>; entry = <0x00200000>; hash { algo = "sha256"; }; };
  ramdisk { data = /incbin/("rescue-initramfs.cpio.gz"); type = "ramdisk"; arch = "arm64"; os = "linux"; compression = "none"; load = <0x21000000>; hash { algo = "sha256"; }; };
  resource { data = /incbin/("resource.img"); type = "multi"; arch = "arm64"; compression = "none"; hash { algo = "sha256"; }; };
 };
 configurations { default = "conf"; conf { description = "Ubuntu persistent rootfs with serial rescue"; rollback-index = <0>; fdt = "fdt"; kernel = "kernel"; ramdisk = "ramdisk"; multi = "resource"; }; };
};
'''
(out / 'boot.its').write_text(its)
print(json.dumps({'kernel_gzip_bytes': (out / 'Image.gz').stat().st_size, 'initramfs_gzip_bytes': (out / 'rescue-initramfs.cpio.gz').stat().st_size, 'resource_bytes': len(output)}))
