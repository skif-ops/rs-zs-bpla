#include "bsp_clock.h"

#include "app_config.h"
#include "evt_pre_20_clock_policy.h"
#include "stm32u5xx_hal.h"

_Static_assert(EVT_PRE_20_EXTERNAL_HSE_ALLOWED == 0, "clock policy forbids HSE");

bool bsp_clock_init_160mhz(void) {
  RCC_OscInitTypeDef osc = {0};
  RCC_ClkInitTypeDef clk = {0};
  RCC_PeriphCLKInitTypeDef pclk = {0};

  /* Vcore range 1 for 160 MHz, SMPS supply as on Rev.A. */
  if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK) return false;
  HAL_PWREx_ConfigSupply(PWR_SMPS_SUPPLY);

  /* LSE: SiT1552 drives OSC32_IN -> bypass mode; MSIS 4 MHz with PLL-mode locked to LSE; HSI16 on for peripherals. */
  osc.OscillatorType = RCC_OSCILLATORTYPE_MSI | RCC_OSCILLATORTYPE_LSE | RCC_OSCILLATORTYPE_HSI;
  osc.LSEState = RCC_LSE_BYPASS;
  osc.MSIState = RCC_MSI_ON;
  osc.MSICalibrationValue = RCC_MSICALIBRATION_DEFAULT;
  osc.MSIClockRange = RCC_MSIRANGE_4;            /* MSIS 4 MHz */
  osc.HSIState = RCC_HSI_ON;
  osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  osc.PLL.PLLState = RCC_PLL_ON;
  osc.PLL.PLLSource = RCC_PLLSOURCE_MSI;
  osc.PLL.PLLMBOOST = RCC_PLLMBOOST_DIV1;
  osc.PLL.PLLM = 1;                              /* 4 MHz reference */
  osc.PLL.PLLN = 80;                             /* VCO 320 MHz */
  osc.PLL.PLLP = 100;                            /* PLL1P = 3.2 MHz -> MDF1 kernel / PDM clock */
  osc.PLL.PLLQ = 2;
  osc.PLL.PLLR = 2;                              /* SYSCLK 160 MHz */
  osc.PLL.PLLRGE = RCC_PLLVCIRANGE_0;            /* 4..8 MHz input */
  osc.PLL.PLLFRACN = 0;
  if (HAL_RCC_OscConfig(&osc) != HAL_OK) return false;
  /* MSI PLL-mode: lock MSIS to LSE so the audio clock inherits the SiT1552 accuracy. */
  HAL_RCCEx_EnableMSIPLLMode();

  clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2 | RCC_CLOCKTYPE_PCLK3;
  clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clk.APB1CLKDivider = RCC_HCLK_DIV1;
  clk.APB2CLKDivider = RCC_HCLK_DIV1;
  clk.APB3CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_4) != HAL_OK) return false;

  /* Kernel clocks: MDF1 from PLL1P (3.2 MHz), UARTs and TIM from HSI16-independent APB (default PCLK). */
  pclk.PeriphClockSelection = RCC_PERIPHCLK_MDF1 | RCC_PERIPHCLK_USART1 | RCC_PERIPHCLK_USART2 |
                              RCC_PERIPHCLK_USART3 | RCC_PERIPHCLK_LPUART1;
  pclk.Mdf1ClockSelection = RCC_MDF1CLKSOURCE_PLL1;
  pclk.Usart1ClockSelection = RCC_USART1CLKSOURCE_HSI;
  pclk.Usart2ClockSelection = RCC_USART2CLKSOURCE_HSI;
  pclk.Usart3ClockSelection = RCC_USART3CLKSOURCE_HSI;
  pclk.Lpuart1ClockSelection = RCC_LPUART1CLKSOURCE_HSI;
  if (HAL_RCCEx_PeriphCLKConfig(&pclk) != HAL_OK) return false;
  return true;
}

uint32_t bsp_clock_mdf_kernel_hz(void) { return APP_MDF_PDM_CLOCK_HZ; }
