#include "zs_event_receipt.h"

#include <string.h>

#define EVENT_RECEIPT_SCHEMA UINT64_C(1)
#define EVENT_RECEIPT_MESSAGE_TYPE UINT64_C(6)

typedef struct {
  const uint8_t *data;
  size_t size;
  size_t offset;
} reader_t;

static bool read_byte(reader_t *reader, uint8_t *value) {
  if (reader->offset >= reader->size) return false;
  *value = reader->data[reader->offset++];
  return true;
}

static bool read_uint(reader_t *reader, uint64_t *value) {
  uint8_t initial, ai;
  unsigned bytes;
  uint64_t decoded = 0u;
  if (!read_byte(reader, &initial) || (initial >> 5) != 0u) return false;
  ai = initial & 0x1fu;
  if (ai < 24u) {
    *value = ai;
    return true;
  }
  if (ai == 24u) bytes = 1u;
  else if (ai == 25u) bytes = 2u;
  else if (ai == 26u) bytes = 4u;
  else if (ai == 27u) bytes = 8u;
  else return false;
  for (unsigned i = 0u; i < bytes; ++i) {
    uint8_t byte;
    if (!read_byte(reader, &byte)) return false;
    decoded = (decoded << 8) | byte;
  }
  if ((bytes == 1u && decoded < 24u) ||
      (bytes == 2u && decoded <= UINT8_MAX) ||
      (bytes == 4u && decoded <= UINT16_MAX) ||
      (bytes == 8u && decoded <= UINT32_MAX))
    return false;
  *value = decoded;
  return true;
}

static bool read_key(reader_t *reader, uint64_t expected) {
  uint64_t key;
  return read_uint(reader, &key) && key == expected;
}

zs_event_receipt_status_t zs_event_receipt_decode(
    const uint8_t *payload,
    size_t payload_size,
    uint32_t expected_station_id,
    zs_event_receipt_t *receipt) {
  reader_t reader;
  zs_event_receipt_t decoded;
  uint64_t value;
  uint8_t byte;
  if (!payload || !receipt || expected_station_id == 0u)
    return ZS_EVENT_RECEIPT_STATUS_INVALID_ARGUMENT;
  if (payload_size == 0u || payload_size > ZS_EVENT_RECEIPT_MAX_BYTES)
    return ZS_EVENT_RECEIPT_STATUS_INVALID_SIZE;
  reader = (reader_t){payload, payload_size, 0u};
  memset(&decoded, 0, sizeof(decoded));
  if (!read_byte(&reader, &byte) || byte != 0xa7u ||
      !read_key(&reader, 0u) || !read_uint(&reader, &value))
    return ZS_EVENT_RECEIPT_STATUS_INVALID_CBOR;
  if (value != EVENT_RECEIPT_SCHEMA)
    return ZS_EVENT_RECEIPT_STATUS_UNSUPPORTED_SCHEMA;
  if (!read_key(&reader, 1u) || !read_uint(&reader, &value))
    return ZS_EVENT_RECEIPT_STATUS_INVALID_CBOR;
  if (value != EVENT_RECEIPT_MESSAGE_TYPE)
    return ZS_EVENT_RECEIPT_STATUS_UNSUPPORTED_SCHEMA;
  if (!read_key(&reader, 2u) || !read_uint(&reader, &value) ||
      value == 0u || value > UINT32_MAX)
    return ZS_EVENT_RECEIPT_STATUS_INVALID_CBOR;
  decoded.station_id = (uint32_t)value;
  if (decoded.station_id != expected_station_id)
    return ZS_EVENT_RECEIPT_STATUS_STATION_MISMATCH;
  if (!read_key(&reader, 3u) || !read_uint(&reader, &value) ||
      value > UINT32_MAX)
    return ZS_EVENT_RECEIPT_STATUS_INVALID_CBOR;
  decoded.boot_id = (uint32_t)value;
  if (!read_key(&reader, 4u) || !read_uint(&reader, &value) ||
      value > UINT32_MAX)
    return ZS_EVENT_RECEIPT_STATUS_INVALID_CBOR;
  decoded.seq_no = (uint32_t)value;
  if (!read_key(&reader, 5u) || !read_uint(&reader, &value) || value == 0u)
    return ZS_EVENT_RECEIPT_STATUS_INVALID_CBOR;
  decoded.event_id = value;
  if (!read_key(&reader, 6u) || !read_byte(&reader, &byte) || byte != 0x58u ||
      !read_byte(&reader, &byte) || byte != ZS_SHA256_DIGEST_BYTES ||
      reader.size - reader.offset != ZS_SHA256_DIGEST_BYTES)
    return ZS_EVENT_RECEIPT_STATUS_INVALID_CBOR;
  memcpy(decoded.payload_sha256, &reader.data[reader.offset],
         ZS_SHA256_DIGEST_BYTES);
  reader.offset += ZS_SHA256_DIGEST_BYTES;
  if (reader.offset != reader.size)
    return ZS_EVENT_RECEIPT_STATUS_INVALID_CBOR;
  *receipt = decoded;
  return ZS_EVENT_RECEIPT_STATUS_OK;
}

static bool is_ascii_alnum(uint8_t value) {
  return (value >= (uint8_t)'A' && value <= (uint8_t)'Z') ||
         (value >= (uint8_t)'a' && value <= (uint8_t)'z') ||
         (value >= (uint8_t)'0' && value <= (uint8_t)'9');
}

