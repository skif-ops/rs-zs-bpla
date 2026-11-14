/* Ed25519 verification and SHA-512 against `cryptography` (Python) vectors; negative cases. */
#include "zs_ed25519.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static size_t unhex(const char *h, uint8_t *out, size_t cap) {
  const size_t n = strlen(h) / 2u;
  assert(n <= cap);
  for (size_t i = 0u; i < n; i++) { unsigned v; assert(sscanf(h + 2u * i, "%2x", &v) == 1); out[i] = (uint8_t)v; }
  return n;
}

static void check_sha(const uint8_t *m, size_t n, const char *hex) {
  uint8_t d[64], e[64];
  zs_sha512(m, n, d);
  unhex(hex, e, 64u);
  assert(memcmp(d, e, 64u) == 0);
}

static void test_sha512(void) {
  uint8_t buf[512];
  check_sha((const uint8_t *)"abc", 3u, "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f");
  memset(buf, 'a', 112u);
  check_sha(buf, 111u, "fa9121c7b32b9e01733d034cfc78cbf67f926c7ed83e82200ef86818196921760b4beff48404df811b953828274461673c68d04e297b0eb7b2b4d60fc6b566a2");
  check_sha(buf, 112u, "c01d080efd492776a1c43bd23dd99d0a2e626d481e16782e75d54c2503b5dc32bd05f0f1ba33e568b88fd2d970929b719ecbb152f58f130a407c8830604b70ca");
  for (unsigned i = 0u; i < 512u; i++) buf[i] = (uint8_t)i;
  check_sha(buf, 512u, "edb9bed721aa6a5f6fbc6619d3a3c2be3d043043f05a9aebc7b1197a2aa9c49a57d5ddd4674c1785785088d9f1ff42c797a02adc9b817a139a50970da6c99524");
  printf("sha512 ok\n");
}

typedef struct { const char *pk, *msg, *sig; } vector_t;

static void test_verify(void) {
  static const vector_t v[] = {
    {"03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8", "",
     "9ca53579530654d5c3df77089ef45eda613e2fedf670e96bedac4639504e5845ef4b95d5793077233dd16817b2532e9c5525872a73a4ad74b759369a9e05c102"},
    {"03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8", "6d75686f656420636f6d6d616e64",
     "4bc379dd6f3f52eb9320f6568d98bab3f17f659820ee6d90f82aa77c85c6c14d72571227181ec004c8515b4ff1b76a93d1649c59257f897109c3e72fc286c208"},
    {"0d7550754e0800a5d237eef5826035766b9b3e5a15868a940ab289958788e3b0",
     "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f505152535455565758595a5b5c5d5e5f606162636465666768696a6b6c6d6e6f707172737475767778797a7b7c7d7e7f808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9fa0a1a2a3a4a5a6a7a8a9aaabacadaeafb0b1b2b3b4b5b6b7b8b9babbbcbdbebfc0c1c2c3c4c5c6c7",
     "1ab35adc8788584b1fc28653529eb57e4063ea5170f6f01b3af07bc11215da20c305957c2b861c8cc89b703dfc3335daffd732654b2f6b9ad62b0fc405745a09"},
  };
  uint8_t pk[32], sig[64], msg[512];
  for (unsigned i = 0u; i < sizeof(v) / sizeof(v[0]); i++) {
    unhex(v[i].pk, pk, 32u); unhex(v[i].sig, sig, 64u);
    const size_t n = unhex(v[i].msg, msg, sizeof(msg));
    assert(zs_ed25519_verify(pk, msg, n, sig));
    /* a flipped message bit, a flipped signature bit, a flipped key bit: all rejected */
    if (n) { msg[0] ^= 1u; assert(!zs_ed25519_verify(pk, msg, n, sig)); msg[0] ^= 1u; }
    sig[5] ^= 1u; assert(!zs_ed25519_verify(pk, msg, n, sig)); sig[5] ^= 1u;
    sig[40] ^= 1u; assert(!zs_ed25519_verify(pk, msg, n, sig)); sig[40] ^= 1u;
    pk[3] ^= 1u; assert(!zs_ed25519_verify(pk, msg, n, sig)); pk[3] ^= 1u;
    assert(zs_ed25519_verify(pk, msg, n, sig));
  }
  /* 300-byte message: exercises the multi-block hashing path */
  {
    uint8_t m[300];
    memset(m, 7, sizeof(m));
    unhex("0020c7635fb087e3351e0ca5a9a6ad67e20a42f05383a42941331d58dc8861f2", pk, 32u);
    unhex("f47e256c90449671a40d0b0839c52923bd2b4ee40df7d076521b629905d788c8a8fd8c6ed39c5a00f7d4f72c8bddc8cade2c6f60a63265163dc5ba6e29be2401", sig, 64u);
    assert(zs_ed25519_verify(pk, m, sizeof(m), sig));
    assert(!zs_ed25519_verify(pk, m, sizeof(m) - 1u, sig));
  }
  /* non-canonical S (S + L) is rejected even though the group equation would still hold */
  {
    static const uint8_t L[32] = {0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10};
    unhex(v[0].pk, pk, 32u); unhex(v[0].sig, sig, 64u);
    unsigned carry = 0u;
    for (unsigned i = 0u; i < 32u; i++) { const unsigned s = sig[32u + i] + L[i] + carry; sig[32u + i] = (uint8_t)s; carry = s >> 8; }
    assert(!zs_ed25519_verify(pk, msg, 0u, sig));
  }
  /* a public key that is not on the curve, and a zero/garbage signature */
  {
    memset(pk, 0xff, 32u); pk[31] = 0x7f;
    unhex(v[0].sig, sig, 64u);
    assert(!zs_ed25519_verify(pk, msg, 0u, sig));
    unhex(v[0].pk, pk, 32u); memset(sig, 0, 64u);
    assert(!zs_ed25519_verify(pk, msg, 0u, sig));
  }
  printf("ed25519 verify ok\n");
}

int main(void) {
  test_sha512();
  test_verify();
  printf("ed25519 tests passed\n");
  return 0;
}
