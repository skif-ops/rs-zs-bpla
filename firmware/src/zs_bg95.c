#include "zs_bg95.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

#define BG95_COMMAND_TIMEOUT_MS 120000u

static bool copy_checked(char *dst, size_t size, const char *src) {
  size_t n;
  if (!dst || !src || size == 0u) return false;
  n = strlen(src);
  if (n == 0u || n >= size || strpbrk(src, "\r\n\"") != NULL) return false;
  memcpy(dst, src, n + 1u);
  return true;
}

static bool contains_private(const char *text) {
  static const char word[] = "private";
  size_t i;
  if (!text) return false;
  for (; *text; ++text) {
    for (i = 0u; word[i] && text[i] &&
         (char)tolower((unsigned char)text[i]) == word[i]; ++i) {}
    if (word[i] == '\0') return true;
  }
  return false;
}

static bool send_cmd(zs_bg95_t *m, const char *command) {
  uint8_t frame[256];
  size_t n;
  if (!m || !command || !m->io.uart_write) return false;
  n = strlen(command);
  if (n == 0u || n >= sizeof(m->last_command) || n + 2u > sizeof(frame)) return false;
  memcpy(m->last_command, command, n + 1u);
  memcpy(frame, command, n);
  frame[n++] = '\r';
  frame[n++] = '\n';
  if (m->io.uart_write(m->io.ctx, m->uart_channel, frame, n) < 0) return false;
  m->command_pending = true;
  return true;
}

static void set_deadline(zs_bg95_t *m, uint32_t now_ms) {
  m->deadline_ms = now_ms + BG95_COMMAND_TIMEOUT_MS;
}

static void fail_transport(zs_bg95_t *m) {
  m->command_pending = false;
  m->mqtt_open = false;
  m->mqtt_connected = false;
  m->state = ZS_BG95_ERROR;
}

static bool send_tls_step(zs_bg95_t *m, uint32_t now_ms) {
  char command[224];
  int n = -1;
  switch (m->tls_step) {
    case 0u:
      n = snprintf(command, sizeof(command), "AT+QSSLCFG=\"sslversion\",%u,4", m->ssl_context);
      break;
    case 1u:
      n = snprintf(command, sizeof(command), "AT+QSSLCFG=\"seclevel\",%u,2", m->ssl_context);
      break;
    case 2u:
      n = snprintf(command, sizeof(command), "AT+QSSLCFG=\"cacert\",%u,\"%s\"",
                   m->ssl_context, m->ca_cert_path);
      break;
    case 3u:
      n = snprintf(command, sizeof(command), "AT+QMTCFG=\"ssl\",%u,1,%u",
                   m->mqtt_client, m->ssl_context);
      break;
    default:
      return false;
  }
  if (n < 0 || (size_t)n >= sizeof(command) || !send_cmd(m, command)) return false;
  set_deadline(m, now_ms);
  return true;
}

void zs_bg95_init(zs_bg95_t *m, const zs_hal_port_t *io,
                  unsigned uart, unsigned pwrkey, const char *apn) {
  if (!m) return;
  memset(m, 0, sizeof(*m));
  if (io) m->io = *io;
  m->uart_channel = uart;
  m->pwrkey_gpio = pwrkey;
  m->state = ZS_BG95_OFF;
  m->ssl_context = 1u;
  if (apn) (void)copy_checked(m->apn, sizeof(m->apn), apn);
}

void zs_bg95_power_on(zs_bg95_t *m, uint32_t now_ms) {
  if (!m) return;
  if (m->io.gpio_write) m->io.gpio_write(m->io.ctx, m->pwrkey_gpio, true);
  m->state = ZS_BG95_POWERING;
  m->deadline_ms = now_ms + 700u;
  m->retries = 0u;
  m->network = ZS_BG95_NET_NONE;
  m->sim_ready = false;
  m->registered_eps = false;
  m->registered_cs = false;
  m->command_pending = false;
  m->mqtt_open = false;
  m->mqtt_connected = false;
}

static int registration_status(const char *line) {
  const char *p = strchr(line, ':');
  int first = -1, second = -1;
  if (!p) return -1;
  if (sscanf(p + 1, " %d,%d", &first, &second) == 2) return second;
  return sscanf(p + 1, " %d", &first) == 1 ? first : -1;
}

