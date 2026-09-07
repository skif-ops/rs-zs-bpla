#ifndef ZS_TARGET_HAL_H
#define ZS_TARGET_HAL_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

/* Board-specific contracts for STM32U585 EVT integration. */
typedef struct {
    bool (*i2s_start_4ch)(uint32_t sample_rate_hz, uint8_t bits_per_sample);
    size_t (*i2s_read_interleaved)(int32_t *dst, size_t frames);
    bool (*gnss_read_time)(int64_t *utc_us, uint32_t *uncertainty_us);
    bool (*pps_capture)(uint64_t *timer_ticks);
    bool (*modem_send)(const uint8_t *data, size_t len);
    bool (*lora_send)(const uint8_t *data, size_t len);
    bool (*storage_append)(const uint8_t *data, size_t len);
    uint16_t (*battery_mv)(void);
    uint16_t (*solar_mv)(void);
    void (*enter_stop2)(void);
} zs_target_hal_t;

bool zs_target_hal_validate(const zs_target_hal_t *hal);
#endif
