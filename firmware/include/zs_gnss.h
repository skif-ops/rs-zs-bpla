#ifndef ZS_GNSS_H
#define ZS_GNSS_H
#include "zs_types.h"
#include <stdbool.h>
#include <stdint.h>
typedef struct { zs_position_t position; uint8_t satellites; uint16_t hdop_x100; bool valid_fix; bool rmc_valid; uint16_t speed_cms; uint16_t course_cdeg; char utc_hhmmss[12]; } zs_gnss_nmea_t;
void zs_gnss_nmea_init(zs_gnss_nmea_t *g);
bool zs_gnss_parse_line(zs_gnss_nmea_t *g, const char *line);
#endif
