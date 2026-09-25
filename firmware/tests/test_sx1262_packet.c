/* SX1262 packet path on a mock SPI: command sequences of configure/transmit/receive per the datasheet, RF switch
   lines, IRQ read/clear, and the packet read-back; plus the RU868 carrier gate. */
#include "zs_sx1262.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define PIN_NSS 1u
#define PIN_BUSY 2u
#define PIN_RESET 3u
#define PIN_DIO1 4u
#define PIN_TXEN 5u
#define PIN_RXEN 6u

static uint8_t ops[64]; static unsigned nops;              /* opcodes in order */
static uint8_t last_tx[300]; static size_t last_tx_n;
static uint8_t payload_written[300]; static size_t payload_written_n;
static bool gpio[16]; static bool dio1_level; static uint16_t irq_to_report; static uint8_t rx_packet[64]; static size_t rx_packet_n;

static int spi(void *c, unsigned bus, const uint8_t *tx, uint8_t *rx, size_t n) {
  (void)c; (void)bus;
  assert(!gpio[PIN_NSS]);                                    /* NSS low during the transaction */
  if (nops < 64u) ops[nops++] = tx[0];
  memcpy(last_tx, tx, n); last_tx_n = n;
  memset(rx, 0, n);
  switch (tx[0]) {
    case 0x0E: memcpy(payload_written, tx + 2, n - 2u); payload_written_n = n - 2u; break;       /* WriteBuffer offset, data */
    case 0x12: rx[2] = (uint8_t)(irq_to_report >> 8); rx[3] = (uint8_t)irq_to_report; break;   /* GetIrqStatus: status, irq16 */
    case 0x13: rx[2] = (uint8_t)rx_packet_n; rx[3] = 0x00; break;                              /* GetRxBufferStatus: len, start */
    case 0x1E: memcpy(rx + 3, rx_packet, rx_packet_n); break;                                  /* ReadBuffer: offset, status, data */
    case 0x14: rx[2] = 140u; rx[3] = 24u; rx[4] = 138u; break;                                  /* -70 dBm, +6 dB */
    default: break;
  }
  return 0;
}
static void gpio_write(void *c, unsigned id, bool level) { (void)c; if (id < 16u) gpio[id] = level; }
static bool gpio_read(void *c, unsigned id) { (void)c; if (id == PIN_BUSY) return false; if (id == PIN_DIO1) return dio1_level; return gpio[id]; }
static void delay(void *c, uint32_t ms) { (void)c; (void)ms; }

