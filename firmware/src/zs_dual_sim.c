#include "zs_dual_sim.h"

#include <string.h>

#define ICCID_MIN_DIGITS 18u
#define ICCID_MAX_DIGITS (ZS_DUAL_SIM_ICCID_CAPACITY - 1u)

static bool valid_slot(zs_dual_sim_slot_t slot) {
  return slot == ZS_DUAL_SIM_SLOT_1 || slot == ZS_DUAL_SIM_SLOT_2;
}

static size_t slot_index(zs_dual_sim_slot_t slot) {
  return (size_t)slot - 1u;
}

static bool valid_iccid(const char *iccid) {
  size_t length = 0u;
  if (!iccid) return false;
  while (iccid[length] != '\0') {
    if (iccid[length] < '0' || iccid[length] > '9' || length >= ICCID_MAX_DIGITS)
      return false;
    ++length;
  }
  return length >= ICCID_MIN_DIGITS;
}

static bool valid_failure(zs_dual_sim_failure_t failure) {
  return failure >= ZS_DUAL_SIM_FAILURE_ATTACH_TIMEOUT &&
         failure <= ZS_DUAL_SIM_FAILURE_SUSTAINED_LINK_LOSS;
}

static bool target_available(const zs_dual_sim_t *controller,
                             zs_dual_sim_slot_t slot) {
  return valid_slot(slot) && controller->presence[slot_index(slot)].stable_present;
}

static void need_safe_off(zs_dual_sim_t *controller) {
  controller->state = ZS_DUAL_SIM_STATE_NEEDS_SAFE_OFF;
  controller->active_slot = ZS_DUAL_SIM_SLOT_NONE;
  controller->pending_slot = ZS_DUAL_SIM_SLOT_NONE;
  controller->active_profile = 0u;
  controller->pending_profile = 0u;
  controller->active_known = false;
  controller->switch_from_active = false;
}

static void begin_switch(zs_dual_sim_t *controller,
                         zs_dual_sim_slot_t target_slot,
                         uint8_t target_profile) {
  controller->pending_slot = target_slot;
  controller->pending_profile = target_profile;
  controller->switch_from_active = true;
  controller->state = ZS_DUAL_SIM_STATE_RECORDING_SWITCH_INTENT;
}

static zs_dual_sim_request_result_t validate_target(
    const zs_dual_sim_t *controller, zs_dual_sim_slot_t target_slot,
    uint8_t target_profile) {
  if (!valid_slot(target_slot)) return ZS_DUAL_SIM_REQUEST_REJECTED_SLOT;
  if (target_profile >= ZS_DUAL_SIM_MAX_PROFILES)
    return ZS_DUAL_SIM_REQUEST_REJECTED_PROFILE;
  if (!target_available(controller, target_slot))
    return ZS_DUAL_SIM_REQUEST_REJECTED_PRESENCE;
  return ZS_DUAL_SIM_REQUEST_ACCEPTED;
}

static zs_dual_sim_request_result_t validate_active_switch(
    const zs_dual_sim_t *controller, zs_dual_sim_slot_t target_slot,
    uint8_t target_profile, uint32_t now_ms) {
  zs_dual_sim_request_result_t result;
  if (!controller || controller->state != ZS_DUAL_SIM_STATE_ACTIVE ||
      !controller->active_known)
    return ZS_DUAL_SIM_REQUEST_REJECTED_STATE;
  result = validate_target(controller, target_slot, target_profile);
  if (result != ZS_DUAL_SIM_REQUEST_ACCEPTED) return result;
  if (target_slot == controller->active_slot)
    return ZS_DUAL_SIM_REQUEST_REJECTED_SAME_SLOT;
  if (!controller->hold_started ||
      (uint32_t)(now_ms - controller->last_activation_ms) <
          ZS_DUAL_SIM_MIN_HOLD_MS)
    return ZS_DUAL_SIM_REQUEST_REJECTED_HOLD;
  return ZS_DUAL_SIM_REQUEST_ACCEPTED;
}

