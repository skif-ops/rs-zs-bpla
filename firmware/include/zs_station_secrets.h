#ifndef ZS_STATION_SECRETS_H
#define ZS_STATION_SECRETS_H
/*
 * Station secrets record (B3, NOR): what provisioning leaves on the STM32 and what must not travel
 * over the label, the BLE configuration or the MQTT link:
 *   - the immutable factory identity and the label pairing secret, written over
 *     the isolated EOL console before the first BLE session,
 *   - the B.9 engineer key (32 bytes; ICD v0.2 §4, `muhoed-pki engineer-key`),
 *   - the expected ICCID of SIM slot 1 and 2 (dual-SIM policy, zs_dual_sim),
 *   - the command trust public key (Ed25519 raw, MQTT ICD §2.1) once it is issued, and the next one while a
 *     remote rotation is in flight (MQTT ICD addendum E: both are trusted until the next one signs a command).
 * Two slots, one erase block each (zs_nor_slot_store): a commit writes the inactive slot and the
 * newest valid record wins, so an interrupted write keeps the previous secrets.  Only the presence of
 * a secret is ever printed; the values stay in RAM and NOR.
 *
 * Record v3 (ZS_STATION_SECRETS_RECORD_BYTES = 192), written by every commit:
 *   [0..8)   magic "ZSSECR03"   [8..12) version LE32   [12..16) flags LE32 (bit0 engineer key,
 *   bit1 iccid 1, bit2 iccid 2, bit3 command key, bit4 next command key, bit5 pairing secret,
 *   bit6 factory serial)   [16..48) engineer key
 *   [48..71) iccid 1 (NUL padded)   [71..94) iccid 2   [94..126) command public key
 *   [126..158) next command public key   [158..174) pairing secret   [174..186) factory serial
 *   [186..188) reserved   [188..192) CRC32 of [0..188)
 * Records v1 ("ZSSECR01", 132 bytes) and v2 ("ZSSECR02", 164 bytes) are still read; their next commit writes v3.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_STATION_SECRETS_SLOT_COUNT 2u
#define ZS_STATION_SECRETS_SLOT_BYTES 192u
#define ZS_STATION_SECRETS_RECORD_BYTES 192u
#define ZS_STATION_SECRETS_KEY_BYTES 32u
#define ZS_STATION_PAIRING_SECRET_BYTES 16u
#define ZS_STATION_FACTORY_SERIAL_CAPACITY 12u
#define ZS_STATION_SECRETS_ICCID_CAPACITY 23u

typedef enum {
  ZS_STATION_SECRETS_OK = 0,
  ZS_STATION_SECRETS_NOT_FOUND,
  ZS_STATION_SECRETS_INVALID_ARGUMENT,
  ZS_STATION_SECRETS_IO_ERROR,
  ZS_STATION_SECRETS_VERIFY_FAILED
} zs_station_secrets_result_t;

typedef struct {
  void *ctx;
  bool (*read)(void *ctx, uint8_t slot, uint32_t offset, uint8_t *data, size_t size);
  bool (*erase)(void *ctx, uint8_t slot);
  bool (*write)(void *ctx, uint8_t slot, uint32_t offset, const uint8_t *data, size_t size);
} zs_station_secrets_io_t;

typedef struct {
  uint32_t version;                                     /* assigned by commit: newest stored + 1 */
  bool engineer_key_set, command_key_set, command_next_key_set;
  bool pairing_secret_set, factory_serial_set;
  uint8_t engineer_key[ZS_STATION_SECRETS_KEY_BYTES];
  char iccid[2][ZS_STATION_SECRETS_ICCID_CAPACITY];     /* empty string = not provisioned */
  uint8_t command_public_key[ZS_STATION_SECRETS_KEY_BYTES];
  uint8_t command_next_key[ZS_STATION_SECRETS_KEY_BYTES]; /* addendum E: installed by CMD_ROTATE_COMMAND_KEY */
  uint8_t pairing_secret[ZS_STATION_PAIRING_SECRET_BYTES];
  char factory_serial[ZS_STATION_FACTORY_SERIAL_CAPACITY];
} zs_station_secrets_t;

/* Newest valid record of the two slots; NOT_FOUND on a blank store. */
zs_station_secrets_result_t zs_station_secrets_load(const zs_station_secrets_io_t *io, zs_station_secrets_t *out, uint8_t *active_slot);
/* Writes `in` (version assigned) to the inactive slot and verifies it by reading it back. */
zs_station_secrets_result_t zs_station_secrets_commit(const zs_station_secrets_io_t *io, zs_station_secrets_t *in);
/* Erases both slots (factory reset / decommissioning). */
zs_station_secrets_result_t zs_station_secrets_clear(const zs_station_secrets_io_t *io);
/* Validates an ICCID string (18..22 digits). */
bool zs_station_secrets_iccid_valid(const char *iccid);
/* EVT-PRE-20 physical serials only: DIO-EVT-001..040 and DIO-EVT-B01. */
bool zs_station_factory_serial_valid(const char *serial, uint32_t *station_id);

#endif
