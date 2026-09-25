#ifndef ZS_SX1262_H
#define ZS_SX1262_H
/*
 * SX1262 driver (Semtech DS.SX1261-2 rev 2.1): SPI command layer, RU868 frequency gate, LoRa modulation, and the
 * packet path used by the LoRa uplink (LORA_BACKUP_ICD_v0_1 addendum A): configure -> transmit -> receive window
 * -> IRQ poll -> read packet.  The RF switch (TXEN/RXEN) is driven through the port's GPIO ids; DIO1 is polled
 * through gpio_read (an EXTI can wake the polling task on the target).  Everything is host-testable through the
 * zs_hal_port_t SPI/GPIO callbacks.
 */
#include "zs_hal_port.h"
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define ZS_SX1262_PAYLOAD_MAX 255u
#define ZS_SX1262_IRQ_TX_DONE 0x0001u
#define ZS_SX1262_IRQ_RX_DONE 0x0002u
#define ZS_SX1262_IRQ_CRC_ERR 0x0040u
#define ZS_SX1262_IRQ_TIMEOUT 0x0200u
#define ZS_SX1262_SYNC_WORD_PRIVATE 0x1424u

typedef struct {
  zs_hal_port_t io;
  unsigned spi_bus, nss_gpio, busy_gpio, reset_gpio;
  unsigned dio1_gpio, txen_gpio, rxen_gpio;     /* 0 = not used */
  uint32_t frequency_hz;
  uint8_t sf, bw_code, cr_code;
  bool packet_ready;                            /* LoRa packet type + params programmed */
  uint32_t tx_count, rx_count, crc_errors;
} zs_sx1262_t;

extern const uint32_t zs_ru868_candidate_channels_hz[7];
bool zs_sx1262_frequency_allowed_ru868(uint32_t frequency_hz);
void zs_sx1262_init(zs_sx1262_t *r, const zs_hal_port_t *io, unsigned spi, unsigned nss, unsigned busy, unsigned reset);
/* Optional pins for the packet path: DIO1 (IRQ line) and the RF switch controls. */
void zs_sx1262_set_packet_pins(zs_sx1262_t *r, unsigned dio1, unsigned txen, unsigned rxen);
bool zs_sx1262_reset(zs_sx1262_t *r);
bool zs_sx1262_set_standby(zs_sx1262_t *r);
bool zs_sx1262_set_sleep(zs_sx1262_t *r);
bool zs_sx1262_set_frequency(zs_sx1262_t *r, uint32_t hz);
bool zs_sx1262_set_lora_modulation(zs_sx1262_t *r, uint8_t sf, uint32_t bandwidth_hz, uint8_t cr_denominator);
bool zs_sx1262_start_rx_duty_cycle(zs_sx1262_t *r, uint32_t rx_us, uint32_t sleep_us);

/* Packet path.  configure_lora: standby, DC-DC regulator, calibration, LoRa packet type, frequency (RU868 gate),
   modulation, PA for the SX1262 at `tx_dbm` (<= 14 dBm for RU868), sync word, buffer bases, DIO1 IRQ mask. */
bool zs_sx1262_configure_lora(zs_sx1262_t *r, uint32_t frequency_hz, uint8_t sf, uint32_t bandwidth_hz, uint8_t cr_denominator, int8_t tx_dbm, uint16_t sync_word);
/* Loads `data` and starts the transmission (explicit header, CRC on); TxDone/timeout arrive via IRQ. */
bool zs_sx1262_transmit(zs_sx1262_t *r, const uint8_t *data, size_t n, uint32_t timeout_ms);
/* Opens a receive window (timeout_ms == 0: continuous). */
bool zs_sx1262_receive(zs_sx1262_t *r, uint32_t timeout_ms);
/* True when DIO1 is high (or DIO1 unused: always true, so the caller falls back to polling the status). */
bool zs_sx1262_irq_pending(const zs_sx1262_t *r);
/* Reads and clears the IRQ status (bits ZS_SX1262_IRQ_*). */
bool zs_sx1262_read_irq(zs_sx1262_t *r, uint16_t *irq);
/* Copies the last received packet out of the radio buffer. */
bool zs_sx1262_read_packet(zs_sx1262_t *r, uint8_t *out, size_t cap, size_t *n);
/* Last packet's RSSI (dBm) and SNR (dB/4 units as the chip reports). */
bool zs_sx1262_packet_status(zs_sx1262_t *r, int16_t *rssi_dbm, int8_t *snr_q2);
#endif
