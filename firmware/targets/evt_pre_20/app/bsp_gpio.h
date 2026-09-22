#ifndef BSP_GPIO_H
#define BSP_GPIO_H
#include <stdbool.h>
/* Pins from the locked Rev.A map (evt_pre_20_board_pins.h). B1 configures what bring-up needs;
   the remaining pins stay in analog/high-Z until their drivers arrive. */
void bsp_gpio_init(void);
void bsp_gpio_mic_rail(bool on);        /* 1V8_MIC enable (EN_AUX on PCB-PWR harness) */
void bsp_gpio_modem_power(bool on);     /* EN_MODEM to PCB-PWR 3V8 rail */
void bsp_gpio_ble_enable(bool on);      /* BLE_EN (PE6): nRF52840 run request */
bool bsp_gpio_mic_wake(void);           /* PA8 aggregated AAD wake level */
bool bsp_gpio_service_button(void);     /* TAMPER_IN (PC7) active: enclosure open = service trigger candidate */
bool bsp_gpio_tamper_active(void);
bool bsp_gpio_power_good(void);
bool bsp_gpio_power_fault(void);
#endif
