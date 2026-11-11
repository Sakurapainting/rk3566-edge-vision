#!/usr/bin/env python3
"""Repack the verified cloud Ubuntu tar as a guarded, RAM-only newc initramfs."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import struct
import subprocess
import tarfile
import zlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--restart-seconds', type=int, default=180)
parser.add_argument('--overlay', type=Path, help='Additional rootfs files; /bin, /sbin and /lib are merged into /usr')
parser.add_argument('--wifi', action='store_true', help='Include the bounded, credential-free wireless probe')
args = parser.parse_args()
assert 60 <= args.restart_seconds <= 1800
root = Path(__file__).resolve().parent.parent
archive_dir = root / 'build/archive/tspi-linux-42811216799/extracted'
archive = archive_dir / 'ubuntu-base-24.04.5-tspi-arm64.tar.gz'
expected = {line.split(maxsplit=1)[1].removeprefix('./'): line.split()[0]
            for line in (archive_dir / 'SHA256SUMS').read_text().splitlines()}
archive_sha = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
assert archive_sha == expected[archive.name]
args.output.mkdir(exist_ok=False)

source = root / 'rootfs/ubuntu-ram-tools.c'
helper = args.output / 'tspi-ram-tools'
command = ['clang', '--target=aarch64-linux-gnu', '-O2', '-ffreestanding',
           '-nostdlib', '-static', '-fno-builtin', '-fno-stack-protector',
           '-Wall', '-Wextra', '-Werror', '-fuse-ld=lld', '-Wl,--build-id=none',
           '-Wl,-z,max-page-size=4096', '-Wl,-e,_start', str(source), '-o', str(helper)]
compiled = subprocess.run(command, capture_output=True)
(args.output / 'compile.stderr').write_bytes(compiled.stderr)
compiled.check_returncode()
elf = helper.read_bytes()
assert elf[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', elf, 18)[0] == 183
phoff = struct.unpack_from('<Q', elf, 32)[0]
phsize, phnum = struct.unpack_from('<HH', elf, 54)
assert all(struct.unpack_from('<I', elf, phoff + i * phsize)[0] != 3 for i in range(phnum))
init = (root / 'rootfs/ubuntu-ram-init.sh').read_bytes()
subprocess.run(['bash', '-n', str(root / 'rootfs/ubuntu-ram-init.sh')], check=True)
assert b'/sbin/tspi-ram-tools return 180 &' in init
init = init.replace(b'/sbin/tspi-ram-tools return 180 &',
                    f'/sbin/tspi-ram-tools return {args.restart_seconds} &'.encode())
if args.wifi:
    assert args.overlay
    ready = b"printf '\\nG5_UBUNTU_READY_20261111\\n'"
    assert ready in init
    init = init.replace(ready,
                        b'timeout 75 /usr/sbin/tspi-wifi-probe || printf "WIFI_PROBE_FAILED=%s\\n" "$?"\n' + ready)
profile = b"export HISTFILE=/dev/null\nexport PS1='TSPI_UBUNTU_RAM# '\n"
overlays = {
    'init': (stat.S_IFREG | 0o755, init),
    'usr/sbin/tspi-ram-tools': (stat.S_IFREG | 0o755, elf),
    'root/.bash_profile': (stat.S_IFREG | 0o644, profile),
    'dev/console': (stat.S_IFCHR | 0o600, b''),
}
if args.overlay:
    assert args.overlay.is_dir()
    for path in sorted(args.overlay.rglob('*')):
        name = path.relative_to(args.overlay).as_posix()
        first, _, rest = name.partition('/')
        if first in {'bin', 'sbin', 'lib', 'lib64'}:
            if not rest:
                assert path.is_dir() and not path.is_symlink()
                continue
            name = 'usr/' + name
        mode = path.lstat().st_mode
        assert not name.startswith('/') and '..' not in PurePosixPath(name).parts
        assert stat.S_ISDIR(mode) or stat.S_ISREG(mode) or stat.S_ISLNK(mode), path
        data = path.readlink().as_posix().encode() if stat.S_ISLNK(mode) else b'' if stat.S_ISDIR(mode) else path.read_bytes()
        if name in overlays:
            assert overlays[name] == (mode, data), name
        else:
            overlays[name] = (mode, data)
if args.wifi:
    for suffix in ['probe', 'connect', 'dhcp']:
        wifi = root / f'rootfs/ubuntu-wifi-{suffix}.sh'
        subprocess.run(['bash', '-n', str(wifi)], check=True)
        overlays[f'usr/sbin/tspi-wifi-{suffix}'] = (stat.S_IFREG | 0o755, wifi.read_bytes())


def safe_name(name):
    p = PurePosixPath(name)
    assert not p.is_absolute() and '..' not in p.parts, name
    return str(p)


output = args.output / 'ubuntu-ram-initramfs.cpio.gz'
records = []
position = 0
with tarfile.open(archive) as tar, output.open('wb') as raw:
    members = {safe_name(m.name): m for m in tar.getmembers()}
    assert 'init' not in members
    assert 'usr/sbin/init' in members and 'usr/bin/bash' in members
    cloud_init = tar.extractfile(members['usr/sbin/init']).read()
    cloud_manifest = json.loads((archive_dir / 'rootfs-build-manifest.json').read_text())
    assert hashlib.sha256(cloud_init).hexdigest() == cloud_manifest['pid1_sha256']
    assert cloud_manifest['matching_kernel_release'] == '6.18.62'
    for filename in ['usr/bin/bash', 'usr/bin/mount', 'usr/bin/dpkg',
                     'usr/bin/getconf', 'usr/sbin/blockdev',
                     'usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1',
                     'usr/lib/modules/6.18.62/kernel/drivers/reset/reset-gpio.ko',
                     'usr/lib/modules/6.18.62/kernel/drivers/phy/rockchip/phy-rockchip-naneng-combphy.ko']:
        assert filename in members, filename
    with gzip.GzipFile(filename='', mode='wb', compresslevel=6, mtime=0, fileobj=raw) as gz:
        def write(data):
            global position
            gz.write(data)
            position += len(data)

        def entry(name, mode, data, uid=0, gid=0, major=0, minor=0):
            fields = [len(records) + 1, mode, uid, gid, 1, 0, len(data), 0, 0,
                      major, minor, len(name.encode()) + 1, 0]
            write(b'070701' + b''.join(f'{x:08x}'.encode() for x in fields))
            write(name.encode() + b'\0')
            write(b'\0' * (-position % 4))
            write(data)
            write(b'\0' * (-position % 4))
            records.append({'name': name, 'mode': oct(mode), 'bytes': len(data),
                            'uid': uid, 'gid': gid, 'sha256': hashlib.sha256(data).hexdigest()})

        # Merge names before sorting: replacing a directory must not move it
        # behind its original children. The kernel does not create parents.
        for name in sorted(set(members) | set(overlays)):
            if name == '.':
                continue
            if name in overlays:
                mode, data = overlays[name]
                entry(name, mode, data, major=5 if name == 'dev/console' else 0,
                      minor=1 if name == 'dev/console' else 0)
                continue
            member = members[name]
            if member.isdir():
                kind, data = stat.S_IFDIR, b''
            elif member.issym():
                kind, data = stat.S_IFLNK, member.linkname.encode()
            elif member.isfile() or member.islnk():
                kind, data = stat.S_IFREG, tar.extractfile(member).read()
            else:
                raise ValueError(f'Unsupported tar member type: {name} {member.type!r}')
            entry(name, kind | member.mode, data, member.uid, member.gid)
        entry('TRAILER!!!', 0, b'')
        write(b'\0' * (-position % 512))

# Re-read the complete gzip/newc independently to catch truncation and header errors.
with gzip.open(output, 'rb') as stream:
    offset = 0
    created_directories = {'.'}
    for record in records:
        header = stream.read(110)
        assert header[:6] == b'070701'
        values = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        size, namesize = values[6], values[11]
        name = stream.read(namesize)
        assert name[-1:] == b'\0' and name[:-1].decode() == record['name']
        offset += 110 + namesize
        stream.read(-offset % 4)
        offset += -offset % 4
        data = stream.read(size)
        assert len(data) == size and hashlib.sha256(data).hexdigest() == record['sha256']
        if record['name'] != 'TRAILER!!!':
            parent = str(PurePosixPath(record['name']).parent)
            assert parent in created_directories, (record['name'], 'parent must precede child', parent)
            if stat.S_ISDIR(values[1]):
                created_directories.add(record['name'])
        offset += size
        stream.read(-offset % 4)
        offset += -offset % 4
    assert not stream.read().strip(b'\0')
size = output.stat().st_size
assert size < 128 * 1024 * 1024
digest = hashlib.file_digest(output.open('rb'), 'sha256').hexdigest()
crc = 0
with output.open('rb') as stream:
    while chunk := stream.read(1024 * 1024):
        crc = zlib.crc32(chunk, crc)
manifest = {
    'purpose': f'Cloud Ubuntu userspace and modules in RAM; serial shell; {args.restart_seconds} s automatic reboot',
    'source_archive': str(archive), 'source_archive_sha256': archive_sha,
    'cloud_actions_run': '42811216799', 'kernelrelease': '6.18.62',
    'cloud_pid1_sha256': hashlib.sha256(cloud_init).hexdigest(),
    'helper_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'init_script_sha256': hashlib.sha256(init).hexdigest(),
    'init_source_sha256': hashlib.sha256((root / 'rootfs/ubuntu-ram-init.sh').read_bytes()).hexdigest(),
    'helper_build_command': command, 'helper_sha256': hashlib.sha256(elf).hexdigest(),
    'archive_bytes': size, 'archive_sha256': digest, 'archive_crc32': f'{crc:08x}',
    'cpio_bytes': position, 'entry_count': len(records),
    'cloud_hardlinks': 'materialized as independent regular files with identical content',
    'overlay_paths': sorted(overlays), 'automatic_restart_seconds': args.restart_seconds,
    'wifi_probe_included': args.wifi,
    'load_address': '0x21000000', 'reserved_bytes': 128 * 1024 * 1024,
    'reserved_end': '0x29000000', 'planned_usb_path': '/tspi-ubuntu/ubuntu-ram-initramfs.cpio.gz',
    'expected_markers': ['G5_UBUNTU_READY_20261111', 'G5_UBUNTU_RESTART_20261111'],
    'expected_shell_prompt': 'TSPI_UBUNTU_RAM# ',
    'disk_filesystem_mounts_in_wrapper': False,
    'board_boot_tested': False,
    'memory_map_status': 'proposed; must refresh U-Boot allocations after USB and before load/boot',
}
(args.output / 'entries.json').write_text(json.dumps(records, indent=2) + '\n')
(args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(args.output / 'SHA256SUMS').write_text(f'{digest}  {output.name}\n')
print(json.dumps({k: manifest[k] for k in ['archive_bytes', 'archive_sha256', 'archive_crc32', 'cpio_bytes', 'entry_count']}))
