/* MQTT ICD addendum G, remote network configuration: the server-signed shared vector
   (tools/generate_network_config_vector.py) goes through the real trust adapter and Ed25519 backend, its patch through
   zs_net_trial on the twin's version 1 record:
     accepted -> the next bring-up tries the candidate -> online -> committed (zs_station_config_store_commit_remote);
     a candidate that never comes online -> rolled back after 3 failed bring-ups, or after 30 minutes;
   every refusal detail, the remote commit guards, a local write cancelling the trial, the heartbeat values of keys
   21..23 (their encoding: test_heartbeat_telemetry.c) and the journal fingerprint of the patch. */
#include "zs_cbor.h"
#include "zs_command_journal.h"
#include "zs_command_trust.h"
#include "zs_ed25519.h"
#include "zs_net_trial.h"
#include "zs_network_config_vector.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static uint8_t cfg_slots[2][ZS_STATION_CONFIG_SLOT_BYTES];
static bool c_read(void *c, uint8_t s, uint32_t o, uint8_t *d, size_t n) { (void)c; if (s > 1u || o + n > ZS_STATION_CONFIG_SLOT_BYTES) return false; memcpy(d, &cfg_slots[s][o], n); return true; }
static bool c_erase(void *c, uint8_t s) { (void)c; if (s > 1u) return false; memset(cfg_slots[s], 0xff, ZS_STATION_CONFIG_SLOT_BYTES); return true; }
static bool c_write(void *c, uint8_t s, uint32_t o, const uint8_t *d, size_t n) { (void)c; if (s > 1u || o + n > ZS_STATION_CONFIG_SLOT_BYTES) return false; for (size_t i = 0u; i < n; i++) { if ((cfg_slots[s][o + i] & d[i]) != d[i]) return false; cfg_slots[s][o + i] = d[i]; } return true; }
static const zs_station_config_io_t cfg_io = {NULL, c_read, c_erase, c_write};

static uint8_t journal[4][ZS_COMMAND_JOURNAL_SLOT_BYTES];
static bool j_read(void *c, uint16_t s, uint32_t o, uint8_t *d, size_t n) { (void)c; if (s >= 4u || o + n > ZS_COMMAND_JOURNAL_SLOT_BYTES) return false; memcpy(d, &journal[s][o], n); return true; }
static bool j_erase(void *c, uint16_t s) { (void)c; if (s >= 4u) return false; memset(journal[s], 0xff, ZS_COMMAND_JOURNAL_SLOT_BYTES); return true; }
static bool j_write(void *c, uint16_t s, uint32_t o, const uint8_t *d, size_t n) { (void)c; if (s >= 4u || o + n > ZS_COMMAND_JOURNAL_SLOT_BYTES) return false; for (size_t i = 0u; i < n; i++) { if ((journal[s][o + i] & d[i]) != d[i]) return false; journal[s][o + i] = d[i]; } return true; }

static bool ed25519(void *ctx, const uint8_t pk[ZS_COMMAND_PUBLIC_KEY_BYTES], const uint8_t *m, size_t n, const uint8_t sig[ZS_COMMAND_SIGNATURE_BYTES]) {
  (void)ctx; return zs_ed25519_verify(pk, m, n, sig);
}
static zs_command_dedup_state_t never_seen(void *ctx, const uint8_t id[ZS_COMMAND_UUID_BYTES]) { (void)ctx; (void)id; return ZS_COMMAND_DEDUP_NOT_SEEN; }

/* the twin's record: station 17, version 1, muhoed.twin:8883, tenant pilot1, APN internet */
static zs_station_config_t twin_record(void) {
  zs_station_config_t cfg;
  zs_station_config_defaults(&cfg, 17u, ZS_STATION_CONFIG_REGION_RU868);
  cfg.version = 1u; strcpy(cfg.server_host, "muhoed.twin"); cfg.mqtt_port = 8883u; strcpy(cfg.ca_reference, "dioneya-root");
  strcpy(cfg.tenant, "pilot1"); strcpy(cfg.topic_prefix, "zs/v1"); cfg.preferred_sim = 1u; strcpy(cfg.apn[0], "internet");
  assert(zs_station_config_validate(&cfg) == 0u && zs_station_config_compute_hash(&cfg, cfg.config_hash));
  return cfg;
}

