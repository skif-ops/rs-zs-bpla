#include "zs_command_clock.h"
#include <stdio.h>
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

static int64_t days_from_civil(int y, unsigned m, unsigned d) {   /* H. Hinnant's algorithm, proleptic Gregorian */
  const int yy = y - (m <= 2u);
  const int era = (yy >= 0 ? yy : yy - 399) / 400;
  const unsigned yoe = (unsigned)(yy - era * 400);
  const unsigned doy = (153u * (m + (m > 2u ? (unsigned)-3 : 9u)) + 2u) / 5u + d - 1u;
  const unsigned doe = yoe * 365u + yoe / 4u - yoe / 100u + doy;
  return (int64_t)era * 146097 + (int64_t)doe - 719468;
}

bool zs_command_clock_parse_qlts(const char *line, int64_t *epoch_us) {
  int y, mo, d, h, mi, s;
  const char *p;
  if (!line || !epoch_us || strncmp(line, "+QLTS: \"", 8u) != 0) return false;
  p = line + 8;
  if (sscanf(p, "%4d/%2d/%2d,%2d:%2d:%2d", &y, &mo, &d, &h, &mi, &s) != 6) return false;
  if (y < 2000 || mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 60 || h < 0 || mi < 0 || s < 0) return false;
  *epoch_us = ((days_from_civil(y, (unsigned)mo, (unsigned)d) * 86400 + h * 3600 + mi * 60 + s) * INT64_C(1000000));
  return true;
}
