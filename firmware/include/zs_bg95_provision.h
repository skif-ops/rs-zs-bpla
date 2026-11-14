#ifndef ZS_BG95_PROVISION_H
#define ZS_BG95_PROVISION_H

/*
 * Service-mode provisioning of the BG95 TLS material and binding of the
 * persistent station configuration (zs_station_config) to the modem driver.
 *
 * Upload sequence per file (Quectel FILE AT commands):
 *   AT+QFDEL="<name>"              -> OK, or +CME ERROR (file absent, accepted)
 *   AT+QFUPL="<name>",<size>,<t>   -> CONNECT, then raw bytes on the UART,
 *                                     then +QFUPL: <size>,<checksum> and OK
 *   AT+QFLST="<name>"              -> +QFLST: "<name>",<size> and OK
 * After all files:
 *   AT+QSSLCFG="clientcert",<ctx>,"<cert>"   AT+QSSLCFG="clientkey",<ctx>,"<key>"
 *
 * The checksum is the 16-bit XOR over the uploaded data (big-endian words, a
 * trailing odd byte padded with 0x00) as documented for +QFUPL; exact modem
 * behaviour is a target validation item.
 *
 * Portable/host only: bytes go out through zs_hal_port_t.uart_write, responses
 * come in line by line through zs_bg95_provision_on_line.  The caller owns the
 * UART for the whole session (nothing else may talk to the modem meanwhile).
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_bg95.h"
#include "zs_hal_port.h"
#include "zs_station_config.h"

#define ZS_BG95_PROVISION_MAX_FILES 3u
#define ZS_BG95_PROVISION_NAME_MAX 31u
#define ZS_BG95_PROVISION_UPLOAD_TIMEOUT_S 60u
#define ZS_BG95_PROVISION_STEP_TIMEOUT_MS 5000u
#define ZS_BG95_PROVISION_UPLOAD_TIMEOUT_MS 65000u
#define ZS_BG95_PROVISION_CHUNK_BYTES 256u

typedef enum {
  ZS_BG95_PROVISION_IDLE = 0,
  ZS_BG95_PROVISION_DELETE,
  ZS_BG95_PROVISION_UPLOAD_CMD,
  ZS_BG95_PROVISION_UPLOAD_DATA,
  ZS_BG95_PROVISION_UPLOAD_RESULT,
  ZS_BG95_PROVISION_LIST,
  ZS_BG95_PROVISION_BIND_CERT,
  ZS_BG95_PROVISION_BIND_KEY,
  ZS_BG95_PROVISION_DONE,
  ZS_BG95_PROVISION_FAILED
} zs_bg95_provision_state_t;

typedef enum {
  ZS_BG95_PROVISION_ERR_NONE = 0,
  ZS_BG95_PROVISION_ERR_TIMEOUT,
  ZS_BG95_PROVISION_ERR_MODEM_ERROR,
  ZS_BG95_PROVISION_ERR_UART,
  ZS_BG95_PROVISION_ERR_SIZE_MISMATCH,
  ZS_BG95_PROVISION_ERR_CHECKSUM_MISMATCH,
  ZS_BG95_PROVISION_ERR_LIST_MISMATCH,
  ZS_BG95_PROVISION_ERR_INVALID_ARGUMENT
} zs_bg95_provision_error_t;

typedef enum {
  ZS_BG95_PROVISION_ROLE_CA = 0,     /* CA chain, name = station config ca_reference */
  ZS_BG95_PROVISION_ROLE_CLIENT_CERT,
  ZS_BG95_PROVISION_ROLE_CLIENT_KEY
} zs_bg95_provision_role_t;

typedef struct {
  char name[ZS_BG95_PROVISION_NAME_MAX + 1u];
  const uint8_t *data;
  size_t size;
  zs_bg95_provision_role_t role;
} zs_bg95_provision_file_t;

typedef struct {
  zs_hal_port_t io;
  unsigned uart_channel;
  uint8_t ssl_context;
  zs_bg95_provision_file_t files[ZS_BG95_PROVISION_MAX_FILES];
  uint8_t file_count;
  uint8_t file_index;
  zs_bg95_provision_state_t state;
  zs_bg95_provision_error_t error;
  uint32_t deadline_ms;
  size_t sent;
  bool result_seen;
  const char *client_cert_name;
  const char *client_key_name;
} zs_bg95_provision_t;

uint16_t zs_bg95_provision_checksum16(const uint8_t *data, size_t size);

void zs_bg95_provision_init(zs_bg95_provision_t *p, const zs_hal_port_t *io, unsigned uart_channel,
                            uint8_t ssl_context);

/* Names are the UFS file names; the CA file name must equal cfg->ca_reference. */
bool zs_bg95_provision_add_file(zs_bg95_provision_t *p, const char *name, const uint8_t *data, size_t size,
                                zs_bg95_provision_role_t role);

/* Requires exactly one CA, one client certificate and one client key file. */
bool zs_bg95_provision_start(zs_bg95_provision_t *p, uint32_t now_ms);
void zs_bg95_provision_tick(zs_bg95_provision_t *p, uint32_t now_ms);
void zs_bg95_provision_on_line(zs_bg95_provision_t *p, const char *line, uint32_t now_ms);
bool zs_bg95_provision_done(const zs_bg95_provision_t *p);
bool zs_bg95_provision_failed(const zs_bg95_provision_t *p);

/*
 * Station configuration -> modem driver binding.
 * Builds client id "dioneya-<station_id>-<boot_id>" and calls
 * zs_bg95_configure_mqtt_tls with host/port/ca_reference from the persistent
 * record.  Returns false when the record is invalid or the modem rejects the
 * endpoint (non-TLS port, private APN).  `tenant_out` receives the tenant bytes
 * for zs_mqtt_event_transport topic building.
 */
bool zs_bg95_provision_apply_station_config(zs_bg95_t *modem, const zs_station_config_t *cfg,
                                            uint32_t boot_id, bool public_apn,
                                            char *tenant_out, size_t tenant_cap);

#endif
