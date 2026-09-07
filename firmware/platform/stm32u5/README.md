# STM32U5 target integration contract — EVT-MB 1.2

- MCU board: WeAct STM32U585CIU6, HSE 25 MHz, LSE 32.768 kHz.
- Audio: one lot of identical ICS-43434 HP or SPH0645LM4H-B I2S modules in two stereo pairs; mixing is forbidden.
- SAI1_A master RX and SAI1_B synchronous slave RX, DMA circular, 32 kHz,
  32-bit slots with 24-bit signed payload.
- GNSS: USART2 + 1PPS on PB3/TIM2_CH2.
- BG95: USART1, AT+IFC=0, dedicated 5 V pulse-capable rail.
- SX1262 and microSD: shared SPI1, independent CS.
- UART BLE service module; I2C2 power and temperature sensors.

The host CMake target verifies portable protocol/DSP scaffolding only. The target
project must be generated in STM32CubeIDE and then checked on hardware.
