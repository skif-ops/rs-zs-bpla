#ifndef ZS_TYPES_H
#define ZS_TYPES_H

#include <stdbool.h>
#include <stdint.h>

#define ZS_FEATURE_COUNT 43u
#define ZS_MAX_LORA_HOPS 5u
#define ZS_MODEL_MAX_CLASSES 16u

typedef enum {
  ZS_CLASS_UNKNOWN = 0,
  ZS_CLASS_PISTON_UAV = 1,
  ZS_CLASS_REACTIVE_UAV = 2,
  ZS_CLASS_ELECTRIC_UAV = 3,
  ZS_CLASS_ROAD_TRAFFIC = 10,
  ZS_CLASS_AIRCRAFT = 11,
  ZS_CLASS_HELICOPTER = 12,
  ZS_CLASS_GENERATOR = 13,
  ZS_CLASS_AGRICULTURAL = 14,
  ZS_CLASS_BIRDS = 15,
  ZS_CLASS_INSECTS = 16,
  ZS_CLASS_GUNFIRE = 17,
  ZS_CLASS_WIND = 18
} zs_class_id_t;

typedef enum {
  ZS_FAMILY_UNKNOWN = 0,
  ZS_FAMILY_PROP_PISTON = 1,
  ZS_FAMILY_ROTOR_ELECTRIC = 2,
  ZS_FAMILY_TURBINE_JET = 3
} zs_family_id_t;

typedef enum {
  ZS_TYPE_UNKNOWN = 0,
  ZS_TYPE_LUTYI = 1,
  ZS_TYPE_FP1 = 2,
  ZS_TYPE_FP2 = 3,
  ZS_TYPE_OTHER = 254
} zs_type_id_t;

typedef enum {
  ZS_DECISION_UNKNOWN = 0,
  ZS_DECISION_CANDIDATE = 1,
  ZS_DECISION_PROVISIONAL = 2,
  ZS_DECISION_STABLE = 3,
  ZS_DECISION_UNSUPPORTED = 4
} zs_decision_status_t;

typedef enum {
  ZS_MOTION_UNKNOWN = 0,
  ZS_MOTION_APPROACH = 1,
  ZS_MOTION_PASSING = 2,
  ZS_MOTION_RECEDE = 3
} zs_motion_hint_t;

typedef enum {
  ZS_ROUTE_LTE = 0,
  ZS_ROUTE_NBIOT = 1,
  ZS_ROUTE_2G = 2,
  ZS_ROUTE_LORA = 3,
  ZS_ROUTE_BLE = 4,
  ZS_ROUTE_TEST = 5
} zs_route_t;

typedef struct {
  int32_t lat_e7, lon_e7, alt_dm;
  uint16_t pos_accuracy_m;
  uint8_t altitude_source;
} zs_position_t;

typedef struct {
  uint8_t fix_type, satellites;
  uint16_t hdop_x100;
  bool pps_ok, jam, spoof;
  uint32_t expected_time_error_us;
} zs_gnss_t;

typedef struct {
  uint8_t class_id, confidence_u8;
  bool unknown;
} zs_classification_t;

typedef struct {
  uint8_t family_id;
  uint8_t family_confidence_u8;
  uint8_t type_id;
  uint8_t type_confidence_u8;
  uint8_t family_status;
  uint8_t type_status;
} zs_hier_classification_t;

typedef struct {
  int16_t height_dm;
  uint16_t height_sigma_dm;
  uint16_t speed_dmps;
  uint16_t speed_sigma_dmps;
  uint8_t confidence_u8;
  uint8_t valid_flags; /* bit0 height, bit1 speed */
  uint8_t motion_hint;
} zs_single_station_estimate_t;

typedef struct {
  int16_t azimuth_cdeg, elevation_cdeg;
  uint16_t sigma_cdeg;
  bool valid;
} zs_doa_t;

typedef struct {
  int16_t tdoa12_us;
  int16_t tdoa13_us;
  int16_t tdoa14_us;
  uint16_t residual_us;
  uint8_t confidence_u8;
  uint8_t geometry_id;
  uint8_t valid_flags; /* bit0 reference TDOAs valid, bit1 direction valid */
} zs_spatial_info_t;

typedef struct {
  uint8_t battery_pct;
  uint16_t battery_mv, solar_mv;
  int16_t temperature_c10;
} zs_power_t;

typedef struct {
  zs_route_t transport;
  uint8_t hop_count;
  int16_t rssi_dbm, snr_db10;
  uint32_t gateway_id;
} zs_route_status_t;

typedef struct {
  uint8_t schema_ver;
  uint32_t station_id, seq_no, boot_id;
  uint64_t event_id;
  int64_t event_time_us;
  zs_position_t station;
  zs_gnss_t gnss;
  zs_classification_t classification;
  zs_hier_classification_t hierarchy;
  zs_single_station_estimate_t single_station;
  float features[ZS_FEATURE_COUNT];
  zs_doa_t doa;
  zs_spatial_info_t spatial;
  zs_power_t power;
  zs_route_status_t route;
  uint16_t sample_rate_hz;
  uint8_t detector_profile;
} zs_detection_t;

#endif
