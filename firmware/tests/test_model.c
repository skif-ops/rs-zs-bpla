/* MQTT ICD addendum I, model package: the built-in table written as package m5 here must be the package the server
   signed (its SHA-256 is in the manifest of the shared vector, tools/generate_model_update_vector.py); then the
   package parser (every refusal), the classifier parity with the built-in table, the active model and its
   seqlock, the release check for target 3, and the two-slot model store filled by the addendum F download engine on
   a RAM flash with NOR semantics (erase to 0xFF, program only clears bits):
     envelope -> zs_fw_model_check -> begin (header erased) -> fwreq bytes equal the server's -> chunks -> SHA-256 +
     package check -> OK -> commit -> activate; torn downloads, a bad package, a wrong version, a corrupted slot. */
#include "zs_command.h"
#include "zs_command_rotate_vector.h"
#include "zs_command_trust.h"
#include "zs_ed25519.h"
#include "zs_fw_update.h"
#include "zs_fw_update_vector.h"
#include "zs_model.h"
#include "zs_model_store.h"
#include "zs_model_update_vector.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static uint8_t pkg[ZS_MODEL_PACKAGE_MAX_BYTES];
#define PKG pkg
#define PKG_BYTES ZS_MODEL_UPDATE_VECTOR_PACKAGE_BYTES

static zs_model_storage_t storage;

static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }
static void put_le32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24); }
static void put_f32(uint8_t *p, float f) { uint32_t b; memcpy(&b, &f, 4u); put_le32(p, b); }

/* The package layout of zs_model.h written from a model: the C side of the server's model_codec.encode_model. */
static size_t build_package(const zs_model_t *m, uint32_t version, uint8_t *out) {
  size_t o = ZS_MODEL_HEADER_BYTES;
  const unsigned n = m->class_count, padded = (n + 3u) & ~3u;
  memset(out, 0, ZS_MODEL_BYTES(n));
  put_le32(&out[0], ZS_MODEL_MAGIC);
  out[4] = (uint8_t)ZS_MODEL_FORMAT; out[6] = (uint8_t)ZS_FEATURE_COUNT; out[8] = (uint8_t)n; out[9] = (uint8_t)(n >> 8);
  put_le32(&out[12], version);
  put_le32(&out[16], m->feature_set);
  for (unsigned i = 0u; i < ZS_FEATURE_COUNT; i++, o += 4u) put_f32(&out[o], m->mean[i]);
  for (unsigned i = 0u; i < ZS_FEATURE_COUNT; i++, o += 4u) put_f32(&out[o], m->std[i]);
  memcpy(&out[o], m->class_id, n); o += padded;
  for (unsigned c = 0u; c < n; c++, o += 4u) put_f32(&out[o], m->radius[c]);
  for (unsigned c = 0u; c < n; c++)
    for (unsigned i = 0u; i < ZS_FEATURE_COUNT; i++, o += 4u) put_f32(&out[o], m->centroid[c][i]);
  return o;
}

static uint8_t pkg_copy[ZS_MODEL_PACKAGE_MAX_BYTES];
static const uint8_t *mutated(size_t offset, uint8_t value) {
  memcpy(pkg_copy, PKG, PKG_BYTES);
  pkg_copy[offset] = value;
  return pkg_copy;
}
static zs_model_status_t parse(const uint8_t *bytes, size_t size) {
  zs_model_t m;
  return zs_model_parse(bytes, size, NULL, &m);
}

