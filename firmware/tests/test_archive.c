#include "zs_archive.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define MOCK_BYTES 65536u
#define MOCK_ERASE 4096u

static uint8_t g_flash[MOCK_BYTES];

typedef struct {
  unsigned erase_calls;
  unsigned write_calls;
} mock_ctx_t;

static int mock_read(void *ctx, uint32_t address, uint8_t *data, size_t len) {
  (void)ctx;
  if (!data || (uint64_t)address + len > MOCK_BYTES) {
    return -1;
  }
  memcpy(data, &g_flash[address], len);
  return 0;
}

static int mock_write(void *ctx, uint32_t address, const uint8_t *data, size_t len) {
  mock_ctx_t *m = (mock_ctx_t *)ctx;
  if (!data || (uint64_t)address + len > MOCK_BYTES) {
    return -1;
  }
  for (size_t i = 0; i < len; ++i) {
    if ((g_flash[address + i] & data[i]) != data[i]) {
      return -2; /* NOR cannot program 0 back to 1 without erase. */
    }
  }
  for (size_t i = 0; i < len; ++i) {
    g_flash[address + i] &= data[i];
  }
  m->write_calls++;
  return 0;
}

static int mock_erase(void *ctx, uint32_t address, size_t len) {
  mock_ctx_t *m = (mock_ctx_t *)ctx;
  if (address % MOCK_ERASE != 0u || len % MOCK_ERASE != 0u ||
      (uint64_t)address + len > MOCK_BYTES) {
    return -1;
  }
  memset(&g_flash[address], 0xff, len);
  m->erase_calls++;
  return 0;
}

static void test_default_capacity(void) {
  zs_archive_layout_t layout;
  assert(zs_archive_make_default_layout(0u, 64u * 1024u * 1024u, 4096u, &layout));
  assert(layout.slot_count == 3u);
  assert(layout.max_pre_bytes == 480000u);
  assert(layout.max_post_bytes == 7680000u);
  assert(layout.slot_bytes == 8163328u);
  assert(layout.prehistory_ring_bytes == 42618880u);
  assert((uint64_t)layout.prehistory_ring_bytes +
             (uint64_t)layout.slot_bytes * layout.slot_count <=
         64u * 1024u * 1024u);
}

static void test_archive_roundtrip(void) {
  memset(g_flash, 0x00, sizeof(g_flash));
  mock_ctx_t mock = {0};
  zs_archive_storage_t storage = {
      .ctx = &mock,
      .size_bytes = MOCK_BYTES,
      .erase_block_bytes = MOCK_ERASE,
      .read = mock_read,
      .write = mock_write,
      .erase = mock_erase,
  };
  zs_archive_layout_t layout = {
      .base_address = 0u,
      .total_bytes = MOCK_BYTES,
      .prehistory_ring_bytes = MOCK_ERASE,
      .slot_bytes = 4u * MOCK_ERASE,
      .slot_count = 3u,
      .max_pre_bytes = 4096u,
      .max_post_bytes = 8192u,
  };
  zs_archive_t archive;
  assert(zs_archive_init(&archive, &storage, &layout));

  /* Erase is an idle-time operation, not part of the event critical path. */
  assert(zs_archive_prepare_slot(&archive, 1u));
  assert(mock.erase_calls == 1u);
  assert(zs_archive_begin(&archive, 1u, 0x1122334455667788ULL, 1780000000123456LL));
  assert(mock.erase_calls == 1u);

  const uint8_t pre_a[] = {1, 2, 3, 4, 5};
  const uint8_t pre_b[] = {6, 7, 8};
  const uint8_t post_a[] = {10, 11, 12, 13, 14, 15};
  assert(zs_archive_write_pre(&archive, pre_a, sizeof(pre_a)));
  assert(zs_archive_write_pre(&archive, pre_b, sizeof(pre_b)));
  assert(zs_archive_write_post(&archive, post_a, sizeof(post_a)));
  assert(zs_archive_finalize(&archive, 30000u, 30000u,
                             ZS_ARCHIVE_CODEC_IMA_ADPCM_MONO,
                             ZS_ARCHIVE_CODEC_PCM16_INTERLEAVED,
                             4u, 32000u, 32000u));
  assert(!archive.active);

  zs_archive_header_t h;
  assert(zs_archive_read_header(&archive, 1u, &h));
  assert(h.event_id == 0x1122334455667788ULL);
  assert(h.event_time_us == 1780000000123456LL);
  assert(h.pre_bytes == 8u);
  assert(h.post_bytes == 6u);
  assert(h.pre_duration_ms == 30000u && h.post_duration_ms == 30000u);
  assert(h.pre_codec == ZS_ARCHIVE_CODEC_IMA_ADPCM_MONO);
  assert(h.post_codec == ZS_ARCHIVE_CODEC_PCM16_INTERLEAVED);
  assert(h.post_channels == 4u);

  uint8_t check[8];
  assert(mock_read(&mock, zs_archive_pre_payload_address(&archive, 1u), check, sizeof(check)) == 0);
  const uint8_t expected_pre[] = {1, 2, 3, 4, 5, 6, 7, 8};
  assert(memcmp(check, expected_pre, sizeof(check)) == 0);

  /* A header bit flip must invalidate the slot. */
  const uint32_t hdr = zs_archive_slot_address(&archive, 1u);
  g_flash[hdr + 20u] ^= 0x01u;
  assert(!zs_archive_read_header(&archive, 1u, &h));
}

int main(void) {
  test_default_capacity();
  test_archive_roundtrip();
  puts("zs_archive_tests: OK");
  return 0;
}
