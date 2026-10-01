/* Station position for detections and heartbeats (zs_station_position): GNSS fixes from GGA, the installation
   record of a commissioned station and the trust verdict of the fixes against it, the encoded station map. */
#include "zs_gnss.h"
#include "zs_protocol.h"
#include "zs_station_position.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

/* a GGA at 55 deg N + north_m, 37 deg E, altitude MSL 152.3 m, HDOP 0.9, 8 satellites, with its checksum */
static void gga(char *out, size_t cap, double north_m, int quality) {
  char body[96];
  const double lat_deg = 55.0 + north_m / 111320.0;
  const double minutes = (lat_deg - 55.0) * 60.0;
  unsigned sum = 0u;
  snprintf(body, sizeof(body), "GNGGA,101500.00,55%07.4f,N,03700.0000,E,%d,08,0.90,152.3,M,14.0,M,,", minutes, quality);
  for (const char *p = body; *p; p++) sum ^= (unsigned char)*p;
  snprintf(out, cap, "$%s*%02X", body, sum & 0xffu);
}

static zs_position_trust_config_t installation(void) {
  zs_position_trust_config_t c;
  memset(&c, 0, sizeof(c));
  c.configured = true;
  c.locked = true;
  c.installation.lat_e7 = 550000000;
  c.installation.lon_e7 = 370000000;
  c.installation.alt_dm = 1500;
  c.installation.pos_accuracy_m = 2u;
  c.installation.altitude_source = 1u;
  c.installation.position_source = ZS_POSITION_SOURCE_CONFIGURED_INSTALL;
  c.warning_distance_m = 25u;
  c.suspect_distance_m = 75u;
  c.gross_jump_distance_m = 250u;
  c.warning_consecutive_fixes = 3u;
  c.suspect_consecutive_fixes = 10u;
  return c;
}

static bool feed(zs_station_position_t *sp, zs_gnss_nmea_t *nmea, double north_m, int quality, uint32_t now_ms) {
  char line[128];
  gga(line, sizeof(line), north_m, quality);
  assert(zs_gnss_parse_line(nmea, line));
  return zs_station_position_on_gnss(sp, nmea, now_ms);
}

