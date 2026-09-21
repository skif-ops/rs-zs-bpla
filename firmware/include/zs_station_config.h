#ifndef ZS_STATION_CONFIG_H
#define ZS_STATION_CONFIG_H

/*
 * Persistent station configuration record (EVT-PRE-20, schema v1).
 *
 * Holds the fields an installer/engineer sets over authenticated BLE
 * `config_write` (server "Muhoed" endpoint, TLS pinning reference, MQTT
 * tenant/topic prefix, public APN names, preferred SIM slot) plus the
 * factory-fixed identity fields (station_id, region) that the patch path is
 * not allowed to change.
 *
 * Storage: two flash slots (A/B), one active at a time.  A commit always
 * writes the inactive slot, verifies it by read-back and only then counts as
 * committed; an interrupted write leaves the previous record untouched.
 *
 * Hash: the station computes a canonical SHA-256 over the record itself and
 * never trusts a hash supplied by the phone (same rule as the installation
 * position store).  The Android app recomputes the same canonical hash after
 * read-back to prove the write landed unchanged.
 *
 * Portable/host only: flash access goes through zs_station_config_io_t.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_STATION_CONFIG_SCHEMA 1u
#define ZS_STATION_CONFIG_SLOT_COUNT 2u
#define ZS_STATION_CONFIG_SLOT_BYTES 320u
#define ZS_STATION_CONFIG_HASH_BYTES 32u

#define ZS_STATION_CONFIG_HOST_MAX 64u
#define ZS_STATION_CONFIG_CA_REF_MAX 32u
#define ZS_STATION_CONFIG_TENANT_MAX 16u
#define ZS_STATION_CONFIG_TOPIC_PREFIX_MAX 32u
#define ZS_STATION_CONFIG_APN_MAX 32u
#define ZS_STATION_CONFIG_APN_COUNT 2u

#define ZS_STATION_CONFIG_REGION_RU868 1u
#define ZS_STATION_CONFIG_REGION_EU868 2u

/* CBOR map keys accepted by zs_station_config_apply_patch (integer keys). */
#define ZS_STATION_CONFIG_KEY_VERSION 1u
#define ZS_STATION_CONFIG_KEY_SERVER_HOST 2u
#define ZS_STATION_CONFIG_KEY_MQTT_PORT 3u
#define ZS_STATION_CONFIG_KEY_HTTPS_PORT 4u
#define ZS_STATION_CONFIG_KEY_CA_REFERENCE 5u
#define ZS_STATION_CONFIG_KEY_SERVER_FINGERPRINT 6u
#define ZS_STATION_CONFIG_KEY_TENANT 7u
#define ZS_STATION_CONFIG_KEY_TOPIC_PREFIX 8u
#define ZS_STATION_CONFIG_KEY_PREFERRED_SIM 9u
#define ZS_STATION_CONFIG_KEY_APN1 10u
#define ZS_STATION_CONFIG_KEY_APN2 11u
#define ZS_STATION_CONFIG_KEY_REGION 12u

typedef enum {
  ZS_STATION_CONFIG_OK = 0,
  ZS_STATION_CONFIG_NOT_FOUND,
  ZS_STATION_CONFIG_INVALID_ARGUMENT,
  ZS_STATION_CONFIG_AUTH_REQUIRED,
  ZS_STATION_CONFIG_INVALID_RECORD,
  ZS_STATION_CONFIG_VERSION_REJECTED,
  ZS_STATION_CONFIG_PATCH_MALFORMED,
  ZS_STATION_CONFIG_PATCH_UNKNOWN_KEY,
  ZS_STATION_CONFIG_PATCH_IMMUTABLE_FIELD,
  ZS_STATION_CONFIG_IO_ERROR,
  ZS_STATION_CONFIG_VERIFY_FAILED
} zs_station_config_result_t;

/* Field-level validation codes (bit mask, zero means valid). */
#define ZS_STATION_CONFIG_ERR_STATION_ID (1u << 0)
#define ZS_STATION_CONFIG_ERR_REGION (1u << 1)
#define ZS_STATION_CONFIG_ERR_HOST (1u << 2)
#define ZS_STATION_CONFIG_ERR_MQTT_PORT (1u << 3)
#define ZS_STATION_CONFIG_ERR_HTTPS_PORT (1u << 4)
#define ZS_STATION_CONFIG_ERR_CA_REFERENCE (1u << 5)
#define ZS_STATION_CONFIG_ERR_TENANT (1u << 6)
#define ZS_STATION_CONFIG_ERR_TOPIC_PREFIX (1u << 7)
#define ZS_STATION_CONFIG_ERR_PREFERRED_SIM (1u << 8)
#define ZS_STATION_CONFIG_ERR_APN (1u << 9)
#define ZS_STATION_CONFIG_ERR_VERSION (1u << 10)

