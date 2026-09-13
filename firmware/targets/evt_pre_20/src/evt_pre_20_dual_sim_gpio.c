#include "evt_pre_20_dual_sim_gpio.h"

#include <string.h>

static bool read_level(evt_pre_20_dual_sim_gpio_t *binding,
                       evt_pre_20_pin_id_t pin,
                       bool expected) {
  bool actual = false;
  return binding && binding->read && binding->read(binding->ctx, pin, &actual) &&
         actual == expected;
}

static bool mux_command_is(evt_pre_20_dual_sim_gpio_t *binding, bool enabled) {
  return read_level(binding, EVT_PRE_20_PIN_SIM_MUX_EN, enabled);
}

static evt_pre_20_dual_sim_io_result_t verify_u13_enable_n(
    evt_pre_20_dual_sim_gpio_t *binding, bool expected_high) {
  bool actual = false;
  if (!binding || !binding->read_u13_enable_n)
    return EVT_PRE_20_DUAL_SIM_IO_COMPLETE_LOGICAL;
  if (!binding->read_u13_enable_n(binding->ctx, &actual) ||
      actual != expected_high)
    return EVT_PRE_20_DUAL_SIM_IO_FAILED;
  return EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL;
}

bool evt_pre_20_dual_sim_gpio_init(
    evt_pre_20_dual_sim_gpio_t *binding,
    void *ctx,
    evt_pre_20_gpio_write_fn write,
    evt_pre_20_gpio_read_fn read,
    evt_pre_20_u13_enable_n_read_fn read_u13_enable_n) {
  if (!binding || !write || !read) return false;
  memset(binding, 0, sizeof(*binding));
  binding->ctx = ctx;
  binding->write = write;
  binding->read = read;
  binding->read_u13_enable_n = read_u13_enable_n;
  binding->selected_slot = ZS_DUAL_SIM_SLOT_NONE;
  return true;
}

bool evt_pre_20_dual_sim_gpio_sample_presence(
    evt_pre_20_dual_sim_gpio_t *binding,
    zs_dual_sim_t *controller,
    uint32_t now_ms) {
  bool slot_1_present = false;
  bool slot_2_present = false;
  if (!binding || !controller ||
      !binding->read(binding->ctx, EVT_PRE_20_PIN_SIM1_DET,
                     &slot_1_present) ||
      !binding->read(binding->ctx, EVT_PRE_20_PIN_SIM2_DET,
                     &slot_2_present))
    return false;
  return zs_dual_sim_update_presence(controller, ZS_DUAL_SIM_SLOT_1,
                                     slot_1_present, now_ms) &&
         zs_dual_sim_update_presence(controller, ZS_DUAL_SIM_SLOT_2,
                                     slot_2_present, now_ms);
}

bool evt_pre_20_dual_sim_gpio_read_cell_status(
    evt_pre_20_dual_sim_gpio_t *binding,
    bool *high) {
  return binding && high && binding->read &&
         binding->read(binding->ctx, EVT_PRE_20_PIN_CELL_STATUS, high);
}

