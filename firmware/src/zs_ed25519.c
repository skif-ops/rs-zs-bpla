#include "zs_ed25519.h"

#include <string.h>

/* ---- SHA-512 (FIPS 180-4) ---------------------------------------------------------------- */

static const uint64_t K512[80] = {
  0x428a2f98d728ae22ull, 0x7137449123ef65cdull, 0xb5c0fbcfec4d3b2full, 0xe9b5dba58189dbbcull, 0x3956c25bf348b538ull,
  0x59f111f1b605d019ull, 0x923f82a4af194f9bull, 0xab1c5ed5da6d8118ull, 0xd807aa98a3030242ull, 0x12835b0145706fbeull,
  0x243185be4ee4b28cull, 0x550c7dc3d5ffb4e2ull, 0x72be5d74f27b896full, 0x80deb1fe3b1696b1ull, 0x9bdc06a725c71235ull,
  0xc19bf174cf692694ull, 0xe49b69c19ef14ad2ull, 0xefbe4786384f25e3ull, 0x0fc19dc68b8cd5b5ull, 0x240ca1cc77ac9c65ull,
  0x2de92c6f592b0275ull, 0x4a7484aa6ea6e483ull, 0x5cb0a9dcbd41fbd4ull, 0x76f988da831153b5ull, 0x983e5152ee66dfabull,
  0xa831c66d2db43210ull, 0xb00327c898fb213full, 0xbf597fc7beef0ee4ull, 0xc6e00bf33da88fc2ull, 0xd5a79147930aa725ull,
  0x06ca6351e003826full, 0x142929670a0e6e70ull, 0x27b70a8546d22ffcull, 0x2e1b21385c26c926ull, 0x4d2c6dfc5ac42aedull,
  0x53380d139d95b3dfull, 0x650a73548baf63deull, 0x766a0abb3c77b2a8ull, 0x81c2c92e47edaee6ull, 0x92722c851482353bull,
  0xa2bfe8a14cf10364ull, 0xa81a664bbc423001ull, 0xc24b8b70d0f89791ull, 0xc76c51a30654be30ull, 0xd192e819d6ef5218ull,
  0xd69906245565a910ull, 0xf40e35855771202aull, 0x106aa07032bbd1b8ull, 0x19a4c116b8d2d0c8ull, 0x1e376c085141ab53ull,
  0x2748774cdf8eeb99ull, 0x34b0bcb5e19b48a8ull, 0x391c0cb3c5c95a63ull, 0x4ed8aa4ae3418acbull, 0x5b9cca4f7763e373ull,
  0x682e6ff3d6b2b8a3ull, 0x748f82ee5defb2fcull, 0x78a5636f43172f60ull, 0x84c87814a1f0ab72ull, 0x8cc702081a6439ecull,
  0x90befffa23631e28ull, 0xa4506cebde82bde9ull, 0xbef9a3f7b2c67915ull, 0xc67178f2e372532bull, 0xca273eceea26619cull,
  0xd186b8c721c0c207ull, 0xeada7dd6cde0eb1eull, 0xf57d4f7fee6ed178ull, 0x06f067aa72176fbaull, 0x0a637dc5a2c898a6ull,
  0x113f9804bef90daeull, 0x1b710b35131c471bull, 0x28db77f523047d84ull, 0x32caab7b40c72493ull, 0x3c9ebe0a15c9bebcull,
  0x431d67c49c100d4cull, 0x4cc5d4becb3e42b6ull, 0x597f299cfc657e2aull, 0x5fcb6fab3ad6faecull, 0x6c44198c4a475817ull};

static uint64_t rotr64(uint64_t x, unsigned n) { return (x >> n) | (x << (64u - n)); }
static uint64_t load64(const uint8_t *p) { uint64_t v = 0u; for (unsigned i = 0u; i < 8u; i++) v = (v << 8) | p[i]; return v; }
static void store64(uint8_t *p, uint64_t v) { for (unsigned i = 0u; i < 8u; i++) p[i] = (uint8_t)(v >> (56u - 8u * i)); }