bool zs_dual_sim_init(zs_dual_sim_t *controller,
                      const char *slot_1_expected_iccid,
                      const char *slot_2_expected_iccid) {
  if (!controller || !valid_iccid(slot_1_expected_iccid) ||
      !valid_iccid(slot_2_expected_iccid) ||
      strcmp(slot_1_expected_iccid, slot_2_expected_iccid) == 0)
    return false;
  memset(controller, 0, sizeof(*controller));
  memcpy(controller->expected_iccid[0], slot_1_expected_iccid,
         strlen(slot_1_expected_iccid) + 1u);
  memcpy(controller->expected_iccid[1], slot_2_expected_iccid,
         strlen(slot_2_expected_iccid) + 1u);
  controller->state = ZS_DUAL_SIM_STATE_NEEDS_SAFE_OFF;
  return true;
}

bool zs_dual_sim_update_presence(zs_dual_sim_t *controller,
                                 zs_dual_sim_slot_t slot,
                                 bool raw_present,
                                 uint32_t now_ms) {
  zs_dual_sim_presence_t *presence;
  if (!controller || !valid_slot(slot)) return false;
  presence = &controller->presence[slot_index(slot)];
  if (!presence->initialized || presence->raw_present != raw_present) {
    presence->initialized = true;
    presence->raw_present = raw_present;
    presence->raw_since_ms = now_ms;
    return true;
  }
  if ((uint32_t)(now_ms - presence->raw_since_ms) >= ZS_DUAL_SIM_DEBOUNCE_MS &&
      presence->stable_present != raw_present) {
    presence->stable_present = raw_present;
    if (!raw_present &&
        ((controller->active_known && controller->active_slot == slot) ||
         controller->pending_slot == slot))
      need_safe_off(controller);
  }
  return true;
}

zs_dual_sim_request_result_t zs_dual_sim_request_start(
    zs_dual_sim_t *controller, zs_dual_sim_slot_t target_slot,
    uint8_t target_profile) {
  zs_dual_sim_request_result_t result;
  if (!controller || controller->state != ZS_DUAL_SIM_STATE_SAFE_OFF)
    return ZS_DUAL_SIM_REQUEST_REJECTED_STATE;
  result = validate_target(controller, target_slot, target_profile);
  if (result != ZS_DUAL_SIM_REQUEST_ACCEPTED) return result;
  controller->pending_slot = target_slot;
  controller->pending_profile = target_profile;
  controller->switch_from_active = false;
  controller->state = ZS_DUAL_SIM_STATE_RECORDING_SWITCH_INTENT;
  return ZS_DUAL_SIM_REQUEST_ACCEPTED;
}

zs_dual_sim_request_result_t zs_dual_sim_request_manual_switch(
    zs_dual_sim_t *controller, zs_dual_sim_slot_t target_slot,
    uint8_t target_profile, bool authenticated, uint32_t now_ms) {
  zs_dual_sim_request_result_t result;
  if (!authenticated) return ZS_DUAL_SIM_REQUEST_REJECTED_AUTH;
  result = validate_active_switch(controller, target_slot, target_profile, now_ms);
  if (result != ZS_DUAL_SIM_REQUEST_ACCEPTED) return result;
  begin_switch(controller, target_slot, target_profile);
  return ZS_DUAL_SIM_REQUEST_ACCEPTED;
}

zs_dual_sim_request_result_t zs_dual_sim_report_failure(
    zs_dual_sim_t *controller, zs_dual_sim_failure_t failure,
    zs_dual_sim_slot_t alternate_slot, uint8_t alternate_profile,
    uint32_t now_ms) {
  uint8_t *attempts;
  zs_dual_sim_request_result_t result;
  if (!controller || controller->state != ZS_DUAL_SIM_STATE_ACTIVE ||
      !controller->active_known)
    return ZS_DUAL_SIM_REQUEST_REJECTED_STATE;
  if (!valid_failure(failure)) return ZS_DUAL_SIM_REQUEST_REJECTED_TRIGGER;
  attempts = &controller->attempts[slot_index(controller->active_slot)]
                                  [controller->active_profile];
  if (*attempts < ZS_DUAL_SIM_MAX_ATTEMPTS_PER_PROFILE) ++*attempts;
  if (*attempts < ZS_DUAL_SIM_MAX_ATTEMPTS_PER_PROFILE)
    return ZS_DUAL_SIM_REQUEST_RETRY_CURRENT;
  result = validate_active_switch(controller, alternate_slot, alternate_profile,
                                  now_ms);
  if (result != ZS_DUAL_SIM_REQUEST_ACCEPTED) return result;
  begin_switch(controller, alternate_slot, alternate_profile);
  return ZS_DUAL_SIM_REQUEST_ACCEPTED;
}

