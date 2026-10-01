#ifndef ZS_MODEL_H
#define ZS_MODEL_H
/*
 * Station classifier model as data (MQTT ICD addendum I): the nearest-centroid model of zs_classifier can come from a
 * signed model package instead of the table compiled into the firmware, so a retrained model reaches the stations
 * without a firmware release.
 *
 * Package "DIOM" format 1, little-endian, 4-byte aligned:
 *   0  magic u32 "DIOM" | 4 format u16 = 1 | 6 feature_count u16 = 43 | 8 class_count u16 (1..ZS_MODEL_PACKAGE_MAX_CLASSES)
 *   10 reserved u16 = 0 | 12 version u32 >= 1 | 16 feature_set u32 (ZS_MODEL_FEATURE_SET) | 20 reserved 12 bytes = 0
 *   32 mean f32[43] | std f32[43] | class_id u8[class_count] padded with zeros to 4 | radius f32[class_count]
 *   | centroid f32[class_count][43]
 * The size is exactly ZS_MODEL_BYTES(class_count).  Every float is finite, std >= 0, radius > 0, class ids are
 * zs_class_id_t values other than UNKNOWN.
 *
 * The built-in model (firmware/generated/zs_model_centroids.h, version 0) is always there; one model loaded from a
 * package lives in RAM.  The pipeline predicts with the active one; activating a package is a seqlock write, so the
 * pipeline task never classifies with a half-written table (a window racing the write uses the built-in model).
 */
#include "zs_classifier.h"
#include "zs_types.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ZS_MODEL_MAGIC 0x4D4F4944u         /* "DIOM" little-endian */
#define ZS_MODEL_FORMAT 1u
#define ZS_MODEL_FEATURE_SET 1u            /* the 43 features of zs_dsp, server/tools/golden/feature_order.txt */
#define ZS_MODEL_HEADER_BYTES 32u
#define ZS_MODEL_PACKAGE_MAX_CLASSES 96u
#define ZS_MODEL_BYTES(n) (ZS_MODEL_HEADER_BYTES + 2u * 4u * ZS_FEATURE_COUNT + (((n) + 3u) & ~3u) + 4u * (n) + 4u * ZS_FEATURE_COUNT * (n))
#define ZS_MODEL_PACKAGE_MAX_BYTES ZS_MODEL_BYTES(ZS_MODEL_PACKAGE_MAX_CLASSES)
#define ZS_MODEL_DESCRIBE_MAX 16u

typedef struct {
  uint32_t version;                        /* 0 = built-in */
  uint32_t feature_set;
  uint16_t class_count;
  const float *mean;
  const float *std;
  const uint8_t *class_id;
  const float *radius;
  const float (*centroid)[ZS_FEATURE_COUNT];
} zs_model_t;

typedef struct {
  float mean[ZS_FEATURE_COUNT];
  float std[ZS_FEATURE_COUNT];
  uint8_t class_id[ZS_MODEL_PACKAGE_MAX_CLASSES];
  float radius[ZS_MODEL_PACKAGE_MAX_CLASSES];
  float centroid[ZS_MODEL_PACKAGE_MAX_CLASSES][ZS_FEATURE_COUNT];
} zs_model_storage_t;

typedef enum {
  ZS_MODEL_OK = 0,
  ZS_MODEL_ERR_READ,          /* the reader failed */
  ZS_MODEL_ERR_HEADER,        /* magic, format, feature count, reserved bytes, version 0 */
  ZS_MODEL_ERR_FEATURE_SET,   /* trained for another feature extractor */
  ZS_MODEL_ERR_SIZE,          /* class count out of range or size != ZS_MODEL_BYTES(class_count) */
  ZS_MODEL_ERR_VALUE          /* a non-finite number, std < 0, radius <= 0 or an unknown class id */
} zs_model_status_t;

/* Reads `size` bytes at `offset` of the package. */
typedef bool (*zs_model_read_fn)(void *ctx, uint32_t offset, uint8_t *data, size_t size);

/* Validates a package of `size` bytes read through `read`; with storage the tables are copied into it and *model
   points at them (storage == NULL: check only, *model gets the header fields and NULL tables). */
zs_model_status_t zs_model_load(zs_model_read_fn read, void *ctx, uint32_t size, zs_model_storage_t *storage, zs_model_t *model);
zs_model_status_t zs_model_parse(const uint8_t *bytes, size_t size, zs_model_storage_t *storage, zs_model_t *model);

const zs_model_t *zs_model_builtin(void);
/* The nearest centroid of one model (z-score, Euclidean distance, confidence 1 - d / (1.5 radius)). */
zs_classifier_result_t zs_model_predict(const zs_model_t *model, const float features[ZS_FEATURE_COUNT]);
/* Heartbeat model text (key 9): "c<classes>" for the built-in model, "m<version>" for a package. */
size_t zs_model_describe(const zs_model_t *model, char *out, size_t cap);

/* ---- the active model ---- */
/* Loads a package into the RAM model and makes it active; the built-in model stays active when it fails (or its
   version is not `expected_version`, unless that is 0). */
zs_model_status_t zs_model_activate(zs_model_read_fn read, void *ctx, uint32_t size, uint32_t expected_version);
void zs_model_activate_builtin(void);
uint32_t zs_model_active_version(void);                       /* 0 = built-in */
size_t zs_model_active_describe(char *out, size_t cap);
zs_classifier_result_t zs_model_predict_active(const float features[ZS_FEATURE_COUNT]);

#endif
