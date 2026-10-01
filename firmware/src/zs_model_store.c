#include "zs_model_store.h"

#include <string.h>

_Static_assert(ZS_FW_MODEL_MIN_BYTES == ZS_MODEL_BYTES(1u), "the model check minimum is a one-class package");

static void put_le32(uint8_t *p, uint32_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static uint32_t get_le32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint32_t slot_base(const zs_model_store_t *s, unsigned slot) { return s->base + slot * s->slot_bytes; }
static uint32_t area_base(const zs_model_store_t *s, unsigned slot) { return slot_base(s, slot) + s->block_bytes; }

uint32_t zs_model_store_capacity(const zs_model_store_t *s) {
  return s && s->slot_bytes > s->block_bytes ? s->slot_bytes - s->block_bytes : 0u;
}

static void header_encode(const zs_model_slot_info_t *info, uint8_t out[ZS_MODEL_SLOT_HEADER_BYTES]) {
  uint8_t digest[ZS_SHA256_DIGEST_BYTES];
  memset(out, 0, ZS_MODEL_SLOT_HEADER_BYTES);
  memcpy(out, ZS_MODEL_SLOT_MAGIC, 8u);
  put_le32(&out[8], info->seq);
  put_le32(&out[12], info->version);
  put_le32(&out[16], info->size);
  memcpy(&out[20], info->sha256, ZS_SHA256_DIGEST_BYTES);
  zs_sha256_digest(out, ZS_MODEL_SLOT_HEADER_BYTES - 4u, digest);
  memcpy(&out[ZS_MODEL_SLOT_HEADER_BYTES - 4u], digest, 4u);
}

/* Reads a slot: a header that checks and a package that matches its SHA-256. */
static bool read_slot(const zs_model_store_t *s, unsigned slot, zs_model_slot_info_t *info) {
  uint8_t head[ZS_MODEL_SLOT_HEADER_BYTES], expect[ZS_MODEL_SLOT_HEADER_BYTES], block[256], digest[ZS_SHA256_DIGEST_BYTES];
  zs_sha256_t sha;
  memset(info, 0, sizeof(*info));
  if (!s->flash->read(s->flash->ctx, slot_base(s, slot), head, sizeof(head))) return false;
  if (memcmp(head, ZS_MODEL_SLOT_MAGIC, 8u) != 0) return true;                 /* empty or erased: not an error */
  info->seq = get_le32(&head[8]);
  info->version = get_le32(&head[12]);
  info->size = get_le32(&head[16]);
  memcpy(info->sha256, &head[20], ZS_SHA256_DIGEST_BYTES);
  header_encode(info, expect);
  if (memcmp(head, expect, sizeof(head)) != 0 || info->size == 0u || info->size > zs_model_store_capacity(s)) return true;
  zs_sha256_init(&sha);
  for (uint32_t off = 0u; off < info->size;) {
    const uint32_t n = info->size - off > sizeof(block) ? (uint32_t)sizeof(block) : info->size - off;
    if (!s->flash->read(s->flash->ctx, area_base(s, slot) + off, block, n)) return false;
    zs_sha256_update(&sha, block, n);
    off += n;
  }
  zs_sha256_final(&sha, digest);
  info->valid = zs_sha256_equal(digest, info->sha256, sizeof(digest));
  return true;
}

static void pick_active(zs_model_store_t *s) {
  s->active = -1;
  for (unsigned i = 0u; i < ZS_MODEL_STORE_SLOTS; i++)
    if (s->slot[i].valid && (s->active < 0 || s->slot[i].seq > s->slot[s->active].seq)) s->active = (int)i;
}

/* ---- package area of the target slot for the download engine ---- */
static bool io_erase(void *ctx, uint32_t offset, uint32_t size) {
  zs_model_store_t *s = (zs_model_store_t *)ctx;
  return offset + size <= zs_model_store_capacity(s) && s->flash->erase(s->flash->ctx, area_base(s, s->target) + offset, size);
}
static bool io_program(void *ctx, uint32_t offset, const uint8_t *data, size_t size) {
  zs_model_store_t *s = (zs_model_store_t *)ctx;
  return offset + size <= zs_model_store_capacity(s) && s->flash->program(s->flash->ctx, area_base(s, s->target) + offset, data, size);
}
static bool io_read(void *ctx, uint32_t offset, uint8_t *data, size_t size) {
  zs_model_store_t *s = (zs_model_store_t *)ctx;
  return offset + size <= zs_model_store_capacity(s) && s->flash->read(s->flash->ctx, area_base(s, s->target) + offset, data, size);
}
static bool io_read_model(void *ctx, uint32_t offset, uint8_t *data, size_t size) { return io_read(ctx, offset, data, size); }
/* The downloaded bytes must be a model package of the manifest's version (addendum I: FAILED 3 otherwise). */
static bool io_validate(void *ctx, const zs_fw_manifest_t *manifest) {
  zs_model_t model;
  return zs_model_load(io_read_model, ctx, manifest->size, NULL, &model) == ZS_MODEL_OK && model.version == manifest->version;
}

bool zs_model_store_init(zs_model_store_t *s, const zs_model_flash_t *flash, uint32_t base, uint32_t slot_bytes, uint32_t block_bytes) {
  if (!s) return false;
  memset(s, 0, sizeof(*s));
  s->active = -1;
  if (!flash || !flash->erase || !flash->program || !flash->read || block_bytes == 0u || slot_bytes % block_bytes ||
      base % block_bytes || slot_bytes < 2u * block_bytes || block_bytes < ZS_MODEL_SLOT_HEADER_BYTES)
    return false;
  s->flash = flash;
  s->base = base;
  s->slot_bytes = slot_bytes;
  s->block_bytes = block_bytes;
  s->io = (zs_fw_image_io_t){s, slot_bytes - block_bytes, block_bytes, 0u, io_erase, io_program, io_read, io_validate};
  for (unsigned i = 0u; i < ZS_MODEL_STORE_SLOTS; i++)
    if (!read_slot(s, i, &s->slot[i])) { s->flash = NULL; return false; }
  pick_active(s);
  return true;
}

const zs_fw_image_io_t *zs_model_store_begin(zs_model_store_t *s) {
  if (!s || !s->flash) return NULL;
  s->target = s->active == 0 ? 1u : 0u;
  memset(&s->slot[s->target], 0, sizeof(s->slot[s->target]));
  if (!s->flash->erase(s->flash->ctx, slot_base(s, s->target), s->block_bytes)) return NULL;
  return &s->io;
}

bool zs_model_store_commit(zs_model_store_t *s, const zs_fw_manifest_t *manifest) {
  uint8_t head[ZS_MODEL_SLOT_HEADER_BYTES];
  zs_model_slot_info_t info;
  if (!s || !s->flash || !manifest || manifest->size == 0u || manifest->size > zs_model_store_capacity(s)) return false;
  memset(&info, 0, sizeof(info));
  info.seq = s->active >= 0 ? s->slot[s->active].seq + 1u : 1u;
  info.version = manifest->version;
  info.size = manifest->size;
  memcpy(info.sha256, manifest->sha256, sizeof(info.sha256));
  header_encode(&info, head);
  if (!s->flash->program(s->flash->ctx, slot_base(s, s->target), head, sizeof(head))) return false;
  if (!read_slot(s, s->target, &s->slot[s->target]) || !s->slot[s->target].valid) return false;
  pick_active(s);
  return s->active == (int)s->target;
}

bool zs_model_store_active(const zs_model_store_t *s, uint32_t *size, uint32_t *version) {
  if (!s || !s->flash || s->active < 0) return false;
  if (size) *size = s->slot[s->active].size;
  if (version) *version = s->slot[s->active].version;
  return true;
}

bool zs_model_store_read_active(void *ctx, uint32_t offset, uint8_t *data, size_t size) {
  const zs_model_store_t *s = (const zs_model_store_t *)ctx;
  if (!s || !s->flash || s->active < 0 || offset + size > s->slot[s->active].size) return false;
  return s->flash->read(s->flash->ctx, area_base(s, (unsigned)s->active) + offset, data, size);
}
