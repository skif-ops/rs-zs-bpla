#include "zs_bg95_provision.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  uint8_t tx[8192];
  size_t tx_len;
  int fail_after_calls;
  int calls;
} uart_stub_t;

static int uart_write(void *ctx, unsigned channel, const uint8_t *data, size_t len) {
  uart_stub_t *u = ctx;
  (void)channel;
  u->calls++;
  if (u->fail_after_calls > 0 && u->calls > u->fail_after_calls) return -1;
  if (u->tx_len + len > sizeof(u->tx)) return -1;
  memcpy(u->tx + u->tx_len, data, len);
  u->tx_len += len;
  return (int)len;
}

static uint32_t millis(void *ctx) { (void)ctx; return 0u; }

static zs_hal_port_t make_io(uart_stub_t *u) {
  zs_hal_port_t io;
  memset(&io, 0, sizeof(io));
  io.ctx = u;
  io.uart_write = uart_write;
  io.millis = millis;
  return io;
}

static bool tx_ends_with(const uart_stub_t *u, const char *s) {
  size_t n = strlen(s);
  return u->tx_len >= n && memcmp(u->tx + u->tx_len - n, s, n) == 0;
}

static bool tx_contains_bytes(const uart_stub_t *u, const uint8_t *d, size_t n) {
  for (size_t i = 0u; i + n <= u->tx_len; i++) if (memcmp(u->tx + i, d, n) == 0) return true;
  return false;
}

static const uint8_t CA[] = "-----BEGIN CERTIFICATE-----\nMIIBxx\n-----END CERTIFICATE-----\n";
static const uint8_t CERT[] = "-----BEGIN CERTIFICATE-----\nMIICyy\n-----END CERTIFICATE-----\n";
static const uint8_t KEY[] = "-----BEGIN PRIVATE KEY-----\nMIGHAg\n-----END PRIVATE KEY-----\n";

static void add_three(zs_bg95_provision_t *p) {
  assert(zs_bg95_provision_add_file(p, "dioneya-root", CA, sizeof(CA) - 1u, ZS_BG95_PROVISION_ROLE_CA));
  assert(zs_bg95_provision_add_file(p, "station.crt", CERT, sizeof(CERT) - 1u, ZS_BG95_PROVISION_ROLE_CLIENT_CERT));
  assert(zs_bg95_provision_add_file(p, "station.key", KEY, sizeof(KEY) - 1u, ZS_BG95_PROVISION_ROLE_CLIENT_KEY));
}

/* Plays the modem side for one file upload and returns after +QFLST OK. */
static void modem_upload_ok(zs_bg95_provision_t *p, uart_stub_t *u, const char *name, const uint8_t *data, size_t size,
                            uint32_t *t) {
  char line[96];
  assert(p->state == ZS_BG95_PROVISION_DELETE);
  snprintf(line, sizeof(line), "AT+QFDEL=\"%s\"\r\n", name);
  assert(tx_ends_with(u, line));
  zs_bg95_provision_on_line(p, "+CME ERROR: 405", *t); /* file did not exist */
  assert(p->state == ZS_BG95_PROVISION_UPLOAD_CMD);
  snprintf(line, sizeof(line), "AT+QFUPL=\"%s\",%u,60\r\n", name, (unsigned)size);
  assert(tx_ends_with(u, line));
  zs_bg95_provision_on_line(p, "CONNECT", *t);
  assert(p->state == ZS_BG95_PROVISION_UPLOAD_DATA);
  zs_bg95_provision_tick(p, *t);
  assert(p->state == ZS_BG95_PROVISION_UPLOAD_RESULT);
  assert(tx_contains_bytes(u, data, size));
  snprintf(line, sizeof(line), "+QFUPL: %u,%u", (unsigned)size, (unsigned)zs_bg95_provision_checksum16(data, size));
  zs_bg95_provision_on_line(p, line, *t);
  zs_bg95_provision_on_line(p, "OK", *t);
  assert(p->state == ZS_BG95_PROVISION_LIST);
  snprintf(line, sizeof(line), "AT+QFLST=\"%s\"\r\n", name);
  assert(tx_ends_with(u, line));
  snprintf(line, sizeof(line), "+QFLST: \"%s\",%u", name, (unsigned)size);
  zs_bg95_provision_on_line(p, line, *t);
  zs_bg95_provision_on_line(p, "OK", *t);
  *t += 10u;
}