static void test_parse(void) {
  zs_model_t m;
  const zs_model_t *b = zs_model_builtin();
  const uint32_t n = b->class_count, ids = ZS_MODEL_HEADER_BYTES + 8u * ZS_FEATURE_COUNT, radius = ids + ((n + 3u) & ~3u);
  assert(PKG_BYTES == ZS_MODEL_BYTES(n) && ZS_MODEL_BYTES(1u) == ZS_FW_MODEL_MIN_BYTES);
  assert(zs_model_parse(PKG, PKG_BYTES, &storage, &m) == ZS_MODEL_OK);
  assert(m.version == ZS_MODEL_UPDATE_VECTOR_VERSION && m.feature_set == ZS_MODEL_FEATURE_SET && m.class_count == n);
  /* the server wrote the built-in table: float for float, class for class */
  assert(memcmp(m.mean, b->mean, sizeof(float) * ZS_FEATURE_COUNT) == 0 && memcmp(m.std, b->std, sizeof(float) * ZS_FEATURE_COUNT) == 0);
  assert(memcmp(m.class_id, b->class_id, n) == 0 && memcmp(m.radius, b->radius, sizeof(float) * n) == 0);
  assert(memcmp(m.centroid, b->centroid, sizeof(float) * ZS_FEATURE_COUNT * n) == 0);
  assert(zs_model_parse(PKG, PKG_BYTES, NULL, &m) == ZS_MODEL_OK && m.mean == NULL && m.version == ZS_MODEL_UPDATE_VECTOR_VERSION);

  assert(parse(mutated(0u, 'X'), PKG_BYTES) == ZS_MODEL_ERR_HEADER);                 /* magic */
  assert(parse(mutated(4u, 2u), PKG_BYTES) == ZS_MODEL_ERR_HEADER);                  /* format */
  assert(parse(mutated(6u, 42u), PKG_BYTES) == ZS_MODEL_ERR_HEADER);                 /* feature count */
  assert(parse(mutated(10u, 1u), PKG_BYTES) == ZS_MODEL_ERR_HEADER);                 /* reserved u16 */
  assert(parse(mutated(31u, 1u), PKG_BYTES) == ZS_MODEL_ERR_HEADER);                 /* reserved bytes */
  memcpy(pkg_copy, PKG, PKG_BYTES); put_le32(&pkg_copy[12], 0u);
  assert(parse(pkg_copy, PKG_BYTES) == ZS_MODEL_ERR_HEADER);                          /* version 0 */
  assert(parse(mutated(16u, 2u), PKG_BYTES) == ZS_MODEL_ERR_FEATURE_SET);            /* another feature extractor */
  assert(parse(PKG, PKG_BYTES - 1u) == ZS_MODEL_ERR_SIZE && parse(PKG, 20u) == ZS_MODEL_ERR_SIZE);
  assert(parse(mutated(8u, 0u), PKG_BYTES) == ZS_MODEL_ERR_SIZE);                    /* 0 classes (n < 256) */
  assert(parse(mutated(8u, (uint8_t)(n + 1u)), PKG_BYTES) == ZS_MODEL_ERR_SIZE);     /* size of another class count */
  assert(parse(mutated(8u, 97u), PKG_BYTES) == ZS_MODEL_ERR_SIZE);                  /* more than ZS_MODEL_PACKAGE_MAX_CLASSES */
  memcpy(pkg_copy, PKG, PKG_BYTES); put_f32(&pkg_copy[ZS_MODEL_HEADER_BYTES + 8u], NAN);
  assert(parse(pkg_copy, PKG_BYTES) == ZS_MODEL_ERR_VALUE);                           /* NaN in the mean */
  memcpy(pkg_copy, PKG, PKG_BYTES); put_f32(&pkg_copy[ZS_MODEL_HEADER_BYTES + 4u * ZS_FEATURE_COUNT], -1.0f);
  assert(parse(pkg_copy, PKG_BYTES) == ZS_MODEL_ERR_VALUE);                           /* negative std */
  memcpy(pkg_copy, PKG, PKG_BYTES); put_f32(&pkg_copy[radius + 4u], 0.0f);
  assert(parse(pkg_copy, PKG_BYTES) == ZS_MODEL_ERR_VALUE);                           /* radius 0 */
  memcpy(pkg_copy, PKG, PKG_BYTES); put_f32(&pkg_copy[PKG_BYTES - 4u], INFINITY);
  assert(parse(pkg_copy, PKG_BYTES) == ZS_MODEL_ERR_VALUE);                           /* inf in the last centroid */
  assert(parse(mutated(ids, 0u), PKG_BYTES) == ZS_MODEL_ERR_VALUE);                  /* UNKNOWN is not a class */
  assert(parse(mutated(ids + 1u, 4u), PKG_BYTES) == ZS_MODEL_ERR_VALUE);             /* a gap in zs_class_id_t */
  if (radius > ids + n) assert(parse(mutated(ids + n, 1u), PKG_BYTES) == ZS_MODEL_ERR_VALUE);   /* padding */
  { /* a smallest package: one class */
    memcpy(pkg_copy, PKG, ZS_MODEL_HEADER_BYTES + 8u * ZS_FEATURE_COUNT);
    pkg_copy[8] = 1u; pkg_copy[9] = 0u;
    uint8_t *p = &pkg_copy[ids];
    memset(p, 0, 4u); p[0] = 15u;
    put_f32(p + 4u, 2.0f);
    for (unsigned i = 0u; i < ZS_FEATURE_COUNT; i++) put_f32(p + 8u + 4u * i, 0.0f);
    assert(zs_model_parse(pkg_copy, ZS_MODEL_BYTES(1u), &storage, &m) == ZS_MODEL_OK && m.class_count == 1u);
    { float f[ZS_FEATURE_COUNT]; memcpy(f, b->mean, sizeof(f)); assert(zs_model_predict(&m, f).class_id == 15u && zs_model_predict(&m, f).confidence_u8 == 255u); }
  }
  printf("parse ok (%u classes, %u bytes)\n", (unsigned)n, (unsigned)PKG_BYTES);
}

