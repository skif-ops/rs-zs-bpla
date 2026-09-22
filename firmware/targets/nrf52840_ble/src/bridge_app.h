#ifndef BRIDGE_APP_H
#define BRIDGE_APP_H
/* Glue between the portable zs_ble_bridge core and the Zephyr BLE stack / UART. */
#include "zs_ble_bridge.h"
#include <zephyr/bluetooth/conn.h>

extern zs_ble_bridge_t bridge;

/* gatt.c */
int gatt_init(void);
bool gatt_notify_frame(uint16_t char_id, const uint8_t *frame, size_t len);
size_t gatt_att_payload(void);
void gatt_set_conn(struct bt_conn *conn);

/* ipc_uart.c */
int ipc_uart_init(void);
bool ipc_uart_send(const uint8_t *wire, size_t len);
/* Drains received bytes into the bridge; called from the main loop. */
void ipc_uart_poll(void);

/* main.c */
void app_advertise(bool on, uint16_t seconds);
void app_set_local_name(const char *name);
void app_set_pairing_secret(const uint8_t secret[16]);

#endif
