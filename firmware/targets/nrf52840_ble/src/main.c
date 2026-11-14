/*
 * Dioneya nRF52840 BLE bridge: advertising, connection/security events, pairing passkey derived
 * from the label secret, and the glue between zs_ble_bridge and the Zephyr stack.
 * Pairing (addendum B.7): LE Secure Connections, passkey entry with a fixed 6-digit passkey
 *   passkey = BE32(SHA-256("DIO-PAIR-V1" || secret)[0..3]) mod 1_000_000
 * The phone derives the same number from the scanned label and shows it to the installer.
 */
#include "bridge_app.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gap.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <string.h>
#ifdef CONFIG_MCUBOOT_IMG_MANAGER
#include <zephyr/dfu/mcuboot.h>
#endif

LOG_MODULE_REGISTER(dio_bridge, LOG_LEVEL_INF);

zs_ble_bridge_t bridge;
static bool window_open;
static struct k_work_delayable window_timer;
static char local_name[32] = CONFIG_BT_DEVICE_NAME;

static const struct bt_data adv_data[] = {
  BT_DATA_BYTES(BT_DATA_FLAGS, BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR),
  BT_DATA_BYTES(BT_DATA_UUID128_ALL, BT_UUID_128_ENCODE(0xd10e0100u, 0x5a53, 0x4c55, 0xb0a1, 0x000000000000ULL)),
};
static struct bt_data scan_rsp[1];

static void start_advertising(void) {
  scan_rsp[0] = (struct bt_data)BT_DATA(BT_DATA_NAME_COMPLETE, local_name, strlen(local_name));
  const int err = bt_le_adv_start(BT_LE_ADV_CONN, adv_data, ARRAY_SIZE(adv_data), scan_rsp, ARRAY_SIZE(scan_rsp));
  if (err && err != -EALREADY) LOG_ERR("adv start %d", err);
}

static void window_expired(struct k_work *work) {
  ARG_UNUSED(work);
  window_open = false;
  (void)bt_le_adv_stop();
  LOG_INF("service window closed");
}

void app_advertise(bool on, uint16_t seconds) {
  window_open = on;
  if (on) {
    start_advertising();
    if (seconds) k_work_reschedule(&window_timer, K_SECONDS(seconds)); else k_work_cancel_delayable(&window_timer);
  } else {
    k_work_cancel_delayable(&window_timer);
    (void)bt_le_adv_stop();
  }
}

/* A freshly swapped-in image is confirmed only after the STM32 has talked to it (IDENTITY_SET arrives at the
   service init and after every recovery); an image that never hears the STM32 is reverted by MCUboot on the
   next reset, which is how a broken bridge update heals itself (addendum C.6). */
static void confirm_running_image(void) {
#ifdef CONFIG_MCUBOOT_IMG_MANAGER
  if (!boot_is_img_confirmed()) {
    const int err = boot_write_img_confirmed();
    LOG_INF("image confirmed (%d)", err);
  }
#endif
}

void app_set_local_name(const char *name) {
  strncpy(local_name, name, sizeof(local_name) - 1u);
  local_name[sizeof(local_name) - 1u] = '\0';
  (void)bt_set_name(local_name);
  confirm_running_image();
}

void app_set_pairing_secret(const uint8_t secret[16]) {
  (void)bt_passkey_set(zs_ble_pairing_passkey(secret));   /* B.7, host-tested in firmware/tests/test_ble_bridge.c */
  LOG_INF("pairing passkey installed");
}

/* ---- connection and security ------------------------------------------------------------ */

static void connected(struct bt_conn *conn, uint8_t err) {
  if (err) { LOG_WRN("connect failed %u", err); return; }
  gatt_set_conn(bt_conn_ref(conn));
  zs_ble_bridge_on_link(&bridge, 1u);
  LOG_INF("connected");
}

static void disconnected(struct bt_conn *conn, uint8_t reason) {
  LOG_INF("disconnected %u", reason);
  gatt_set_conn(NULL);
  bt_conn_unref(conn);
  zs_ble_bridge_on_link(&bridge, 0u);
  if (window_open) start_advertising();
}

static void security_changed(struct bt_conn *conn, bt_security_t level, enum bt_security_err err) {
  ARG_UNUSED(conn);
  if (err == BT_SECURITY_ERR_SUCCESS && level >= BT_SECURITY_L3) zs_ble_bridge_on_link(&bridge, 2u);   /* authenticated (MITM) LESC */
  LOG_INF("security level %d err %d", level, err);
}

BT_CONN_CB_DEFINE(conn_cb) = {
  .connected = connected,
  .disconnected = disconnected,
  .security_changed = security_changed,
};

static void auth_cancel(struct bt_conn *conn) { ARG_UNUSED(conn); LOG_WRN("pairing cancelled"); }
static void auth_passkey_display(struct bt_conn *conn, unsigned int passkey) { ARG_UNUSED(conn); ARG_UNUSED(passkey); }
static const struct bt_conn_auth_cb auth_cb = {
  .passkey_display = auth_passkey_display,   /* display capability: the phone enters the label-derived passkey */
  .cancel = auth_cancel,
};

/* ---- bridge port ------------------------------------------------------------------------- */

static bool port_uart_send(void *ctx, const uint8_t *wire, size_t len) { ARG_UNUSED(ctx); return ipc_uart_send(wire, len); }
static bool port_notify(void *ctx, uint16_t id, const uint8_t *frame, size_t len) { ARG_UNUSED(ctx); return gatt_notify_frame(id, frame, len); }
static size_t port_att(void *ctx) { ARG_UNUSED(ctx); return gatt_att_payload(); }
static void port_advertise(void *ctx, bool on, uint16_t s) { ARG_UNUSED(ctx); app_advertise(on, s); }
static void port_name(void *ctx, const char *n) { ARG_UNUSED(ctx); app_set_local_name(n); }
static void port_secret(void *ctx, const uint8_t s[16]) { ARG_UNUSED(ctx); app_set_pairing_secret(s); }

static const zs_ble_bridge_port_t port = {NULL, port_uart_send, port_notify, port_att, port_advertise, port_name, port_secret};

int main(void) {
  k_work_init_delayable(&window_timer, window_expired);
  zs_ble_bridge_init(&bridge, &port);
  if (ipc_uart_init()) return -1;
  int err = bt_enable(NULL);
  if (err) { LOG_ERR("bt_enable %d", err); return err; }
  (void)bt_conn_auth_cb_register(&auth_cb);
  (void)gatt_init();
  LOG_INF("Dioneya BLE bridge ready; waiting for the STM32 (IDENTITY_SET / SERVICE_WINDOW)");
  for (;;) ipc_uart_poll();   /* feeds the bridge; every reply goes back over the UART from the same thread */
  return 0;
}