static void test_checksum(void) {
  const uint8_t a[] = {0x12, 0x34, 0x56, 0x78};
  const uint8_t b[] = {0x12, 0x34, 0x56};
  assert(zs_bg95_provision_checksum16(a, 4u) == (0x1234u ^ 0x5678u));
  assert(zs_bg95_provision_checksum16(b, 3u) == (0x1234u ^ 0x5600u));
  assert(zs_bg95_provision_checksum16(a, 0u) == 0u);
}

static void test_full_sequence(void) {
  uart_stub_t u = {0};
  zs_hal_port_t io = make_io(&u);
  zs_bg95_provision_t p;
  uint32_t t = 1000u;
  zs_bg95_provision_init(&p, &io, 1u, 1u);
  add_three(&p);
  assert(zs_bg95_provision_start(&p, t));
  modem_upload_ok(&p, &u, "dioneya-root", CA, sizeof(CA) - 1u, &t);
  modem_upload_ok(&p, &u, "station.crt", CERT, sizeof(CERT) - 1u, &t);
  modem_upload_ok(&p, &u, "station.key", KEY, sizeof(KEY) - 1u, &t);
  assert(p.state == ZS_BG95_PROVISION_BIND_CERT);
  assert(tx_ends_with(&u, "AT+QSSLCFG=\"clientcert\",1,\"station.crt\"\r\n"));
  zs_bg95_provision_on_line(&p, "OK", t);
  assert(p.state == ZS_BG95_PROVISION_BIND_KEY);
  assert(tx_ends_with(&u, "AT+QSSLCFG=\"clientkey\",1,\"station.key\"\r\n"));
  zs_bg95_provision_on_line(&p, "OK", t);
  assert(zs_bg95_provision_done(&p) && !zs_bg95_provision_failed(&p));
  /* nothing else is sent after completion */
  {
    size_t before = u.tx_len;
    zs_bg95_provision_tick(&p, t + 100000u);
    zs_bg95_provision_on_line(&p, "OK", t);
    assert(u.tx_len == before && zs_bg95_provision_done(&p));
  }
}

