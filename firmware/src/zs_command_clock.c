#include "zs_command_clock.h"
#include <string.h>

void zs_command_clock_init(zs_command_clock_t *c, uint32_t network_max_age_ms) {
  if (!c) return;
  memset(c, 0, sizeof(*c));
  c->network_max_age_ms = network_max_age_ms;
}

bool zs_command_clock_set_network(zs_command_clock_t *c, int64_t epoch_us, uint32_t now_ms) {
  if (!c) return false;
  if (epoch_us < ZS_COMMAND_CLOCK_MIN_EPOCH_US || epoch_us < c->floor_us) { c->network_rejected++; return false; }
  c->network_epoch_us = epoch_us;
  c->network_anchor_ms = now_ms;
  c->network_valid = true;
  c->network_sets++;
  return true;
}

bool zs_command_clock_now(zs_command_clock_t *c, int64_t gnss_us, bool gnss_trusted, uint32_t now_ms, uint64_t *now_us) {
  int64_t t;
  if (!c || !now_us) return false;
  if (gnss_trusted && gnss_us >= ZS_COMMAND_CLOCK_MIN_EPOCH_US) {
    t = gnss_us;
    c->last_source = ZS_COMMAND_CLOCK_GNSS;
    c->gnss_reads++;
  } else if (c->network_valid && (uint32_t)(now_ms - c->network_anchor_ms) <= c->network_max_age_ms) {
    t = c->network_epoch_us + (int64_t)(uint32_t)(now_ms - c->network_anchor_ms) * 1000;
    c->last_source = ZS_COMMAND_CLOCK_NETWORK;
    c->network_reads++;
  } else {
    c->last_source = ZS_COMMAND_CLOCK_NONE;
    c->untrusted_reads++;
    return false;
  }
  if (t < c->floor_us) t = c->floor_us;          /* never backwards (GNSS re-lock jitter, anchor rounding) */
  c->floor_us = t;
  *now_us = (uint64_t)t;
  return true;
}
