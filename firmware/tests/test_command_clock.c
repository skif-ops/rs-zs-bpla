/* Command-validity clock: GNSS first, network fallback with a bounded age, monotonic floor, QLTS parsing. */
#include "zs_command_clock.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
  zs_command_clock_t c;
  uint64_t t;
  const int64_t T0 = INT64_C(1800000000000000);          /* 2027-01-15 */
  zs_command_clock_init(&c, 3600000u);                  /* network time usable for 1 h */

  /* nothing yet: untrusted (the state every target command was in before this module) */
  assert(!zs_command_clock_now(&c, 0, false, 1000u, &t) && c.last_source == ZS_COMMAND_CLOCK_NONE);
  /* GNSS trusted/holdover wins */
  assert(zs_command_clock_now(&c, T0, true, 2000u, &t) && t == (uint64_t)T0 && c.last_source == ZS_COMMAND_CLOCK_GNSS);
  /* a GNSS value before 2025 is not a time, even if flagged trusted */
  assert(!zs_command_clock_now(&c, 5, true, 2100u, &t));
  /* GNSS lost: network time (set at 10 s) propagates with the tick */
  assert(zs_command_clock_set_network(&c, T0 + 8000000, 10000u));
  assert(zs_command_clock_now(&c, 0, false, 70000u, &t) && t == (uint64_t)(T0 + 68000000) && c.last_source == ZS_COMMAND_CLOCK_NETWORK);
  /* ... until it is older than the limit */
  assert(zs_command_clock_now(&c, 0, false, 10000u + 3600000u, &t));
  assert(!zs_command_clock_now(&c, 0, false, 10000u + 3600001u, &t));
  /* network time behind the floor (a fake cell setting the clock back) and modem defaults are refused */
  assert(!zs_command_clock_set_network(&c, T0, 3700000u) && c.network_rejected == 1u);
  assert(!zs_command_clock_set_network(&c, INT64_C(946684800000000), 3700000u) && c.network_rejected == 2u);   /* 2000-01-01 */
  /* monotonic: a GNSS re-lock slightly behind the last handed-out time does not step back */
  assert(zs_command_clock_set_network(&c, T0 + 3700000000, 3700000u));
  assert(zs_command_clock_now(&c, 0, false, 3700500u, &t) && t == (uint64_t)(T0 + 3700500000));
  assert(zs_command_clock_now(&c, T0 + 3700400000, true, 3700600u, &t) && t == (uint64_t)(T0 + 3700500000));
  /* tick wrap: anchor near UINT32_MAX */
  zs_command_clock_init(&c, 3600000u);
  assert(zs_command_clock_set_network(&c, T0, 0xFFFFF000u));
  assert(zs_command_clock_now(&c, 0, false, 0x00001000u, &t) && t == (uint64_t)(T0 + 0x2000 * 1000));

  /* AT+QLTS=1 */
  {
    int64_t e;
    assert(zs_command_clock_parse_qlts("+QLTS: \"2026/09/25,08:10:05+12,0\"", &e) && e == INT64_C(1790323805000000));
    assert(zs_command_clock_parse_qlts("+QLTS: \"2024/02/29,23:59:59+00,0\"", &e) && e == INT64_C(1709251199000000));
    assert(!zs_command_clock_parse_qlts("+QLTS: \"2026/13/25,08:10:05+12,0\"", &e));
    assert(!zs_command_clock_parse_qlts("+CCLK: \"26/09/25,08:10:05+12\"", &e));
    assert(!zs_command_clock_parse_qlts("+QLTS: \"\"", &e));
  }
  printf("command clock tests passed\n");
  return 0;
}
