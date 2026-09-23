/* mcumgr serial client against a mock of MCUboot serial recovery (boot_serial): framing, CRC, base64,
   SMP header, image upload with resume, reset. */
#include "zs_mcumgr_serial.h"
#include "zs_cbor.h"
#include "zs_cbor_read.h"
#include "zs_sha256.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- mock target ------------------------------------------------------------------------------- */
static struct {
  zs_mcumgr_decoder_t dec;
  uint8_t slot[70000];
  size_t received, declared_len;
  uint8_t sha[32];
  unsigned uploads, resets, drop_next, corrupt_next;
  uint8_t out[1024];
  size_t out_len;
} tgt;

static void tgt_reply(uint8_t seq, int rc, size_t off) {
  uint8_t cbor[32], pkt[64];
  zs_cbor_t c; zs_cbor_init(&c, cbor, sizeof(cbor));
  zs_cbor_map(&c, 2u); zs_cbor_text(&c, "rc"); zs_cbor_int(&c, rc); zs_cbor_text(&c, "off"); zs_cbor_uint(&c, off);
  size_t n = zs_mcumgr_smp_build(ZS_MCUMGR_OP_WRITE | 1u, ZS_MCUMGR_GROUP_IMAGE, ZS_MCUMGR_IMAGE_ID_UPLOAD, seq, cbor, c.len, pkt, sizeof(pkt));
  tgt.out_len = zs_mcumgr_frame_encode(pkt, n, tgt.out, sizeof(tgt.out));
  if (tgt.corrupt_next) { tgt.out[10] ^= 0x01u; tgt.corrupt_next--; }   /* flip a base64 char: CRC must reject it */
  if (tgt.drop_next) { tgt.out_len = 0u; tgt.drop_next--; }
}

static void tgt_handle(const uint8_t *pkt, size_t len) {
  zs_smp_header_t h; const uint8_t *cbor; size_t cl;
  assert(zs_mcumgr_smp_parse(pkt, len, &h, &cbor, &cl));
  if (h.group_lo == ZS_MCUMGR_GROUP_OS && h.id == ZS_MCUMGR_OS_ID_RESET) { tgt.resets++; tgt.out_len = 0u; return; }
  assert(h.op == ZS_MCUMGR_OP_WRITE && h.group_lo == ZS_MCUMGR_GROUP_IMAGE && h.id == ZS_MCUMGR_IMAGE_ID_UPLOAD);
  zs_cbor_reader_t r; zs_cbor_reader_init(&r, cbor, cl);
  uint32_t count; assert(zs_cbor_read_map(&r, &count));
  uint64_t off = 0u, ln = 0u, image = 0u; const uint8_t *data = NULL; size_t dn = 0u; const uint8_t *sha = NULL; size_t shan = 0u;
  for (uint32_t i = 0u; i < count; i++) {
    char key[8]; assert(zs_cbor_read_text(&r, key, sizeof(key)));
    if (!strcmp(key, "off")) assert(zs_cbor_read_uint(&r, &off));
    else if (!strcmp(key, "len")) assert(zs_cbor_read_uint(&r, &ln));
    else if (!strcmp(key, "image")) assert(zs_cbor_read_uint(&r, &image));
    else if (!strcmp(key, "data")) assert(zs_cbor_read_bytes(&r, &data, &dn));
    else if (!strcmp(key, "sha")) assert(zs_cbor_read_bytes(&r, &sha, &shan));
    else assert(!"unexpected key");
  }
  assert(zs_cbor_reader_at_end(&r) && data);
  assert(len <= ZS_MCUMGR_PACKET_MAX);
  tgt.uploads++;
  if (off == 0u) { assert(ln && sha && shan == 32u); tgt.declared_len = (size_t)ln; memcpy(tgt.sha, sha, 32u); tgt.received = 0u; }
  if (off != tgt.received) { tgt_reply(h.seq, 0, tgt.received); return; }   /* out of order: tell the client where we are */
  memcpy(tgt.slot + off, data, dn);
  tgt.received = (size_t)off + dn;
  tgt_reply(h.seq, 0, tgt.received);
}

static void tgt_feed(const uint8_t *serial, size_t n) {
  for (size_t i = 0u; i < n; i++) { const uint8_t *pkt; size_t len; if (zs_mcumgr_decoder_feed(&tgt.dec, serial[i], &pkt, &len)) tgt_handle(pkt, len); }
}

