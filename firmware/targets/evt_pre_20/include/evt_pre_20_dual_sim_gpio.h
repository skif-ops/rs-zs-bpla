#ifndef EVT_PRE_20_DUAL_SIM_GPIO_H
#define EVT_PRE_20_DUAL_SIM_GPIO_H

#include "evt_pre_20_board_pins.h"
#include "zs_dual_sim.h"

#include <stdbool.h>
#include <stdint.h>

#define EVT_PRE_20_PWRKEY_ON_PULSE_MS 700u
#define EVT_PRE_20_PWRKEY_FALLBACK_PULSE_MS 1000u

typedef bool (*evt_pre_20_gpio_write_fn)(void *ctx,
                                          evt_pre_20_pin_id_t pin,
                                          bool high);
typedef bool (*evt_pre_20_gpio_read_fn)(void *ctx,
                                         evt_pre_20_pin_id_t pin,
                                         bool *high);

/*
 * U13_EN_N is not routed to an MCU GPIO in Rev.A. A fixture may provide this
 * callback during qualification. Runtime without a fixture can prove only the
 * SIM_MUX_EN command/read-back and the controlled pull-up/open-collector
 * design assumption; physical High-Z evidence remains an EVT release gate.
 */
typedef bool (*evt_pre_20_u13_enable_n_read_fn)(void *ctx, bool *high);

typedef enum {
  EVT_PRE_20_DUAL_SIM_IO_FAILED = 0,
  EVT_PRE_20_DUAL_SIM_IO_WAITING,
  EVT_PRE_20_DUAL_SIM_IO_COMPLETE_LOGICAL,
  EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL
} evt_pre_20_dual_sim_io_result_t;

typedef struct {
  void *ctx;
  evt_pre_20_gpio_write_fn write;
  evt_pre_20_gpio_read_fn read;
  evt_pre_20_u13_enable_n_read_fn read_u13_enable_n;
  bool fallback_pulse_active;
  uint32_t fallback_pulse_started_ms;
  bool modem_off_observed;
  bool mux_disabled_verified;
  bool selected_slot_known;
  zs_dual_sim_slot_t selected_slot;
  bool power_good_tracking;
  uint32_t power_good_high_since_ms;
  bool power_good_stable;
} evt_pre_20_dual_sim_gpio_t;

bool evt_pre_20_dual_sim_gpio_init(
    evt_pre_20_dual_sim_gpio_t *binding,
    void *ctx,
    evt_pre_20_gpio_write_fn write,
    evt_pre_20_gpio_read_fn read,
    evt_pre_20_u13_enable_n_read_fn read_u13_enable_n);

bool evt_pre_20_dual_sim_gpio_sample_presence(
    evt_pre_20_dual_sim_gpio_t *binding,
    zs_dual_sim_t *controller,
    uint32_t now_ms);
bool evt_pre_20_dual_sim_gpio_read_cell_status(
    evt_pre_20_dual_sim_gpio_t *binding,
    bool *high);

evt_pre_20_dual_sim_io_result_t
evt_pre_20_dual_sim_gpio_drive_recovery_fallback(
    evt_pre_20_dual_sim_gpio_t *binding,
    bool graceful_shutdown_unavailable,
    uint32_t now_ms);
bool evt_pre_20_dual_sim_gpio_verify_modem_off(
    evt_pre_20_dual_sim_gpio_t *binding);
bool evt_pre_20_dual_sim_gpio_disable_mux(
    evt_pre_20_dual_sim_gpio_t *binding);
evt_pre_20_dual_sim_io_result_t evt_pre_20_dual_sim_gpio_verify_mux_disabled(
    evt_pre_20_dual_sim_gpio_t *binding);
bool evt_pre_20_dual_sim_gpio_disable_modem_rail(
    evt_pre_20_dual_sim_gpio_t *binding);
bool evt_pre_20_dual_sim_gpio_select_slot(
    evt_pre_20_dual_sim_gpio_t *binding,
    zs_dual_sim_slot_t slot);
bool evt_pre_20_dual_sim_gpio_enable_modem_rail(
    evt_pre_20_dual_sim_gpio_t *binding);
evt_pre_20_dual_sim_io_result_t evt_pre_20_dual_sim_gpio_check_power_good(
    evt_pre_20_dual_sim_gpio_t *binding,
    uint32_t now_ms);
bool evt_pre_20_dual_sim_gpio_enable_mux(
    evt_pre_20_dual_sim_gpio_t *binding);
evt_pre_20_dual_sim_io_result_t evt_pre_20_dual_sim_gpio_verify_mux_enabled(
    evt_pre_20_dual_sim_gpio_t *binding);
bool evt_pre_20_dual_sim_gpio_write_pwrkey(
    evt_pre_20_dual_sim_gpio_t *binding,
    bool asserted);

#endif
