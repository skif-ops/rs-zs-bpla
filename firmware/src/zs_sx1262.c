#include "zs_sx1262.h"
#include <string.h>

/* RU868 allocation of the pilot (config/lora/RU868.yaml): the driver refuses any other carrier. */
const uint32_t zs_ru868_candidate_channels_hz[7] = {864100000u, 864300000u, 864500000u, 864700000u, 864900000u, 868900000u, 869100000u};
bool zs_sx1262_frequency_allowed_ru868(uint32_t hz) { for (size_t i = 0; i < 7u; i++) if (zs_ru868_candidate_channels_hz[i] == hz) return true; return false; }

static bool wait_busy(zs_sx1262_t *r) {
  if (!r->io.gpio_read) return true;
  for (unsigned i = 0; i < 1000; i++) { if (!r->io.gpio_read(r->io.ctx, r->busy_gpio)) return true; if (r->io.delay_ms) r->io.delay_ms(r->io.ctx, 1); }
  return false;
}

/* One SPI transaction: opcode + parameters out, `rx` (same length as tx) in. */
static bool xfer(zs_sx1262_t *r, const uint8_t *tx, uint8_t *rx, size_t n) {
  int z;
  if (!r || !r->io.spi_transfer || !wait_busy(r)) return false;
  if (r->io.gpio_write) r->io.gpio_write(r->io.ctx, r->nss_gpio, false);
  z = r->io.spi_transfer(r->io.ctx, r->spi_bus, tx, rx, n);
  if (r->io.gpio_write) r->io.gpio_write(r->io.ctx, r->nss_gpio, true);
  return z >= 0 && wait_busy(r);
}

static bool cmd(zs_sx1262_t *r, uint8_t op, const uint8_t *p, size_t n) {
  uint8_t tx[ZS_SX1262_PAYLOAD_MAX + 4u], rx[ZS_SX1262_PAYLOAD_MAX + 4u];
  if (n + 1u > sizeof(tx)) return false;
  tx[0] = op;
  if (n) memcpy(tx + 1, p, n);
  return xfer(r, tx, rx, n + 1u);
}

/* Command with a response: opcode, one status byte, then `n` bytes read. */
static bool query(zs_sx1262_t *r, uint8_t op, const uint8_t *p, size_t np, uint8_t *out, size_t n) {
  uint8_t tx[ZS_SX1262_PAYLOAD_MAX + 4u] = {0}, rx[ZS_SX1262_PAYLOAD_MAX + 4u];
  const size_t total = 1u + np + 1u + n;
  if (total > sizeof(tx)) return false;
  tx[0] = op;
  if (np) memcpy(tx + 1, p, np);
  if (!xfer(r, tx, rx, total)) return false;
  memcpy(out, rx + 1u + np + 1u, n);
  return true;
}

void zs_sx1262_init(zs_sx1262_t *r, const zs_hal_port_t *io, unsigned spi, unsigned nss, unsigned busy, unsigned reset) {
  if (!r) return;
  memset(r, 0, sizeof(*r));
  if (io) r->io = *io;
  r->spi_bus = spi; r->nss_gpio = nss; r->busy_gpio = busy; r->reset_gpio = reset;
  r->sf = 9; r->bw_code = 4; r->cr_code = 1;
}
void zs_sx1262_set_packet_pins(zs_sx1262_t *r, unsigned dio1, unsigned txen, unsigned rxen) { if (r) { r->dio1_gpio = dio1; r->txen_gpio = txen; r->rxen_gpio = rxen; } }

bool zs_sx1262_reset(zs_sx1262_t *r) {
  if (!r) return false;
  if (r->io.gpio_write) {
    r->io.gpio_write(r->io.ctx, r->reset_gpio, false);
    if (r->io.delay_ms) r->io.delay_ms(r->io.ctx, 2);
    r->io.gpio_write(r->io.ctx, r->reset_gpio, true);
    if (r->io.delay_ms) r->io.delay_ms(r->io.ctx, 10);
  }
  r->packet_ready = false;
  return wait_busy(r);
}
bool zs_sx1262_set_standby(zs_sx1262_t *r) { uint8_t x = 0; return cmd(r, 0x80, &x, 1); }
bool zs_sx1262_set_sleep(zs_sx1262_t *r) { uint8_t x = 0x04; return cmd(r, 0x84, &x, 1); }
bool zs_sx1262_set_frequency(zs_sx1262_t *r, uint32_t hz) {
  if (!zs_sx1262_frequency_allowed_ru868(hz)) return false;
  uint32_t reg = (uint32_t)(((uint64_t)hz << 25) / 32000000u);
  uint8_t x[4] = {(uint8_t)(reg >> 24), (uint8_t)(reg >> 16), (uint8_t)(reg >> 8), (uint8_t)reg};
  if (cmd(r, 0x86, x, 4)) { r->frequency_hz = hz; return true; }
  return false;
}
static uint8_t bw(uint32_t h) { if (h <= 7800) return 0; if (h <= 10400) return 8; if (h <= 15600) return 1; if (h <= 20800) return 9; if (h <= 31250) return 2; if (h <= 41700) return 10; if (h <= 62500) return 3; if (h <= 125000) return 4; if (h <= 250000) return 5; return 6; }
bool zs_sx1262_set_lora_modulation(zs_sx1262_t *r, uint8_t sf, uint32_t bandwidth, uint8_t crden) {
  if (sf < 5 || sf > 12) return false;
  uint8_t cr = (crden >= 5 && crden <= 8) ? (uint8_t)(crden - 4) : 1;
  uint8_t x[4] = {sf, bw(bandwidth), cr, (sf >= 11 && bandwidth == 125000) ? 1 : 0};
  if (cmd(r, 0x8B, x, 4)) { r->sf = sf; r->bw_code = x[1]; r->cr_code = cr; return true; }
  return false;
}
static uint32_t tick24(uint32_t us) { uint64_t v = (uint64_t)us * 64u / 1000u; if (v > 0xFFFFFFu) v = 0xFFFFFFu; return (uint32_t)v; }
bool zs_sx1262_start_rx_duty_cycle(zs_sx1262_t *r, uint32_t rx_us, uint32_t sleep_us) {
  uint32_t a = tick24(rx_us), b = tick24(sleep_us);
  uint8_t x[6] = {(uint8_t)(a >> 16), (uint8_t)(a >> 8), (uint8_t)a, (uint8_t)(b >> 16), (uint8_t)(b >> 8), (uint8_t)b};
  return cmd(r, 0x94, x, 6);
}