static void test_predict(void) {
  zs_model_t m;
  const zs_model_t *b = zs_model_builtin();
  unsigned seed = 12345u;
  assert(zs_model_parse(PKG, PKG_BYTES, &storage, &m) == ZS_MODEL_OK);
  for (unsigned k = 0u; k < 200u; k++) {
    float f[ZS_FEATURE_COUNT];
    for (unsigned i = 0u; i < ZS_FEATURE_COUNT; i++) {
      seed = seed * 1103515245u + 12345u;
      f[i] = b->mean[i] + b->std[i] * ((float)((seed >> 8) % 4001u) / 1000.0f - 2.0f);
    }
    const zs_classifier_result_t x = zs_model_predict(&m, f), y = zs_model_predict(b, f);
    assert(x.class_id == y.class_id && x.confidence_u8 == y.confidence_u8 && x.distance == y.distance);
  }
  for (unsigned s = 0u; s < ZS_MODEL_UPDATE_VECTOR_SAMPLES; s++) {   /* the Python mirror of the server agrees */
    const zs_classifier_result_t r = zs_model_predict(&m, zs_model_update_vector_features[s]);
    const int dc = (int)r.confidence_u8 - (int)zs_model_update_vector_sample_conf[s];
    assert(r.class_id == zs_model_update_vector_sample_class[s] && dc >= -1 && dc <= 1);
  }
  { char t[ZS_MODEL_DESCRIBE_MAX]; assert(zs_model_describe(&m, t, sizeof(t)) == 2u && strcmp(t, "m5") == 0);
    assert(zs_model_describe(b, t, sizeof(t)) > 0u && t[0] == 'c'); assert(zs_model_describe(&m, t, 2u) == 0u); }
  printf("predict ok (package == built-in on 200 windows, %u server samples)\n", (unsigned)ZS_MODEL_UPDATE_VECTOR_SAMPLES);
}

/* a reader over a buffer that, on one call of the loading pass, classifies with the active model (it runs inside the
   seqlock write, like the pipeline task preempting the comms task) */
typedef struct {
  const uint8_t *bytes;
  uint32_t size;
  unsigned calls, probe_at, fail_at;
  zs_classifier_result_t probe;
} probe_reader_t;
static bool probe_read(void *ctx, uint32_t offset, uint8_t *data, size_t size) {
  probe_reader_t *r = ctx;
  if (offset > r->size || size > r->size - offset || ++r->calls == r->fail_at) return false;
  memcpy(data, r->bytes + offset, size);
  if (r->calls == r->probe_at) r->probe = zs_model_predict_active(zs_model_update_vector_features[0]);
  return true;
}

