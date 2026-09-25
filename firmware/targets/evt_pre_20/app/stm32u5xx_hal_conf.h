/*
 * HAL configuration for Dioneya EVT-PRE-20 (STM32U585VIT6Q, Rev.A).
 * Compact equivalent of STM32CubeU5 v1.9.0 stm32u5xx_hal_conf_template.h with only the modules
 * the B1 application uses. No HSE (clock policy REV_A_INTERNAL_HSI_MSI_PLL_NO_HSE); LSE is the
 * SiT1552 MEMS oscillator in bypass mode.
 */
#ifndef STM32U5xx_HAL_CONF_H
#define STM32U5xx_HAL_CONF_H

#ifdef __cplusplus
extern "C" {
#endif

/* ---- module selection ---- */
#define HAL_MODULE_ENABLED
#define HAL_CORTEX_MODULE_ENABLED
#define HAL_DMA_MODULE_ENABLED
#define HAL_EXTI_MODULE_ENABLED
#define HAL_FLASH_MODULE_ENABLED
#define HAL_GPIO_MODULE_ENABLED
#define HAL_I2C_MODULE_ENABLED
#define HAL_ICACHE_MODULE_ENABLED
#define HAL_MDF_MODULE_ENABLED
#define HAL_OSPI_MODULE_ENABLED
#define HAL_SPI_MODULE_ENABLED
#define HAL_PWR_MODULE_ENABLED
#define HAL_RCC_MODULE_ENABLED
#define HAL_RNG_MODULE_ENABLED
#define HAL_TIM_MODULE_ENABLED
#define HAL_UART_MODULE_ENABLED

/* ---- oscillator values ---- */
#if !defined (HSE_VALUE)
#define HSE_VALUE               16000000UL   /* no HSE on Rev.A; value unused */
#endif
#if !defined (HSE_STARTUP_TIMEOUT)
#define HSE_STARTUP_TIMEOUT     100UL
#endif
#if !defined (MSI_VALUE)
#define MSI_VALUE               4000000UL
#endif
#if !defined (HSI_VALUE)
#define HSI_VALUE               16000000UL
#endif
#if !defined (HSI48_VALUE)
#define HSI48_VALUE             48000000UL
#endif
#if !defined (LSI_VALUE)
#define LSI_VALUE               32000UL
#endif
#if !defined (LSI_STARTUP_TIMEOUT)
#define LSI_STARTUP_TIMEOUT     130UL
#endif
#if !defined (LSE_VALUE)
#define LSE_VALUE               32768UL      /* SiT1552AI-JE-DCC-32.768D, bypass */
#endif
#if !defined (LSE_STARTUP_TIMEOUT)
#define LSE_STARTUP_TIMEOUT     5000UL
#endif
#if !defined (EXTERNAL_SAI1_CLOCK_VALUE)
#define EXTERNAL_SAI1_CLOCK_VALUE 48000UL
#endif

/* ---- system ---- */
#define VDD_VALUE               3300UL
#define TICK_INT_PRIORITY       15U          /* HAL timebase on TIM6: lowest priority, below the FreeRTOS syscall level */
#define USE_RTOS                0U
#define PREFETCH_ENABLE         1U

/* ---- register callbacks: none ---- */
#define USE_HAL_DMA_REGISTER_CALLBACKS   0U
#define USE_HAL_MDF_REGISTER_CALLBACKS   0U
#define USE_HAL_TIM_REGISTER_CALLBACKS   0U
#define USE_HAL_UART_REGISTER_CALLBACKS  0U
#define USE_HAL_OSPI_REGISTER_CALLBACKS  0U
#define USE_HAL_RNG_REGISTER_CALLBACKS   0U

/* ---- driver headers (order as in the template) ---- */
#ifdef HAL_RCC_MODULE_ENABLED
#include "stm32u5xx_hal_rcc.h"
#endif
#ifdef HAL_GPIO_MODULE_ENABLED
#include "stm32u5xx_hal_gpio.h"
#endif
#ifdef HAL_ICACHE_MODULE_ENABLED
#include "stm32u5xx_hal_icache.h"
#endif
#ifdef HAL_DMA_MODULE_ENABLED
#include "stm32u5xx_hal_dma.h"
#endif

#ifdef HAL_I2C_MODULE_ENABLED
#include "stm32u5xx_hal_i2c.h"
#endif
#ifdef HAL_SPI_MODULE_ENABLED
#include "stm32u5xx_hal_spi.h"
#endif
#ifdef HAL_CORTEX_MODULE_ENABLED
#include "stm32u5xx_hal_cortex.h"
#endif
#ifdef HAL_FLASH_MODULE_ENABLED
#include "stm32u5xx_hal_flash.h"
#endif
#ifdef HAL_EXTI_MODULE_ENABLED
#include "stm32u5xx_hal_exti.h"
#endif
#ifdef HAL_MDF_MODULE_ENABLED
#include "stm32u5xx_hal_mdf.h"
#endif
#ifdef HAL_PWR_MODULE_ENABLED
#include "stm32u5xx_hal_pwr.h"
#endif
#ifdef HAL_TIM_MODULE_ENABLED
#include "stm32u5xx_hal_tim.h"
#endif
#ifdef HAL_OSPI_MODULE_ENABLED
#include "stm32u5xx_hal_ospi.h"
#endif
#ifdef HAL_RNG_MODULE_ENABLED
#include "stm32u5xx_hal_rng.h"
#endif
#ifdef HAL_UART_MODULE_ENABLED
#include "stm32u5xx_hal_uart.h"
#endif

/* ---- assert ---- */
#ifdef USE_FULL_ASSERT
#define assert_param(expr) ((expr) ? (void)0U : assert_failed((uint8_t *)__FILE__, __LINE__))
void assert_failed(uint8_t *file, uint32_t line);
#else
#define assert_param(expr) ((void)0U)
#endif

#ifdef __cplusplus
}
#endif

#endif /* STM32U5xx_HAL_CONF_H */
