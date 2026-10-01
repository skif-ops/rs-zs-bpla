#include "zs_station_pipeline.h"
#include <math.h>
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
  zs_bearing_init(&p->bearing_ctx, NULL);
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
  if (p->last_bearing.valid && p->last_bearing_end == end_sample) {
    const zs_bearing_t *b = &p->last_bearing;
    long az = lroundf(b->azimuth_deg * 100.0f) % 36000L;
    const long sigma = lroundf(b->sigma_deg * 100.0f);
    if (az < 0) az += 36000L;
    d->doa.azimuth_cdeg = (uint16_t)az;
    d->doa.elevation_cdeg = (int16_t)lroundf(b->elevation_deg * 100.0f);
    d->doa.sigma_cdeg = (uint16_t)(sigma > 65535L ? 65535L : sigma);
    d->doa.valid = true;
    d->spatial.tdoa12_us = (int16_t)lroundf(b->tdoa_us[0]);
    d->spatial.tdoa13_us = (int16_t)lroundf(b->tdoa_us[1]);
    d->spatial.tdoa14_us = (int16_t)lroundf(b->tdoa_us[2]);
    d->spatial.residual_us = (uint16_t)lroundf(b->residual_us);
    d->spatial.confidence_u8 = (uint8_t)lroundf(b->confidence * 255.0f);
    d->spatial.geometry_id = p->bearing_ctx.geometry.geometry_id;
    d->spatial.valid_flags = 0x03u;                                   /* TDOAs and direction valid */
  }
  d->sample_rate_hz = ZS_AIR_SAMPLE_RATE;
  d->detector_profile = detector_profile_for(p->hierarchy.family_id);
}

_Static_assert(ZS_PIPELINE_WINDOW_SAMPLES >= ZS_BEARING_FRAME_MEMORY, "the 1 s window lends the bearing frames");
_Static_assert(ZS_AIR_SCRATCH_COMPLEX * sizeof(zs_complex_t) >= sizeof(zs_spatial_gcc_workspace_t), "the gate scratch lends the GCC workspace");

/* Bearing of a CONFIRMED window from the 4-channel ring; the window and the gate scratch are idle by now. */
static void update_bearing(zs_station_pipeline_t *p, uint64_t end_sample) {
  const float t = p->port->temperature_c ? p->port->temperature_c(p->port->ctx) : 15.0f;
  p->last_bearing.valid = false;
  if (!p->ring) return;
  if (zs_bearing_from_ring(&p->bearing_ctx, p->ring, end_sample, ZS_PIPELINE_BEARING_SPAN, t, p->window,
                           (zs_spatial_gcc_workspace_t *)(void *)p->scratch, &p->last_bearing))
    p->last_bearing_end = end_sample;
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
  /* the gate first: with several sources it finds the strongest comb and the others (zs_air_gate.h), and the
     classifier gets the window with the others suppressed, so it classifies the source the station tracks; a
     window with one source reaches the classifier unchanged */
  if (!zs_air_gate_push(&p->gate, pcm, ZS_PIPELINE_WINDOW_SAMPLES, p->scratch, &p->last_gate)) return false;
  if (p->last_gate.secondary_count) {
    if (pcm != p->window) memcpy(p->window, pcm, ZS_PIPELINE_WINDOW_SAMPLES * sizeof(int16_t));
    zs_air_gate_suppress_secondary(p->window, ZS_PIPELINE_WINDOW_SAMPLES, &p->last_gate);
    pcm = p->window;
    p->separated_windows++;
  }
  if (!p->port->extract(p->port->ctx, pcm, ZS_PIPELINE_WINDOW_SAMPLES, p->features)) return false;
  p->last_window = zs_classifier_predict_centroid(p->features);
  (void)zs_classifier_consensus_push(&p->votes, p->last_window, &p->classification, &p->hierarchy);
  p->presence = zs_presence_evaluate(&p->votes, &p->last_gate);
  p->windows++;
  switch (p->presence.level) {
    case ZS_PRESENCE_CONFIRMED: p->confirmed_windows++; break;
    case ZS_PRESENCE_SUSPECT: p->suspect_windows++; break;
    case ZS_PRESENCE_ENGINE_UNCONFIRMED: p->engine_windows++; break;
    default: break;
  }
  if (p->presence.level == ZS_PRESENCE_CONFIRMED) {
    update_bearing(p, end_sample);
    if (!p->confirmed) {                                                            /* rising edge */
      p->confirmed = true;
      emit(p, end_sample);
      p->track_event_id = ((uint64_t)p->port->boot_id << 32) | p->seq_no;
    } else if (++p->windows_since_event >= period) emit(p, end_sample);            /* keep-alive update */
    if (p->last_bearing.valid && p->port->bearing) p->port->bearing(p->port->ctx, &p->last_bearing, end_sample, p->track_event_id);
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
  p->ring = ring;
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
