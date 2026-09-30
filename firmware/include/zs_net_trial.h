#ifndef ZS_NET_TRIAL_H
#define ZS_NET_TRIAL_H

/*
 * Remote network configuration with trial and automatic rollback (MQTT ICD addendum G).
 *
 * CMD_SET_NETWORK_CONFIG carries a station configuration patch in the BLE config_write format.  The station applies
 * it to the stable (stored) record in RAM and answers at once: REJECTED with a detail, or OK = accepted for trial.
 * The session that brought the command ends normally (the ACK goes out under the old configuration); every bring-up
 * after it uses the candidate.  The first session that comes online with it proves it: the candidate is committed to
 * the store and becomes the stable record.  Three failed bring-ups, or 30 minutes without success, roll back to the
 * stable record; a reset during the trial does the same (the candidate lives in RAM only).
 *
 * Remotely settable: server host, MQTT/HTTPS ports, server certificate pin, tenant, topic prefix, preferred SIM and the
 * APNs.  The CA reference (the trust anchor in the modem) stays a service-mode field, region and station id never
 * change.  Portable: no I/O here; the caller commits the candidate (zs_station_config_store_commit_remote).
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_command.h"
#include "zs_station_config.h"

#define ZS_NET_TRIAL_ATTEMPTS 3u
#define ZS_NET_TRIAL_TIMEOUT_MS (30u * 60u * 1000u)

/* ACK REJECTED details (addendum G §2) */
#define ZS_NET_REJECT_UNSUPPORTED 1u  /* no configuration store / firmware without the addendum */
#define ZS_NET_REJECT_MALFORMED 2u    /* not a canonical patch, unknown key, wrong type */
#define ZS_NET_REJECT_VERSION 3u      /* version missing or not above the stored one */
#define ZS_NET_REJECT_INVALID 4u      /* the resulting record fails validation (host, ports, names, APN), or its MQTT
                                         port is not one the modem opens TLS on (8883, 443: zs_bg95_configure_mqtt_tls) */
#define ZS_NET_REJECT_IMMUTABLE 5u    /* region, or the CA reference (service mode only) */
#define ZS_NET_REJECT_BUSY 6u         /* another configuration is accepted or on trial */
#define ZS_NET_REJECT_NO_CHANGE 7u    /* the patch leaves every network field as it is */

typedef enum {
  ZS_NET_STATE_STABLE = 0,      /* the stored record is in use */
  ZS_NET_STATE_ACCEPTED = 1,    /* accepted; the next bring-up uses the candidate */
  ZS_NET_STATE_TRIAL = 2,       /* bring-ups use the candidate until one comes online */
  ZS_NET_STATE_ROLLED_BACK = 3  /* the last candidate failed; the stored record is in use */
} zs_net_state_t;

typedef struct {
  zs_net_state_t state;
  zs_station_config_t stable;     /* the record the candidate was built on (valid while accepted/on trial) */
  zs_station_config_t candidate;
  uint8_t failures;               /* failed bring-ups on trial */
  uint32_t trial_started_ms;
  uint32_t failed_version;        /* heartbeat key 23 */
  uint32_t accepted, confirmed, rolled_back;
} zs_net_trial_t;

void zs_net_trial_init(zs_net_trial_t *t);

/* Executor part of CMD_SET_NETWORK_CONFIG: the ACK result and detail for `cmd` against the stable record. */
void zs_net_trial_accept(zs_net_trial_t *t, const zs_station_config_t *stable, const zs_set_network_command_t *cmd,
                         zs_command_ack_result_t *result, uint16_t *detail);

/* The record the next bring-up uses: the candidate while accepted/on trial, otherwise `stable`. */
const zs_station_config_t *zs_net_trial_config(const zs_net_trial_t *t, const zs_station_config_t *stable);

/* A bring-up starts (modem power-on): accepted -> trial, the 30-minute clock starts with the first one. */
void zs_net_trial_on_bringup(zs_net_trial_t *t, uint32_t now_ms);

/* A bring-up on trial failed (no attach/PDP, endpoint, TLS/MQTT or subscription): true when this rolled back. */
bool zs_net_trial_on_failure(zs_net_trial_t *t, uint32_t now_ms);

/* A session came online: true when the candidate must be committed now (then zs_net_trial_finish). */
bool zs_net_trial_on_online(const zs_net_trial_t *t);

/* The commit outcome: true -> stable with the candidate, false -> rolled back (the candidate is not durable). */
void zs_net_trial_finish(zs_net_trial_t *t, bool committed);

/* The 30-minute limit, checked between bring-ups: true when this rolled back. */
bool zs_net_trial_tick(zs_net_trial_t *t, uint32_t now_ms);

/* A local write (BLE config_write) replaced the stored record: the trial is dropped without a rollback mark. */
void zs_net_trial_cancel(zs_net_trial_t *t);

/* Accepted or on trial (the S3 watchdog gives the trial its time, a second command is refused). */
bool zs_net_trial_busy(const zs_net_trial_t *t);

/* Heartbeat keys 21..23. */
void zs_net_trial_heartbeat(const zs_net_trial_t *t, const zs_station_config_t *stable, uint32_t *version, uint8_t *state,
                            uint32_t *failed_version);

#endif
