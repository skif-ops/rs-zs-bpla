#ifndef ZS_PDM_CAPTURE_H
#define ZS_PDM_CAPTURE_H

/*
 * Four-channel PDM capture through MDF1 (STM32U585) with one circular GPDMA
 * transfer per channel.  The HAL layer owns the DMA buffers and calls
 * zs_pdm_capture_on_dma_half / _on_dma_full from the ISR; a task calls
 * zs_pdm_capture_process to convert the finished half into int16 frames,
 * push them into the audio ring and advance the monotonic sample counter
 * used by zs_time / zs_pps_sync.
 *
 * Buffer layout: per channel `2 * block_samples` int32 words (MDF output is
 * 24-bit left-aligned in 32-bit), first half = block 0, second half = block 1.
 * All four channels use the same block size and are started synchronously by
 * the MDF driver, so block boundaries line up across channels; the lag
 * self-test below verifies that on the bench with a common acoustic source.
 *
 * Portable/host only: no HAL calls, ISR-safe flag handling with volatile.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "zs_audio.h"

#define ZS_PDM_CHANNELS ZS_AUDIO_CHANNELS
#define ZS_PDM_MAX_BLOCK_SAMPLES 1024u

typedef struct {
  uint32_t sample_rate;   /* 32000 for EVT */
  uint32_t block_samples; /* samples per channel per DMA half, <= ZS_PDM_MAX_BLOCK_SAMPLES */
  uint8_t shift_bits;     /* right shift from 32-bit MDF word to int16 (16 = keep top 16 bits) */
  int32_t dc_alpha_q15;   /* one-pole DC blocker coefficient in Q15 (0 = off), typical 32440 (~0.99) */
} zs_pdm_config_t;

typedef struct {
  zs_pdm_config_t cfg;
  const int32_t *dma[ZS_PDM_CHANNELS]; /* per-channel double buffers, 2*block_samples words */
  zs_audio_ring_t *ring;
  volatile uint8_t pending_mask; /* bit0 = block 0 ready, bit1 = block 1 ready */
  volatile uint8_t last_ready;   /* which block became ready most recently */
  volatile uint8_t ready_seen;   /* at least one block has been marked ready */
  uint8_t next_block;            /* block expected by process() in order */
  uint64_t samples_total;        /* monotonic per-channel sample counter (frames pushed) */
  uint32_t blocks_processed;
  uint32_t overruns;             /* a block became ready while its predecessor was unprocessed */
  uint32_t sequence_errors;      /* ISR order violated (half/full out of sequence) */
  int32_t dc_state[ZS_PDM_CHANNELS];
  int32_t dc_x1[ZS_PDM_CHANNELS];
  int16_t peak[ZS_PDM_CHANNELS];  /* absolute peak of the last processed block */
} zs_pdm_capture_t;

zs_pdm_config_t zs_pdm_config_default(void);

bool zs_pdm_capture_init(zs_pdm_capture_t *c, const zs_pdm_config_t *cfg,
                         const int32_t *const dma[ZS_PDM_CHANNELS], zs_audio_ring_t *ring);

/* ISR context: called by the MDF/DMA half-transfer (block 0) and transfer-complete (block 1) callbacks. */
void zs_pdm_capture_on_dma_half(zs_pdm_capture_t *c);
void zs_pdm_capture_on_dma_full(zs_pdm_capture_t *c);

/* Task context: converts one ready block if any; returns true when a block was consumed. */
bool zs_pdm_capture_process(zs_pdm_capture_t *c);

/* Returns true when a block is waiting for process(). */
bool zs_pdm_capture_pending(const zs_pdm_capture_t *c);

/* Sample counter at the *end* of the last processed block (frames pushed into the ring). */
uint64_t zs_pdm_capture_sample_counter(const zs_pdm_capture_t *c);

/*
 * Bench self-test: estimated lag in samples of channel `ch` relative to
 * channel 0 over the last `count` frames of the ring (normalized
 * cross-correlation over +-max_lag).  Returns false when the ring holds too
 * little data or the signal is too weak to correlate.  Synchronous MDF start
 * must give |lag| == 0 on a common source.
 */
bool zs_pdm_capture_channel_lag(const zs_pdm_capture_t *c, unsigned ch, uint32_t count, int max_lag, int *lag_out);

#endif