static void make_all_wind(uint8_t *out, uint32_t version) {
  const uint32_t ids = ZS_MODEL_HEADER_BYTES + 8u * ZS_FEATURE_COUNT, n = le32(&PKG[8]) & 0xffffu;
  memcpy(out, PKG, PKG_BYTES);
  put_le32(&out[12], version);
  memset(&out[ids], 18u, n);                                                  /* every centroid says "wind" */
}

static void test_active(void) {
  static uint8_t wind[ZS_MODEL_PACKAGE_MAX_BYTES];
  char t[ZS_MODEL_DESCRIBE_MAX];
  const float *f = zs_model_update_vector_features[0];
  const zs_classifier_result_t builtin = zs_model_predict(zs_model_builtin(), f);
  probe_reader_t r = {PKG, PKG_BYTES, 0u, 0u, 0u, {0}};
  assert(zs_model_active_version() == 0u && zs_model_active_describe(t, sizeof(t)) > 0u && t[0] == 'c');
  assert(zs_model_activate(probe_read, &r, PKG_BYTES, ZS_MODEL_UPDATE_VECTOR_VERSION) == ZS_MODEL_OK);
  assert(zs_model_active_version() == 5u && zs_model_active_describe(t, sizeof(t)) == 2u && strcmp(t, "m5") == 0);
  make_all_wind(wind, 6u);
  { /* activation with a wrong expected version or a bad package leaves m5 untouched */
    probe_reader_t w = {wind, PKG_BYTES, 0u, 0u, 0u, {0}};
    assert(zs_model_activate(probe_read, &w, PKG_BYTES, 7u) == ZS_MODEL_ERR_HEADER && zs_model_active_version() == 5u);
    wind[0] ^= 1u;
    assert(zs_model_activate(probe_read, &w, PKG_BYTES, 0u) == ZS_MODEL_ERR_HEADER && zs_model_active_version() == 5u);
    wind[0] ^= 1u;
    assert(zs_model_predict_active(f).class_id == builtin.class_id);
  }
  { /* during the table write the pipeline gets the built-in model, afterwards the new one */
    probe_reader_t w = {wind, PKG_BYTES, 0u, 0u, 0u, {0}};
    unsigned check_calls;
    assert(zs_model_activate(probe_read, &w, PKG_BYTES, 0u) == ZS_MODEL_OK);
    check_calls = w.calls / 2u;                                               /* the check pass, then the loading pass */
    w.calls = 0u; w.probe_at = check_calls + 3u;
    make_all_wind(wind, 7u);
    assert(zs_model_activate(probe_read, &w, PKG_BYTES, 7u) == ZS_MODEL_OK);
    assert(w.probe.class_id == builtin.class_id && w.probe.confidence_u8 == builtin.confidence_u8);
    assert(zs_model_active_version() == 7u && zs_model_predict_active(f).class_id == 18u);
    assert(zs_classifier_predict_centroid(f).class_id == 18u);               /* the pipeline's entry point follows */
  }
  { /* a reader that fails in the check pass changes nothing; one that fails while the tables are written leaves
       the built-in model active (never a half-written table) */
    probe_reader_t w = {wind, PKG_BYTES, 0u, 0u, 3u, {0}};
    unsigned pass;
    assert(zs_model_activate(probe_read, &w, PKG_BYTES, 0u) == ZS_MODEL_ERR_READ && zs_model_active_version() == 7u);
    w.calls = 0u; w.fail_at = 0u;
    assert(zs_model_activate(probe_read, &w, PKG_BYTES, 0u) == ZS_MODEL_OK);
    pass = w.calls / 2u;
    w.calls = 0u; w.fail_at = pass + 5u;
    assert(zs_model_activate(probe_read, &w, PKG_BYTES, 0u) == ZS_MODEL_ERR_READ && zs_model_active_version() == 0u);
    assert(zs_model_predict_active(f).class_id == builtin.class_id);
  }
  zs_model_activate_builtin();
  assert(zs_model_active_version() == 0u && zs_model_predict_active(f).class_id == builtin.class_id);
  printf("active model ok (seqlock probe during the write saw the built-in model)\n");
}

