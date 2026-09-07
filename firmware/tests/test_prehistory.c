#include "zs_adpcm.h"
#include "zs_archive.h"
#include "zs_prehistory.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MOCK_ERASE 4096u
#define MOCK_BYTES (2u * 1024u * 1024u)
#define RING_BYTES (32u * 16384u)
#define FRAME_SAMPLES 32000u

static uint8_t *g_flash;

typedef struct {
  uint32_t erase_calls;
  uint32_t write_calls;
} mock_ctx_t;

static int flash_read(void *ctx, uint32_t address, uint8_t *data, size_t len) {
  (void)ctx;
  if (!data || (uint64_t)address + len > MOCK_BYTES) return -1;
  memcpy(data, &g_flash[address], len);
  return 0;
}

static int flash_write(void *ctx, uint32_t address, const uint8_t *data, size_t len) {
  mock_ctx_t *m = (mock_ctx_t *)ctx;
  if (!data || (uint64_t)address + len > MOCK_BYTES) return -1;
  for (size_t i = 0u; i < len; ++i) {
    if ((g_flash[address + i] & data[i]) != data[i]) return -2;
  }
  for (size_t i = 0u; i < len; ++i) g_flash[address + i] &= data[i];
  m->write_calls++;
  return 0;
}

static int flash_erase(void *ctx, uint32_t address, size_t len) {
  mock_ctx_t *m = (mock_ctx_t *)ctx;
  if ((address % MOCK_ERASE) != 0u || (len % MOCK_ERASE) != 0u ||
      (uint64_t)address + len > MOCK_BYTES) {
    return -1;
  }
  memset(&g_flash[address], 0xff, len);
  m->erase_calls++;
  return 0;
}

static zs_archive_storage_t make_storage(mock_ctx_t *ctx) {
  return (zs_archive_storage_t){
      .ctx = ctx,
      .size_bytes = MOCK_BYTES,
      .erase_block_bytes = MOCK_ERASE,
      .read = flash_read,
      .write = flash_write,
      .erase = flash_erase,
  };
}

static void test_adpcm_known_vector(void) {
  const int16_t samples[] = {0, 1000, -1000, 2000, -2000, 3000, -3000, 100, 0};
  const uint8_t expected[] = {0x00u, 0x00u, 0x00u, 0x00u, 0xf7u, 0xf7u, 0xf7u, 0x82u};
  uint8_t encoded[32] = {0};
  size_t encoded_bytes = 0u;
  assert(zs_ima_adpcm_block_bytes_for_samples(9u) == sizeof(expected));
  assert(zs_ima_adpcm_encode_block(samples, 9u, encoded, sizeof(encoded), &encoded_bytes));
  assert(encoded_bytes == sizeof(expected));
  assert(memcmp(encoded, expected, sizeof(expected)) == 0);
  assert(zs_ima_adpcm_block_bytes_for_samples(FRAME_SAMPLES) == 16004u);
}

static void write_constant_frame(zs_prehistory_t *ring, uint32_t sequence) {
  assert(zs_prehistory_begin_frame(ring, (int64_t)sequence * 1000000LL));
  int16_t chunk[257];
  const int16_t value = (int16_t)(sequence * 100u);
  for (unsigned i = 0u; i < 257u; ++i) chunk[i] = value;
  uint32_t remaining = FRAME_SAMPLES;
  while (remaining != 0u) {
    const uint32_t n = remaining < 257u ? remaining : 257u;
    assert(zs_prehistory_push_pcm(ring, chunk, n));
    remaining -= n;
  }
  assert(zs_prehistory_finalize_frame(ring));
}

static zs_archive_t make_event_archive(const zs_archive_storage_t *storage) {
  const zs_archive_layout_t layout = {
      .base_address = 0u,
      .total_bytes = MOCK_BYTES,
      .prehistory_ring_bytes = RING_BYTES,
      .slot_bytes = 128u * MOCK_ERASE,
      .slot_count = 1u,
      .max_pre_bytes = 480120u,
      .max_post_bytes = 0u,
  };
  zs_archive_t archive;
  assert(zs_archive_init(&archive, storage, &layout));
  return archive;
}

