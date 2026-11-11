#!/usr/bin/env python3
"""Extract newc entries in archive order, without creating missing parents.

Like Linux initramfs.c, a failed file creation does not abort later entries.
Unlike permissive test extractors, this reports every failed creation and
checks the actual init interpreter, ELF loader and retained PID1 afterward.
Device nodes are counted but not created on the host.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import struct

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--archive',type=Path,required=True)
p.add_argument('--extract',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--required-executable', action='append', help='Override the default Ubuntu executable checks')
a=p.parse_args()
a.extract.mkdir(exist_ok=False)
root=a.extract.resolve()
failures=[]
records=[]
offset=0
with gzip.open(a.archive,'rb') as s:
    while True:
        lead=s.read(1)
        if not lead:
            break
        if lead==b'\0':
            offset+=1
            continue
        h=lead+s.read(109)
        assert offset%4==0 and h[:6]==b'070701',(offset,h[:6])
        v=[int(h[6+i*8:14+i*8],16) for i in range(13)]
        size,namesize=v[6],v[11]
        n=s.read(namesize)
        assert n[-1:]==b'\0'
        name=n[:-1].decode()
        assert not name.startswith('/') and '..' not in PurePosixPath(name).parts
        offset+=110+namesize
        pad=-offset%4
        assert not s.read(pad).strip(b'\0')
        offset+=pad
        data=s.read(size)
        assert len(data)==size
        offset+=size
        pad=-offset%4
        assert not s.read(pad).strip(b'\0')
        offset+=pad
        records.append(dict(name=name,mode=oct(v[1]),bytes=size,sha256=hashlib.sha256(data).hexdigest()))
        if name=='TRAILER!!!':
            continue
        dest=root/name
        assert dest.parent.resolve().is_relative_to(root)
        mode=v[1]
        try:
            if dest.exists() or dest.is_symlink():
                old=dest.lstat().st_mode
                if stat.S_IFMT(old)!=stat.S_IFMT(mode) or stat.S_ISLNK(mode):
                    if stat.S_ISDIR(old):
                        dest.rmdir()
                    else:
                        dest.unlink()
            if stat.S_ISDIR(mode):
                if not dest.exists():
                    dest.mkdir()
                dest.chmod(stat.S_IMODE(mode))
            elif stat.S_ISLNK(mode):
                dest.symlink_to(data.decode())
            elif stat.S_ISREG(mode):
                dest.write_bytes(data)
                dest.chmod(stat.S_IMODE(mode))
            else:
                assert stat.S_ISCHR(mode) or stat.S_ISBLK(mode)
        except OSError as exc:
            failures.append(dict(name=name,errno=exc.errno))

checks={}
for n in (a.required_executable or ['init','bin/bash','bin/sh','sbin/init','usr/lib/aarch64-linux-gnu/ld-linux-aarch64.so.1',
          'usr/sbin/iw','usr/sbin/wpa_supplicant','usr/bin/busybox']):
    path=root/n
    ok=path.is_file() and os.access(path,os.X_OK)
    checks[n]=dict(exists_executable=ok)
    if ok:
        b=path.read_bytes()
        checks[n]['sha256']=hashlib.sha256(b).hexdigest()
        if b.startswith(b'\x7fELF'):
            assert b[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',b,18)[0]==183
            phoff=struct.unpack_from('<Q',b,32)[0]
            phsize,phnum=struct.unpack_from('<HH',b,54)
            for i in range(phnum):
                ph=phoff+i*phsize
                if struct.unpack_from('<I',b,ph)[0]==3:
                    lo=struct.unpack_from('<Q',b,ph+8)[0]
                    length=struct.unpack_from('<Q',b,ph+32)[0]
                    interp=b[lo:lo+length].rstrip(b'\0').decode()
                    checks[n].update(elf_interpreter=interp,elf_interpreter_present=(root/interp.lstrip('/')).is_file())
        elif b.startswith(b'#!'):
            interp=b.splitlines()[0][2:].strip().decode().split()[0]
            checks[n].update(script_interpreter=interp,script_interpreter_present=(root/interp.lstrip('/')).is_file())
passed=not failures and all(c['exists_executable'] and c.get('elf_interpreter_present',True) and c.get('script_interpreter_present',True) for c in checks.values())
result=dict(archive=str(a.archive.resolve()),archive_sha256=hashlib.file_digest(a.archive.open('rb'),'sha256').hexdigest(),
            entry_count=len(records),cpio_bytes=offset,failed_creations=len(failures),first_failures=failures[:12],
            checks=checks,ordered_extraction_passed=passed,scope='Ordered file extraction and init/ELF paths; not hardware or radio emulation')
a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
raise SystemExit(0 if passed else 1)