/* ---- the model store on a RAM flash with NOR semantics ---- */
#define BLOCK 4096u
#define SLOT (16u * BLOCK)
#define BASE (3u * BLOCK)
static uint8_t nor[BASE + 2u * SLOT + BLOCK];
static unsigned nor_fail_program_at, nor_programs;
static bool n_erase(void *c, uint32_t a, uint32_t n) { (void)c; if (a % BLOCK || n % BLOCK || a + n > sizeof(nor)) return false; memset(&nor[a], 0xff, n); return true; }
static bool n_program(void *c, uint32_t a, const uint8_t *d, size_t n) {
  (void)c;
  if (a + n > sizeof(nor) || ++nor_programs == nor_fail_program_at) return false;
  for (size_t i = 0u; i < n; i++) nor[a + i] &= d[i];
  return true;
}
static bool n_read(void *c, uint32_t a, uint8_t *d, size_t n) { (void)c; if (a + n > sizeof(nor)) return false; memcpy(d, &nor[a], n); return true; }
static const zs_model_flash_t flash = {NULL, n_erase, n_program, n_read};

static const uint8_t cid[ZS_COMMAND_UUID_BYTES] = {0x2b, 0x0f, 0x1c, 0x3a, 0, 0, 0x40, 0, 0x80, 0, 0, 0, 0, 0, 0, 9};

/* the engine with chunks cut from `image`; `stop_after` chunks then a "power loss" (0 = run to the end) */
static zs_fw_step_t download(zs_model_store_t *s, const zs_fw_manifest_t *manifest, const uint8_t *image, unsigned stop_after) {
  zs_fw_download_t dl;
  zs_fw_step_t st;
  unsigned guard = 0u;
  const zs_fw_image_io_t *io = zs_model_store_begin(s);
  assert(io && io->validate && io->capacity == SLOT - BLOCK);
  assert(zs_fw_download_start(&dl, io, ZS_MODEL_UPDATE_VECTOR_STATION_ID, cid, manifest));
  while ((st = zs_fw_download_step(&dl, 4096u)) != ZS_FW_STEP_FINISHED && guard++ < 1000u) {
    if (st == ZS_FW_STEP_NEED_CHUNK) {
      const uint32_t want = zs_fw_download_want(&dl);
      const zs_fw_chunk_t c = {ZS_MODEL_UPDATE_VECTOR_STATION_ID, {0}, dl.offset, image + dl.offset, want};
      zs_fw_chunk_t cc = c;
      if (stop_after && dl.chunks == stop_after) return ZS_FW_STEP_BUSY;
      memcpy(cc.command_id, cid, sizeof(cid));
      assert(zs_fw_download_on_chunk(&dl, &cc) == ZS_FW_CHUNK_ACCEPTED);
    }
  }
  assert(st == ZS_FW_STEP_FINISHED);
  if (dl.result != ZS_COMMAND_ACK_OK) return (zs_fw_step_t)(100 + dl.detail);
  return st;
}

static zs_fw_manifest_t manifest_of(const uint8_t *bytes, uint32_t size, uint32_t version) {
  zs_fw_manifest_t m;
  memset(&m, 0, sizeof(m));
  m.target = ZS_FW_TARGET_MODEL; m.version = version; m.size = size;
  zs_sha256_digest(bytes, size, m.sha256);
  return m;
}