zs_dual_sim_action_t zs_dual_sim_next_action(const zs_dual_sim_t *controller) {
  if (!controller) return ZS_DUAL_SIM_ACTION_NONE;
  switch (controller->state) {
    case ZS_DUAL_SIM_STATE_NEEDS_SAFE_OFF:
      return ZS_DUAL_SIM_ACTION_REQUEST_MODEM_OFF_GRACEFUL_OR_FALLBACK_1000_MS;
    case ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MODEM_OFF:
      return ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF;
    case ZS_DUAL_SIM_STATE_RECOVERY_DISABLING_MUX:
      return ZS_DUAL_SIM_ACTION_DISABLE_MUX;
    case ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MUX_HIGH_Z:
      return ZS_DUAL_SIM_ACTION_VERIFY_MUX_HIGH_Z;
    case ZS_DUAL_SIM_STATE_RECOVERY_DISABLING_MODEM_RAIL:
      return ZS_DUAL_SIM_ACTION_DISABLE_MODEM_RAIL;
    case ZS_DUAL_SIM_STATE_RECORDING_SWITCH_INTENT:
      return ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT;
    case ZS_DUAL_SIM_STATE_STOPPING_TRAFFIC:
      return ZS_DUAL_SIM_ACTION_STOP_NEW_TRAFFIC;
    case ZS_DUAL_SIM_STATE_PERSISTING_QUEUE:
      return ZS_DUAL_SIM_ACTION_PERSIST_QUEUE_AND_SESSION;
    case ZS_DUAL_SIM_STATE_CLOSING_TRANSPORT:
      return ZS_DUAL_SIM_ACTION_CLOSE_TRANSPORT_AND_DETACH;
    case ZS_DUAL_SIM_STATE_POWERING_MODEM_OFF:
      return ZS_DUAL_SIM_ACTION_GRACEFUL_MODEM_OFF;
    case ZS_DUAL_SIM_STATE_VERIFYING_MODEM_OFF:
      return ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF;
    case ZS_DUAL_SIM_STATE_DISABLING_MUX:
      return ZS_DUAL_SIM_ACTION_DISABLE_MUX;
    case ZS_DUAL_SIM_STATE_VERIFYING_MUX_HIGH_Z:
      return ZS_DUAL_SIM_ACTION_VERIFY_MUX_HIGH_Z;
    case ZS_DUAL_SIM_STATE_DISABLING_MODEM_RAIL:
      return ZS_DUAL_SIM_ACTION_DISABLE_MODEM_RAIL;
    case ZS_DUAL_SIM_STATE_SELECTING_SLOT:
      return ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT;
    case ZS_DUAL_SIM_STATE_ENABLING_MODEM_RAIL:
      return ZS_DUAL_SIM_ACTION_ENABLE_MODEM_RAIL;
    case ZS_DUAL_SIM_STATE_VERIFYING_POWER_GOOD:
      return ZS_DUAL_SIM_ACTION_VERIFY_POWER_GOOD_30_MS;
    case ZS_DUAL_SIM_STATE_ENABLING_MUX:
      return ZS_DUAL_SIM_ACTION_ENABLE_MUX;
    case ZS_DUAL_SIM_STATE_VERIFYING_MUX_ENABLED:
      return ZS_DUAL_SIM_ACTION_VERIFY_MUX_ENABLED;
    case ZS_DUAL_SIM_STATE_PULSING_PWRKEY:
      return ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS;
    case ZS_DUAL_SIM_STATE_VERIFYING_MODEM_ON:
      return ZS_DUAL_SIM_ACTION_VERIFY_MODEM_ON;
    case ZS_DUAL_SIM_STATE_VERIFYING_ICCID:
      return ZS_DUAL_SIM_ACTION_READ_AND_VERIFY_ICCID;
    case ZS_DUAL_SIM_STATE_VALIDATING_LINK:
      return ZS_DUAL_SIM_ACTION_ATTACH_VALIDATE_DNS_TLS;
    case ZS_DUAL_SIM_STATE_RECORDING_SWITCH_COMMIT:
      return ZS_DUAL_SIM_ACTION_RECORD_SWITCH_COMMIT;
    case ZS_DUAL_SIM_STATE_RESUMING_QUEUE:
      return ZS_DUAL_SIM_ACTION_RESUME_PRESERVED_QUEUE;
    case ZS_DUAL_SIM_STATE_SAFE_OFF:
    case ZS_DUAL_SIM_STATE_ACTIVE:
    default:
      return ZS_DUAL_SIM_ACTION_NONE;
  }
}

