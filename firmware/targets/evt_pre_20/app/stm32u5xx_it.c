/* Core exception handlers. Peripheral handlers live next to their drivers (bsp_*.c);
   SVC/PendSV/SysTick are provided by the FreeRTOS port through FreeRTOSConfig.h. */
#include "stm32u5xx_hal.h"

void NMI_Handler(void) { for (;;) {} }
void HardFault_Handler(void) { for (;;) {} }
void MemManage_Handler(void) { for (;;) {} }
void BusFault_Handler(void) { for (;;) {} }
void UsageFault_Handler(void) { for (;;) {} }
void SecureFault_Handler(void) { for (;;) {} }
void DebugMon_Handler(void) {}

void EXTI8_IRQHandler(void) { HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_8); }
