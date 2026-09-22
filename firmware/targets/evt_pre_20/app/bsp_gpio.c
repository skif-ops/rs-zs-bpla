#include "bsp_gpio.h"

#include "evt_pre_20_board_pins.h"
#include "stm32u5xx_hal.h"

/* Bring-up subset of the Rev.A pin map. Alternate-function pins are configured by the MSP of their driver. */
#define PIN_MIC_WAKE_PORT   GPIOA
#define PIN_MIC_WAKE        GPIO_PIN_8
#define PIN_EN_MODEM_PORT   GPIOD
#define PIN_EN_MODEM        GPIO_PIN_4    /* EN_MODEM (PD4, pin 85) -> PCB-PWR 3V8 rail */
#define PIN_BLE_EN_PORT     GPIOE
#define PIN_BLE_EN          GPIO_PIN_6    /* BLE_EN (PE6, pin 5): nRF52840 active-HIGH run request */
#define PIN_BLE_DFU_PORT    GPIOB
#define PIN_BLE_DFU         GPIO_PIN_2    /* BLE_DFU_REQ (PB2, pin 34): open-drain to U11 P0.15, 10 k pull-up; never drive HIGH */
#define PIN_EN_AUX_PORT     GPIOD
#define PIN_EN_AUX          GPIO_PIN_5    /* EN_AUX (PD5, pin 86) -> 1V8_MIC / aux RF */
#define PIN_PWR_GOOD_PORT   GPIOD
#define PIN_PWR_GOOD        GPIO_PIN_0    /* PWR_GOOD (PD0) from PCB-PWR */
#define PIN_PWR_FAULT_PORT  GPIOD
#define PIN_PWR_FAULT       GPIO_PIN_1    /* PWR_FAULT (PD1) from PCB-PWR */
#define PIN_AAD_CFG_PORT    GPIOA
#define PIN_AAD_CFG         GPIO_PIN_15   /* AAD_CFG (PA15): shared T5838 THSEL one-wire */
#define PIN_TAMPER_PORT     GPIOC
#define PIN_TAMPER          GPIO_PIN_7    /* TAMPER_IN (PC7): enclosure switch, active low when open */
/* Decision 2026-09-21 (no board change): the Rev.A map has no service button, so the enclosure
   tamper switch doubles as the service trigger. Held active for the 5 s hold time = service mode
   request (the enclosure is open for a service visit anyway); shorter activations stay tamper events. */

void bsp_gpio_init(void) {
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();

  /* Rail enables: default off. */
  HAL_GPIO_WritePin(PIN_EN_MODEM_PORT, PIN_EN_MODEM, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(PIN_BLE_EN_PORT, PIN_BLE_EN, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(PIN_EN_AUX_PORT, PIN_EN_AUX, GPIO_PIN_RESET);
  g.Pin = PIN_EN_MODEM;
  g.Mode = GPIO_MODE_OUTPUT_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(PIN_EN_MODEM_PORT, &g);
  g.Pin = PIN_EN_AUX;
  HAL_GPIO_Init(PIN_EN_AUX_PORT, &g);
  g.Pin = PIN_BLE_EN;
  HAL_GPIO_Init(PIN_BLE_EN_PORT, &g);

  /* BLE_DFU_REQ: open-drain, released (high-Z) by default; only a controlled recovery pulls it LOW. */
  HAL_GPIO_WritePin(PIN_BLE_DFU_PORT, PIN_BLE_DFU, GPIO_PIN_SET);
  g.Pin = PIN_BLE_DFU;
  g.Mode = GPIO_MODE_OUTPUT_OD;
  g.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(PIN_BLE_DFU_PORT, &g);

  /* MIC_WAKE: EXTI8 rising edge (AAD wake), pulled down (T5838 WAKE is push-pull high on detect). */
  g.Pin = PIN_MIC_WAKE;
  g.Mode = GPIO_MODE_IT_RISING;
  g.Pull = GPIO_PULLDOWN;
  HAL_GPIO_Init(PIN_MIC_WAKE_PORT, &g);
  HAL_NVIC_SetPriority(EXTI8_IRQn, 9, 0);
  HAL_NVIC_EnableIRQ(EXTI8_IRQn);

  /* Power interface status inputs. */
  g.Pin = PIN_PWR_GOOD | PIN_PWR_FAULT;
  g.Mode = GPIO_MODE_INPUT;
  g.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(PIN_PWR_GOOD_PORT, &g);

  /* TAMPER_IN doubles as the service trigger: input with pull-up, polled by the supervisor. */
  g.Pin = PIN_TAMPER;
  g.Mode = GPIO_MODE_INPUT;
  g.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(PIN_TAMPER_PORT, &g);

  /* AAD_CFG idle low until the THSEL programming sequence (target_status AAD addendum) runs. */
  HAL_GPIO_WritePin(PIN_AAD_CFG_PORT, PIN_AAD_CFG, GPIO_PIN_RESET);
  g.Pin = PIN_AAD_CFG;
  g.Mode = GPIO_MODE_OUTPUT_PP;
  g.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(PIN_AAD_CFG_PORT, &g);
}

void bsp_gpio_mic_rail(bool on) { HAL_GPIO_WritePin(PIN_EN_AUX_PORT, PIN_EN_AUX, on ? GPIO_PIN_SET : GPIO_PIN_RESET); }
void bsp_gpio_ble_enable(bool on) { HAL_GPIO_WritePin(PIN_BLE_EN_PORT, PIN_BLE_EN, on ? GPIO_PIN_SET : GPIO_PIN_RESET); }
void bsp_gpio_ble_dfu_request(bool on) { HAL_GPIO_WritePin(PIN_BLE_DFU_PORT, PIN_BLE_DFU, on ? GPIO_PIN_RESET : GPIO_PIN_SET); }
void bsp_gpio_modem_power(bool on) { HAL_GPIO_WritePin(PIN_EN_MODEM_PORT, PIN_EN_MODEM, on ? GPIO_PIN_SET : GPIO_PIN_RESET); }
bool bsp_gpio_mic_wake(void) { return HAL_GPIO_ReadPin(PIN_MIC_WAKE_PORT, PIN_MIC_WAKE) == GPIO_PIN_SET; }
bool bsp_gpio_service_button(void) { return HAL_GPIO_ReadPin(PIN_TAMPER_PORT, PIN_TAMPER) == GPIO_PIN_RESET; }
bool bsp_gpio_tamper_active(void) { return bsp_gpio_service_button(); }
bool bsp_gpio_power_good(void) { return HAL_GPIO_ReadPin(PIN_PWR_GOOD_PORT, PIN_PWR_GOOD) == GPIO_PIN_SET; }
bool bsp_gpio_power_fault(void) { return HAL_GPIO_ReadPin(PIN_PWR_FAULT_PORT, PIN_PWR_FAULT) == GPIO_PIN_SET; }
