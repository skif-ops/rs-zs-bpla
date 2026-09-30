#include "zs_fw_update.h"

#include "zs_cbor.h"
#include "zs_cbor_read.h"
#include "zs_ed25519.h"

#include <string.h>

static uint32_t get_le32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void put_le32(uint8_t *p, uint32_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

bool zs_fw_info_parse(const uint8_t bytes[ZS_FW_INFO_BYTES], zs_fw_info_t *info) {
  if (!bytes || !info) return false;
  info->magic = get_le32(&bytes[0]);
  info->format = (uint16_t)(bytes[4] | (bytes[5] << 8));
  info->target = (uint16_t)(bytes[6] | (bytes[7] << 8));
  info->version = get_le32(&bytes[8]);
  memcpy(info->reserved, &bytes[12], sizeof(info->reserved));
  return info->magic == ZS_FW_INFO_MAGIC && info->format == ZS_FW_INFO_FORMAT && info->version != 0u;
}

void zs_fw_info_encode(uint32_t target, uint32_t version, uint8_t out[ZS_FW_INFO_BYTES]) {
  memset(out, 0, ZS_FW_INFO_BYTES);
  put_le32(&out[0], ZS_FW_INFO_MAGIC);
  out[4] = (uint8_t)ZS_FW_INFO_FORMAT;
  out[6] = (uint8_t)target; out[7] = (uint8_t)(target >> 8);
  put_le32(&out[8], version);
}

static bool expect_key(zs_cbor_reader_t *r, uint64_t key) {
  uint64_t v;
  return zs_cbor_read_uint(r, &v) && v == key;
}

static bool read_u32(zs_cbor_reader_t *r, uint32_t *out) {
  uint64_t v;
  if (!zs_cbor_read_uint(r, &v) || v > UINT32_MAX) return false;
  *out = (uint32_t)v;
  return true;
}

bool zs_fw_manifest_decode(const uint8_t *bytes, size_t size, zs_fw_manifest_t *manifest) {
  zs_cbor_reader_t r;
  uint32_t count, schema;
  const uint8_t *sha;
  size_t sha_len;
  if (!bytes || !manifest || size == 0u || size > ZS_FW_MANIFEST_MAX_BYTES) return false;
  memset(manifest, 0, sizeof(*manifest));
  zs_cbor_reader_init(&r, bytes, size);
  if (!zs_cbor_read_map(&r, &count) || count != 5u ||
      !expect_key(&r, 0u) || !read_u32(&r, &schema) || schema != ZS_FW_MANIFEST_SCHEMA ||
      !expect_key(&r, 1u) || !read_u32(&r, &manifest->target) || manifest->target == 0u ||
      !expect_key(&r, 2u) || !read_u32(&r, &manifest->version) || manifest->version == 0u ||
      !expect_key(&r, 3u) || !read_u32(&r, &manifest->size) || manifest->size == 0u ||
      !expect_key(&r, 4u) || !zs_cbor_read_bytes(&r, &sha, &sha_len) || sha_len != ZS_SHA256_DIGEST_BYTES ||
      !zs_cbor_reader_at_end(&r))
    return false;
  memcpy(manifest->sha256, sha, ZS_SHA256_DIGEST_BYTES);
  return true;
}

void zs_fw_release_key_id(const uint8_t public_key[ZS_FW_RELEASE_PUBLIC_KEY_BYTES], uint8_t key_id[ZS_FW_RELEASE_KEY_ID_BYTES]) {
  uint8_t digest[ZS_SHA256_DIGEST_BYTES];
  zs_sha256_digest(public_key, ZS_FW_RELEASE_PUBLIC_KEY_BYTES, digest);
  memcpy(key_id, digest, ZS_FW_RELEASE_KEY_ID_BYTES);
}

uint16_t zs_fw_update_check(const zs_update_firmware_command_t *cmd, const zs_fw_station_t *station, zs_fw_manifest_t *manifest) {
  uint8_t signed_msg[ZS_FW_SIGN_DOMAIN_BYTES + ZS_FW_MANIFEST_MAX_BYTES];
  const zs_fw_release_key_t *key = NULL;
  if (!cmd || !station || !manifest) return ZS_FW_REJECT_UNSUPPORTED;
  if (!station->keys || station->key_count == 0u || station->capacity == 0u) return ZS_FW_REJECT_UNSUPPORTED;
  if (cmd->manifest_size == 0u || cmd->manifest_size > ZS_FW_MANIFEST_MAX_BYTES ||
      !zs_fw_manifest_decode(cmd->manifest, cmd->manifest_size, manifest))
    return ZS_FW_REJECT_MANIFEST;
  for (size_t i = 0u; i < station->key_count && i < ZS_FW_RELEASE_KEYS_MAX; i++) {
    uint8_t id[ZS_FW_RELEASE_KEY_ID_BYTES];
    zs_fw_release_key_id(station->keys[i].public_key, id);
    if (memcmp(id, cmd->key_id, sizeof(id)) == 0) { key = &station->keys[i]; break; }
  }
  if (!key) return ZS_FW_REJECT_MANIFEST;
  memcpy(signed_msg, ZS_FW_SIGN_DOMAIN, ZS_FW_SIGN_DOMAIN_BYTES);
  memcpy(&signed_msg[ZS_FW_SIGN_DOMAIN_BYTES], cmd->manifest, cmd->manifest_size);
  if (!zs_ed25519_verify(key->public_key, signed_msg, ZS_FW_SIGN_DOMAIN_BYTES + cmd->manifest_size, cmd->signature))
    return ZS_FW_REJECT_MANIFEST;
  if (manifest->target != station->target) return ZS_FW_REJECT_TARGET;
  if (manifest->version <= station->running_version) return ZS_FW_REJECT_VERSION;
  if (manifest->size > station->capacity || manifest->size <= ZS_FW_INFO_OFFSET + ZS_FW_INFO_BYTES) return ZS_FW_REJECT_SIZE;
  if (station->trial) return ZS_FW_REJECT_TRIAL;
  return 0u;
}

size_t zs_fw_request_encode(uint32_t station_id, const uint8_t command_id[ZS_COMMAND_UUID_BYTES], uint32_t offset,
                            uint32_t length, uint8_t *out, size_t cap) {
  zs_cbor_t c;
  if (!command_id || !out || station_id == 0u || length == 0u || length > ZS_FW_CHUNK_BYTES) return 0u;
  zs_cbor_init(&c, out, cap);
  zs_cbor_map(&c, 6u);
  zs_cbor_uint(&c, 0u); zs_cbor_uint(&c, ZS_FW_MESSAGE_SCHEMA);
  zs_cbor_uint(&c, 1u); zs_cbor_uint(&c, ZS_FW_REQUEST_MESSAGE_TYPE);
  zs_cbor_uint(&c, 2u); zs_cbor_uint(&c, station_id);
  zs_cbor_uint(&c, 3u); zs_cbor_bytes(&c, command_id, ZS_COMMAND_UUID_BYTES);
  zs_cbor_uint(&c, 4u); zs_cbor_uint(&c, offset);
  zs_cbor_uint(&c, 5u); zs_cbor_uint(&c, length);
  return c.error ? 0u : c.len;
}

/* The common head {0: 1, 1: type, 2: station_id, 3: command_id, 4: offset} of fwreq and fw. */
static bool read_head(zs_cbor_reader_t *r, uint64_t type, uint32_t *station_id, uint8_t command_id[ZS_COMMAND_UUID_BYTES], uint32_t *offset) {
  uint32_t count, schema, message_type;
  const uint8_t *id;
  size_t id_len;
  uint8_t any = 0u;
  if (!zs_cbor_read_map(r, &count) || count != 6u ||
      !expect_key(r, 0u) || !read_u32(r, &schema) || schema != ZS_FW_MESSAGE_SCHEMA ||
      !expect_key(r, 1u) || !read_u32(r, &message_type) || message_type != type ||
      !expect_key(r, 2u) || !read_u32(r, station_id) || *station_id == 0u ||
      !expect_key(r, 3u) || !zs_cbor_read_bytes(r, &id, &id_len) || id_len != ZS_COMMAND_UUID_BYTES ||
      !expect_key(r, 4u) || !read_u32(r, offset))
    return false;
  for (size_t i = 0u; i < ZS_COMMAND_UUID_BYTES; i++) any |= id[i];
  if (!any) return false;
  memcpy(command_id, id, ZS_COMMAND_UUID_BYTES);
  return true;
}

bool zs_fw_chunk_decode(const uint8_t *bytes, size_t size, zs_fw_chunk_t *chunk) {
  zs_cbor_reader_t r;
  if (!bytes || !chunk || size == 0u || size > ZS_FW_CHUNK_MESSAGE_MAX_BYTES) return false;
  memset(chunk, 0, sizeof(*chunk));
  zs_cbor_reader_init(&r, bytes, size);
  return read_head(&r, ZS_FW_CHUNK_MESSAGE_TYPE, &chunk->station_id, chunk->command_id, &chunk->offset) &&
         expect_key(&r, 5u) && zs_cbor_read_bytes(&r, &chunk->data, &chunk->data_len) &&
         chunk->data_len > 0u && chunk->data_len <= ZS_FW_CHUNK_BYTES && zs_cbor_reader_at_end(&r);
}

bool zs_fw_request_decode(const uint8_t *bytes, size_t size, uint32_t *station_id, uint8_t command_id[ZS_COMMAND_UUID_BYTES],
                          uint32_t *offset, uint32_t *length) {
  zs_cbor_reader_t r;
  if (!bytes || !station_id || !command_id || !offset || !length || size == 0u || size > ZS_FW_REQUEST_MAX_BYTES) return false;
  zs_cbor_reader_init(&r, bytes, size);
  return read_head(&r, ZS_FW_REQUEST_MESSAGE_TYPE, station_id, command_id, offset) &&
         expect_key(&r, 5u) && read_u32(&r, length) && *length > 0u && *length <= ZS_FW_CHUNK_BYTES &&
         zs_cbor_reader_at_end(&r);
}

/* ---- download engine ---- */

static void finish(zs_fw_download_t *dl, zs_command_ack_result_t result, uint16_t detail) {
  dl->state = ZS_FW_DOWNLOAD_FINISHED;
  dl->result = result;
  dl->detail = detail;
}

bool zs_fw_download_start(zs_fw_download_t *dl, const zs_fw_image_io_t *io, uint32_t station_id,
                          const uint8_t command_id[ZS_COMMAND_UUID_BYTES], const zs_fw_manifest_t *manifest) {
  if (!dl) return false;
  memset(dl, 0, sizeof(*dl));
  if (!io || !io->erase || !io->program || !io->read || io->page_bytes == 0u || !command_id || !manifest ||
      station_id == 0u || manifest->size == 0u || manifest->size > io->capacity)
    return false;
  dl->io = io;
  dl->station_id = station_id;
  memcpy(dl->command_id, command_id, ZS_COMMAND_UUID_BYTES);
  dl->manifest = *manifest;
  dl->erase_end = ((manifest->size + io->page_bytes - 1u) / io->page_bytes) * io->page_bytes;
  dl->state = ZS_FW_DOWNLOAD_ERASING;
  return true;
}

bool zs_fw_download_active(const zs_fw_download_t *dl) {
  return dl && dl->state != ZS_FW_DOWNLOAD_IDLE && dl->state != ZS_FW_DOWNLOAD_FINISHED;
}

void zs_fw_download_abort(zs_fw_download_t *dl) {
  if (dl) memset(dl, 0, sizeof(*dl));
}

void zs_fw_download_fail(zs_fw_download_t *dl, uint16_t detail) {
  if (zs_fw_download_active(dl)) finish(dl, ZS_COMMAND_ACK_FAILED, detail);
}

static zs_fw_step_t verify_step(zs_fw_download_t *dl, uint32_t budget) {
  uint8_t block[256];
  uint32_t done = 0u;
  while (dl->verify_offset < dl->manifest.size && done < budget) {
    uint32_t n = dl->manifest.size - dl->verify_offset;
    if (n > sizeof(block)) n = sizeof(block);
    if (!dl->io->read(dl->io->ctx, dl->verify_offset, block, n)) { finish(dl, ZS_COMMAND_ACK_FAILED, ZS_FW_FAIL_FLASH); return ZS_FW_STEP_FINISHED; }
    zs_sha256_update(&dl->sha, block, n);
    dl->verify_offset += n;
    done += n;
  }
  if (dl->verify_offset < dl->manifest.size) return ZS_FW_STEP_BUSY;
  {
    uint8_t digest[ZS_SHA256_DIGEST_BYTES], info_bytes[ZS_FW_INFO_BYTES];
    zs_fw_info_t info;
    zs_sha256_final(&dl->sha, digest);
    if (!zs_sha256_equal(digest, dl->manifest.sha256, sizeof(digest))) { finish(dl, ZS_COMMAND_ACK_FAILED, ZS_FW_FAIL_SHA256); return ZS_FW_STEP_FINISHED; }
    if (!dl->io->read(dl->io->ctx, ZS_FW_INFO_OFFSET, info_bytes, sizeof(info_bytes))) { finish(dl, ZS_COMMAND_ACK_FAILED, ZS_FW_FAIL_FLASH); return ZS_FW_STEP_FINISHED; }
    if (!zs_fw_info_parse(info_bytes, &info) || info.target != dl->manifest.target || info.version != dl->manifest.version) {
      finish(dl, ZS_COMMAND_ACK_FAILED, ZS_FW_FAIL_INFO);
      return ZS_FW_STEP_FINISHED;
    }
  }
  finish(dl, ZS_COMMAND_ACK_OK, dl->chunks > 0xFFFFu ? 0xFFFFu : (uint16_t)dl->chunks);
  return ZS_FW_STEP_FINISHED;
}

zs_fw_step_t zs_fw_download_step(zs_fw_download_t *dl, uint32_t budget_bytes) {
  if (!dl || dl->state == ZS_FW_DOWNLOAD_IDLE) return ZS_FW_STEP_IDLE;
  switch (dl->state) {
    case ZS_FW_DOWNLOAD_ERASING: {
      uint32_t pages = budget_bytes / 65536u;
      if (pages == 0u) pages = 1u;
      while (pages-- > 0u && dl->erase_offset < dl->erase_end) {
        if (!dl->io->erase(dl->io->ctx, dl->erase_offset, dl->io->page_bytes)) { finish(dl, ZS_COMMAND_ACK_FAILED, ZS_FW_FAIL_FLASH); return ZS_FW_STEP_FINISHED; }
        dl->erase_offset += dl->io->page_bytes;
      }
      if (dl->erase_offset < dl->erase_end) return ZS_FW_STEP_BUSY;
      /* the boot record of the other bank goes too: a stale trial/rollback mark must not survive a new image */
      if (dl->io->record_offset && !dl->io->erase(dl->io->ctx, dl->io->record_offset, dl->io->page_bytes)) {
        finish(dl, ZS_COMMAND_ACK_FAILED, ZS_FW_FAIL_FLASH);
        return ZS_FW_STEP_FINISHED;
      }
      dl->state = ZS_FW_DOWNLOAD_FETCHING;
      return ZS_FW_STEP_NEED_CHUNK;
    }
    case ZS_FW_DOWNLOAD_FETCHING:
      return ZS_FW_STEP_NEED_CHUNK;
    case ZS_FW_DOWNLOAD_VERIFYING:
      return verify_step(dl, budget_bytes ? budget_bytes : 1u);
    case ZS_FW_DOWNLOAD_FINISHED:
      return ZS_FW_STEP_FINISHED;
    case ZS_FW_DOWNLOAD_IDLE:
    default:
      return ZS_FW_STEP_IDLE;
  }
}

uint32_t zs_fw_download_want(const zs_fw_download_t *dl) {
  uint32_t n;
  if (!dl || dl->state != ZS_FW_DOWNLOAD_FETCHING || dl->offset >= dl->manifest.size) return 0u;
  n = dl->manifest.size - dl->offset;
  return n > ZS_FW_CHUNK_BYTES ? ZS_FW_CHUNK_BYTES : n;
}

size_t zs_fw_download_request(const zs_fw_download_t *dl, uint8_t *out, size_t cap) {
  const uint32_t want = zs_fw_download_want(dl);
  if (want == 0u) return 0u;
  return zs_fw_request_encode(dl->station_id, dl->command_id, dl->offset, want, out, cap);
}

zs_fw_chunk_result_t zs_fw_download_on_chunk(zs_fw_download_t *dl, const zs_fw_chunk_t *chunk) {
  const uint32_t want = zs_fw_download_want(dl);
  size_t aligned;
  if (!chunk || want == 0u || chunk->station_id != dl->station_id ||
      memcmp(chunk->command_id, dl->command_id, ZS_COMMAND_UUID_BYTES) != 0 ||
      chunk->offset != dl->offset || chunk->data_len != want || !chunk->data)
    return ZS_FW_CHUNK_IGNORED;
  aligned = chunk->data_len - chunk->data_len % ZS_FW_PROGRAM_ALIGN;
  if (aligned && !dl->io->program(dl->io->ctx, dl->offset, chunk->data, aligned)) {
    finish(dl, ZS_COMMAND_ACK_FAILED, ZS_FW_FAIL_FLASH);
    return ZS_FW_CHUNK_FAILED;
  }
  if (aligned < chunk->data_len) {                       /* the image tail: one quad-word padded with erased bytes */
    uint8_t tail[ZS_FW_PROGRAM_ALIGN];
    memset(tail, 0xff, sizeof(tail));
    memcpy(tail, &chunk->data[aligned], chunk->data_len - aligned);
    if (!dl->io->program(dl->io->ctx, dl->offset + (uint32_t)aligned, tail, sizeof(tail))) {
      finish(dl, ZS_COMMAND_ACK_FAILED, ZS_FW_FAIL_FLASH);
      return ZS_FW_CHUNK_FAILED;
    }
  }
  dl->offset += (uint32_t)chunk->data_len;
  dl->chunks++;
  if (dl->offset >= dl->manifest.size) {
    dl->state = ZS_FW_DOWNLOAD_VERIFYING;
    dl->verify_offset = 0u;
    zs_sha256_init(&dl->sha);
  }
  return ZS_FW_CHUNK_ACCEPTED;
}
