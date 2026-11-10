#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <termios.h>
#include <unistd.h>

static void mount_virtual_fs(const char *source, const char *target,
                             const char *type, unsigned long flags,
                             const char *data)
{
    if (mount(source, target, type, flags, data) < 0 && errno != EBUSY)
        dprintf(STDERR_FILENO, "init: mount %s on %s failed: %s\n",
                type, target, strerror(errno));
}

static void run_console_shell(void)
{
    pid_t child = fork();

    if (child < 0) {
        dprintf(STDERR_FILENO, "init: fork failed: %s\n", strerror(errno));
        sleep(1);
        return;
    }

    if (child == 0) {
        int console;

        setsid();
        console = open("/dev/console", O_RDWR);
        if (console >= 0) {
            ioctl(console, TIOCSCTTY, 0);
            dup2(console, STDIN_FILENO);
            dup2(console, STDOUT_FILENO);
            dup2(console, STDERR_FILENO);
            if (console > STDERR_FILENO)
                close(console);
        }

        execl("/bin/bash", "bash", "--login", "-i", (char *)NULL);
        execl("/bin/sh", "sh", "-i", (char *)NULL);
        dprintf(STDERR_FILENO, "init: no shell available: %s\n",
                strerror(errno));
        _exit(127);
    }

    for (;;) {
        pid_t reaped = waitpid(-1, NULL, 0);

        if (reaped == child || (reaped < 0 && errno == ECHILD))
            return;
        if (reaped < 0 && errno != EINTR) {
            dprintf(STDERR_FILENO, "init: waitpid failed: %s\n",
                    strerror(errno));
            sleep(1);
            return;
        }
    }
}

int main(void)
{
    int console = open("/dev/console", O_RDWR);

    if (console >= 0) {
        dup2(console, STDIN_FILENO);
        dup2(console, STDOUT_FILENO);
        dup2(console, STDERR_FILENO);
        if (console > STDERR_FILENO)
            close(console);
    }

    mount_virtual_fs("proc", "/proc", "proc", MS_NOSUID | MS_NOEXEC, NULL);
    mount_virtual_fs("sysfs", "/sys", "sysfs",
                     MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL);
    mount_virtual_fs("devtmpfs", "/dev", "devtmpfs", MS_NOSUID, "mode=0755");
    mount_virtual_fs("devpts", "/dev/pts", "devpts",
                     MS_NOSUID | MS_NOEXEC, "mode=0620,ptmxmode=0666");

    setenv("HOME", "/root", 1);
    setenv("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", 1);
    setenv("TERM", "vt100", 0);

    dprintf(STDOUT_FILENO,
            "Minimal Ubuntu Base rootfs: serial-only root shell for bring-up.\n");
    for (;;)
        run_console_shell();
}
