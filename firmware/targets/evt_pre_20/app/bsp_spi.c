#include "bsp_spi.h"

#include "stm32u5xx_hal.h"

#define SPI_TIMEOUT_MS 50u

static SPI_HandleTypeDef hspi1;
static bool ready;
static uint32_t errors;

static void lora_gpio_init(void) {
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOB_CLK_ENABLE(); __HAL_RCC_GPIOC_CLK_ENABLE(); __HAL_RCC_GPIOD_CLK_ENABLE();
  /* outputs: NSS high (idle), RESET_N high (out of reset), TXEN/RXEN low (RF switch idle) */
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_10, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_15, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_8, GPIO_PIN_RESET);
  g.Mode = GPIO_MODE_OUTPUT_PP; g.Pull = GPIO_NOPULL; g.Speed = GPIO_SPEED_FREQ_LOW;
  g.Pin = GPIO_PIN_4; HAL_GPIO_Init(GPIOA, &g);
  g.Pin = GPIO_PIN_15; HAL_GPIO_Init(GPIOB, &g);
  g.Pin = GPIO_PIN_8 | GPIO_PIN_10; HAL_GPIO_Init(GPIOD, &g);
  /* inputs: BUSY, DIO1 */
  g.Mode = GPIO_MODE_INPUT; g.Pull = GPIO_PULLDOWN;
  g.Pin = GPIO_PIN_9; HAL_GPIO_Init(GPIOD, &g);
  g.Pin = GPIO_PIN_2; HAL_GPIO_Init(GPIOC, &g);
}

bool bsp_spi_init(void) {
  lora_gpio_init();
  hspi1.Instance = SPI1;
  hspi1.Init.Mode = SPI_MODE_MASTER;
  hspi1.Init.Direction = SPI_DIRECTION_2LINES;
  hspi1.Init.DataSize = SPI_DATASIZE_8BIT;
  hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi1.Init.CLKPhase = SPI_PHASE_1EDGE;
  hspi1.Init.NSS = SPI_NSS_SOFT;
  hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_32;    /* 160 MHz / 32 = 5 MHz (< 16 MHz of the SX1262) */
  hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi1.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi1.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi1.Init.NSSPMode = SPI_NSS_PULSE_DISABLE;
  hspi1.Init.NSSPolarity = SPI_NSS_POLARITY_LOW;
  hspi1.Init.FifoThreshold = SPI_FIFO_THRESHOLD_01DATA;
  hspi1.Init.MasterSSIdleness = SPI_MASTER_SS_IDLENESS_00CYCLE;
  hspi1.Init.MasterInterDataIdleness = SPI_MASTER_INTERDATA_IDLENESS_00CYCLE;
  hspi1.Init.MasterReceiverAutoSusp = SPI_MASTER_RX_AUTOSUSP_DISABLE;
  hspi1.Init.MasterKeepIOState = SPI_MASTER_KEEP_IO_STATE_ENABLE;
  hspi1.Init.IOSwap = SPI_IO_SWAP_DISABLE;
  hspi1.Init.ReadyMasterManagement = SPI_RDY_MASTER_MANAGEMENT_INTERNALLY;
  hspi1.Init.ReadyPolarity = SPI_RDY_POLARITY_HIGH;
  ready = HAL_SPI_Init(&hspi1) == HAL_OK;
  return ready;
}

bool bsp_spi_transfer(const uint8_t *tx, uint8_t *rx, size_t len) {
  if (!ready || !tx || !rx || len == 0u || len > 0xffffu) return false;
  if (HAL_SPI_TransmitReceive(&hspi1, (uint8_t *)tx, rx, (uint16_t)len, SPI_TIMEOUT_MS) != HAL_OK) { errors++; return false; }
  return true;
}

void bsp_lora_pin_write(bsp_lora_pin_t pin, bool level) {
  const GPIO_PinState s = level ? GPIO_PIN_SET : GPIO_PIN_RESET;
  switch (pin) {
    case BSP_LORA_PIN_NSS: HAL_GPIO_WritePin(GPIOA, GPIO_PIN_4, s); break;
    case BSP_LORA_PIN_RESET: HAL_GPIO_WritePin(GPIOD, GPIO_PIN_10, s); break;
    case BSP_LORA_PIN_TXEN: HAL_GPIO_WritePin(GPIOB, GPIO_PIN_15, s); break;
    case BSP_LORA_PIN_RXEN: HAL_GPIO_WritePin(GPIOD, GPIO_PIN_8, s); break;
    default: break;
  }
}

bool bsp_lora_pin_read(bsp_lora_pin_t pin) {
  switch (pin) {
    case BSP_LORA_PIN_BUSY: return HAL_GPIO_ReadPin(GPIOD, GPIO_PIN_9) == GPIO_PIN_SET;
    case BSP_LORA_PIN_DIO1: return HAL_GPIO_ReadPin(GPIOC, GPIO_PIN_2) == GPIO_PIN_SET;
    case BSP_LORA_PIN_NSS: return HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_4) == GPIO_PIN_SET;
    case BSP_LORA_PIN_TXEN: return HAL_GPIO_ReadPin(GPIOB, GPIO_PIN_15) == GPIO_PIN_SET;
    case BSP_LORA_PIN_RXEN: return HAL_GPIO_ReadPin(GPIOD, GPIO_PIN_8) == GPIO_PIN_SET;
    default: return false;
  }
}

uint32_t bsp_spi_errors(void) { return errors; }
