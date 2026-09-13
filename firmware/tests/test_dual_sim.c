#include "zs_dual_sim.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define SLOT1_ICCID "89701012345678901234"
#define SLOT2_ICCID "89702012345678901234"

static void set_present(zs_dual_sim_t *controller, zs_dual_sim_slot_t slot,
                        uint32_t start_ms) {
  assert(zs_dual_sim_update_presence(controller, slot, true, start_ms));
  assert(zs_dual_sim_update_presence(controller, slot, true,
                                     start_ms + ZS_DUAL_SIM_DEBOUNCE_MS));
}

static void complete(zs_dual_sim_t *controller, zs_dual_sim_action_t action,
                     uint32_t now_ms) {
  zs_dual_sim_action_t actual = zs_dual_sim_next_action(controller);
  if (actual != action)
    fprintf(stderr, "unexpected action: got %u expected %u in state %s\n",
            (unsigned)actual, (unsigned)action,
            zs_dual_sim_state_name(zs_dual_sim_state(controller)));
  assert(actual == action);
  assert(zs_dual_sim_complete_action(controller, action, true, now_ms));
}

static uint32_t drive_power_on(zs_dual_sim_t *controller, uint32_t now_ms,
                               const char *iccid) {
  complete(controller, ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT, now_ms++);
  complete(controller, ZS_DUAL_SIM_ACTION_ENABLE_MODEM_RAIL, now_ms++);
  assert(!zs_dual_sim_complete_action(
      controller, ZS_DUAL_SIM_ACTION_VERIFY_POWER_GOOD_30_MS, true,
      now_ms + ZS_DUAL_SIM_POWER_GOOD_STABLE_MS - 2u));
  complete(controller, ZS_DUAL_SIM_ACTION_VERIFY_POWER_GOOD_30_MS,
           now_ms + ZS_DUAL_SIM_POWER_GOOD_STABLE_MS);
  now_ms += ZS_DUAL_SIM_POWER_GOOD_STABLE_MS + 1u;
  complete(controller, ZS_DUAL_SIM_ACTION_ENABLE_MUX, now_ms++);
  complete(controller, ZS_DUAL_SIM_ACTION_VERIFY_MUX_ENABLED, now_ms++);
  complete(controller, ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS, now_ms++);
  complete(controller, ZS_DUAL_SIM_ACTION_VERIFY_MODEM_ON, now_ms++);
  assert(zs_dual_sim_next_action(controller) ==
         ZS_DUAL_SIM_ACTION_READ_AND_VERIFY_ICCID);
  assert(zs_dual_sim_on_iccid(controller, iccid));
  complete(controller, ZS_DUAL_SIM_ACTION_ATTACH_VALIDATE_DNS_TLS, now_ms++);
  complete(controller, ZS_DUAL_SIM_ACTION_RECORD_SWITCH_COMMIT, now_ms++);
  complete(controller, ZS_DUAL_SIM_ACTION_RESUME_PRESERVED_QUEUE, now_ms++);
  return now_ms;
}

static void start_slot_1(zs_dual_sim_t *controller, uint32_t *now_ms) {
  assert(zs_dual_sim_init(controller, SLOT1_ICCID, SLOT2_ICCID));
  assert(zs_dual_sim_next_action(controller) ==
         ZS_DUAL_SIM_ACTION_APPLY_SAFE_OFF);
  set_present(controller, ZS_DUAL_SIM_SLOT_1, 0u);
  set_present(controller, ZS_DUAL_SIM_SLOT_2, 0u);
  complete(controller, ZS_DUAL_SIM_ACTION_APPLY_SAFE_OFF, 21u);
  assert(zs_dual_sim_request_start(controller, ZS_DUAL_SIM_SLOT_1, 0u) ==
         ZS_DUAL_SIM_REQUEST_ACCEPTED);
  complete(controller, ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT, 22u);
  *now_ms = drive_power_on(controller, 23u, SLOT1_ICCID);
  assert(zs_dual_sim_state(controller) == ZS_DUAL_SIM_STATE_ACTIVE);
  assert(zs_dual_sim_active_slot(controller) == ZS_DUAL_SIM_SLOT_1);
}

static void drive_safe_switch_prefix(zs_dual_sim_t *controller,
                                     uint32_t now_ms) {
  static const zs_dual_sim_action_t actions[] = {
      ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT,
      ZS_DUAL_SIM_ACTION_STOP_NEW_TRAFFIC,
      ZS_DUAL_SIM_ACTION_PERSIST_QUEUE_AND_SESSION,
      ZS_DUAL_SIM_ACTION_CLOSE_TRANSPORT_AND_DETACH,
      ZS_DUAL_SIM_ACTION_GRACEFUL_MODEM_OFF,
      ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF,
      ZS_DUAL_SIM_ACTION_DISABLE_MUX,
      ZS_DUAL_SIM_ACTION_VERIFY_MUX_HIGH_Z,
      ZS_DUAL_SIM_ACTION_DISABLE_MODEM_RAIL};
  size_t i;
  assert(zs_dual_sim_next_action(controller) == actions[0]);
  assert(!zs_dual_sim_complete_action(controller,
                                      ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT,
                                      true, now_ms));
  for (i = 0u; i < sizeof(actions) / sizeof(actions[0]); ++i)
    complete(controller, actions[i], now_ms + (uint32_t)i);
  assert(zs_dual_sim_next_action(controller) ==
         ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT);
}

