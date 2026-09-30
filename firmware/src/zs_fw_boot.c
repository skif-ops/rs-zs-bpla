#include "zs_fw_boot.h"

#include <string.h>

#define MAGIC_TRIAL 0x54574644u     /* "DFWT" little-endian */
#define MAGIC_CONFIRM 0x43574644u   /* "DFWC" */
#define MAGIC_ROLLBACK 0x52574644u  /* "DFWR" */
#define MAGIC_ATTEMPT 0x41574644u   /* "DFWA" */

static uint32_t crc32(const uint8_t *data, size_t size) {
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0u; i < size; i++) {
    crc ^= data[i];
    for (unsigned b = 0u; b < 8u; b++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
  }
  return ~crc;
}
static uint32_t get_le32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void put_le32(uint8_t *p, uint32_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static void encode_slot(uint32_t magic, uint32_t a, uint32_t b, uint8_t out[ZS_FW_BOOT_SLOT_BYTES]) {
  put_le32(&out[0], magic);
  put_le32(&out[4], a);
  put_le32(&out[8], b);
  put_le32(&out[12], crc32(out, 12u));
}

static bool slot_erased(const uint8_t *slot) {
  for (unsigned i = 0u; i < ZS_FW_BOOT_SLOT_BYTES; i++) if (slot[i] != 0xFFu) return false;
  return true;
}

static bool slot_valid(const uint8_t *slot, uint32_t magic) {
  return get_le32(&slot[0]) == magic && get_le32(&slot[12]) == crc32(slot, 12u);
}

void zs_fw_boot_parse(const uint8_t bytes[ZS_FW_BOOT_RECORD_BYTES], zs_fw_boot_record_t *record) {
  const uint8_t *trial = &bytes[ZS_FW_BOOT_SLOT_TRIAL * ZS_FW_BOOT_SLOT_BYTES];
  const uint8_t *confirm = &bytes[ZS_FW_BOOT_SLOT_CONFIRM * ZS_FW_BOOT_SLOT_BYTES];
  memset(record, 0, sizeof(*record));
  if (!slot_valid(trial, MAGIC_TRIAL) || get_le32(&trial[4]) == 0u) return;     /* erased or garbage: not armed */
  record->armed = true;
  record->version = get_le32(&trial[4]);
  record->previous_version = get_le32(&trial[8]);
  record->confirmed = slot_valid(confirm, MAGIC_CONFIRM) && get_le32(&confirm[4]) == record->version;
  record->rolled_back = !slot_erased(&bytes[ZS_FW_BOOT_SLOT_ROLLBACK * ZS_FW_BOOT_SLOT_BYTES]);
  for (unsigned i = 0u; i < ZS_FW_BOOT_MAX_ATTEMPTS; i++)
    if (!slot_erased(&bytes[(ZS_FW_BOOT_SLOT_ATTEMPT0 + i) * ZS_FW_BOOT_SLOT_BYTES])) record->attempts++;
}

zs_fw_boot_action_t zs_fw_boot_decide(const zs_fw_boot_record_t *record) {
  if (!record || !record->armed || record->confirmed) return ZS_FW_BOOT_NORMAL;
  if (record->rolled_back || record->attempts >= ZS_FW_BOOT_MAX_ATTEMPTS) return ZS_FW_BOOT_ROLLBACK;
  return ZS_FW_BOOT_TRIAL;
}

bool zs_fw_boot_read(const zs_fw_boot_port_t *port, zs_fw_boot_record_t *record) {
  uint8_t bytes[ZS_FW_BOOT_RECORD_BYTES];
  if (!port || !port->read || !record || !port->read(port->ctx, 0u, bytes, sizeof(bytes))) {
    if (record) memset(record, 0, sizeof(*record));
    return false;
  }
  zs_fw_boot_parse(bytes, record);
  return true;
}

zs_fw_boot_action_t zs_fw_boot_guard(const zs_fw_boot_port_t *port, zs_fw_boot_record_t *record) {
  uint8_t slot[ZS_FW_BOOT_SLOT_BYTES];
  zs_fw_boot_action_t action;
  if (!port || !port->program || !zs_fw_boot_read(port, record)) return ZS_FW_BOOT_NORMAL;   /* unreadable: nothing to decide on */
  action = zs_fw_boot_decide(record);
  if (action == ZS_FW_BOOT_TRIAL) {
    encode_slot(MAGIC_ATTEMPT, record->version, record->attempts, slot);
    if (port->program(port->ctx, (ZS_FW_BOOT_SLOT_ATTEMPT0 + record->attempts) * ZS_FW_BOOT_SLOT_BYTES, slot)) {
      record->attempts++;
      return ZS_FW_BOOT_TRIAL;
    }
    action = ZS_FW_BOOT_ROLLBACK;
  }
  if (action == ZS_FW_BOOT_ROLLBACK && !record->rolled_back) {
    encode_slot(MAGIC_ROLLBACK, record->version, record->attempts, slot);
    (void)port->program(port->ctx, ZS_FW_BOOT_SLOT_ROLLBACK * ZS_FW_BOOT_SLOT_BYTES, slot);
    record->rolled_back = true;
  }
  return action;
}

bool zs_fw_boot_arm(const zs_fw_boot_port_t *other_bank, uint32_t version, uint32_t previous_version) {
  uint8_t slot[ZS_FW_BOOT_SLOT_BYTES];
  zs_fw_boot_record_t check;
  if (!other_bank || !other_bank->program || version == 0u) return false;
  encode_slot(MAGIC_TRIAL, version, previous_version, slot);
  if (!other_bank->program(other_bank->ctx, ZS_FW_BOOT_SLOT_TRIAL * ZS_FW_BOOT_SLOT_BYTES, slot)) return false;
  return zs_fw_boot_read(other_bank, &check) && check.armed && check.version == version && !check.confirmed &&
         !check.rolled_back && check.attempts == 0u;
}

bool zs_fw_boot_confirm(const zs_fw_boot_port_t *port, zs_fw_boot_record_t *record) {
  uint8_t slot[ZS_FW_BOOT_SLOT_BYTES];
  if (!port || !port->program || !record) return false;
  if (!record->armed || record->confirmed) return true;
  encode_slot(MAGIC_CONFIRM, record->version, 0u, slot);
  if (!port->program(port->ctx, ZS_FW_BOOT_SLOT_CONFIRM * ZS_FW_BOOT_SLOT_BYTES, slot)) return false;
  return zs_fw_boot_read(port, record) && record->confirmed;
}

const char *zs_fw_boot_action_name(zs_fw_boot_action_t action) {
  switch (action) {
    case ZS_FW_BOOT_NORMAL: return "normal";
    case ZS_FW_BOOT_TRIAL: return "trial";
    case ZS_FW_BOOT_ROLLBACK: return "rollback";
    default: return "?";
  }
}