static void on_ok(zs_bg95_t *m, uint32_t now_ms) {
  char command[224];
  int n;
  m->command_pending = false;
  switch (m->state) {
    case ZS_BG95_AT_SYNC:
      m->retries = 0u;
      m->state = ZS_BG95_SIM_CHECK;
      if (!send_cmd(m, "AT+CPIN?")) fail_transport(m);
      break;
    case ZS_BG95_CONFIGURE:
      m->retries = 0u;
      m->state = ZS_BG95_REGISTERING;
      if (!send_cmd(m, "AT+CEREG?")) fail_transport(m);
      break;
    case ZS_BG95_PDP_ACTIVATING:
      m->state = ZS_BG95_TLS_CONFIGURING;
      m->tls_step = 0u;
      if (!send_tls_step(m, now_ms)) fail_transport(m);
      break;
    case ZS_BG95_TLS_CONFIGURING:
      ++m->tls_step;
      if (m->tls_step < 4u) {
        if (!send_tls_step(m, now_ms)) fail_transport(m);
      } else {
        n = snprintf(command, sizeof(command), "AT+QMTOPEN=%u,\"%s\",%u",
                     m->mqtt_client, m->mqtt_host, m->mqtt_port);
        m->state = ZS_BG95_MQTT_OPENING;
        if (n < 0 || (size_t)n >= sizeof(command) || !send_cmd(m, command)) fail_transport(m);
        else set_deadline(m, now_ms);
      }
      break;
    default:
      break;
  }
}

void zs_bg95_on_line(zs_bg95_t *m, const char *line, uint32_t now_ms) {
  char command[224];
  unsigned client = 0u, result = 0u, ack = 0u;
  int n;
  if (!m || !line) return;
  if (strstr(line, "+CPIN: READY")) {
    m->sim_ready = true;
    m->state = ZS_BG95_CONFIGURE;
    if (m->apn[0]) {
      n = snprintf(command, sizeof(command), "AT+CGDCONT=1,\"IP\",\"%s\"", m->apn);
      if (n < 0 || (size_t)n >= sizeof(command) || !send_cmd(m, command)) fail_transport(m);
    } else if (!send_cmd(m, "ATE0")) {
      fail_transport(m);
    }
    return;
  }
  if (strstr(line, "+CEREG:")) {
    int status = registration_status(line);
    m->registered_eps = status == 1 || status == 5;
    if (!m->registered_eps && m->state >= ZS_BG95_PDP_ACTIVATING &&
        m->state <= ZS_BG95_ONLINE) {
      fail_transport(m);
      return;
    }
    if (m->registered_eps && m->state == ZS_BG95_REGISTERING) {
      m->network = ZS_BG95_NET_LTE;
      m->state = ZS_BG95_READY;
      m->command_pending = false;
    }
    return;
  }
  if (strstr(line, "+CREG:")) {
    int status = registration_status(line);
    m->registered_cs = status == 1 || status == 5;
    if (!m->registered_cs && m->network == ZS_BG95_NET_2G &&
        m->state >= ZS_BG95_PDP_ACTIVATING && m->state <= ZS_BG95_ONLINE) {
      fail_transport(m);
      return;
    }
    if (m->registered_cs && m->state == ZS_BG95_REGISTERING) {
      m->network = ZS_BG95_NET_2G;
      m->state = ZS_BG95_READY;
      m->command_pending = false;
    }
    return;
  }
  if (sscanf(line, "+QMTOPEN: %u,%u", &client, &result) == 2) {
    if (client != m->mqtt_client || result != 0u || m->state != ZS_BG95_MQTT_OPENING) {
      fail_transport(m);
      return;
    }
    m->mqtt_open = true;
    n = snprintf(command, sizeof(command), "AT+QMTCONN=%u,\"%s\"",
                 m->mqtt_client, m->mqtt_client_id);
    m->state = ZS_BG95_MQTT_CONNECTING;
    if (n < 0 || (size_t)n >= sizeof(command) || !send_cmd(m, command)) fail_transport(m);
    else set_deadline(m, now_ms);
    return;
  }
  if (sscanf(line, "+QMTCONN: %u,%u,%u", &client, &result, &ack) == 3) {
    if (client != m->mqtt_client || result != 0u || ack != 0u ||
        m->state != ZS_BG95_MQTT_CONNECTING) {
      fail_transport(m);
      return;
    }
    m->command_pending = false;
    m->mqtt_connected = true;
    m->state = ZS_BG95_ONLINE;
    return;
  }
  if (strstr(line, "+QMTSTAT:")) {
    fail_transport(m);
    return;
  }
  if (strcmp(line, "OK") == 0) {
    on_ok(m, now_ms);
    return;
  }
  if (strstr(line, "ERROR")) {
    if (m->state >= ZS_BG95_PDP_ACTIVATING) {
      fail_transport(m);
    } else {
      m->command_pending = false;
      if (++m->retries > 3u) m->state = ZS_BG95_ERROR;
      else m->retry_at_ms = now_ms + 1000u;
    }
  }
}