int main(void) {
  zs_station_position_t sp;
  zs_gnss_nmea_t nmea;
  zs_position_t st;
  zs_gnss_t g;
  zs_position_trust_config_t inst = installation();

  zs_station_position_init(&sp);
  zs_gnss_nmea_init(&nmea);
  memset(&st, 0, sizeof(st));
  memset(&g, 0, sizeof(g));
  assert(!zs_station_position_fill(&sp, 0u, &st, &g));                       /* nothing known yet: nothing filled */
  assert(st.lat_e7 == 0 && st.lon_e7 == 0);

  /* no fix yet (quality 0): still unknown */
  assert(!feed(&sp, &nmea, 0.0, 0, 1000u));
  assert(!zs_station_position_fill(&sp, 1000u, &st, &g));

  /* the first fix: the GNSS position, MSL altitude, accuracy HDOP 0.9 x 4 m -> 4 m */
  assert(feed(&sp, &nmea, 0.0, 1, 2000u));
  assert(zs_station_position_fill(&sp, 2000u, &st, &g));
  assert(st.lat_e7 == 550000000 && st.lon_e7 == 370000000 && st.alt_dm == 1523);
  assert(st.position_source == ZS_POSITION_SOURCE_GNSS_LIVE && st.altitude_source == 0u && st.pos_accuracy_m == 4u);
  assert(g.fix_type == 1u && g.satellites == 8u && g.hdop_x100 == 90u);
  assert(g.position_trust == ZS_POSITION_TRUST_UNCONFIGURED && !g.position_warn && !g.position_suspect);

  /* the same GGA is not taken twice; an RMC is not a fix of the station position */
  assert(!zs_station_position_on_gnss(&sp, &nmea, 2500u));
  assert(zs_gnss_parse_line(&nmea, "$GNRMC,101501.00,A,5510.000,N,03710.000,E,0.0,0.0,011026,,,A"));
  assert(!zs_station_position_on_gnss(&sp, &nmea, 2600u));
  assert(zs_station_position_fill(&sp, 2600u, &st, &g) && st.lat_e7 == 550000000);

  /* the receiver loses the sky: the station keeps its last fix, the GNSS block says there is no fix now */
  assert(zs_station_position_fill(&sp, 2000u + ZS_STATION_POSITION_FIX_FRESH_MS + 1u, &st, &g));
  assert(st.lat_e7 == 550000000 && g.fix_type == 0u && g.satellites == 0u && g.hdop_x100 == 0u);

  /* commissioned: the installation record wins over GNSS, verdict OK until a fix says otherwise */
  zs_station_position_set_installation(&sp, &inst);
  assert(zs_station_position_fill(&sp, 3000u, &st, &g));
  assert(st.lat_e7 == 550000000 && st.alt_dm == 1500 && st.altitude_source == 1u && st.pos_accuracy_m == 2u);
  assert(st.position_source == ZS_POSITION_SOURCE_CONFIGURED_INSTALL);
  assert(g.position_trust == ZS_POSITION_TRUST_CONFIGURED_OK && !g.position_warn && g.position_delta_m == 0u);
  assert(feed(&sp, &nmea, 3.0, 1, 4000u));                                   /* 3 m off: fine */
  assert(zs_station_position_fill(&sp, 4000u, &st, &g) && g.position_trust == ZS_POSITION_TRUST_CONFIGURED_OK);
  assert(g.position_delta_m == 3u && g.fix_type == 1u);
  for (uint32_t k = 0u; k < 3u; k++) assert(feed(&sp, &nmea, 40.0, 1, 5000u + k * 1000u));   /* 40 m off, 3 fixes */
  assert(zs_station_position_fill(&sp, 7000u, &st, &g));
  assert(g.position_trust == ZS_POSITION_TRUST_CONFIGURED_WARN && g.position_warn && !g.position_suspect);
  assert(g.position_delta_m == 40u && st.lat_e7 == 550000000);              /* still the installation position */
  assert(feed(&sp, &nmea, 400.0, 1, 8000u));                                 /* a gross jump: suspect at once */
  assert(zs_station_position_fill(&sp, 8000u, &st, &g) && g.position_trust == ZS_POSITION_TRUST_CONFIGURED_SUSPECT);
  assert(g.position_warn && g.position_suspect && st.lat_e7 == 550000000);

  /* the station map as the detection carries it: configured flag (bit 2 of key 7) and the recorded position */
  {
    zs_detection_t d;
    uint8_t buf[512];
    const uint8_t lat[] = {0x00, 0x1a, 0x20, 0xc8, 0x55, 0x80};             /* key 0: uint32 550000000 */
    size_t n;
    bool found = false;
    memset(&d, 0, sizeof(d));
    d.schema_ver = 4u; d.station_id = 17u; d.seq_no = 1u; d.boot_id = 5u; d.event_id = ((uint64_t)5u << 32) | 1u;
    d.event_time_us = 1800000000000000LL;
    assert(zs_station_position_fill(&sp, 8000u, &d.station, &d.gnss));
    n = zs_protocol_encode_detection_summary(&d, buf, sizeof(buf));
    assert(n > 0u);
    for (size_t i = 0u; i + sizeof(lat) <= n; i++) if (memcmp(&buf[i], lat, sizeof(lat)) == 0) found = true;
    assert(found);
  }

  /* the record removed (recommissioning in progress): back to GNSS */
  zs_station_position_set_installation(&sp, NULL);
  assert(zs_station_position_fill(&sp, 8000u, &st, &g));
  assert(st.position_source == ZS_POSITION_SOURCE_GNSS_LIVE && fabs((double)(st.lat_e7 - 550000000) - 400.0 / 111320.0 * 1e7) < 2.0);
  assert(g.position_trust == ZS_POSITION_TRUST_UNCONFIGURED);

  puts("station_position: ok");
  return 0;
}
