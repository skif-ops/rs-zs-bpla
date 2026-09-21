#include "zs_station_config.h"

#include "zs_cbor.h"
#include "zs_sha256.h"

#include <string.h>

/* ---- slot layout (little-endian, 320 bytes) ------------------------------- */
#define RECORD_MAGIC UINT32_C(0x3143535a) /* "ZSC1" */
#define RECORD_COMMIT UINT32_C(0x54494d43) /* "CMIT" */
#define RECORD_FORMAT UINT16_C(1)
#define OFF_GENERATION 8u
#define OFF_VERSION 12u
#define OFF_STATION_ID 16u
#define OFF_REGION 20u
#define OFF_PREFERRED_SIM 21u
#define OFF_MQTT_PORT 22u
#define OFF_HTTPS_PORT 24u
#define OFF_HOST_LEN 26u
#define OFF_CA_LEN 27u
#define OFF_TENANT_LEN 28u
#define OFF_PREFIX_LEN 29u
#define OFF_APN1_LEN 30u
#define OFF_APN2_LEN 31u
#define OFF_HOST 32u
#define OFF_CA 96u
#define OFF_FINGERPRINT 128u
#define OFF_TENANT 160u
#define OFF_PREFIX 176u
#define OFF_APN1 208u
#define OFF_APN2 240u
#define OFF_HASH 272u
#define OFF_CRC 304u
#define OFF_COMMIT 308u
#define RECORD_PAYLOAD_BYTES UINT16_C(OFF_CRC - OFF_GENERATION)
#define HASH_INPUT_BYTES 281u

_Static_assert(OFF_COMMIT + 4u <= ZS_STATION_CONFIG_SLOT_BYTES, "station config slot layout overflow");

/* ---- byte helpers ---------------------------------------------------------- */
static uint16_t get_u16(const uint8_t *p) { return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8)); }
static uint32_t get_u32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void put_u16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put_u32(uint8_t *p, uint32_t v) { for (unsigned i = 0u; i < 4u; i++) p[i] = (uint8_t)(v >> (8u * i)); }
static void put_be16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void put_be32(uint8_t *p, uint32_t v) {
  p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}

static uint32_t crc32(const uint8_t *data, size_t size) {
  uint32_t crc = UINT32_MAX;
  for (size_t i = 0u; i < size; i++) {
    crc ^= data[i];
    for (unsigned bit = 0u; bit < 8u; bit++) crc = (crc >> 1) ^ (UINT32_C(0xedb88320) & (uint32_t)-(int32_t)(crc & 1u));
  }
  return ~crc;
}

static size_t bounded_len(const char *s, size_t max) {
  size_t n = 0u;
  while (n <= max && s[n] != '\0') n++;
  return n; /* n == max + 1 means unterminated / too long */
}

