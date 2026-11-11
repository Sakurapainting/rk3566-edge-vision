#!/usr/bin/env python3
"""Prepend a directory-only newc member to an immutable, verified initramfs.

Linux init/initramfs.c accepts concatenated compressed cpio members. This
permits a small, hash-verified repair on the removable USB without modifying
the retained failing input. Future builds use the corrected merged ordering.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zlib

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--usb-directory', required=True)
a = p.parse_args()
base = a.source / 'ubuntu-ram-initramfs.cpio.gz'
m = json.loads((a.source / 'manifest.json').read_text())
assert hashlib.file_digest(base.open('rb'), 'sha256').hexdigest() == m['archive_sha256']
original = json.loads((a.source / 'entries.json').read_text())
dirs = [r for r in original if stat.S_ISDIR(int(r['mode'], 8))]
assert len({r['name'] for r in dirs}) == len(dirs)
a.output.mkdir(exist_ok=False)
payload = bytearray()
prefix_records = []
for i, r in enumerate(sorted(dirs, key=lambda r: r['name']) + [dict(name='TRAILER!!!', mode='0o0', uid=0, gid=0)]):
    name = r['name']
    assert not name.startswith('/') and '..' not in PurePosixPath(name).parts
    fields = [i+1, int(r['mode'], 8), r['uid'], r['gid'], 1, 0, 0, 0, 0, 0, 0, len(name.encode())+1, 0]
    payload.extend(b'070701' + b''.join(f'{v:08x}'.encode() for v in fields))
    payload.extend(name.encode() + b'\0')
    payload.extend(b'\0' * (-len(payload) % 4))
    prefix_records.append(dict(name=name, mode=r['mode'], uid=r['uid'], gid=r['gid'], bytes=0,
                               sha256=hashlib.sha256(b'').hexdigest()))
payload.extend(b'\0' * (-len(payload) % 512))
prefix = a.output / 'directory-prefix.cpio.gz'
prefix.write_bytes(gzip.compress(payload, compresslevel=6, mtime=0))
out = a.output / base.name
with out.open('wb') as stream:
    stream.write(prefix.read_bytes())
    with base.open('rb') as source:
        shutil.copyfileobj(source, stream)
digest = hashlib.file_digest(out.open('rb'), 'sha256').hexdigest()
crc = 0
with out.open('rb') as stream:
    while data := stream.read(1024*1024):
        crc = zlib.crc32(data, crc)
assert out.stat().st_size < 128*1024*1024
m.update(archive_bytes=out.stat().st_size, archive_sha256=digest, archive_crc32=f'{crc:08x}',
         cpio_bytes=m['cpio_bytes']+len(payload), entry_count=len(prefix_records)+len(original),
         purpose='RAM-only Ubuntu Wi-Fi test with directory prelude repair; 600 s automatic return',
         repair_source=str(a.source.resolve()), repair_source_sha256=m['archive_sha256'],
         directory_prefix_bytes=prefix.stat().st_size,
         directory_prefix_sha256=hashlib.file_digest(prefix.open('rb'), 'sha256').hexdigest(),
         directory_prefix_count=len(dirs),
         archive_structure='directory-only gzip/newc member followed by unchanged original gzip/newc member',
         planned_usb_path=a.usb_directory+'/'+base.name, board_boot_tested=False)
(a.output/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
(a.output/'entries.json').write_text(json.dumps(prefix_records+original,indent=2)+'\n')
b = json.loads((a.source/'boot-manifest.json').read_text())
b.update(purpose=m['purpose'], ubuntu_manifest=str((a.output/'manifest.json').resolve()))
for r in b['layout']:
    if r['name'] == base.name:
        r.update(file_size=m['archive_bytes'], usb_path=m['planned_usb_path'])
b['files'][base.name].update(bytes=m['archive_bytes'],sha256=digest,crc32=m['archive_crc32'])
(a.output/'boot-manifest.json').write_text(json.dumps(b,indent=2)+'\n')
names = [base.name, 'directory-prefix.cpio.gz', 'manifest.json', 'boot-manifest.json']
(a.output/'SHA256SUMS').write_text(''.join(hashlib.file_digest((a.output/n).open('rb'),'sha256').hexdigest()+'  '+n+'\n' for n in names))
print(json.dumps({k:m[k] for k in ['archive_bytes','archive_sha256','archive_crc32','directory_prefix_count','directory_prefix_bytes','directory_prefix_sha256']}))