/* ---- tests -------------------------------------------------------------------------------------- */
static void test_framing(void) {
  static const uint8_t pkt[] = {2, 0, 0, 2, 0, 1, 7, 1, 0xa0, 0x00};
  uint8_t serial[256];
  size_t n = zs_mcumgr_frame_encode(pkt, sizeof(pkt), serial, sizeof(serial));
  assert(n > 0u && serial[0] == 0x06u && serial[1] == 0x09u && serial[n - 1u] == '\n');
  zs_mcumgr_decoder_t d; zs_mcumgr_decoder_init(&d);
  const uint8_t *out = NULL; size_t out_len = 0u; bool got = false;
  for (size_t i = 0u; i < n; i++) got |= zs_mcumgr_decoder_feed(&d, serial[i], &out, &out_len);
  assert(got && out_len == sizeof(pkt) && !memcmp(out, pkt, sizeof(pkt)) && d.packets == 1u && d.bad_frames == 0u);
  /* a long packet spans several frames of <= 127 bytes, continuation markers 04 14 */
  uint8_t big[300]; for (unsigned i = 0u; i < sizeof(big); i++) big[i] = (uint8_t)i;
  uint8_t wire[600];
  n = zs_mcumgr_frame_encode(big, sizeof(big), wire, sizeof(wire));
  unsigned lines = 0u, longest = 0u, cur = 0u;
  for (size_t i = 0u; i < n; i++) { cur++; if (wire[i] == '\n') { lines++; if (cur > longest) longest = cur; cur = 0u; } }
  assert(lines == 4u && longest <= ZS_MCUMGR_FRAME_MAX && wire[0] == 0x06u && wire[1] == 0x09u);
  zs_mcumgr_decoder_init(&d); got = false;
  for (size_t i = 0u; i < n; i++) got |= zs_mcumgr_decoder_feed(&d, wire[i], &out, &out_len);
  assert(got && out_len == sizeof(big) && !memcmp(out, big, sizeof(big)));
  /* CRC-16/XMODEM check value and a corrupted frame */
  assert(zs_mcumgr_crc16((const uint8_t *)"123456789", 9u) == 0x31C3u);
  wire[20] ^= 0x01u;
  zs_mcumgr_decoder_init(&d); got = false;
  for (size_t i = 0u; i < n; i++) got |= zs_mcumgr_decoder_feed(&d, wire[i], &out, &out_len);
  assert(!got && d.bad_frames == 1u);
  /* noise before a frame and CR/LF line ends are tolerated */
  static const uint8_t noise[] = "boot> \r\n";
  zs_mcumgr_decoder_init(&d);
  for (size_t i = 0u; i < sizeof(noise) - 1u; i++) assert(!zs_mcumgr_decoder_feed(&d, noise[i], &out, &out_len));
  n = zs_mcumgr_frame_encode(pkt, sizeof(pkt), serial, sizeof(serial)); serial[n - 1u] = '\r'; serial[n++] = '\n';
  got = false; for (size_t i = 0u; i < n; i++) got |= zs_mcumgr_decoder_feed(&d, serial[i], &out, &out_len);
  assert(got && out_len == sizeof(pkt));
  printf("mcumgr framing ok\n");
}

static void run_upload(const uint8_t *image, size_t size, unsigned expect_min_requests) {
  zs_mcumgr_upload_t up; zs_mcumgr_upload_init(&up, image, size);
  zs_mcumgr_decoder_t host; zs_mcumgr_decoder_init(&host);
  uint8_t serial[1024];
  unsigned requests = 0u, timeouts = 0u;
  while (!up.done && !up.failed) {
    size_t n = zs_mcumgr_upload_request(&up, serial, sizeof(serial));
    assert(n > 0u); requests++;
    tgt_feed(serial, n);
    if (tgt.out_len == 0u) { assert(++timeouts < 10u); up.retries++; continue; }   /* host timeout: resend the same request */
    bool replied = false;
    for (size_t i = 0u; i < tgt.out_len; i++) { const uint8_t *pkt; size_t len; if (zs_mcumgr_decoder_feed(&host, tgt.out[i], &pkt, &len)) replied = zs_mcumgr_upload_response(&up, pkt, len); }
    if (!replied) up.retries++;       /* corrupted reply: the host times out and resends */
    tgt.out_len = 0u;
  }
  assert(up.done && !up.failed);
  assert(tgt.received == size && tgt.declared_len == size && !memcmp(tgt.slot, image, size) && !memcmp(tgt.sha, up.sha, 32u));
  assert(requests >= expect_min_requests);
  size_t n = zs_mcumgr_reset_request(up.seq, serial, sizeof(serial));
  assert(n > 0u); tgt_feed(serial, n);
  assert(tgt.resets == 1u);
}

static void test_upload(void) {
  static uint8_t image[65537];
  for (size_t i = 0u; i < sizeof(image); i++) image[i] = (uint8_t)(i * 7u + (i >> 8));
  memset(&tgt, 0, sizeof(tgt)); zs_mcumgr_decoder_init(&tgt.dec);
  run_upload(image, sizeof(image), (unsigned)((sizeof(image) + ZS_MCUMGR_UPLOAD_CHUNK - 1u) / ZS_MCUMGR_UPLOAD_CHUNK));
  printf("mcumgr upload ok: %u requests for %zu bytes, %u frames rejected by the target\n", tgt.uploads, sizeof(image), tgt.dec.bad_frames);
  /* a lost reply and a corrupted reply: the client resends and resumes from the target's offset */
  memset(&tgt, 0, sizeof(tgt)); zs_mcumgr_decoder_init(&tgt.dec);
  tgt.drop_next = 1u; tgt.corrupt_next = 1u;
  run_upload(image, 1000u, 3u);
  assert(tgt.uploads >= 4u);
  /* a tiny image is one request */
  memset(&tgt, 0, sizeof(tgt)); zs_mcumgr_decoder_init(&tgt.dec);
  run_upload(image, 100u, 1u);
  assert(tgt.uploads == 1u);
  printf("mcumgr upload with lost/corrupted replies ok\n");
}

int main(void) {
  test_framing();
  test_upload();
  printf("mcumgr serial tests passed\n");
  return 0;
}
