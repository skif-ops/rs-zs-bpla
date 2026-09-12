#include "zs_bg95.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

#define BG95_COMMAND_TIMEOUT_MS 120000u
#define BG95_NO_PROFILE 0xffu

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

static bool digits_only(const char *text, size_t minimum, size_t maximum) {
  size_t i, n;
  if (!text) return false;
  n = strlen(text);
  if (n < minimum || n > maximum) return false;
  for (i = 0u; i < n; ++i) {
    if (!isdigit((unsigned char)text[i])) return false;
  }
  return true;
}

static bool valid_apn(const char *apn) {
  size_t i, n;
  if (!apn) return false;
  n = strlen(apn);
  if (n == 0u || n >= sizeof(((zs_bg95_t *)0)->apn) || contains_private(apn)) return false;
  for (i = 0u; i < n; ++i) {
    unsigned char c = (unsigned char)apn[i];
    if (!isalnum(c) && c != '.' && c != '-') return false;
  }
  return true;
}

static bool copy_quoted_field(const char *line, unsigned field,
                              char *dst, size_t size) {
  const char *start = line;
  const char *end = NULL;
  unsigned current;
  size_t n;
  if (!line || !dst || size == 0u) return false;
  for (current = 0u; current <= field; ++current) {
    start = strchr(start, '"');
    if (!start) return false;
    ++start;
    end = strchr(start, '"');
    if (!end) return false;
    if (current == field) break;
    start = end + 1;
  }
  n = (size_t)(end - start);
  if (n == 0u || n >= size) return false;
  memcpy(dst, start, n);
  dst[n] = '\0';
  return true;
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

static bool send_timed_cmd(zs_bg95_t *m, const char *command, uint32_t now_ms) {
  if (!send_cmd(m, command)) return false;
  set_deadline(m, now_ms);
  return true;
}

static void fail_transport(zs_bg95_t *m) {
  m->command_pending = false;
  m->mqtt_open = false;
  m->mqtt_connected = false;
  m->network_settings.valid = false;
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
  return n >= 0 && (size_t)n < sizeof(command) && send_timed_cmd(m, command, now_ms);
}

static bool begin_apn_configuration(zs_bg95_t *m, uint32_t now_ms) {
  char command[128];
  int n;
  if (!m->apn_public_approved || !valid_apn(m->apn)) return false;
  n = snprintf(command, sizeof(command), "AT+CGDCONT=1,\"IP\",\"%s\"", m->apn);
  if (n < 0 || (size_t)n >= sizeof(command)) return false;
  m->state = ZS_BG95_CONFIGURE;
  return send_timed_cmd(m, command, now_ms);
}

static bool select_apn_profile(zs_bg95_t *m, const char *imsi) {
  size_t best = 0u;
  uint8_t selected = BG95_NO_PROFILE;
  uint8_t i;
  if (!digits_only(imsi, 14u, 16u)) return false;
  for (i = 0u; i < m->apn_profile_count; ++i) {
    size_t n = strlen(m->apn_profiles[i].imsi_prefix);
    if (n > best && strncmp(imsi, m->apn_profiles[i].imsi_prefix, n) == 0) {
      best = n;
      selected = i;
    }
  }
  if (selected == BG95_NO_PROFILE) return false;
  m->selected_apn_profile = selected;
  memcpy(m->network_settings.imsi, imsi, strlen(imsi) + 1u);
  memcpy(m->network_settings.home_plmn,
         m->apn_profiles[selected].imsi_prefix, best + 1u);
  return true;
}

static bool finish_apn_discovery(zs_bg95_t *m, uint32_t now_ms) {
  const zs_bg95_apn_profile_t *profile;
  if (m->selected_apn_profile >= m->apn_profile_count) return false;
  profile = &m->apn_profiles[m->selected_apn_profile];
  if (m->network_apn[0] && profile->allow_network_apn && valid_apn(m->network_apn)) {
    if (!copy_checked(m->apn, sizeof(m->apn), m->network_apn)) return false;
    m->network_settings.apn_source = ZS_BG95_APN_NETWORK;
  } else if (profile->apn[0] && valid_apn(profile->apn)) {
    if (!copy_checked(m->apn, sizeof(m->apn), profile->apn)) return false;
    m->network_settings.apn_source = ZS_BG95_APN_CATALOG;
  } else {
    return false;
  }
  m->apn_public_approved = profile->public_apn;
  return begin_apn_configuration(m, now_ms);
}

static bool parse_iccid(zs_bg95_t *m, const char *line) {
  const char *p = strchr(line, ':');
  char iccid[sizeof(m->network_settings.iccid)];
  size_t n = 0u;
  if (!p) return false;
  ++p;
  while (*p && isspace((unsigned char)*p)) ++p;
  if (*p == '"') ++p;
  while (isdigit((unsigned char)*p) && n + 1u < sizeof(iccid)) iccid[n++] = *p++;
  iccid[n] = '\0';
  if (n < 18u || n > 22u || isdigit((unsigned char)*p)) return false;
  memcpy(m->network_settings.iccid, iccid, n + 1u);
  return true;
}

static void parse_operator(zs_bg95_t *m, const char *line) {
  char name[sizeof(m->network_settings.registered_operator)];
  const char *end;
  unsigned act;
  if (!copy_quoted_field(line, 0u, name, sizeof(name))) return;
  end = strrchr(line, ',');
  if (end && sscanf(end + 1, "%u", &act) == 1 && act <= 255u) {
    m->network_settings.access_technology = (uint8_t)act;
  }
  memcpy(m->network_settings.registered_operator, name, strlen(name) + 1u);
}

static void parse_network_apn(zs_bg95_t *m, const char *line) {
  char apn[sizeof(m->network_apn)];
  if (copy_quoted_field(line, 0u, apn, sizeof(apn)) && valid_apn(apn)) {
    memcpy(m->network_apn, apn, strlen(apn) + 1u);
  }
}

static bool parse_pdp_settings(zs_bg95_t *m, const char *line) {
  char apn[64], local[64], gateway[64], dns1[64], dns2[64];
  int cid, bearer;
  int fields;
  fields = sscanf(line,
                  "+CGCONTRDP: %d,%d,\"%63[^\"]\",\"%63[^\"]\",\"%63[^\"]\",\"%63[^\"]\",\"%63[^\"]\"",
                  &cid, &bearer, apn, local, gateway, dns1, dns2);
  if (fields < 6 || cid != 1 || bearer < 0 || !valid_apn(apn) ||
      strcmp(apn, m->apn) != 0) return false;
  if (!copy_checked(m->network_settings.apn, sizeof(m->network_settings.apn), apn) ||
      !copy_checked(m->network_settings.local_address,
                    sizeof(m->network_settings.local_address), local) ||
      !copy_checked(m->network_settings.gateway, sizeof(m->network_settings.gateway), gateway) ||
      !copy_checked(m->network_settings.primary_dns,
                    sizeof(m->network_settings.primary_dns), dns1)) return false;
  m->network_settings.secondary_dns[0] = '\0';
  if (fields >= 7 && !copy_checked(m->network_settings.secondary_dns,
                                   sizeof(m->network_settings.secondary_dns), dns2)) return false;
  m->network_settings.valid = true;
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
  m->selected_apn_profile = BG95_NO_PROFILE;
  if (apn && valid_apn(apn) && copy_checked(m->apn, sizeof(m->apn), apn)) {
    m->network_settings.apn_source = ZS_BG95_APN_EXPLICIT;
  }
}

bool zs_bg95_configure_auto_network(zs_bg95_t *m,
                                    const zs_bg95_apn_profile_t *profiles,
                                    size_t profile_count) {
  size_t i, j;
  if (!m || m->state != ZS_BG95_OFF || !profiles || profile_count == 0u ||
      profile_count > ZS_BG95_MAX_APN_PROFILES) return false;
  for (i = 0u; i < profile_count; ++i) {
    const zs_bg95_apn_profile_t *profile = &profiles[i];
    if (!memchr(profile->imsi_prefix, '\0', sizeof(profile->imsi_prefix)) ||
        !memchr(profile->apn, '\0', sizeof(profile->apn)) ||
        !digits_only(profile->imsi_prefix, 5u, 6u) || !profile->public_apn ||
        (!profile->allow_network_apn && profile->apn[0] == '\0') ||
        (profile->apn[0] && !valid_apn(profile->apn))) return false;
    for (j = 0u; j < i; ++j) {
      if (strcmp(profile->imsi_prefix, profiles[j].imsi_prefix) == 0) return false;
    }
  }
  memcpy(m->apn_profiles, profiles, profile_count * sizeof(*profiles));
  m->apn_profile_count = (uint8_t)profile_count;
  m->selected_apn_profile = BG95_NO_PROFILE;
  m->auto_network = true;
  m->apn_public_approved = false;
  m->apn[0] = '\0';
  m->network_settings.apn_source = ZS_BG95_APN_NONE;
  return true;
}

void zs_bg95_power_on(zs_bg95_t *m, uint32_t now_ms) {
  zs_bg95_apn_source_t apn_source;
  if (!m) return;
  apn_source = m->auto_network ? ZS_BG95_APN_NONE : m->network_settings.apn_source;
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
  memset(&m->network_settings, 0, sizeof(m->network_settings));
  m->network_settings.apn_source = apn_source;
  m->network_apn[0] = '\0';
  if (m->auto_network) {
    m->selected_apn_profile = BG95_NO_PROFILE;
    m->apn_public_approved = false;
    m->apn[0] = '\0';
  }
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
      if (!send_timed_cmd(m, "AT+CPIN?", now_ms)) fail_transport(m);
      break;
    case ZS_BG95_SIM_CHECK:
      if (!m->sim_ready) {
        fail_transport(m);
      } else {
        m->state = ZS_BG95_SIM_ICCID_QUERY;
        if (!send_timed_cmd(m, "AT+QCCID", now_ms)) fail_transport(m);
      }
      break;
    case ZS_BG95_SIM_ICCID_QUERY:
      if (!digits_only(m->network_settings.iccid, 18u, 22u)) {
        fail_transport(m);
      } else {
        m->state = ZS_BG95_SIM_IMSI_QUERY;
        if (!send_timed_cmd(m, "AT+CIMI", now_ms)) fail_transport(m);
      }
      break;
    case ZS_BG95_SIM_IMSI_QUERY:
      if (!digits_only(m->network_settings.imsi, 14u, 16u) ||
          (m->auto_network && m->selected_apn_profile == BG95_NO_PROFILE)) {
        fail_transport(m);
      } else {
        m->state = ZS_BG95_OPERATOR_QUERY;
        if (!send_timed_cmd(m, "AT+COPS?", now_ms)) fail_transport(m);
      }
      break;
    case ZS_BG95_OPERATOR_QUERY:
      if (m->auto_network) {
        m->state = ZS_BG95_APN_DISCOVERING;
        if (!send_timed_cmd(m, "AT+CGNAPN", now_ms)) fail_transport(m);
      } else {
        m->apn_public_approved = true;
        if (!begin_apn_configuration(m, now_ms)) fail_transport(m);
      }
      break;
    case ZS_BG95_APN_DISCOVERING:
      if (!finish_apn_discovery(m, now_ms)) fail_transport(m);
      break;
    case ZS_BG95_CONFIGURE:
      m->retries = 0u;
      m->state = ZS_BG95_REGISTERING;
      if (!send_timed_cmd(m, "AT+CEREG?", now_ms)) fail_transport(m);
      break;
    case ZS_BG95_PDP_ACTIVATING:
      m->state = ZS_BG95_PDP_SETTINGS_QUERY;
      if (!send_timed_cmd(m, "AT+CGCONTRDP=1", now_ms)) fail_transport(m);
      break;
    case ZS_BG95_PDP_SETTINGS_QUERY:
      if (!m->network_settings.valid) {
        fail_transport(m);
      } else {
        m->state = ZS_BG95_TLS_CONFIGURING;
        m->tls_step = 0u;
        if (!send_tls_step(m, now_ms)) fail_transport(m);
      }
      break;
    case ZS_BG95_TLS_CONFIGURING:
      ++m->tls_step;
      if (m->tls_step < 4u) {
        if (!send_tls_step(m, now_ms)) fail_transport(m);
      } else {
        n = snprintf(command, sizeof(command), "AT+QMTOPEN=%u,\"%s\",%u",
                     m->mqtt_client, m->mqtt_host, m->mqtt_port);
        m->state = ZS_BG95_MQTT_OPENING;
        if (n < 0 || (size_t)n >= sizeof(command) ||
            !send_timed_cmd(m, command, now_ms)) fail_transport(m);
      }
      break;
    default:
      break;
  }
}

