#ifndef BSP_CLOCK_H
#define BSP_CLOCK_H
#include <stdbool.h>
#include <stdint.h>
/* Rev.A clock policy REV_A_INTERNAL_HSI_MSI_PLL_NO_HSE: MSIS 4 MHz (PLL-mode locked to LSE) -> PLL1 -> 160 MHz SYSCLK,
   PLL1P 3.2 MHz for MDF1, LSE = SiT1552 in bypass, HSI16 for TIM2/UART kernel clocks. */
bool bsp_clock_init_160mhz(void);
uint32_t bsp_clock_mdf_kernel_hz(void);
#endif
