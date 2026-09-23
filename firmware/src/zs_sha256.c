#include "zs_sha256.h"

#include <string.h>

static const uint32_t round_constants[64] = {
    UINT32_C(0x428a2f98), UINT32_C(0x71374491), UINT32_C(0xb5c0fbcf), UINT32_C(0xe9b5dba5),
    UINT32_C(0x3956c25b), UINT32_C(0x59f111f1), UINT32_C(0x923f82a4), UINT32_C(0xab1c5ed5),
    UINT32_C(0xd807aa98), UINT32_C(0x12835b01), UINT32_C(0x243185be), UINT32_C(0x550c7dc3),
    UINT32_C(0x72be5d74), UINT32_C(0x80deb1fe), UINT32_C(0x9bdc06a7), UINT32_C(0xc19bf174),
    UINT32_C(0xe49b69c1), UINT32_C(0xefbe4786), UINT32_C(0x0fc19dc6), UINT32_C(0x240ca1cc),
    UINT32_C(0x2de92c6f), UINT32_C(0x4a7484aa), UINT32_C(0x5cb0a9dc), UINT32_C(0x76f988da),
    UINT32_C(0x983e5152), UINT32_C(0xa831c66d), UINT32_C(0xb00327c8), UINT32_C(0xbf597fc7),
    UINT32_C(0xc6e00bf3), UINT32_C(0xd5a79147), UINT32_C(0x06ca6351), UINT32_C(0x14292967),
    UINT32_C(0x27b70a85), UINT32_C(0x2e1b2138), UINT32_C(0x4d2c6dfc), UINT32_C(0x53380d13),
    UINT32_C(0x650a7354), UINT32_C(0x766a0abb), UINT32_C(0x81c2c92e), UINT32_C(0x92722c85),
    UINT32_C(0xa2bfe8a1), UINT32_C(0xa81a664b), UINT32_C(0xc24b8b70), UINT32_C(0xc76c51a3),
    UINT32_C(0xd192e819), UINT32_C(0xd6990624), UINT32_C(0xf40e3585), UINT32_C(0x106aa070),
    UINT32_C(0x19a4c116), UINT32_C(0x1e376c08), UINT32_C(0x2748774c), UINT32_C(0x34b0bcb5),
    UINT32_C(0x391c0cb3), UINT32_C(0x4ed8aa4a), UINT32_C(0x5b9cca4f), UINT32_C(0x682e6ff3),
    UINT32_C(0x748f82ee), UINT32_C(0x78a5636f), UINT32_C(0x84c87814), UINT32_C(0x8cc70208),
    UINT32_C(0x90befffa), UINT32_C(0xa4506ceb), UINT32_C(0xbef9a3f7), UINT32_C(0xc67178f2)};

static uint32_t rotate_right(uint32_t value, unsigned shift) {
  return (value >> shift) | (value << (32u - shift));
}