typedef struct {
  void *ctx;
  bool (*read)(void *ctx, uint8_t slot, uint32_t offset, uint8_t *data, size_t size);
  bool (*erase)(void *ctx, uint8_t slot);
  bool (*write)(void *ctx, uint8_t slot, uint32_t offset, const uint8_t *data, size_t size);
} zs_station_config_io_t;

typedef struct {
  /* Factory-fixed identity; patch may not change these. */
  uint32_t station_id;
  uint8_t region; /* ZS_STATION_CONFIG_REGION_* */

  /* Installer/engineer-settable. */
  uint32_t version; /* monotonic, set by the writer, must increase on every commit */
  char server_host[ZS_STATION_CONFIG_HOST_MAX + 1u]; /* IPv4 literal, IPv6 literal or RFC 1123 hostname */
  uint16_t mqtt_port;  /* 1..65535, TLS MQTT */
  uint16_t https_port; /* 0 = no HTTPS fallback, else 1..65535 */
  char ca_reference[ZS_STATION_CONFIG_CA_REF_MAX + 1u];
  uint8_t server_fingerprint[ZS_STATION_CONFIG_HASH_BYTES]; /* SHA-256 of server certificate, all zero = not pinned */
  char tenant[ZS_STATION_CONFIG_TENANT_MAX + 1u];
  char topic_prefix[ZS_STATION_CONFIG_TOPIC_PREFIX_MAX + 1u];
  uint8_t preferred_sim; /* 1 or 2 */
  char apn[ZS_STATION_CONFIG_APN_COUNT][ZS_STATION_CONFIG_APN_MAX + 1u]; /* ordered public APN names, empty = unused */

  /* Store metadata (read-only for callers). */
  uint32_t storage_generation;
  uint8_t config_hash[ZS_STATION_CONFIG_HASH_BYTES];
} zs_station_config_t;

/* Fills a record with factory defaults for the given identity (version 0, no server). */
void zs_station_config_defaults(zs_station_config_t *cfg, uint32_t station_id, uint8_t region);

/* Returns a ZS_STATION_CONFIG_ERR_* bit mask; zero means every field is valid. */
uint32_t zs_station_config_validate(const zs_station_config_t *cfg);

/* Host literal checks, exported for tests and for the BLE/USB service layer. */
bool zs_station_config_host_is_ipv4(const char *host);
bool zs_station_config_host_is_ipv6(const char *host);
bool zs_station_config_host_is_hostname(const char *host);

/* Canonical SHA-256 over the settable fields + identity (never over storage metadata). */
bool zs_station_config_compute_hash(const zs_station_config_t *cfg, uint8_t hash[ZS_STATION_CONFIG_HASH_BYTES]);
bool zs_station_config_hash_valid(const zs_station_config_t *cfg);

/*
 * Applies a BLE `config_write` CBOR patch (definite-length map with unsigned
 * integer keys from ZS_STATION_CONFIG_KEY_*) on top of `base` into `out`.
 * Fail-closed: unknown keys, wrong value types, duplicate keys, indefinite
 * lengths, a version that does not exceed base->version, or any attempt to
 * change station_id/region are rejected and `out` is left untouched.  The
 * resulting record must also pass zs_station_config_validate.
 * On success `out->config_hash` is recomputed by the station.
 */
zs_station_config_result_t zs_station_config_apply_patch(
    const zs_station_config_t *base,
    const uint8_t *patch,
    size_t patch_len,
    zs_station_config_t *out,
    uint32_t *validation_errors);

/*
 * Encodes the read-back view for BLE `config_read` as a canonical CBOR map
 * (keys ascending) so the phone can compare field by field and recompute the
 * hash.  Returns the encoded size or 0 if `cap` is too small.
 */
size_t zs_station_config_encode_readback(const zs_station_config_t *cfg, uint8_t *buf, size_t cap);

zs_station_config_result_t zs_station_config_store_load(
    const zs_station_config_io_t *io,
    zs_station_config_t *cfg,
    uint8_t *active_slot);

/*
 * Commits `cfg` to the inactive slot.  Requires physical service mode and an
 * authenticated role (installer/engineer), a valid record whose version is
 * greater than the currently stored one (or any version > 0 when the store is
 * empty), and a read-back that decodes to the same hash.
 */
zs_station_config_result_t zs_station_config_store_commit(
    const zs_station_config_io_t *io,
    const zs_station_config_t *cfg,
    bool physical_service_mode,
    bool authenticated_role);

#endif
