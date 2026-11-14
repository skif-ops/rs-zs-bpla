#ifndef BSP_UART_H
#define BSP_UART_H
/* Interrupt-driven UARTs with lock-free RX rings (single producer ISR / single consumer task).
   USART1 = BG95 (PB6/PB7 AF7), USART2 = GNSS (PA2/PA3 AF7), LPUART1 = console (PC1/PC0 AF8),
   USART3 = nRF52840 BLE bridge (PB10/PB11 AF7). */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef enum { BSP_UART_CELL = 0, BSP_UART_GNSS, BSP_UART_CONSOLE, BSP_UART_BLE, BSP_UART_COUNT } bsp_uart_id_t;
bool bsp_uart_init(bsp_uart_id_t id, uint32_t baud);
int bsp_uart_write(bsp_uart_id_t id, const uint8_t *data, size_t len);   /* blocking, returns len or -1 */
size_t bsp_uart_read(bsp_uart_id_t id, uint8_t *out, size_t cap);         /* non-blocking drain of the RX ring */
uint32_t bsp_uart_rx_overruns(bsp_uart_id_t id);
/* Called from the RX ISR after a byte is queued so a task can wake; provided by tasks.c. */
void app_uart_rx_notify_from_isr(bsp_uart_id_t id);
#endif
