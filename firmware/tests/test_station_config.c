#include "zs_station_config.h"

#include "zs_cbor.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  uint8_t slots[ZS_STATION_CONFIG_SLOT_COUNT][ZS_STATION_CONFIG_SLOT_BYTES];
  unsigned write_calls;
  unsigned fail_write_call;
} memory_store_t;

static bool mem_read(void *ctx, uint8_t slot, uint32_t offset, uint8_t *data, size_t size) {
  memory_store_t *s = ctx;
  if (slot >= ZS_STATION_CONFIG_SLOT_COUNT || offset + size > ZS_STATION_CONFIG_SLOT_BYTES) return false;
  memcpy(data, &s->slots[slot][offset], size);
  return true;
}
static bool mem_erase(void *ctx, uint8_t slot) {
  memory_store_t *s = ctx;
  if (slot >= ZS_STATION_CONFIG_SLOT_COUNT) return false;
  memset(s->slots[slot], 0xff, ZS_STATION_CONFIG_SLOT_BYTES);
  return true;
}
static bool mem_write(void *ctx, uint8_t slot, uint32_t offset, const uint8_t *data, size_t size) {
  memory_store_t *s = ctx;
  if (slot >= ZS_STATION_CONFIG_SLOT_COUNT || offset + size > ZS_STATION_CONFIG_SLOT_BYTES) return false;
  s->write_calls++;
  if (s->fail_write_call != 0u && s->write_calls == s->fail_write_call) return false;
  for (size_t i = 0u; i < size; i++) {
    if ((s->slots[slot][offset + i] & data[i]) != data[i]) return false; /* NOR: only 1->0 */
    s->slots[slot][offset + i] = data[i];
  }
  return true;
}
static zs_station_config_io_t mem_io(memory_store_t *s) {
  zs_station_config_io_t io = {s, mem_read, mem_erase, mem_write};
  return io;
}
static void mem_init(memory_store_t *s) {
  memset(s, 0, sizeof(*s));
  memset(s->slots, 0xff, sizeof(s->slots));
}

static void hex(const char *label, const uint8_t *d, size_t n) {
  printf("%s=", label);
  for (size_t i = 0u; i < n; i++) printf("%02x", d[i]);
  printf("\n");
}

/* Reference configuration shared with the Android known-answer test. */
static void reference_config(zs_station_config_t *cfg) {
  zs_station_config_defaults(cfg, 7u, ZS_STATION_CONFIG_REGION_RU868);
  cfg->version = 3u;
  strcpy(cfg->server_host, "10.20.30.40");
  cfg->mqtt_port = 8883u;
  cfg->https_port = 8443u;
  strcpy(cfg->ca_reference, "dioneya-root-2026");
  for (unsigned i = 0u; i < ZS_STATION_CONFIG_HASH_BYTES; i++) cfg->server_fingerprint[i] = (uint8_t)i;
  strcpy(cfg->tenant, "pilot");
  strcpy(cfg->topic_prefix, "zs/v1");
  cfg->preferred_sim = 2u;
  strcpy(cfg->apn[0], "internet.mts.ru");
  strcpy(cfg->apn[1], "internet");
  assert(zs_station_config_compute_hash(cfg, cfg->config_hash));
}

/* The same patch the Android app must produce for the reference configuration. */
static size_t reference_patch(uint8_t *buf, size_t cap) {
  zs_cbor_t c;
  uint8_t fp[ZS_STATION_CONFIG_HASH_BYTES];
  for (unsigned i = 0u; i < sizeof(fp); i++) fp[i] = (uint8_t)i;
  zs_cbor_init(&c, buf, cap);
  zs_cbor_map(&c, 11u);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_VERSION); zs_cbor_uint(&c, 3u);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_SERVER_HOST); zs_cbor_text(&c, "10.20.30.40");
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_MQTT_PORT); zs_cbor_uint(&c, 8883u);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_HTTPS_PORT); zs_cbor_uint(&c, 8443u);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_CA_REFERENCE); zs_cbor_text(&c, "dioneya-root-2026");
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_SERVER_FINGERPRINT); zs_cbor_bytes(&c, fp, sizeof(fp));
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_TENANT); zs_cbor_text(&c, "pilot");
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_TOPIC_PREFIX); zs_cbor_text(&c, "zs/v1");
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_PREFERRED_SIM); zs_cbor_uint(&c, 2u);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_APN1); zs_cbor_text(&c, "internet.mts.ru");
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_APN2); zs_cbor_text(&c, "internet");
  assert(!c.error);
  return c.len;
}

