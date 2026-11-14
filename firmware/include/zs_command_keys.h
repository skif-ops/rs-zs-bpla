#ifndef ZS_COMMAND_KEYS_H
#define ZS_COMMAND_KEYS_H
/*
 * Command trust keys of the station and their remote rotation (MQTT_TLS_ICD_v0_1 addendum E).
 *
 * The station secrets record (zs_station_secrets, NOR) holds the current command public key and, while a rotation
 * is in flight, the next one.  Both are trusted.  CMD_ROTATE_COMMAND_KEY, signed by a trusted key, installs the
 * next key; the first command that verifies with the next key proves the server signs with it, so the next key
 * becomes the current one and the old key is dropped.  Until then a server that lost the new private key still
 * reaches the station with the old one.
 *
 * Every call reads the record fresh and commits a whole new record (two slots, newest valid wins), so a power loss
 * leaves either the old or the new trust set.  The BLE engineer path (ICD BLE v0.3, key 4) that writes the command
 * key clears the next key: it is the recovery when the rotation went wrong.
 */
#include "zs_command.h"
#include "zs_command_trust.h"
#include "zs_station_secrets.h"

#include <stdbool.h>
#include <stdint.h>

/* ACK details of CMD_ROTATE_COMMAND_KEY (REJECTED 1 stays "not implemented" on older firmware) */
#define ZS_COMMAND_KEYS_REJECT_INVALID_KEY 2u   /* all-zero key, or the key is already the current one */
#define ZS_COMMAND_KEYS_REJECT_NO_RECORD 3u     /* no secrets record to extend (cannot happen for a verified command) */
#define ZS_COMMAND_KEYS_FAIL_STORAGE 1u         /* FAILED: the NOR commit did not verify */

/* Key id of the MQTT ICD §2.1: the first 8 bytes of SHA-256 over the raw public key. */
void zs_command_key_id(const uint8_t public_key[ZS_COMMAND_PUBLIC_KEY_BYTES], uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES]);
/* The key id as the heartbeat carries it (detector keys 16/17): big-endian uint64 of the 8 bytes, 0 = no key. */
uint64_t zs_command_key_id_u64(const uint8_t public_key[ZS_COMMAND_PUBLIC_KEY_BYTES]);

/* The trust set of a record for zs_command_trust_init: the current key, then the next one when set.  Returns the
   count (0 when no command key is provisioned). */
size_t zs_command_keys_trust_set(const zs_station_secrets_t *rec, zs_command_trust_key_t out[2]);

/* Executor of CMD_ROTATE_COMMAND_KEY: installs `next` as the next key (idempotent when it already is). */
void zs_command_keys_rotate(const zs_station_secrets_io_t *io, const uint8_t next[ZS_COMMAND_PUBLIC_KEY_BYTES],
                            zs_command_ack_result_t *result, uint16_t *detail);

/* Called for every verified command before it executes: when `key_id` is the next key's id, the next key becomes
   the current one and the old key is dropped.  Returns true when it promoted (the trust set must be reloaded). */
bool zs_command_keys_on_verified(const zs_station_secrets_io_t *io, const uint8_t key_id[ZS_COMMAND_KEY_ID_BYTES]);

#endif
