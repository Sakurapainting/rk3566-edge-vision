# RK3566 Edge Vision Build

This repository builds an ARM64 Linux kernel and a minimal Ubuntu Base rootfs for the LCSC Taishan Pi RK3566 board family.

The build inputs are pinned in `config/versions.env`. Run `tools/build-kernel.sh` followed by `sudo tools/build-ubuntu-base-rootfs.sh` for a local build, or dispatch the `RK3566 Linux and rootfs build` workflow from the GitHub Actions page. The workflow uploads a 14-day artifact containing the kernel image, candidate DTB, modules, rootfs archive, build metadata, and SHA256 checksums.

The DTB is an upstream board-family candidate and has not been validated against the exact PCB revision. The rootfs is a tar archive with a temporary serial root shell; it is not a partition image or a production system. No artifact in this repository has been booted on the board.

Device backups, raw hardware captures, local source downloads, and generated build outputs are intentionally kept outside this build repository. See `BUILD.md` for prerequisites and output details.
