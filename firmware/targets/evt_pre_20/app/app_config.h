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
#define APP_AUDIO_RING_FRAMES_B1     (APP_AUDIO_SAMPLE_RATE_HZ * 9u / 8u)   /* 1.125 s: a 1 s window plus the fetch latency of the pipeline (<= 100 ms) */

/* PPS timestamping: TIM2 free-running 32-bit at 16 MHz (62.5 ns), input capture on CH1 (PA0). */
#define APP_TIM2_CLOCK_HZ            16000000u
#define APP_PPS_LABEL_TIMEOUT_MS     900u

/* UARTs. */
#define APP_UART_CELL_BAUD           115200u   /* BG95 main UART, USART1 PB6/PB7 */
#define APP_UART_GNSS_BAUD           9600u     /* USART2 PA2/PA3 */
#define APP_UART_BLE_BAUD            115200u   /* USART3 PB10/PB11 (nRF52840 bridge, IPC link addendum C) */
#define APP_BLE_SERVICE_WINDOW_S     600u      /* advertising window opened with S4 SERVICE */
#define APP_STATION_SERIAL           "DIO-EVT-B01"   /* B1 bench identity until provisioning lands the label data */
#define APP_STATION_ID               901u
#define APP_STATION_HW_REV           "Rev.A"
#define APP_STATION_FW_VERSION       "0.1.0-b1"
#define APP_STATION_BL_VERSION       "0.1.0"
#define APP_UART_CONSOLE_BAUD        115200u   /* LPUART1 PC0/PC1 diagnostic console */
#define APP_UART_RX_RING             512u

/* NOR map (zs_nor_storage_layout_make_stores): archive | command journal | event outbox | secrets x2 | boot counter | nrf image | config x2 | installation x2. */
#define APP_NOR_COMMAND_SLOTS        16u
#define APP_NOR_OUTBOX_SLOTS         256u

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
#define APP_STACK_COMMS              2048     /* Ed25519 verify of a command runs on this stack (~3 KB peak) */
#define APP_STACK_SERVICE            768
#define APP_STACK_CONSOLE            1024     /* nrfimg: NOR erase/verify and printf on the console stack */
#define APP_PRIO_BLE                 3
#define APP_PRIO_DSP                 2        /* station pipeline: below capture and the service tasks, above the console */
#define APP_STACK_DSP                1536
#define APP_BOOT_ID                  1u       /* boot_id until the NOR boot counter is bound (RAM fallback keeps it) */
#define APP_STACK_BLE                1280     /* config/installation/secrets commits + nRF image update on this stack */
#define APP_COMMS_HEARTBEAT_MS       60000u   /* zs_station_comms heartbeat period */
#define APP_COMMS_LINGER_MS          10000u   /* S3 stays this long after the last activity: queued/answering commands */
#define APP_COMMS_PUBLIC_APN         1        /* pilot policy: public APNs only (CELLULAR_CONNECTIVITY_BASELINE) */
#define APP_SIM_DET_ACTIVE_HIGH      1        /* SIMx_DET level that means "card present" (confirm on Rev.A) */
#define APP_SIM_SAFE_OFF_RETRY_MS    600000u  /* both slots exhausted / no SIM: reset the failure counters and try again */
/* Power monitor (INA226 on I2C2): sampling period and the battery level map (bus voltage -> percent; the pack
   chemistry / cell count of the pilot enclosure is not final: 4S LiFePO4 assumed, confirm before the field). */
#define APP_POWER_PERIOD_MS          1000u
#define APP_BATTERY_EMPTY_MV         11800u
#define APP_BATTERY_FULL_MV          14200u
#define APP_PRIO_POWER               3
#define APP_STACK_POWER              512
#define APP_DSP_QUIET_WINDOWS        6u       /* S2 -> DSP_DONE_NOTHING after this many windows at level NONE (3 s at the 0.5 s hop) */
#define APP_OUTBOX_RETRY_MS          300000u  /* pending events after a failed S3: first retry after 5 min, doubling */
#define APP_OUTBOX_RETRY_MAX_MS      3600000u /* ... up to once an hour, until a session completes */
#define APP_COMMS_DEGRADED_AFTER     3u       /* consecutive S3 sessions ended by the watchdog -> GSM degraded */
#define APP_COMMS_MAX_DEGRADED_MS    60000u   /* S3 watchdog while degraded (default policy: 180 s) */
#define APP_GSM_PROBE_MS             1800000u /* while degraded: try GSM again every 30 min (capped S3) */
/* LoRa fallback (ICD addendum A). TX stays disabled until the signed RU868 profile and the RF gate are closed:
   the task runs DRY (radio bring-up + frame log only). Carrier from config/lora/RU868.yaml, +14 dBm = 25 mW RU limit. */
#define APP_LORA_TX_ENABLED          0
#define APP_LORA_FREQUENCY_HZ        868900000u
#define APP_LORA_SF                  9u
#define APP_LORA_BW_HZ               125000u
#define APP_LORA_TX_DBM              14
#define APP_LORA_PROFILE_ID          1u
#define APP_PRIO_LORA                3
#define APP_STACK_LORA               768
/* Hardware watchdog: IWDG timeout and the task-liveness window (longest normal block: INA226 re-probe 5 s). */
#define APP_WATCHDOG_TIMEOUT_MS      25000u
#define APP_WATCHDOG_WINDOW_MS       10000u
#define APP_NRF_UPDATE_HOLD_MS       900000u /* nRF image update blocks the BLE task: exempt it for up to 15 min */
/* Command validity (ICD §2.1): network time (NITZ) stands in for GNSS this long after it was read (tick drift is
   LSE-locked, ~0.2 s/h). */
#define APP_COMMAND_NETWORK_TIME_MAX_MS 86400000u
/* Remote commands (ICD addendum D): minimum delay between the reboot ACK and the reset; runtime parameter record in
   the last APP_PARAMS_NOR_BLOCKS erase blocks of the nRF image partition (128 blocks, MCUboot needs 119). */
#define APP_REBOOT_MIN_DELAY_S       5u
#define APP_PARAMS_NOR_BLOCKS        2u
/* Audio prehistory (addendum B): the recorder task, and the capture kept on (any mode but SHUTDOWN) this long after
   an event so the post-event segment exists (S3 and S0 otherwise stop the PDM clock). */
#define APP_PRIO_REC                 3
#define APP_STACK_REC                768
#define APP_AUDIO_POST_EVENT_MS      30000u

/* NVIC priorities (0 = highest). FreeRTOS syscall ceiling is 5: ISRs at 5..15 may call FromISR APIs. */
#define APP_IRQ_PRIO_TIM2_PPS        4   /* timestamp capture: above the RTOS ceiling, no RTOS calls inside */
#define APP_IRQ_PRIO_GPDMA_MDF       6
#define APP_IRQ_PRIO_MDF             7
#define APP_IRQ_PRIO_UART            8
#define APP_IRQ_PRIO_EXTI            9

#endif
