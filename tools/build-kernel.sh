#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../config/versions.env
source "$PROJECT_ROOT/config/versions.env"

ARCHIVE_DIR="$PROJECT_ROOT/sources/archives"
ARCHIVE="$ARCHIVE_DIR/linux-$KERNEL_VERSION.tar.xz"
SOURCE_DIR="${KERNEL_SOURCE_DIR:-$PROJECT_ROOT/sources/linux-$KERNEL_VERSION}"
BUILD_DIR="$PROJECT_ROOT/build/kernel-$KERNEL_VERSION"
ARTIFACT_DIR="$PROJECT_ROOT/build/artifacts/tspi-linux-$KERNEL_VERSION"
CROSS_COMPILE="${CROSS_COMPILE:-aarch64-linux-gnu-}"
JOBS="${JOBS:-$(nproc)}"

mkdir -p "$ARCHIVE_DIR" "$BUILD_DIR" "$ARTIFACT_DIR"
if [[ ! -f "$ARCHIVE" ]]; then
    curl --fail --location --retry 3 "$KERNEL_ARCHIVE_URL" --output "$ARCHIVE"
fi
printf '%s  %s\n' "$KERNEL_ARCHIVE_SHA256" "$ARCHIVE" | sha256sum --check

if [[ ! -f "$SOURCE_DIR/Makefile" ]]; then
    mkdir -p "$PROJECT_ROOT/sources"
    tar -xJf "$ARCHIVE" -C "$PROJECT_ROOT/sources"
    SOURCE_DIR="$PROJECT_ROOT/sources/linux-$KERNEL_VERSION"
fi
grep -q "^SUBLEVEL = ${KERNEL_VERSION##*.}$" "$SOURCE_DIR/Makefile"

make -C "$SOURCE_DIR" O="$BUILD_DIR/obj" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" defconfig
"$SOURCE_DIR/scripts/kconfig/merge_config.sh" -m -O "$BUILD_DIR/obj" \
    "$BUILD_DIR/obj/.config" "$PROJECT_ROOT/config/linux-arm64.fragment"
make -C "$SOURCE_DIR" O="$BUILD_DIR/obj" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" olddefconfig

make -C "$SOURCE_DIR" O="$BUILD_DIR/obj" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" \
    -j"$JOBS" Image modules "rockchip/$KERNEL_DTB"

KERNEL_RELEASE="$(make -s -C "$SOURCE_DIR" O="$BUILD_DIR/obj" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" kernelrelease)"
MODULES_ROOT="$BUILD_DIR/modules-root"
make -C "$SOURCE_DIR" O="$BUILD_DIR/obj" ARCH=arm64 CROSS_COMPILE="$CROSS_COMPILE" \
    INSTALL_MOD_PATH="$MODULES_ROOT" modules_install

rm -f "$MODULES_ROOT/lib/modules/$KERNEL_RELEASE/build" \
    "$MODULES_ROOT/lib/modules/$KERNEL_RELEASE/source"

install -m 0644 "$BUILD_DIR/obj/arch/arm64/boot/Image" "$ARTIFACT_DIR/Image"
install -m 0644 "$BUILD_DIR/obj/arch/arm64/boot/dts/rockchip/$KERNEL_DTB" "$ARTIFACT_DIR/$KERNEL_DTB"
install -m 0644 "$BUILD_DIR/obj/.config" "$ARTIFACT_DIR/kernel.config"
install -m 0644 "$BUILD_DIR/obj/System.map" "$ARTIFACT_DIR/System.map"
install -m 0644 "$BUILD_DIR/obj/Module.symvers" "$ARTIFACT_DIR/Module.symvers"
printf '%s\n' "$KERNEL_RELEASE" > "$ARTIFACT_DIR/kernelrelease"
rm -rf -- "$ARTIFACT_DIR/modules"
mkdir -p "$ARTIFACT_DIR/modules"
cp -a "$MODULES_ROOT/lib/modules/$KERNEL_RELEASE" "$ARTIFACT_DIR/modules/"
tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
    -C "$ARTIFACT_DIR/modules" -cf - . | gzip -n -9 > "$ARTIFACT_DIR/modules-$KERNEL_RELEASE.tar.gz"
jq -n \
    --arg version "$KERNEL_VERSION" \
    --arg release "$KERNEL_RELEASE" \
    --arg source_sha256 "$KERNEL_ARCHIVE_SHA256" \
    --arg compiler "$("${CROSS_COMPILE}gcc" --version | head -n 1)" \
    --arg dtb "$KERNEL_DTB" \
    '{kernel_version:$version, kernel_release:$release, source_archive_sha256:$source_sha256, cross_compiler:$compiler, dtb:$dtb, dtb_status:"upstream board-family candidate; hardware compatibility unverified"}' \
    > "$ARTIFACT_DIR/build-manifest.json"

(
    cd "$ARTIFACT_DIR"
    sha256sum Image "$KERNEL_DTB" kernel.config System.map Module.symvers kernelrelease \
        "modules-$KERNEL_RELEASE.tar.gz" build-manifest.json > SHA256SUMS
)
printf 'Built Linux %s for arm64; DTB is an upstream board-family candidate and is not hardware-validated.\n' "$KERNEL_VERSION"
printf 'Artifacts: %s\n' "$ARTIFACT_DIR"
