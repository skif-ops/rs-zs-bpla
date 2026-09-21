/* Minimal newlib glue: printf goes to the LPUART1 console, heap for newlib is the region after .bss. */
#include <errno.h>
#include <stddef.h>
#include <sys/stat.h>

#include "bsp_uart.h"

extern char _end;      /* from the linker script */
extern char _sstack;

int _write(int fd, const char *buf, int len) {
  (void)fd;
  return bsp_uart_write(BSP_UART_CONSOLE, (const uint8_t *)buf, (size_t)len);
}
int _read(int fd, char *buf, int len) { (void)fd; (void)buf; (void)len; return 0; }
int _close(int fd) { (void)fd; return -1; }
int _fstat(int fd, struct stat *st) { (void)fd; st->st_mode = S_IFCHR; return 0; }
int _isatty(int fd) { (void)fd; return 1; }
int _lseek(int fd, int off, int whence) { (void)fd; (void)off; (void)whence; return 0; }
void *_sbrk(int incr) {
  static char *heap_end;
  char *prev;
  if (!heap_end) heap_end = &_end;
  if (heap_end + incr > &_sstack) { errno = ENOMEM; return (void *)-1; }
  prev = heap_end;
  heap_end += incr;
  return prev;
}
