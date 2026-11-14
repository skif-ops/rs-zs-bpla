#ifndef ZS_LORA_FRAME_H
#define ZS_LORA_FRAME_H
/*
 * LoRa uplink frames (LORA_UPLINK_ICD_v0_1): the fallback transport for detection events when the GSM link is
 * degraded.  One event fits a 38-byte frame (vs ~230 bytes of detection CBOR); the gateway forwards it to the
 * server and answers with a 21-byte ACK only after the server accepted the event, so the outbox semantics stay
 * the same as over MQTT (delivered = application receipt).  Integrity: HMAC-SHA256 truncated to 8 bytes with a
 * key derived from the station's engineer key (both sides have it: station secrets record, server registry).
 * All multi-byte fields are little-endian.  This is the compact single-hop event uplink of
 * LORA_BACKUP_ICD_v0_1 addendum A: the regional profile gate (tx_enabled) of the ICD applies unchanged; AEAD /
 * relay hops / fragmentation of ICD §3 remain pending the security review and are not replaced here.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_LORA_FRAME_EVENT_TYPE 0x10u
#define ZS_LORA_FRAME_ACK_TYPE 0x90u
#define ZS_LORA_EVENT_FRAME_BYTES 38u
#define ZS_LORA_ACK_FRAME_BYTES 21u
#define ZS_LORA_TAG_BYTES 8u
#define ZS_LORA_KEY_BYTES 32u
#define ZS_LORA_KEY_CONTEXT "DIO-LORA-V1"

#define ZS_LORA_EVENT_FLAG_RETRY 0x01u        /* not the first transmission of this event */
#define ZS_LORA_EVENT_FLAG_GSM_DEGRADED 0x02u /* sent because the GSM link was marked degraded */

typedef struct {
  uint16_t profile_id;                    /* regional profile id of the signed RU868/EU868 profile (ICD v0.1 §2) */
  uint32_t station_id, boot_id, seq_no;   /* event_id = (boot_id << 32) | seq_no */
  uint32_t time_s;                        /* unix seconds of the event */
  uint16_t time_ms;
  uint8_t class_id, confidence_u8, presence_level;
  uint16_t f0_hz;
  uint16_t battery_mv;
  uint8_t battery_pct;
  uint8_t flags;
} zs_lora_event_t;

/* key = SHA-256(ZS_LORA_KEY_CONTEXT || engineer_key) */
void zs_lora_derive_key(const uint8_t engineer_key[32], uint8_t key[ZS_LORA_KEY_BYTES]);

/* Encodes an event frame (exactly ZS_LORA_EVENT_FRAME_BYTES); false on a bad argument. */
bool zs_lora_encode_event(const zs_lora_event_t *e, const uint8_t key[ZS_LORA_KEY_BYTES], uint8_t out[ZS_LORA_EVENT_FRAME_BYTES]);
/* Decodes and authenticates an event frame. */
bool zs_lora_decode_event(const uint8_t *frame, size_t n, const uint8_t key[ZS_LORA_KEY_BYTES], zs_lora_event_t *e);
/* ACK from the gateway for one event (after the server accepted it). */
bool zs_lora_encode_ack(uint32_t station_id, uint32_t boot_id, uint32_t seq_no, const uint8_t key[ZS_LORA_KEY_BYTES], uint8_t out[ZS_LORA_ACK_FRAME_BYTES]);
bool zs_lora_decode_ack(const uint8_t *frame, size_t n, const uint8_t key[ZS_LORA_KEY_BYTES], uint32_t *station_id, uint32_t *boot_id, uint32_t *seq_no);

/* Time on air in milliseconds for a LoRa payload (explicit header, CRC on, preamble 8, low data-rate optimisation
   as the SX1262 requires it for SF11/SF12 at 125 kHz). */
uint32_t zs_lora_airtime_ms(size_t payload_bytes, uint8_t sf, uint32_t bandwidth_hz, uint8_t cr_denominator);

#endif
