#include "zs_station_pipeline.h"
#include <string.h>

/* Most frequent UAV class among the weak-or-better votes: what the event names before the 5/8 type consensus. */
static uint8_t leading_uav_class(const zs_classifier_consensus_t *v) {
  uint8_t best = ZS_CLASS_UNKNOWN, best_n = 0u;
  for (uint8_t c = ZS_CLASS_PISTON_UAV; c <= ZS_CLASS_ELECTRIC_UAV; c++) {
    uint8_t n = 0u;
    for (uint8_t i = 0u; i < v->count; i++) if (v->class_id[i] == c && v->confidence_u8[i] >= ZS_PRESENCE_WEAK_CONFIDENCE_U8) n++;
    if (n > best_n) { best_n = n; best = c; }
  }
  return best;
}

static uint8_t detector_profile_for(uint8_t family) {
  return family == ZS_FAMILY_PROP_PISTON ? 1u : (family == ZS_FAMILY_TURBINE_JET ? 2u : 0u);
}

bool zs_station_pipeline_init(zs_station_pipeline_t *p, const zs_station_pipeline_port_t *port,
                              zs_complex_t *scratch, int16_t *window) {
  if (!p || !port || !port->extract || !port->emit || !scratch || !window || port->channel >= ZS_AUDIO_CHANNELS) return false;
  memset(p, 0, sizeof(*p));
  p->port = port;
  p->scratch = scratch;
  p->window = window;
  zs_classifier_consensus_init(&p->votes);
  zs_air_gate_init(&p->gate);
  p->classification.unknown = true;
  p->next_window_end = ZS_PIPELINE_WINDOW_SAMPLES;
  return true;
}

void zs_station_pipeline_fill_detection(const zs_station_pipeline_t *p, uint64_t end_sample, zs_detection_t *d) {
  memset(d, 0, sizeof(*d));
  d->schema_ver = 4u;
  d->station_id = p->port->station_id;
  d->boot_id = p->port->boot_id;
  d->seq_no = p->seq_no;
  d->event_id = ((uint64_t)p->port->boot_id << 32) | p->seq_no;
  d->event_time_us = p->port->sample_time_us ? p->port->sample_time_us(p->port->ctx, end_sample) : 0;
  d->classification = p->classification;
  d->classification.confidence_u8 = p->presence.confidence_u8;     /* level 1 confidence governs the event */
  d->hierarchy = p->hierarchy;
  if (p->classification.unknown && p->presence.level == ZS_PRESENCE_CONFIRMED) {
    /* confirmed at level 1 before the 5/8 type consensus: name the leading UAV class, keep `unknown` set */
    d->classification.class_id = leading_uav_class(&p->votes);
    if (d->hierarchy.family_status == ZS_DECISION_UNKNOWN) d->hierarchy.family_status = ZS_DECISION_CANDIDATE;
  }
  memcpy(d->features, p->features, sizeof(d->features));
  d->sample_rate_hz = ZS_AIR_SAMPLE_RATE;
  d->detector_profile = detector_profile_for(p->hierarchy.family_id);
}

static void emit(zs_station_pipeline_t *p, uint64_t end_sample) {
  zs_detection_t d;
  p->seq_no++;
  zs_station_pipeline_fill_detection(p, end_sample, &d);
  if (p->port->emit(p->port->ctx, &d)) p->events_emitted++; else p->events_refused++;
  p->windows_since_event = 0u;
}

bool zs_station_pipeline_push_window(zs_station_pipeline_t *p, const int16_t *pcm, uint64_t end_sample) {
  const uint8_t period = p->port->update_period_windows ? p->port->update_period_windows : ZS_PIPELINE_DEFAULT_UPDATE_WINDOWS;
  if (!p || !pcm) return false;
  if (!p->port->extract(p->port->ctx, pcm, ZS_PIPELINE_WINDOW_SAMPLES, p->features)) return false;
  p->last_window = zs_classifier_predict_centroid(p->features);
  (void)zs_classifier_consensus_push(&p->votes, p->last_window, &p->classification, &p->hierarchy);
  if (!zs_air_gate_push(&p->gate, pcm, ZS_PIPELINE_WINDOW_SAMPLES, p->scratch, &p->last_gate)) return false;
  p->presence = zs_presence_evaluate(&p->votes, &p->last_gate);
  p->windows++;
  switch (p->presence.level) {
    case ZS_PRESENCE_CONFIRMED: p->confirmed_windows++; break;
    case ZS_PRESENCE_SUSPECT: p->suspect_windows++; break;
    case ZS_PRESENCE_ENGINE_UNCONFIRMED: p->engine_windows++; break;
    default: break;
  }
  if (p->presence.level == ZS_PRESENCE_CONFIRMED) {
    if (!p->confirmed) { p->confirmed = true; emit(p, end_sample); }               /* rising edge */
    else if (++p->windows_since_event >= period) emit(p, end_sample);              /* keep-alive update */
  } else {
    p->confirmed = false;
    p->windows_since_event = 0u;
  }
  return true;
}

bool zs_station_pipeline_fetch(zs_station_pipeline_t *p, const zs_audio_ring_t *ring) {
  if (!p || !ring || p->pending) return false;
  /* windows whose start the ring has already overwritten are lost: skip to the oldest one still complete */
  if (ring->total_frames > ring->frames_capacity) {
    const uint64_t oldest_end = ring->total_frames - ring->frames_capacity + ZS_PIPELINE_WINDOW_SAMPLES;
    while (p->next_window_end < oldest_end) { p->next_window_end += ZS_PIPELINE_HOP_SAMPLES; p->windows_dropped++; }
  }
  if (p->next_window_end > ring->total_frames) return false;
  if (!zs_audio_ring_copy_mono(ring, p->next_window_end, ZS_PIPELINE_WINDOW_SAMPLES, p->window, p->port->channel)) return false;
  p->pending_end = p->next_window_end;
  p->pending = true;
  p->next_window_end += ZS_PIPELINE_HOP_SAMPLES;
  return true;
}

bool zs_station_pipeline_run_pending(zs_station_pipeline_t *p) {
  bool ok;
  if (!p || !p->pending) return false;
  ok = zs_station_pipeline_push_window(p, p->window, p->pending_end);
  p->pending = false;
  return ok;
}

unsigned zs_station_pipeline_poll(zs_station_pipeline_t *p, const zs_audio_ring_t *ring) {
  unsigned done = 0u;
  while (zs_station_pipeline_fetch(p, ring)) { if (!zs_station_pipeline_run_pending(p)) break; done++; }
  return done;
}
