#include "bsp_nor.h"

#include "FreeRTOS.h"
#include "semphr.h"
#include "task.h"
#include "stm32u5xx_hal.h"

#include <string.h>

static OSPI_HandleTypeDef hospi;

/* One NOR, many tasks (outbox, command journal, records, nRF image, audio prehistory): zs_nor takes this lock per
   page program, erase block and read.  Static mutex with priority inheritance; before the scheduler runs there is
   only one context, so the lock is a no-op then. */
static StaticSemaphore_t nor_mutex_storage;
static SemaphoreHandle_t nor_mutex;
static void nor_lock(void *ctx) {
  (void)ctx;
  if (nor_mutex && xTaskGetSchedulerState() == taskSCHEDULER_RUNNING) (void)xSemaphoreTake(nor_mutex, portMAX_DELAY);
}
static void nor_unlock(void *ctx) {
  (void)ctx;
  if (nor_mutex && xTaskGetSchedulerState() == taskSCHEDULER_RUNNING) (void)xSemaphoreGive(nor_mutex);
}

/* zs_nor_port_t command executor: opcode, optional 3/4-byte address, then either tx or rx data on one line.
   tx followed by rx under the same nCS is only supported when tx is a dummy prefix (SFDP read 0x5A). */
static int nor_command(void *ctx, uint8_t opcode, uint32_t address, uint8_t address_bytes,
                       const uint8_t *tx, size_t tx_len, uint8_t *rx, size_t rx_len) {
  OSPI_RegularCmdTypeDef cmd;
  (void)ctx;
  if (address_bytes != 0u && address_bytes != 3u && address_bytes != 4u) return -1;
  if (tx_len > 256u || rx_len > 4096u) return -1;
  memset(&cmd, 0, sizeof(cmd));
  cmd.OperationType = HAL_OSPI_OPTYPE_COMMON_CFG;
  cmd.FlashId = HAL_OSPI_FLASH_ID_1;
  cmd.Instruction = opcode;
  cmd.InstructionMode = HAL_OSPI_INSTRUCTION_1_LINE;
  cmd.InstructionSize = HAL_OSPI_INSTRUCTION_8_BITS;
  cmd.InstructionDtrMode = HAL_OSPI_INSTRUCTION_DTR_DISABLE;
  cmd.AddressMode = address_bytes ? HAL_OSPI_ADDRESS_1_LINE : HAL_OSPI_ADDRESS_NONE;
  cmd.AddressSize = address_bytes == 3u ? HAL_OSPI_ADDRESS_24_BITS : HAL_OSPI_ADDRESS_32_BITS;
  cmd.Address = address;
  cmd.AddressDtrMode = HAL_OSPI_ADDRESS_DTR_DISABLE;
  cmd.AlternateBytesMode = HAL_OSPI_ALTERNATE_BYTES_NONE;
  cmd.DataDtrMode = HAL_OSPI_DATA_DTR_DISABLE;
  cmd.DQSMode = HAL_OSPI_DQS_DISABLE;
  cmd.SIOOMode = HAL_OSPI_SIOO_INST_EVERY_CMD;
  cmd.DummyCycles = 0u;
  if (tx && tx_len && rx && rx_len) {           /* dummy prefix before a read: only zero/0xff bytes are expressible */
    for (size_t i = 0u; i < tx_len; i++) if (tx[i] != 0u && tx[i] != 0xffu) return -1;
    cmd.DummyCycles = (uint32_t)tx_len * 8u;
    tx = NULL; tx_len = 0u;
  }
  if ((tx && tx_len) || (rx && rx_len)) {
    cmd.DataMode = HAL_OSPI_DATA_1_LINE;
    cmd.NbData = (uint32_t)(tx_len ? tx_len : rx_len);
  } else {
    cmd.DataMode = HAL_OSPI_DATA_NONE;
    cmd.NbData = 0u;
  }
  if (HAL_OSPI_Command(&hospi, &cmd, HAL_OSPI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) return -1;
  if (tx && tx_len) return HAL_OSPI_Transmit(&hospi, (uint8_t *)tx, HAL_OSPI_TIMEOUT_DEFAULT_VALUE) == HAL_OK ? 0 : -1;
  if (rx && rx_len) return HAL_OSPI_Receive(&hospi, rx, HAL_OSPI_TIMEOUT_DEFAULT_VALUE) == HAL_OK ? 0 : -1;
  return 0;
}

static uint32_t nor_millis(void *ctx) { (void)ctx; return xTaskGetTickCount(); }
static void nor_delay(void *ctx, uint32_t ms) { (void)ctx; vTaskDelay(pdMS_TO_TICKS(ms ? ms : 1u)); }

bool bsp_nor_init(zs_nor_t *nor) {
  OSPIM_CfgTypeDef iom;
  const zs_nor_port_t port = {NULL, nor_command, nor_millis, nor_delay};
  const zs_nor_geometry_t geometry = zs_nor_geometry_64m_4byte();
  memset(&hospi, 0, sizeof(hospi));
  hospi.Instance = OCTOSPI1;
  hospi.Init.FifoThreshold = 4u;
  hospi.Init.DualQuad = HAL_OSPI_DUALQUAD_DISABLE;
  hospi.Init.MemoryType = HAL_OSPI_MEMTYPE_MICRON;   /* generic SPI-NOR command set */
  hospi.Init.DeviceSize = 26u;                        /* 2^26 = 64 MiB */
  hospi.Init.ChipSelectHighTime = 2u;
  hospi.Init.FreeRunningClock = HAL_OSPI_FREERUNCLK_DISABLE;
  hospi.Init.ClockMode = HAL_OSPI_CLOCK_MODE_0;
  hospi.Init.WrapSize = HAL_OSPI_WRAP_NOT_SUPPORTED;
  hospi.Init.ClockPrescaler = 4u;                     /* 160 MHz / 4 = 40 MHz, within the 50 MHz READ (0x13) limit */
  hospi.Init.SampleShifting = HAL_OSPI_SAMPLE_SHIFTING_NONE;
  hospi.Init.DelayHoldQuarterCycle = HAL_OSPI_DHQC_DISABLE;
  hospi.Init.ChipSelectBoundary = 0u;
  hospi.Init.DelayBlockBypass = HAL_OSPI_DELAY_BLOCK_BYPASSED;
  hospi.Init.MaxTran = 0u;
  hospi.Init.Refresh = 0u;
  if (HAL_OSPI_Init(&hospi) != HAL_OK) return false;
  memset(&iom, 0, sizeof(iom));
  iom.ClkPort = 1u;
  iom.NCSPort = 1u;
  iom.IOLowPort = HAL_OSPIM_IOPORT_1_LOW;
  if (HAL_OSPIM_Config(&hospi, &iom, HAL_OSPI_TIMEOUT_DEFAULT_VALUE) != HAL_OK) return false;
  if (!zs_nor_init(nor, &port, &geometry)) return false;
  if (!nor_mutex) nor_mutex = xSemaphoreCreateMutexStatic(&nor_mutex_storage);
  zs_nor_set_lock(nor, nor_lock, nor_unlock, NULL);
  return true;
}

void HAL_OSPI_MspInit(OSPI_HandleTypeDef *h) {
  GPIO_InitTypeDef g = {0};
  if (h->Instance != OCTOSPI1) return;
  __HAL_RCC_OSPIM_CLK_ENABLE();
  __HAL_RCC_OSPI1_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  g.Pin = GPIO_PIN_10 | GPIO_PIN_11 | GPIO_PIN_12 | GPIO_PIN_13 | GPIO_PIN_14 | GPIO_PIN_15;   /* NOR_CLK NCS IO0..IO3 */
  g.Mode = GPIO_MODE_AF_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  g.Alternate = GPIO_AF10_OCTOSPI1;
  HAL_GPIO_Init(GPIOE, &g);
}
