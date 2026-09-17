#include "zs_gnss.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

static bool checksum_ok(const char *s) {
  if (!s || *s != '$') return false;
  const char *star = strchr(s, '*');
  if (!star) return true;
  unsigned checksum = 0;
  for (const char *p = s + 1; p < star; p++) checksum ^= (unsigned char)*p;
  const unsigned received = strtoul(star + 1, NULL, 16);
  return (checksum & 255u) == (received & 255u);
}

static int split(char *buffer, char *values[], int max_values) {
  int count = 0;
  char *p = buffer;
  while (count < max_values) {
    values[count++] = p;
    char *comma = strchr(p, ',');
    if (!comma) break;
    *comma = 0;
    p = comma + 1;
  }
  return count;
}

static int32_t coord_e7(const char *text, char hemisphere) {
  if (!text || !*text) return 0;
  const double value = strtod(text, NULL);
  const double degrees = floor(value / 100.0);
  const double minutes = value - degrees * 100.0;
  double result = degrees + minutes / 60.0;
  if (hemisphere == 'S' || hemisphere == 'W') result = -result;
  return (int32_t)llround(result * 1e7);
}

static int64_t days_from_civil(int year, unsigned month, unsigned day) {
  year -= month <= 2u;
  const int era = (year >= 0 ? year : year - 399) / 400;
  const unsigned yoe = (unsigned)(year - era * 400);
  const unsigned month_prime = month > 2u ? month - 3u : month + 9u;
  const unsigned doy = (153u * month_prime + 2u) / 5u + day - 1u;
  const unsigned doe = yoe * 365u + yoe / 4u - yoe / 100u + doy;
  return (int64_t)era * 146097 + (int64_t)doe - 719468;
}

static bool parse_rmc_epoch(const char *time, const char *date, int64_t *epoch_us) {
  if (!time || !date || !epoch_us || strlen(time) < 6u || strlen(date) < 6u) return false;
  const int hour = (time[0] - '0') * 10 + time[1] - '0';
  const int minute = (time[2] - '0') * 10 + time[3] - '0';
  const int second = (time[4] - '0') * 10 + time[5] - '0';
  const unsigned day = (unsigned)((date[0] - '0') * 10 + date[1] - '0');
  const unsigned month = (unsigned)((date[2] - '0') * 10 + date[3] - '0');
  const int yy = (date[4] - '0') * 10 + date[5] - '0';
  const int year = yy >= 80 ? 1900 + yy : 2000 + yy;
  if (hour > 23 || minute > 59 || second > 60 || day < 1u || day > 31u || month < 1u || month > 12u) return false;
  *epoch_us = (days_from_civil(year, month, day) * 86400 + hour * 3600 + minute * 60 + second) * 1000000;
  return true;
}

void zs_gnss_nmea_init(zs_gnss_nmea_t *g) {
  if (g) memset(g, 0, sizeof(*g));
}

bool zs_gnss_parse_line(zs_gnss_nmea_t *g, const char *line) {
  if (!g || !line || !checksum_ok(line)) return false;
  char buffer[160];
  const size_t length = strlen(line);
  if (length >= sizeof(buffer)) return false;
  memcpy(buffer, line, length + 1u);
  char *star = strchr(buffer, '*');
  if (star) *star = 0;
  char *values[24];
  const int count = split(buffer, values, 24);
  if (count < 2) return false;

  if (strstr(values[0], "GGA")) {
    if (count < 10) return false;
    strncpy(g->utc_hhmmss, values[1], sizeof(g->utc_hhmmss) - 1u);
    const int fix = atoi(values[6]);
    g->satellites = (uint8_t)atoi(values[7]);
    g->hdop_x100 = (uint16_t)lround(strtod(values[8], NULL) * 100.0);
    g->valid_fix = fix > 0;
    if (g->valid_fix) {
      g->position.lat_e7 = coord_e7(values[2], values[3][0]);
      g->position.lon_e7 = coord_e7(values[4], values[5][0]);
      g->position.alt_dm = (int32_t)lround(strtod(values[9], NULL) * 10.0);
      g->position.altitude_source = 1;
    }
    return true;
  }

  if (strstr(values[0], "RMC")) {
    if (count < 10) return false;
    strncpy(g->utc_hhmmss, values[1], sizeof(g->utc_hhmmss) - 1u);
    strncpy(g->utc_ddmmyy, values[9], sizeof(g->utc_ddmmyy) - 1u);
    g->utc_epoch_valid = parse_rmc_epoch(values[1], values[9], &g->utc_epoch_us);
    g->rmc_valid = values[2][0] == 'A';
    if (g->rmc_valid) {
      g->position.lat_e7 = coord_e7(values[3], values[4][0]);
      g->position.lon_e7 = coord_e7(values[5], values[6][0]);
      const double knots = strtod(values[7], NULL);
      g->speed_cms = (uint16_t)lround(knots * 0.514444 * 100.0);
      g->course_cdeg = (uint16_t)lround(strtod(values[8], NULL) * 100.0);
    }
    return true;
  }
  return false;
}
