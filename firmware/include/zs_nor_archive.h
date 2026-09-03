#ifndef ZS_NOR_ARCHIVE_H
#define ZS_NOR_ARCHIVE_H

#include "zs_archive.h"
#include "zs_nor.h"

#include <stdbool.h>

typedef struct {
  zs_nor_t *nor;
} zs_nor_archive_adapter_t;

bool zs_nor_archive_storage_init(zs_nor_archive_adapter_t *adapter,
                                 zs_nor_t *nor,
                                 zs_archive_storage_t *out_storage);

#endif
