#include "zs_audio_i2s.h"

static int32_t sample24(uint32_t slot)
{
    return ((int32_t)slot) >> 8;
}

void zs_i2s_unpack_4ch(const uint32_t *a,
                       const uint32_t *b,
                       int32_t *dst,
                       size_t frames)
{
    if (!a || !b || !dst) return;
    for (size_t i = 0; i < frames; ++i) {
        dst[4U * i + 0U] = sample24(a[2U * i + 0U]);
        dst[4U * i + 1U] = sample24(a[2U * i + 1U]);
        dst[4U * i + 2U] = sample24(b[2U * i + 0U]);
        dst[4U * i + 3U] = sample24(b[2U * i + 1U]);
    }
}