static void test_host_literals(void) {
  assert(zs_station_config_host_is_ipv4("10.20.30.40"));
  assert(zs_station_config_host_is_ipv4("255.255.255.255"));
  assert(!zs_station_config_host_is_ipv4("256.1.1.1"));
  assert(!zs_station_config_host_is_ipv4("1.2.3"));
  assert(!zs_station_config_host_is_ipv4("01.2.3.4"));
  assert(!zs_station_config_host_is_ipv4("1.2.3.4."));
  assert(zs_station_config_host_is_ipv6("2001:db8::1"));
  assert(zs_station_config_host_is_ipv6("::1"));
  assert(zs_station_config_host_is_ipv6("fe80:0:0:0:0:0:0:1"));
  assert(!zs_station_config_host_is_ipv6("2001:db8:::1"));
  assert(!zs_station_config_host_is_ipv6("2001:db8::1::2"));
  assert(!zs_station_config_host_is_ipv6("12345::1"));
  assert(!zs_station_config_host_is_ipv6("1:2:3:4:5:6:7:8:9"));
  assert(zs_station_config_host_is_hostname("muhoed.example.ru"));
  assert(zs_station_config_host_is_hostname("srv-1"));
  assert(!zs_station_config_host_is_hostname("-bad.ru"));
  assert(!zs_station_config_host_is_hostname("bad-.ru"));
  assert(!zs_station_config_host_is_hostname("bad..ru"));
  assert(!zs_station_config_host_is_hostname("bad_host.ru"));
  assert(!zs_station_config_host_is_hostname("123.456"));  /* all-numeric last label is not a hostname */
  assert(!zs_station_config_host_is_hostname("mqtts://x.ru"));
}

static void test_validate_and_hash(void) {
  zs_station_config_t cfg, other;
  uint8_t h1[32], h2[32];
  reference_config(&cfg);
  assert(zs_station_config_validate(&cfg) == 0u);
  assert(zs_station_config_hash_valid(&cfg));
  hex("REF_HASH", cfg.config_hash, sizeof(cfg.config_hash));

  other = cfg; other.mqtt_port = 0u;
  assert(zs_station_config_validate(&other) & ZS_STATION_CONFIG_ERR_MQTT_PORT);
  other = cfg; other.https_port = 8883u;
  assert(zs_station_config_validate(&other) & ZS_STATION_CONFIG_ERR_HTTPS_PORT);
  other = cfg; strcpy(other.server_host, "mqtts://host");
  assert(zs_station_config_validate(&other) & ZS_STATION_CONFIG_ERR_HOST);
  other = cfg; other.server_host[0] = '\0';
  assert(zs_station_config_validate(&other) & ZS_STATION_CONFIG_ERR_HOST);
  other = cfg; strcpy(other.topic_prefix, "/zs");
  assert(zs_station_config_validate(&other) & ZS_STATION_CONFIG_ERR_TOPIC_PREFIX);
  other = cfg; strcpy(other.tenant, "pi lot");
  assert(zs_station_config_validate(&other) & ZS_STATION_CONFIG_ERR_TENANT);
  other = cfg; other.preferred_sim = 3u;
  assert(zs_station_config_validate(&other) & ZS_STATION_CONFIG_ERR_PREFERRED_SIM);
  other = cfg; other.apn[0][0] = '\0';
  assert(zs_station_config_validate(&other) & ZS_STATION_CONFIG_ERR_APN); /* apn2 without apn1 */
  other = cfg; other.region = 9u;
  assert(zs_station_config_validate(&other) & ZS_STATION_CONFIG_ERR_REGION);
  other = cfg; other.version = 0u;
  assert(zs_station_config_validate(&other) & ZS_STATION_CONFIG_ERR_VERSION);

  /* Hash covers every settable field and the identity. */
  other = cfg; other.server_fingerprint[31] ^= 1u;
  assert(zs_station_config_compute_hash(&cfg, h1) && zs_station_config_compute_hash(&other, h2));
  assert(memcmp(h1, h2, 32) != 0);
  other = cfg; other.station_id = 8u;
  assert(zs_station_config_compute_hash(&other, h2)); assert(memcmp(h1, h2, 32) != 0);
  other = cfg; other.storage_generation = 99u;
  assert(zs_station_config_compute_hash(&other, h2)); assert(memcmp(h1, h2, 32) == 0); /* metadata excluded */
}