evt_pre_20_dual_sim_io_result_t
evt_pre_20_dual_sim_gpio_drive_recovery_fallback(
    evt_pre_20_dual_sim_gpio_t *binding,
    bool graceful_shutdown_unavailable,
    uint32_t now_ms) {
  bool cell_status_high = false;
  if (!evt_pre_20_dual_sim_gpio_read_cell_status(binding, &cell_status_high))
    return EVT_PRE_20_DUAL_SIM_IO_FAILED;
  if (!cell_status_high) {
    if (binding->fallback_pulse_active &&
        !binding->write(binding->ctx, EVT_PRE_20_PIN_CELL_PWRKEY_CMD, false))
      return EVT_PRE_20_DUAL_SIM_IO_FAILED;
    binding->fallback_pulse_active = false;
    binding->modem_off_observed = true;
    return EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL;
  }
  if (!graceful_shutdown_unavailable)
    return EVT_PRE_20_DUAL_SIM_IO_WAITING;
  if (!binding->fallback_pulse_active) {
    if (!binding->write(binding->ctx, EVT_PRE_20_PIN_CELL_PWRKEY_CMD, true))
      return EVT_PRE_20_DUAL_SIM_IO_FAILED;
    binding->fallback_pulse_active = true;
    binding->fallback_pulse_started_ms = now_ms;
    return EVT_PRE_20_DUAL_SIM_IO_WAITING;
  }
  if ((uint32_t)(now_ms - binding->fallback_pulse_started_ms) <
      EVT_PRE_20_PWRKEY_FALLBACK_PULSE_MS)
    return EVT_PRE_20_DUAL_SIM_IO_WAITING;
  if (!binding->write(binding->ctx, EVT_PRE_20_PIN_CELL_PWRKEY_CMD, false))
    return EVT_PRE_20_DUAL_SIM_IO_FAILED;
  binding->fallback_pulse_active = false;
  return EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL;
}

bool evt_pre_20_dual_sim_gpio_verify_modem_off(
    evt_pre_20_dual_sim_gpio_t *binding) {
  if (!read_level(binding, EVT_PRE_20_PIN_CELL_STATUS, false)) return false;
  binding->modem_off_observed = true;
  return true;
}

bool evt_pre_20_dual_sim_gpio_disable_mux(
    evt_pre_20_dual_sim_gpio_t *binding) {
  if (!binding || !binding->modem_off_observed ||
      !read_level(binding, EVT_PRE_20_PIN_CELL_STATUS, false) ||
      !binding->write(binding->ctx, EVT_PRE_20_PIN_SIM_MUX_EN, false))
    return false;
  binding->mux_disabled_verified = false;
  binding->power_good_stable = false;
  return true;
}

evt_pre_20_dual_sim_io_result_t evt_pre_20_dual_sim_gpio_verify_mux_disabled(
    evt_pre_20_dual_sim_gpio_t *binding) {
  evt_pre_20_dual_sim_io_result_t result;
  if (!mux_command_is(binding, false))
    return EVT_PRE_20_DUAL_SIM_IO_FAILED;
  result = verify_u13_enable_n(binding, true);
  if (result == EVT_PRE_20_DUAL_SIM_IO_FAILED) return result;
  binding->mux_disabled_verified = true;
  return result;
}

bool evt_pre_20_dual_sim_gpio_disable_modem_rail(
    evt_pre_20_dual_sim_gpio_t *binding) {
  if (!binding || !binding->modem_off_observed ||
      !binding->mux_disabled_verified ||
      !read_level(binding, EVT_PRE_20_PIN_CELL_STATUS, false) ||
      !mux_command_is(binding, false))
    return false;
  if (binding->read_u13_enable_n &&
      verify_u13_enable_n(binding, true) !=
          EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL)
    return false;
  if (!binding->write(binding->ctx, EVT_PRE_20_PIN_EN_MODEM, false))
    return false;
  binding->selected_slot_known = false;
  binding->selected_slot = ZS_DUAL_SIM_SLOT_NONE;
  binding->power_good_tracking = false;
  binding->power_good_stable = false;
  return true;
}

bool evt_pre_20_dual_sim_gpio_select_slot(
    evt_pre_20_dual_sim_gpio_t *binding,
    zs_dual_sim_slot_t slot) {
  bool select_high;
  if (!binding ||
      (slot != ZS_DUAL_SIM_SLOT_1 && slot != ZS_DUAL_SIM_SLOT_2) ||
      !read_level(binding, EVT_PRE_20_PIN_EN_MODEM, false) ||
      !read_level(binding, EVT_PRE_20_PIN_CELL_STATUS, false) ||
      !mux_command_is(binding, false))
    return false;
  select_high = slot == ZS_DUAL_SIM_SLOT_2;
  if (!binding->write(binding->ctx, EVT_PRE_20_PIN_SIM_MUX_SEL, select_high))
    return false;
  binding->selected_slot_known = true;
  binding->selected_slot = slot;
  return true;
}

