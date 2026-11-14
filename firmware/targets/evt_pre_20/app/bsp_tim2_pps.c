#include "bsp_tim2_pps.h"

#include "app_config.h"
#include "stm32u5xx_hal.h"

static TIM_HandleTypeDef htim2;
static zs_pps_sync_t *g_pps;
static uint32_t g_edges;

bool bsp_tim2_pps_init(zs_pps_sync_t *pps) {
  TIM_IC_InitTypeDef ic = {0};
  uint32_t timclk;
  g_pps = pps;
  __HAL_RCC_TIM2_CLK_ENABLE();
  /* TIM2 kernel clock = PCLK1 (x2 when APB1 prescaler != 1); Rev.A runs APB1 at HCLK so it is 160 MHz. */
  timclk = HAL_RCC_GetPCLK1Freq();
  if ((RCC->CFGR2 & RCC_CFGR2_PPRE1) != 0u) timclk *= 2u;
  htim2.Instance = TIM2;
  htim2.Init.Prescaler = (timclk / APP_TIM2_CLOCK_HZ) - 1u;   /* 16 MHz -> 62.5 ns resolution */
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 0xFFFFFFFFu;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_IC_Init(&htim2) != HAL_OK) return false;
  ic.ICPolarity = TIM_INPUTCHANNELPOLARITY_RISING;
  ic.ICSelection = TIM_ICSELECTION_DIRECTTI;
  ic.ICPrescaler = TIM_ICPSC_DIV1;
  ic.ICFilter = 3;                                              /* ~4 clock glitch filter */
  if (HAL_TIM_IC_ConfigChannel(&htim2, &ic, TIM_CHANNEL_1) != HAL_OK) return false;
  HAL_NVIC_SetPriority(TIM2_IRQn, APP_IRQ_PRIO_TIM2_PPS, 0);
  HAL_NVIC_EnableIRQ(TIM2_IRQn);
  return HAL_TIM_IC_Start_IT(&htim2, TIM_CHANNEL_1) == HAL_OK;
}

uint32_t bsp_tim2_pps_now(void) { return __HAL_TIM_GET_COUNTER(&htim2); }
uint32_t bsp_tim2_pps_edges(void) { return g_edges; }

void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim) {
  if (htim->Instance == TIM2 && htim->Channel == HAL_TIM_ACTIVE_CHANNEL_1) {
    uint32_t ticks = HAL_TIM_ReadCapturedValue(htim, TIM_CHANNEL_1);
    g_edges++;
    if (g_pps) zs_pps_sync_on_pps(g_pps, ticks);   /* no RTOS calls: this ISR runs above the syscall ceiling */
  }
}

void TIM2_IRQHandler(void) { HAL_TIM_IRQHandler(&htim2); }

/* HAL timebase (TIM6) MSP hooks are in the HAL template; TIM2 MSP is here. */
void HAL_TIM_IC_MspInit(TIM_HandleTypeDef *htim) {
  if (htim->Instance == TIM2) {
    GPIO_InitTypeDef g = {0};
    __HAL_RCC_GPIOA_CLK_ENABLE();
    g.Pin = GPIO_PIN_0;                 /* GNSS_PPS, TIM2_CH1, AF1 */
    g.Mode = GPIO_MODE_AF_PP;
    g.Pull = GPIO_PULLDOWN;
    g.Speed = GPIO_SPEED_FREQ_LOW;
    g.Alternate = GPIO_AF1_TIM2;
    HAL_GPIO_Init(GPIOA, &g);
  }
}
