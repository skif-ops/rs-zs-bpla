#include "bsp_rng.h"
#include "stm32u5xx_hal.h"

static RNG_HandleTypeDef hrng;
static bool ready;

bool bsp_rng_init(void) {
  __HAL_RCC_RNG_CLK_ENABLE();
  hrng.Instance = RNG;
  hrng.Init.ClockErrorDetection = RNG_CED_ENABLE;
  ready = HAL_RNG_Init(&hrng) == HAL_OK;
  return ready;
}

bool bsp_rng_fill(uint8_t *out, size_t len) {
  if (!ready || !out) return false;
  for (size_t i = 0u; i < len; i += 4u) {
    uint32_t v;
    if (HAL_RNG_GenerateRandomNumber(&hrng, &v) != HAL_OK) return false;
    for (size_t k = 0u; k < 4u && i + k < len; k++) out[i + k] = (uint8_t)(v >> (8u * k));
  }
  return true;
}
