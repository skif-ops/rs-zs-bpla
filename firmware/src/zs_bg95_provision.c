#include "zs_bg95_provision.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

uint16_t zs_bg95_provision_checksum16(const uint8_t *data, size_t size) {
  uint16_t sum = 0u;
  size_t i;
  for (i = 0u; i + 1u < size; i += 2u) sum ^= (uint16_t)(((uint16_t)data[i] << 8) | data[i + 1u]);
  if (i < size) sum ^= (uint16_t)((uint16_t)data[i] << 8);
  return sum;
}

static bool name_ok(const char *name) {
  size_t n = 0u;
  if (!name) return false;
  while (name[n] != '\0') {
    char c = name[n];
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')) return false;
    if (++n > ZS_BG95_PROVISION_NAME_MAX) return false;
  }
  return n > 0u;
}

void zs_bg95_provision_init(zs_bg95_provision_t *p, const zs_hal_port_t *io, unsigned uart_channel,
                            uint8_t ssl_context) {
  if (!p) return;
  memset(p, 0, sizeof(*p));
  if (io) p->io = *io;
  p->uart_channel = uart_channel;
  p->ssl_context = ssl_context;
  p->state = ZS_BG95_PROVISION_IDLE;
}

bool zs_bg95_provision_add_file(zs_bg95_provision_t *p, const char *name, const uint8_t *data, size_t size,
                                zs_bg95_provision_role_t role) {
  zs_bg95_provision_file_t *f;
  if (!p || p->state != ZS_BG95_PROVISION_IDLE || p->file_count >= ZS_BG95_PROVISION_MAX_FILES ||
      !name_ok(name) || !data || size == 0u || size > 65535u) return false;
  for (uint8_t i = 0u; i < p->file_count; i++) {
    if (p->files[i].role == role || strcmp(p->files[i].name, name) == 0) return false;
  }
  f = &p->files[p->file_count++];
  strcpy(f->name, name);
  f->data = data;
  f->size = size;
  f->role = role;
  if (role == ZS_BG95_PROVISION_ROLE_CLIENT_CERT) p->client_cert_name = f->name;
  if (role == ZS_BG95_PROVISION_ROLE_CLIENT_KEY) p->client_key_name = f->name;
  return true;
}

static bool write_all(zs_bg95_provision_t *p, const uint8_t *data, size_t len) {
  if (!p->io.uart_write) return false;
  return p->io.uart_write(p->io.ctx, p->uart_channel, data, len) == (int)len;
}

static bool send_line(zs_bg95_provision_t *p, const char *command, uint32_t now_ms, uint32_t timeout_ms) {
  char frame[128];
  int n = snprintf(frame, sizeof(frame), "%s\r\n", command);
  if (n <= 0 || (size_t)n >= sizeof(frame)) return false;
  if (!write_all(p, (const uint8_t *)frame, (size_t)n)) return false;
  p->deadline_ms = now_ms + timeout_ms;
  p->result_seen = false;
  return true;
}

static void fail(zs_bg95_provision_t *p, zs_bg95_provision_error_t err) {
  p->state = ZS_BG95_PROVISION_FAILED;
  p->error = err;
}

static const zs_bg95_provision_file_t *current(const zs_bg95_provision_t *p) {
  return &p->files[p->file_index];
}

static bool enter(zs_bg95_provision_t *p, zs_bg95_provision_state_t state, uint32_t now_ms) {
  char cmd[128];
  const zs_bg95_provision_file_t *f = current(p);
  int n = -1;
  p->state = state;
  switch (state) {
    case ZS_BG95_PROVISION_DELETE:
      n = snprintf(cmd, sizeof(cmd), "AT+QFDEL=\"%s\"", f->name);
      break;
    case ZS_BG95_PROVISION_UPLOAD_CMD:
      n = snprintf(cmd, sizeof(cmd), "AT+QFUPL=\"%s\",%u,%u", f->name, (unsigned)f->size,
                   (unsigned)ZS_BG95_PROVISION_UPLOAD_TIMEOUT_S);
      break;
    case ZS_BG95_PROVISION_LIST:
      n = snprintf(cmd, sizeof(cmd), "AT+QFLST=\"%s\"", f->name);
      break;
    case ZS_BG95_PROVISION_BIND_CERT:
      n = snprintf(cmd, sizeof(cmd), "AT+QSSLCFG=\"clientcert\",%u,\"%s\"", p->ssl_context, p->client_cert_name);
      break;
    case ZS_BG95_PROVISION_BIND_KEY:
      n = snprintf(cmd, sizeof(cmd), "AT+QSSLCFG=\"clientkey\",%u,\"%s\"", p->ssl_context, p->client_key_name);
      break;
    default:
      return false;
  }
  if (n <= 0 || (size_t)n >= sizeof(cmd) || !send_line(p, cmd, now_ms, ZS_BG95_PROVISION_STEP_TIMEOUT_MS)) {
    fail(p, ZS_BG95_PROVISION_ERR_UART);
    return false;
  }
  return true;
}

