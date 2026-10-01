#include "zs_station_position.h"

#include <string.h>

void zs_station_position_init(zs_station_position_t *sp) {
  if (!sp) return;
  memset(sp, 0, sizeof(*sp));
  zs_position_trust_init(&sp->trust);
}

void zs_station_position_set_installation(zs_station_position_t *sp, const zs_position_trust_config_t *installation) {
  if (!sp) return;
  memset(&sp->installation, 0, sizeof(sp->installation));
  if (installation && installation->configured && installation->locked) {
    sp->installation = *installation;
    sp->installation.installation.position_source = ZS_POSITION_SOURCE_CONFIGURED_INSTALL;
  }
  zs_position_trust_init(&sp->trust);         /* a new installation is judged from scratch */
  memset(&sp->last, 0, sizeof(sp->last));
  sp->checked = false;
}

static uint16_t accuracy_m(uint16_t hdop_x100) {
  uint32_t m;
  if (hdop_x100 == 0u) return 20u;            /* the receiver gave no HDOP: the ICD default */
  m = ((uint32_t)hdop_x100 * ZS_STATION_POSITION_UERE_DM + 999u) / 1000u;
  return (uint16_t)(m < 1u ? 1u : (m > 65535u ? 65535u : m));
}

bool zs_station_position_on_gnss(zs_station_position_t *sp, const zs_gnss_nmea_t *nmea, uint32_t now_ms) {
  if (!sp || !nmea || nmea->gga_count == sp->seen_gga) return false;
  sp->seen_gga = nmea->gga_count;
  sp->fix_quality = nmea->gga_quality;
  sp->satellites = nmea->satellites;
  sp->hdop_x100 = nmea->hdop_x100;
  if (!nmea->valid_fix || nmea->gga_quality == 0u) return false;
  sp->fix = nmea->position;
  sp->fix.pos_accuracy_m = accuracy_m(nmea->hdop_x100);
  sp->fix.altitude_source = 0u;               /* GNSS MSL */
  sp->fix.position_source = ZS_POSITION_SOURCE_GNSS_LIVE;
  sp->have_fix = true;
  sp->fix_ms = now_ms;
  sp->fixes++;
  if (sp->installation.configured) {
    sp->last = zs_position_trust_update(&sp->installation, &sp->trust, &sp->fix, sp->fix.pos_accuracy_m, false, false);
    sp->checked = true;
  }
  return true;
}

bool zs_station_position_fill(const zs_station_position_t *sp, uint32_t now_ms, zs_position_t *station, zs_gnss_t *gnss) {
  bool fresh;
  if (!sp || !station || !gnss) return false;
  if (!sp->installation.configured && !sp->have_fix) return false;
  fresh = sp->have_fix && (uint32_t)(now_ms - sp->fix_ms) <= ZS_STATION_POSITION_FIX_FRESH_MS;
  gnss->fix_type = fresh ? sp->fix_quality : 0u;
  gnss->satellites = fresh ? sp->satellites : 0u;
  gnss->hdop_x100 = fresh ? sp->hdop_x100 : 0u;
  if (sp->installation.configured) {
    *station = sp->installation.installation;
    gnss->position_trust = (uint8_t)(sp->checked ? sp->last.trust : ZS_POSITION_TRUST_CONFIGURED_OK);
    gnss->position_warn = sp->checked && sp->last.warning;
    gnss->position_suspect = sp->checked && sp->last.suspect;
    gnss->position_delta_m = sp->checked ? sp->last.distance_m : 0u;
  } else {
    *station = sp->fix;
    gnss->position_trust = ZS_POSITION_TRUST_UNCONFIGURED;
    gnss->position_warn = false;
    gnss->position_suspect = false;
    gnss->position_delta_m = 0u;
  }
  return true;
}
