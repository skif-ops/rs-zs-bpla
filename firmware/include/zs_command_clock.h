#ifndef ZS_COMMAND_CLOCK_H
#define ZS_COMMAND_CLOCK_H
/*
 * Wall time for the validity check of signed commands (MQTT_TLS_ICD_v0_1 §2.1: execution only inside
 * [created_time_us, expires_time_us), a station without sufficiently trusted time rejects the command).
 *
 * Sources, in order: GNSS/PPS-disciplined time when its trust is GNSS_TRUSTED or HOLDOVER; otherwise the last
 * network time (NITZ, e.g. BG95 AT+QLTS=1) propagated with the MCU tick for at most `network_max_age_ms`.  The
 * command TTL is 15 minutes, so seconds of network-time error are harmless, while without this fallback a station
 * that lost its GNSS fix could not receive the very command meant to recover it.  Network time is not
 * authenticated (a fake base station can set it), but commands only arrive over the mutually authenticated MQTT
 * session and are signed, so a wrong clock can only make valid commands expire early or stale queued commands
 * look fresh; the second case is bounded by a monotonic floor: the clock never hands out a time earlier than one it
 * already handed out, and a network time behind that floor is refused.  Portable, host-tested.
 */
#include <stdbool.h>
#include <stdint.h>

#define ZS_COMMAND_CLOCK_MIN_EPOCH_US INT64_C(1735689600000000)   /* 2025-01-01: earlier values are modem defaults */

typedef enum { ZS_COMMAND_CLOCK_NONE = 0, ZS_COMMAND_CLOCK_GNSS = 1, ZS_COMMAND_CLOCK_NETWORK = 2 } zs_command_clock_source_t;

typedef struct {
  int64_t network_epoch_us;
  uint32_t network_anchor_ms, network_max_age_ms;
  bool network_valid;
  int64_t floor_us;                     /* highest time handed out so far */
  uint8_t last_source;                  /* zs_command_clock_source_t of the last successful read */
  uint32_t gnss_reads, network_reads, untrusted_reads, network_sets, network_rejected;
} zs_command_clock_t;

void zs_command_clock_init(zs_command_clock_t *c, uint32_t network_max_age_ms);
/* Network time observed at `now_ms`; false when implausible (before 2025) or behind the monotonic floor. */
bool zs_command_clock_set_network(zs_command_clock_t *c, int64_t epoch_us, uint32_t now_ms);
/* Time for a command check at `now_ms`.  `gnss_us`/`gnss_trusted`: the PPS-disciplined time and whether its trust is
   GNSS_TRUSTED or HOLDOVER.  Returns false (time untrusted) when neither source is usable. */
bool zs_command_clock_now(zs_command_clock_t *c, int64_t gnss_us, bool gnss_trusted, uint32_t now_ms, uint64_t *now_us);
/* Parses the BG95 reply `+QLTS: "yyyy/MM/dd,hh:mm:ss±zz,dst"` of AT+QLTS=1 (time in GMT; the zone field is informative). */
bool zs_command_clock_parse_qlts(const char *line, int64_t *epoch_us);
#endif
