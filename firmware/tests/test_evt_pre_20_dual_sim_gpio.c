#include "evt_pre_20_dual_sim_gpio.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define SLOT1_ICCID "89701012345678901234"
#define SLOT2_ICCID "89702012345678901234"
#define EVENT_CAPACITY 64u

typedef struct {
  evt_pre_20_pin_id_t pin;
  bool high;
} gpio_event_t;

typedef struct {
  bool level[EVT_PRE_20_PIN_COUNT];
  bool u13_enable_n_high;
  bool u13_read_ok;
  gpio_event_t events[EVENT_CAPACITY];
  size_t event_count;
} mock_gpio_t;

static bool gpio_write(void *ctx, evt_pre_20_pin_id_t pin, bool high) {
  mock_gpio_t *mock = ctx;
  if (!mock || pin >= EVT_PRE_20_PIN_COUNT ||
      mock->event_count >= EVENT_CAPACITY)
    return false;
  mock->level[pin] = high;
  if (pin == EVT_PRE_20_PIN_SIM_MUX_EN)
    mock->u13_enable_n_high = !high;
  mock->events[mock->event_count].pin = pin;
  mock->events[mock->event_count].high = high;
  ++mock->event_count;
  return true;
}

static bool gpio_read(void *ctx, evt_pre_20_pin_id_t pin, bool *high) {
  mock_gpio_t *mock = ctx;
  if (!mock || !high || pin >= EVT_PRE_20_PIN_COUNT) return false;
  *high = mock->level[pin];
  return true;
}

static bool u13_enable_n_read(void *ctx, bool *high) {
  mock_gpio_t *mock = ctx;
  if (!mock || !high || !mock->u13_read_ok) return false;
  *high = mock->u13_enable_n_high;
  return true;
}

static void assert_pin(evt_pre_20_pin_id_t id,
                       const char *net,
                       char port,
                       uint8_t gpio_pin,
                       uint8_t package_pin,
                       evt_pre_20_pin_direction_t direction) {
  const evt_pre_20_pin_contract_t *pin = &evt_pre_20_pin_contract[id];
  assert(strcmp(pin->net, net) == 0);
  assert(pin->gpio_port == port);
  assert(pin->gpio_pin == gpio_pin);
  assert(pin->lqfp100_pin == package_pin);
  assert(pin->direction == direction);
}

static void assert_event(const mock_gpio_t *mock,
                         size_t index,
                         evt_pre_20_pin_id_t pin,
                         bool high) {
  assert(index < mock->event_count);
  assert(mock->events[index].pin == pin);
  assert(mock->events[index].high == high);
}

static evt_pre_20_dual_sim_gpio_t binding(mock_gpio_t *mock,
                                           bool with_u13_fixture) {
  evt_pre_20_dual_sim_gpio_t result;
  assert(evt_pre_20_dual_sim_gpio_init(
      &result, mock, gpio_write, gpio_read,
      with_u13_fixture ? u13_enable_n_read : NULL));
  return result;
}