static void on_discovery_error(zs_bg95_t *m, uint32_t now_ms) {
  m->command_pending = false;
  if (m->state == ZS_BG95_OPERATOR_QUERY) {
    if (m->auto_network) {
      m->state = ZS_BG95_APN_DISCOVERING;
      if (!send_timed_cmd(m, "AT+CGNAPN", now_ms)) fail_transport(m);
    } else {
      m->apn_public_approved = true;
      if (!begin_apn_configuration(m, now_ms)) fail_transport(m);
    }
  } else if (m->state == ZS_BG95_APN_DISCOVERING) {
    if (!finish_apn_discovery(m, now_ms)) fail_transport(m);
  } else {
    fail_transport(m);
  }
}

void zs_bg95_on_line(zs_bg95_t *m, const char *line, uint32_t now_ms) {
  char command[224];
  unsigned client = 0u, result = 0u, ack = 0u;
  int n;
  if (!m || !line) return;
  if (strstr(line, "+CPIN: READY")) {
    m->sim_ready = true;
    return;
  }
  if (m->state == ZS_BG95_SIM_ICCID_QUERY && strstr(line, "+QCCID:")) {
    if (!parse_iccid(m, line)) fail_transport(m);
    return;
  }
  if (m->state == ZS_BG95_SIM_IMSI_QUERY && digits_only(line, 14u, 16u)) {
    if (m->auto_network) {
      if (!select_apn_profile(m, line)) fail_transport(m);
    } else {
      memcpy(m->network_settings.imsi, line, strlen(line) + 1u);
    }
    return;
  }
  if (m->state == ZS_BG95_OPERATOR_QUERY && strstr(line, "+COPS:")) {
    parse_operator(m, line);
    return;
  }
  if (m->state == ZS_BG95_APN_DISCOVERING && strstr(line, "+CGNAPN:")) {
    parse_network_apn(m, line);
    return;
  }
  if (m->state == ZS_BG95_PDP_SETTINGS_QUERY && strstr(line, "+CGCONTRDP:")) {
    if (!parse_pdp_settings(m, line)) fail_transport(m);
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
    if (n < 0 || (size_t)n >= sizeof(command) ||
        !send_timed_cmd(m, command, now_ms)) fail_transport(m);
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
    if (m->state == ZS_BG95_SIM_ICCID_QUERY ||
        m->state == ZS_BG95_OPERATOR_QUERY ||
        m->state == ZS_BG95_APN_DISCOVERING) {
      on_discovery_error(m, now_ms);
    } else if (m->state == ZS_BG95_AT_SYNC || m->state == ZS_BG95_REGISTERING) {
      m->command_pending = false;
      if (++m->retries > 3u) m->state = ZS_BG95_ERROR;
      else m->retry_at_ms = now_ms + 1000u;
    } else {
      fail_transport(m);
    }
  }
}

