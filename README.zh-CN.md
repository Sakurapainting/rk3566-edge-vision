# 泰山派 RK3566 边缘视觉构建

[简体中文](README.zh-CN.md) | [English](README.md)

本仓库用于为立创泰山派 RK3566 板族构建 ARM64 Linux 内核和精简 Ubuntu Base rootfs。

构建输入版本记录在 `config/versions.env`。后续部署以 GitHub Actions 产物为准；本地构建脚本用于对照和故障排查。手动运行 `RK3566 Linux and rootfs build` workflow 后，会生成保留 14 天的 artifact，其中包括内核镜像、候选 DTB、模块包、rootfs 归档、构建信息和 SHA256 校验文件。使用前先下载并运行 `sha256sum -c SHA256SUMS`；需要长期保留的产物请及时归档。

2026-11-10 的云端构建运行 ID 为 `42811216799`，artifact 名称为 `tspi-linux-42811216799`，计划于 2026-11-24 过期。

**当前限制：** DTB 是上游板族候选，尚未针对实物 PCB 修订验证。板上 Android FDT 的 compatible 为 `lckfb,tspi-v10`，当前候选 DTB 的 compatible 与之不同。仓库中的产物尚未在板上启动。rootfs 是带临时串口 root shell 的 tar 归档，不是分区镜像或可直接烧写的整机镜像，也不适合正式或联网部署。

设备备份、原始硬件采集、本地源码下载和生成的构建文件不放在本构建仓库。构建依赖与产物说明见 [BUILD.md](BUILD.md)。
