#ifndef ZS_BG95_H
#define ZS_BG95_H

#include "zs_hal_port.h"
#include "zs_types.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_BG95_MAX_APN_PROFILES 8u

typedef enum {
  ZS_BG95_OFF = 0,
  ZS_BG95_POWERING,
  ZS_BG95_AT_SYNC,
  ZS_BG95_SIM_CHECK,
  ZS_BG95_SIM_ICCID_QUERY,
  ZS_BG95_SIM_IMSI_QUERY,
  ZS_BG95_OPERATOR_QUERY,
  ZS_BG95_APN_DISCOVERING,
  ZS_BG95_CONFIGURE,
  ZS_BG95_REGISTERING,
  ZS_BG95_READY,
  ZS_BG95_PDP_ACTIVATING,
  ZS_BG95_PDP_SETTINGS_QUERY,
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

typedef enum {
  ZS_BG95_APN_NONE = 0,
  ZS_BG95_APN_EXPLICIT,
  ZS_BG95_APN_NETWORK,
  ZS_BG95_APN_CATALOG
} zs_bg95_apn_source_t;

typedef struct {
  char imsi_prefix[7];
  char apn[64];
  bool public_apn;
  bool allow_network_apn;
} zs_bg95_apn_profile_t;

typedef struct {
  char imsi[17];
  char iccid[23];
  char home_plmn[7];
  char registered_operator[32];
  char apn[64];
  char local_address[64];
  char gateway[64];
  char primary_dns[64];
  char secondary_dns[64];
  uint8_t access_technology;
  zs_bg95_apn_source_t apn_source;
  bool valid;
} zs_bg95_network_settings_t;

typedef struct {
  zs_hal_port_t io;
  unsigned uart_channel;
  unsigned pwrkey_gpio;
  zs_bg95_state_t state;
  zs_bg95_net_t network;
  zs_bg95_apn_profile_t apn_profiles[ZS_BG95_MAX_APN_PROFILES];
  zs_bg95_network_settings_t network_settings;
  char apn[64];
  char network_apn[64];
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
  uint8_t apn_profile_count;
  uint8_t selected_apn_profile;
  bool auto_network;
  bool apn_public_approved;
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
bool zs_bg95_configure_auto_network(zs_bg95_t *m,
                                    const zs_bg95_apn_profile_t *profiles,
                                    size_t profile_count);
void zs_bg95_power_on(zs_bg95_t *m, uint32_t now_ms);
void zs_bg95_tick(zs_bg95_t *m, uint32_t now_ms);
void zs_bg95_on_line(zs_bg95_t *m, const char *line, uint32_t now_ms);
bool zs_bg95_configure_mqtt_tls(zs_bg95_t *m, const char *host, uint16_t port,
                                const char *client_id, const char *ca_cert_path,
                                bool public_apn);
bool zs_bg95_start_mqtt(zs_bg95_t *m, uint32_t now_ms);
bool zs_bg95_ready(const zs_bg95_t *m);
bool zs_bg95_online(const zs_bg95_t *m);
const zs_bg95_network_settings_t *zs_bg95_get_network_settings(const zs_bg95_t *m);
bool zs_bg95_export_cellular_telemetry(const zs_bg95_t *m,
                                       zs_cellular_telemetry_t *telemetry);
const char *zs_bg95_state_name(zs_bg95_state_t state);

#endif
