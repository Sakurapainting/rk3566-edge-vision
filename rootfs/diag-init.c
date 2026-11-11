/* AArch64 RAM-only PID1 diagnostics. No libc, block writes or disk mounts. */
typedef unsigned long usize;
typedef unsigned long long u64;
typedef long s64;

static long sc(long nr, long a, long b, long c, long d, long e, long f)
{
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    register long x4 __asm__("x4") = e;
    register long x5 __asm__("x5") = f;
    register long x8 __asm__("x8") = nr;
    __asm__ volatile("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3),
                     "r"(x4), "r"(x5), "r"(x8) : "memory", "cc");
    return x0;
}

static usize length(const char *s)
{
    usize n = 0;
    while (s[n]) n++;
    return n;
}

static int prefix(const char *s, const char *p)
{
    while (*p) if (*s++ != *p++) return 0;
    return 1;
}

static void output(const void *p, usize n)
{
    const char *s = p;
    while (n) {
        long r = sc(64, 1, (long)s, n, 0, 0, 0);
        if (r == -4) continue;
        if (r <= 0) break;
        s += r;
        n -= (usize)r;
    }
}

static void put(const char *s) { output(s, length(s)); }

static void number(long n)
{
    char buf[32];
    usize i = sizeof(buf);
    unsigned long v;
    if (n < 0) { put("-"); v = (unsigned long)(-(n + 1)) + 1; }
    else v = (unsigned long)n;
    do { buf[--i] = '0' + v % 10; v /= 10; } while (v);
    output(buf + i, sizeof(buf) - i);
}

static long open_ro(const char *p)
{
    return sc(56, -100, (long)p, 0, 0, 0, 0);
}

static void close_fd(long fd) { if (fd >= 0) sc(57, fd, 0, 0, 0, 0, 0); }

static void join(char *out, const char *a, const char *b)
{
    usize n = 0;
    while (*a && n < 510) out[n++] = *a++;
    while (*b && n < 510) out[n++] = *b++;
    out[n] = 0;
}

static void pause_seconds(long seconds)
{
    struct { long sec, nsec; } req = {seconds, 0}, remain;
    while (sc(101, (long)&req, (long)&remain, 0, 0, 0, 0) == -4) req = remain;
}

static void dump(const char *path)
{
    char buf[4096];
    long fd = open_ro(path), n;
    usize total = 0;
    put("\nDIAG_FILE_BEGIN "); put(path); put("\n");
    if (fd < 0) { put("open_errno="); number(-fd); put("\n"); }
    else {
        while ((n = sc(63, fd, (long)buf, sizeof(buf), 0, 0, 0)) > 0) {
            output(buf, (usize)n);
            total += (usize)n;
            if (total >= 262144) { put("\nTRUNCATED\n"); break; }
        }
        if (n < 0) { put("\nread_errno="); number(-n); put("\n"); }
        close_fd(fd);
    }
    put("\nDIAG_FILE_END "); put(path); put("\n");
}

static void mount_virtual(const char *source, const char *target,
                          const char *type, long flags)
{
    long r = sc(40, (long)source, (long)target, (long)type, flags, 0, 0);
    put("DIAG_MOUNT "); put(target); put(" result="); number(r); put("\n");
}

struct dirent64 {
    u64 ino;
    s64 offset;
    unsigned short reclen;
    unsigned char type;
    char name[];
};

static void each_entry(const char *path, void (*visit)(const char *))
{
    char buf[4096] __attribute__((aligned(8)));
    long fd = open_ro(path), n;
    if (fd < 0) return;
    while ((n = sc(61, fd, (long)buf, sizeof(buf), 0, 0, 0)) > 0) {
        long pos = 0;
        while (pos < n) {
            struct dirent64 *ent = (void *)(buf + pos);
            if (ent->reclen < 20 || pos + ent->reclen > n) break;
            if (ent->name[0] != '.') visit(ent->name);
            pos += ent->reclen;
        }
    }
    close_fd(fd);
}

static void block_readonly(const char *name)
{
    char path[512];
    int one = 1;
    long fd, r;
    if (!prefix(name, "mmcblk") && !prefix(name, "sd")) return;
    join(path, "/dev/", name);
    fd = open_ro(path);
    r = fd < 0 ? fd : sc(29, fd, 0x125d, (long)&one, 0, 0, 0); /* BLKROSET */
    close_fd(fd);
    put("DIAG_BLOCK_RO "); put(name); put(" result="); number(r); put("\n");
}

static void block_info(const char *name)
{
    const char *fields[] = {"/uevent", "/size", "/ro", "/device/type",
                            "/device/name", "/device/cid"};
    char base[512], path[512];
    if (!prefix(name, "mmcblk") && !prefix(name, "sd")) return;
    join(base, "/sys/class/block/", name);
    for (usize i = 0; i < sizeof(fields)/sizeof(fields[0]); i++) {
        join(path, base, fields[i]);
        dump(path);
    }
}

