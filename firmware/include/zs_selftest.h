#ifndef ZS_SELFTEST_H
#define ZS_SELFTEST_H

/*
 * Registry of interface self-tests run at boot and on demand from the
 * service mode (BLE `self_test`).  Each test is a function returning a
 * result code and a detail value (measured number: voltage in mV, RSSI, lag
 * in samples, ...).  Results are kept for the diagnostics characteristic and
 * encoded as a compact CBOR map {test_id: [code, detail_u32]} with zs_cbor.
 *
 * Portable/host only: the target registers HAL-backed test functions.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum {
  ZS_ST_NOT_RUN = 0,
  ZS_ST_PASS,
  ZS_ST_FAIL,
  ZS_ST_SKIPPED,   /* peripheral not powered in the current mode */
  ZS_ST_TIMEOUT
} zs_selftest_code_t;

typedef enum {
  ZS_ST_ID_POWER_INA226 = 1,  /* detail: VBAT mV */
  ZS_ST_ID_NOR_SFDP = 2,      /* detail: capacity Mbit */
  ZS_ST_ID_SD_CARD = 3,       /* detail: capacity MB */
  ZS_ST_ID_MIC_CAPTURE = 4,   /* detail: min channel peak */
  ZS_ST_ID_MIC_ALIGNMENT = 5, /* detail: max |lag| samples */
  ZS_ST_ID_GNSS_UART = 6,     /* detail: satellites */
  ZS_ST_ID_GNSS_PPS = 7,      /* detail: bound PPS count */
  ZS_ST_ID_LORA_SPI = 8,      /* detail: SX1262 status byte */
  ZS_ST_ID_MODEM_AT = 9,      /* detail: CSQ */
  ZS_ST_ID_MODEM_TLS = 10,    /* detail: TLS handshake ms */
  ZS_ST_ID_BLE_LINK = 11,     /* detail: nRF firmware version */
  ZS_ST_ID_RTC_LSE = 12,      /* detail: LSE frequency error ppm (abs) */
  ZS_ST_ID_STATION_CONFIG = 13, /* detail: config version */
  ZS_ST_ID_COUNT = 14
} zs_selftest_id_t;

typedef zs_selftest_code_t (*zs_selftest_fn_t)(void *ctx, uint32_t *detail_out);

typedef struct {
  uint8_t id;
  const char *name;
  zs_selftest_fn_t fn;
  void *ctx;
  bool required;   /* a FAIL here blocks BOOT_DONE */
} zs_selftest_entry_t;

#define ZS_SELFTEST_MAX 16u

typedef struct {
  zs_selftest_entry_t entries[ZS_SELFTEST_MAX];
  uint8_t count;
  zs_selftest_code_t result[ZS_ST_ID_COUNT];
  uint32_t detail[ZS_ST_ID_COUNT];
  uint32_t last_run_ms;
} zs_selftest_registry_t;

void zs_selftest_init(zs_selftest_registry_t *r);
bool zs_selftest_register(zs_selftest_registry_t *r, uint8_t id, const char *name, zs_selftest_fn_t fn, void *ctx, bool required);

/* Runs every registered test; returns true when all required tests passed (SKIPPED counts as not failed). */
bool zs_selftest_run_all(zs_selftest_registry_t *r, uint32_t now_ms);

/* Runs one test by id; returns its code (ZS_ST_NOT_RUN if unknown). */
zs_selftest_code_t zs_selftest_run_one(zs_selftest_registry_t *r, uint8_t id, uint32_t now_ms);

bool zs_selftest_required_ok(const zs_selftest_registry_t *r);

/* CBOR map {id: [code, detail]} over registered tests, keys ascending; returns bytes or 0 if cap too small. */
size_t zs_selftest_encode(const zs_selftest_registry_t *r, uint8_t *buf, size_t cap);

const char *zs_selftest_code_name(zs_selftest_code_t code);

#endif
