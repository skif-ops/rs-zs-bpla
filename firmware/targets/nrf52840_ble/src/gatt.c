/* GATT table of ICD addendum B.1 on top of the portable bridge (zs_ble_bridge). */
#include "bridge_app.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(gatt, LOG_LEVEL_INF);

/* d10eXXXX-5a53-4c55-b0a1-000000000000 */
#define DIO_UUID(id16) BT_UUID_DECLARE_128(BT_UUID_128_ENCODE(0xd10e0000u | (id16), 0x5a53, 0x4c55, 0xb0a1, 0x000000000000ULL))

static struct bt_conn *current_conn;

static ssize_t read_cb(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset) {
  const uint16_t char_id = (uint16_t)(uintptr_t)attr->user_data;
  uint8_t frame[ZS_BLE_ATT_PAYLOAD_MAX];
  size_t n;
  if (offset != 0u) return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET); /* every ATT read is one frame (B.2) */
  if (!zs_ble_bridge_on_gatt_read(&bridge, char_id, frame, sizeof(frame), &n)) return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
  return bt_gatt_attr_read(conn, attr, buf, len, 0u, frame, (uint16_t)n);
}

static ssize_t write_cb(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags) {
  const uint16_t char_id = (uint16_t)(uintptr_t)attr->user_data;
  ARG_UNUSED(conn); ARG_UNUSED(flags);
  if (offset != 0u) return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
  if (!zs_ble_bridge_on_gatt_write(&bridge, char_id, buf, len)) return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
  return len;
}

static void ccc_changed(const struct bt_gatt_attr *attr, uint16_t value) { ARG_UNUSED(attr); ARG_UNUSED(value); }

#define CHAR_ID(id) ((void *)(uintptr_t)(id))
/* Reads before pairing are allowed only for identity (B.4); everything else needs an authenticated (MITM) link. */
BT_GATT_SERVICE_DEFINE(dio_device_info,
  BT_GATT_PRIMARY_SERVICE(DIO_UUID(0x0100)),
  BT_GATT_CHARACTERISTIC(DIO_UUID(0x0101), BT_GATT_CHRC_READ, BT_GATT_PERM_READ, read_cb, NULL, CHAR_ID(ZS_CHAR_IDENTITY)),
);

BT_GATT_SERVICE_DEFINE(dio_configuration,
  BT_GATT_PRIMARY_SERVICE(DIO_UUID(0x0200)),
  BT_GATT_CHARACTERISTIC(DIO_UUID(0x0201), BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ_AUTHEN, read_cb, NULL, CHAR_ID(ZS_CHAR_CONFIG_READ)),
  BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_AUTHEN),
  BT_GATT_CHARACTERISTIC(DIO_UUID(0x0202), BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_WRITE_AUTHEN, NULL, write_cb, CHAR_ID(ZS_CHAR_CONFIG_WRITE)),
  BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_AUTHEN),
  BT_GATT_CHARACTERISTIC(DIO_UUID(0x0203), BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ_AUTHEN | BT_GATT_PERM_WRITE_AUTHEN, read_cb, write_cb, CHAR_ID(ZS_CHAR_INSTALLATION_POSITION)),
  BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_AUTHEN),
  BT_GATT_CHARACTERISTIC(DIO_UUID(0x0204), BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ_AUTHEN | BT_GATT_PERM_WRITE_AUTHEN, read_cb, write_cb, CHAR_ID(ZS_CHAR_POSITION_TRUST_POLICY)),
  BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_AUTHEN),
  BT_GATT_CHARACTERISTIC(DIO_UUID(0x0205), BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ_AUTHEN | BT_GATT_PERM_WRITE_AUTHEN, read_cb, write_cb, CHAR_ID(ZS_CHAR_SESSION_ROLE)),   /* B.9 */
  BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_AUTHEN),
  BT_GATT_CHARACTERISTIC(DIO_UUID(0x0206), BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ_AUTHEN | BT_GATT_PERM_WRITE_AUTHEN, read_cb, write_cb, CHAR_ID(ZS_CHAR_STATION_SECRETS)),   /* v0.3 */
  BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_AUTHEN),
);

BT_GATT_SERVICE_DEFINE(dio_diagnostics,
  BT_GATT_PRIMARY_SERVICE(DIO_UUID(0x0300)),
  BT_GATT_CHARACTERISTIC(DIO_UUID(0x0301), BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ_AUTHEN, read_cb, NULL, CHAR_ID(ZS_CHAR_STATUS)),
  BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_AUTHEN),
  BT_GATT_CHARACTERISTIC(DIO_UUID(0x0302), BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ_AUTHEN, read_cb, NULL, CHAR_ID(ZS_CHAR_GNSS_INTEGRITY)),
  BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_AUTHEN),
  BT_GATT_CHARACTERISTIC(DIO_UUID(0x0303), BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_WRITE_AUTHEN, NULL, write_cb, CHAR_ID(ZS_CHAR_SELF_TEST)),
  BT_GATT_CCC(ccc_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE_AUTHEN),
);

/* Finds the characteristic value attribute for a bridge char id (static tables, so a linear scan is fine). */
static const struct bt_gatt_attr *value_attr(uint16_t char_id) {
  const struct bt_gatt_service_static *svcs[] = {&dio_device_info, &dio_configuration, &dio_diagnostics};
  for (size_t s = 0u; s < ARRAY_SIZE(svcs); s++)
    for (size_t i = 0u; i < svcs[s]->attr_count; i++) {
      const struct bt_gatt_attr *a = &svcs[s]->attrs[i];
      if (a->user_data == CHAR_ID(char_id) && (a->read == read_cb || a->write == write_cb)) return a;
    }
  return NULL;
}

bool gatt_notify_frame(uint16_t char_id, const uint8_t *frame, size_t len) {
  const struct bt_gatt_attr *attr = value_attr(char_id);
  if (attr == NULL || current_conn == NULL) return false;
  if (!bt_gatt_is_subscribed(current_conn, attr, BT_GATT_CCC_NOTIFY)) return false;
  return bt_gatt_notify(current_conn, attr, frame, (uint16_t)len) == 0;
}

size_t gatt_att_payload(void) {
  if (current_conn == NULL) return ZS_BLE_ATT_PAYLOAD_MIN;
  const uint16_t mtu = bt_gatt_get_mtu(current_conn);
  if (mtu < ZS_BLE_ATT_PAYLOAD_MIN + 3u) return ZS_BLE_ATT_PAYLOAD_MIN;
  return mtu - 3u > ZS_BLE_ATT_PAYLOAD_MAX ? ZS_BLE_ATT_PAYLOAD_MAX : mtu - 3u;
}

void gatt_set_conn(struct bt_conn *conn) { current_conn = conn; }

int gatt_init(void) { return 0; }