/* ---- host literal checks --------------------------------------------------- */
static bool is_digit(char c) { return c >= '0' && c <= '9'; }
static bool is_alpha(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
static bool is_hex(char c) { return is_digit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'); }

bool zs_station_config_host_is_ipv4(const char *host) {
  unsigned octets = 0u;
  const char *p = host;
  if (host == NULL || *host == '\0') return false;
  while (1) {
    unsigned value = 0u, digits = 0u;
    while (is_digit(*p)) {
      value = value * 10u + (unsigned)(*p - '0');
      if (++digits > 3u || value > 255u) return false;
      p++;
    }
    if (digits == 0u || (digits > 1u && *(p - digits) == '0')) return false;
    octets++;
    if (*p == '\0') return octets == 4u;
    if (*p != '.' || octets == 4u) return false;
    p++;
  }
}

bool zs_station_config_host_is_ipv6(const char *host) {
  unsigned groups = 0u, digits = 0u;
  bool double_colon = false;
  const char *p = host;
  if (host == NULL || *host == '\0') return false;
  if (p[0] == ':' && p[1] != ':') return false;
  while (*p != '\0') {
    if (*p == ':') {
      if (p[1] == ':') {
        if (double_colon) return false;
        double_colon = true;
        if (digits > 0u) groups++;
        digits = 0u;
        p += 2;
        if (*p == ':') return false;
        continue;
      }
      if (digits == 0u) return false;
      groups++;
      digits = 0u;
      p++;
      if (*p == '\0') return false;
      continue;
    }
    if (!is_hex(*p) || ++digits > 4u) return false;
    p++;
  }
  if (digits > 0u) groups++;
  return double_colon ? groups <= 7u : groups == 8u;
}

bool zs_station_config_host_is_hostname(const char *host) {
  size_t label = 0u, total = 0u;
  bool last_label_numeric = true;
  const char *p = host;
  if (host == NULL || *host == '\0') return false;
  while (1) {
    char c = *p;
    if (c == '.' || c == '\0') {
      if (label == 0u || label > 63u || *(p - 1) == '-') return false;
      if (c == '\0') return total <= ZS_STATION_CONFIG_HOST_MAX && !last_label_numeric;
      label = 0u;
      last_label_numeric = true;
    } else {
      if (!(is_alpha(c) || is_digit(c) || c == '-')) return false;
      if (label == 0u && c == '-') return false;
      if (!is_digit(c)) last_label_numeric = false;
      label++;
    }
    p++;
    total++;
  }
}

static bool host_valid(const char *host) {
  size_t n = bounded_len(host, ZS_STATION_CONFIG_HOST_MAX);
  if (n == 0u || n > ZS_STATION_CONFIG_HOST_MAX) return false;
  return zs_station_config_host_is_ipv4(host) || zs_station_config_host_is_ipv6(host) ||
         zs_station_config_host_is_hostname(host);
}

static bool token_valid(const char *s, size_t max, bool allow_slash, bool required) {
  size_t n = bounded_len(s, max);
  if (n > max) return false;
  if (n == 0u) return !required;
  for (size_t i = 0u; i < n; i++) {
    char c = s[i];
    if (!(is_alpha(c) || is_digit(c) || c == '.' || c == '_' || c == '-' || (allow_slash && c == '/'))) return false;
  }
  return true;
}

static bool apn_valid(const char *s) {
  size_t n = bounded_len(s, ZS_STATION_CONFIG_APN_MAX);
  if (n > ZS_STATION_CONFIG_APN_MAX) return false;
  for (size_t i = 0u; i < n; i++) {
    char c = s[i];
    if (!(is_alpha(c) || is_digit(c) || c == '.' || c == '-')) return false;
  }
  return true;
}

/* ---- public: defaults / validate / hash ----------------------------------- */
void zs_station_config_defaults(zs_station_config_t *cfg, uint32_t station_id, uint8_t region) {
  if (cfg == NULL) return;
  memset(cfg, 0, sizeof(*cfg));
  cfg->station_id = station_id;
  cfg->region = region;
  cfg->mqtt_port = 8883u;
  cfg->https_port = 0u;
  cfg->preferred_sim = 1u;
  (void)zs_station_config_compute_hash(cfg, cfg->config_hash);
}

uint32_t zs_station_config_validate(const zs_station_config_t *cfg) {
  uint32_t err = 0u;
  if (cfg == NULL) return UINT32_MAX;
  if (cfg->station_id == 0u) err |= ZS_STATION_CONFIG_ERR_STATION_ID;
  if (cfg->region != ZS_STATION_CONFIG_REGION_RU868 && cfg->region != ZS_STATION_CONFIG_REGION_EU868) err |= ZS_STATION_CONFIG_ERR_REGION;
  if (!host_valid(cfg->server_host)) err |= ZS_STATION_CONFIG_ERR_HOST;
  if (cfg->mqtt_port == 0u) err |= ZS_STATION_CONFIG_ERR_MQTT_PORT;
  if (cfg->https_port != 0u && cfg->https_port == cfg->mqtt_port) err |= ZS_STATION_CONFIG_ERR_HTTPS_PORT;
  if (!token_valid(cfg->ca_reference, ZS_STATION_CONFIG_CA_REF_MAX, false, true)) err |= ZS_STATION_CONFIG_ERR_CA_REFERENCE;
  if (!token_valid(cfg->tenant, ZS_STATION_CONFIG_TENANT_MAX, false, true)) err |= ZS_STATION_CONFIG_ERR_TENANT;
  if (!token_valid(cfg->topic_prefix, ZS_STATION_CONFIG_TOPIC_PREFIX_MAX, true, true) ||
      cfg->topic_prefix[0] == '/' || cfg->topic_prefix[bounded_len(cfg->topic_prefix, ZS_STATION_CONFIG_TOPIC_PREFIX_MAX) - 1u] == '/') {
    err |= ZS_STATION_CONFIG_ERR_TOPIC_PREFIX;
  }
  if (cfg->preferred_sim != 1u && cfg->preferred_sim != 2u) err |= ZS_STATION_CONFIG_ERR_PREFERRED_SIM;
  if (!apn_valid(cfg->apn[0]) || !apn_valid(cfg->apn[1]) || (cfg->apn[0][0] == '\0' && cfg->apn[1][0] != '\0')) err |= ZS_STATION_CONFIG_ERR_APN;
  if (cfg->version == 0u) err |= ZS_STATION_CONFIG_ERR_VERSION;
  return err;
}

static void put_field(uint8_t *dst, size_t *pos, const char *s, size_t max) {
  size_t n = bounded_len(s, max);
  if (n > max) n = max;
  dst[(*pos)++] = (uint8_t)n;
  memcpy(&dst[*pos], s, n);
  *pos += max;
}

bool zs_station_config_compute_hash(const zs_station_config_t *cfg, uint8_t hash[ZS_STATION_CONFIG_HASH_BYTES]) {
  static const uint8_t domain[] = {'Z', 'S', '-', 'S', 'T', 'A', 'T', 'I', 'O', 'N', '-', 'C', 'O', 'N', 'F', 'I', 'G', '-', 'V', '1'};
  uint8_t bytes[HASH_INPUT_BYTES] = {0};
  size_t pos = 0u;
  _Static_assert(sizeof(domain) == 20u, "station config hash domain length drift");
  if (cfg == NULL || hash == NULL) return false;
  memcpy(bytes, domain, sizeof(domain));
  pos = sizeof(domain);
  bytes[pos++] = (uint8_t)ZS_STATION_CONFIG_SCHEMA;
  put_be32(&bytes[pos], cfg->version); pos += 4u;
  put_be32(&bytes[pos], cfg->station_id); pos += 4u;
  bytes[pos++] = cfg->region;
  bytes[pos++] = cfg->preferred_sim;
  put_be16(&bytes[pos], cfg->mqtt_port); pos += 2u;
  put_be16(&bytes[pos], cfg->https_port); pos += 2u;
  put_field(bytes, &pos, cfg->server_host, ZS_STATION_CONFIG_HOST_MAX);
  put_field(bytes, &pos, cfg->ca_reference, ZS_STATION_CONFIG_CA_REF_MAX);
  memcpy(&bytes[pos], cfg->server_fingerprint, ZS_STATION_CONFIG_HASH_BYTES); pos += ZS_STATION_CONFIG_HASH_BYTES;
  put_field(bytes, &pos, cfg->tenant, ZS_STATION_CONFIG_TENANT_MAX);
  put_field(bytes, &pos, cfg->topic_prefix, ZS_STATION_CONFIG_TOPIC_PREFIX_MAX);
  put_field(bytes, &pos, cfg->apn[0], ZS_STATION_CONFIG_APN_MAX);
  put_field(bytes, &pos, cfg->apn[1], ZS_STATION_CONFIG_APN_MAX);
  if (pos != HASH_INPUT_BYTES) return false;
  zs_sha256_digest(bytes, sizeof(bytes), hash);
  return true;
}

bool zs_station_config_hash_valid(const zs_station_config_t *cfg) {
  uint8_t expected[ZS_STATION_CONFIG_HASH_BYTES];
  uint8_t diff = 0u;
  if (cfg == NULL || !zs_station_config_compute_hash(cfg, expected)) return false;
  for (size_t i = 0u; i < sizeof(expected); i++) diff |= (uint8_t)(cfg->config_hash[i] ^ expected[i]);
  return diff == 0u;
}

/* ---- minimal bounded CBOR reader (definite lengths only) ------------------ */
typedef struct {
  const uint8_t *p;
  size_t len, pos;
} reader_t;

static bool read_head(reader_t *r, uint8_t *major, uint64_t *value) {
  uint8_t ib, ai;
  if (r->pos >= r->len) return false;
  ib = r->p[r->pos++];
  *major = (uint8_t)(ib >> 5);
  ai = (uint8_t)(ib & 0x1fu);
  if (ai < 24u) { *value = ai; return true; }
  if (ai == 24u) { if (r->pos + 1u > r->len) return false; *value = r->p[r->pos]; r->pos += 1u; return *value >= 24u; }
  if (ai == 25u) {
    if (r->pos + 2u > r->len) return false;
    *value = ((uint64_t)r->p[r->pos] << 8) | r->p[r->pos + 1u]; r->pos += 2u;
    return *value > 0xffu;
  }
  if (ai == 26u) {
    if (r->pos + 4u > r->len) return false;
    *value = ((uint64_t)r->p[r->pos] << 24) | ((uint64_t)r->p[r->pos + 1u] << 16) |
             ((uint64_t)r->p[r->pos + 2u] << 8) | r->p[r->pos + 3u];
    r->pos += 4u;
    return *value > 0xffffu;
  }
  return false; /* 8-byte, indefinite and reserved forms are rejected */
}

static bool read_uint(reader_t *r, uint64_t *v) {
  uint8_t major;
  return read_head(r, &major, v) && major == 0u;
}

static bool read_string(reader_t *r, uint8_t want_major, char *dst, size_t max) {
  uint8_t major; uint64_t n;
  if (!read_head(r, &major, &n) || major != want_major || n > max || r->pos + n > r->len) return false;
  memcpy(dst, &r->p[r->pos], (size_t)n);
  dst[n] = '\0';
  r->pos += (size_t)n;
  return memchr(dst, '\0', (size_t)n) == NULL; /* embedded NUL is malformed */
}

static bool read_bytes_exact(reader_t *r, uint8_t *dst, size_t want) {
  uint8_t major; uint64_t n;
  if (!read_head(r, &major, &n) || major != 2u || n != want || r->pos + want > r->len) return false;
  memcpy(dst, &r->p[r->pos], want);
  r->pos += want;
  return true;
}

zs_station_config_result_t zs_station_config_apply_patch(
    const zs_station_config_t *base, const uint8_t *patch, size_t patch_len,
    zs_station_config_t *out, uint32_t *validation_errors) {
  zs_station_config_t work;
  reader_t r = {patch, patch_len, 0u};
  uint8_t major; uint64_t count, last_key = 0u;
  bool version_seen = false;
  if (validation_errors) *validation_errors = 0u;
  if (base == NULL || patch == NULL || out == NULL || patch_len == 0u) return ZS_STATION_CONFIG_INVALID_ARGUMENT;
  work = *base;
  if (!read_head(&r, &major, &count) || major != 5u || count == 0u || count > 12u) return ZS_STATION_CONFIG_PATCH_MALFORMED;
  for (uint64_t i = 0u; i < count; i++) {
    uint64_t key, v;
    char text[ZS_STATION_CONFIG_HOST_MAX + 1u];
    if (!read_uint(&r, &key)) return ZS_STATION_CONFIG_PATCH_MALFORMED;
    if (i > 0u && key <= last_key) return ZS_STATION_CONFIG_PATCH_MALFORMED; /* canonical order, no duplicates */
    last_key = key;
    switch (key) {
      case ZS_STATION_CONFIG_KEY_VERSION:
        if (!read_uint(&r, &v) || v > UINT32_MAX) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        work.version = (uint32_t)v; version_seen = true; break;
      case ZS_STATION_CONFIG_KEY_SERVER_HOST:
        if (!read_string(&r, 3u, text, ZS_STATION_CONFIG_HOST_MAX)) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        memcpy(work.server_host, text, sizeof(work.server_host)); break;
      case ZS_STATION_CONFIG_KEY_MQTT_PORT:
        if (!read_uint(&r, &v) || v > 65535u) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        work.mqtt_port = (uint16_t)v; break;
      case ZS_STATION_CONFIG_KEY_HTTPS_PORT:
        if (!read_uint(&r, &v) || v > 65535u) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        work.https_port = (uint16_t)v; break;
      case ZS_STATION_CONFIG_KEY_CA_REFERENCE:
        if (!read_string(&r, 3u, work.ca_reference, ZS_STATION_CONFIG_CA_REF_MAX)) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        break;
      case ZS_STATION_CONFIG_KEY_SERVER_FINGERPRINT:
        if (!read_bytes_exact(&r, work.server_fingerprint, ZS_STATION_CONFIG_HASH_BYTES)) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        break;
      case ZS_STATION_CONFIG_KEY_TENANT:
        if (!read_string(&r, 3u, work.tenant, ZS_STATION_CONFIG_TENANT_MAX)) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        break;
      case ZS_STATION_CONFIG_KEY_TOPIC_PREFIX:
        if (!read_string(&r, 3u, work.topic_prefix, ZS_STATION_CONFIG_TOPIC_PREFIX_MAX)) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        break;
      case ZS_STATION_CONFIG_KEY_PREFERRED_SIM:
        if (!read_uint(&r, &v) || v > 255u) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        work.preferred_sim = (uint8_t)v; break;
      case ZS_STATION_CONFIG_KEY_APN1:
        if (!read_string(&r, 3u, work.apn[0], ZS_STATION_CONFIG_APN_MAX)) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        break;
      case ZS_STATION_CONFIG_KEY_APN2:
        if (!read_string(&r, 3u, work.apn[1], ZS_STATION_CONFIG_APN_MAX)) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        break;
      case ZS_STATION_CONFIG_KEY_REGION:
        if (!read_uint(&r, &v)) return ZS_STATION_CONFIG_PATCH_MALFORMED;
        if (v != base->region) return ZS_STATION_CONFIG_PATCH_IMMUTABLE_FIELD; /* region change is never allowed */
        break;
      default:
        return ZS_STATION_CONFIG_PATCH_UNKNOWN_KEY;
    }
  }
  if (r.pos != r.len) return ZS_STATION_CONFIG_PATCH_MALFORMED; /* trailing bytes */
  if (!version_seen || work.version <= base->version) return ZS_STATION_CONFIG_VERSION_REJECTED;
  {
    uint32_t err = zs_station_config_validate(&work);
    if (validation_errors) *validation_errors = err;
    if (err != 0u) return ZS_STATION_CONFIG_INVALID_RECORD;
  }
  if (!zs_station_config_compute_hash(&work, work.config_hash)) return ZS_STATION_CONFIG_INVALID_RECORD;
  *out = work;
  return ZS_STATION_CONFIG_OK;
}

size_t zs_station_config_encode_readback(const zs_station_config_t *cfg, uint8_t *buf, size_t cap) {
  zs_cbor_t c;
  if (cfg == NULL || buf == NULL) return 0u;
  zs_cbor_init(&c, buf, cap);
  zs_cbor_map(&c, 14u);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_VERSION); zs_cbor_uint(&c, cfg->version);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_SERVER_HOST); zs_cbor_text(&c, cfg->server_host);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_MQTT_PORT); zs_cbor_uint(&c, cfg->mqtt_port);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_HTTPS_PORT); zs_cbor_uint(&c, cfg->https_port);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_CA_REFERENCE); zs_cbor_text(&c, cfg->ca_reference);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_SERVER_FINGERPRINT); zs_cbor_bytes(&c, cfg->server_fingerprint, ZS_STATION_CONFIG_HASH_BYTES);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_TENANT); zs_cbor_text(&c, cfg->tenant);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_TOPIC_PREFIX); zs_cbor_text(&c, cfg->topic_prefix);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_PREFERRED_SIM); zs_cbor_uint(&c, cfg->preferred_sim);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_APN1); zs_cbor_text(&c, cfg->apn[0]);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_APN2); zs_cbor_text(&c, cfg->apn[1]);
  zs_cbor_uint(&c, ZS_STATION_CONFIG_KEY_REGION); zs_cbor_uint(&c, cfg->region);
  zs_cbor_uint(&c, 13u); zs_cbor_uint(&c, cfg->station_id);           /* read-only identity */
  zs_cbor_uint(&c, 14u); zs_cbor_bytes(&c, cfg->config_hash, ZS_STATION_CONFIG_HASH_BYTES); /* station-computed hash */
  return c.error ? 0u : c.len;
}

