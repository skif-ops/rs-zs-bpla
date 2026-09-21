#include "bsp_uart.h"

#include "app_config.h"
#include "stm32u5xx_hal.h"

typedef struct {
  UART_HandleTypeDef h;
  uint8_t ring[APP_UART_RX_RING];
  volatile uint16_t head, tail;
  uint8_t rx_byte;
  uint32_t overruns;
} uart_t;

static uart_t u[BSP_UART_COUNT];

static USART_TypeDef *const instance[BSP_UART_COUNT] = {USART1, USART2, LPUART1};
static const IRQn_Type irq[BSP_UART_COUNT] = {USART1_IRQn, USART2_IRQn, LPUART1_IRQn};

bool bsp_uart_init(bsp_uart_id_t id, uint32_t baud) {
  uart_t *p;
  if (id >= BSP_UART_COUNT) return false;
  p = &u[id];
  p->head = p->tail = 0u;
  p->h.Instance = instance[id];
  p->h.Init.BaudRate = baud;
  p->h.Init.WordLength = UART_WORDLENGTH_8B;
  p->h.Init.StopBits = UART_STOPBITS_1;
  p->h.Init.Parity = UART_PARITY_NONE;
  p->h.Init.Mode = UART_MODE_TX_RX;
  p->h.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  p->h.Init.OverSampling = UART_OVERSAMPLING_16;
  p->h.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  p->h.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  p->h.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  if (HAL_UART_Init(&p->h) != HAL_OK) return false;
  HAL_NVIC_SetPriority(irq[id], APP_IRQ_PRIO_UART, 0);
  HAL_NVIC_EnableIRQ(irq[id]);
  return HAL_UART_Receive_IT(&p->h, &p->rx_byte, 1u) == HAL_OK;
}

int bsp_uart_write(bsp_uart_id_t id, const uint8_t *data, size_t len) {
  if (id >= BSP_UART_COUNT || (!data && len)) return -1;
  if (len == 0u) return 0;
  return HAL_UART_Transmit(&u[id].h, data, (uint16_t)len, 1000u) == HAL_OK ? (int)len : -1;
}

size_t bsp_uart_read(bsp_uart_id_t id, uint8_t *out, size_t cap) {
  size_t n = 0u;
  uart_t *p;
  if (id >= BSP_UART_COUNT) return 0u;
  p = &u[id];
  while (n < cap && p->tail != p->head) {
    out[n++] = p->ring[p->tail];
    p->tail = (uint16_t)((p->tail + 1u) % APP_UART_RX_RING);
  }
  return n;
}

uint32_t bsp_uart_rx_overruns(bsp_uart_id_t id) { return id < BSP_UART_COUNT ? u[id].overruns : 0u; }

static uart_t *lookup(UART_HandleTypeDef *h, bsp_uart_id_t *id) {
  for (unsigned i = 0u; i < BSP_UART_COUNT; i++) if (h == &u[i].h) { *id = (bsp_uart_id_t)i; return &u[i]; }
  return NULL;
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *h) {
  bsp_uart_id_t id;
  uart_t *p = lookup(h, &id);
  if (!p) return;
  {
    uint16_t next = (uint16_t)((p->head + 1u) % APP_UART_RX_RING);
    if (next == p->tail) p->overruns++;
    else { p->ring[p->head] = p->rx_byte; p->head = next; }
  }
  (void)HAL_UART_Receive_IT(h, &p->rx_byte, 1u);
  app_uart_rx_notify_from_isr(id);
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *h) {
  bsp_uart_id_t id;
  uart_t *p = lookup(h, &id);
  if (!p) return;
  p->overruns++;
  __HAL_UART_CLEAR_FLAG(h, UART_CLEAR_OREF | UART_CLEAR_NEF | UART_CLEAR_FEF | UART_CLEAR_PEF);
  (void)HAL_UART_Receive_IT(h, &p->rx_byte, 1u);
}

void USART1_IRQHandler(void) { HAL_UART_IRQHandler(&u[BSP_UART_CELL].h); }
void USART2_IRQHandler(void) { HAL_UART_IRQHandler(&u[BSP_UART_GNSS].h); }
void LPUART1_IRQHandler(void) { HAL_UART_IRQHandler(&u[BSP_UART_CONSOLE].h); }

void HAL_UART_MspInit(UART_HandleTypeDef *h) {
  GPIO_InitTypeDef g = {0};
  g.Mode = GPIO_MODE_AF_PP;
  g.Pull = GPIO_PULLUP;
  g.Speed = GPIO_SPEED_FREQ_MEDIUM;
  if (h->Instance == USART1) {          /* CELL_TX PB6 / CELL_RX PB7, AF7 */
    __HAL_RCC_USART1_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    g.Pin = GPIO_PIN_6 | GPIO_PIN_7;
    g.Alternate = GPIO_AF7_USART1;
    HAL_GPIO_Init(GPIOB, &g);
  } else if (h->Instance == USART2) {   /* GNSS_TX PA2 / GNSS_RX PA3, AF7 */
    __HAL_RCC_USART2_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();
    g.Pin = GPIO_PIN_2 | GPIO_PIN_3;
    g.Alternate = GPIO_AF7_USART2;
    HAL_GPIO_Init(GPIOA, &g);
  } else if (h->Instance == LPUART1) {  /* TEST_UART_RX PC0 / TEST_UART_TX PC1, AF8 */
    __HAL_RCC_LPUART1_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    g.Pin = GPIO_PIN_0 | GPIO_PIN_1;
    g.Alternate = GPIO_AF8_LPUART1;
    HAL_GPIO_Init(GPIOC, &g);
  }
}
