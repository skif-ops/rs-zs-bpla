#include "zs_selftest.h"

#include "zs_cbor.h"

#include <string.h>

void zs_selftest_init(zs_selftest_registry_t *r) {
  if (r) memset(r, 0, sizeof(*r));
}

bool zs_selftest_register(zs_selftest_registry_t *r, uint8_t id, const char *name, zs_selftest_fn_t fn, void *ctx, bool required) {
  zs_selftest_entry_t *e;
  if (!r || !fn || id == 0u || id >= ZS_ST_ID_COUNT || r->count >= ZS_SELFTEST_MAX) return false;
  for (uint8_t i = 0u; i < r->count; i++) if (r->entries[i].id == id) return false;
  e = &r->entries[r->count++];
  e->id = id;
  e->name = name ? name : "";
  e->fn = fn;
  e->ctx = ctx;
  e->required = required;
  return true;
}

static zs_selftest_code_t run_entry(zs_selftest_registry_t *r, const zs_selftest_entry_t *e) {
  uint32_t detail = 0u;
  zs_selftest_code_t code = e->fn(e->ctx, &detail);
  if (code == ZS_ST_NOT_RUN) code = ZS_ST_FAIL; /* a test that reports NOT_RUN is broken */
  r->result[e->id] = code;
  r->detail[e->id] = detail;
  return code;
}

bool zs_selftest_run_all(zs_selftest_registry_t *r, uint32_t now_ms) {
  if (!r) return false;
  for (uint8_t i = 0u; i < r->count; i++) run_entry(r, &r->entries[i]);
  r->last_run_ms = now_ms;
  return zs_selftest_required_ok(r);
}

zs_selftest_code_t zs_selftest_run_one(zs_selftest_registry_t *r, uint8_t id, uint32_t now_ms) {
  if (!r) return ZS_ST_NOT_RUN;
  for (uint8_t i = 0u; i < r->count; i++) {
    if (r->entries[i].id == id) {
      r->last_run_ms = now_ms;
      return run_entry(r, &r->entries[i]);
    }
  }
  return ZS_ST_NOT_RUN;
}

bool zs_selftest_required_ok(const zs_selftest_registry_t *r) {
  if (!r) return false;
  for (uint8_t i = 0u; i < r->count; i++) {
    const zs_selftest_entry_t *e = &r->entries[i];
    zs_selftest_code_t c = r->result[e->id];
    if (e->required && (c == ZS_ST_FAIL || c == ZS_ST_TIMEOUT || c == ZS_ST_NOT_RUN)) return false;
  }
  return true;
}

/* zs_cbor has no array encoder; a two-element definite array is a single head byte. */
static void cbor_array2(zs_cbor_t *c) {
  if (c->len < c->cap) c->buf[c->len++] = 0x82u;
  else c->error = true;
}

size_t zs_selftest_encode(const zs_selftest_registry_t *r, uint8_t *buf, size_t cap) {
  zs_cbor_t c;
  if (!r || !buf) return 0u;
  zs_cbor_init(&c, buf, cap);
  zs_cbor_map(&c, r->count);
  for (uint8_t id = 1u; id < ZS_ST_ID_COUNT; id++) { /* ascending keys = canonical */
    bool registered = false;
    for (uint8_t i = 0u; i < r->count; i++) if (r->entries[i].id == id) { registered = true; break; }
    if (!registered) continue;
    zs_cbor_uint(&c, id);
    cbor_array2(&c);
    zs_cbor_uint(&c, (uint32_t)r->result[id]);
    zs_cbor_uint(&c, r->detail[id]);
  }
  return c.error ? 0u : c.len;
}

const char *zs_selftest_code_name(zs_selftest_code_t code) {
  static const char *const names[] = {"NOT_RUN", "PASS", "FAIL", "SKIPPED", "TIMEOUT"};
  return (unsigned)code < 5u ? names[code] : "?";
}