bool zs_bg95_provision_start(zs_bg95_provision_t *p, uint32_t now_ms) {
  bool ca = false, cert = false, key = false;
  if (!p || p->state != ZS_BG95_PROVISION_IDLE) return false;
  for (uint8_t i = 0u; i < p->file_count; i++) {
    ca |= p->files[i].role == ZS_BG95_PROVISION_ROLE_CA;
    cert |= p->files[i].role == ZS_BG95_PROVISION_ROLE_CLIENT_CERT;
    key |= p->files[i].role == ZS_BG95_PROVISION_ROLE_CLIENT_KEY;
  }
  if (!ca || !cert || !key) {
    fail(p, ZS_BG95_PROVISION_ERR_INVALID_ARGUMENT);
    return false;
  }
  p->file_index = 0u;
  return enter(p, ZS_BG95_PROVISION_DELETE, now_ms);
}

static void next_file_or_bind(zs_bg95_provision_t *p, uint32_t now_ms) {
  if (p->file_index + 1u < p->file_count) {
    p->file_index++;
    enter(p, ZS_BG95_PROVISION_DELETE, now_ms);
  } else {
    enter(p, ZS_BG95_PROVISION_BIND_CERT, now_ms);
  }
}

void zs_bg95_provision_tick(zs_bg95_provision_t *p, uint32_t now_ms) {
  const zs_bg95_provision_file_t *f;
  if (!p) return;
  switch (p->state) {
    case ZS_BG95_PROVISION_UPLOAD_DATA:
      f = current(p);
      while (p->sent < f->size) {
        size_t chunk = f->size - p->sent;
        if (chunk > ZS_BG95_PROVISION_CHUNK_BYTES) chunk = ZS_BG95_PROVISION_CHUNK_BYTES;
        if (!write_all(p, f->data + p->sent, chunk)) {
          fail(p, ZS_BG95_PROVISION_ERR_UART);
          return;
        }
        p->sent += chunk;
      }
      p->state = ZS_BG95_PROVISION_UPLOAD_RESULT;
      p->deadline_ms = now_ms + ZS_BG95_PROVISION_UPLOAD_TIMEOUT_MS;
      p->result_seen = false;
      return;
    case ZS_BG95_PROVISION_IDLE:
    case ZS_BG95_PROVISION_DONE:
    case ZS_BG95_PROVISION_FAILED:
      return;
    default:
      if ((int32_t)(now_ms - p->deadline_ms) > 0) fail(p, ZS_BG95_PROVISION_ERR_TIMEOUT);
      return;
  }
}

static bool starts_with(const char *line, const char *prefix) { return strncmp(line, prefix, strlen(prefix)) == 0; }