static void test_ring_wrap_copy_recover(void) {
  memset(g_flash, 0xff, MOCK_BYTES);
  mock_ctx_t ctx = {0};
  const zs_archive_storage_t storage = make_storage(&ctx);

  zs_prehistory_t ring;
  assert(zs_prehistory_init(&ring, &storage, 0u, RING_BYTES, FRAME_SAMPLES));
  assert(ring.record_bytes == 16384u);
  assert(ring.record_count == 32u);
  assert(zs_prehistory_recover(&ring));
  assert(ring.next_sequence == 0u && ring.available_records == 0u);

  for (uint32_t seq = 0u; seq < 35u; ++seq) write_constant_frame(&ring, seq);
  assert(ring.next_sequence == 35u);
  assert(ring.available_records == 32u);

  zs_prehistory_record_info_t info;
  assert(!zs_prehistory_read_record_info(&ring, 2u, &info));
  assert(zs_prehistory_read_record_info(&ring, 3u, &info));
  assert(info.sequence == 3u && info.payload_bytes == 16004u && info.sample_count == FRAME_SAMPLES);

  zs_archive_t archive = make_event_archive(&storage);
  assert(zs_archive_prepare_slot(&archive, 0u));
  assert(zs_archive_begin(&archive, 0u, 77u, 35000000LL));
  uint8_t scratch[257];
  zs_prehistory_copy_result_t copied;
  assert(zs_prehistory_copy_latest(&ring, &archive, 30u, scratch, sizeof(scratch), &copied));
  assert(copied.records_copied == 30u);
  assert(copied.bytes_copied == 480120u);
  assert(copied.start_time_us == 5000000LL);
  assert(copied.end_time_us == 35000000LL);
  assert(archive.pre_written == 480120u);

  uint8_t first_header[4] = {0};
  assert(flash_read(&ctx, zs_archive_pre_payload_address(&archive, 0u),
                    first_header, sizeof(first_header)) == 0);
  const int16_t first_predictor =
      (int16_t)((uint16_t)first_header[0] | ((uint16_t)first_header[1] << 8));
  assert(first_predictor == 500);
  assert(first_header[2] == 0u && first_header[3] == 0u);

  assert(zs_archive_finalize(&archive, 30000u, 0u,
                             ZS_ARCHIVE_CODEC_IMA_ADPCM_MONO,
                             ZS_ARCHIVE_CODEC_PCM16_INTERLEAVED,
                             1u, FRAME_SAMPLES, FRAME_SAMPLES));

  /* Reconstruct state from headers only after a simulated reboot. */
  zs_prehistory_t recovered;
  assert(zs_prehistory_init(&recovered, &storage, 0u, RING_BYTES, FRAME_SAMPLES));
  assert(zs_prehistory_recover(&recovered));
  assert(recovered.next_sequence == 35u && recovered.available_records == 32u);

  /* Simulate power loss in record 35: payload exists but the commit header does not. */
  assert(zs_prehistory_begin_frame(&recovered, 35000000LL));
  int16_t partial[100];
  for (unsigned i = 0u; i < 100u; ++i) partial[i] = 3500;
  assert(zs_prehistory_push_pcm(&recovered, partial, 100u));

  zs_prehistory_t after_loss;
  assert(zs_prehistory_init(&after_loss, &storage, 0u, RING_BYTES, FRAME_SAMPLES));
  assert(zs_prehistory_recover(&after_loss));
  assert(after_loss.next_sequence == 35u);
  assert(after_loss.available_records == 31u); /* erased oldest record was not replaced */

  /* CRC is checked before event slot mutation. Corrupt the latest completed payload. */
  const uint32_t seq34_slot = 34u % 32u;
  const uint32_t corrupt_address = seq34_slot * 16384u + ZS_PREHISTORY_HEADER_BYTES;
  g_flash[corrupt_address] ^= 0x01u;

  zs_archive_t archive2 = make_event_archive(&storage);
  assert(zs_archive_prepare_slot(&archive2, 0u));
  assert(zs_archive_begin(&archive2, 0u, 78u, 35000000LL));
  assert(!zs_prehistory_copy_latest(&after_loss, &archive2, 30u,
                                    scratch, sizeof(scratch), &copied));
  assert(archive2.pre_written == 0u);
}

int main(void) {
  g_flash = (uint8_t *)malloc(MOCK_BYTES);
  assert(g_flash != NULL);
  test_adpcm_known_vector();
  test_ring_wrap_copy_recover();
  free(g_flash);
  puts("zs_prehistory_tests: OK");
  return 0;
}
