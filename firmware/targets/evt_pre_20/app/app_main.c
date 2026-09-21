/*
 * Dioneya EVT-PRE-20 station firmware, milestone B1 bring-up entry point.
 * HAL init -> Rev.A clock tree -> GPIO -> UARTs -> FreeRTOS tasks (audio/supervisor/gnss/console).
 */
#include "FreeRTOS.h"
#include "app_config.h"
#include "bsp_clock.h"
#include "bsp_gpio.h"
#include "bsp_uart.h"
#include "stm32u5xx_hal.h"
#include "task.h"
#include "tasks.h"

static void fatal(void) {
  taskDISABLE_INTERRUPTS();
  for (;;) {}
}

int main(void) {
  HAL_Init();
  if (!bsp_clock_init_160mhz()) fatal();
  HAL_ICACHE_Enable();
  bsp_gpio_init();
  if (!bsp_uart_init(BSP_UART_CONSOLE, APP_UART_CONSOLE_BAUD)) fatal();
  if (!bsp_uart_init(BSP_UART_GNSS, APP_UART_GNSS_BAUD)) fatal();
  if (!bsp_uart_init(BSP_UART_CELL, APP_UART_CELL_BAUD)) fatal();
  if (!app_tasks_create()) fatal();
  vTaskStartScheduler();
  fatal();
  return 0;
}

/* ---- FreeRTOS hooks ---------------------------------------------------------- */
void vApplicationStackOverflowHook(TaskHandle_t task, char *name) { (void)task; (void)name; fatal(); }
void vApplicationMallocFailedHook(void) { fatal(); }

void vApplicationGetIdleTaskMemory(StaticTask_t **tcb, StackType_t **stack, configSTACK_DEPTH_TYPE *size) {
  static StaticTask_t idle_tcb;
  static StackType_t idle_stack[configMINIMAL_STACK_SIZE];
  *tcb = &idle_tcb; *stack = idle_stack; *size = configMINIMAL_STACK_SIZE;
}
void vApplicationGetTimerTaskMemory(StaticTask_t **tcb, StackType_t **stack, configSTACK_DEPTH_TYPE *size) {
  static StaticTask_t timer_tcb;
  static StackType_t timer_stack[configTIMER_TASK_STACK_DEPTH];
  *tcb = &timer_tcb; *stack = timer_stack; *size = configTIMER_TASK_STACK_DEPTH;
}

/* HAL_Delay must not spin on the HAL tick while the scheduler runs. */
void HAL_Delay(uint32_t ms) {
  if (xTaskGetSchedulerState() == taskSCHEDULER_RUNNING) vTaskDelay(pdMS_TO_TICKS(ms));
  else { uint32_t start = HAL_GetTick(); while ((HAL_GetTick() - start) < ms) {} }
}
