#ifndef ZS_BG95_H
#define ZS_BG95_H

#include "zs_hal_port.h"

#include <stdbool.h>
#include <stdint.h>

typedef enum {
  ZS_BG95_OFF = 0,
  ZS_BG95_POWERING,
  ZS_BG95_AT_SYNC,
  ZS_BG95_SIM_CHECK,
  ZS_BG95_CONFIGURE,
  ZS_BG95_REGISTERING,
  ZS_BG95_READY,
  ZS_BG95_PDP_ACTIVATING,
  ZS_BG95_TLS_CONFIGURING,
  ZS_BG95_MQTT_OPENING,
  ZS_BG95_MQTT_CONNECTING,
  ZS_BG95_ONLINE,
  ZS_BG95_ERROR
} zs_bg95_state_t;

typedef enum {
  ZS_BG95_NET_NONE = 0,
  ZS_BG95_NET_LTE = 1,
  ZS_BG95_NET_NBIOT = 2,
  ZS_BG95_NET_2G = 3
} zs_bg95_net_t;

typedef struct {
  zs_hal_port_t io;
  unsigned uart_channel;
  unsigned pwrkey_gpio;
  zs_bg95_state_t state;
  zs_bg95_net_t network;
  char apn[64];
  char mqtt_host[96];
  char mqtt_client_id[64];
  char ca_cert_path[96];
  char last_command[224];
  uint32_t deadline_ms;
  uint32_t retry_at_ms;
  uint16_t mqtt_port;
  uint8_t retries;
  uint8_t tls_step;
  uint8_t ssl_context;
  uint8_t mqtt_client;
  bool sim_ready;
  bool registered_eps;
  bool registered_cs;
  bool command_pending;
  bool transport_configured;
  bool mqtt_open;
  bool mqtt_connected;
} zs_bg95_t;

void zs_bg95_init(zs_bg95_t *m, const zs_hal_port_t *io,
                  unsigned uart_channel, unsigned pwrkey_gpio, const char *apn);
void zs_bg95_power_on(zs_bg95_t *m, uint32_t now_ms);
void zs_bg95_tick(zs_bg95_t *m, uint32_t now_ms);
void zs_bg95_on_line(zs_bg95_t *m, const char *line, uint32_t now_ms);
bool zs_bg95_configure_mqtt_tls(zs_bg95_t *m, const char *host, uint16_t port,
                                const char *client_id, const char *ca_cert_path,
                                bool public_apn);
bool zs_bg95_start_mqtt(zs_bg95_t *m, uint32_t now_ms);
bool zs_bg95_ready(const zs_bg95_t *m);
bool zs_bg95_online(const zs_bg95_t *m);
const char *zs_bg95_state_name(zs_bg95_state_t state);

#endif
