#include "zs_dual_sim_bg95.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define SLOT1_ICCID "89701012345678901234"
#define SLOT2_ICCID "89702012345678901234"

typedef struct {
  char uart[2048];
  size_t used;
  bool pwrkey;
} mock_t;

static int uart_write(void *ctx, unsigned channel, const uint8_t *data,
                      size_t size) {
  mock_t *mock = ctx;
  (void)channel;
  if (mock->used + size >= sizeof(mock->uart)) return -1;
  memcpy(&mock->uart[mock->used], data, size);
  mock->used += size;
  mock->uart[mock->used] = '\0';
  return 0;
}

static void gpio_write(void *ctx, unsigned id, bool level) {
  mock_t *mock = ctx;
  (void)id;
  mock->pwrkey = level;
}

static zs_hal_port_t port(mock_t *mock) {
  zs_hal_port_t io = {0};
  io.ctx = mock;
  io.uart_write = uart_write;
  io.gpio_write = gpio_write;
  return io;
}

static void complete(zs_dual_sim_t *controller,
                     zs_dual_sim_action_t action, uint32_t now_ms) {
  assert(zs_dual_sim_next_action(controller) == action);
  assert(zs_dual_sim_complete_action(controller, action, true, now_ms));
}

static void make_slot_present(zs_dual_sim_t *controller,
                              zs_dual_sim_slot_t slot) {
  assert(zs_dual_sim_update_presence(controller, slot, true, 0u));
  assert(zs_dual_sim_update_presence(
      controller, slot, true, ZS_DUAL_SIM_DEBOUNCE_MS));
}

static void controller_to_pwrkey(zs_dual_sim_t *controller) {
  complete(controller, ZS_DUAL_SIM_ACTION_APPLY_SAFE_OFF, 21u);
  assert(zs_dual_sim_request_start(controller, ZS_DUAL_SIM_SLOT_1, 0u) ==
         ZS_DUAL_SIM_REQUEST_ACCEPTED);
  complete(controller, ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT, 22u);
  complete(controller, ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT, 23u);
  complete(controller, ZS_DUAL_SIM_ACTION_ENABLE_MODEM_RAIL, 24u);
  complete(controller, ZS_DUAL_SIM_ACTION_VERIFY_POWER_GOOD_30_MS, 54u);
  complete(controller, ZS_DUAL_SIM_ACTION_ENABLE_MUX, 55u);
  complete(controller, ZS_DUAL_SIM_ACTION_VERIFY_MUX_ENABLED, 56u);
}

static void establish_online_modem(zs_bg95_t *modem) {
  strcpy(modem->network_settings.iccid, SLOT1_ICCID);
  strcpy(modem->network_settings.imsi, "250011234567890");
  strcpy(modem->network_settings.apn, "network.apn");
  strcpy(modem->network_settings.local_address, "10.10.0.2");
  strcpy(modem->network_settings.gateway, "10.10.0.1");
  strcpy(modem->network_settings.primary_dns, "1.1.1.1");
  modem->network_settings.valid = true;
  modem->command_pending = false;
  modem->mqtt_connected = true;
  modem->mqtt_open = true;
  modem->state = ZS_BG95_ONLINE;
}

static void test_power_identity_link_and_shutdown_bridge(void) {
  static const zs_bg95_apn_profile_t profiles[] = {
      {"25001", "", true, true},
  };
  zs_dual_sim_t controller;
  zs_bg95_t modem;
  mock_t mock = {0};
  zs_hal_port_t io = port(&mock);
  uint32_t switch_ms;

  assert(zs_dual_sim_init(&controller, SLOT1_ICCID, SLOT2_ICCID));
  make_slot_present(&controller, ZS_DUAL_SIM_SLOT_1);
  make_slot_present(&controller, ZS_DUAL_SIM_SLOT_2);
  controller_to_pwrkey(&controller);

  zs_bg95_init(&modem, &io, 1u, 2u, NULL);
  assert(zs_bg95_configure_auto_network(&modem, profiles, 1u));
  assert(zs_dual_sim_bg95_begin_power_on(&controller, &modem, 57u));
  assert(mock.pwrkey);
  assert(!zs_dual_sim_bg95_confirm_modem_on(
      &controller, &modem, false, 757u));
  zs_bg95_tick(&modem, 757u);
  assert(!mock.pwrkey);
  assert(modem.state == ZS_BG95_AT_SYNC);
  assert(zs_dual_sim_bg95_confirm_modem_on(
      &controller, &modem, true, 758u));
  assert(!zs_dual_sim_bg95_verify_iccid(&controller, &modem));

  establish_online_modem(&modem);
  assert(zs_dual_sim_bg95_verify_iccid(&controller, &modem));
  assert(zs_dual_sim_bg95_confirm_link(&controller, &modem, 759u));
  complete(&controller, ZS_DUAL_SIM_ACTION_RECORD_SWITCH_COMMIT, 760u);
  complete(&controller, ZS_DUAL_SIM_ACTION_RESUME_PRESERVED_QUEUE, 761u);
  assert(zs_dual_sim_active_slot(&controller) == ZS_DUAL_SIM_SLOT_1);

  switch_ms = controller.last_activation_ms + ZS_DUAL_SIM_MIN_HOLD_MS;
  assert(zs_dual_sim_request_manual_switch(
             &controller, ZS_DUAL_SIM_SLOT_2, 1u, true, switch_ms) ==
         ZS_DUAL_SIM_REQUEST_ACCEPTED);
  complete(&controller, ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT, switch_ms + 1u);
  complete(&controller, ZS_DUAL_SIM_ACTION_STOP_NEW_TRAFFIC, switch_ms + 2u);
  complete(&controller, ZS_DUAL_SIM_ACTION_PERSIST_QUEUE_AND_SESSION,
           switch_ms + 3u);
  complete(&controller, ZS_DUAL_SIM_ACTION_CLOSE_TRANSPORT_AND_DETACH,
           switch_ms + 4u);
  assert(zs_dual_sim_bg95_begin_graceful_shutdown(
      &controller, &modem, switch_ms + 5u));
  assert(strstr(mock.uart, "AT+QPOWD\r\n") != NULL);
  assert(!zs_dual_sim_bg95_confirm_shutdown(
      &controller, &modem, false, switch_ms + 6u));
  zs_bg95_on_line(&modem, "NORMAL POWER DOWN", switch_ms + 7u);
  assert(zs_dual_sim_bg95_confirm_shutdown(
      &controller, &modem, true, switch_ms + 8u));
  assert(modem.state == ZS_BG95_OFF);
  assert(modem.network_settings.iccid[0] == '\0');
  assert(zs_dual_sim_next_action(&controller) ==
         ZS_DUAL_SIM_ACTION_DISABLE_MUX);
}

int main(void) {
  test_power_identity_link_and_shutdown_bridge();
  puts("dual-SIM BG95 bridge tests passed");
  return 0;
}
