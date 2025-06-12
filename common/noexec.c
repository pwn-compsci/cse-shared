#include <errno.h>
#include <stdio.h>
#include <unistd.h>

int execve(const char *pathname, char *const argv[], char *const envp[]) {
    fprintf(stderr, "Blocked attempt to execute: %s\n", pathname);
    errno = EACCES; // Permission Denied
    return -1; // Fail the execve call
}
