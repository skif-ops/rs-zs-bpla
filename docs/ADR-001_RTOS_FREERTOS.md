# ADR-001: RTOS for the EVT-PRE-20 station firmware

Date: 2026-09-21. Status: PROPOSED (to be recorded in docs/DECISION_LOG.csv as a DEC entry after review).

## Context

The portable firmware core (41 modules, host-tested) has no execution model: no `main`, no scheduler,
no HAL binding. The station has five operating modes (S0..S4), several concurrent I/O streams
(4-channel PDM via DMA, GNSS UART, BG95 UART, nRF52840 UART, LoRa SPI) and hard timing on the
PPS/sample-counter binding. The decision log contains no RTOS decision.

## Decision

FreeRTOS kernel V11.1.0, GCC ARM_CM33_NTZ port (TrustZone disabled, FPU on), heap_4 (96 KB),
1 kHz tick on SysTick, HAL timebase on TIM6. Task set for B1: audio (prio 6), supervisor (5),
gnss (3), console (1); B2 adds comms (BG95) and service (nRF UART). ISRs above the FreeRTOS
syscall ceiling (priority < 5) are limited to timestamp capture (TIM2 PPS) and make no RTOS calls.

## Alternatives considered

- Bare-metal super-loop: simplest, but the BG95 session, PDM processing and the service link
  each need blocking waits; a cooperative loop would make the 10 ms audio deadline depend on
  every other driver's worst case.
- Zephyr: better long-term ecosystem (BLE, MCUboot) but a different build system and board
  port work that competes with the pilot schedule; the nRF52840 side may still use Zephyr.
- ThreadX (Azure RTOS, ST-supported): comparable; FreeRTOS is chosen for the wider in-house
  familiarity and MIT licence.

## Consequences

- Tickless idle on LPTIM and STOP2 entry (S0) are implemented in the low-power milestone (B3);
  B1 runs at 160 MHz continuously.
- Every ISR that wakes a task uses `*FromISR` APIs and priority >= 5.
- Stack sizes are watermarked with `uxTaskGetStackHighWaterMark` on the bench before release.