bool evt_pre_20_dual_sim_gpio_enable_modem_rail(
    evt_pre_20_dual_sim_gpio_t *binding) {
  if (!binding || !binding->selected_slot_known ||
      !read_level(binding, EVT_PRE_20_PIN_EN_MODEM, false) ||
      !read_level(binding, EVT_PRE_20_PIN_CELL_STATUS, false) ||
      !read_level(binding, EVT_PRE_20_PIN_SIM_MUX_SEL,
                  binding->selected_slot == ZS_DUAL_SIM_SLOT_2) ||
      !mux_command_is(binding, false) ||
      !binding->write(binding->ctx, EVT_PRE_20_PIN_EN_MODEM, true))
    return false;
  binding->modem_off_observed = false;
  binding->power_good_tracking = false;
  binding->power_good_stable = false;
  return true;
}

evt_pre_20_dual_sim_io_result_t evt_pre_20_dual_sim_gpio_check_power_good(
    evt_pre_20_dual_sim_gpio_t *binding,
    uint32_t now_ms) {
  if (!binding || !read_level(binding, EVT_PRE_20_PIN_EN_MODEM, true))
    return EVT_PRE_20_DUAL_SIM_IO_FAILED;
  if (!read_level(binding, EVT_PRE_20_PIN_PWR_GOOD, true)) {
    binding->power_good_tracking = false;
    binding->power_good_stable = false;
    return EVT_PRE_20_DUAL_SIM_IO_WAITING;
  }
  if (!binding->power_good_tracking) {
    binding->power_good_tracking = true;
    binding->power_good_high_since_ms = now_ms;
    return EVT_PRE_20_DUAL_SIM_IO_WAITING;
  }
  if ((uint32_t)(now_ms - binding->power_good_high_since_ms) <
      ZS_DUAL_SIM_POWER_GOOD_STABLE_MS)
    return EVT_PRE_20_DUAL_SIM_IO_WAITING;
  binding->power_good_stable = true;
  return EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL;
}

bool evt_pre_20_dual_sim_gpio_enable_mux(
    evt_pre_20_dual_sim_gpio_t *binding) {
  if (!binding || !binding->power_good_stable ||
      !read_level(binding, EVT_PRE_20_PIN_EN_MODEM, true) ||
      !read_level(binding, EVT_PRE_20_PIN_PWR_GOOD, true) ||
      !binding->write(binding->ctx, EVT_PRE_20_PIN_SIM_MUX_EN, true))
    return false;
  binding->mux_disabled_verified = false;
  return true;
}

evt_pre_20_dual_sim_io_result_t evt_pre_20_dual_sim_gpio_verify_mux_enabled(
    evt_pre_20_dual_sim_gpio_t *binding) {
  if (!binding || !binding->power_good_stable ||
      !read_level(binding, EVT_PRE_20_PIN_EN_MODEM, true) ||
      !read_level(binding, EVT_PRE_20_PIN_PWR_GOOD, true) ||
      !mux_command_is(binding, true))
    return EVT_PRE_20_DUAL_SIM_IO_FAILED;
  return verify_u13_enable_n(binding, false);
}

bool evt_pre_20_dual_sim_gpio_write_pwrkey(
    evt_pre_20_dual_sim_gpio_t *binding,
    bool asserted) {
  if (!binding) return false;
  if (asserted &&
      (!binding->power_good_stable ||
       !read_level(binding, EVT_PRE_20_PIN_EN_MODEM, true) ||
       !read_level(binding, EVT_PRE_20_PIN_PWR_GOOD, true) ||
       !mux_command_is(binding, true)))
    return false;
  if (asserted && binding->read_u13_enable_n &&
      verify_u13_enable_n(binding, false) !=
          EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL)
    return false;
  return binding->write(binding->ctx, EVT_PRE_20_PIN_CELL_PWRKEY_CMD,
                        asserted);
}
