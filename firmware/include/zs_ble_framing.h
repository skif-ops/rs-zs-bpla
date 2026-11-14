#ifndef ZS_BLE_FRAMING_H
#define ZS_BLE_FRAMING_H
/*
 * Framing of GATT values longer than one ATT packet (ICD BLE addendum B.2).
 * Mirrors android core/ble/LongValueFraming.kt byte for byte:
 *   [seq:1][flags:1][total_len:2 BE — first frame only][data...]
 *   flags bit0 FIRST, bit1 LAST; seq wraps at 256; total_len <= 4096.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_BLE_FRAME_HEADER 2u
#define ZS_BLE_FRAME_FIRST_EXTRA 2u
#define ZS_BLE_FRAME_FLAG_FIRST 0x01u
#define ZS_BLE_FRAME_FLAG_LAST 0x02u
#define ZS_BLE_VALUE_MAX 4096u
#define ZS_BLE_ATT_PAYLOAD_MIN 20u /* MTU 23 - 3 */
#define ZS_BLE_ATT_PAYLOAD_MAX 244u /* MTU 247 - 3 */

/* Splitter: iterates frames of `value` for a given ATT payload size. */
typedef struct {
  const uint8_t *value;
  size_t len, pos;
  uint8_t seq;
  bool done;
} zs_ble_splitter_t;

bool zs_ble_splitter_init(zs_ble_splitter_t *s, const uint8_t *value, size_t len);
/* Writes the next frame into `frame` (cap >= att_payload). Returns frame length, 0 when done. */
size_t zs_ble_splitter_next(zs_ble_splitter_t *s, size_t att_payload, uint8_t *frame, size_t cap);

/* Reassembler: feed frames in order; complete when the LAST frame closes the announced length. */
typedef struct {
  uint8_t *buf;
  size_t cap, total, filled;
  uint8_t expected_seq;
  bool active, complete;
} zs_ble_reassembler_t;

void zs_ble_reassembler_init(zs_ble_reassembler_t *r, uint8_t *buf, size_t cap);
void zs_ble_reassembler_reset(zs_ble_reassembler_t *r);
/* Returns false (and resets) on any framing error: bad seq, missing FIRST, overflow, short LAST. */
bool zs_ble_reassembler_feed(zs_ble_reassembler_t *r, const uint8_t *frame, size_t len);

#endif