/* a patch {1: version, key: text} (or {1: version, key: uint} when text is NULL), plus trailing junk on request */
static zs_set_network_command_t patch(uint32_t version, unsigned key, const char *text, uint64_t value, bool junk) {
  zs_set_network_command_t cmd;
  zs_cbor_t c;
  memset(&cmd, 0, sizeof(cmd));
  zs_cbor_init(&c, cmd.patch, sizeof(cmd.patch));
  zs_cbor_map(&c, key ? 2u : 1u);
  zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, version);
  if (key) { zs_cbor_uint(&c, key); if (text) zs_cbor_text(&c, text); else zs_cbor_uint(&c, value); }
  assert(!c.error);
  cmd.patch_size = (uint8_t)c.len;
  if (junk) cmd.patch[cmd.patch_size++] = 0x00u;
  return cmd;
}

static uint16_t reject_detail(const zs_station_config_t *stable, zs_set_network_command_t cmd) {
  zs_net_trial_t t;
  zs_command_ack_result_t r;
  uint16_t d;
  zs_net_trial_init(&t);
  zs_net_trial_accept(&t, stable, &cmd, &r, &d);
  assert(r == ZS_COMMAND_ACK_REJECTED && t.state == ZS_NET_STATE_STABLE);
  return d;
}

static void heartbeat(const zs_net_trial_t *t, const zs_station_config_t *stable, uint32_t v, uint8_t s, uint32_t f) {
  uint32_t version, failed;
  uint8_t state;
  zs_net_trial_heartbeat(t, stable, &version, &state, &failed);
  assert(version == v && state == s && failed == f);
}

