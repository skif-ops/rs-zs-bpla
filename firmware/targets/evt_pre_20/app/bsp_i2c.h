#ifndef BSP_I2C_H
#define BSP_I2C_H
/* I2C2 (PB13 SCL / PB14 SDA, AF4): power and sensor bus of Rev.A - INA226 battery monitor (0x40).
   100 kHz standard mode from the HSI16 kernel clock; blocking register access with a timeout, serialised by
   the calling task (one owner: the power task). */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

bool bsp_i2c_init(void);
/* Register read/write in the zs_hal_port i2c_mem_* shape: 0 on success, -1 on NACK/bus error/timeout. */
int bsp_i2c_mem_read(uint8_t address7, uint8_t reg, uint8_t *data, size_t len);
int bsp_i2c_mem_write(uint8_t address7, uint8_t reg, const uint8_t *data, size_t len);
/* Recovery after a stuck bus: re-initialises the peripheral. */
bool bsp_i2c_reset(void);
uint32_t bsp_i2c_errors(void);
#endif
