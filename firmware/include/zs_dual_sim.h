#ifndef ZS_DUAL_SIM_H
#define ZS_DUAL_SIM_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_DUAL_SIM_SLOT_COUNT 2u
#define ZS_DUAL_SIM_MAX_PROFILES 8u
#define ZS_DUAL_SIM_ICCID_CAPACITY 23u
#define ZS_DUAL_SIM_DEBOUNCE_MS 20u
#define ZS_DUAL_SIM_MIN_HOLD_MS 900000u
#define ZS_DUAL_SIM_MAX_ATTEMPTS_PER_PROFILE 3u
#define ZS_DUAL_SIM_POWER_GOOD_STABLE_MS 30u

typedef enum {
  ZS_DUAL_SIM_SLOT_NONE = 0,
  ZS_DUAL_SIM_SLOT_1 = 1,
  ZS_DUAL_SIM_SLOT_2 = 2
} zs_dual_sim_slot_t;

typedef enum {
  ZS_DUAL_SIM_FAILURE_ATTACH_TIMEOUT = 0,
  ZS_DUAL_SIM_FAILURE_PDP,
  ZS_DUAL_SIM_FAILURE_DNS,
  ZS_DUAL_SIM_FAILURE_TLS,
  ZS_DUAL_SIM_FAILURE_SUSTAINED_LINK_LOSS
} zs_dual_sim_failure_t;

typedef enum {
  ZS_DUAL_SIM_STATE_NEEDS_SAFE_OFF = 0,
  ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MODEM_OFF,
  ZS_DUAL_SIM_STATE_RECOVERY_DISABLING_MUX,
  ZS_DUAL_SIM_STATE_RECOVERY_VERIFYING_MUX_HIGH_Z,
  ZS_DUAL_SIM_STATE_RECOVERY_DISABLING_MODEM_RAIL,
  ZS_DUAL_SIM_STATE_SAFE_OFF,
  ZS_DUAL_SIM_STATE_ACTIVE,
  ZS_DUAL_SIM_STATE_RECORDING_SWITCH_INTENT,
  ZS_DUAL_SIM_STATE_STOPPING_TRAFFIC,
  ZS_DUAL_SIM_STATE_PERSISTING_QUEUE,
  ZS_DUAL_SIM_STATE_CLOSING_TRANSPORT,
  ZS_DUAL_SIM_STATE_POWERING_MODEM_OFF,
  ZS_DUAL_SIM_STATE_VERIFYING_MODEM_OFF,
  ZS_DUAL_SIM_STATE_DISABLING_MUX,
  ZS_DUAL_SIM_STATE_VERIFYING_MUX_HIGH_Z,
  ZS_DUAL_SIM_STATE_DISABLING_MODEM_RAIL,
  ZS_DUAL_SIM_STATE_SELECTING_SLOT,
  ZS_DUAL_SIM_STATE_ENABLING_MODEM_RAIL,
  ZS_DUAL_SIM_STATE_VERIFYING_POWER_GOOD,
  ZS_DUAL_SIM_STATE_ENABLING_MUX,
  ZS_DUAL_SIM_STATE_VERIFYING_MUX_ENABLED,
  ZS_DUAL_SIM_STATE_PULSING_PWRKEY,
  ZS_DUAL_SIM_STATE_VERIFYING_MODEM_ON,
  ZS_DUAL_SIM_STATE_VERIFYING_ICCID,
  ZS_DUAL_SIM_STATE_VALIDATING_LINK,
  ZS_DUAL_SIM_STATE_RECORDING_SWITCH_COMMIT,
  ZS_DUAL_SIM_STATE_RESUMING_QUEUE
} zs_dual_sim_state_t;

typedef enum {
  ZS_DUAL_SIM_ACTION_NONE = 0,
  ZS_DUAL_SIM_ACTION_REQUEST_MODEM_OFF_GRACEFUL_OR_FALLBACK_1000_MS,
  ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT,
  ZS_DUAL_SIM_ACTION_STOP_NEW_TRAFFIC,
  ZS_DUAL_SIM_ACTION_PERSIST_QUEUE_AND_SESSION,
  ZS_DUAL_SIM_ACTION_CLOSE_TRANSPORT_AND_DETACH,
  ZS_DUAL_SIM_ACTION_GRACEFUL_MODEM_OFF,
  ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF,
  ZS_DUAL_SIM_ACTION_DISABLE_MUX,
  ZS_DUAL_SIM_ACTION_VERIFY_MUX_HIGH_Z,
  ZS_DUAL_SIM_ACTION_DISABLE_MODEM_RAIL,
  ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT,
  ZS_DUAL_SIM_ACTION_ENABLE_MODEM_RAIL,
  ZS_DUAL_SIM_ACTION_VERIFY_POWER_GOOD_30_MS,
  ZS_DUAL_SIM_ACTION_ENABLE_MUX,
  ZS_DUAL_SIM_ACTION_VERIFY_MUX_ENABLED,
  ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS,
  ZS_DUAL_SIM_ACTION_VERIFY_MODEM_ON,
  ZS_DUAL_SIM_ACTION_READ_AND_VERIFY_ICCID,
  ZS_DUAL_SIM_ACTION_ATTACH_VALIDATE_DNS_TLS,
  ZS_DUAL_SIM_ACTION_RECORD_SWITCH_COMMIT,
  ZS_DUAL_SIM_ACTION_RESUME_PRESERVED_QUEUE
} zs_dual_sim_action_t;