static bool tenant_valid(const uint8_t *tenant, size_t tenant_size) {
  if (!tenant || tenant_size == 0u ||
      tenant_size > ZS_EVENT_RECEIPT_TENANT_MAX_BYTES ||
      !is_ascii_alnum(tenant[0]))
    return false;
  for (size_t i = 1u; i < tenant_size; ++i) {
    if (!is_ascii_alnum(tenant[i]) && tenant[i] != (uint8_t)'_' &&
        tenant[i] != (uint8_t)'-')
      return false;
  }
  return true;
}

static size_t write_station_id(uint32_t station_id, uint8_t *output) {
  uint8_t reverse[10];
  size_t size = 0u;
  do {
    reverse[size++] = (uint8_t)('0' + station_id % 10u);
    station_id /= 10u;
  } while (station_id != 0u);
  for (size_t i = 0u; i < size; ++i) output[i] = reverse[size - i - 1u];
  return size;
}

bool zs_event_receipt_transport_init(
    zs_event_receipt_transport_t *transport,
    uint32_t station_id,
    const uint8_t *tenant,
    size_t tenant_size) {
  static const uint8_t prefix[] = {'z', 's', '/', 'v', '1', '/'};
  static const uint8_t suffix[] = {'/', 'r', 'e', 'c', 'e', 'i', 'p', 't'};
  size_t offset = 0u;
  if (!transport) return false;
  memset(transport, 0, sizeof(*transport));
  if (station_id == 0u || !tenant_valid(tenant, tenant_size) ||
      sizeof(prefix) + tenant_size + 1u + 10u + sizeof(suffix) >
          sizeof(transport->topic))
    return false;
  memcpy(&transport->topic[offset], prefix, sizeof(prefix));
  offset += sizeof(prefix);
  memcpy(&transport->topic[offset], tenant, tenant_size);
  offset += tenant_size;
  transport->topic[offset++] = (uint8_t)'/';
  offset += write_station_id(station_id, &transport->topic[offset]);
  memcpy(&transport->topic[offset], suffix, sizeof(suffix));
  offset += sizeof(suffix);
  transport->station_id = station_id;
  transport->topic_size = offset;
  return true;
}

zs_event_receipt_result_t zs_event_receipt_transport_handle(
    const zs_event_receipt_transport_t *transport,
    const zs_event_outbox_io_t *outbox,
    const zs_event_outbox_item_t *item,
    const uint8_t *topic,
    size_t topic_size,
    const uint8_t *payload,
    size_t payload_size,
    uint8_t qos,
    bool retained,
    zs_event_receipt_status_t *decode_status) {
  zs_event_receipt_t receipt;
  zs_event_outbox_result_t result;
  if (decode_status) *decode_status = ZS_EVENT_RECEIPT_STATUS_INVALID_ARGUMENT;
  if (!transport || transport->station_id == 0u ||
      transport->topic_size == 0u ||
      transport->topic_size > sizeof(transport->topic) || !outbox || !item ||
      !topic || topic_size == 0u || !payload || payload_size == 0u ||
      !decode_status)
    return ZS_EVENT_RECEIPT_INVALID_ARGUMENT;
  if (topic_size != transport->topic_size ||
      memcmp(topic, transport->topic, transport->topic_size) != 0)
    return ZS_EVENT_RECEIPT_REJECTED_TOPIC;
  if (qos != ZS_EVENT_RECEIPT_QOS || retained)
    return ZS_EVENT_RECEIPT_REJECTED_DELIVERY;
  *decode_status = zs_event_receipt_decode(
      payload, payload_size, transport->station_id, &receipt);
  if (*decode_status != ZS_EVENT_RECEIPT_STATUS_OK)
    return ZS_EVENT_RECEIPT_REJECTED_RECEIPT;
  if (item->station_id != transport->station_id ||
      receipt.boot_id != item->boot_id || receipt.seq_no != item->seq_no ||
      receipt.event_id != item->event_id) {
    *decode_status = ZS_EVENT_RECEIPT_STATUS_ITEM_MISMATCH;
    return ZS_EVENT_RECEIPT_REJECTED_RECEIPT;
  }
  if (memcmp(receipt.payload_sha256, item->payload_sha256,
             ZS_SHA256_DIGEST_BYTES) != 0) {
    *decode_status = ZS_EVENT_RECEIPT_STATUS_SHA256_MISMATCH;
    return ZS_EVENT_RECEIPT_REJECTED_RECEIPT;
  }
  result = zs_event_outbox_mark_application_acked(outbox, item);
  if (result == ZS_EVENT_OUTBOX_OK) return ZS_EVENT_RECEIPT_APPLIED;
  if (result == ZS_EVENT_OUTBOX_ALREADY_ACKED)
    return ZS_EVENT_RECEIPT_ALREADY_APPLIED;
  if (result == ZS_EVENT_OUTBOX_INVALID_ARGUMENT)
    return ZS_EVENT_RECEIPT_INVALID_ARGUMENT;
  if (result == ZS_EVENT_OUTBOX_STALE_ITEM) {
    *decode_status = ZS_EVENT_RECEIPT_STATUS_ITEM_MISMATCH;
    return ZS_EVENT_RECEIPT_REJECTED_RECEIPT;
  }
  return ZS_EVENT_RECEIPT_STORAGE_ERROR;
}
