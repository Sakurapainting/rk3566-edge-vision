#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../config/versions.env
source "$PROJECT_ROOT/config/versions.env"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run as root (or inside a user namespace) to preserve ARM64 rootfs ownership." >&2
    exit 1
fi

ARCHIVE_DIR="$PROJECT_ROOT/sources/archives"
ARCHIVE="$ARCHIVE_DIR/ubuntu-base-$ROOTFS_VERSION-base-arm64.tar.gz"
STAGE_ROOT="$PROJECT_ROOT/build/rootfs"
STAGE="$STAGE_ROOT/ubuntu-base-$ROOTFS_VERSION-arm64-stage"
ARTIFACT_DIR="$PROJECT_ROOT/build/artifacts/tspi-linux-$KERNEL_VERSION"
OUTPUT="$ARTIFACT_DIR/ubuntu-base-$ROOTFS_VERSION-tspi-arm64.tar.gz"
MARKER="$STAGE_ROOT/.ubuntu-base-$ROOTFS_VERSION-arm64-stage.codex-owned"

mkdir -p "$ARCHIVE_DIR" "$STAGE_ROOT" "$ARTIFACT_DIR"
if [[ ! -f "$ARCHIVE" ]]; then
    curl --fail --location --retry 3 "$ROOTFS_ARCHIVE_URL" --output "$ARCHIVE"
fi
printf '%s  %s\n' "$ROOTFS_ARCHIVE_SHA256" "$ARCHIVE" | sha256sum --check

if [[ -e "$STAGE" ]]; then
    if [[ ! -f "$MARKER" ]]; then
        echo "Refusing to replace unmarked rootfs directory: $STAGE" >&2
        exit 1
    fi
    rm -rf -- "$STAGE"
fi
touch "$MARKER"
mkdir -p "$STAGE"
tar --numeric-owner --xattrs --acls -xzf "$ARCHIVE" -C "$STAGE"

printf 'tspi\n' > "$STAGE/etc/hostname"
cat > "$STAGE/etc/hosts" <<'EOF'
127.0.0.1 localhost
127.0.1.1 tspi
::1 localhost ip6-localhost ip6-loopback
EOF

KERNEL_RELEASE_FILE="$ARTIFACT_DIR/kernelrelease"
if [[ ! -f "$KERNEL_RELEASE_FILE" ]]; then
    echo "Missing matching kernel release file: $KERNEL_RELEASE_FILE" >&2
    exit 1
fi
KERNEL_RELEASE="$(<"$KERNEL_RELEASE_FILE")"
if [[ ! -d "$ARTIFACT_DIR/modules/$KERNEL_RELEASE" ]]; then
    echo "Missing matching kernel modules: $ARTIFACT_DIR/modules/$KERNEL_RELEASE" >&2
    exit 1
fi
mkdir -p "$STAGE/lib/modules"
cp -a "$ARTIFACT_DIR/modules/$KERNEL_RELEASE" "$STAGE/lib/modules/"
rm -f "$STAGE/lib/modules/$KERNEL_RELEASE/build" \
    "$STAGE/lib/modules/$KERNEL_RELEASE/source"

TOOL_PREFIX="${CROSS_COMPILE:-aarch64-linux-gnu-}"
"${TOOL_PREFIX}gcc" -static -Os -Wall -Wextra -Werror \
    "$PROJECT_ROOT/rootfs/init.c" -o "$STAGE/sbin/init"
chmod 0755 "$STAGE/sbin/init"

tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
    --xattrs --acls --pax-option=delete=atime,delete=ctime \
    -C "$STAGE" -cf - . | gzip -n -9 > "$OUTPUT"
(
    cd "$ARTIFACT_DIR"
    awk -v file="$(basename "$OUTPUT")" '$2 != file { print }' SHA256SUMS > SHA256SUMS.tmp
    mv SHA256SUMS.tmp SHA256SUMS
    sha256sum "$(basename "$OUTPUT")" >> SHA256SUMS
    jq -n \
        --arg distribution "Ubuntu Base" \
        --arg release "$ROOTFS_VERSION" \
        --arg architecture "arm64" \
        --arg source_sha256 "$ROOTFS_ARCHIVE_SHA256" \
        --arg pid1_sha256 "$(sha256sum "$STAGE/sbin/init" | cut -d ' ' -f 1)" \
        --arg kernel_release "$(cat "$KERNEL_RELEASE_FILE" 2>/dev/null || true)" \
        '{distribution:$distribution, release:$release, architecture:$architecture, base_archive_sha256:$source_sha256, pid1:"static serial root shell for bring-up", pid1_sha256:$pid1_sha256, matching_kernel_release:$kernel_release, artifact_type:"rootfs tar archive, not a partition image", hardware_boot_validated:false}' \
        > rootfs-build-manifest.json
    sha256sum rootfs-build-manifest.json >> SHA256SUMS
)
printf 'Assembled Ubuntu Base %s ARM64 bring-up rootfs with a static PID 1 console shell.\n' "$ROOTFS_VERSION"
printf 'This is a rootfs archive, not a partition image; board login and boot remain unvalidated.\n'
printf 'Artifact: %s\n' "$OUTPUT"
