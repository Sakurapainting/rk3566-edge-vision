#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json,shutil,struct,tarfile,zlib
p=argparse.ArgumentParser();p.add_argument("--boot-directory",default="boot");p.add_argument("--payload-directory",default="usb-payload");a=p.parse_args()
out=Path('build/emmc-deploy-20261111-01');dst=out/a.payload_directory;dst.mkdir(exist_ok=True)
fit=(out/a.boot_directory/'boot.itb').read_bytes(); assert len(fit)<41943040 and struct.unpack_from('>I',fit,4)[0]<4096
(dst/'boot.img').write_bytes(fit+b'\0'*(41943040-len(fit)))
shutil.copyfile(out/'ubuntu-rootfs.tar.gz',dst/'ubuntu-rootfs.tar.gz')
shutil.copyfile('backups/android-original-20261110-01/boot.img',dst/'original-boot.img')
shutil.copyfile('rootfs/install-emmc-rootfs.sh',dst/'install-rootfs.sh')
shutil.copyfile(out/a.boot_directory/'board.dtb',dst/'board.dtb')
files={f.name:{'bytes':f.stat().st_size,'sha256':hashlib.file_digest(f.open('rb'),'sha256').hexdigest(),'crc32':f'{zlib.crc32(f.read_bytes()):08x}'} for f in sorted(dst.iterdir()) if f.name in ['boot.img','original-boot.img','ubuntu-rootfs.tar.gz','install-rootfs.sh','board.dtb']}
with tarfile.open(dst/'ubuntu-rootfs.tar.gz') as t:
 members={x.name.removeprefix('./'):x for x in t.getmembers()}
 assert members['usr/sbin/init'].issym() and members['usr/sbin/init'].linkname=='../lib/systemd/systemd'
 assert members['etc/machine-id'].size==0
 assert 'init' not in members and 'usr/sbin/tspi-ram-tools' not in members
 for n in ['etc/fstab','etc/tspi-build-info','etc/systemd/system/serial-getty@ttyS2.service.d/override.conf','etc/modules-load.d/tspi.conf','usr/lib/firmware/brcm/brcmfmac43430-sdio.bin']:
  assert n in members,n
 status=t.extractfile(members['var/lib/dpkg/status']).read().decode()
 for pkg in ['systemd','systemd-sysv','udev','systemd-resolved']:
  records=[p for p in status.split('\n\n') if p.startswith('Package: '+pkg+'\n')];assert len(records)==1 and 'Status: install ok installed' in records[0],pkg
 assert not any('wellrun-guest-password' in n or n.startswith('build/private') or n.endswith('.core') for n in members)
manifest={'schema':1,'date':'2026-11-11','board_serial':'86b2acaf11e3305','emmc_cid':'150100414a5444345206c9a794736a00','soc':'rk3566','kernel':'6.18.62','ubuntu':'24.04.5 arm64','authorization':'User: then do it (after asking to flash and debug via UART)','hardware_boot_validated':False,'fit_bytes_unpadded':len(fit),'boot_partition_bytes':41943040,'targets':{'boot':{'partition':7,'start':51200,'sectors':81920,'partuuid':'297b0000-0000-493e-8000-5df200004702'},'rootfs':{'partition':14,'start':8310784,'sectors':22224832,'partuuid':'153f0000-0000-4c04-8000-6fb500005626','label':'tspi-root','uuid':'2cce377d-b731-4de2-ac51-e8ad1d44f466'}},'files':files,'fit_ram_load':'0x30000000','kernel_load_entry':'0x00200000','kernel_runtime_reserved_bytes':51249152,'fdt_load':'0x20000000','initrd_load':'0x21000000','initrd_reserved_bytes':8388608,'preserve':['GPT','DDR loader','U-Boot','trust','recovery','super'],'rootfs_package_audit':'passed','initramfs_order_and_qemu_tools':'passed','credentials_included':False,'automatic_reboot_guard':False,'remaining':'Hardware FIT boot with default environment; install rootfs; systemd validation; boot write/readback; persistent restart validation'}
(dst/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(dst/'README.txt').write_text('Authorized persistent eMMC Ubuntu deployment, 2026-11-11.\nInstall userdata p14 only from the serial RAM rescue environment, verify systemd, then write boot p7.\nKeep GPT, loader, U-Boot, trust and recovery. No Wi-Fi credentials included.\nOriginal boot SHA256: 0edf6e9967cafae5e6970abde398135347ab8c10b6cd9832514f1671a34714b2\nU-Boot recovery (verify serial# and GPT first; USB KIOXIA must be usb 0:1):\nfatload usb 0:1 30000000 /tspi-emmc/original-boot.img\ncrc32 30000000 2800000\n# expected CRC32: '+files['original-boot.img']['crc32']+'\nmmc dev 0\nmmc write 30000000 c800 14000\nmmc read 34000000 c800 14000\ncrc32 34000000 2800000\n# same CRC32 required. This restores boot only; Android userdata has been replaced.\nRAM USB Linux remains available independently. Full Maskrom restore has not been exercised.\n')
with (dst/'README.txt').open('a') as readme:
 readme.write('\nBoot-mode compatibility for this board: the original misc image contains a stale boot-recovery message at byte offset 16384. Android >=10 used BCB offset 0, while the vendor loader selects the legacy 16KiB offset for a FIT boot. Inspect both offsets before the first automatic FIT boot. After checking the board identity, partition bounds and original misc SHA256 c2ab93407bfab2e256943f9e3400c7a806e4b63716061d6ee1c9d6d92fd8e1ee, clear only the 2048-byte legacy BCB message at offset 16384. The expected full 4MiB misc SHA256 is then 709be7d58cdad9db99b7503a37e44f72de0a0a48983d5a97d81b91d4b43d36a1. All bytes outside that message must remain unchanged. See evidence/emmc-deployment-20261111.md for the observed recovery detour and verified correction.\n')
(dst/'SHA256SUMS').write_text(''.join(hashlib.file_digest(f.open('rb'),'sha256').hexdigest()+'  '+f.name+'\n' for f in sorted(dst.iterdir()) if f.name!='SHA256SUMS'))
print(json.dumps({'payload':str(dst),'files':files,'host_validation':'passed'},indent=2))
