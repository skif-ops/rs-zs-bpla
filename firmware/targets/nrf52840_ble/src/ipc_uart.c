/* Interrupt-driven UART to the STM32U585: RX bytes go to a ring buffer, the main loop feeds the bridge. */
#include "bridge_app.h"

#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/ring_buffer.h>

LOG_MODULE_REGISTER(ipc_uart, LOG_LEVEL_INF);

static const struct device *const uart_dev = DEVICE_DT_GET(DT_CHOSEN(dioneya_ipc_uart));
RING_BUF_DECLARE(rx_ring, 2048);
static struct k_sem rx_sem;

static void uart_isr(const struct device *dev, void *user_data) {
  uint8_t buf[64];
  ARG_UNUSED(user_data);
  while (uart_irq_update(dev) && uart_irq_is_pending(dev)) {
    if (!uart_irq_rx_ready(dev)) break;
    const int n = uart_fifo_read(dev, buf, sizeof(buf));
    if (n <= 0) break;
    if (ring_buf_put(&rx_ring, buf, (uint32_t)n) != (uint32_t)n) LOG_WRN("rx ring overflow");
    k_sem_give(&rx_sem);
  }
}

int ipc_uart_init(void) {
  if (!device_is_ready(uart_dev)) { LOG_ERR("ipc uart not ready"); return -ENODEV; }
  k_sem_init(&rx_sem, 0, 1);
  uart_irq_callback_user_data_set(uart_dev, uart_isr, NULL);
  uart_irq_rx_enable(uart_dev);
  return 0;
}

bool ipc_uart_send(const uint8_t *wire, size_t len) {
  for (size_t i = 0u; i < len; i++) uart_poll_out(uart_dev, wire[i]);
  return true;
}

void ipc_uart_poll(void) {
  uint8_t buf[64];
  (void)k_sem_take(&rx_sem, K_MSEC(100));
  for (;;) {
    const uint32_t n = ring_buf_get(&rx_ring, buf, sizeof(buf));
    if (n == 0u) break;
    zs_ble_bridge_on_uart_rx(&bridge, buf, n);
  }
}