bool zs_dual_sim_complete_action(zs_dual_sim_t *controller,
                                 zs_dual_sim_action_t action,
                                 bool success, uint32_t now_ms) {
  zs_dual_sim_state_t state_before;
  if (!controller || action == ZS_DUAL_SIM_ACTION_NONE ||
      action != zs_dual_sim_next_action(controller))
    return false;
  state_before = controller->state;
  if (!success) {
    if (state_before == ZS_DUAL_SIM_STATE_NEEDS_SAFE_OFF ||
        state_before == ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MODEM_OFF ||
        state_before == ZS_DUAL_SIM_STATE_RECOVERY_DISABLING_MUX ||
        state_before == ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MUX_HIGH_Z ||
        state_before == ZS_DUAL_SIM_STATE_RECOVERY_DISABLING_MODEM_RAIL)
      return false;
    need_safe_off(controller);
    return true;
  }
  switch (action) {
    case ZS_DUAL_SIM_ACTION_REQUEST_MODEM_OFF_GRACEFUL_OR_FALLBACK_1000_MS:
      controller->state = ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MODEM_OFF;
      break;
    case ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT:
      controller->state = controller->switch_from_active
                              ? ZS_DUAL_SIM_STATE_STOPPING_TRAFFIC
                              : ZS_DUAL_SIM_STATE_SELECTING_SLOT;
      break;
    case ZS_DUAL_SIM_ACTION_STOP_NEW_TRAFFIC:
      controller->state = ZS_DUAL_SIM_STATE_PERSISTING_QUEUE;
      break;
    case ZS_DUAL_SIM_ACTION_PERSIST_QUEUE_AND_SESSION:
      controller->state = ZS_DUAL_SIM_STATE_CLOSING_TRANSPORT;
      break;
    case ZS_DUAL_SIM_ACTION_CLOSE_TRANSPORT_AND_DETACH:
      controller->state = ZS_DUAL_SIM_STATE_POWERING_MODEM_OFF;
      break;
    case ZS_DUAL_SIM_ACTION_GRACEFUL_MODEM_OFF:
      controller->state = ZS_DUAL_SIM_STATE_VERIFYING_MODEM_OFF;
      break;
    case ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF:
      controller->state = state_before ==
                                  ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MODEM_OFF
                              ? ZS_DUAL_SIM_STATE_RECOVERY_DISABLING_MUX
                              : ZS_DUAL_SIM_STATE_DISABLING_MUX;
      break;
    case ZS_DUAL_SIM_ACTION_DISABLE_MUX:
      controller->state = state_before ==
                                  ZS_DUAL_SIM_STATE_RECOVERY_DISABLING_MUX
                              ? ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MUX_HIGH_Z
                              : ZS_DUAL_SIM_STATE_VERIFYING_MUX_HIGH_Z;
      break;
    case ZS_DUAL_SIM_ACTION_VERIFY_MUX_HIGH_Z:
      controller->state =
          state_before == ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MUX_HIGH_Z
              ? ZS_DUAL_SIM_STATE_RECOVERY_DISABLING_MODEM_RAIL
              : ZS_DUAL_SIM_STATE_DISABLING_MODEM_RAIL;
      break;
    case ZS_DUAL_SIM_ACTION_DISABLE_MODEM_RAIL:
      controller->state =
          state_before == ZS_DUAL_SIM_STATE_RECOVERY_DISABLING_MODEM_RAIL
              ? ZS_DUAL_SIM_STATE_SAFE_OFF
              : ZS_DUAL_SIM_STATE_SELECTING_SLOT;
      break;
    case ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT:
      controller->state = ZS_DUAL_SIM_STATE_ENABLING_MODEM_RAIL;
      break;
    case ZS_DUAL_SIM_ACTION_ENABLE_MODEM_RAIL:
      controller->modem_rail_enabled_ms = now_ms;
      controller->state = ZS_DUAL_SIM_STATE_VERIFYING_POWER_GOOD;
      break;
    case ZS_DUAL_SIM_ACTION_VERIFY_POWER_GOOD_30_MS:
      if ((uint32_t)(now_ms - controller->modem_rail_enabled_ms) <
          ZS_DUAL_SIM_POWER_GOOD_STABLE_MS)
        return false;
      controller->state = ZS_DUAL_SIM_STATE_ENABLING_MUX;
      break;
    case ZS_DUAL_SIM_ACTION_ENABLE_MUX:
      controller->state = ZS_DUAL_SIM_STATE_VERIFYING_MUX_ENABLED;
      break;
    case ZS_DUAL_SIM_ACTION_VERIFY_MUX_ENABLED:
      controller->state = ZS_DUAL_SIM_STATE_PULSING_PWRKEY;
      break;
    case ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS:
      controller->state = ZS_DUAL_SIM_STATE_VERIFYING_MODEM_ON;
      break;
    case ZS_DUAL_SIM_ACTION_VERIFY_MODEM_ON:
      controller->state = ZS_DUAL_SIM_STATE_VERIFYING_ICCID;
      break;
    case ZS_DUAL_SIM_ACTION_ATTACH_VALIDATE_DNS_TLS:
      controller->state = ZS_DUAL_SIM_STATE_RECORDING_SWITCH_COMMIT;
      break;
    case ZS_DUAL_SIM_ACTION_RECORD_SWITCH_COMMIT:
      controller->state = ZS_DUAL_SIM_STATE_RESUMING_QUEUE;
      break;
    case ZS_DUAL_SIM_ACTION_RESUME_PRESERVED_QUEUE:
      controller->active_slot = controller->pending_slot;
      controller->active_profile = controller->pending_profile;
      controller->pending_slot = ZS_DUAL_SIM_SLOT_NONE;
      controller->pending_profile = 0u;
      controller->attempts[slot_index(controller->active_slot)]
                          [controller->active_profile] = 0u;
      controller->last_activation_ms = now_ms;
      controller->hold_started = true;
      controller->active_known = true;
      controller->switch_from_active = false;
      controller->state = ZS_DUAL_SIM_STATE_ACTIVE;
      break;
    case ZS_DUAL_SIM_ACTION_READ_AND_VERIFY_ICCID:
    case ZS_DUAL_SIM_ACTION_NONE:
    default:
      return false;
  }
  return true;
}

