#ifndef ZS_NOR_EVENT_OUTBOX_H
#define ZS_NOR_EVENT_OUTBOX_H

#include "zs_event_outbox.h"
#include "zs_nor.h"

#include <stdbool.h>
#include <stdint.h>

typedef struct {
  zs_nor_t *nor;
  uint32_t base_address;
  uint16_t slot_count;
} zs_nor_event_outbox_adapter_t;

/*
 * Bind the portable outbox to a dedicated NOR partition. Every logical slot
 * owns one complete physical erase block so reclaim cannot erase a neighbour.
 * The partition base must be erase-aligned and must not overlap other users.
 */
bool zs_nor_event_outbox_io_init(
    zs_nor_event_outbox_adapter_t *adapter,
    zs_nor_t *nor,
    uint32_t base_address,
    uint16_t slot_count,
    zs_event_outbox_io_t *out_io);

#endif
