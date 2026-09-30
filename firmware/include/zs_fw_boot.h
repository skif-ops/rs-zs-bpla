#ifndef ZS_FW_BOOT_H
#define ZS_FW_BOOT_H
/*
 * A/B boot record (MQTT_TLS_ICD_v0_1 addendum F §3): the last flash page of each bank tells the early boot guard
 * whether the image of that bank is on trial, confirmed or rolled back.  Every mark is its own 16-byte quad-word,
 * programmed once after the page erase (never rewritten), with a CRC32; the page is erased only when a new image is
 * downloaded into that bank.
 *
 *   slot 0  TRIAL     "DFWT" version previous_version   written by the old image into the new bank before the swap
 *   slot 1  CONFIRM   "DFWC" version                    the new image works (self-test + a completed session)
 *   slot 2  ROLLBACK  "DFWR" version attempts           the guard gave up: back to the other bank
 *   slot 3+ ATTEMPT i "DFWA" version i                  one per boot on trial (the guard writes it before anything)
 *
 * The guard decides on the record of the running bank: no trial / confirmed -> normal boot; attempts left -> mark the
 * attempt, start the watchdog early, run on trial; ZS_FW_BOOT_MAX_ATTEMPTS used or a rollback mark -> swap back.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_FW_BOOT_SLOT_BYTES 16u
#define ZS_FW_BOOT_MAX_ATTEMPTS 3u
#define ZS_FW_BOOT_SLOT_TRIAL 0u
#define ZS_FW_BOOT_SLOT_CONFIRM 1u
#define ZS_FW_BOOT_SLOT_ROLLBACK 2u
#define ZS_FW_BOOT_SLOT_ATTEMPT0 3u
#define ZS_FW_BOOT_RECORD_BYTES ((ZS_FW_BOOT_SLOT_ATTEMPT0 + ZS_FW_BOOT_MAX_ATTEMPTS) * ZS_FW_BOOT_SLOT_BYTES)
#define ZS_FW_BOOT_TRIAL_TIMEOUT_MS 1800000u   /* an unconfirmed trial reboots (the next attempt) after 30 min */

typedef struct {
  bool armed;              /* a valid TRIAL mark */
  uint32_t version;        /* of the TRIAL mark */
  uint32_t previous_version;
  bool confirmed;          /* a valid CONFIRM mark for that version */
  bool rolled_back;        /* the ROLLBACK slot is used (a torn mark counts) */
  unsigned attempts;       /* ATTEMPT slots used (a torn mark counts) */
} zs_fw_boot_record_t;

typedef enum {
  ZS_FW_BOOT_NORMAL = 0,   /* no trial or confirmed */
  ZS_FW_BOOT_TRIAL,        /* on trial: attempt marked, watchdog early, confirm or reboot within the trial timeout */
  ZS_FW_BOOT_ROLLBACK      /* swap back to the other bank and reset */
} zs_fw_boot_action_t;

/* The record page of one bank; offsets are within the page. */
typedef struct {
  void *ctx;
  bool (*read)(void *ctx, uint32_t offset, uint8_t *data, size_t size);
  bool (*program)(void *ctx, uint32_t offset, const uint8_t slot[ZS_FW_BOOT_SLOT_BYTES]);
} zs_fw_boot_port_t;

/* Parses the first ZS_FW_BOOT_RECORD_BYTES of a record page (an erased page is a normal, unarmed record). */
void zs_fw_boot_parse(const uint8_t bytes[ZS_FW_BOOT_RECORD_BYTES], zs_fw_boot_record_t *record);
zs_fw_boot_action_t zs_fw_boot_decide(const zs_fw_boot_record_t *record);
bool zs_fw_boot_read(const zs_fw_boot_port_t *port, zs_fw_boot_record_t *record);
/* Early boot on the running bank's record: marks the attempt (TRIAL) or the rollback (ROLLBACK); a TRIAL whose
   attempt cannot be marked becomes ROLLBACK (an uncounted trial could loop forever). */
zs_fw_boot_action_t zs_fw_boot_guard(const zs_fw_boot_port_t *port, zs_fw_boot_record_t *record);
/* The old image arms the freshly written bank (its record page is erased by the download). */
bool zs_fw_boot_arm(const zs_fw_boot_port_t *other_bank, uint32_t version, uint32_t previous_version);
/* The running image on trial proved itself; true also when it is not on trial / already confirmed. */
bool zs_fw_boot_confirm(const zs_fw_boot_port_t *port, zs_fw_boot_record_t *record);
const char *zs_fw_boot_action_name(zs_fw_boot_action_t action);

#endif