static void test_store(const zs_fw_manifest_t *signed_manifest) {
  static uint8_t wind[ZS_MODEL_PACKAGE_MAX_BYTES], junk[4096];
  zs_model_store_t s;
  uint32_t size = 0u, version = 0u;
  memset(nor, 0xff, sizeof(nor));
  assert(!zs_model_store_init(&s, &flash, BASE + 1u, SLOT, BLOCK) && !zs_model_store_init(&s, &flash, BASE, SLOT, 32u));
  assert(zs_model_store_init(&s, &flash, BASE, SLOT, BLOCK) && s.active == -1 && !zs_model_store_active(&s, &size, &version));
  assert(zs_model_store_capacity(&s) == SLOT - BLOCK && zs_model_store_capacity(&s) >= ZS_MODEL_PACKAGE_MAX_BYTES);

  /* the signed vector package into slot 0; nothing is active before the commit, even across a reboot */
  assert(download(&s, signed_manifest, PKG, 0u) == ZS_FW_STEP_FINISHED);
  { zs_model_store_t again; assert(zs_model_store_init(&again, &flash, BASE, SLOT, BLOCK) && again.active == -1); }
  assert(zs_model_store_commit(&s, signed_manifest) && s.active == 0 && s.slot[0].seq == 1u);
  assert(zs_model_store_active(&s, &size, &version) && size == PKG_BYTES && version == 5u);
  assert(zs_model_activate(zs_model_store_read_active, &s, size, version) == ZS_MODEL_OK && zs_model_active_version() == 5u);
  for (uint32_t a = 0u; a < BASE; a++) assert(nor[a] == 0xffu);                    /* nothing outside the region */
  for (uint32_t a = BASE + 2u * SLOT; a < sizeof(nor); a++) assert(nor[a] == 0xffu);

  /* m6 goes to slot 1 and wins by seq; after a reboot too */
  make_all_wind(wind, 6u);
  { const zs_fw_manifest_t m6 = manifest_of(wind, PKG_BYTES, 6u);
    assert(download(&s, &m6, wind, 0u) == ZS_FW_STEP_FINISHED && s.target == 1u && zs_model_store_commit(&s, &m6)); }
  { zs_model_store_t again; assert(zs_model_store_init(&again, &flash, BASE, SLOT, BLOCK) && again.active == 1 && again.slot[1].seq == 2u && again.slot[1].version == 6u); }

  /* a torn download into slot 0 (power loss after 3 chunks) leaves m6 active; slot 0 lost its header first */
  assert(download(&s, signed_manifest, PKG, 3u) == ZS_FW_STEP_BUSY && s.target == 0u);
  { zs_model_store_t again; assert(zs_model_store_init(&again, &flash, BASE, SLOT, BLOCK) && again.active == 1 && !again.slot[0].valid); }

  /* the engine refuses what is not a package of the manifest version: FAILED 3 (package check) */
  { const zs_fw_manifest_t m9 = manifest_of(PKG, PKG_BYTES, 9u);
    assert((int)download(&s, &m9, PKG, 0u) == 100 + ZS_FW_FAIL_INFO); }
  for (unsigned i = 0u; i < sizeof(junk); i++) junk[i] = (uint8_t)(i * 7u + 1u);
  { const zs_fw_manifest_t mj = manifest_of(junk, sizeof(junk), 8u);
    assert((int)download(&s, &mj, junk, 0u) == 100 + ZS_FW_FAIL_INFO); }
  { zs_fw_manifest_t bad = *signed_manifest; bad.sha256[0] ^= 1u;
    assert((int)download(&s, &bad, PKG, 0u) == 100 + ZS_FW_FAIL_SHA256); }

  /* m5 again (a rollback is a re-release), then a flash error while its header is written */
  assert(download(&s, signed_manifest, PKG, 0u) == ZS_FW_STEP_FINISHED);
  nor_programs = 0u; nor_fail_program_at = 1u;
  assert(!zs_model_store_commit(&s, signed_manifest) && s.active == 1);
  nor_fail_program_at = 0u;
  assert(download(&s, signed_manifest, PKG, 0u) == ZS_FW_STEP_FINISHED && zs_model_store_commit(&s, signed_manifest));
  assert(s.active == 0 && s.slot[0].seq == 3u);

  /* a bit flip in the active package: the next boot falls back to the other slot */
  nor[BASE + BLOCK + 100u] ^= 0x01u;
  { zs_model_store_t again; assert(zs_model_store_init(&again, &flash, BASE, SLOT, BLOCK) && again.active == 1 && again.slot[1].version == 6u); }
  zs_model_activate_builtin();
  printf("model store ok (commit after ACK, torn download, package check, bit flip)\n");
}

