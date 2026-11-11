# Build and Deployment

## Versions and Build Inputs

The deployed system uses Linux 6.18.62 and Ubuntu 24.04.5 ARM64. The kernel `Image` and matching modules came from GitHub Actions run `42811216799`. The eMMC root filesystem was assembled from the verified Ubuntu Base archive, matching kernel modules, board firmware, and additional Ubuntu packages. The board DTB is derived from the Linux mainline Taishan Pi family candidate and includes the observed RAM layout and boot arguments.

The exact physical PCB revision is unknown. The DTB and boot path have been validated sufficiently to boot the installed system, but this is not a complete validation of all peripherals.

## Base Kernel and Rootfs Build

The local container build environment is Debian Bookworm x86_64 with AArch64 GCC 12.2. Required packages are `bc bison build-essential ca-certificates curl device-tree-compiler flex gcc-aarch64-linux-gnu jq kmod libc6-dev-arm64-cross libelf-dev libssl-dev python3 rsync xz-utils`.

```sh
tools/build-kernel.sh
sudo tools/build-ubuntu-base-rootfs.sh
```

The scripts download version-pinned inputs and write base artifacts to `build/artifacts/tspi-linux-6.18.62/`. Verify the outputs with:

```sh
(cd build/artifacts/tspi-linux-6.18.62 && sha256sum -c SHA256SUMS)
```

The kernel build produces `Image`, the upstream board-family DTB, modules, kernel configuration, and build metadata. The base rootfs script starts from the official Ubuntu Base ARM64 archive, adds matching kernel modules and a minimal serial bring-up init. It does not compile the Ubuntu userspace from source.

## GitHub Actions

`.github/workflows/build-linux.yml` provides a manual `workflow_dispatch` build. It installs dependencies, builds the kernel/modules and base Ubuntu rootfs, then uploads a 14-day artifact with SHA256 checksums. Run `sha256sum -c SHA256SUMS` after downloading it. Run `42811216799` is the artifact used as the kernel and rootfs baseline for the deployed board; its artifact is scheduled to expire on 2026-11-24. A verified copy is archived locally under `build/archive/tspi-linux-42811216799/`.

## eMMC Deployment Package

The deployment-specific scripts are:

- `tools/build-emmc-rootfs.sh` assembles the Ubuntu 24.04.5 systemd rootfs, matching modules, firmware, network configuration, and serial getty configuration.
- `tools/build-emmc-boot.py` builds the rescue initramfs and FIT description from the kernel, board DTB, initramfs, and Rockchip resource image.
- `tools/package-emmc-deploy.py` creates the USB deployment payload, pads the FIT to the boot partition size, and records file hashes and partition metadata.
- `rootfs/install-emmc-rootfs.sh` validates the board/storage identities, creates ext4 on p14, extracts the rootfs archive, and runs an offline filesystem check.
- `rootfs/emmc-init.sh` runs from the initramfs at boot. It checks for the expected rootfs marker, mounts p14, and switches to systemd; if that check fails, it leaves a serial rescue shell.

The verified local output is under `build/emmc-deploy-20261111-01/`:

```text
boot-02/boot.itb                  FIT container, about 19 MB
boot-02/                           FIT inputs and listing, including board.dtb
ubuntu-rootfs.tar.gz              Ubuntu rootfs archive
usb-payload-03/boot.img           40 MiB padded image written to p7
usb-payload-03/ubuntu-rootfs.tar.gz
usb-payload-03/install-rootfs.sh
usb-payload-03/original-boot.img  Original boot partition backup
usb-payload-03/manifest.json
usb-payload-03/SHA256SUMS
```

`boot.img` is a raw FIT image padded to the fixed 40 MiB p7 size; it is not a filesystem image. `ubuntu-rootfs.tar.gz` is extracted into an ext4 filesystem created on p14. The FIT contains the compressed kernel, board DTB, rescue initramfs, and a Rockchip resource image carrying the DTB for the vendor U-Boot path. The deployment used the same mainline-derived DTB in the FIT and resource image because this U-Boot can prefer its preloaded control DTB over the FIT FDT.

The deployment package depends on the downloaded Actions artifact and local assembly inputs under `build/`, which are generated or ignored and are not included in a clean source checkout. Rebuilding the exact deployment package therefore requires restoring and checksum-verifying those inputs first. Do not treat the local `build/emmc-deploy-20261111-01/` directory as a versioned source artifact.

## Installation and Validation

The deployed FIT is on eMMC p7 and the Ubuntu root filesystem is on p14. The installer checked the board/eMMC identity and partition geometry before writing. The p14 ext4 filesystem passed `e2fsck`; the full p7 image passed a direct readback SHA256 check after write. A stale legacy recovery message in the board's misc partition was cleared at its specific 2 KiB range so the vendor boot flow would select normal FIT boot. The GPT, U-Boot, trust, recovery, and unrelated partitions were preserved.

Two default eMMC boots passed after the BCB correction, including a software reboot from Ubuntu. Validation confirmed Linux 6.18.62, Ubuntu 24.04.5 ARM64, systemd running with zero failed units, root mounted read-write from p14, serial root login on `ttyS2` at 1,500,000 baud/8N1, and a persistent file surviving reboot. No U-Boot environment update or `saveenv` was performed.

## Limits

- The exact PCB revision is unconfirmed. Successful boot and serial validation do not establish full peripheral compatibility.
- Physical power-cycle cold boot and full Maskrom recovery have not been tested.
- UVC camera capture, RKNN inference, display, USB 3 throughput, and sustained-load tests remain open.
- Wi-Fi driver/firmware load, but the external antenna was unavailable and the target network was not discovered. Authentication, DHCP, and DNS are unverified. Bluetooth patches and UART DMA fallback are also unverified.
- Serial root autologin is for local development only. Change the account and authentication configuration before using the image in a production or untrusted network environment.
