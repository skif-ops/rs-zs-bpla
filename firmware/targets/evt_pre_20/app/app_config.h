#ifndef APP_CONFIG_H
#define APP_CONFIG_H

/* Dioneya EVT-PRE-20 target application: fixed parameters of milestone B1 (bring-up). */

#include <stdint.h>

/* Audio: 4 x T5838 on MDF1, PDM clock 3.2 MHz (PLL1P) / SINC5 decimation 100 = 32 kHz. */
#define APP_AUDIO_SAMPLE_RATE_HZ     32000u
#define APP_MDF_PDM_CLOCK_HZ         3200000u
#define APP_MDF_DECIMATION           100u
#define APP_AUDIO_BLOCK_SAMPLES      320u        /* 10 ms per DMA half per channel */
#define APP_AUDIO_RING_FRAMES        (APP_AUDIO_SAMPLE_RATE_HZ * 3u)   /* 3 s prehistory, 4 ch x int16 = 768 KB? no: 3 s x 32000 x 4 x 2 = 768 KB */
/* The 3 s prehistory does not fit SRAM together with everything else; B1 keeps 1 s (256 KB) and moves the
   prehistory to NOR in B3 (zs_prehistory / zs_nor_archive). */
#define APP_AUDIO_RING_FRAMES_B1     (APP_AUDIO_SAMPLE_RATE_HZ * 1u)

/* PPS timestamping: TIM2 free-running 32-bit at 16 MHz (62.5 ns), input capture on CH1 (PA0). */
#define APP_TIM2_CLOCK_HZ            16000000u
#define APP_PPS_LABEL_TIMEOUT_MS     900u

/* UARTs. */
#define APP_UART_CELL_BAUD           115200u   /* BG95 main UART, USART1 PB6/PB7 */
#define APP_UART_GNSS_BAUD           9600u     /* USART2 PA2/PA3 */
#define APP_UART_BLE_BAUD            115200u   /* USART3 PB10/PB11 (nRF52840), not started in B1 */
#define APP_UART_CONSOLE_BAUD        115200u   /* LPUART1 PC0/PC1 diagnostic console */
#define APP_UART_RX_RING             512u

/* Service mode trigger: TAMPER_IN (PC7) held active for this long (BLE ICD: 5 s). */
#define APP_SERVICE_HOLD_MS          5000u

/* Task priorities (higher = more urgent) and stacks in words. */
#define APP_PRIO_AUDIO               6
#define APP_PRIO_SUPERVISOR          5
#define APP_PRIO_COMMS               3
#define APP_PRIO_SERVICE             3
#define APP_PRIO_CONSOLE             1
#define APP_STACK_AUDIO              1024
#define APP_STACK_SUPERVISOR         768
#define APP_STACK_COMMS              1536
#define APP_STACK_SERVICE            768
#define APP_STACK_CONSOLE            512

/* NVIC priorities (0 = highest). FreeRTOS syscall ceiling is 5: ISRs at 5..15 may call FromISR APIs. */
#define APP_IRQ_PRIO_TIM2_PPS        4   /* timestamp capture: above the RTOS ceiling, no RTOS calls inside */
#define APP_IRQ_PRIO_GPDMA_MDF       6
#define APP_IRQ_PRIO_MDF             7
#define APP_IRQ_PRIO_UART            8
#define APP_IRQ_PRIO_EXTI            9

#endif