static bool ed25519(void *ctx, const uint8_t pk[ZS_COMMAND_PUBLIC_KEY_BYTES], const uint8_t *m, size_t n, const uint8_t sig[ZS_COMMAND_SIGNATURE_BYTES]) {
  (void)ctx; return zs_ed25519_verify(pk, m, n, sig);
}
static zs_command_dedup_state_t never_seen(void *ctx, const uint8_t id[ZS_COMMAND_UUID_BYTES]) { (void)ctx; (void)id; return ZS_COMMAND_DEDUP_NOT_SEEN; }

static void decode(const uint8_t *bytes, size_t size, uint8_t *workspace, size_t cap, zs_command_t *cmd) {
  zs_command_trust_key_t key;
  zs_command_trust_t trust;
  memset(&key, 0, sizeof(key));
  memcpy(key.public_key, zs_command_rotate_vector_current_public_key, 32u);
  key.enabled = true;
  assert(zs_command_trust_init(&trust, &key, 1u, ed25519, NULL));
  assert(zs_command_decode_verify(bytes, size, ZS_MODEL_UPDATE_VECTOR_STATION_ID, ZS_MODEL_UPDATE_VECTOR_CREATED_US + 1000u, true,
                                  zs_command_trust_verify, &trust, never_seen, NULL, workspace, cap, cmd) == ZS_COMMAND_STATUS_OK);
  assert(cmd->code == ZS_COMMAND_UPDATE_FIRMWARE);
}

