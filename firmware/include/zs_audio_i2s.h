#ifndef ZS_AUDIO_I2S_H
#define ZS_AUDIO_I2S_H

#include <stddef.h>
#include <stdint.h>

/* Convert two synchronous stereo I2S streams to MIC0..MIC3 order. */
void zs_i2s_unpack_4ch(const uint32_t *sai_a,
                       const uint32_t *sai_b,
                       int32_t *dst_interleaved,
                       size_t frames);

#endif
