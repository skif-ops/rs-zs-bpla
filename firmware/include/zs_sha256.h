#ifndef ZS_SHA256_H
#define ZS_SHA256_H

#include <stddef.h>
#include <stdint.h>

#define ZS_SHA256_BLOCK_BYTES 64u
#define ZS_SHA256_DIGEST_BYTES 32u

typedef struct {
  uint32_t state[8];
  uint64_t total_bytes;
  uint8_t block[ZS_SHA256_BLOCK_BYTES];
  size_t block_size;
} zs_sha256_t;

void zs_sha256_init(zs_sha256_t *ctx);
void zs_sha256_update(zs_sha256_t *ctx, const void *data, size_t size);
void zs_sha256_final(zs_sha256_t *ctx, uint8_t digest[ZS_SHA256_DIGEST_BYTES]);
void zs_sha256_digest(const void *data, size_t size, uint8_t digest[ZS_SHA256_DIGEST_BYTES]);

#endif