bool zs_bg95_configure_mqtt_tls(zs_bg95_t *m, const char *host, uint16_t port,
                                const char *client_id, const char *ca_cert_path,
                                bool public_apn) {
  if (!m) return false;
  m->transport_configured = false;
  if (!public_apn || m->apn[0] == '\0' || contains_private(m->apn) ||
      (port != 443u && port != 8883u)) return false;
  if (!copy_checked(m->mqtt_host, sizeof(m->mqtt_host), host) ||
      !copy_checked(m->mqtt_client_id, sizeof(m->mqtt_client_id), client_id) ||
      !copy_checked(m->ca_cert_path, sizeof(m->ca_cert_path), ca_cert_path)) return false;
  m->mqtt_port = port;
  m->transport_configured = true;
  return true;
}

bool zs_bg95_start_mqtt(zs_bg95_t *m, uint32_t now_ms) {
  if (!m || m->state != ZS_BG95_READY || !m->transport_configured ||
      !m->sim_ready || m->network == ZS_BG95_NET_NONE) return false;
  m->state = ZS_BG95_PDP_ACTIVATING;
  if (!send_cmd(m, "AT+QIACT=1")) {
    fail_transport(m);
    return false;
  }
  set_deadline(m, now_ms);
  return true;
}

void zs_bg95_tick(zs_bg95_t *m, uint32_t now_ms) {
  if (!m) return;
  if (m->state == ZS_BG95_POWERING && now_ms >= m->deadline_ms) {
    if (m->io.gpio_write) m->io.gpio_write(m->io.ctx, m->pwrkey_gpio, false);
    m->state = ZS_BG95_AT_SYNC;
    m->retry_at_ms = now_ms;
  }
  if (m->state == ZS_BG95_AT_SYNC && !m->command_pending && now_ms >= m->retry_at_ms) {
    if (!send_cmd(m, "AT")) fail_transport(m);
    m->retry_at_ms = now_ms + 1000u;
  }
  if (m->state == ZS_BG95_REGISTERING && !m->command_pending && now_ms >= m->retry_at_ms) {
    if (m->retries < 5u) {
      if (!send_cmd(m, "AT+CEREG?")) fail_transport(m);
      ++m->retries;
    } else if (!send_cmd(m, "AT+CREG?")) {
      fail_transport(m);
    }
    m->retry_at_ms = now_ms + 2000u;
  }
  if (m->state >= ZS_BG95_PDP_ACTIVATING && m->state <= ZS_BG95_MQTT_CONNECTING &&
      now_ms >= m->deadline_ms) fail_transport(m);
}

bool zs_bg95_ready(const zs_bg95_t *m) {
  return m && (m->state == ZS_BG95_READY || m->state == ZS_BG95_ONLINE);
}

bool zs_bg95_online(const zs_bg95_t *m) {
  return m && m->state == ZS_BG95_ONLINE && m->mqtt_connected;
}

const char *zs_bg95_state_name(zs_bg95_state_t state) {
  static const char *const names[] = {
    "OFF", "POWERING", "AT_SYNC", "SIM_CHECK", "CONFIGURE", "REGISTERING",
    "READY", "PDP_ACTIVATING", "TLS_CONFIGURING", "MQTT_OPENING",
    "MQTT_CONNECTING", "ONLINE", "ERROR"
  };
  return state <= ZS_BG95_ERROR ? names[state] : "?";
}