void zs_bg95_provision_on_line(zs_bg95_provision_t *p, const char *line, uint32_t now_ms) {
  const zs_bg95_provision_file_t *f;
  bool ok, err;
  if (!p || !line) return;
  while (*line == ' ' || *line == '\r' || *line == '\n') line++;
  if (*line == '\0') return;
  ok = strcmp(line, "OK") == 0;
  err = starts_with(line, "ERROR") || starts_with(line, "+CME ERROR") || starts_with(line, "+CMS ERROR");
  f = current(p);
  switch (p->state) {
    case ZS_BG95_PROVISION_DELETE:
      if (ok || err) enter(p, ZS_BG95_PROVISION_UPLOAD_CMD, now_ms); /* absent file is fine */
      break;
    case ZS_BG95_PROVISION_UPLOAD_CMD:
      if (strcmp(line, "CONNECT") == 0) {
        p->state = ZS_BG95_PROVISION_UPLOAD_DATA;
        p->sent = 0u;
      } else if (err) {
        fail(p, ZS_BG95_PROVISION_ERR_MODEM_ERROR);
      }
      break;
    case ZS_BG95_PROVISION_UPLOAD_RESULT:
      if (starts_with(line, "+QFUPL:")) {
        unsigned size = 0u, checksum = 0u;
        if (sscanf(line + 7, " %u,%u", &size, &checksum) != 2 || size != f->size) {
          fail(p, ZS_BG95_PROVISION_ERR_SIZE_MISMATCH);
        } else if ((uint16_t)checksum != zs_bg95_provision_checksum16(f->data, f->size)) {
          fail(p, ZS_BG95_PROVISION_ERR_CHECKSUM_MISMATCH);
        } else {
          p->result_seen = true;
        }
      } else if (ok) {
        if (p->result_seen) enter(p, ZS_BG95_PROVISION_LIST, now_ms);
        else fail(p, ZS_BG95_PROVISION_ERR_MODEM_ERROR);
      } else if (err) {
        fail(p, ZS_BG95_PROVISION_ERR_MODEM_ERROR);
      }
      break;
    case ZS_BG95_PROVISION_LIST:
      if (starts_with(line, "+QFLST:")) {
        char name[ZS_BG95_PROVISION_NAME_MAX + 1u];
        unsigned size = 0u;
        char fmt[48];
        snprintf(fmt, sizeof(fmt), " \"%%%u[^\"]\",%%u", (unsigned)ZS_BG95_PROVISION_NAME_MAX);
        if (sscanf(line + 7, fmt, name, &size) == 2 && strcmp(name, f->name) == 0 && size == f->size) {
          p->result_seen = true;
        } else {
          fail(p, ZS_BG95_PROVISION_ERR_LIST_MISMATCH);
        }
      } else if (ok) {
        if (p->result_seen) next_file_or_bind(p, now_ms);
        else fail(p, ZS_BG95_PROVISION_ERR_LIST_MISMATCH);
      } else if (err) {
        fail(p, ZS_BG95_PROVISION_ERR_MODEM_ERROR);
      }
      break;
    case ZS_BG95_PROVISION_BIND_CERT:
      if (ok) enter(p, ZS_BG95_PROVISION_BIND_KEY, now_ms);
      else if (err) fail(p, ZS_BG95_PROVISION_ERR_MODEM_ERROR);
      break;
    case ZS_BG95_PROVISION_BIND_KEY:
      if (ok) p->state = ZS_BG95_PROVISION_DONE;
      else if (err) fail(p, ZS_BG95_PROVISION_ERR_MODEM_ERROR);
      break;
    default:
      break;
  }
}

bool zs_bg95_provision_done(const zs_bg95_provision_t *p) { return p && p->state == ZS_BG95_PROVISION_DONE; }
bool zs_bg95_provision_failed(const zs_bg95_provision_t *p) { return p && p->state == ZS_BG95_PROVISION_FAILED; }

bool zs_bg95_provision_apply_station_config(zs_bg95_t *modem, const zs_station_config_t *cfg,
                                            uint32_t boot_id, bool public_apn,
                                            char *tenant_out, size_t tenant_cap) {
  char client_id[64];
  int n;
  if (!modem || !cfg || zs_station_config_validate(cfg) != 0u || !zs_station_config_hash_valid(cfg)) return false;
  n = snprintf(client_id, sizeof(client_id), "dioneya-%lu-%lu", (unsigned long)cfg->station_id, (unsigned long)boot_id);
  if (n <= 0 || (size_t)n >= sizeof(client_id)) return false;
  if (!zs_bg95_configure_mqtt_tls(modem, cfg->server_host, cfg->mqtt_port, client_id, cfg->ca_reference, public_apn)) return false;
  if (tenant_out) {
    size_t len = strlen(cfg->tenant);
    if (tenant_cap == 0u || len >= tenant_cap) return false;
    memcpy(tenant_out, cfg->tenant, len + 1u);
  }
  return true;
}