static void test_boot_and_bounded_automatic_failover(void) {
  zs_dual_sim_t controller;
  uint32_t now_ms;
  uint32_t failover_ms;
  start_slot_1(&controller, &now_ms);

  assert(zs_dual_sim_report_failure(
             &controller, ZS_DUAL_SIM_FAILURE_ATTACH_TIMEOUT,
             ZS_DUAL_SIM_SLOT_2, 1u, now_ms + 1u) ==
         ZS_DUAL_SIM_REQUEST_RETRY_CURRENT);
  assert(zs_dual_sim_report_failure(
             &controller, ZS_DUAL_SIM_FAILURE_PDP,
             ZS_DUAL_SIM_SLOT_2, 1u, now_ms + 2u) ==
         ZS_DUAL_SIM_REQUEST_RETRY_CURRENT);
  assert(zs_dual_sim_report_failure(
             &controller, ZS_DUAL_SIM_FAILURE_DNS,
             ZS_DUAL_SIM_SLOT_2, 1u, now_ms + 3u) ==
         ZS_DUAL_SIM_REQUEST_REJECTED_HOLD);
  assert(zs_dual_sim_state(&controller) == ZS_DUAL_SIM_STATE_ACTIVE);

  failover_ms = controller.last_activation_ms + ZS_DUAL_SIM_MIN_HOLD_MS;
  assert(zs_dual_sim_report_failure(
             &controller, ZS_DUAL_SIM_FAILURE_TLS,
             ZS_DUAL_SIM_SLOT_2, 1u, failover_ms) ==
         ZS_DUAL_SIM_REQUEST_ACCEPTED);
  assert(controller.attempts[0][0] == ZS_DUAL_SIM_MAX_ATTEMPTS_PER_PROFILE);
  drive_safe_switch_prefix(&controller, failover_ms + 1u);
  now_ms = drive_power_on(&controller, failover_ms + 20u, SLOT2_ICCID);
  assert(zs_dual_sim_active_slot(&controller) == ZS_DUAL_SIM_SLOT_2);
  assert(controller.active_profile == 1u);
  assert(controller.attempts[1][1] == 0u);
  assert(strcmp(zs_dual_sim_state_name(zs_dual_sim_state(&controller)),
                "active") == 0);
  (void)now_ms;
}

static void test_auth_presence_and_configuration_guards(void) {
  zs_dual_sim_t controller;
  uint32_t now_ms;

  assert(!zs_dual_sim_init(NULL, SLOT1_ICCID, SLOT2_ICCID));
  assert(!zs_dual_sim_init(&controller, "1234", SLOT2_ICCID));
  assert(!zs_dual_sim_init(&controller, SLOT1_ICCID, SLOT1_ICCID));
  start_slot_1(&controller, &now_ms);

  assert(zs_dual_sim_request_manual_switch(
             &controller, ZS_DUAL_SIM_SLOT_2, 0u, false,
             controller.last_activation_ms + ZS_DUAL_SIM_MIN_HOLD_MS) ==
         ZS_DUAL_SIM_REQUEST_REJECTED_AUTH);
  assert(zs_dual_sim_request_manual_switch(
             &controller, ZS_DUAL_SIM_SLOT_1, 0u, true,
             controller.last_activation_ms + ZS_DUAL_SIM_MIN_HOLD_MS) ==
         ZS_DUAL_SIM_REQUEST_REJECTED_SAME_SLOT);
  assert(zs_dual_sim_request_manual_switch(
             &controller, ZS_DUAL_SIM_SLOT_2,
             ZS_DUAL_SIM_MAX_PROFILES, true,
             controller.last_activation_ms + ZS_DUAL_SIM_MIN_HOLD_MS) ==
         ZS_DUAL_SIM_REQUEST_REJECTED_PROFILE);
  assert(zs_dual_sim_report_failure(
             &controller, (zs_dual_sim_failure_t)99,
             ZS_DUAL_SIM_SLOT_2, 0u,
             controller.last_activation_ms + ZS_DUAL_SIM_MIN_HOLD_MS) ==
         ZS_DUAL_SIM_REQUEST_REJECTED_TRIGGER);

  assert(zs_dual_sim_update_presence(&controller, ZS_DUAL_SIM_SLOT_2, false,
                                     now_ms + 100u));
  assert(zs_dual_sim_update_presence(
      &controller, ZS_DUAL_SIM_SLOT_2, false,
      now_ms + 100u + ZS_DUAL_SIM_DEBOUNCE_MS));
  assert(zs_dual_sim_request_manual_switch(
             &controller, ZS_DUAL_SIM_SLOT_2, 0u, true,
             controller.last_activation_ms + ZS_DUAL_SIM_MIN_HOLD_MS) ==
         ZS_DUAL_SIM_REQUEST_REJECTED_PRESENCE);
}

