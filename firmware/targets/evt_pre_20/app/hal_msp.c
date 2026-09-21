#include "stm32u5xx_hal.h"

void HAL_MspInit(void) {
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_RCC_SYSCFG_CLK_ENABLE();
  HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4);
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
