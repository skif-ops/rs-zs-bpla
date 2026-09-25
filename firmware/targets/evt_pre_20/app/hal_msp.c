#include "stm32u5xx_hal.h"

void HAL_MspInit(void) {
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_RCC_SYSCFG_CLK_ENABLE();
  HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4);
}

/* I2C2 (INA226 power monitor): PB13 SCL / PB14 SDA AF4 open-drain, kernel clock HSI16 (timing in bsp_i2c.c). */
void HAL_I2C_MspInit(I2C_HandleTypeDef *hi2c) {
  GPIO_InitTypeDef g = {0};
  RCC_PeriphCLKInitTypeDef pclk = {0};
  if (hi2c->Instance != I2C2) return;
  pclk.PeriphClockSelection = RCC_PERIPHCLK_I2C2;
  pclk.I2c2ClockSelection = RCC_I2C2CLKSOURCE_HSI;
  (void)HAL_RCCEx_PeriphCLKConfig(&pclk);
  __HAL_RCC_GPIOB_CLK_ENABLE();
  g.Pin = GPIO_PIN_13 | GPIO_PIN_14;
  g.Mode = GPIO_MODE_AF_OD;
  g.Pull = GPIO_NOPULL;                            /* external pull-ups on the power bus */
  g.Speed = GPIO_SPEED_FREQ_LOW;
  g.Alternate = GPIO_AF4_I2C2;
  HAL_GPIO_Init(GPIOB, &g);
  __HAL_RCC_I2C2_CLK_ENABLE();
}

void HAL_SPI_MspInit(SPI_HandleTypeDef *hspi) {
  GPIO_InitTypeDef g = {0};
  if (hspi->Instance != SPI1) return;
  __HAL_RCC_GPIOA_CLK_ENABLE();
  g.Pin = GPIO_PIN_5 | GPIO_PIN_6 | GPIO_PIN_7;             /* SCK, MISO, MOSI; NSS (PA4) is a GPIO */
  g.Mode = GPIO_MODE_AF_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_HIGH;
  g.Alternate = GPIO_AF5_SPI1;
  HAL_GPIO_Init(GPIOA, &g);
  __HAL_RCC_SPI1_CLK_ENABLE();
}

void HAL_SPI_MspDeInit(SPI_HandleTypeDef *hspi) {
  if (hspi->Instance != SPI1) return;
  __HAL_RCC_SPI1_CLK_DISABLE();
  HAL_GPIO_DeInit(GPIOA, GPIO_PIN_5 | GPIO_PIN_6 | GPIO_PIN_7);
}

void HAL_I2C_MspDeInit(I2C_HandleTypeDef *hi2c) {
  if (hi2c->Instance != I2C2) return;
  __HAL_RCC_I2C2_CLK_DISABLE();
  HAL_GPIO_DeInit(GPIOB, GPIO_PIN_13 | GPIO_PIN_14);
}

void HAL_MDF_MspInit(MDF_HandleTypeDef *hmdf) {
  GPIO_InitTypeDef g = {0};
  (void)hmdf;
  __HAL_RCC_MDF1_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  g.Mode = GPIO_MODE_AF_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_HIGH;
  g.Alternate = GPIO_AF6_MDF1;
  g.Pin = GPIO_PIN_9 | GPIO_PIN_7 | GPIO_PIN_4;   /* PE9 CCK0, PE7 SDI2, PE4 SDI3 */
  HAL_GPIO_Init(GPIOE, &g);
  g.Pin = GPIO_PIN_1;                             /* PB1 SDI0 */
  HAL_GPIO_Init(GPIOB, &g);
  g.Pin = GPIO_PIN_6;                             /* PD6 SDI1 */
  HAL_GPIO_Init(GPIOD, &g);
  HAL_NVIC_SetPriority(MDF1_FLT0_IRQn, 7, 0); HAL_NVIC_EnableIRQ(MDF1_FLT0_IRQn);
  HAL_NVIC_SetPriority(MDF1_FLT1_IRQn, 7, 0); HAL_NVIC_EnableIRQ(MDF1_FLT1_IRQn);
  HAL_NVIC_SetPriority(MDF1_FLT2_IRQn, 7, 0); HAL_NVIC_EnableIRQ(MDF1_FLT2_IRQn);
  HAL_NVIC_SetPriority(MDF1_FLT3_IRQn, 7, 0); HAL_NVIC_EnableIRQ(MDF1_FLT3_IRQn);
}