int main(void) {
  static uint8_t ws_model[256], ws_fw[256];
  zs_command_t cmd, fw_cmd;
  zs_fw_release_key_t release;
  zs_fw_station_t station;
  zs_fw_manifest_t manifest;
  zs_fw_chunk_t chunk;
  uint8_t buf[64];

  /* the package the server signed is the built-in table in the package layout, byte for byte */
  assert(build_package(zs_model_builtin(), ZS_MODEL_UPDATE_VECTOR_VERSION, pkg) == PKG_BYTES);
  {
    zs_fw_manifest_t signed_manifest;
    uint8_t d[ZS_SHA256_DIGEST_BYTES];
    assert(zs_fw_manifest_decode(zs_model_update_vector_manifest, sizeof(zs_model_update_vector_manifest), &signed_manifest));
    zs_sha256_digest(pkg, PKG_BYTES, d);
    assert(signed_manifest.size == PKG_BYTES && memcmp(d, signed_manifest.sha256, sizeof(d)) == 0);
  }
  test_parse();
  test_predict();
  test_active();

  /* ---- the envelope and the release check for target 3 ---- */
  decode(zs_model_update_vector_command, sizeof(zs_model_update_vector_command), ws_model, sizeof(ws_model), &cmd);
  assert(cmd.firmware.manifest_size == sizeof(zs_model_update_vector_manifest) &&
         memcmp(cmd.firmware.manifest, zs_model_update_vector_manifest, sizeof(zs_model_update_vector_manifest)) == 0 &&
         memcmp(cmd.firmware.signature, zs_model_update_vector_signature, 64u) == 0);
  memcpy(release.public_key, zs_model_update_vector_release_public_key, 32u);
  assert(memcmp(release.public_key, zs_fw_update_vector_release_public_key, 32u) == 0);   /* one release key for both */
  assert(zs_fw_update_target(&cmd.firmware) == ZS_FW_TARGET_MODEL);
  station = (zs_fw_station_t){&release, 1u, 0u, 0u, SLOT - BLOCK, true};                 /* target/trial are not used */
  assert(zs_fw_model_check(&cmd.firmware, &station, &manifest) == 0u);
  assert(manifest.target == ZS_FW_TARGET_MODEL && manifest.version == 5u && manifest.size == PKG_BYTES);
  { uint8_t d[32]; zs_sha256_digest(PKG, PKG_BYTES, d); assert(memcmp(d, manifest.sha256, 32u) == 0); }
  {
    zs_fw_station_t st = station;
    zs_update_firmware_command_t f = cmd.firmware;
    zs_fw_manifest_t m;
    st.running_version = 5u; assert(zs_fw_model_check(&f, &st, &m) == ZS_FW_REJECT_VERSION);   /* already active */
    st.running_version = 9u; assert(zs_fw_model_check(&f, &st, &m) == 0u);                   /* going back is allowed */
    st = station; st.capacity = PKG_BYTES - 1u; assert(zs_fw_model_check(&f, &st, &m) == ZS_FW_REJECT_SIZE);
    st = station; st.key_count = 0u; assert(zs_fw_model_check(&f, &st, &m) == ZS_FW_REJECT_UNSUPPORTED);
    f.signature[3] ^= 1u; assert(zs_fw_model_check(&f, &station, &m) == ZS_FW_REJECT_MANIFEST);
    f = cmd.firmware; f.manifest[5] ^= 1u; assert(zs_fw_model_check(&f, &station, &m) == ZS_FW_REJECT_MANIFEST);
    /* the image path refuses a model manifest, the model path an image manifest */
    st = (zs_fw_station_t){&release, 1u, ZS_FW_TARGET_STM32_APP, 1u, 1u << 20, false};
    assert(zs_fw_update_check(&cmd.firmware, &st, &m) == ZS_FW_REJECT_TARGET);
    decode(zs_fw_update_vector_command, sizeof(zs_fw_update_vector_command), ws_fw, sizeof(ws_fw), &fw_cmd);
    assert(zs_fw_update_target(&fw_cmd.firmware) == ZS_FW_TARGET_STM32_APP);
    assert(zs_fw_model_check(&fw_cmd.firmware, &station, &m) == ZS_FW_REJECT_TARGET);
    f.manifest_size = 0u; assert(zs_fw_update_target(&f) == 0u);
  }

  /* ---- the first request is the server's bytes ---- */
  {
    zs_fw_download_t dl;
    zs_model_store_t s;
    memset(nor, 0xff, sizeof(nor));
    assert(zs_model_store_init(&s, &flash, BASE, SLOT, BLOCK));
    assert(zs_fw_download_start(&dl, zs_model_store_begin(&s), ZS_MODEL_UPDATE_VECTOR_STATION_ID, cid, &manifest));
    while (zs_fw_download_step(&dl, 65536u) == ZS_FW_STEP_BUSY) {}
    assert(zs_fw_download_request(&dl, buf, sizeof(buf)) == sizeof(zs_model_update_vector_request0) &&
           memcmp(buf, zs_model_update_vector_request0, sizeof(zs_model_update_vector_request0)) == 0);
    chunk = (zs_fw_chunk_t){ZS_MODEL_UPDATE_VECTOR_STATION_ID, {0}, 0u, PKG, ZS_FW_CHUNK_BYTES};
    memcpy(chunk.command_id, cid, sizeof(cid));
    assert(zs_fw_download_on_chunk(&dl, &chunk) == ZS_FW_CHUNK_ACCEPTED && dl.offset == ZS_FW_CHUNK_BYTES);
  }

  test_store(&manifest);

  (void)zs_fw_update_vector_image; (void)zs_fw_update_vector_manifest; (void)zs_fw_update_vector_signature;
  (void)zs_fw_update_vector_request0; (void)zs_fw_update_vector_chunk0; (void)zs_fw_update_vector_chunk1; (void)zs_fw_update_vector_chunk2;
  printf("model tests passed\n");
  return 0;
}
