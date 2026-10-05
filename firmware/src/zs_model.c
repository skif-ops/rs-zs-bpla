#include "zs_model.h"

#include "zs_model_centroids.h"

#include <math.h>
#include <stdio.h>
#include <string.h>
#if defined(_MSC_VER)
#include <intrin.h>
#pragma intrinsic(_ReadWriteBarrier)
#endif

_Static_assert(ZS_MODEL_CLASS_COUNT <= ZS_MODEL_PACKAGE_MAX_CLASSES, "the built-in model fits the package limits");

static const zs_model_t builtin = {
  0u, ZS_MODEL_FEATURE_SET, ZS_MODEL_CLASS_COUNT, zs_model_mean, zs_model_std, zs_model_class_id, zs_model_radius,
  zs_model_centroid,
};

const zs_model_t *zs_model_builtin(void) { return &builtin; }

static uint32_t le32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static uint16_t le16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }

static bool known_class(uint8_t id) {
  return (id >= ZS_CLASS_PISTON_UAV && id <= ZS_CLASS_ELECTRIC_UAV) || (id >= ZS_CLASS_ROAD_TRAFFIC && id <= ZS_CLASS_WIND);
}

/* Reads `count` little-endian floats at `offset` in bounded blocks; out may be NULL (check only). */
static zs_model_status_t read_floats(zs_model_read_fn read, void *ctx, uint32_t offset, float *out, size_t count,
                                     bool positive, bool non_negative) {
  uint8_t block[128];
  size_t done = 0u;
  while (done < count) {
    size_t n = count - done;
    if (n > sizeof(block) / 4u) n = sizeof(block) / 4u;
    if (!read(ctx, offset + (uint32_t)(done * 4u), block, n * 4u)) return ZS_MODEL_ERR_READ;
    for (size_t i = 0u; i < n; i++) {
      const uint32_t bits = le32(&block[i * 4u]);
      float v;
      memcpy(&v, &bits, sizeof(v));
      if (!isfinite(v) || (positive && !(v > 0.0f)) || (non_negative && v < 0.0f)) return ZS_MODEL_ERR_VALUE;
      if (out) out[done + i] = v;
    }
    done += n;
  }
  return ZS_MODEL_OK;
}

zs_model_status_t zs_model_load(zs_model_read_fn read, void *ctx, uint32_t size, zs_model_storage_t *storage, zs_model_t *model) {
  uint8_t head[ZS_MODEL_HEADER_BYTES], ids[ZS_MODEL_PACKAGE_MAX_CLASSES + 3u];
  uint32_t offset, version, feature_set;
  uint16_t classes, padded;
  zs_model_status_t st;
  if (!read || !model) return ZS_MODEL_ERR_READ;
  memset(model, 0, sizeof(*model));
  if (size < ZS_MODEL_HEADER_BYTES) return ZS_MODEL_ERR_SIZE;
  if (!read(ctx, 0u, head, sizeof(head))) return ZS_MODEL_ERR_READ;
  version = le32(&head[12]);
  feature_set = le32(&head[16]);
  classes = le16(&head[8]);
  if (le32(&head[0]) != ZS_MODEL_MAGIC || le16(&head[4]) != ZS_MODEL_FORMAT || le16(&head[6]) != ZS_FEATURE_COUNT ||
      le16(&head[10]) != 0u || version == 0u)
    return ZS_MODEL_ERR_HEADER;
  for (unsigned i = 20u; i < ZS_MODEL_HEADER_BYTES; i++)
    if (head[i] != 0u) return ZS_MODEL_ERR_HEADER;
  if (feature_set != ZS_MODEL_FEATURE_SET) return ZS_MODEL_ERR_FEATURE_SET;
  if (classes == 0u || classes > ZS_MODEL_PACKAGE_MAX_CLASSES || size != ZS_MODEL_BYTES(classes)) return ZS_MODEL_ERR_SIZE;
  offset = ZS_MODEL_HEADER_BYTES;
  if ((st = read_floats(read, ctx, offset, storage ? storage->mean : NULL, ZS_FEATURE_COUNT, false, false)) != ZS_MODEL_OK) return st;
  offset += 4u * ZS_FEATURE_COUNT;
  if ((st = read_floats(read, ctx, offset, storage ? storage->std : NULL, ZS_FEATURE_COUNT, false, true)) != ZS_MODEL_OK) return st;
  offset += 4u * ZS_FEATURE_COUNT;
  padded = (uint16_t)((classes + 3u) & ~3u);
  if (!read(ctx, offset, ids, padded)) return ZS_MODEL_ERR_READ;
  for (unsigned i = 0u; i < padded; i++) {
    if (i < classes ? !known_class(ids[i]) : ids[i] != 0u) return ZS_MODEL_ERR_VALUE;
  }
  if (storage) memcpy(storage->class_id, ids, classes);
  offset += padded;
  if ((st = read_floats(read, ctx, offset, storage ? storage->radius : NULL, classes, true, false)) != ZS_MODEL_OK) return st;
  offset += 4u * classes;
  if ((st = read_floats(read, ctx, offset, storage ? &storage->centroid[0][0] : NULL, (size_t)classes * ZS_FEATURE_COUNT, false, false)) != ZS_MODEL_OK)
    return st;
  model->version = version;
  model->feature_set = feature_set;
  model->class_count = classes;
  if (storage) {
    model->mean = storage->mean;
    model->std = storage->std;
    model->class_id = storage->class_id;
    model->radius = storage->radius;
    model->centroid = (const float (*)[ZS_FEATURE_COUNT])storage->centroid;
  }
  return ZS_MODEL_OK;
}

