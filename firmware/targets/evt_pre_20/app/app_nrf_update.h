#ifndef APP_NRF_UPDATE_H
#define APP_NRF_UPDATE_H
/*
 * nRF52840 bridge image handling on the B1 bench (ICD addendum C.6):
 *   nrfimg begin <size> <version> <sha256hex>   erase the NOR slot, open a write session
 *   nrfimg put <offset> <base64>                 append up to 96 bytes (tools/nrf_image_push.py streams a .bin this way)
 *   nrfimg end                                   verify running + read-back SHA-256, commit the header
 *   nrfimg                                       slot status
 *   nrfupd                                       restart the module in MCUboot serial recovery, upload the slot image
 *                                                over the IPC UART with zs_mcumgr_serial, reset it (runs in the ble task)
 */
#include "zs_nor.h"
#include "zs_nor_storage_layout.h"
#include <stdbool.h>

typedef void (*app_print_fn)(const char *fmt, ...);

void app_nrf_update_bind(zs_nor_t *nor, const zs_nor_storage_layout_t *layout, app_print_fn print);
/* Console front end; returns true when the line was an nrfimg/nrfupd command. */
bool app_nrf_console(const char *line);
/* nrfupd was requested and not yet run. */
bool app_nrf_update_pending(void);
/* Runs the update (blocking, ble task context, several minutes at 115200 baud); the caller re-inits the IPC link after. */
void app_nrf_update_run(void);

#endif
