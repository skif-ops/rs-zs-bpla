#ifndef ZS_GNSS_H
#define ZS_GNSS_H
#include "zs_types.h"
#include <stdbool.h>
#include <stdint.h>
/* position: the last fix (GGA: lat, lon, altitude MSL; RMC: lat, lon).  gga_quality is the GGA fix quality (0 none,
   1 GNSS, 2 DGNSS, 4/5 RTK) and gga_count counts parsed GGA sentences, so a reader can tell a new fix from an old one. */
typedef struct { zs_position_t position; uint8_t satellites; uint16_t hdop_x100; bool valid_fix; bool rmc_valid; bool utc_epoch_valid; uint16_t speed_cms; uint16_t course_cdeg; int64_t utc_epoch_us; char utc_hhmmss[12]; char utc_ddmmyy[7]; uint8_t gga_quality; uint32_t gga_count; } zs_gnss_nmea_t;
void zs_gnss_nmea_init(zs_gnss_nmea_t *g);
bool zs_gnss_parse_line(zs_gnss_nmea_t *g, const char *line);
#endif