static void test_patch(void) {
  zs_station_config_t base, out, expected;
  uint8_t patch[256];
  size_t n;
  uint32_t err = 0u;
  zs_station_config_defaults(&base, 7u, ZS_STATION_CONFIG_REGION_RU868);
  reference_config(&expected);
  n = reference_patch(patch, sizeof(patch));
  hex("REF_PATCH", patch, n);
  assert(zs_station_config_apply_patch(&base, patch, n, &out, &err) == ZS_STATION_CONFIG_OK);
  assert(err == 0u);
  assert(memcmp(out.config_hash, expected.config_hash, 32) == 0);
  assert(out.version == 3u && out.mqtt_port == 8883u && out.https_port == 8443u && out.preferred_sim == 2u);
  assert(strcmp(out.server_host, "10.20.30.40") == 0 && strcmp(out.apn[1], "internet") == 0);
  {
    uint8_t rb[512];
    size_t m = zs_station_config_encode_readback(&out, rb, sizeof(rb));
    assert(m > 0u);
    hex("REF_READBACK", rb, m);
    assert(zs_station_config_encode_readback(&out, rb, 16u) == 0u); /* capacity guard */
  }
  /* Same version as base: rejected. */
  assert(zs_station_config_apply_patch(&out, patch, n, &out, &err) == ZS_STATION_CONFIG_VERSION_REJECTED);
  /* Partial patch on top of a committed config keeps other fields. */
  {
    zs_cbor_t c; uint8_t p2[64]; zs_station_config_t out2;
    zs_cbor_init(&c, p2, sizeof(p2)); zs_cbor_map(&c, 2u);
    zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_VERSION); zs_cbor_uint(&c, 4u);
    zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_SERVER_HOST); zs_cbor_text(&c, "muhoed.example.ru");
    assert(zs_station_config_apply_patch(&out, p2, c.len, &out2, &err) == ZS_STATION_CONFIG_OK);
    assert(strcmp(out2.server_host, "muhoed.example.ru") == 0 && out2.mqtt_port == 8883u && strcmp(out2.tenant, "pilot") == 0);
    assert(zs_station_config_hash_valid(&out2));
  }
  /* Fail-closed cases. */
  {
    zs_cbor_t c; uint8_t p[96]; zs_station_config_t o; uint8_t fp[31] = {0};
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 2u);
    zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, 99u); zs_cbor_uint(&c, 1u);
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_PATCH_UNKNOWN_KEY);
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 2u);
    zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, 12u); zs_cbor_uint(&c, ZS_STATION_CONFIG_REGION_EU868);
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_PATCH_IMMUTABLE_FIELD);
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 2u);
    zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, 12u); zs_cbor_uint(&c, ZS_STATION_CONFIG_REGION_RU868);
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_OK); /* same region is a no-op */
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 2u);
    zs_cbor_uint(&c, 2u); zs_cbor_text(&c, "a.ru"); zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 4u); /* keys out of order */
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_PATCH_MALFORMED);
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 2u);
    zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 5u); /* duplicate key */
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_PATCH_MALFORMED);
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 2u);
    zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, 3u); zs_cbor_text(&c, "8883"); /* wrong type */
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_PATCH_MALFORMED);
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 2u);
    zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, 6u); zs_cbor_bytes(&c, fp, sizeof(fp)); /* 31-byte fp */
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_PATCH_MALFORMED);
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 2u);
    zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, 3u); zs_cbor_uint(&c, 70000u); /* port range */
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_PATCH_MALFORMED);
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 2u);
    zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, 2u); zs_cbor_text(&c, "bad_host");
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, &err) == ZS_STATION_CONFIG_INVALID_RECORD);
    assert(err & ZS_STATION_CONFIG_ERR_HOST);
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 1u);
    zs_cbor_uint(&c, 2u); zs_cbor_text(&c, "a.ru"); /* no version */
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_VERSION_REJECTED);
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 1u);
    zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, 4u);
    p[c.len] = 0x00; /* trailing byte */
    assert(zs_station_config_apply_patch(&out, p, c.len + 1u, &o, NULL) == ZS_STATION_CONFIG_PATCH_MALFORMED);
    p[0] = 0xbf; /* indefinite map */
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_PATCH_MALFORMED);
    assert(zs_station_config_apply_patch(&out, p, 0u, &o, NULL) == ZS_STATION_CONFIG_INVALID_ARGUMENT);
    /* out untouched on failure */
    memset(&o, 0xAB, sizeof(o));
    zs_cbor_init(&c, p, sizeof(p)); zs_cbor_map(&c, 1u); zs_cbor_uint(&c, 99u); zs_cbor_uint(&c, 0u);
    assert(zs_station_config_apply_patch(&out, p, c.len, &o, NULL) == ZS_STATION_CONFIG_PATCH_UNKNOWN_KEY);
    assert(o.server_host[0] == (char)0xAB);
  }
}

