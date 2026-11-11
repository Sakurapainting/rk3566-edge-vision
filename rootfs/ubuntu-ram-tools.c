/* AArch64 syscall-only helpers for the temporary Ubuntu RAM rootfs. */
typedef unsigned long usize;

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

static void put(const char *s)
{
    usize n = 0;
    while (s[n]) n++;
    while (n) {
        long r = sc(64, 1, (long)s, n, 0, 0, 0);
        if (r == -4) continue;
        if (r <= 0) break;
        s += r;
        n -= (usize)r;
    }
}

static void number(long n)
{
    char buf[32];
    usize i = sizeof(buf) - 1;
    unsigned long v;
    buf[i] = 0;
    if (n < 0) { put("-"); v = (unsigned long)(-(n + 1)) + 1; }
    else v = (unsigned long)n;
    do { buf[--i] = '0' + v % 10; v /= 10; } while (v);
    put(buf + i);
}

static int equal(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static long restart_delay(const char *s)
{
    long seconds = 0;
    if (!*s) return -1;
    while (*s) {
        if (*s < '0' || *s > '9') return -1;
        seconds = seconds * 10 + *s++ - '0';
        if (seconds > 3600) return -1;
    }
    return seconds >= 1 ? seconds : -1;
}

static void pause_seconds(long seconds)
{
    struct { long sec, nsec; } req = {seconds, 0}, remain;
    while (sc(101, (long)&req, (long)&remain, 0, 0, 0, 0) == -4) req = remain;
}

void ram_tools_main(long *stack)
{
    long argc = stack[0], result = -22;
    char **argv = (char **)(stack + 1);
    if (argc == 3 && equal(argv[1], "insmod")) {
        long fd = sc(56, -100, (long)argv[2], 0, 0, 0, 0);
        result = fd < 0 ? fd : sc(273, fd, (long)"", 0, 0, 0, 0);
        if (fd >= 0) sc(57, fd, 0, 0, 0, 0, 0);
        put("UBUNTU_RAM_MODULE "); put(argv[2]); put(" result=");
        number(result); put("\n");
    } else if (argc == 3 && equal(argv[1], "return") &&
               (equal(argv[2], "now") || restart_delay(argv[2]) > 0)) {
        if (!equal(argv[2], "now")) pause_seconds(restart_delay(argv[2]));
        put("\nG5_UBUNTU_RESTART_20261111\n");
        result = sc(142, 0xfee1dead, 0x28121969, 0x01234567, 0, 0, 0);
        put("UBUNTU_RAM_REBOOT_FAILED result="); number(result); put("\n");
    }
    sc(93, result < 0 ? 1 : 0, 0, 0, 0, 0, 0);
    for (;;) pause_seconds(30);
}

__asm__(".global _start\n_start:\nmov x0, sp\nbl ram_tools_main\n1: b 1b\n");
