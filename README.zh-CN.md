# 泰山派 RK3566 边缘视觉构建

[简体中文](README.zh-CN.md) | [English](README.md)

本仓库包含立创泰山派 RK3566 的 Linux 内核、设备树、Ubuntu ARM64 根文件系统构建与部署工具。构建输入版本记录在 `config/versions.env`；具体部署使用的版本和验证范围见下文及 `BUILD.md`。

## 当前部署

2026-11-11，泰山派已安装并从 eMMC 启动 Ubuntu 24.04.5 ARM64、Linux 6.18.62。内核 `Image` 来自 GitHub Actions run `42811216799`；设备树基于 Linux 主线泰山派板族候选，加入实测双段 RAM 布局及串口启动参数。内核、设备树和救援 initramfs 被打包为 FIT 启动镜像。

FIT 写入 eMMC p7，Ubuntu ext4 根文件系统安装在 p14。为使厂商启动流程选择正常 FIT 启动，还清除了 misc p4 中偏移 16 KiB 处的 2 KiB 旧 recovery 标记；p4 其余数据保持不变。GPT、U-Boot、trust、recovery 等其他区域均保留。串口控制台为 `ttyS2`、1,500,000 baud、8N1，当前配置自动以 root 登录，仅适用于本地 bring-up/开发。

常规 eMMC 启动验证通过两次，其中一次由运行中的 Ubuntu 执行软件重启；systemd 为 running、failed units 为 0、根分区为 p14 且可读写，持久文件重启后仍存在。物理断电冷启动尚未验证。

## 产物

部署产物保存在本机 `build/emmc-deploy-20261111-01/`，不纳入 Git：

- `boot-02/boot.itb`：未补齐固定分区大小的 FIT，约 19 MB。
- `usb-payload-03/boot.img`：补齐至 40 MiB、实际写入 p7 的镜像。
- `ubuntu-rootfs.tar.gz`：Ubuntu 根文件系统归档；安装器在 p14 创建 ext4 后解包，并非直接写入的分区镜像。
- `usb-payload-03/`：部署包，含启动镜像、rootfs 归档、安装器、校验清单及原始 boot 分区备份。

GitHub Actions run `42811216799` 提供本次使用的内核、模块和 Ubuntu Base 基础归档，artifact 名称为 `tspi-linux-42811216799`，计划于 2026-11-24 过期。本机已保存校验过的副本；最终 FIT 和 eMMC rootfs 是在此基础上结合板级配置及额外软件包组装的。

## 尚未验证

- 实物 PCB 修订未确认；本次 DTB 已成功启动，但这不代表所有板级外设均已验证。
- 摄像头 UVC 采集、RKNN 推理、显示、USB 3 实际吞吐和长时间负载测试未完成。
- Wi-Fi 驱动和固件已加载，但缺少外置天线且未发现目标网络；认证、DHCP 和 DNS 未验证。蓝牙补丁及 UART DMA 路径也未验证。
- 尚未做物理断电冷启动或完整 Maskrom 恢复演练。
- 串口 root 自动登录是开发配置，不适合暴露在不可信网络或用作生产系统。

构建输入、流程和限制见 [BUILD.md](BUILD.md)。本机生成物、设备备份和测试证据不属于源码提交；重新部署前应检查对应 `SHA256SUMS` 和 manifest。