static void test_store(void) {
  memory_store_t mem;
  zs_station_config_io_t io = mem_io(&mem);
  zs_station_config_t cfg, loaded, next;
  uint8_t slot = 9u;
  mem_init(&mem);
  reference_config(&cfg);
  assert(zs_station_config_store_load(&io, &loaded, &slot) == ZS_STATION_CONFIG_NOT_FOUND);
  assert(zs_station_config_store_commit(&io, &cfg, false, true) == ZS_STATION_CONFIG_AUTH_REQUIRED);
  assert(zs_station_config_store_commit(&io, &cfg, true, false) == ZS_STATION_CONFIG_AUTH_REQUIRED);
  cfg.config_hash[0] ^= 1u;
  assert(zs_station_config_store_commit(&io, &cfg, true, true) == ZS_STATION_CONFIG_INVALID_RECORD);
  cfg.config_hash[0] ^= 1u;
  assert(zs_station_config_store_commit(&io, &cfg, true, true) == ZS_STATION_CONFIG_OK);
  assert(zs_station_config_store_load(&io, &loaded, &slot) == ZS_STATION_CONFIG_OK);
  assert(slot == 0u && loaded.storage_generation == 1u && loaded.version == 3u);
  assert(memcmp(loaded.config_hash, cfg.config_hash, 32) == 0 && strcmp(loaded.apn[0], "internet.mts.ru") == 0);
  assert(memcmp(loaded.server_fingerprint, cfg.server_fingerprint, 32) == 0);

  /* Version must increase; identity must not change. */
  next = loaded;
  assert(zs_station_config_store_commit(&io, &next, true, true) == ZS_STATION_CONFIG_VERSION_REJECTED);
  next.version = 4u; next.station_id = 8u; assert(zs_station_config_compute_hash(&next, next.config_hash));
  assert(zs_station_config_store_commit(&io, &next, true, true) == ZS_STATION_CONFIG_PATCH_IMMUTABLE_FIELD);
  next.station_id = 7u; strcpy(next.server_host, "muhoed.example.ru"); assert(zs_station_config_compute_hash(&next, next.config_hash));
  assert(zs_station_config_store_commit(&io, &next, true, true) == ZS_STATION_CONFIG_OK);
  assert(zs_station_config_store_load(&io, &loaded, &slot) == ZS_STATION_CONFIG_OK);
  assert(slot == 1u && loaded.storage_generation == 2u && strcmp(loaded.server_host, "muhoed.example.ru") == 0);

  /* Torn write (power loss before the commit marker): previous record survives. */
  next.version = 5u; strcpy(next.tenant, "site2"); assert(zs_station_config_compute_hash(&next, next.config_hash));
  mem.write_calls = 0u; mem.fail_write_call = 2u; /* fail the commit-marker write */
  assert(zs_station_config_store_commit(&io, &next, true, true) == ZS_STATION_CONFIG_IO_ERROR);
  mem.fail_write_call = 0u;
  assert(zs_station_config_store_load(&io, &loaded, &slot) == ZS_STATION_CONFIG_OK);
  assert(slot == 1u && loaded.version == 4u && strcmp(loaded.tenant, "pilot") == 0);
  /* Retry succeeds into the other slot. */
  assert(zs_station_config_store_commit(&io, &next, true, true) == ZS_STATION_CONFIG_OK);
  assert(zs_station_config_store_load(&io, &loaded, &slot) == ZS_STATION_CONFIG_OK);
  assert(slot == 0u && loaded.version == 5u && loaded.storage_generation == 3u);

  /* Corrupted active slot: falls back to the older valid one. */
  mem.slots[0][40] ^= 0x55u;
  assert(zs_station_config_store_load(&io, &loaded, &slot) == ZS_STATION_CONFIG_OK);
  assert(slot == 1u && loaded.version == 4u);
  /* Both slots corrupted: not found. */
  mem.slots[1][40] ^= 0x55u;
  assert(zs_station_config_store_load(&io, &loaded, &slot) == ZS_STATION_CONFIG_NOT_FOUND);
}

int main(void) {
  test_host_literals();
  test_validate_and_hash();
  test_patch();
  test_store();
  printf("station_config tests passed\n");
  return 0;
}
