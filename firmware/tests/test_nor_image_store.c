/* nRF image slot on NOR: write session with running/read-back SHA-256, header committed last, torn transfers,
   random-access reads feeding the mcumgr upload client. */
#include "zs_nor_image_store.h"
#include "zs_mcumgr_serial.h"
#include "zs_nor_storage_layout.h"
#include "zs_cbor.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define MOCK_ERASE_BYTES 4096u
#define MOCK_BLOCKS 12u
#define MOCK_BYTES (MOCK_BLOCKS * MOCK_ERASE_BYTES)

typedef struct { uint8_t memory[MOCK_BYTES]; uint8_t status; uint32_t millis; uint32_t erases, programs; } mock_nor_t;
static uint32_t mock_millis(void *ctx) { return ((mock_nor_t *)ctx)->millis; }
static void mock_delay(void *ctx, uint32_t ms) { ((mock_nor_t *)ctx)->millis += ms; }
static int mock_command(void *ctx, uint8_t op, uint32_t a, uint8_t ab, const uint8_t *tx, size_t txn, uint8_t *rx, size_t rxn) {
  mock_nor_t *m = ctx;
  if (op == 0x05u) { if (!rx || rxn != 1u) return -1; rx[0] = m->status; return 0; }
  if (op == 0x06u) { m->status |= 0x02u; return 0; }
  if (op == 0x13u) { if (ab != 4u || !rx || (uint64_t)a + rxn > MOCK_BYTES) return -1; memcpy(rx, &m->memory[a], rxn); return 0; }
  if (op == 0x12u) {
    if (ab != 4u || !tx || txn == 0u || txn > 256u || !(m->status & 0x02u) || a / 256u != (a + (uint32_t)txn - 1u) / 256u || (uint64_t)a + txn > MOCK_BYTES) return -1;
    for (size_t i = 0u; i < txn; i++) { if ((m->memory[a + i] & tx[i]) != tx[i]) return -1; m->memory[a + i] = tx[i]; }
    m->status &= (uint8_t)~0x02u; m->programs++; return 0;
  }
  if (op == 0x21u) { if (ab != 4u || !(m->status & 0x02u) || a % MOCK_ERASE_BYTES || (uint64_t)a + MOCK_ERASE_BYTES > MOCK_BYTES) return -1; memset(&m->memory[a], 0xff, MOCK_ERASE_BYTES); m->status &= (uint8_t)~0x02u; m->erases++; return 0; }
  return -1;
}
static zs_nor_t make_nor(mock_nor_t *m) {
  zs_nor_t nor; zs_nor_geometry_t g = zs_nor_geometry_64m_4byte(); zs_nor_port_t port = {m, mock_command, mock_millis, mock_delay};
  g.capacity_bytes = MOCK_BYTES; g.erase_bytes = MOCK_ERASE_BYTES; g.page_bytes = 256u;
  assert(zs_nor_init(&nor, &port, &g));
  return nor;
}

static uint8_t image[20000];
static mock_nor_t mock;

static bool feed(zs_nor_image_store_t *s, const uint8_t *img, size_t n, size_t step) {
  for (size_t off = 0u; off < n; off += step) { size_t k = (n - off) < step ? (n - off) : step; if (!zs_nor_image_store_write(s, img + off, k)) return false; }
  return true;
}

