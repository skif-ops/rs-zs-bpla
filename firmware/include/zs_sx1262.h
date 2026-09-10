#ifndef ZS_SX1262_H
#define ZS_SX1262_H
#include "zs_hal_port.h"
#include <stdint.h>
#include <stdbool.h>
typedef struct { zs_hal_port_t io; unsigned spi_bus,nss_gpio,busy_gpio,reset_gpio; uint32_t frequency_hz; uint8_t sf,bw_code,cr_code; } zs_sx1262_t;
extern const uint32_t zs_ru868_candidate_channels_hz[7];
bool zs_sx1262_frequency_allowed_ru868(uint32_t frequency_hz);
void zs_sx1262_init(zs_sx1262_t*r,const zs_hal_port_t*io,unsigned spi,unsigned nss,unsigned busy,unsigned reset);
bool zs_sx1262_reset(zs_sx1262_t*r);
bool zs_sx1262_set_standby(zs_sx1262_t*r);
bool zs_sx1262_set_sleep(zs_sx1262_t*r);
bool zs_sx1262_set_frequency(zs_sx1262_t*r,uint32_t hz);
bool zs_sx1262_set_lora_modulation(zs_sx1262_t*r,uint8_t sf,uint32_t bandwidth_hz,uint8_t cr_denominator);
bool zs_sx1262_start_rx_duty_cycle(zs_sx1262_t*r,uint32_t rx_us,uint32_t sleep_us);
#endif