static void test_iccid_mismatch_and_action_failure_fail_closed(void) {
  zs_dual_sim_t controller;
  uint32_t now_ms;
  uint32_t switch_ms;
  start_slot_1(&controller, &now_ms);
  switch_ms = controller.last_activation_ms + ZS_DUAL_SIM_MIN_HOLD_MS;
  assert(zs_dual_sim_request_manual_switch(
             &controller, ZS_DUAL_SIM_SLOT_2, 2u, true, switch_ms) ==
         ZS_DUAL_SIM_REQUEST_ACCEPTED);
  drive_safe_switch_prefix(&controller, switch_ms + 1u);
  complete(&controller, ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT, switch_ms + 20u);
  complete(&controller, ZS_DUAL_SIM_ACTION_ENABLE_MODEM_RAIL, switch_ms + 21u);
  complete(&controller, ZS_DUAL_SIM_ACTION_VERIFY_POWER_GOOD_30_MS,
           switch_ms + 51u);
  complete(&controller, ZS_DUAL_SIM_ACTION_ENABLE_MUX, switch_ms + 52u);
  complete(&controller, ZS_DUAL_SIM_ACTION_VERIFY_MUX_ENABLED, switch_ms + 53u);
  complete(&controller, ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS, switch_ms + 54u);
  complete(&controller, ZS_DUAL_SIM_ACTION_VERIFY_MODEM_ON, switch_ms + 55u);
  assert(!zs_dual_sim_on_iccid(&controller, SLOT1_ICCID));
  assert(zs_dual_sim_active_slot(&controller) == ZS_DUAL_SIM_SLOT_NONE);
  assert(zs_dual_sim_next_action(&controller) ==
         ZS_DUAL_SIM_ACTION_APPLY_SAFE_OFF);
  complete(&controller, ZS_DUAL_SIM_ACTION_APPLY_SAFE_OFF, switch_ms + 56u);
  assert(zs_dual_sim_state(&controller) == ZS_DUAL_SIM_STATE_SAFE_OFF);

  assert(zs_dual_sim_request_start(&controller, ZS_DUAL_SIM_SLOT_1, 0u) ==
         ZS_DUAL_SIM_REQUEST_ACCEPTED);
  complete(&controller, ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT,
           switch_ms + 57u);
  assert(zs_dual_sim_complete_action(
      &controller, ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT, false,
      switch_ms + 58u));
  assert(zs_dual_sim_next_action(&controller) ==
         ZS_DUAL_SIM_ACTION_APPLY_SAFE_OFF);
  assert(!zs_dual_sim_complete_action(
      &controller, ZS_DUAL_SIM_ACTION_APPLY_SAFE_OFF, false,
      switch_ms + 59u));
  assert(zs_dual_sim_state(&controller) ==
         ZS_DUAL_SIM_STATE_NEEDS_SAFE_OFF);
}

static void test_brownout_and_debounced_active_slot_removal(void) {
  zs_dual_sim_t controller;
  uint32_t now_ms;
  start_slot_1(&controller, &now_ms);
  zs_dual_sim_report_brownout(&controller);
  assert(zs_dual_sim_active_slot(&controller) == ZS_DUAL_SIM_SLOT_NONE);
  assert(zs_dual_sim_next_action(&controller) ==
         ZS_DUAL_SIM_ACTION_APPLY_SAFE_OFF);

  start_slot_1(&controller, &now_ms);
  assert(zs_dual_sim_update_presence(&controller, ZS_DUAL_SIM_SLOT_1, false,
                                     now_ms + 1u));
  assert(zs_dual_sim_state(&controller) == ZS_DUAL_SIM_STATE_ACTIVE);
  assert(zs_dual_sim_update_presence(
      &controller, ZS_DUAL_SIM_SLOT_1, false,
      now_ms + 1u + ZS_DUAL_SIM_DEBOUNCE_MS));
  assert(zs_dual_sim_state(&controller) ==
         ZS_DUAL_SIM_STATE_NEEDS_SAFE_OFF);
}

int main(void) {
  test_boot_and_bounded_automatic_failover();
  test_auth_presence_and_configuration_guards();
  test_iccid_mismatch_and_action_failure_fail_closed();
  test_brownout_and_debounced_active_slot_removal();
  puts("dual-SIM safe failover tests passed");
  return 0;
}