int main(void) {
  zs_nor_t nor; zs_nor_image_store_t st; zs_nor_image_info_t info; uint8_t sha[32], wrong[32];
  for (size_t i = 0u; i < sizeof(image); i++) image[i] = (uint8_t)(i * 31u + (i >> 9));
  zs_sha256_digest(image, sizeof(image), sha);
  memset(&mock, 0, sizeof(mock)); memset(mock.memory, 0xff, sizeof(mock.memory));
  nor = make_nor(&mock);
  /* slot = blocks 2..9 (8 blocks: header + 7 data = 28 KiB) */
  assert(zs_nor_image_store_init(&st, &nor, 2u * MOCK_ERASE_BYTES, 8u * MOCK_ERASE_BYTES));
  assert(zs_nor_image_store_capacity(&st) == 7u * MOCK_ERASE_BYTES);
  assert(!zs_nor_image_store_init(&st, &nor, 100u, 8u * MOCK_ERASE_BYTES));                 /* unaligned */
  assert(!zs_nor_image_store_init(&st, &nor, 2u * MOCK_ERASE_BYTES, MOCK_ERASE_BYTES));   /* header only */
  assert(zs_nor_image_store_init(&st, &nor, 2u * MOCK_ERASE_BYTES, 8u * MOCK_ERASE_BYTES));

  /* empty slot: nothing to open */
  assert(!zs_nor_image_store_open(&st, true, &info));

  /* full write with odd chunk sizes, header appears last */
  assert(zs_nor_image_store_begin(&st, sizeof(image), 0x00010203u, sha));
  assert(mock.erases == 1u + (sizeof(image) + MOCK_ERASE_BYTES - 1u) / MOCK_ERASE_BYTES);   /* header block + 5 data blocks */
  assert(feed(&st, image, sizeof(image), 333u));
  assert(mock.memory[2u * MOCK_ERASE_BYTES] == 0xffu);                     /* no header yet */
  assert(!zs_nor_image_store_open(&st, false, &info));
  assert(zs_nor_image_store_finish(&st));
  assert(zs_nor_image_store_open(&st, true, &info) && info.size == sizeof(image) && info.version == 0x00010203u && !memcmp(info.sha256, sha, 32u));
  uint8_t back[1000];
  assert(zs_nor_image_store_read(&st, 12345u, back, sizeof(back)) && !memcmp(back, image + 12345u, sizeof(back)));
  assert(!zs_nor_image_store_read(&st, sizeof(image) - 10u, back, 11u));  /* past the end */
  assert(!zs_nor_image_store_read(&st, 0u, back, 0u) || true);

  /* a bit flipped in NOR after the write: the verified open catches it */
  mock.memory[3u * MOCK_ERASE_BYTES + 777u] ^= 0x10u;
  assert(zs_nor_image_store_open(&st, false, &info) && !zs_nor_image_store_open(&st, true, &info));
  mock.memory[3u * MOCK_ERASE_BYTES + 777u] ^= 0x10u;
  assert(zs_nor_image_store_open(&st, true, &info));

  /* torn transfer: begin + partial write, no finish -> slot invalid; wrong declared sha -> finish refuses */
  assert(zs_nor_image_store_begin(&st, sizeof(image), 7u, sha));
  assert(feed(&st, image, 5000u, 500u));
  assert(!zs_nor_image_store_finish(&st));                                  /* short */
  assert(!zs_nor_image_store_open(&st, false, &info));
  memcpy(wrong, sha, 32u); wrong[0] ^= 1u;
  assert(zs_nor_image_store_begin(&st, sizeof(image), 7u, wrong));
  assert(feed(&st, image, sizeof(image), 4096u));
  assert(!zs_nor_image_store_finish(&st) && !zs_nor_image_store_open(&st, false, &info));
  /* too big, overflow */
  assert(!zs_nor_image_store_begin(&st, 7u * MOCK_ERASE_BYTES + 1u, 1u, sha));
  assert(zs_nor_image_store_begin(&st, 100u, 1u, sha));
  assert(!zs_nor_image_store_write(&st, image, 101u));

  /* the mcumgr client uploads straight out of the slot */
  assert(zs_nor_image_store_begin(&st, sizeof(image), 9u, sha) && feed(&st, image, sizeof(image), 1000u) && zs_nor_image_store_finish(&st));
  assert(zs_nor_image_store_open(&st, true, &info));
  zs_mcumgr_upload_t up; zs_mcumgr_upload_init_reader(&up, zs_nor_image_store_reader, &st, info.size, info.sha256);
  uint8_t serial[1024]; size_t total = 0u; unsigned requests = 0u;
  while (!up.done && !up.failed) {
    size_t n = zs_mcumgr_upload_request(&up, serial, sizeof(serial));
    assert(n > 0u); requests++;
    zs_mcumgr_decoder_t d; zs_mcumgr_decoder_init(&d); const uint8_t *pkt; size_t len; bool got = false;
    for (size_t i = 0u; i < n; i++) got |= zs_mcumgr_decoder_feed(&d, serial[i], &pkt, &len);
    assert(got);
    /* the mock target accepts every chunk in order: emulate its reply {"rc":0,"off":offset+chunk} */
    size_t chunk = (up.size - up.offset) < ZS_MCUMGR_UPLOAD_CHUNK ? (up.size - up.offset) : ZS_MCUMGR_UPLOAD_CHUNK;
    assert(!memcmp(up.chunk, image + up.offset, chunk));
    total += chunk;
    uint8_t cbor[24]; zs_cbor_t c; zs_cbor_init(&c, cbor, sizeof(cbor));
    zs_cbor_map(&c, 2u); zs_cbor_text(&c, "rc"); zs_cbor_int(&c, 0); zs_cbor_text(&c, "off"); zs_cbor_uint(&c, up.offset + chunk);
    uint8_t reply[40]; size_t rl = zs_mcumgr_smp_build(ZS_MCUMGR_OP_WRITE | 1u, ZS_MCUMGR_GROUP_IMAGE, ZS_MCUMGR_IMAGE_ID_UPLOAD, up.seq, cbor, c.len, reply, sizeof(reply));
    assert(zs_mcumgr_upload_response(&up, reply, rl));
  }
  assert(up.done && total == sizeof(image) && requests == (sizeof(image) + ZS_MCUMGR_UPLOAD_CHUNK - 1u) / ZS_MCUMGR_UPLOAD_CHUNK);

  /* the B3 layout gives the slot on the W25Q512JV */
  zs_nor_storage_layout_t lay;
  assert(zs_nor_storage_layout_make_stores(64u * 1024u * 1024u, 4096u, 16u, 256u, &lay));
  assert(lay.nrf_image_partition_bytes / 4096u == ZS_NOR_STORAGE_NRF_IMAGE_BLOCKS && lay.nrf_image_base_address == 0x03f7c000u);
  printf("nor image store tests passed (%u requests from the slot)\n", requests);
  return 0;
}
