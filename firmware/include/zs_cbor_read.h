#ifndef ZS_CBOR_READ_H
#define ZS_CBOR_READ_H
/* Minimal strict CBOR reader (definite lengths, canonical integer encodings) for BLE payloads. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct { const uint8_t *buf; size_t len, pos; } zs_cbor_reader_t;

void zs_cbor_reader_init(zs_cbor_reader_t *r, const uint8_t *buf, size_t len);
bool zs_cbor_read_map(zs_cbor_reader_t *r, uint32_t *count);
bool zs_cbor_read_uint(zs_cbor_reader_t *r, uint64_t *v);
bool zs_cbor_read_int(zs_cbor_reader_t *r, int64_t *v);      /* major 0 or 1 */
bool zs_cbor_read_bool(zs_cbor_reader_t *r, bool *v);
bool zs_cbor_read_bytes(zs_cbor_reader_t *r, const uint8_t **data, size_t *n);
bool zs_cbor_read_text(zs_cbor_reader_t *r, char *dst, size_t cap); /* NUL-terminated copy */
bool zs_cbor_reader_at_end(const zs_cbor_reader_t *r);

#endif