/* ---- slot encode / decode -------------------------------------------------- */
static void put_slot_field(uint8_t *bytes, size_t len_off, size_t data_off, const char *s, size_t max) {
  size_t n = bounded_len(s, max);
  if (n > max) n = max;
  bytes[len_off] = (uint8_t)n;
  memset(&bytes[data_off], 0, max);
  memcpy(&bytes[data_off], s, n);
}

static bool get_slot_field(const uint8_t *bytes, size_t len_off, size_t data_off, char *dst, size_t max) {
  size_t n = bytes[len_off];
  if (n > max) return false;
  memcpy(dst, &bytes[data_off], n);
  dst[n] = '\0';
  return memchr(dst, '\0', n) == NULL;
}

static void encode_slot(const zs_station_config_t *cfg, uint32_t generation, uint8_t bytes[ZS_STATION_CONFIG_SLOT_BYTES]) {
  memset(bytes, 0xff, ZS_STATION_CONFIG_SLOT_BYTES);
  put_u32(&bytes[0], RECORD_MAGIC);
  put_u16(&bytes[4], RECORD_FORMAT);
  put_u16(&bytes[6], RECORD_PAYLOAD_BYTES);
  put_u32(&bytes[OFF_GENERATION], generation);
  put_u32(&bytes[OFF_VERSION], cfg->version);
  put_u32(&bytes[OFF_STATION_ID], cfg->station_id);
  bytes[OFF_REGION] = cfg->region;
  bytes[OFF_PREFERRED_SIM] = cfg->preferred_sim;
  put_u16(&bytes[OFF_MQTT_PORT], cfg->mqtt_port);
  put_u16(&bytes[OFF_HTTPS_PORT], cfg->https_port);
  put_slot_field(bytes, OFF_HOST_LEN, OFF_HOST, cfg->server_host, ZS_STATION_CONFIG_HOST_MAX);
  put_slot_field(bytes, OFF_CA_LEN, OFF_CA, cfg->ca_reference, ZS_STATION_CONFIG_CA_REF_MAX);
  memcpy(&bytes[OFF_FINGERPRINT], cfg->server_fingerprint, ZS_STATION_CONFIG_HASH_BYTES);
  put_slot_field(bytes, OFF_TENANT_LEN, OFF_TENANT, cfg->tenant, ZS_STATION_CONFIG_TENANT_MAX);
  put_slot_field(bytes, OFF_PREFIX_LEN, OFF_PREFIX, cfg->topic_prefix, ZS_STATION_CONFIG_TOPIC_PREFIX_MAX);
  put_slot_field(bytes, OFF_APN1_LEN, OFF_APN1, cfg->apn[0], ZS_STATION_CONFIG_APN_MAX);
  put_slot_field(bytes, OFF_APN2_LEN, OFF_APN2, cfg->apn[1], ZS_STATION_CONFIG_APN_MAX);
  memcpy(&bytes[OFF_HASH], cfg->config_hash, ZS_STATION_CONFIG_HASH_BYTES);
  put_u32(&bytes[OFF_CRC], crc32(bytes, OFF_CRC));
  put_u32(&bytes[OFF_COMMIT], RECORD_COMMIT);
}

