#ifndef BSP_SPI_H
#define BSP_SPI_H
/* SPI1 to the SX1262 (PA4 NSS as GPIO, PA5 SCK, PA6 MISO, PA7 MOSI, AF5) and the LoRa control pins: DIO1 PC2 (in),
   TXEN PB15 / RXEN PD8 (out), BUSY PD9 (in), RESET_N PD10 (out).  Mode 0, MSB first, 8 MHz from the 160 MHz bus
   (the SX1262 allows up to 16 MHz). */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum { BSP_LORA_PIN_NSS = 1, BSP_LORA_PIN_BUSY, BSP_LORA_PIN_RESET, BSP_LORA_PIN_DIO1, BSP_LORA_PIN_TXEN, BSP_LORA_PIN_RXEN } bsp_lora_pin_t;

bool bsp_spi_init(void);
/* Full-duplex transfer of `len` bytes (tx may equal rx); false on a HAL error/timeout. */
bool bsp_spi_transfer(const uint8_t *tx, uint8_t *rx, size_t len);
void bsp_lora_pin_write(bsp_lora_pin_t pin, bool level);
bool bsp_lora_pin_read(bsp_lora_pin_t pin);
uint32_t bsp_spi_errors(void);
#endif
