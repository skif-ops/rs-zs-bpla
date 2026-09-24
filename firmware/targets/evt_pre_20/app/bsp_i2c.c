#include "bsp_i2c.h"

#include "stm32u5xx_hal.h"

/* CubeMX timing for HSI16 kernel clock, 100 kHz standard mode, analog filter on, 0 digital filter. */
#define I2C2_TIMING_HSI16_100K 0x00303D5Bu
#define I2C_TIMEOUT_MS 20u

static I2C_HandleTypeDef hi2c2;
static bool ready;
static uint32_t errors;

bool bsp_i2c_init(void) {
  hi2c2.Instance = I2C2;
  hi2c2.Init.Timing = I2C2_TIMING_HSI16_100K;
  hi2c2.Init.OwnAddress1 = 0u;
  hi2c2.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c2.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c2.Init.OwnAddress2 = 0u;
  hi2c2.Init.OwnAddress2Masks = I2C_OA2_NOMASK;
  hi2c2.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c2.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c2) != HAL_OK) { ready = false; return false; }
  if (HAL_I2CEx_ConfigAnalogFilter(&hi2c2, I2C_ANALOGFILTER_ENABLE) != HAL_OK) { ready = false; return false; }
  ready = true;
  return true;
}

bool bsp_i2c_reset(void) {
  if (ready) (void)HAL_I2C_DeInit(&hi2c2);
  ready = false;
  return bsp_i2c_init();
}

uint32_t bsp_i2c_errors(void) { return errors; }

int bsp_i2c_mem_read(uint8_t address7, uint8_t reg, uint8_t *data, size_t len) {
  if (!ready || !data || len == 0u || len > 0xffffu) return -1;
  if (HAL_I2C_Mem_Read(&hi2c2, (uint16_t)(address7 << 1), reg, I2C_MEMADD_SIZE_8BIT, data, (uint16_t)len, I2C_TIMEOUT_MS) != HAL_OK) { errors++; return -1; }
  return 0;
}

int bsp_i2c_mem_write(uint8_t address7, uint8_t reg, const uint8_t *data, size_t len) {
  if (!ready || !data || len == 0u || len > 0xffffu) return -1;
  if (HAL_I2C_Mem_Write(&hi2c2, (uint16_t)(address7 << 1), reg, I2C_MEMADD_SIZE_8BIT, (uint8_t *)data, (uint16_t)len, I2C_TIMEOUT_MS) != HAL_OK) { errors++; return -1; }
  return 0;
}