static void test_failures(void) {
  uart_stub_t u;
  zs_hal_port_t io;
  zs_bg95_provision_t p;
  uint32_t t = 0u;

  /* incomplete file set */
  memset(&u, 0, sizeof(u)); io = make_io(&u);
  zs_bg95_provision_init(&p, &io, 1u, 1u);
  assert(zs_bg95_provision_add_file(&p, "dioneya-root", CA, sizeof(CA) - 1u, ZS_BG95_PROVISION_ROLE_CA));
  assert(!zs_bg95_provision_start(&p, t) && zs_bg95_provision_failed(&p) && p.error == ZS_BG95_PROVISION_ERR_INVALID_ARGUMENT);

  /* duplicate role / bad name / oversize */
  zs_bg95_provision_init(&p, &io, 1u, 1u);
  assert(zs_bg95_provision_add_file(&p, "dioneya-root", CA, sizeof(CA) - 1u, ZS_BG95_PROVISION_ROLE_CA));
  assert(!zs_bg95_provision_add_file(&p, "other", CA, sizeof(CA) - 1u, ZS_BG95_PROVISION_ROLE_CA));
  assert(!zs_bg95_provision_add_file(&p, "bad name", CERT, sizeof(CERT) - 1u, ZS_BG95_PROVISION_ROLE_CLIENT_CERT));
  assert(!zs_bg95_provision_add_file(&p, "cert", CERT, 70000u, ZS_BG95_PROVISION_ROLE_CLIENT_CERT));

  /* modem refuses upload */
  memset(&u, 0, sizeof(u)); io = make_io(&u);
  zs_bg95_provision_init(&p, &io, 1u, 1u); add_three(&p);
  assert(zs_bg95_provision_start(&p, t));
  zs_bg95_provision_on_line(&p, "OK", t);
  zs_bg95_provision_on_line(&p, "+CME ERROR: 403", t);
  assert(zs_bg95_provision_failed(&p) && p.error == ZS_BG95_PROVISION_ERR_MODEM_ERROR);

  /* checksum mismatch */
  memset(&u, 0, sizeof(u)); io = make_io(&u);
  zs_bg95_provision_init(&p, &io, 1u, 1u); add_three(&p);
  assert(zs_bg95_provision_start(&p, t));
  zs_bg95_provision_on_line(&p, "OK", t);
  zs_bg95_provision_on_line(&p, "CONNECT", t);
  zs_bg95_provision_tick(&p, t);
  {
    char line[64];
    snprintf(line, sizeof(line), "+QFUPL: %u,%u", (unsigned)(sizeof(CA) - 1u),
             (unsigned)(zs_bg95_provision_checksum16(CA, sizeof(CA) - 1u) ^ 1u));
    zs_bg95_provision_on_line(&p, line, t);
  }
  assert(zs_bg95_provision_failed(&p) && p.error == ZS_BG95_PROVISION_ERR_CHECKSUM_MISMATCH);

  /* size mismatch */
  memset(&u, 0, sizeof(u)); io = make_io(&u);
  zs_bg95_provision_init(&p, &io, 1u, 1u); add_three(&p);
  assert(zs_bg95_provision_start(&p, t));
  zs_bg95_provision_on_line(&p, "OK", t);
  zs_bg95_provision_on_line(&p, "CONNECT", t);
  zs_bg95_provision_tick(&p, t);
  zs_bg95_provision_on_line(&p, "+QFUPL: 10,0", t);
  assert(zs_bg95_provision_failed(&p) && p.error == ZS_BG95_PROVISION_ERR_SIZE_MISMATCH);

  /* OK without +QFUPL result line */
  memset(&u, 0, sizeof(u)); io = make_io(&u);
  zs_bg95_provision_init(&p, &io, 1u, 1u); add_three(&p);
  assert(zs_bg95_provision_start(&p, t));
  zs_bg95_provision_on_line(&p, "OK", t);
  zs_bg95_provision_on_line(&p, "CONNECT", t);
  zs_bg95_provision_tick(&p, t);
  zs_bg95_provision_on_line(&p, "OK", t);
  assert(zs_bg95_provision_failed(&p) && p.error == ZS_BG95_PROVISION_ERR_MODEM_ERROR);

  /* list reports another size */
  memset(&u, 0, sizeof(u)); io = make_io(&u);
  zs_bg95_provision_init(&p, &io, 1u, 1u); add_three(&p);
  assert(zs_bg95_provision_start(&p, t));
  zs_bg95_provision_on_line(&p, "OK", t);
  zs_bg95_provision_on_line(&p, "CONNECT", t);
  zs_bg95_provision_tick(&p, t);
  {
    char line[64];
    snprintf(line, sizeof(line), "+QFUPL: %u,%u", (unsigned)(sizeof(CA) - 1u),
             (unsigned)zs_bg95_provision_checksum16(CA, sizeof(CA) - 1u));
    zs_bg95_provision_on_line(&p, line, t);
  }
  zs_bg95_provision_on_line(&p, "OK", t);
  zs_bg95_provision_on_line(&p, "+QFLST: \"dioneya-root\",12", t);
  assert(zs_bg95_provision_failed(&p) && p.error == ZS_BG95_PROVISION_ERR_LIST_MISMATCH);

  /* timeout waiting for CONNECT */
  memset(&u, 0, sizeof(u)); io = make_io(&u);
  zs_bg95_provision_init(&p, &io, 1u, 1u); add_three(&p);
  assert(zs_bg95_provision_start(&p, t));
  zs_bg95_provision_on_line(&p, "OK", t);
  zs_bg95_provision_tick(&p, t + ZS_BG95_PROVISION_STEP_TIMEOUT_MS - 1u);
  assert(!zs_bg95_provision_failed(&p));
  zs_bg95_provision_tick(&p, t + ZS_BG95_PROVISION_STEP_TIMEOUT_MS + 1u);
  assert(zs_bg95_provision_failed(&p) && p.error == ZS_BG95_PROVISION_ERR_TIMEOUT);

  /* UART write failure during raw data */
  memset(&u, 0, sizeof(u)); io = make_io(&u);
  zs_bg95_provision_init(&p, &io, 1u, 1u); add_three(&p);
  assert(zs_bg95_provision_start(&p, t));
  zs_bg95_provision_on_line(&p, "OK", t);
  zs_bg95_provision_on_line(&p, "CONNECT", t);
  u.fail_after_calls = u.calls;
  zs_bg95_provision_tick(&p, t);
  assert(zs_bg95_provision_failed(&p) && p.error == ZS_BG95_PROVISION_ERR_UART);
}