typedef struct {
  const uint8_t *bytes;
  size_t size;
} memory_t;

static bool memory_read(void *ctx, uint32_t offset, uint8_t *data, size_t size) {
  const memory_t *m = (const memory_t *)ctx;
  if ((size_t)offset > m->size || size > m->size - offset) return false;
  memcpy(data, m->bytes + offset, size);
  return true;
}

zs_model_status_t zs_model_parse(const uint8_t *bytes, size_t size, zs_model_storage_t *storage, zs_model_t *model) {
  memory_t m = {bytes, size};
  if (!bytes || size > UINT32_MAX) return ZS_MODEL_ERR_READ;
  return zs_model_load(memory_read, &m, (uint32_t)size, storage, model);
}

zs_classifier_result_t zs_model_predict(const zs_model_t *m, const float f[ZS_FEATURE_COUNT]) {
  float best = 1e30f;
  unsigned bi = 0u;
  float conf;
  for (unsigned c = 0u; c < m->class_count; c++) {
    float d = 0.0f;
    for (unsigned i = 0u; i < ZS_FEATURE_COUNT; i++) {
      const float z = (f[i] - m->mean[i]) / (m->std[i] + 1e-6f);
      const float q = z - m->centroid[c][i];
      d += q * q;
    }
    d = sqrtf(d);
    if (d < best) { best = d; bi = c; }
  }
  conf = 1.0f - best / (m->radius[bi] * 1.5f + 1e-6f);
  if (conf < 0.0f) conf = 0.0f;
  if (conf > 1.0f) conf = 1.0f;
  return (zs_classifier_result_t){m->class_id[bi], (uint8_t)(conf * 255.0f + 0.5f), best};
}

size_t zs_model_describe(const zs_model_t *m, char *out, size_t cap) {
  int n;
  if (!m || !out || cap == 0u) return 0u;
  n = m->version ? snprintf(out, cap, "m%lu", (unsigned long)m->version) : snprintf(out, cap, "c%u", (unsigned)m->class_count);
  return n > 0 && (size_t)n < cap ? (size_t)n : 0u;
}

/* ---- the active model: one RAM table behind a sequence counter (odd while it is written) ---- */
static zs_model_storage_t ram_storage;
static zs_model_t ram_model;
static volatile uint32_t ram_seq;          /* odd: being written */
static volatile bool ram_active;

static void fence(void) {
#if defined(_MSC_VER)
  _ReadWriteBarrier();
#else
  __atomic_thread_fence(__ATOMIC_SEQ_CST);
#endif
}

zs_model_status_t zs_model_activate(zs_model_read_fn read, void *ctx, uint32_t size, uint32_t expected_version) {
  zs_model_t check;
  zs_model_status_t st = zs_model_load(read, ctx, size, NULL, &check);     /* the whole package first, tables untouched */
  if (st != ZS_MODEL_OK) return st;
  if (expected_version && check.version != expected_version) return ZS_MODEL_ERR_HEADER;
  ram_active = false;
  ram_seq = ram_seq + 1u;                  /* odd: readers fall back to the built-in model */
  fence();
  st = zs_model_load(read, ctx, size, &ram_storage, &ram_model);
  fence();
  ram_seq = ram_seq + 1u;
  fence();
  ram_active = st == ZS_MODEL_OK;
  return st;
}

void zs_model_activate_builtin(void) { ram_active = false; }

uint32_t zs_model_active_version(void) { return ram_active ? ram_model.version : 0u; }

size_t zs_model_active_describe(char *out, size_t cap) {
  return zs_model_describe(ram_active ? &ram_model : &builtin, out, cap);
}

zs_classifier_result_t zs_model_predict_active(const float f[ZS_FEATURE_COUNT]) {
  uint32_t before;
  zs_classifier_result_t r;
  if (!ram_active) return zs_model_predict(&builtin, f);
  before = ram_seq;
  fence();
  if (before & 1u) return zs_model_predict(&builtin, f);
  r = zs_model_predict(&ram_model, f);
  fence();
  if (ram_seq != before || !ram_active) return zs_model_predict(&builtin, f);
  return r;
}
