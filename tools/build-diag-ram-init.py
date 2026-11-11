#!/usr/bin/env python3
"""Build the syscall-only diagnostic PID1 with two verified cloud modules."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tarfile
import zlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
archive_dir = root / "build/archive/tspi-linux-42811216799/extracted"
args.output.mkdir(exist_ok=False)
expected = {line.split(maxsplit=1)[1].removeprefix("./"): line.split()[0]
            for line in (archive_dir / "SHA256SUMS").read_text().splitlines()}
archive = archive_dir / "modules-6.18.62.tar.gz"
archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
assert archive_sha == expected[archive.name]
modules = {}
with tarfile.open(archive) as tar:
    for member in tar:
        if member.name.endswith(("/reset-gpio.ko", "/phy-rockchip-naneng-combphy.ko")):
            data = tar.extractfile(member).read()
            assert b"vermagic=6.18.62 " in data
            modules[Path(member.name).name] = data
assert len(modules) == 2
source = root / "rootfs/diag-init.c"
command = ["clang", "--target=aarch64-linux-gnu", "-O2", "-ffreestanding",
           "-nostdlib", "-static", "-fno-builtin", "-fno-stack-protector",
           "-Wall", "-Wextra", "-Werror", "-fuse-ld=lld", "-Wl,--build-id=none",
           "-Wl,-z,max-page-size=4096", "-Wl,-e,_start", str(source),
           "-o", str(args.output / "init")]
result = subprocess.run(command, capture_output=True)
(args.output / "compile.stderr").write_bytes(result.stderr)
result.check_returncode()
elf = (args.output / "init").read_bytes()
assert elf[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", elf, 18)[0] == 183
phoff = struct.unpack_from("<Q", elf, 32)[0]
phsize, phnum = struct.unpack_from("<HH", elf, 54)
assert all(struct.unpack_from("<I", elf, phoff + i * phsize)[0] != 3 for i in range(phnum))
cpio = bytearray()
entries = []


def entry(name, mode, data=b"", major=0, minor=0):
    fields = [len(entries) + 1, mode, 0, 0, 1, 0, len(data), 0, 0,
              major, minor, len(name.encode()) + 1, 0]
    cpio.extend(b"070701" + b"".join(f"{v:08x}".encode() for v in fields))
    cpio.extend(name.encode() + b"\0")
    cpio.extend(b"\0" * (-len(cpio) % 4))
    cpio.extend(data)
    cpio.extend(b"\0" * (-len(cpio) % 4))
    entries.append({"name": name, "mode": oct(mode), "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest()})


for name in ("dev", "proc", "sys", "modules"):
    entry(name, 0o040755)
entry("dev/console", 0o020600, major=5, minor=1)
entry("init", 0o100755, elf)
for name, data in sorted(modules.items()):
    entry("modules/" + name, 0o100644, data)
entry("TRAILER!!!", 0)
cpio.extend(b"\0" * (-len(cpio) % 512))
blob = gzip.compress(cpio, compresslevel=9, mtime=0)
assert len(blob) < 1048576
(args.output / "diag-initramfs.cpio.gz").write_bytes(blob)
manifest = {
    "purpose": "RAM diagnostics: pseudo filesystems, temporary BLKROSET, two cloud modules, live FDT dump and automatic restart",
    "kernelrelease": "6.18.62", "cloud_run": "42811216799",
    "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "build_command": command, "module_archive_sha256": archive_sha,
    "initramfs_bytes": len(blob), "initramfs_sha256": hashlib.sha256(blob).hexdigest(),
    "initramfs_crc32": f"{zlib.crc32(blob):08x}", "uncompressed_cpio_bytes": len(cpio),
    "entries": entries, "board_boot_tested": False,
    "load_address": "0x21000000", "reserved_end": "0x21100000",
    "planned_usb_path": "/tspi-diag/diag-initramfs.cpio.gz",
    "expected_markers": ["G4_DIAG_READY_20261111", "G4_DIAG_DONE_20261111", "G4_DIAG_RESTART_20261111"]
}
(args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({key: manifest[key] for key in
                  ("initramfs_bytes", "initramfs_sha256", "initramfs_crc32")}))
