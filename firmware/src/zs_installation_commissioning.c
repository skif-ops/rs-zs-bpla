#include "zs_installation_commissioning.h"

#include <string.h>

static bool role_valid(zs_commissioning_role_t role) {
  return role == ZS_COMMISSIONING_ROLE_INSTALLER || role == ZS_COMMISSIONING_ROLE_ENGINEER;
}

static zs_commissioning_result_t peer_gate(const zs_commissioning_context_t *context) {
  if (context == NULL) return ZS_COMMISSIONING_INVALID_ARGUMENT;
  if (context->origin != ZS_COMMISSIONING_ORIGIN_BLE_LOCAL) {
    return ZS_COMMISSIONING_LOCAL_BLE_REQUIRED;
  }
  if (!context->ble_secure_connections || !context->peer_identity_verified ||
      !role_valid(context->role)) {
    return ZS_COMMISSIONING_PEER_AUTH_REQUIRED;
  }
  return ZS_COMMISSIONING_OK;
}

static bool default_policy(const zs_installation_record_t *record) {
  const zs_position_trust_config_t *trust = &record->trust;
  return trust->warning_distance_m == 25u && trust->suspect_distance_m == 75u &&
         trust->gross_jump_distance_m == 250u && trust->warning_consecutive_fixes == 3u &&
         trust->suspect_consecutive_fixes == 10u;
}

static zs_commissioning_result_t map_store_result(zs_installation_store_result_t result) {
  switch (result) {
    case ZS_INSTALLATION_STORE_OK:
      return ZS_COMMISSIONING_OK;
    case ZS_INSTALLATION_STORE_NOT_FOUND:
      return ZS_COMMISSIONING_NOT_FOUND;
    case ZS_INSTALLATION_STORE_INVALID_ARGUMENT:
      return ZS_COMMISSIONING_INVALID_ARGUMENT;
    case ZS_INSTALLATION_STORE_AUTH_REQUIRED:
      return ZS_COMMISSIONING_PEER_AUTH_REQUIRED;
    case ZS_INSTALLATION_STORE_INVALID_RECORD:
      return ZS_COMMISSIONING_INVALID_RECORD;
    case ZS_INSTALLATION_STORE_LOCKED:
      return ZS_COMMISSIONING_LOCKED;
    case ZS_INSTALLATION_STORE_VERSION_REJECTED:
      return ZS_COMMISSIONING_VERSION_REJECTED;
    case ZS_INSTALLATION_STORE_IO_ERROR:
      return ZS_COMMISSIONING_STORAGE_IO_ERROR;
    case ZS_INSTALLATION_STORE_VERIFY_FAILED:
      return ZS_COMMISSIONING_VERIFY_FAILED;
  }
  return ZS_COMMISSIONING_STORAGE_IO_ERROR;
}

static bool append_audit(
    const zs_commissioning_audit_io_t *audit,
    zs_commissioning_audit_phase_t phase,
    zs_commissioning_operation_t operation,
    zs_commissioning_role_t role,
    zs_commissioning_result_t result,
    const zs_installation_record_t *record) {
  zs_commissioning_audit_event_t event;
  if (audit == NULL || audit->append == NULL || record == NULL) return false;
  memset(&event, 0, sizeof(event));
  event.phase = phase;
  event.operation = operation;
  event.role = role;
  event.result = result;
  event.version = record->version;
  memcpy(event.commissioning_hash, record->commissioning_hash, sizeof(event.commissioning_hash));
  return audit->append(audit->ctx, &event);
}

zs_commissioning_result_t zs_installation_commissioning_read(
    const zs_installation_store_io_t *store,
    const zs_commissioning_context_t *context,
    zs_installation_record_t *record) {
  const zs_commissioning_result_t gate = peer_gate(context);
  if (store == NULL || record == NULL) return ZS_COMMISSIONING_INVALID_ARGUMENT;
  if (gate != ZS_COMMISSIONING_OK) return gate;
  return map_store_result(zs_installation_store_load(store, record, NULL));
}

zs_commissioning_result_t zs_installation_commissioning_apply(
    const zs_installation_store_io_t *store,
    const zs_commissioning_audit_io_t *audit,
    const zs_commissioning_context_t *context,
    zs_commissioning_operation_t operation,
    const zs_installation_record_t *requested,
    zs_installation_record_t *readback,
    bool *committed) {
  zs_installation_record_t candidate;
  zs_commissioning_result_t result;
  zs_installation_store_result_t store_result;
  if (committed != NULL) *committed = false;
  if (store == NULL || requested == NULL || readback == NULL || committed == NULL ||
      (operation != ZS_COMMISSIONING_OPERATION_INITIAL &&
       operation != ZS_COMMISSIONING_OPERATION_RECOMMISSION)) {
    return ZS_COMMISSIONING_INVALID_ARGUMENT;
  }

  result = peer_gate(context);
  if (result != ZS_COMMISSIONING_OK) return result;
  if (!context->physical_service_mode ||
      (uint32_t)(context->now_ms - context->service_mode_started_ms) >
          ZS_INSTALLATION_SERVICE_WINDOW_MS) {
    return ZS_COMMISSIONING_SERVICE_MODE_REQUIRED;
  }

  candidate = *requested;
  candidate.storage_generation = 0u;
  candidate.trust.configured = true;
  candidate.trust.locked = true;
  candidate.trust.installation.position_source = ZS_POSITION_SOURCE_CONFIGURED_INSTALL;
  if (!default_policy(&candidate) && context->role != ZS_COMMISSIONING_ROLE_ENGINEER) {
    return ZS_COMMISSIONING_POLICY_ROLE_REQUIRED;
  }
  if (!zs_installation_record_compute_hash(&candidate, candidate.commissioning_hash)) {
    return ZS_COMMISSIONING_INVALID_RECORD;
  }
  if (!append_audit(audit, ZS_COMMISSIONING_AUDIT_INTENT, operation, context->role,
                    ZS_COMMISSIONING_OK, &candidate)) {
    return ZS_COMMISSIONING_AUDIT_REQUIRED;
  }

  store_result = zs_installation_store_commit(
      store, &candidate, true, true, operation == ZS_COMMISSIONING_OPERATION_RECOMMISSION);
  result = map_store_result(store_result);
  if (result != ZS_COMMISSIONING_OK) {
    (void)append_audit(audit, ZS_COMMISSIONING_AUDIT_REJECTED, operation, context->role,
                       result, &candidate);
    return result;
  }
  *committed = true;

  store_result = zs_installation_store_load(store, readback, NULL);
  if (store_result != ZS_INSTALLATION_STORE_OK || readback->version != candidate.version ||
      memcmp(readback->commissioning_hash, candidate.commissioning_hash,
             ZS_INSTALLATION_HASH_BYTES) != 0 ||
      !zs_installation_record_hash_valid(readback)) {
    return ZS_COMMISSIONING_READBACK_FAILED;
  }
  if (!append_audit(audit, ZS_COMMISSIONING_AUDIT_COMMITTED, operation, context->role,
                    ZS_COMMISSIONING_OK, readback)) {
    return ZS_COMMISSIONING_AUDIT_FINALIZE_FAILED;
  }
  return ZS_COMMISSIONING_OK;
}
