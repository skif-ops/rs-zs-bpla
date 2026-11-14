#ifndef BSP_GPIO_H
#define BSP_GPIO_H
#include <stdbool.h>
/* Pins from the locked Rev.A map (evt_pre_20_board_pins.h). B1 configures what bring-up needs;
   the remaining pins stay in analog/high-Z until their drivers arrive. */
void bsp_gpio_init(void);
void bsp_gpio_mic_rail(bool on);        /* 1V8_MIC enable (EN_AUX on PCB-PWR harness) */
void bsp_gpio_modem_power(bool on);     /* EN_MODEM to PCB-PWR 3V8 rail */
void bsp_gpio_modem_pwrkey(bool on);    /* CELL_PWRKEY_CMD (PD11): BG95 PWRKEY pulse driver, active HIGH */
void bsp_gpio_ble_enable(bool on);      /* BLE_EN (PE6): nRF52840 run request */
void bsp_gpio_ble_dfu_request(bool on); /* BLE_DFU_REQ (PB2, open-drain, active LOW): on = pull LOW, off = release */
bool bsp_gpio_mic_wake(void);           /* PA8 aggregated AAD wake level */
/* Dual-SIM path (evt_pre_20_dual_sim_gpio): mux select/enable outputs, card-detect and modem STATUS inputs. */
void bsp_gpio_sim_mux_select(bool slot2);   /* SIM_MUX_SEL (PE0): low = slot 1, high = slot 2 */
void bsp_gpio_sim_mux_enable(bool on);      /* SIM_MUX_EN (PE2) */
bool bsp_gpio_sim_mux_select_level(void);
bool bsp_gpio_sim_mux_enable_level(void);
bool bsp_gpio_modem_power_level(void);      /* EN_MODEM read-back */
bool bsp_gpio_sim_present(unsigned slot);   /* SIM1_DET (PE3) / SIM2_DET (PE5); polarity APP_SIM_DET_ACTIVE_HIGH */
bool bsp_gpio_cell_status(void);            /* CELL_STATUS (PD13): modem running */
bool bsp_gpio_service_button(void);     /* TAMPER_IN (PC7) active: enclosure open = service trigger candidate */
bool bsp_gpio_tamper_active(void);
bool bsp_gpio_power_good(void);
bool bsp_gpio_power_fault(void);
#endif
