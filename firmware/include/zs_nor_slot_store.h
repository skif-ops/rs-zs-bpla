#ifndef ZS_NOR_SLOT_STORE_H
#define ZS_NOR_SLOT_STORE_H
/*
 * NOR binding for the small double-slot records of the station (B3):
 *   station configuration (zs_station_config, 2 x 320 B) and the installation
 *   record (zs_installation_store, 2 x 96 B).  Every slot owns one whole erase
 *   block, so committing to the inactive slot never touches the active one.
 * The same adapter serves both io types because their signatures are identical.
 */
#include "zs_installation_store.h"
#include "zs_nor.h"
#include "zs_station_config.h"

typedef struct {
  zs_nor_t *nor;
  uint32_t base_address; /* erase-block aligned */
  uint8_t slot_count;
  uint32_t record_bytes; /* bytes addressable inside a slot (<= erase block) */
} zs_nor_slot_store_t;

bool zs_nor_slot_store_init(zs_nor_slot_store_t *store, zs_nor_t *nor, uint32_t base_address,
                            uint8_t slot_count, uint32_t record_bytes);

/* Both bind the same adapter; the adapter must outlive the io. */
bool zs_nor_slot_store_config_io(zs_nor_slot_store_t *store, zs_station_config_io_t *out_io);
bool zs_nor_slot_store_installation_io(zs_nor_slot_store_t *store, zs_installation_store_io_t *out_io);

#endif
