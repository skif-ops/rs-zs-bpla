#ifndef ZS_CBOR_H
#define ZS_CBOR_H
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
typedef struct { uint8_t *buf; size_t cap, len; bool error; } zs_cbor_t;
void zs_cbor_init(zs_cbor_t *c, uint8_t *buf, size_t cap);
void zs_cbor_map(zs_cbor_t *c, uint32_t count);
void zs_cbor_uint(zs_cbor_t *c, uint64_t v);
void zs_cbor_int(zs_cbor_t *c, int64_t v);
void zs_cbor_bool(zs_cbor_t *c, bool v);
void zs_cbor_bytes(zs_cbor_t *c, const void *data, size_t n);
#endif