static uint32_t load_be32(const uint8_t *p) {
  return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
         ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

static void store_be32(uint8_t *p, uint32_t value) {
  p[0] = (uint8_t)(value >> 24);
  p[1] = (uint8_t)(value >> 16);
  p[2] = (uint8_t)(value >> 8);
  p[3] = (uint8_t)value;
}

static void transform(zs_sha256_t *ctx, const uint8_t block[ZS_SHA256_BLOCK_BYTES]) {
  uint32_t words[64];
  for (unsigned i = 0u; i < 16u; i++) words[i] = load_be32(&block[i * 4u]);
  for (unsigned i = 16u; i < 64u; i++) {
    const uint32_t s0 = rotate_right(words[i - 15u], 7u) ^
                        rotate_right(words[i - 15u], 18u) ^ (words[i - 15u] >> 3);
    const uint32_t s1 = rotate_right(words[i - 2u], 17u) ^
                        rotate_right(words[i - 2u], 19u) ^ (words[i - 2u] >> 10);
    words[i] = words[i - 16u] + s0 + words[i - 7u] + s1;
  }

  uint32_t a = ctx->state[0];
  uint32_t b = ctx->state[1];
  uint32_t c = ctx->state[2];
  uint32_t d = ctx->state[3];
  uint32_t e = ctx->state[4];
  uint32_t f = ctx->state[5];
  uint32_t g = ctx->state[6];
  uint32_t h = ctx->state[7];
  for (unsigned i = 0u; i < 64u; i++) {
    const uint32_t sum1 = rotate_right(e, 6u) ^ rotate_right(e, 11u) ^ rotate_right(e, 25u);
    const uint32_t choose = (e & f) ^ ((~e) & g);
    const uint32_t temp1 = h + sum1 + choose + round_constants[i] + words[i];
    const uint32_t sum0 = rotate_right(a, 2u) ^ rotate_right(a, 13u) ^ rotate_right(a, 22u);
    const uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
    const uint32_t temp2 = sum0 + majority;
    h = g;
    g = f;
    f = e;
    e = d + temp1;
    d = c;
    c = b;
    b = a;
    a = temp1 + temp2;
  }
  ctx->state[0] += a;
  ctx->state[1] += b;
  ctx->state[2] += c;
  ctx->state[3] += d;
  ctx->state[4] += e;
  ctx->state[5] += f;
  ctx->state[6] += g;
  ctx->state[7] += h;
}

void zs_sha256_init(zs_sha256_t *ctx) {
  if (ctx == NULL) return;
  ctx->state[0] = UINT32_C(0x6a09e667);
  ctx->state[1] = UINT32_C(0xbb67ae85);
  ctx->state[2] = UINT32_C(0x3c6ef372);
  ctx->state[3] = UINT32_C(0xa54ff53a);
  ctx->state[4] = UINT32_C(0x510e527f);
  ctx->state[5] = UINT32_C(0x9b05688c);
  ctx->state[6] = UINT32_C(0x1f83d9ab);
  ctx->state[7] = UINT32_C(0x5be0cd19);
  ctx->total_bytes = 0u;
  ctx->block_size = 0u;
  memset(ctx->block, 0, sizeof(ctx->block));
}

void zs_sha256_update(zs_sha256_t *ctx, const void *data, size_t size) {
  const uint8_t *input = data;
  if (ctx == NULL || (data == NULL && size != 0u)) return;
  ctx->total_bytes += size;
  while (size > 0u) {
    const size_t available = ZS_SHA256_BLOCK_BYTES - ctx->block_size;
    const size_t take = size < available ? size : available;
    memcpy(&ctx->block[ctx->block_size], input, take);
    ctx->block_size += take;
    input += take;
    size -= take;
    if (ctx->block_size == ZS_SHA256_BLOCK_BYTES) {
      transform(ctx, ctx->block);
      ctx->block_size = 0u;
    }
  }
}

void zs_sha256_final(zs_sha256_t *ctx, uint8_t digest[ZS_SHA256_DIGEST_BYTES]) {
  if (ctx == NULL || digest == NULL) return;
  const uint64_t total_bits = ctx->total_bytes * UINT64_C(8);
  ctx->block[ctx->block_size++] = 0x80u;
  if (ctx->block_size > 56u) {
    memset(&ctx->block[ctx->block_size], 0, ZS_SHA256_BLOCK_BYTES - ctx->block_size);
    transform(ctx, ctx->block);
    ctx->block_size = 0u;
  }
  memset(&ctx->block[ctx->block_size], 0, 56u - ctx->block_size);
  for (unsigned i = 0u; i < 8u; i++) {
    ctx->block[63u - i] = (uint8_t)(total_bits >> (i * 8u));
  }
  transform(ctx, ctx->block);
  for (unsigned i = 0u; i < 8u; i++) store_be32(&digest[i * 4u], ctx->state[i]);
  memset(ctx, 0, sizeof(*ctx));
}

void zs_sha256_digest(const void *data, size_t size, uint8_t digest[ZS_SHA256_DIGEST_BYTES]) {
  zs_sha256_t ctx;
  if (digest == NULL || (data == NULL && size != 0u)) return;
  zs_sha256_init(&ctx);
  zs_sha256_update(&ctx, data, size);
  zs_sha256_final(&ctx, digest);
}

void zs_hmac_sha256(const uint8_t *key, size_t key_len, const void *data, size_t size, uint8_t mac[ZS_SHA256_DIGEST_BYTES]) {
  uint8_t k[ZS_SHA256_BLOCK_BYTES], pad[ZS_SHA256_BLOCK_BYTES], inner[ZS_SHA256_DIGEST_BYTES];
  zs_sha256_t ctx;
  if (mac == NULL || (key == NULL && key_len != 0u) || (data == NULL && size != 0u)) return;
  memset(k, 0, sizeof(k));
  if (key_len > ZS_SHA256_BLOCK_BYTES) zs_sha256_digest(key, key_len, k);
  else if (key_len) memcpy(k, key, key_len);
  for (size_t i = 0u; i < ZS_SHA256_BLOCK_BYTES; i++) pad[i] = (uint8_t)(k[i] ^ 0x36u);
  zs_sha256_init(&ctx); zs_sha256_update(&ctx, pad, sizeof(pad)); zs_sha256_update(&ctx, data, size); zs_sha256_final(&ctx, inner);
  for (size_t i = 0u; i < ZS_SHA256_BLOCK_BYTES; i++) pad[i] = (uint8_t)(k[i] ^ 0x5cu);
  zs_sha256_init(&ctx); zs_sha256_update(&ctx, pad, sizeof(pad)); zs_sha256_update(&ctx, inner, sizeof(inner)); zs_sha256_final(&ctx, mac);
  memset(k, 0, sizeof(k)); memset(pad, 0, sizeof(pad));
}

bool zs_sha256_equal(const uint8_t *a, const uint8_t *b, size_t len) {
  uint8_t d = 0u;
  if (a == NULL || b == NULL) return false;
  for (size_t i = 0u; i < len; i++) d |= (uint8_t)(a[i] ^ b[i]);
  return d == 0u;
}