static void test_apply_station_config(void) {
  uart_stub_t u = {0};
  zs_hal_port_t io = make_io(&u);
  zs_bg95_t modem;
  zs_station_config_t cfg;
  char tenant[ZS_STATION_CONFIG_TENANT_MAX + 1u];
  zs_bg95_init(&modem, &io, 1u, 2u, "internet");
  zs_station_config_defaults(&cfg, 12u, ZS_STATION_CONFIG_REGION_RU868);
  /* invalid record (no host, version 0) is refused before touching the modem */
  assert(!zs_bg95_provision_apply_station_config(&modem, &cfg, 7u, true, tenant, sizeof(tenant)));
  cfg.version = 1u;
  strcpy(cfg.server_host, "muhoed.example.ru");
  strcpy(cfg.ca_reference, "dioneya-root");
  strcpy(cfg.tenant, "pilot1");
  strcpy(cfg.topic_prefix, "zs/v1");
  strcpy(cfg.apn[0], "internet");
  assert(zs_station_config_compute_hash(&cfg, cfg.config_hash));
  assert(zs_bg95_provision_apply_station_config(&modem, &cfg, 7u, true, tenant, sizeof(tenant)));
  assert(modem.transport_configured);
  assert(strcmp(modem.mqtt_host, "muhoed.example.ru") == 0 && modem.mqtt_port == 8883u);
  assert(strcmp(modem.ca_cert_path, "dioneya-root") == 0);
  assert(strcmp(modem.mqtt_client_id, "dioneya-12-7") == 0);
  assert(strcmp(tenant, "pilot1") == 0);
  /* stale hash (record edited without rehash) is refused */
  cfg.mqtt_port = 8884u;
  assert(!zs_bg95_provision_apply_station_config(&modem, &cfg, 7u, true, tenant, sizeof(tenant)));
  /* non-TLS port is refused by the modem driver contract */
  cfg.mqtt_port = 1883u;
  assert(zs_station_config_compute_hash(&cfg, cfg.config_hash));
  assert(!zs_bg95_provision_apply_station_config(&modem, &cfg, 7u, true, tenant, sizeof(tenant)));
  /* private APN policy is enforced by the driver */
  cfg.mqtt_port = 8883u;
  assert(zs_station_config_compute_hash(&cfg, cfg.config_hash));
  assert(!zs_bg95_provision_apply_station_config(&modem, &cfg, 7u, false, tenant, sizeof(tenant)));
}

int main(void) {
  test_checksum();
  test_full_sequence();
  test_failures();
  test_apply_station_config();
  printf("bg95_provision tests passed\n");
  return 0;
}
