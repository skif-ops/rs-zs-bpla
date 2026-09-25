/* LoRa uplink frames: encode/decode round trip, authentication, the cross-vector shared with server/station/lora_codec.py,
   and the time-on-air table. */
#include "zs_lora_frame.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
  uint8_t ek[32], key[32], frame[ZS_LORA_EVENT_FRAME_BYTES], ack[ZS_LORA_ACK_FRAME_BYTES];
  zs_lora_event_t e = {1u, 17u, 5u, 42u, 1800000123u, 456u, 3u, 188u, 3u, 185u, 13200u, 80u, ZS_LORA_EVENT_FLAG_GSM_DEGRADED}, d;
  uint32_t s, b, q;
  for (unsigned i = 0u; i < 32u; i++) ek[i] = (uint8_t)(0xa0u + i);
  zs_lora_derive_key(ek, key);
  assert(zs_lora_encode_event(&e, key, frame));
  assert(frame[0] == 0x10u && frame[1] == 1u && frame[3] == 17u && frame[11] == 42u && frame[21] == 3u && frame[29] == 0x02u);
  assert(zs_lora_decode_event(frame, sizeof(frame), key, &d));
  assert(d.profile_id == e.profile_id && d.station_id == e.station_id && d.boot_id == e.boot_id && d.seq_no == e.seq_no && d.time_s == e.time_s && d.time_ms == e.time_ms &&
         d.class_id == e.class_id && d.confidence_u8 == e.confidence_u8 && d.presence_level == e.presence_level && d.f0_hz == e.f0_hz &&
         d.battery_mv == e.battery_mv && d.battery_pct == e.battery_pct && d.flags == e.flags);
  /* cross vector (server/tests/test_lora_codec.py encodes the same event with the same engineer key) */
  printf("vector event frame: ");
  for (unsigned i = 0u; i < sizeof(frame); i++) printf("%02x", frame[i]);
  printf("\n");
  /* tampering, wrong key, wrong length, wrong type */
  frame[22] ^= 1u; assert(!zs_lora_decode_event(frame, sizeof(frame), key, &d)); frame[22] ^= 1u;
  key[0] ^= 1u; assert(!zs_lora_decode_event(frame, sizeof(frame), key, &d)); key[0] ^= 1u;
  assert(!zs_lora_decode_event(frame, sizeof(frame) - 1u, key, &d));
  frame[0] = 0x11u; assert(!zs_lora_decode_event(frame, sizeof(frame), key, &d)); frame[0] = 0x10u;
  assert(zs_lora_decode_event(frame, sizeof(frame), key, &d));
  /* ack */
  assert(zs_lora_encode_ack(17u, 5u, 42u, key, ack));
  printf("vector ack frame: ");
  for (unsigned i = 0u; i < sizeof(ack); i++) printf("%02x", ack[i]);
  printf("\n");
  assert(zs_lora_decode_ack(ack, sizeof(ack), key, &s, &b, &q) && s == 17u && b == 5u && q == 42u);
  ack[5] ^= 1u; assert(!zs_lora_decode_ack(ack, sizeof(ack), key, &s, &b, &q)); ack[5] ^= 1u;
  assert(!zs_lora_decode_ack(frame, sizeof(frame), key, &s, &b, &q));          /* an event frame is not an ack */
  /* time on air: SF7..SF12 at 125 kHz for the 38-byte event, 21-byte ack; the 1 % duty cycle budget is 36 s/hour */
  {
    static const uint32_t expect_sf9[2] = {267u, 185u};                        /* +-5 ms of the Semtech AN1200.13 formula */
    const uint32_t ev = zs_lora_airtime_ms(38u, 9u, 125000u, 5u), ak = zs_lora_airtime_ms(21u, 9u, 125000u, 5u);
    printf("airtime SF9/125k: event %lu ms, ack %lu ms; SF7 %lu ms; SF12 %lu ms\n", (unsigned long)ev, (unsigned long)ak,
           (unsigned long)zs_lora_airtime_ms(38u, 7u, 125000u, 5u), (unsigned long)zs_lora_airtime_ms(38u, 12u, 125000u, 5u));
    assert(ev + 5u >= expect_sf9[0] && ev <= expect_sf9[0] + 5u && ak + 5u >= expect_sf9[1] && ak <= expect_sf9[1] + 5u);
    assert(zs_lora_airtime_ms(38u, 7u, 125000u, 5u) < ev && zs_lora_airtime_ms(38u, 12u, 125000u, 5u) > 1500u);
    assert(zs_lora_airtime_ms(38u, 4u, 125000u, 5u) == 0u && zs_lora_airtime_ms(38u, 9u, 125000u, 9u) == 0u);
  }
  printf("lora frame tests passed\n");
  return 0;
}