static void sha512_block(uint64_t h[8], const uint8_t block[128]) {
  uint64_t w[80], a, b, c, d, e, f, g, hh;
  for (unsigned i = 0u; i < 16u; i++) w[i] = load64(block + 8u * i);
  for (unsigned i = 16u; i < 80u; i++) {
    const uint64_t s0 = rotr64(w[i - 15], 1) ^ rotr64(w[i - 15], 8) ^ (w[i - 15] >> 7);
    const uint64_t s1 = rotr64(w[i - 2], 19) ^ rotr64(w[i - 2], 61) ^ (w[i - 2] >> 6);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  a = h[0]; b = h[1]; c = h[2]; d = h[3]; e = h[4]; f = h[5]; g = h[6]; hh = h[7];
  for (unsigned i = 0u; i < 80u; i++) {
    const uint64_t S1 = rotr64(e, 14) ^ rotr64(e, 18) ^ rotr64(e, 41);
    const uint64_t ch = (e & f) ^ (~e & g);
    const uint64_t t1 = hh + S1 + ch + K512[i] + w[i];
    const uint64_t S0 = rotr64(a, 28) ^ rotr64(a, 34) ^ rotr64(a, 39);
    const uint64_t maj = (a & b) ^ (a & c) ^ (b & c);
    const uint64_t t2 = S0 + maj;
    hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
  }
  h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
}

void zs_sha512(const uint8_t *data, size_t len, uint8_t out[ZS_SHA512_DIGEST_BYTES]) {
  uint64_t h[8] = {0x6a09e667f3bcc908ull, 0xbb67ae8584caa73bull, 0x3c6ef372fe94f82bull, 0xa54ff53a5f1d36f1ull,
                   0x510e527fade682d1ull, 0x9b05688c2b3e6c1full, 0x1f83d9abfb41bd6bull, 0x5be0cd19137e2179ull};
  uint8_t block[128];
  size_t i = 0u;
  while (len - i >= 128u) { sha512_block(h, data + i); i += 128u; }
  const size_t rest = len - i;
  memset(block, 0, sizeof(block));
  memcpy(block, data + i, rest);
  block[rest] = 0x80u;
  if (rest >= 112u) { sha512_block(h, block); memset(block, 0, sizeof(block)); }
  store64(block + 120, (uint64_t)len << 3);      /* messages far below 2^61 bytes: the high length word stays 0 */
  sha512_block(h, block);
  for (unsigned j = 0u; j < 8u; j++) store64(out + 8u * j, h[j]);
}

/* ---- field / group arithmetic (TweetNaCl style, 2^255 - 19) ------------------------------ */

typedef int64_t gf[16];

static const gf gf0 = {0};
static const gf gf1 = {1};
static const gf D = {0x78a3, 0x1359, 0x4dca, 0x75eb, 0xd8ab, 0x4141, 0x0a4d, 0x0070, 0xe898, 0x7779, 0x4079, 0x8cc7, 0xfe73, 0x2b6f, 0x6cee, 0x5203};
static const gf D2 = {0xf159, 0x26b2, 0x9b94, 0xebd6, 0xb156, 0x8283, 0x149a, 0x00e0, 0xd130, 0xeef3, 0x80f2, 0x198e, 0xfce7, 0x56df, 0xd9dc, 0x2406};
static const gf X = {0xd51a, 0x8f25, 0x2d60, 0xc956, 0xa7b2, 0x9525, 0xc760, 0x692c, 0xdc5c, 0xfdd6, 0xe231, 0xc0a4, 0x53fe, 0xcd6e, 0x36d3, 0x2169};
static const gf Y = {0x6658, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666, 0x6666};
static const gf I = {0xa0b0, 0x4a0e, 0x1b27, 0xc4ee, 0xe478, 0xad2f, 0x1806, 0x2f43, 0xd7a7, 0x3dfb, 0x0099, 0x2b4d, 0xdf0b, 0x4fc1, 0x2480, 0x2b83};
static const uint8_t L[32] = {0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10};

static void set25519(gf r, const gf a) { for (unsigned i = 0u; i < 16u; i++) r[i] = a[i]; }

static void car25519(gf o) {
  for (unsigned i = 0u; i < 16u; i++) {
    o[i] += (int64_t)1 << 16;
    const int64_t c = o[i] >> 16;
    o[(i + 1u) * (i < 15u)] += c - 1 + 37 * (c - 1) * (i == 15u);
    o[i] -= c << 16;
  }
}

static void sel25519(gf p, gf q, int b) {
  const int64_t c = ~(int64_t)(b - 1);
  for (unsigned i = 0u; i < 16u; i++) { const int64_t t = c & (p[i] ^ q[i]); p[i] ^= t; q[i] ^= t; }
}

static void pack25519(uint8_t *o, const gf n) {
  gf m, t;
  set25519(t, n);
  car25519(t); car25519(t); car25519(t);
  for (unsigned j = 0u; j < 2u; j++) {
    m[0] = t[0] - 0xffed;
    for (unsigned i = 1u; i < 15u; i++) { m[i] = t[i] - 0xffff - ((m[i - 1] >> 16) & 1); m[i - 1] &= 0xffff; }
    m[15] = t[15] - 0x7fff - ((m[14] >> 16) & 1);
    const int b = (int)((m[15] >> 16) & 1);
    m[14] &= 0xffff;
    sel25519(t, m, 1 - b);
  }
  for (unsigned i = 0u; i < 16u; i++) { o[2u * i] = (uint8_t)(t[i] & 0xff); o[2u * i + 1u] = (uint8_t)(t[i] >> 8); }
}

static int verify32(const uint8_t *a, const uint8_t *b) {
  unsigned d = 0u;
  for (unsigned i = 0u; i < 32u; i++) d |= (unsigned)(a[i] ^ b[i]);
  return (int)((1u & ((d - 1u) >> 8)) - 1u);   /* 0 when equal, -1 otherwise */
}

static int neq25519(const gf a, const gf b) { uint8_t c[32], d[32]; pack25519(c, a); pack25519(d, b); return verify32(c, d); }
static uint8_t par25519(const gf a) { uint8_t d[32]; pack25519(d, a); return d[0] & 1u; }

static void unpack25519(gf o, const uint8_t *n) {
  for (unsigned i = 0u; i < 16u; i++) o[i] = n[2u * i] + ((int64_t)n[2u * i + 1u] << 8);
  o[15] &= 0x7fff;
}

static void A(gf o, const gf a, const gf b) { for (unsigned i = 0u; i < 16u; i++) o[i] = a[i] + b[i]; }
static void Z(gf o, const gf a, const gf b) { for (unsigned i = 0u; i < 16u; i++) o[i] = a[i] - b[i]; }

static void M(gf o, const gf a, const gf b) {
  int64_t t[31];
  for (unsigned i = 0u; i < 31u; i++) t[i] = 0;
  for (unsigned i = 0u; i < 16u; i++) for (unsigned j = 0u; j < 16u; j++) t[i + j] += a[i] * b[j];
  for (unsigned i = 0u; i < 15u; i++) t[i] += 38 * t[i + 16u];
  for (unsigned i = 0u; i < 16u; i++) o[i] = t[i];
  car25519(o); car25519(o);
}

static void S(gf o, const gf a) { M(o, a, a); }

static void inv25519(gf o, const gf i) {
  gf c;
  set25519(c, i);
  for (int a = 253; a >= 0; a--) { S(c, c); if (a != 2 && a != 4) M(c, c, i); }
  set25519(o, c);
}

static void pow2523(gf o, const gf i) {
  gf c;
  set25519(c, i);
  for (int a = 250; a >= 0; a--) { S(c, c); if (a != 1) M(c, c, i); }
  set25519(o, c);
}

static void add(gf p[4], gf q[4]) {
  gf a, b, c, d, t, e, f, g, h;
  Z(a, p[1], p[0]); Z(t, q[1], q[0]); M(a, a, t);
  A(b, p[0], p[1]); A(t, q[0], q[1]); M(b, b, t);
  M(c, p[3], q[3]); M(c, c, D2);
  M(d, p[2], q[2]); A(d, d, d);
  Z(e, b, a); Z(f, d, c); A(g, d, c); A(h, b, a);
  M(p[0], e, f); M(p[1], h, g); M(p[2], g, f); M(p[3], e, h);
}

static void cswap(gf p[4], gf q[4], uint8_t b) { for (unsigned i = 0u; i < 4u; i++) sel25519(p[i], q[i], (int)b); }

static void pack(uint8_t *r, gf p[4]) {
  gf tx, ty, zi;
  inv25519(zi, p[2]);
  M(tx, p[0], zi); M(ty, p[1], zi);
  pack25519(r, ty);
  r[31] ^= (uint8_t)(par25519(tx) << 7);
}

static void scalarmult(gf p[4], gf q[4], const uint8_t *s) {
  set25519(p[0], gf0); set25519(p[1], gf1); set25519(p[2], gf1); set25519(p[3], gf0);
  for (int i = 255; i >= 0; --i) {
    const uint8_t b = (uint8_t)((s[i / 8] >> (i & 7)) & 1u);
    cswap(p, q, b);
    add(q, p);
    add(p, p);
    cswap(p, q, b);
  }
}

static void scalarbase(gf p[4], const uint8_t *s) {
  gf q[4];
  set25519(q[0], X); set25519(q[1], Y); set25519(q[2], gf1); M(q[3], X, Y);
  scalarmult(p, q, s);
}

static int unpackneg(gf r[4], const uint8_t p[32]) {
  gf t, chk, num, den, den2, den4, den6;
  set25519(r[2], gf1);
  unpack25519(r[1], p);
  S(num, r[1]);
  M(den, num, D);
  Z(num, num, r[2]);
  A(den, r[2], den);
  S(den2, den); S(den4, den2); M(den6, den4, den2);
  M(t, den6, num); M(t, t, den);
  pow2523(t, t);
  M(t, t, num); M(t, t, den); M(t, t, den); M(r[0], t, den);
  S(chk, r[0]); M(chk, chk, den);
  if (neq25519(chk, num)) M(r[0], r[0], I);
  S(chk, r[0]); M(chk, chk, den);
  if (neq25519(chk, num)) return -1;
  if (par25519(r[0]) == (p[31] >> 7)) Z(r[0], gf0, r[0]);
  M(r[3], r[0], r[1]);
  return 0;
}

static void modL(uint8_t *r, int64_t x[64]) {
  int64_t carry;
  int i, j;
  for (i = 63; i >= 32; --i) {
    carry = 0;
    for (j = i - 32; j < i - 12; ++j) {
      x[j] += carry - 16 * x[i] * L[j - (i - 32)];
      carry = (x[j] + 128) >> 8;
      x[j] -= carry << 8;
    }
    x[j] += carry;
    x[i] = 0;
  }
  carry = 0;
  for (j = 0; j < 32; ++j) { x[j] += carry - (x[31] >> 4) * L[j]; carry = x[j] >> 8; x[j] &= 255; }
  for (j = 0; j < 32; ++j) x[j] -= carry * L[j];
  for (i = 0; i < 32; ++i) { x[i + 1] += x[i] >> 8; r[i] = (uint8_t)(x[i] & 255); }
}

static void reduce(uint8_t *r) {
  int64_t x[64];
  for (unsigned i = 0u; i < 64u; i++) x[i] = (int64_t)r[i];
  for (unsigned i = 0u; i < 64u; i++) r[i] = 0u;
  modL(r, x);
}

/* S < L (little-endian compare against the group order): non-canonical signatures are rejected (RFC 8032 §5.1.7). */
static bool scalar_canonical(const uint8_t s[32]) {
  for (int i = 31; i >= 0; i--) {
    if (s[i] < L[i]) return true;
    if (s[i] > L[i]) return false;
  }
  return false;
}

bool zs_ed25519_verify(const uint8_t public_key[32], const uint8_t *message, size_t message_len, const uint8_t signature[64]) {
  gf p[4], q[4];
  uint8_t h[64], t[32], head[64];
  if (!public_key || !signature || (!message && message_len != 0u)) return false;
  if (!scalar_canonical(signature + 32)) return false;
  if (unpackneg(q, public_key)) return false;
  /* h = SHA-512(R || A || M), streamed: the 64-byte prefix as one block, then the message with its own padding */
  {
    /* one-shot over a small stack copy when the message is short; otherwise stream by re-running the block function */
    uint8_t block[128];
    uint64_t hs[8] = {0x6a09e667f3bcc908ull, 0xbb67ae8584caa73bull, 0x3c6ef372fe94f82bull, 0xa54ff53a5f1d36f1ull,
                      0x510e527fade682d1ull, 0x9b05688c2b3e6c1full, 0x1f83d9abfb41bd6bull, 0x5be0cd19137e2179ull};
    size_t i = 0u, fill = 64u;
    memcpy(head, signature, 32u); memcpy(head + 32, public_key, 32u);
    memcpy(block, head, 64u);
    /* fill the first block with the start of the message */
    while (fill < 128u && i < message_len) block[fill++] = message[i++];
    if (fill == 128u) { sha512_block(hs, block); fill = 0u; }
    while (message_len - i >= 128u && fill == 0u) { sha512_block(hs, message + i); i += 128u; }
    while (i < message_len) { block[fill++] = message[i++]; if (fill == 128u) { sha512_block(hs, block); fill = 0u; } }
    memset(block + fill, 0, 128u - fill);
    block[fill] = 0x80u;
    if (fill >= 112u) { sha512_block(hs, block); memset(block, 0, 128u); }
    store64(block + 120, (uint64_t)(64u + message_len) << 3);
    sha512_block(hs, block);
    for (unsigned j = 0u; j < 8u; j++) store64(h + 8u * j, hs[j]);
  }
  reduce(h);
  scalarmult(p, q, h);          /* h * (-A) */
  scalarbase(q, signature + 32); /* S * B */
  add(p, q);                     /* S*B - h*A == R when the signature is valid */
  pack(t, p);
  return verify32(signature, t) == 0;
}
