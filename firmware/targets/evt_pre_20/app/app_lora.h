#ifndef APP_LORA_H
#define APP_LORA_H
/*
 * LoRa fallback task (LORA_BACKUP_ICD_v0_1 addendum A): zs_lora_uplink over the SX1262 on SPI1.  The regional gate
 * of the ICD applies: with APP_LORA_TX_ENABLED == 0 the task runs DRY - it brings the radio up (SPI/BUSY/reset are
 * exercised on the bench), encodes every frame the uplink would send, logs it to the console with its airtime, and
 * never asserts TXEN nor issues SetTx.  Setting APP_LORA_TX_ENABLED to 1 (after the signed RU868 profile and the RF
 * gate) turns the same path into the live transport.
 */
#include "zs_event_outbox.h"
#include "zs_lora_frame.h"
#include <stdbool.h>
#include <stdint.h>

/* Outbox to drain, station id, the engineer key (LoRa key derives from it; NULL keeps the uplink inactive). */
void app_lora_bind(const zs_event_outbox_io_t *outbox, uint32_t station_id, const uint8_t engineer_key[32], void (*log)(const char *fmt, ...));
/* Detection fields for the compact frame (called from the DSP task when an event is emitted). */
void app_lora_remember_event(uint64_t event_id, uint8_t class_id, uint8_t confidence_u8, uint8_t presence_level, uint16_t f0_hz);
/* Route hint from the supervisor: true while the GSM link is degraded. */
void app_lora_set_route_hint(bool lora_preferred);
void app_lora_task(void *arg);
void app_lora_status(void (*print)(const char *fmt, ...));
#endif
