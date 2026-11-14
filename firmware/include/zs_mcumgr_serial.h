#ifndef ZS_MCUMGR_SERIAL_H
#define ZS_MCUMGR_SERIAL_H
/*
 * mcumgr SMP client over the serial transport, as MCUboot serial recovery speaks it (ICD addendum C.6):
 * the STM32 uploads the nRF52840 bridge image into the module's secondary slot and resets it.
 *
 * Serial framing (Zephyr mcumgr "shell/serial" transport, MCUboot boot_serial):
 *   frame = [0x06 0x09] (first) or [0x04 0x14] (continuation) + base64 chunk + '\n', <= 127 bytes;
 *   the base64 stream carries [len BE16][SMP packet][crc16 BE], len = packet length + 2,
 *   crc16 = CRC-16/XMODEM (poly 0x1021, init 0) over the SMP packet. Each frame carries whole base64 quads
 *   of a 3-byte-aligned slice, so a frame decodes on its own and the packet is reassembled across frames.
 * SMP header (8 bytes): op, flags, len BE16, group BE16, seq, id. Groups/ids used here:
 *   OS (0): reset (5);  IMAGE (1): state (0), upload (1).
 * Image upload: write requests {"image":0,"len":size,"sha":sha256,"off":0,"data":...} then {"off","data"},
 * every reply {"rc":0,"off":next}; the client resumes from the offset the target reports, so a lost or
 * rejected chunk is simply resent. MCUboot marks the uploaded image pending; the reset boots it in test
 * mode and the bridge confirms itself once the STM32 talks to it (firmware/targets/nrf52840_ble).
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_MCUMGR_FRAME_MAX 127u
#define ZS_MCUMGR_PACKET_MAX 512u         /* MCUboot CONFIG_BOOT_SERIAL_MAX_RECEIVE_SIZE default */
#define ZS_MCUMGR_UPLOAD_CHUNK 384u       /* image bytes per upload request: fits the 512-byte packet with CBOR + header */

#define ZS_MCUMGR_OP_READ 0u
#define ZS_MCUMGR_OP_WRITE 2u
#define ZS_MCUMGR_GROUP_OS 0u
#define ZS_MCUMGR_GROUP_IMAGE 1u
#define ZS_MCUMGR_OS_ID_RESET 5u
#define ZS_MCUMGR_IMAGE_ID_STATE 0u
#define ZS_MCUMGR_IMAGE_ID_UPLOAD 1u

typedef struct {
  uint8_t op, flags, group_hi, group_lo, seq, id;
  uint16_t len;      /* CBOR payload length */
} zs_smp_header_t;

uint16_t zs_mcumgr_crc16(const uint8_t *data, size_t len);

/* Builds an SMP packet (header + CBOR payload) into out; returns the packet length or 0 when it does not fit. */
size_t zs_mcumgr_smp_build(uint8_t op, uint16_t group, uint8_t id, uint8_t seq, const uint8_t *cbor, size_t cbor_len, uint8_t *out, size_t cap);
bool zs_mcumgr_smp_parse(const uint8_t *pkt, size_t len, zs_smp_header_t *hdr, const uint8_t **cbor, size_t *cbor_len);

/* Serial framing of a whole SMP packet; returns the number of serial bytes written or 0 when it does not fit. */
size_t zs_mcumgr_frame_encode(const uint8_t *pkt, size_t len, uint8_t *out, size_t cap);

/* Byte-wise frame decoder: feed the UART stream; returns true once a whole packet is available in `packet`. */
typedef struct {
  uint8_t line[ZS_MCUMGR_FRAME_MAX + 1u];
  size_t line_len;
  uint8_t packet[ZS_MCUMGR_PACKET_MAX + 4u];
  size_t packet_len, expected;   /* expected = len field + 2 (the length word itself) */
  bool in_packet;
  uint32_t bad_frames, packets;
} zs_mcumgr_decoder_t;

void zs_mcumgr_decoder_init(zs_mcumgr_decoder_t *d);
bool zs_mcumgr_decoder_feed(zs_mcumgr_decoder_t *d, uint8_t byte, const uint8_t **packet, size_t *len);

/* Image upload client. The image is read through a callback (NOR slot, zs_nor_image_store) or from memory. */
typedef bool (*zs_mcumgr_image_read_fn)(void *ctx, size_t offset, uint8_t *dst, size_t len);

typedef struct {
  zs_mcumgr_image_read_fn read;
  void *read_ctx;
  const uint8_t *image;    /* in-memory source when read == NULL */
  size_t size, offset;
  uint8_t sha[32];
  uint8_t seq;
  uint8_t retries;         /* consecutive rejected/mismatched replies */
  bool done, failed;
  int last_rc;
  uint8_t chunk[ZS_MCUMGR_UPLOAD_CHUNK];
} zs_mcumgr_upload_t;

void zs_mcumgr_upload_init(zs_mcumgr_upload_t *u, const uint8_t *image, size_t size);
/* Reader-based source; sha256 must be the digest of the whole image (the NOR slot header carries it). */
void zs_mcumgr_upload_init_reader(zs_mcumgr_upload_t *u, zs_mcumgr_image_read_fn read, void *ctx, size_t size, const uint8_t sha256[32]);
/* Next upload request as serial frames (0 when done/failed or out of space). */
size_t zs_mcumgr_upload_request(zs_mcumgr_upload_t *u, uint8_t *serial, size_t cap);
/* Feeds a decoded reply packet; returns false when the reply is not an upload reply for the outstanding request. */
bool zs_mcumgr_upload_response(zs_mcumgr_upload_t *u, const uint8_t *pkt, size_t len);
/* Reset request (OS group) as serial frames. */
size_t zs_mcumgr_reset_request(uint8_t seq, uint8_t *serial, size_t cap);

#endif
