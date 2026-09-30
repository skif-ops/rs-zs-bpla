#ifndef ZS_FW_UPDATE_H
#define ZS_FW_UPDATE_H
/*
 * Firmware update over MQTT (MQTT_TLS_ICD_v0_1 addendum F): the release manifest and its offline signature, the
 * image information block, the fwreq/fw messages and the download engine that fills the inactive flash bank.
 *
 *   CMD_UPDATE_FIRMWARE {0: manifest, 1: release key id, 2: release signature}
 *     -> zs_fw_update_check (key, Ed25519 over "DIO-FW-V1" || manifest, target, version, size)
 *     -> zs_fw_download_start (erase) -> request/chunk pairs, stop-and-wait -> SHA-256 read back + .fw_info
 *     -> FINISHED with an ACK result (OK / FAILED detail)
 *
 * The engine is portable: flash access goes through zs_fw_image_io_t (the target programs the other bank of the
 * STM32U585, the twin a RAM bank).  Every call does bounded work (a few pages erased, one chunk programmed, a few KiB
 * hashed) so the comms task keeps its watchdog window.
 */
#include "zs_command.h"
#include "zs_sha256.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_FW_MANIFEST_MAX_BYTES 96u
#define ZS_FW_RELEASE_KEY_ID_BYTES 8u
#define ZS_FW_RELEASE_SIGNATURE_BYTES 64u
#define ZS_FW_RELEASE_PUBLIC_KEY_BYTES 32u
#define ZS_FW_RELEASE_KEYS_MAX 2u
#define ZS_FW_SIGN_DOMAIN "DIO-FW-V1"
#define ZS_FW_SIGN_DOMAIN_BYTES 9u
#define ZS_FW_MANIFEST_SCHEMA 1u
#define ZS_FW_TARGET_STM32_APP 1u      /* EVT-PRE-20 STM32U585 application */
#define ZS_FW_TARGET_NRF52 2u          /* reserved (nRF52840 image, addendum C.6 path today) */

#define ZS_FW_INFO_OFFSET 0x400u
#define ZS_FW_INFO_BYTES 32u
#define ZS_FW_INFO_MAGIC 0x464F4944u   /* "DIOF" little-endian */
#define ZS_FW_INFO_FORMAT 1u

#define ZS_FW_MESSAGE_SCHEMA 1u
#define ZS_FW_REQUEST_MESSAGE_TYPE 8u
#define ZS_FW_CHUNK_MESSAGE_TYPE 9u
#define ZS_FW_CHUNK_BYTES 1024u
#define ZS_FW_REQUEST_MAX_BYTES 48u
#define ZS_FW_CHUNK_MESSAGE_MAX_BYTES (ZS_FW_CHUNK_BYTES + 48u)
#define ZS_FW_PROGRAM_ALIGN 16u        /* STM32U5 quad-word; the last one is padded with 0xFF */

/* ACK details (addendum F §3) */
#define ZS_FW_REJECT_UNSUPPORTED 1u
#define ZS_FW_REJECT_MANIFEST 2u
#define ZS_FW_REJECT_TARGET 3u
#define ZS_FW_REJECT_VERSION 4u
#define ZS_FW_REJECT_SIZE 5u
#define ZS_FW_REJECT_BUSY 6u
#define ZS_FW_REJECT_TRIAL 7u
#define ZS_FW_FAIL_FLASH 1u
#define ZS_FW_FAIL_SHA256 2u
#define ZS_FW_FAIL_INFO 3u
#define ZS_FW_FAIL_STALLED 4u

/* The .fw_info block every application image carries at ZS_FW_INFO_OFFSET (the linker places it). */
typedef struct {
  uint32_t magic;
  uint16_t format;
  uint16_t target;
  uint32_t version;
  uint8_t reserved[20];
} zs_fw_info_t;

typedef struct {
  uint32_t target;
  uint32_t version;
  uint32_t size;
  uint8_t sha256[ZS_SHA256_DIGEST_BYTES];
} zs_fw_manifest_t;

typedef struct {
  uint8_t public_key[ZS_FW_RELEASE_PUBLIC_KEY_BYTES];
} zs_fw_release_key_t;

/* The running station as the check sees it. */
typedef struct {
  const zs_fw_release_key_t *keys;   /* compiled-in release keys; NULL/0 = OTA unsupported (REJECTED 1) */
  size_t key_count;
  uint32_t target;                   /* ZS_FW_TARGET_* of this station */
  uint32_t running_version;          /* .fw_info of the running image */
  uint32_t capacity;                 /* bytes of the image area of the other bank */
  bool trial;                        /* the running image is on trial (not confirmed yet) */
} zs_fw_station_t;

/* Parses a .fw_info block (32 bytes, little-endian); false when the magic/format is not ours. */
bool zs_fw_info_parse(const uint8_t bytes[ZS_FW_INFO_BYTES], zs_fw_info_t *info);
void zs_fw_info_encode(uint32_t target, uint32_t version, uint8_t out[ZS_FW_INFO_BYTES]);