static void test_exact_rev_a_mapping_and_presence(void) {
  zs_dual_sim_t controller;
  mock_gpio_t mock = {0};
  evt_pre_20_dual_sim_gpio_t io = binding(&mock, true);

  assert_pin(EVT_PRE_20_PIN_CELL_PWRKEY_CMD, "CELL_PWRKEY_CMD", 'D', 11u,
             58u, EVT_PRE_20_DIRECTION_OUT);
  assert_pin(EVT_PRE_20_PIN_CELL_STATUS, "CELL_STATUS", 'D', 13u, 60u,
             EVT_PRE_20_DIRECTION_IN);
  assert_pin(EVT_PRE_20_PIN_SIM_MUX_SEL, "SIM_MUX_SEL", 'E', 0u, 97u,
             EVT_PRE_20_DIRECTION_OUT);
  assert_pin(EVT_PRE_20_PIN_SIM_MUX_EN, "SIM_MUX_EN", 'E', 2u, 1u,
             EVT_PRE_20_DIRECTION_OUT);
  assert_pin(EVT_PRE_20_PIN_SIM1_DET, "SIM1_DET", 'E', 3u, 2u,
             EVT_PRE_20_DIRECTION_IN);
  assert_pin(EVT_PRE_20_PIN_SIM2_DET, "SIM2_DET", 'E', 5u, 4u,
             EVT_PRE_20_DIRECTION_IN);
  assert_pin(EVT_PRE_20_PIN_PWR_GOOD, "PWR_GOOD", 'D', 0u, 81u,
             EVT_PRE_20_DIRECTION_IN);
  assert_pin(EVT_PRE_20_PIN_EN_MODEM, "EN_MODEM", 'D', 4u, 85u,
             EVT_PRE_20_DIRECTION_OUT);

  assert(zs_dual_sim_init(&controller, SLOT1_ICCID, SLOT2_ICCID));
  mock.level[EVT_PRE_20_PIN_SIM1_DET] = true;
  mock.level[EVT_PRE_20_PIN_SIM2_DET] = true;
  assert(evt_pre_20_dual_sim_gpio_sample_presence(&io, &controller, 0u));
  assert(evt_pre_20_dual_sim_gpio_sample_presence(
      &io, &controller, ZS_DUAL_SIM_DEBOUNCE_MS));
  assert(controller.presence[0].stable_present);
  assert(controller.presence[1].stable_present);
}

static void test_safe_recovery_and_power_on_order(void) {
  mock_gpio_t mock = {0};
  evt_pre_20_dual_sim_gpio_t io = binding(&mock, true);
  evt_pre_20_dual_sim_io_result_t result;

  mock.u13_read_ok = true;
  mock.level[EVT_PRE_20_PIN_CELL_STATUS] = true;
  mock.level[EVT_PRE_20_PIN_SIM_MUX_EN] = true;
  mock.level[EVT_PRE_20_PIN_EN_MODEM] = true;
  mock.level[EVT_PRE_20_PIN_PWR_GOOD] = true;
  mock.u13_enable_n_high = false;

  result = evt_pre_20_dual_sim_gpio_drive_recovery_fallback(
      &io, false, 100u);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_WAITING);
  assert(mock.event_count == 0u);
  assert(!evt_pre_20_dual_sim_gpio_disable_mux(&io));
  assert(!evt_pre_20_dual_sim_gpio_disable_modem_rail(&io));

  result = evt_pre_20_dual_sim_gpio_drive_recovery_fallback(
      &io, true, 101u);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_WAITING);
  assert_event(&mock, 0u, EVT_PRE_20_PIN_CELL_PWRKEY_CMD, true);
  result = evt_pre_20_dual_sim_gpio_drive_recovery_fallback(
      &io, true, 1100u);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_WAITING);
  result = evt_pre_20_dual_sim_gpio_drive_recovery_fallback(
      &io, true, 1101u);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL);
  assert_event(&mock, 1u, EVT_PRE_20_PIN_CELL_PWRKEY_CMD, false);

  assert(!evt_pre_20_dual_sim_gpio_verify_modem_off(&io));
  mock.level[EVT_PRE_20_PIN_CELL_STATUS] = false;
  assert(evt_pre_20_dual_sim_gpio_verify_modem_off(&io));
  mock.level[EVT_PRE_20_PIN_CELL_STATUS] = true;
  assert(!evt_pre_20_dual_sim_gpio_disable_mux(&io));
  mock.level[EVT_PRE_20_PIN_CELL_STATUS] = false;
  assert(evt_pre_20_dual_sim_gpio_disable_mux(&io));
  assert_event(&mock, 2u, EVT_PRE_20_PIN_SIM_MUX_EN, false);
  result = evt_pre_20_dual_sim_gpio_verify_mux_disabled(&io);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL);
  assert(evt_pre_20_dual_sim_gpio_disable_modem_rail(&io));
  assert_event(&mock, 3u, EVT_PRE_20_PIN_EN_MODEM, false);

  assert(evt_pre_20_dual_sim_gpio_select_slot(&io,
                                               ZS_DUAL_SIM_SLOT_2));
  assert_event(&mock, 4u, EVT_PRE_20_PIN_SIM_MUX_SEL, true);
  assert(evt_pre_20_dual_sim_gpio_enable_modem_rail(&io));
  assert_event(&mock, 5u, EVT_PRE_20_PIN_EN_MODEM, true);
  assert(!evt_pre_20_dual_sim_gpio_write_pwrkey(&io, true));

  result = evt_pre_20_dual_sim_gpio_check_power_good(&io, 2000u);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_WAITING);
  result = evt_pre_20_dual_sim_gpio_check_power_good(&io, 2029u);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_WAITING);
  mock.level[EVT_PRE_20_PIN_PWR_GOOD] = false;
  result = evt_pre_20_dual_sim_gpio_check_power_good(&io, 2030u);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_WAITING);
  mock.level[EVT_PRE_20_PIN_PWR_GOOD] = true;
  result = evt_pre_20_dual_sim_gpio_check_power_good(&io, 2031u);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_WAITING);
  result = evt_pre_20_dual_sim_gpio_check_power_good(&io, 2060u);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_WAITING);
  result = evt_pre_20_dual_sim_gpio_check_power_good(&io, 2061u);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL);

  assert(evt_pre_20_dual_sim_gpio_enable_mux(&io));
  assert_event(&mock, 6u, EVT_PRE_20_PIN_SIM_MUX_EN, true);
  result = evt_pre_20_dual_sim_gpio_verify_mux_enabled(&io);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL);
  assert(evt_pre_20_dual_sim_gpio_write_pwrkey(&io, true));
  assert_event(&mock, 7u, EVT_PRE_20_PIN_CELL_PWRKEY_CMD, true);
  assert(evt_pre_20_dual_sim_gpio_write_pwrkey(&io, false));
  assert_event(&mock, 8u, EVT_PRE_20_PIN_CELL_PWRKEY_CMD, false);
}