/* ---- packet path ---- */
static void rf_switch(zs_sx1262_t *r, bool tx, bool rx) {
  if (!r->io.gpio_write) return;
  if (r->txen_gpio) r->io.gpio_write(r->io.ctx, r->txen_gpio, tx);
  if (r->rxen_gpio) r->io.gpio_write(r->io.ctx, r->rxen_gpio, rx);
}
static bool write_register(zs_sx1262_t *r, uint16_t addr, const uint8_t *v, size_t n) {
  uint8_t p[2 + 8];
  if (n > 8u) return false;
  p[0] = (uint8_t)(addr >> 8); p[1] = (uint8_t)addr; memcpy(p + 2, v, n);
  return cmd(r, 0x0D, p, 2u + n);
}

bool zs_sx1262_configure_lora(zs_sx1262_t *r, uint32_t frequency_hz, uint8_t sf, uint32_t bandwidth_hz, uint8_t cr_denominator, int8_t tx_dbm, uint16_t sync_word) {
  uint8_t x[8];
  if (!r || tx_dbm > 22 || tx_dbm < -9) return false;
  r->packet_ready = false;
  if (!zs_sx1262_set_standby(r)) return false;                                   /* STDBY_RC */
  x[0] = 0x01; if (!cmd(r, 0x96, x, 1)) return false;                            /* SetRegulatorMode: DC-DC */
  x[0] = 0x7F; if (!cmd(r, 0x89, x, 1)) return false;                            /* Calibrate: all blocks */
  if (r->io.delay_ms) r->io.delay_ms(r->io.ctx, 5);
  x[0] = 0x01; if (!cmd(r, 0x8A, x, 1)) return false;                            /* SetPacketType: LoRa */
  if (!zs_sx1262_set_frequency(r, frequency_hz)) return false;                   /* RU868 gate inside */
  if (!zs_sx1262_set_lora_modulation(r, sf, bandwidth_hz, cr_denominator)) return false;
  /* SetPaConfig for the SX1262 (DS table 13-21): +14 dBm -> 0x02,0x02; +17 -> 0x02,0x03; +20 -> 0x03,0x05; +22 -> 0x04,0x07 */
  { uint8_t pa[4] = {0x02, 0x02, 0x00, 0x01};
    if (tx_dbm > 20) { pa[0] = 0x04; pa[1] = 0x07; } else if (tx_dbm > 17) { pa[0] = 0x03; pa[1] = 0x05; } else if (tx_dbm > 14) { pa[0] = 0x02; pa[1] = 0x03; }
    if (!cmd(r, 0x95, pa, 4)) return false; }
  x[0] = (uint8_t)tx_dbm; x[1] = 0x04; if (!cmd(r, 0x8E, x, 2)) return false;   /* SetTxParams: power, ramp 200 us */
  x[0] = (uint8_t)(sync_word >> 8); x[1] = (uint8_t)sync_word;
  if (!write_register(r, 0x0740, x, 2)) return false;                            /* LoRa sync word */
  x[0] = 0x00; x[1] = 0x00; if (!cmd(r, 0x8F, x, 2)) return false;               /* SetBufferBaseAddress tx 0, rx 0 */
  /* SetDioIrqParams: mask TxDone|RxDone|CrcErr|Timeout, all routed to DIO1 */
  { const uint16_t m = ZS_SX1262_IRQ_TX_DONE | ZS_SX1262_IRQ_RX_DONE | ZS_SX1262_IRQ_CRC_ERR | ZS_SX1262_IRQ_TIMEOUT;
    uint8_t irq[8] = {(uint8_t)(m >> 8), (uint8_t)m, (uint8_t)(m >> 8), (uint8_t)m, 0, 0, 0, 0};
    if (!cmd(r, 0x08, irq, 8)) return false; }
  rf_switch(r, false, false);
  r->packet_ready = true;
  return true;
}

