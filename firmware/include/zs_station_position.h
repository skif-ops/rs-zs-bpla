#ifndef ZS_STATION_POSITION_H
#define ZS_STATION_POSITION_H
/*
 * Where the station stands, for every detection and heartbeat (the station map, key 8 of the detection and key 4 of
 * the heartbeat).  The server needs it to fuse the bearings of several stations; without it a detection carries
 * zeros and the station takes no part in a fused track.
 *
 *   - commissioned station (installation record of the BLE commissioning, B.6): the recorded position, source
 *     CONFIGURED_INSTALL.  Every GNSS fix is compared with it (zs_position_trust: warning / suspect after several fixes
 *     away from it) and the verdict travels in the GNSS block (position_trust, warn, suspect, distance);
 *   - not commissioned: the last GNSS fix (GGA: latitude, longitude, altitude MSL), source GNSS_LIVE, accuracy from
 *     HDOP.  A station does not move, so the last fix stays in use after the receiver loses the sky; the fix type,
 *     satellites and HDOP of the GNSS block are those of a fix younger than ZS_STATION_POSITION_FIX_FRESH_MS only;
 *   - neither: nothing is filled (the server then has no position for the station).
 *
 * Portable state, no locking: the target serialises the GNSS task (writer) against the DSP and comms tasks (readers).
 */
#include "zs_gnss.h"
#include "zs_position_trust.h"
#include "zs_types.h"

#include <stdbool.h>
#include <stdint.h>

#define ZS_STATION_POSITION_FIX_FRESH_MS 5000u
#define ZS_STATION_POSITION_UERE_DM 40u          /* user equivalent range error 4 m: horizontal accuracy = HDOP x 4 m */

typedef struct {
  zs_position_trust_config_t installation;      /* configured = false: not commissioned */
  zs_position_trust_state_t trust;
  zs_position_trust_result_t last;              /* verdict of the last fix against the installation */
  bool checked;                                 /* `last` holds a verdict */
  zs_position_t fix;                            /* the last GNSS fix */
  bool have_fix;
  uint32_t fix_ms;
  uint8_t fix_quality, satellites;
  uint16_t hdop_x100;
  uint32_t seen_gga;
  uint32_t fixes;                               /* counters for the console */
} zs_station_position_t;

void zs_station_position_init(zs_station_position_t *sp);
/* The installation record's position and trust thresholds (NULL or not configured: not commissioned). */
void zs_station_position_set_installation(zs_station_position_t *sp, const zs_position_trust_config_t *installation);
/* After zs_gnss_parse_line: takes a GGA parsed since the last call; true when it carried a fix. */
bool zs_station_position_on_gnss(zs_station_position_t *sp, const zs_gnss_nmea_t *nmea, uint32_t now_ms);
/* Fills the station position and the position part of the GNSS block (fix type, satellites, HDOP, position trust,
   warn, suspect, distance); the time fields of the GNSS block are left alone.  False (nothing filled) when the
   position is unknown. */
bool zs_station_position_fill(const zs_station_position_t *sp, uint32_t now_ms, zs_position_t *station, zs_gnss_t *gnss);

#endif
