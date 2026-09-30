/* MQTT ICD addendum F, A/B boot record: the guard on a RAM record page with flash semantics (quad-words programmed
   once after the erase).  Normal boot, arming by the old image, three trial attempts, the rollback mark and a
   repeated rollback, confirmation (no further attempts), torn and corrupted marks, a failing program. */
#include "zs_fw_boot.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct { uint8_t mem[256]; unsigned programs, fail_at; } page_t;
static bool p_read(void *c, uint32_t o, uint8_t *d, size_t n) { page_t *p = c; if (o + n > sizeof(p->mem)) return false; memcpy(d, &p->mem[o], n); return true; }
static bool p_program(void *c, uint32_t o, const uint8_t slot[ZS_FW_BOOT_SLOT_BYTES]) {
  page_t *p = c;
  if (o % ZS_FW_BOOT_SLOT_BYTES || o + ZS_FW_BOOT_SLOT_BYTES > sizeof(p->mem)) return false;
  if (++p->programs == p->fail_at) return false;
  for (unsigned i = 0u; i < ZS_FW_BOOT_SLOT_BYTES; i++) if (p->mem[o + i] != 0xffu) return false;
  memcpy(&p->mem[o], slot, ZS_FW_BOOT_SLOT_BYTES);
  return true;
}

int main(void) {
  static page_t page;
  const zs_fw_boot_port_t port = {&page, p_read, p_program};
  zs_fw_boot_record_t rec;

  /* factory flash: an erased record is a normal boot, nothing is written */
  memset(page.mem, 0xff, sizeof(page.mem));
  assert(zs_fw_boot_guard(&port, &rec) == ZS_FW_BOOT_NORMAL && !rec.armed && page.programs == 0u);

  /* the old image arms the new bank; three boots on trial, the fourth swaps back, and keeps swapping back */
  assert(zs_fw_boot_arm(&port, 8u, 7u));
  assert(zs_fw_boot_read(&port, &rec) && rec.armed && rec.version == 8u && rec.previous_version == 7u && rec.attempts == 0u);
  assert(!zs_fw_boot_arm(&port, 9u, 8u));                                    /* the trial slot is programmed once */
  for (unsigned i = 1u; i <= ZS_FW_BOOT_MAX_ATTEMPTS; i++) { assert(zs_fw_boot_guard(&port, &rec) == ZS_FW_BOOT_TRIAL && rec.attempts == i); }
  assert(zs_fw_boot_guard(&port, &rec) == ZS_FW_BOOT_ROLLBACK && rec.rolled_back);
  assert(zs_fw_boot_read(&port, &rec) && rec.rolled_back && rec.attempts == 3u && !rec.confirmed);
  assert(zs_fw_boot_guard(&port, &rec) == ZS_FW_BOOT_ROLLBACK);              /* the swap did not happen: again */
  assert(!zs_fw_boot_confirm(&port, &rec) || rec.confirmed);                 /* too late to matter, never harmful */

  /* confirmed after the first trial boot: normal from then on, no more attempt marks */
  memset(page.mem, 0xff, sizeof(page.mem)); page.programs = 0u;
  assert(zs_fw_boot_arm(&port, 8u, 7u));
  assert(zs_fw_boot_guard(&port, &rec) == ZS_FW_BOOT_TRIAL);
  assert(zs_fw_boot_confirm(&port, &rec) && rec.confirmed);
  { const unsigned before = page.programs; assert(zs_fw_boot_guard(&port, &rec) == ZS_FW_BOOT_NORMAL && page.programs == before); }
  assert(zs_fw_boot_confirm(&port, &rec));                                    /* idempotent */
  assert(zs_fw_boot_decide(&rec) == ZS_FW_BOOT_NORMAL);

  /* a torn attempt mark counts as an attempt; a torn trial mark is no trial */
  memset(page.mem, 0xff, sizeof(page.mem));
  assert(zs_fw_boot_arm(&port, 8u, 7u));
  page.mem[ZS_FW_BOOT_SLOT_ATTEMPT0 * ZS_FW_BOOT_SLOT_BYTES + 5u] = 0x00u;
  assert(zs_fw_boot_guard(&port, &rec) == ZS_FW_BOOT_TRIAL && rec.attempts == 2u);
  page.mem[3] ^= 0x01u;                                                       /* the trial mark's magic */
  assert(zs_fw_boot_guard(&port, &rec) == ZS_FW_BOOT_NORMAL && !rec.armed);

  /* a confirm mark of another version does not confirm this trial */
  memset(page.mem, 0xff, sizeof(page.mem));
  assert(zs_fw_boot_arm(&port, 8u, 7u));
  {
    page_t other; const zs_fw_boot_port_t oport = {&other, p_read, p_program}; zs_fw_boot_record_t orec;
    memset(other.mem, 0xff, sizeof(other.mem)); other.programs = other.fail_at = 0u;
    assert(zs_fw_boot_arm(&oport, 9u, 8u) && zs_fw_boot_read(&oport, &orec));
    assert(zs_fw_boot_confirm(&oport, &orec) && orec.confirmed);
    memcpy(&page.mem[ZS_FW_BOOT_SLOT_CONFIRM * ZS_FW_BOOT_SLOT_BYTES], &other.mem[ZS_FW_BOOT_SLOT_CONFIRM * ZS_FW_BOOT_SLOT_BYTES], ZS_FW_BOOT_SLOT_BYTES);
  }
  assert(zs_fw_boot_read(&port, &rec) && rec.armed && !rec.confirmed && zs_fw_boot_decide(&rec) == ZS_FW_BOOT_TRIAL);

  /* an attempt that cannot be marked must not run uncounted: roll back */
  memset(page.mem, 0xff, sizeof(page.mem)); page.programs = 0u;
  assert(zs_fw_boot_arm(&port, 8u, 7u));
  page.fail_at = page.programs + 1u;
  assert(zs_fw_boot_guard(&port, &rec) == ZS_FW_BOOT_ROLLBACK);
  page.fail_at = 0u;
  assert(zs_fw_boot_read(&port, &rec) && rec.rolled_back);                   /* the rollback mark went in */

  /* an unreadable page decides nothing */
  { const zs_fw_boot_port_t broken = {&page, NULL, p_program}; assert(zs_fw_boot_guard(&broken, &rec) == ZS_FW_BOOT_NORMAL); }
  assert(!zs_fw_boot_arm(&port, 0u, 7u));
  assert(strcmp(zs_fw_boot_action_name(ZS_FW_BOOT_ROLLBACK), "rollback") == 0);

  puts("zs_fw_boot_tests: OK");
  return 0;
}