bool zs_bg95_configure_mqtt_tls(zs_bg95_t *m, const char *host, uint16_t port,
                                const char *client_id, const char *ca_cert_path,
                                bool public_apn) {
  if (!m) return false;
  m->transport_configured = false;
  if (!public_apn || (!m->auto_network && !valid_apn(m->apn)) ||
      (m->apn[0] && contains_private(m->apn)) ||
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
      !m->sim_ready || m->network == ZS_BG95_NET_NONE ||
      !m->apn_public_approved || !valid_apn(m->apn) ||
      !digits_only(m->network_settings.imsi, 14u, 16u) ||
      !digits_only(m->network_settings.iccid, 18u, 22u)) return false;
  memset(m->network_settings.apn, 0, sizeof(m->network_settings.apn));
  memset(m->network_settings.local_address, 0, sizeof(m->network_settings.local_address));
  memset(m->network_settings.gateway, 0, sizeof(m->network_settings.gateway));
  memset(m->network_settings.primary_dns, 0, sizeof(m->network_settings.primary_dns));
  memset(m->network_settings.secondary_dns, 0, sizeof(m->network_settings.secondary_dns));
  m->network_settings.valid = false;
  m->state = ZS_BG95_PDP_ACTIVATING;
  if (!send_timed_cmd(m, "AT+QIACT=1", now_ms)) {
    fail_transport(m);
    return false;
  }
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
    if (!send_timed_cmd(m, "AT", now_ms)) fail_transport(m);
    m->retry_at_ms = now_ms + 1000u;
  }
  if (m->state == ZS_BG95_REGISTERING && !m->command_pending && now_ms >= m->retry_at_ms) {
    if (m->retries < 5u) {
      if (!send_timed_cmd(m, "AT+CEREG?", now_ms)) fail_transport(m);
      ++m->retries;
    } else if (!send_timed_cmd(m, "AT+CREG?", now_ms)) {
      fail_transport(m);
    }
    m->retry_at_ms = now_ms + 2000u;
  }
  if (m->command_pending && m->state >= ZS_BG95_AT_SYNC &&
      m->state <= ZS_BG95_REGISTERING && now_ms >= m->deadline_ms) {
    fail_transport(m);
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

const zs_bg95_network_settings_t *zs_bg95_get_network_settings(const zs_bg95_t *m) {
  return m ? &m->network_settings : NULL;
}

bool zs_bg95_export_cellular_telemetry(const zs_bg95_t *m,
                                       zs_cellular_telemetry_t *telemetry) {
  if (!m || !telemetry || !m->network_settings.valid ||
      !digits_only(m->network_settings.imsi, 14u, 16u) ||
      !digits_only(m->network_settings.iccid, 18u, 22u)) return false;
  memset(telemetry, 0, sizeof(*telemetry));
  memcpy(telemetry->imsi, m->network_settings.imsi,
         strlen(m->network_settings.imsi) + 1u);
  memcpy(telemetry->iccid, m->network_settings.iccid,
         strlen(m->network_settings.iccid) + 1u);
  memcpy(telemetry->home_plmn, m->network_settings.home_plmn,
         strlen(m->network_settings.home_plmn) + 1u);
  memcpy(telemetry->registered_operator, m->network_settings.registered_operator,
         strlen(m->network_settings.registered_operator) + 1u);
  memcpy(telemetry->apn, m->network_settings.apn,
         strlen(m->network_settings.apn) + 1u);
  memcpy(telemetry->local_address, m->network_settings.local_address,
         strlen(m->network_settings.local_address) + 1u);
  memcpy(telemetry->gateway, m->network_settings.gateway,
         strlen(m->network_settings.gateway) + 1u);
  memcpy(telemetry->primary_dns, m->network_settings.primary_dns,
         strlen(m->network_settings.primary_dns) + 1u);
  memcpy(telemetry->secondary_dns, m->network_settings.secondary_dns,
         strlen(m->network_settings.secondary_dns) + 1u);
  telemetry->access_technology = m->network_settings.access_technology;
  telemetry->apn_source = (uint8_t)m->network_settings.apn_source;
  telemetry->settings_valid = true;
  return true;
}

const char *zs_bg95_state_name(zs_bg95_state_t state) {
  static const char *const names[] = {
    "OFF", "POWERING", "AT_SYNC", "SIM_CHECK", "SIM_ICCID_QUERY",
    "SIM_IMSI_QUERY", "OPERATOR_QUERY", "APN_DISCOVERING", "CONFIGURE",
    "REGISTERING", "READY", "PDP_ACTIVATING", "PDP_SETTINGS_QUERY",
    "TLS_CONFIGURING", "MQTT_OPENING", "MQTT_CONNECTING", "ONLINE", "ERROR"
  };
  return state <= ZS_BG95_ERROR ? names[state] : "?";
}
