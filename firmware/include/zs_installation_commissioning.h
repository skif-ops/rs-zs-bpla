#ifndef ZS_INSTALLATION_COMMISSIONING_H
#define ZS_INSTALLATION_COMMISSIONING_H

#include "zs_installation_store.h"

#include <stdbool.h>
#include <stdint.h>

#define ZS_INSTALLATION_SERVICE_WINDOW_MS UINT32_C(600000)

typedef enum {
  ZS_COMMISSIONING_ORIGIN_BLE_LOCAL = 0,
  ZS_COMMISSIONING_ORIGIN_MQTT_REMOTE = 1,
  ZS_COMMISSIONING_ORIGIN_HTTPS_REMOTE = 2
} zs_commissioning_origin_t;

typedef enum {
  ZS_COMMISSIONING_ROLE_NONE = 0,
  ZS_COMMISSIONING_ROLE_INSTALLER = 1,
  ZS_COMMISSIONING_ROLE_ENGINEER = 2
} zs_commissioning_role_t;

typedef enum {
  ZS_COMMISSIONING_OPERATION_INITIAL = 0,
  ZS_COMMISSIONING_OPERATION_RECOMMISSION = 1
} zs_commissioning_operation_t;

typedef enum {
  ZS_COMMISSIONING_AUDIT_INTENT = 0,
  ZS_COMMISSIONING_AUDIT_COMMITTED = 1,
  ZS_COMMISSIONING_AUDIT_REJECTED = 2
} zs_commissioning_audit_phase_t;

typedef enum {
  ZS_COMMISSIONING_OK = 0,
  ZS_COMMISSIONING_INVALID_ARGUMENT,
  ZS_COMMISSIONING_LOCAL_BLE_REQUIRED,
  ZS_COMMISSIONING_PEER_AUTH_REQUIRED,
  ZS_COMMISSIONING_SERVICE_MODE_REQUIRED,
  ZS_COMMISSIONING_POLICY_ROLE_REQUIRED,
  ZS_COMMISSIONING_AUDIT_REQUIRED,
  ZS_COMMISSIONING_NOT_FOUND,
  ZS_COMMISSIONING_INVALID_RECORD,
  ZS_COMMISSIONING_LOCKED,
  ZS_COMMISSIONING_VERSION_REJECTED,
  ZS_COMMISSIONING_STORAGE_IO_ERROR,
  ZS_COMMISSIONING_VERIFY_FAILED,
  ZS_COMMISSIONING_READBACK_FAILED,
  ZS_COMMISSIONING_AUDIT_FINALIZE_FAILED
} zs_commissioning_result_t;

typedef struct {
  zs_commissioning_origin_t origin;
  zs_commissioning_role_t role;
  bool ble_secure_connections;
  bool peer_identity_verified;
  bool physical_service_mode;
  uint32_t service_mode_started_ms;
  uint32_t now_ms;
} zs_commissioning_context_t;

typedef struct {
  zs_commissioning_audit_phase_t phase;
  zs_commissioning_operation_t operation;
  zs_commissioning_role_t role;
  zs_commissioning_result_t result;
  uint32_t version;
  uint8_t commissioning_hash[ZS_INSTALLATION_HASH_BYTES];
} zs_commissioning_audit_event_t;

typedef struct {
  void *ctx;
  bool (*append)(void *ctx, const zs_commissioning_audit_event_t *event);
} zs_commissioning_audit_io_t;

zs_commissioning_result_t zs_installation_commissioning_read(
    const zs_installation_store_io_t *store,
    const zs_commissioning_context_t *context,
    zs_installation_record_t *record);

zs_commissioning_result_t zs_installation_commissioning_apply(
    const zs_installation_store_io_t *store,
    const zs_commissioning_audit_io_t *audit,
    const zs_commissioning_context_t *context,
    zs_commissioning_operation_t operation,
    const zs_installation_record_t *requested,
    zs_installation_record_t *readback,
    bool *committed);

#endif