int main(void) {
  static uint8_t workspace[256];
  zs_station_config_t stable = twin_record(), loaded;
  zs_command_trust_key_t key;
  zs_command_trust_t trust;
  zs_command_t cmd;
  zs_net_trial_t t;
  zs_command_ack_result_t result;
  uint16_t detail;
  const zs_station_config_t *use;

  memset(cfg_slots, 0xff, sizeof(cfg_slots));
  assert(zs_station_config_store_commit(&cfg_io, &stable, true, true) == ZS_STATION_CONFIG_OK);
  assert(zs_station_config_store_load(&cfg_io, &stable, NULL) == ZS_STATION_CONFIG_OK && stable.version == 1u);

  /* ---- the server-signed command verifies with the real backend and carries the server's patch bytes ---- */
  memset(&key, 0, sizeof(key));
  memcpy(key.public_key, zs_network_config_vector_public_key, sizeof(key.public_key)); key.enabled = true;
  assert(zs_command_trust_init(&trust, &key, 1u, ed25519, NULL));
  assert(zs_command_decode_verify(zs_network_config_vector_command, sizeof(zs_network_config_vector_command),
                                  ZS_NETWORK_CONFIG_VECTOR_STATION_ID, ZS_NETWORK_CONFIG_VECTOR_CREATED_US + 1000u, true,
                                  zs_command_trust_verify, &trust, never_seen, NULL, workspace, sizeof(workspace), &cmd) == ZS_COMMAND_STATUS_OK);
  assert(cmd.code == ZS_COMMAND_SET_NETWORK && cmd.network.patch_size == sizeof(zs_network_config_vector_patch));
  assert(memcmp(cmd.network.patch, zs_network_config_vector_patch, sizeof(zs_network_config_vector_patch)) == 0);
  {   /* one flipped byte in the signed patch: refused before any side effect */
    uint8_t forged[sizeof(zs_network_config_vector_command)];
    zs_command_t f;
    memcpy(forged, zs_network_config_vector_command, sizeof(forged));
    forged[60] ^= 0x01u;
    assert(zs_command_decode_verify(forged, sizeof(forged), 17u, ZS_NETWORK_CONFIG_VECTOR_CREATED_US + 1000u, true, zs_command_trust_verify,
                                    &trust, never_seen, NULL, workspace, sizeof(workspace), &f) != ZS_COMMAND_STATUS_OK);
  }

  /* ---- accepted: the stable record stays in use until the next bring-up ---- */
  zs_net_trial_init(&t);
  heartbeat(&t, &stable, 1u, ZS_NET_STATE_STABLE, 0u);
  assert(zs_net_trial_config(&t, &stable) == &stable && !zs_net_trial_busy(&t));
  zs_net_trial_accept(&t, &stable, &cmd.network, &result, &detail);
  assert(result == ZS_COMMAND_ACK_OK && detail == 0u && t.state == ZS_NET_STATE_ACCEPTED && zs_net_trial_busy(&t));
  heartbeat(&t, &stable, 1u, ZS_NET_STATE_ACCEPTED, 0u);
  use = zs_net_trial_config(&t, &stable);
  assert(use == &t.candidate && use->version == ZS_NETWORK_CONFIG_VECTOR_VERSION);
  assert(strcmp(use->server_host, ZS_NETWORK_CONFIG_VECTOR_HOST) == 0 && use->mqtt_port == ZS_NETWORK_CONFIG_VECTOR_MQTT_PORT);
  assert(strcmp(use->apn[0], ZS_NETWORK_CONFIG_VECTOR_APN1) == 0 && strcmp(use->ca_reference, "dioneya-root") == 0);
  assert(strcmp(use->tenant, "pilot1") == 0 && use->station_id == 17u && zs_station_config_hash_valid(use));
  /* a second configuration while the first is pending */
  {
    zs_set_network_command_t other = patch(5u, ZS_STATION_CONFIG_KEY_SERVER_HOST, "other.twin", 0u, false);
    zs_net_trial_accept(&t, &stable, &other, &result, &detail);
    assert(result == ZS_COMMAND_ACK_REJECTED && detail == ZS_NET_REJECT_BUSY && t.state == ZS_NET_STATE_ACCEPTED);
  }
  assert(!zs_net_trial_on_failure(&t, 0u) && !zs_net_trial_on_online(&t) && !zs_net_trial_tick(&t, ZS_NET_TRIAL_TIMEOUT_MS * 2u));

  /* ---- trial: the bring-up uses the candidate; online -> committed -> stable ---- */
  zs_net_trial_on_bringup(&t, 1000u);
  assert(t.state == ZS_NET_STATE_TRIAL);
  heartbeat(&t, &stable, 2u, ZS_NET_STATE_TRIAL, 0u);
  assert(!zs_net_trial_on_failure(&t, 2000u) && t.failures == 1u);    /* one failed attempt is not yet a rollback */
  zs_net_trial_on_bringup(&t, 3000u);                                   /* later bring-ups keep the trial clock */
  assert(t.trial_started_ms == 1000u);
  assert(zs_net_trial_on_online(&t));
  assert(zs_station_config_store_commit_remote(&cfg_io, &t.candidate, &t.stable) == ZS_STATION_CONFIG_OK);
  zs_net_trial_finish(&t, true);
  assert(t.state == ZS_NET_STATE_STABLE && t.confirmed == 1u && !zs_net_trial_busy(&t));
  assert(zs_station_config_store_load(&cfg_io, &loaded, NULL) == ZS_STATION_CONFIG_OK && loaded.version == 2u);
  assert(strcmp(loaded.server_host, ZS_NETWORK_CONFIG_VECTOR_HOST) == 0 && memcmp(loaded.config_hash, t.stable.config_hash, 32u) == 0);
  stable = loaded;
  heartbeat(&t, &stable, 2u, ZS_NET_STATE_STABLE, 0u);

  /* ---- a candidate that never comes online: three failed bring-ups roll back ---- */
  {
    zs_set_network_command_t dead = patch(3u, ZS_STATION_CONFIG_KEY_SERVER_HOST, "dead.twin", 0u, false);
    zs_net_trial_accept(&t, &stable, &dead, &result, &detail);
    assert(result == ZS_COMMAND_ACK_OK);
    zs_net_trial_on_bringup(&t, 10000u);
    assert(!zs_net_trial_on_failure(&t, 11000u) && !zs_net_trial_on_failure(&t, 12000u));
    assert(zs_net_trial_on_failure(&t, 13000u));
    assert(t.state == ZS_NET_STATE_ROLLED_BACK && t.failed_version == 3u && t.rolled_back == 1u);
    assert(zs_net_trial_config(&t, &stable) == &stable);
    heartbeat(&t, &stable, 2u, ZS_NET_STATE_ROLLED_BACK, 3u);
    assert(!zs_net_trial_on_failure(&t, 14000u) && !zs_net_trial_on_online(&t));
    assert(zs_station_config_store_load(&cfg_io, &loaded, NULL) == ZS_STATION_CONFIG_OK && loaded.version == 2u);   /* nothing written */

    /* rolled back is not busy: a corrected configuration is accepted, the 30-minute limit rolls it back too */
    dead = patch(4u, ZS_STATION_CONFIG_KEY_SERVER_HOST, "slow.twin", 0u, false);
    zs_net_trial_accept(&t, &stable, &dead, &result, &detail);
    assert(result == ZS_COMMAND_ACK_OK && t.failed_version == 3u);
    heartbeat(&t, &stable, 2u, ZS_NET_STATE_ACCEPTED, 3u);
    zs_net_trial_on_bringup(&t, 20000u);
    assert(!zs_net_trial_tick(&t, 20000u + ZS_NET_TRIAL_TIMEOUT_MS - 1u));
    assert(zs_net_trial_tick(&t, 20000u + ZS_NET_TRIAL_TIMEOUT_MS));
    heartbeat(&t, &stable, 2u, ZS_NET_STATE_ROLLED_BACK, 4u);

    /* a confirmed trial clears the failure mark */
    dead = patch(5u, ZS_STATION_CONFIG_KEY_MQTT_PORT, NULL, 8883u, false);   /* back from the vector's 443 */
    zs_net_trial_accept(&t, &stable, &dead, &result, &detail);
    zs_net_trial_on_bringup(&t, 30000u);
    assert(zs_net_trial_on_online(&t) && zs_station_config_store_commit_remote(&cfg_io, &t.candidate, &t.stable) == ZS_STATION_CONFIG_OK);
    zs_net_trial_finish(&t, true);
    assert(zs_station_config_store_load(&cfg_io, &stable, NULL) == ZS_STATION_CONFIG_OK && stable.version == 5u && stable.mqtt_port == 8883u);
    heartbeat(&t, &stable, 5u, ZS_NET_STATE_STABLE, 0u);
  }

  /* ---- a commit that cannot happen rolls back: the stored record changed under the trial (BLE write) ---- */
  {
    zs_set_network_command_t next = patch(6u, ZS_STATION_CONFIG_KEY_TENANT, "pilot2", 0u, false);
    zs_station_config_t local = stable;
    zs_net_trial_accept(&t, &stable, &next, &result, &detail);
    assert(result == ZS_COMMAND_ACK_OK);
    zs_net_trial_on_bringup(&t, 40000u);
    local.version = 7u; strcpy(local.apn[1], "backup"); assert(zs_station_config_compute_hash(&local, local.config_hash));
    assert(zs_station_config_store_commit(&cfg_io, &local, true, true) == ZS_STATION_CONFIG_OK);
    assert(zs_station_config_store_commit_remote(&cfg_io, &t.candidate, &t.stable) == ZS_STATION_CONFIG_VERSION_REJECTED);
    zs_net_trial_finish(&t, false);
    assert(t.state == ZS_NET_STATE_ROLLED_BACK && t.failed_version == 6u);
    assert(zs_station_config_store_load(&cfg_io, &stable, NULL) == ZS_STATION_CONFIG_OK && stable.version == 7u);
  }

  /* ---- a local write drops a pending trial without a failure mark ---- */
  {
    zs_set_network_command_t next = patch(8u, ZS_STATION_CONFIG_KEY_PREFERRED_SIM, NULL, 2u, false);
    zs_net_trial_init(&t);
    zs_net_trial_accept(&t, &stable, &next, &result, &detail);
    assert(result == ZS_COMMAND_ACK_OK && zs_net_trial_config(&t, &stable)->preferred_sim == 2u);
    zs_net_trial_cancel(&t);
    assert(t.state == ZS_NET_STATE_STABLE && t.failed_version == 0u && zs_net_trial_config(&t, &stable) == &stable);
  }

  /* ---- the remote commit never moves the trust anchor or the identity ---- */
  {
    zs_station_config_t forged = stable;
    forged.version = 9u; strcpy(forged.ca_reference, "attacker-ca"); assert(zs_station_config_compute_hash(&forged, forged.config_hash));
    assert(zs_station_config_store_commit_remote(&cfg_io, &forged, &stable) == ZS_STATION_CONFIG_PATCH_IMMUTABLE_FIELD);
    forged = stable; forged.version = 9u; forged.region = ZS_STATION_CONFIG_REGION_EU868; assert(zs_station_config_compute_hash(&forged, forged.config_hash));
    assert(zs_station_config_store_commit_remote(&cfg_io, &forged, &stable) == ZS_STATION_CONFIG_PATCH_IMMUTABLE_FIELD);
    forged = stable;                                                   /* not above the stored version */
    assert(zs_station_config_store_commit_remote(&cfg_io, &forged, &stable) == ZS_STATION_CONFIG_VERSION_REJECTED);
  }

  /* ---- refusals: every detail, nothing accepted ---- */
  assert(reject_detail(&stable, patch(7u, ZS_STATION_CONFIG_KEY_SERVER_HOST, "x.twin", 0u, false)) == ZS_NET_REJECT_VERSION);
  assert(reject_detail(&stable, patch(9u, ZS_STATION_CONFIG_KEY_SERVER_HOST, "x.twin", 0u, true)) == ZS_NET_REJECT_MALFORMED);
  assert(reject_detail(&stable, patch(9u, 13u, NULL, 17u, false)) == ZS_NET_REJECT_MALFORMED);            /* station_id: unknown key */
  assert(reject_detail(&stable, patch(9u, ZS_STATION_CONFIG_KEY_SERVER_HOST, "bad host", 0u, false)) == ZS_NET_REJECT_INVALID);
  assert(reject_detail(&stable, patch(9u, ZS_STATION_CONFIG_KEY_MQTT_PORT, NULL, 0u, false)) == ZS_NET_REJECT_INVALID);
  assert(reject_detail(&stable, patch(9u, ZS_STATION_CONFIG_KEY_MQTT_PORT, NULL, 9883u, false)) == ZS_NET_REJECT_INVALID);   /* no TLS there */
  assert(reject_detail(&stable, patch(9u, ZS_STATION_CONFIG_KEY_REGION, NULL, ZS_STATION_CONFIG_REGION_EU868, false)) == ZS_NET_REJECT_IMMUTABLE);
  assert(reject_detail(&stable, patch(9u, ZS_STATION_CONFIG_KEY_CA_REFERENCE, "attacker-ca", 0u, false)) == ZS_NET_REJECT_IMMUTABLE);
  assert(reject_detail(&stable, patch(9u, 0u, NULL, 0u, false)) == ZS_NET_REJECT_NO_CHANGE);
  assert(reject_detail(&stable, patch(9u, ZS_STATION_CONFIG_KEY_SERVER_HOST, stable.server_host, 0u, false)) == ZS_NET_REJECT_NO_CHANGE);
  {
    zs_station_config_t empty;
    zs_station_config_defaults(&empty, 17u, ZS_STATION_CONFIG_REGION_RU868);   /* never configured: nothing to patch remotely */
    assert(reject_detail(&empty, patch(9u, ZS_STATION_CONFIG_KEY_SERVER_HOST, "x.twin", 0u, false)) == ZS_NET_REJECT_UNSUPPORTED);
  }
  /* a CA reference repeated unchanged is not a change of the anchor */
  {
    zs_set_network_command_t same_ca;
    zs_cbor_t c;
    memset(&same_ca, 0, sizeof(same_ca));
    zs_cbor_init(&c, same_ca.patch, sizeof(same_ca.patch));
    zs_cbor_map(&c, 3u);
    zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 9u);
    zs_cbor_uint(&c, 2u); zs_cbor_text(&c, "y.twin");
    zs_cbor_uint(&c, 5u); zs_cbor_text(&c, stable.ca_reference);
    same_ca.patch_size = (uint8_t)c.len;
    zs_net_trial_init(&t);
    zs_net_trial_accept(&t, &stable, &same_ca, &result, &detail);
    assert(result == ZS_COMMAND_ACK_OK && strcmp(t.candidate.server_host, "y.twin") == 0);
  }

  /* ---- the journal fingerprints the patch: the same UUID with another patch conflicts ---- */
  {
    zs_command_t other = cmd;
    uint8_t buf[ZS_COMMAND_ACK_MAX_BYTES];
    const zs_command_journal_io_t jio = {NULL, 4u, j_read, j_erase, j_write};
    memset(journal, 0xff, sizeof(journal));
    assert(zs_command_journal_accept(&jio, &cmd, ZS_NETWORK_CONFIG_VECTOR_CREATED_US + 1000u) == ZS_COMMAND_JOURNAL_OK);
    assert(zs_command_journal_accept(&jio, &cmd, ZS_NETWORK_CONFIG_VECTOR_CREATED_US + 2000u) == ZS_COMMAND_JOURNAL_ALREADY_ACCEPTED);
    other.network.patch[other.network.patch_size - 1u] ^= 1u;
    assert(zs_command_journal_accept(&jio, &other, ZS_NETWORK_CONFIG_VECTOR_CREATED_US + 2000u) == ZS_COMMAND_JOURNAL_CONFLICT);
    other = cmd; other.network.patch_size = 0u;
    assert(zs_command_journal_accept(&jio, &other, ZS_NETWORK_CONFIG_VECTOR_CREATED_US + 2000u) == ZS_COMMAND_JOURNAL_INVALID_COMMAND);
    assert(zs_command_journal_complete(&jio, cmd.command_id, ZS_COMMAND_ACK_OK, 0u, ZS_NETWORK_CONFIG_VECTOR_CREATED_US + 3000u) == ZS_COMMAND_JOURNAL_OK);
    assert(zs_command_journal_encode_ack(&jio, cmd.command_id, buf, sizeof(buf)) > 0u);
  }

  puts("zs_net_trial_tests: OK");
  return 0;
}
