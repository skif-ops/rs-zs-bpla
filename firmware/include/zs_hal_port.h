#ifndef ZS_HAL_PORT_H
#define ZS_HAL_PORT_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
typedef struct { void *ctx; uint32_t (*millis)(void *ctx); void (*delay_ms)(void *ctx, uint32_t ms); int (*uart_write)(void *ctx, unsigned channel, const uint8_t *data, size_t len); int (*spi_transfer)(void *ctx, unsigned bus, const uint8_t *tx, uint8_t *rx, size_t len); void (*gpio_write)(void *ctx, unsigned id, bool level); bool (*gpio_read)(void *ctx, unsigned id); } zs_hal_port_t;
#endif