int main(void) {
  static zs_sx1262_t r;
  zs_hal_port_t io = {0};
  const uint8_t frame[38] = {0x10, 0x01, 0x00, 17u};
  uint8_t out[64]; size_t n; uint16_t irq; int16_t rssi; int8_t snr;
  io.spi_transfer = spi; io.gpio_write = gpio_write; io.gpio_read = gpio_read; io.delay_ms = delay;
  gpio[PIN_NSS] = true;
  zs_sx1262_init(&r, &io, 1u, PIN_NSS, PIN_BUSY, PIN_RESET);
  zs_sx1262_set_packet_pins(&r, PIN_DIO1, PIN_TXEN, PIN_RXEN);
  assert(zs_sx1262_reset(&r) && gpio[PIN_RESET]);

  /* configure: the RU868 gate refuses 868.1 MHz, accepts 868.9; the command sequence follows the datasheet */
  assert(!zs_sx1262_configure_lora(&r, 868100000u, 9u, 125000u, 5u, 14, ZS_SX1262_SYNC_WORD_PRIVATE) && !r.packet_ready);
  nops = 0u;
  assert(zs_sx1262_configure_lora(&r, 868900000u, 9u, 125000u, 5u, 14, ZS_SX1262_SYNC_WORD_PRIVATE) && r.packet_ready);
  {
    static const uint8_t expect[] = {0x80, 0x96, 0x89, 0x8A, 0x86, 0x8B, 0x95, 0x8E, 0x0D, 0x8F, 0x08};
    assert(nops == sizeof(expect) && memcmp(ops, expect, sizeof(expect)) == 0);
    assert(r.frequency_hz == 868900000u && r.sf == 9u && r.bw_code == 4u && r.cr_code == 1u);
    assert(!gpio[PIN_TXEN] && !gpio[PIN_RXEN] && gpio[PIN_NSS]);
  }
  assert(!zs_sx1262_configure_lora(&r, 868900000u, 9u, 125000u, 5u, 23, ZS_SX1262_SYNC_WORD_PRIVATE));   /* > +22 dBm */

  /* transmit: packet params, WriteBuffer with the frame, clear IRQ, TXEN, SetTx */
  assert(zs_sx1262_configure_lora(&r, 868900000u, 9u, 125000u, 5u, 14, ZS_SX1262_SYNC_WORD_PRIVATE));
  nops = 0u;
  assert(zs_sx1262_transmit(&r, frame, sizeof(frame), 5000u));
  { static const uint8_t expect[] = {0x8C, 0x0E, 0x02, 0x83}; assert(nops == 4u && memcmp(ops, expect, 4u) == 0); }
  assert(payload_written_n == 38u && memcmp(payload_written, frame, 38u) == 0 && gpio[PIN_TXEN] && !gpio[PIN_RXEN] && r.tx_count == 1u);
  /* SetTx timeout: 5000 ms * 64 = 320000 ticks = 0x04E200 */
  assert(last_tx[1] == 0x04u && last_tx[2] == 0xE2u && last_tx[3] == 0x00u);
  /* TxDone via DIO1: read + clear, RF switch idle */
  dio1_level = true; irq_to_report = ZS_SX1262_IRQ_TX_DONE;
  assert(zs_sx1262_irq_pending(&r));
  nops = 0u;
  assert(zs_sx1262_read_irq(&r, &irq) && irq == ZS_SX1262_IRQ_TX_DONE && ops[0] == 0x12 && ops[1] == 0x02 && !gpio[PIN_TXEN]);
  dio1_level = false; irq_to_report = 0u;
  assert(zs_sx1262_read_irq(&r, &irq) && irq == 0u);
  assert(!zs_sx1262_irq_pending(&r));

  /* receive window 3 s: RXEN, SetRx; RxDone -> read the ACK back */
  nops = 0u;
  assert(zs_sx1262_receive(&r, 3000u) && gpio[PIN_RXEN] && !gpio[PIN_TXEN]);
  { static const uint8_t expect[] = {0x8C, 0x02, 0x82}; assert(nops == 3u && memcmp(ops, expect, 3u) == 0); }
  memset(rx_packet, 0x90, 21u); rx_packet_n = 21u;
  dio1_level = true; irq_to_report = ZS_SX1262_IRQ_RX_DONE;
  assert(zs_sx1262_read_irq(&r, &irq) && (irq & ZS_SX1262_IRQ_RX_DONE) && !gpio[PIN_RXEN] && r.rx_count == 1u);
  assert(zs_sx1262_read_packet(&r, out, sizeof(out), &n) && n == 21u && out[0] == 0x90u && out[20] == 0x90u);
  assert(zs_sx1262_packet_status(&r, &rssi, &snr) && rssi == -70 && snr == 24);
  assert(!zs_sx1262_read_packet(&r, out, 10u, &n));                              /* too small for 21 bytes */
  /* CRC error is counted; timeout drops the RF switch */
  irq_to_report = ZS_SX1262_IRQ_CRC_ERR; assert(zs_sx1262_read_irq(&r, &irq) && r.crc_errors == 1u);
  assert(zs_sx1262_receive(&r, 0u) && gpio[PIN_RXEN] && last_tx[1] == 0xFFu && last_tx[2] == 0xFFu && last_tx[3] == 0xFFu);   /* continuous */
  irq_to_report = ZS_SX1262_IRQ_TIMEOUT; assert(zs_sx1262_read_irq(&r, &irq) && !gpio[PIN_RXEN]);
  /* a payload that does not fit, or before configure */
  { uint8_t big[256]; assert(!zs_sx1262_transmit(&r, big, sizeof(big), 100u)); }
  assert(zs_sx1262_reset(&r) && !r.packet_ready && !zs_sx1262_transmit(&r, frame, sizeof(frame), 100u));
  printf("sx1262 packet tests passed\n");
  return 0;
}