static bool decode_slot(const uint8_t bytes[ZS_STATION_CONFIG_SLOT_BYTES], zs_station_config_t *cfg) {
  if (get_u32(&bytes[0]) != RECORD_MAGIC || get_u16(&bytes[4]) != RECORD_FORMAT ||
      get_u16(&bytes[6]) != RECORD_PAYLOAD_BYTES || get_u32(&bytes[OFF_COMMIT]) != RECORD_COMMIT ||
      get_u32(&bytes[OFF_CRC]) != crc32(bytes, OFF_CRC)) {
    return false;
  }
  memset(cfg, 0, sizeof(*cfg));
  cfg->storage_generation = get_u32(&bytes[OFF_GENERATION]);
  cfg->version = get_u32(&bytes[OFF_VERSION]);
  cfg->station_id = get_u32(&bytes[OFF_STATION_ID]);
  cfg->region = bytes[OFF_REGION];
  cfg->preferred_sim = bytes[OFF_PREFERRED_SIM];
  cfg->mqtt_port = get_u16(&bytes[OFF_MQTT_PORT]);
  cfg->https_port = get_u16(&bytes[OFF_HTTPS_PORT]);
  if (!get_slot_field(bytes, OFF_HOST_LEN, OFF_HOST, cfg->server_host, ZS_STATION_CONFIG_HOST_MAX) ||
      !get_slot_field(bytes, OFF_CA_LEN, OFF_CA, cfg->ca_reference, ZS_STATION_CONFIG_CA_REF_MAX) ||
      !get_slot_field(bytes, OFF_TENANT_LEN, OFF_TENANT, cfg->tenant, ZS_STATION_CONFIG_TENANT_MAX) ||
      !get_slot_field(bytes, OFF_PREFIX_LEN, OFF_PREFIX, cfg->topic_prefix, ZS_STATION_CONFIG_TOPIC_PREFIX_MAX) ||
      !get_slot_field(bytes, OFF_APN1_LEN, OFF_APN1, cfg->apn[0], ZS_STATION_CONFIG_APN_MAX) ||
      !get_slot_field(bytes, OFF_APN2_LEN, OFF_APN2, cfg->apn[1], ZS_STATION_CONFIG_APN_MAX)) {
    return false;
  }
  memcpy(cfg->server_fingerprint, &bytes[OFF_FINGERPRINT], ZS_STATION_CONFIG_HASH_BYTES);
  memcpy(cfg->config_hash, &bytes[OFF_HASH], ZS_STATION_CONFIG_HASH_BYTES);
  return cfg->storage_generation > 0u && zs_station_config_validate(cfg) == 0u && zs_station_config_hash_valid(cfg);
}

