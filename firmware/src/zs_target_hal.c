#include "zs_target_hal.h"

bool zs_target_hal_validate(const zs_target_hal_t *h){
  return h && h->i2s_start_4ch && h->i2s_read_interleaved && h->gnss_read_time &&
         h->pps_capture && h->modem_send && h->lora_send && h->storage_append &&
         h->battery_mv && h->solar_mv && h->enter_stop2;
}