static void usb_info(const char *name)
{
    const char *fields[] = {"/idVendor", "/idProduct", "/product", "/serial", "/speed"};
    char base[512], path[512];
    if (prefix(name, "usb") || prefix(name, "1-") || prefix(name, "2-") ||
        prefix(name, "3-") || prefix(name, "4-") || prefix(name, "5-") ||
        prefix(name, "6-") || prefix(name, "7-") || prefix(name, "8-")) {
        join(base, "/sys/bus/usb/devices/", name);
        for (usize i = 0; i < sizeof(fields)/sizeof(fields[0]); i++) {
            join(path, base, fields[i]); dump(path);
        }
    }
}

static void module_load(const char *path)
{
    long fd = open_ro(path);
    long r = fd < 0 ? fd : sc(273, fd, (long)"", 0, 0, 0, 0);
    close_fd(fd);
    put("DIAG_MODULE "); put(path); put(" result="); number(r); put("\n");
}

static void mmc_info(const char *name)
{
    const char *fields[] = {"/type", "/name", "/modalias", "/vendor", "/device", "/uevent"};
    char base[512], path[512];
    join(base, "/sys/bus/mmc/devices/", name);
    for (usize i = 0; i < sizeof(fields)/sizeof(fields[0]); i++) {
        join(path, base, fields[i]); dump(path);
    }
}

static void dump_dmesg(void)
{
    static char buf[131072];
    long n = sc(116, 3, (long)buf, sizeof(buf), 0, 0, 0); /* read-all syslog */
    put("\nDIAG_DMESG_BEGIN\n");
    if (n > 0) output(buf, (usize)n);
    else { put("syslog_result="); number(n); }
    put("\nDIAG_DMESG_END\n");
}

static void dump_fdt(void)
{
    unsigned char buf[64];
    char line[129];
    const char hex[] = "0123456789abcdef";
    long fd = open_ro("/sys/firmware/fdt"), n;
    usize total = 0;
    put("\nDIAG_FDT_BEGIN\n");
    if (fd >= 0) {
        while ((n = sc(63, fd, (long)buf, sizeof(buf), 0, 0, 0)) > 0) {
            for (long i = 0; i < n; i++) {
                line[2*i] = hex[buf[i] >> 4];
                line[2*i+1] = hex[buf[i] & 15];
            }
            line[2*n] = '\n'; output(line, (usize)(2*n+1));
            total += (usize)n;
            if (total >= 1048576) break;
        }
        close_fd(fd);
    }
    put("DIAG_FDT_END bytes="); number((long)total); put("\n");
}

void diag_main(void)
{
    long fd;
    mount_virtual("proc", "/proc", "proc", 2|8);
    mount_virtual("sysfs", "/sys", "sysfs", 2|4|8);
    mount_virtual("devtmpfs", "/dev", "devtmpfs", 2);
    sc(34, -100, (long)"/sys/kernel/debug", 0755, 0, 0, 0);
    mount_virtual("debugfs", "/sys/kernel/debug", "debugfs", 1|2|4|8);
    /* Reduce interleaved kernel chatter; printk is RAM-local to this boot. */
    fd = sc(56, -100, (long)"/proc/sys/kernel/printk", 1, 0, 0, 0);
    if (fd >= 0) { sc(64, fd, (long)"1\n", 2, 0, 0, 0); close_fd(fd); }
    put("\nG4_DIAG_READY_20261111\n");
    pause_seconds(4);
    each_entry("/sys/class/block", block_readonly);
    put("\nDIAG_STAGE BEFORE_MODULES\n");
    dump("/proc/version"); dump("/proc/cmdline"); dump("/proc/cpuinfo");
    dump("/proc/meminfo"); dump("/proc/partitions"); dump("/proc/mounts");
    dump("/sys/devices/system/cpu/online");
    dump("/proc/modules"); dump("/sys/kernel/debug/devices_deferred");
    module_load("/modules/reset-gpio.ko");
    module_load("/modules/phy-rockchip-naneng-combphy.ko");
    pause_seconds(12);
    each_entry("/sys/class/block", block_readonly);
    put("\nDIAG_STAGE AFTER_MODULES\n");
    dump("/proc/modules"); dump("/sys/kernel/debug/devices_deferred");
    dump("/proc/partitions"); dump("/proc/mounts");
    each_entry("/sys/class/block", block_info);
    each_entry("/sys/bus/usb/devices", usb_info);
    each_entry("/sys/bus/mmc/devices", mmc_info);
    dump("/sys/kernel/debug/gpio");
    dump("/sys/kernel/debug/regulator/regulator_summary");
    dump("/sys/kernel/debug/clk/clk_summary");
    dump("/sys/kernel/debug/pm_genpd/pm_genpd_summary");
    dump_dmesg();
    dump_fdt();
    put("\nG4_DIAG_DONE_20261111\n");
    pause_seconds(2);
    put("\nG4_DIAG_RESTART_20261111\n");
    sc(142, 0xfee1dead, 0x28121969, 0x01234567, 0, 0, 0);
    for (;;) pause_seconds(30);
}

__asm__(".global _start\n_start:\nbl diag_main\n1: b 1b\n");