static bool generation_newer(uint32_t candidate, uint32_t reference) {
  return candidate != reference && (uint32_t)(candidate - reference) < UINT32_C(0x80000000);
}

static bool io_valid(const zs_station_config_io_t *io) {
  return io != NULL && io->read != NULL && io->erase != NULL && io->write != NULL;
}

zs_station_config_result_t zs_station_config_store_load(
    const zs_station_config_io_t *io, zs_station_config_t *cfg, uint8_t *active_slot) {
  zs_station_config_t decoded[ZS_STATION_CONFIG_SLOT_COUNT];
  bool valid[ZS_STATION_CONFIG_SLOT_COUNT] = {false, false};
  bool read_failed = false;
  int best = -1;
  if (!io_valid(io) || cfg == NULL) return ZS_STATION_CONFIG_INVALID_ARGUMENT;
  for (uint8_t s = 0u; s < ZS_STATION_CONFIG_SLOT_COUNT; s++) {
    uint8_t bytes[ZS_STATION_CONFIG_SLOT_BYTES];
    if (!io->read(io->ctx, s, 0u, bytes, sizeof(bytes))) { read_failed = true; continue; }
    valid[s] = decode_slot(bytes, &decoded[s]);
    if (valid[s] && (best < 0 || generation_newer(decoded[s].storage_generation, decoded[best].storage_generation))) best = (int)s;
  }
  if (best < 0) return read_failed ? ZS_STATION_CONFIG_IO_ERROR : ZS_STATION_CONFIG_NOT_FOUND;
  *cfg = decoded[best];
  if (active_slot) *active_slot = (uint8_t)best;
  return ZS_STATION_CONFIG_OK;
}

