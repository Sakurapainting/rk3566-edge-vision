# 构建说明

当前产物针对主机侧验证和后续 RAM-only bring-up 准备。内核版本、rootfs 归档及上游 DTB 都已固定记录；实板 PCB 修订仍未确认，不能把构建成功当作板上兼容性结论。

## 本机容器构建

构建环境为 Debian Bookworm x86_64，AArch64 GCC 12.2。需要 `bc bison build-essential ca-certificates curl device-tree-compiler flex gcc-aarch64-linux-gnu jq kmod libc6-dev-arm64-cross libelf-dev libssl-dev python3 rsync xz-utils`。

```sh
tools/build-kernel.sh
sudo tools/build-ubuntu-base-rootfs.sh
```

rootfs 脚本需要 root 或 user namespace，以保留归档中的 ARM64 rootfs 所有权。两步输出到 `build/artifacts/tspi-linux-6.18.62/`，每次完成后可运行：

```sh
(cd build/artifacts/tspi-linux-6.18.62 && sha256sum -c SHA256SUMS)
```

## GitHub Actions

`.github/workflows/build-linux.yml` 提供 `workflow_dispatch` 手动任务：安装依赖、构建内核和模块、组装 Ubuntu Base rootfs，并将产物作为 14 天 artifact 上传。后续部署以 Actions 运行产物为准；本地编译仅用于需要时的对照或故障排查。

2026-11-10 首次云端构建通过，运行 ID `42811216799`，artifact 名为 `tspi-linux-42811216799`。下载 ZIP 后先在解压目录执行 `sha256sum -c SHA256SUMS`。该 artifact 计划于 2026-11-24 过期；需要长期保留的版本应提前下载并另行归档。

云端产物包含 `Image`、候选 DTB、模块包、Ubuntu Base rootfs tar、`kernel.config`、`System.map`、`Module.symvers`、kernel release、构建清单和 `SHA256SUMS`。Git 仓库中的 `config/`、构建脚本和 `rootfs/init.c` 是重建输入，不能当作生成产物删除。

rootfs 是下载已编译好的 Ubuntu Base ARM64、加入匹配模块和静态 PID 1 后打包；它不从源代码编译完整 Ubuntu 用户态。

## 限制

- `rk3566-lckfb-tspi.dtb` 是上游板族候选；实板 Android FDT compatible 为 `lckfb,tspi-v10`，兼容性未确认。
- rootfs 是压缩 tar 归档，不是 ext4 分区镜像或可直接烧写的整机镜像。
- rootfs 的 PID 1 提供串口 root shell，仅用于隔离 bring-up 测试，不可用于联网或正式部署。
- 未在泰山派上启动此内核、DTB 或 rootfs，也未将任何新产物写入 eMMC。