static void test_fail_closed_readback_and_logical_only_boundary(void) {
  mock_gpio_t mock = {0};
  evt_pre_20_dual_sim_gpio_t strict_io = binding(&mock, true);
  evt_pre_20_dual_sim_gpio_t runtime_io;
  evt_pre_20_dual_sim_io_result_t result;

  mock.level[EVT_PRE_20_PIN_CELL_STATUS] = false;
  mock.level[EVT_PRE_20_PIN_SIM_MUX_EN] = false;
  mock.level[EVT_PRE_20_PIN_EN_MODEM] = false;
  mock.u13_read_ok = true;
  mock.u13_enable_n_high = false;
  assert(evt_pre_20_dual_sim_gpio_verify_modem_off(&strict_io));
  assert(evt_pre_20_dual_sim_gpio_disable_mux(&strict_io));
  mock.u13_enable_n_high = false;
  result = evt_pre_20_dual_sim_gpio_verify_mux_disabled(&strict_io);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_FAILED);
  assert(!evt_pre_20_dual_sim_gpio_disable_modem_rail(&strict_io));

  runtime_io = binding(&mock, false);
  assert(evt_pre_20_dual_sim_gpio_verify_modem_off(&runtime_io));
  assert(evt_pre_20_dual_sim_gpio_disable_mux(&runtime_io));
  result = evt_pre_20_dual_sim_gpio_verify_mux_disabled(&runtime_io);
  assert(result == EVT_PRE_20_DUAL_SIM_IO_COMPLETE_LOGICAL);
  assert(evt_pre_20_dual_sim_gpio_disable_modem_rail(&runtime_io));
}

int main(void) {
  test_exact_rev_a_mapping_and_presence();
  test_safe_recovery_and_power_on_order();
  test_fail_closed_readback_and_logical_only_boundary();
  puts("EVT-PRE-20 dual-SIM GPIO binding tests passed");
  return 0;
}
