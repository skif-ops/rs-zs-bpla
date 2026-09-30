#include "zs_net_trial.h"

#include <string.h>

void zs_net_trial_init(zs_net_trial_t *t) {
  if (t) memset(t, 0, sizeof(*t));
}

static bool network_equal(const zs_station_config_t *a, const zs_station_config_t *b) {
  return strcmp(a->server_host, b->server_host) == 0 && a->mqtt_port == b->mqtt_port && a->https_port == b->https_port &&
         memcmp(a->server_fingerprint, b->server_fingerprint, sizeof(a->server_fingerprint)) == 0 &&
         strcmp(a->tenant, b->tenant) == 0 && strcmp(a->topic_prefix, b->topic_prefix) == 0 &&
         a->preferred_sim == b->preferred_sim && strcmp(a->apn[0], b->apn[0]) == 0 && strcmp(a->apn[1], b->apn[1]) == 0;
}

void zs_net_trial_accept(zs_net_trial_t *t, const zs_station_config_t *stable, const zs_set_network_command_t *cmd,
                         zs_command_ack_result_t *result, uint16_t *detail) {
  zs_station_config_t next;
  uint32_t errors = 0u;
  zs_station_config_result_t r;
  *result = ZS_COMMAND_ACK_REJECTED;
  if (!t || !stable || !cmd || stable->version == 0u) { *detail = ZS_NET_REJECT_UNSUPPORTED; return; }
  if (zs_net_trial_busy(t)) { *detail = ZS_NET_REJECT_BUSY; return; }
  r = zs_station_config_apply_patch(stable, cmd->patch, cmd->patch_size, &next, &errors);
  switch (r) {
    case ZS_STATION_CONFIG_OK: break;
    case ZS_STATION_CONFIG_VERSION_REJECTED: *detail = ZS_NET_REJECT_VERSION; return;
    case ZS_STATION_CONFIG_INVALID_RECORD: *detail = ZS_NET_REJECT_INVALID; return;
    case ZS_STATION_CONFIG_PATCH_IMMUTABLE_FIELD: *detail = ZS_NET_REJECT_IMMUTABLE; return;
    default: *detail = ZS_NET_REJECT_MALFORMED; return;
  }
  if (strcmp(next.ca_reference, stable->ca_reference) != 0) { *detail = ZS_NET_REJECT_IMMUTABLE; return; }
  if (next.mqtt_port != 8883u && next.mqtt_port != 443u) { *detail = ZS_NET_REJECT_INVALID; return; }   /* the modem's TLS policy */
  if (network_equal(&next, stable)) { *detail = ZS_NET_REJECT_NO_CHANGE; return; }
  t->stable = *stable;
  t->candidate = next;
  t->state = ZS_NET_STATE_ACCEPTED;
  t->failures = 0u;
  t->accepted++;
  *result = ZS_COMMAND_ACK_OK;
  *detail = 0u;
}

bool zs_net_trial_busy(const zs_net_trial_t *t) {
  return t && (t->state == ZS_NET_STATE_ACCEPTED || t->state == ZS_NET_STATE_TRIAL);
}

const zs_station_config_t *zs_net_trial_config(const zs_net_trial_t *t, const zs_station_config_t *stable) {
  return zs_net_trial_busy(t) ? &t->candidate : stable;
}

void zs_net_trial_on_bringup(zs_net_trial_t *t, uint32_t now_ms) {
  if (!t || t->state != ZS_NET_STATE_ACCEPTED) return;
  t->state = ZS_NET_STATE_TRIAL;
  t->trial_started_ms = now_ms;
  t->failures = 0u;
}

static void roll_back(zs_net_trial_t *t) {
  t->failed_version = t->candidate.version;
  t->state = ZS_NET_STATE_ROLLED_BACK;
  t->rolled_back++;
  memset(&t->candidate, 0, sizeof(t->candidate));
}

bool zs_net_trial_on_failure(zs_net_trial_t *t, uint32_t now_ms) {
  (void)now_ms;
  if (!t || t->state != ZS_NET_STATE_TRIAL) return false;
  if (++t->failures < ZS_NET_TRIAL_ATTEMPTS) return false;
  roll_back(t);
  return true;
}

bool zs_net_trial_on_online(const zs_net_trial_t *t) { return t && t->state == ZS_NET_STATE_TRIAL; }

void zs_net_trial_finish(zs_net_trial_t *t, bool committed) {
  if (!t || t->state != ZS_NET_STATE_TRIAL) return;
  if (!committed) { roll_back(t); return; }
  t->stable = t->candidate;
  t->state = ZS_NET_STATE_STABLE;
  t->failed_version = 0u;
  t->confirmed++;
}

bool zs_net_trial_tick(zs_net_trial_t *t, uint32_t now_ms) {
  if (!t || t->state != ZS_NET_STATE_TRIAL || (uint32_t)(now_ms - t->trial_started_ms) < ZS_NET_TRIAL_TIMEOUT_MS) return false;
  roll_back(t);
  return true;
}

void zs_net_trial_cancel(zs_net_trial_t *t) {
  if (!t || !zs_net_trial_busy(t)) return;
  t->state = ZS_NET_STATE_STABLE;
  memset(&t->candidate, 0, sizeof(t->candidate));
}

void zs_net_trial_heartbeat(const zs_net_trial_t *t, const zs_station_config_t *stable, uint32_t *version, uint8_t *state,
                            uint32_t *failed_version) {
  const zs_net_state_t s = t ? t->state : ZS_NET_STATE_STABLE;
  *version = s == ZS_NET_STATE_TRIAL ? t->candidate.version : (stable ? stable->version : 0u);
  *state = (uint8_t)s;
  *failed_version = t ? t->failed_version : 0u;
}