/* Strict canonical decode of the manifest map. */
bool zs_fw_manifest_decode(const uint8_t *bytes, size_t size, zs_fw_manifest_t *manifest);
/* Release key id of a raw public key (first 8 bytes of its SHA-256). */
void zs_fw_release_key_id(const uint8_t public_key[ZS_FW_RELEASE_PUBLIC_KEY_BYTES], uint8_t key_id[ZS_FW_RELEASE_KEY_ID_BYTES]);
/* Checks a CMD_UPDATE_FIRMWARE payload against the station: 0 = acceptable (*manifest set), otherwise the
   REJECTED detail (ZS_FW_REJECT_*; BUSY is the caller's). */
uint16_t zs_fw_update_check(const zs_update_firmware_command_t *cmd, const zs_fw_station_t *station, zs_fw_manifest_t *manifest);

/* fwreq / fw messages */
size_t zs_fw_request_encode(uint32_t station_id, const uint8_t command_id[ZS_COMMAND_UUID_BYTES], uint32_t offset,
                            uint32_t length, uint8_t *out, size_t cap);
typedef struct {
  uint32_t station_id;
  uint8_t command_id[ZS_COMMAND_UUID_BYTES];
  uint32_t offset;
  const uint8_t *data;
  size_t data_len;
} zs_fw_chunk_t;
bool zs_fw_chunk_decode(const uint8_t *bytes, size_t size, zs_fw_chunk_t *chunk);
bool zs_fw_request_decode(const uint8_t *bytes, size_t size, uint32_t *station_id, uint8_t command_id[ZS_COMMAND_UUID_BYTES],
                          uint32_t *offset, uint32_t *length);

/* ---- download engine ---- */
typedef struct {
  void *ctx;
  uint32_t capacity;       /* image area of the other bank */
  uint32_t page_bytes;     /* erase granularity */
  uint32_t record_offset;  /* boot record page of the other bank (erased with the image), 0 = none */
  bool (*erase)(void *ctx, uint32_t offset, uint32_t size);                        /* page-aligned */
  bool (*program)(void *ctx, uint32_t offset, const uint8_t *data, size_t size);  /* ZS_FW_PROGRAM_ALIGN-aligned */
  bool (*read)(void *ctx, uint32_t offset, uint8_t *data, size_t size);
} zs_fw_image_io_t;

typedef enum {
  ZS_FW_DOWNLOAD_IDLE = 0,
  ZS_FW_DOWNLOAD_ERASING,
  ZS_FW_DOWNLOAD_FETCHING,
  ZS_FW_DOWNLOAD_VERIFYING,
  ZS_FW_DOWNLOAD_FINISHED
} zs_fw_download_state_t;

typedef enum {
  ZS_FW_STEP_BUSY = 0,       /* more local work (erase/verify): call again */
  ZS_FW_STEP_NEED_CHUNK,     /* a request for dl->offset should be outstanding */
  ZS_FW_STEP_FINISHED,       /* dl->result / dl->detail hold the ACK */
  ZS_FW_STEP_IDLE
} zs_fw_step_t;

typedef enum {
  ZS_FW_CHUNK_ACCEPTED = 0,  /* programmed; dl->offset advanced */
  ZS_FW_CHUNK_IGNORED,       /* not the chunk we wait for (other command, offset, length): skipped */
  ZS_FW_CHUNK_FAILED         /* flash error: the download FINISHED with FAILED */
} zs_fw_chunk_result_t;

typedef struct {
  const zs_fw_image_io_t *io;
  zs_fw_download_state_t state;
  uint32_t station_id;
  uint8_t command_id[ZS_COMMAND_UUID_BYTES];
  zs_fw_manifest_t manifest;
  uint32_t erase_offset, erase_end;
  uint32_t offset;           /* next image byte wanted */
  uint32_t verify_offset;
  uint32_t chunks;
  zs_sha256_t sha;
  zs_command_ack_result_t result;
  uint16_t detail;
} zs_fw_download_t;

bool zs_fw_download_start(zs_fw_download_t *dl, const zs_fw_image_io_t *io, uint32_t station_id,
                          const uint8_t command_id[ZS_COMMAND_UUID_BYTES], const zs_fw_manifest_t *manifest);
/* Bounded local work; `budget_bytes` limits the hash read per call (erase: one page per 64 KiB of budget, >= 1). */
zs_fw_step_t zs_fw_download_step(zs_fw_download_t *dl, uint32_t budget_bytes);
/* Length of the chunk to request at dl->offset (0 when nothing is wanted). */
uint32_t zs_fw_download_want(const zs_fw_download_t *dl);
size_t zs_fw_download_request(const zs_fw_download_t *dl, uint8_t *out, size_t cap);
zs_fw_chunk_result_t zs_fw_download_on_chunk(zs_fw_download_t *dl, const zs_fw_chunk_t *chunk);
/* Ends the download with FAILED/detail (stalled) without touching the flash. */
void zs_fw_download_fail(zs_fw_download_t *dl, uint16_t detail);
bool zs_fw_download_active(const zs_fw_download_t *dl);
void zs_fw_download_abort(zs_fw_download_t *dl);

#endif
