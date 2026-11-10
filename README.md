# RK3566 Edge Vision Build

[简体中文](README.zh-CN.md) | English

This repository builds an ARM64 Linux kernel and a minimal Ubuntu Base rootfs for the LCSC Taishan Pi RK3566 board family.

The build inputs are pinned in `config/versions.env`. The GitHub Actions artifact is the canonical build output for deployment; local build scripts are available for comparison and troubleshooting. The manual `RK3566 Linux and rootfs build` workflow uploads a 14-day artifact containing the kernel image, candidate DTB, modules, rootfs archive, build metadata, and SHA256 checksums. Download and verify `SHA256SUMS` before use, and archive any output needed beyond the artifact retention period.

The DTB is an upstream board-family candidate and has not been validated against the exact PCB revision. The rootfs is a tar archive with a temporary serial root shell; it is not a partition image or a production system. No artifact in this repository has been booted on the board.

Device backups, raw hardware captures, local source downloads, and generated build outputs are intentionally kept outside this build repository. See `BUILD.md` for prerequisites and output details.
