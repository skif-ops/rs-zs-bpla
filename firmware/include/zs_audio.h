#ifndef ZS_AUDIO_H
#define ZS_AUDIO_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#define ZS_AUDIO_CHANNELS 4u

typedef struct { int16_t *storage; size_t frames_capacity; size_t write_frame; uint64_t total_frames; uint32_t sample_rate; } zs_audio_ring_t;
void zs_audio_ring_init(zs_audio_ring_t*r,int16_t*storage,size_t frames_capacity,uint32_t sample_rate);
void zs_audio_ring_push(zs_audio_ring_t*r,const int16_t frame[ZS_AUDIO_CHANNELS]);
bool zs_audio_ring_copy_mono(const zs_audio_ring_t*r,uint64_t end_sample,uint32_t count,int16_t*out,unsigned channel);
bool zs_audio_ring_copy_average(const zs_audio_ring_t*r,uint64_t end_sample,uint32_t count,int16_t*out);
#endif