static bool set_packet_params(zs_sx1262_t *r, uint8_t payload_len) {
  /* preamble 8, explicit header, length, CRC on, standard IQ */
  uint8_t p[6] = {0x00, 0x08, 0x00, payload_len, 0x01, 0x00};
  return cmd(r, 0x8C, p, 6);
}

bool zs_sx1262_transmit(zs_sx1262_t *r, const uint8_t *data, size_t n, uint32_t timeout_ms) {
  uint8_t buf[ZS_SX1262_PAYLOAD_MAX + 1u];
  uint32_t t;
  uint8_t x[3];
  if (!r || !r->packet_ready || !data || n == 0u || n > ZS_SX1262_PAYLOAD_MAX) return false;
  if (!set_packet_params(r, (uint8_t)n)) return false;
  buf[0] = 0x00; memcpy(buf + 1, data, n);                                       /* WriteBuffer offset 0 */
  if (!cmd(r, 0x0E, buf, n + 1u)) return false;
  x[0] = 0x02; x[1] = 0x03; if (!cmd(r, 0x02, x, 2)) return false;               /* ClearIrqStatus all */
  rf_switch(r, true, false);
  t = tick24(timeout_ms * 1000u);
  x[0] = (uint8_t)(t >> 16); x[1] = (uint8_t)(t >> 8); x[2] = (uint8_t)t;
  if (!cmd(r, 0x83, x, 3)) { rf_switch(r, false, false); return false; }          /* SetTx */
  r->tx_count++;
  return true;
}

bool zs_sx1262_receive(zs_sx1262_t *r, uint32_t timeout_ms) {
  uint8_t x[3];
  uint32_t t;
  if (!r || !r->packet_ready) return false;
  if (!set_packet_params(r, ZS_SX1262_PAYLOAD_MAX)) return false;
  x[0] = 0x02; x[1] = 0x03; if (!cmd(r, 0x02, x, 2)) return false;
  rf_switch(r, false, true);
  t = timeout_ms == 0u ? 0xFFFFFFu : tick24(timeout_ms * 1000u);                 /* 0xFFFFFF = continuous */
  x[0] = (uint8_t)(t >> 16); x[1] = (uint8_t)(t >> 8); x[2] = (uint8_t)t;
  if (!cmd(r, 0x82, x, 3)) { rf_switch(r, false, false); return false; }          /* SetRx */
  return true;
}

bool zs_sx1262_irq_pending(const zs_sx1262_t *r) {
  if (!r) return false;
  if (!r->dio1_gpio || !r->io.gpio_read) return true;
  return r->io.gpio_read(r->io.ctx, r->dio1_gpio);
}

bool zs_sx1262_read_irq(zs_sx1262_t *r, uint16_t *irq) {
  uint8_t st[2], x[2];
  if (!r || !irq || !query(r, 0x12, NULL, 0u, st, 2u)) return false;             /* GetIrqStatus */
  *irq = (uint16_t)(((uint16_t)st[0] << 8) | st[1]);
  if (*irq == 0u) return true;
  x[0] = st[0]; x[1] = st[1];
  if (!cmd(r, 0x02, x, 2)) return false;                                          /* ClearIrqStatus of what we saw */
  if (*irq & (ZS_SX1262_IRQ_TX_DONE | ZS_SX1262_IRQ_TIMEOUT)) rf_switch(r, false, false);
  if (*irq & ZS_SX1262_IRQ_RX_DONE) { r->rx_count++; rf_switch(r, false, false); }
  if (*irq & ZS_SX1262_IRQ_CRC_ERR) r->crc_errors++;
  return true;
}

bool zs_sx1262_read_packet(zs_sx1262_t *r, uint8_t *out, size_t cap, size_t *n) {
  uint8_t st[2], off[1];
  if (!r || !out || !n || !query(r, 0x13, NULL, 0u, st, 2u)) return false;       /* GetRxBufferStatus: len, start */
  if (st[0] == 0u || st[0] > cap) return false;
  off[0] = st[1];
  if (!query(r, 0x1E, off, 1u, out, st[0])) return false;                         /* ReadBuffer offset: status, then data */
  *n = st[0];
  return true;
}

bool zs_sx1262_packet_status(zs_sx1262_t *r, int16_t *rssi_dbm, int8_t *snr_q2) {
  uint8_t st[3];
  if (!r || !query(r, 0x14, NULL, 0u, st, 3u)) return false;                      /* GetPacketStatus: RssiPkt, SnrPkt, SignalRssiPkt */
  if (rssi_dbm) *rssi_dbm = (int16_t)(-(int16_t)st[0] / 2);
  if (snr_q2) *snr_q2 = (int8_t)st[1];
  return true;
}