typedef enum {
  ZS_DUAL_SIM_REQUEST_ACCEPTED = 0,
  ZS_DUAL_SIM_REQUEST_RETRY_CURRENT,
  ZS_DUAL_SIM_REQUEST_REJECTED_STATE,
  ZS_DUAL_SIM_REQUEST_REJECTED_AUTH,
  ZS_DUAL_SIM_REQUEST_REJECTED_HOLD,
  ZS_DUAL_SIM_REQUEST_REJECTED_PRESENCE,
  ZS_DUAL_SIM_REQUEST_REJECTED_SLOT,
  ZS_DUAL_SIM_REQUEST_REJECTED_PROFILE,
  ZS_DUAL_SIM_REQUEST_REJECTED_TRIGGER,
  ZS_DUAL_SIM_REQUEST_REJECTED_SAME_SLOT
} zs_dual_sim_request_result_t;

typedef struct {
  bool initialized;
  bool raw_present;
  bool stable_present;
  uint32_t raw_since_ms;
} zs_dual_sim_presence_t;

typedef struct {
  char expected_iccid[ZS_DUAL_SIM_SLOT_COUNT][ZS_DUAL_SIM_ICCID_CAPACITY];
  zs_dual_sim_presence_t presence[ZS_DUAL_SIM_SLOT_COUNT];
  uint8_t attempts[ZS_DUAL_SIM_SLOT_COUNT][ZS_DUAL_SIM_MAX_PROFILES];
  zs_dual_sim_state_t state;
  zs_dual_sim_slot_t active_slot;
  zs_dual_sim_slot_t pending_slot;
  uint8_t active_profile;
  uint8_t pending_profile;
  uint32_t last_activation_ms;
  uint32_t modem_rail_enabled_ms;
  bool active_known;
  bool hold_started;
  bool switch_from_active;
} zs_dual_sim_t;

bool zs_dual_sim_init(zs_dual_sim_t *controller,
                      const char *slot_1_expected_iccid,
                      const char *slot_2_expected_iccid);
bool zs_dual_sim_update_presence(zs_dual_sim_t *controller,
                                 zs_dual_sim_slot_t slot,
                                 bool raw_present,
                                 uint32_t now_ms);
zs_dual_sim_request_result_t zs_dual_sim_request_start(
    zs_dual_sim_t *controller, zs_dual_sim_slot_t target_slot,
    uint8_t target_profile);
zs_dual_sim_request_result_t zs_dual_sim_request_manual_switch(
    zs_dual_sim_t *controller, zs_dual_sim_slot_t target_slot,
    uint8_t target_profile, bool authenticated, uint32_t now_ms);
zs_dual_sim_request_result_t zs_dual_sim_report_failure(
    zs_dual_sim_t *controller, zs_dual_sim_failure_t failure,
    zs_dual_sim_slot_t alternate_slot, uint8_t alternate_profile,
    uint32_t now_ms);
zs_dual_sim_action_t zs_dual_sim_next_action(const zs_dual_sim_t *controller);
bool zs_dual_sim_complete_action(zs_dual_sim_t *controller,
                                 zs_dual_sim_action_t action,
                                 bool success, uint32_t now_ms);
bool zs_dual_sim_on_iccid(zs_dual_sim_t *controller, const char *full_iccid);
void zs_dual_sim_report_brownout(zs_dual_sim_t *controller);
zs_dual_sim_state_t zs_dual_sim_state(const zs_dual_sim_t *controller);
zs_dual_sim_slot_t zs_dual_sim_active_slot(const zs_dual_sim_t *controller);
bool zs_dual_sim_pending_profile(const zs_dual_sim_t *controller,
                                 uint8_t *profile_index);
const char *zs_dual_sim_state_name(zs_dual_sim_state_t state);

#endif
