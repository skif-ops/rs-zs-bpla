#ifndef APP_LORA_H
#define APP_LORA_H
/* SX1262 fallback uplink. Field TX needs a verified persistent RU868 profile. RF test TX is time-limited, available
   only in physical service mode and never changes the persistent field authorization. */
#include "zs_event_outbox.h"
#include "zs_lora_frame.h"
#include "zs_lora_rf_profile.h"
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>

/* Outbox to drain, station id, the engineer key (LoRa key derives from it; NULL keeps the uplink inactive). */
void app_lora_bind(const zs_event_outbox_io_t *outbox, uint32_t station_id, const uint8_t engineer_key[32], void (*log)(const char *fmt, ...));
/* Detection fields for the compact frame (called from the DSP task when an event is emitted). */
void app_lora_remember_event(uint64_t event_id, uint8_t class_id, uint8_t confidence_u8, uint8_t presence_level, uint16_t f0_hz);
/* Route hint from the supervisor: true while the GSM link is degraded. */
void app_lora_set_route_hint(bool lora_preferred);
void app_lora_set_service_mode(bool active);
bool app_lora_start_rf_test(uint32_t seconds);
void app_lora_stop_rf_test(void);
void app_lora_set_field_profile(const zs_lora_rf_profile_t *profile);
void app_lora_clear_field_profile(void);
size_t app_lora_encode_status(uint8_t *out, size_t capacity);
void app_lora_task(void *arg);
void app_lora_status(void (*print)(const char *fmt, ...));
#endif