zs_station_config_result_t zs_station_config_store_commit(
    const zs_station_config_io_t *io, const zs_station_config_t *cfg,
    bool physical_service_mode, bool authenticated_role) {
  zs_station_config_t current, verify;
  uint8_t bytes[ZS_STATION_CONFIG_SLOT_BYTES], readback[ZS_STATION_CONFIG_SLOT_BYTES];
  uint8_t active = 0u, target;
  uint32_t generation = 1u;
  zs_station_config_result_t load;
  if (!io_valid(io) || cfg == NULL) return ZS_STATION_CONFIG_INVALID_ARGUMENT;
  if (!physical_service_mode || !authenticated_role) return ZS_STATION_CONFIG_AUTH_REQUIRED;
  if (zs_station_config_validate(cfg) != 0u || !zs_station_config_hash_valid(cfg)) return ZS_STATION_CONFIG_INVALID_RECORD;
  load = zs_station_config_store_load(io, &current, &active);
  if (load == ZS_STATION_CONFIG_OK) {
    if (cfg->version <= current.version) return ZS_STATION_CONFIG_VERSION_REJECTED;
    if (cfg->station_id != current.station_id || cfg->region != current.region) return ZS_STATION_CONFIG_PATCH_IMMUTABLE_FIELD;
    generation = current.storage_generation + 1u;
    if (generation == 0u) generation = 1u;
    target = (uint8_t)((active + 1u) % ZS_STATION_CONFIG_SLOT_COUNT);
  } else if (load == ZS_STATION_CONFIG_NOT_FOUND) {
    target = 0u;
  } else {
    return load;
  }
  encode_slot(cfg, generation, bytes);
  if (!io->erase(io->ctx, target)) return ZS_STATION_CONFIG_IO_ERROR;
  /* Payload first, commit marker last: a torn write never yields a decodable slot. */
  if (!io->write(io->ctx, target, 0u, bytes, OFF_COMMIT)) return ZS_STATION_CONFIG_IO_ERROR;
  if (!io->write(io->ctx, target, OFF_COMMIT, &bytes[OFF_COMMIT], 4u)) return ZS_STATION_CONFIG_IO_ERROR;
  if (!io->read(io->ctx, target, 0u, readback, sizeof(readback))) return ZS_STATION_CONFIG_IO_ERROR;
  if (!decode_slot(readback, &verify) || verify.storage_generation != generation ||
      memcmp(verify.config_hash, cfg->config_hash, ZS_STATION_CONFIG_HASH_BYTES) != 0) {
    return ZS_STATION_CONFIG_VERIFY_FAILED;
  }
  return ZS_STATION_CONFIG_OK;
}
