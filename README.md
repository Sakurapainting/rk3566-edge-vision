# RK3566 Edge Vision Build

[简体中文](README.zh-CN.md) | English

This repository contains build and deployment tools for an ARM64 Linux kernel, device tree, and Ubuntu root filesystem for the LCSC Taishan Pi RK3566. Build inputs are pinned in `config/versions.env`; see `BUILD.md` for the build paths and validation scope.

## Deployment status

On 2026-11-11, Ubuntu 24.04.5 ARM64 with Linux 6.18.62 was installed to eMMC and booted on the board. The kernel `Image` came from GitHub Actions run `42811216799`. The board-family mainline DTB was derived with the observed two-bank RAM layout and serial boot arguments, then packaged with the kernel and rescue initramfs as a FIT image.

The FIT image is installed in eMMC p7; the Ubuntu ext4 root filesystem is installed in p14. To make the vendor boot flow select normal FIT boot, the legacy recovery message at offset 16 KiB in misc p4 was cleared over its 2 KiB range; the rest of p4 was preserved. The GPT, U-Boot, trust, recovery, and other regions were preserved. The serial console uses `ttyS2` at 1,500,000 baud, 8N1, with root autologin enabled for local development.

Two normal eMMC boots passed, including one software reboot initiated from Ubuntu. systemd was running with zero failed units, the root filesystem was mounted read-write from p14, and a persistent file survived reboot. A physical power-cycle cold boot has not been tested.

## Artifacts

Deployment outputs are kept locally under `build/emmc-deploy-20261111-01/` and are not committed to Git:

- `boot-02/boot.itb`: FIT container, about 19 MB before partition padding.
- `usb-payload-03/boot.img`: the 40 MiB padded image written to p7.
- `ubuntu-rootfs.tar.gz`: root filesystem archive. The installer creates an ext4 filesystem on p14 and extracts this archive; it is not a raw partition image.
- `usb-payload-03/`: deployment payload with the boot image, rootfs archive, installer, checksums, manifest, and original boot-partition backup.

GitHub Actions run `42811216799` supplied the kernel, modules, and Ubuntu Base starting archive used for this deployment. Its artifact is named `tspi-linux-42811216799` and is scheduled to expire on 2026-11-24. A checksum-verified copy is archived locally. The final FIT and eMMC root filesystem were assembled locally with board-specific configuration and additional packages.

## Not yet validated

- The exact physical PCB revision is unknown. The derived DTB has booted successfully, but this does not validate every board peripheral.
- UVC camera capture, RKNN inference, display, USB 3 throughput, and sustained-load testing remain open.
- The Wi-Fi driver and firmware load, but the external antenna is unavailable and the target network was not found. Authentication, DHCP, and DNS remain unverified. Bluetooth firmware patches and UART DMA fallback are also unverified.
- A physical power-cycle cold boot and full Maskrom recovery have not been tested.
- Serial root autologin is a development configuration, not suitable for production or exposure to an untrusted network.

Build inputs, procedures, and limitations are documented in [BUILD.md](BUILD.md). Generated outputs, board backups, and test evidence remain local and are not source files; verify the matching `SHA256SUMS` and manifest before deployment.