bool zs_dual_sim_on_iccid(zs_dual_sim_t *controller, const char *full_iccid) {
  if (!controller || controller->state != ZS_DUAL_SIM_STATE_VERIFYING_ICCID ||
      !valid_slot(controller->pending_slot))
    return false;
  if (!valid_iccid(full_iccid) || strcmp(full_iccid,
             controller->expected_iccid[slot_index(controller->pending_slot)]) != 0) {
    need_safe_off(controller);
    return false;
  }
  controller->state = ZS_DUAL_SIM_STATE_VALIDATING_LINK;
  return true;
}

void zs_dual_sim_report_brownout(zs_dual_sim_t *controller) {
  if (controller) need_safe_off(controller);
}

zs_dual_sim_state_t zs_dual_sim_state(const zs_dual_sim_t *controller) {
  return controller ? controller->state : ZS_DUAL_SIM_STATE_NEEDS_SAFE_OFF;
}

zs_dual_sim_slot_t zs_dual_sim_active_slot(const zs_dual_sim_t *controller) {
  return controller && controller->state == ZS_DUAL_SIM_STATE_ACTIVE &&
                 controller->active_known
             ? controller->active_slot
             : ZS_DUAL_SIM_SLOT_NONE;
}

const char *zs_dual_sim_state_name(zs_dual_sim_state_t state) {
  static const char *const names[] = {
      "needs_safe_off",       "recovery_verifying_modem_off",
      "recovery_disabling_mux", "recovery_verifying_mux_high_z",
      "recovery_disabling_modem_rail", "safe_off", "active",
      "recording_switch_intent", "stopping_traffic", "persisting_queue",
      "closing_transport",
      "powering_modem_off",   "verifying_modem_off", "disabling_mux",
      "verifying_mux_high_z", "disabling_modem_rail", "selecting_slot",
      "enabling_modem_rail",  "verifying_power_good", "enabling_mux",
      "verifying_mux_enabled", "pulsing_pwrkey",    "verifying_modem_on",
      "verifying_iccid",      "validating_link",   "recording_switch_commit",
      "resuming_queue"};
  if ((size_t)state >= sizeof(names) / sizeof(names[0])) return "unknown";
  return names[state];
}
