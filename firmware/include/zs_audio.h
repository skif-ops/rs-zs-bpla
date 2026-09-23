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
/* True when [end_sample-count, end_sample) is still inside the ring. */
bool zs_audio_ring_range_ok(const zs_audio_ring_t*r,uint64_t end_sample,uint32_t count);
/* Sample `i` (0..count-1) of channel `ch` in that range; no checks (call range_ok first). */
static inline int16_t zs_audio_ring_at(const zs_audio_ring_t*r,uint64_t end_sample,uint32_t count,uint32_t i,unsigned ch){return r->storage[(size_t)((end_sample-count+i)%r->frames_capacity)*ZS_AUDIO_CHANNELS+ch];}
bool zs_audio_ring_copy_average(const zs_audio_ring_t*r,uint64_t end_sample,uint32_t count,int16_t*out);
#endif
