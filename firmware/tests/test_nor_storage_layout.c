#include "zs_nor_storage_layout.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define CAPACITY_64_MIB (64u * 1024u * 1024u)
#define ERASE_4_KIB 4096u

static int unused_command(void *ctx, uint8_t opcode, uint32_t address,
                          uint8_t address_bytes, const uint8_t *tx,
                          size_t tx_size, uint8_t *rx, size_t rx_size) {
  (void)ctx;
  (void)opcode;
  (void)address;
  (void)address_bytes;
  (void)tx;
  (void)tx_size;
  (void)rx;
  (void)rx_size;
  return -1;
}

static uint32_t unused_millis(void *ctx) {
  (void)ctx;
  return 0u;
}

static void unused_delay(void *ctx, uint32_t millis) {
  (void)ctx;
  (void)millis;
}

static zs_nor_t make_nor(void) {
  const zs_nor_port_t port = {
      NULL, unused_command, unused_millis, unused_delay};
  const zs_nor_geometry_t geometry = zs_nor_geometry_64m_4byte();
  zs_nor_t nor;
  assert(zs_nor_init(&nor, &port, &geometry));
  return nor;
}

static uint64_t archive_end(const zs_archive_layout_t *archive) {
  return (uint64_t)archive->base_address + archive->prehistory_ring_bytes +
         (uint64_t)archive->slot_bytes * archive->slot_count;
}

static void test_default_64m_tail_partition(void) {
  zs_nor_storage_layout_t layout;

  assert(zs_nor_storage_layout_make(
      CAPACITY_64_MIB, ERASE_4_KIB, 256u, &layout));
  assert(layout.capacity_bytes == CAPACITY_64_MIB);
  assert(layout.erase_block_bytes == ERASE_4_KIB);
  assert(layout.outbox_slot_count == 256u);
  assert(layout.outbox_partition_bytes == 1024u * 1024u);
  assert(layout.outbox_base_address == 63u * 1024u * 1024u);
  assert(layout.archive.base_address == 0u);
  assert(layout.archive.total_bytes == layout.outbox_base_address);
  assert(layout.archive.slot_count == ZS_ARCHIVE_DEFAULT_SLOTS);
  assert(layout.archive.slot_bytes == 8163328u);
  assert(layout.archive.prehistory_ring_bytes == 41570304u);
  assert(layout.archive.max_pre_bytes == 480120u);
  assert(layout.archive.max_post_bytes == 7680000u);
  assert(archive_end(&layout.archive) == layout.outbox_base_address);
  assert((uint64_t)layout.outbox_base_address +
             layout.outbox_partition_bytes ==
         layout.capacity_bytes);
}

static void test_slot_count_remains_a_target_input(void) {
  zs_nor_storage_layout_t one;
  zs_nor_storage_layout_t many;

  assert(zs_nor_storage_layout_make(
      CAPACITY_64_MIB, ERASE_4_KIB, 1u, &one));
  assert(zs_nor_storage_layout_make(
      CAPACITY_64_MIB, ERASE_4_KIB, 1024u, &many));
  assert(one.outbox_partition_bytes == ERASE_4_KIB);
  assert(many.outbox_partition_bytes == 4u * 1024u * 1024u);
  assert(one.outbox_base_address > many.outbox_base_address);
  assert(archive_end(&one.archive) <= one.outbox_base_address);
  assert(archive_end(&many.archive) <= many.outbox_base_address);
}

static void test_capacity_and_geometry_guards(void) {
  zs_nor_storage_layout_t layout;
  zs_nor_storage_layout_t zero;

  memset(&zero, 0, sizeof(zero));
  memset(&layout, 0xa5, sizeof(layout));
  assert(!zs_nor_storage_layout_make(
      CAPACITY_64_MIB, ERASE_4_KIB, 256u, NULL));
  assert(!zs_nor_storage_layout_make(
      CAPACITY_64_MIB, ERASE_4_KIB, 0u, &layout));
  assert(memcmp(&layout, &zero, sizeof(layout)) == 0);
  assert(!zs_nor_storage_layout_make(
      CAPACITY_64_MIB - 1u, ERASE_4_KIB, 1u, &layout));
  assert(!zs_nor_storage_layout_make(
      CAPACITY_64_MIB, 512u, 1u, &layout));
  assert(!zs_nor_storage_layout_make(
      CAPACITY_64_MIB, ERASE_4_KIB, 11000u, &layout));
  assert(!zs_nor_storage_layout_make(
      ERASE_4_KIB, ERASE_4_KIB, 1u, &layout));
}

static void test_shared_binding_caps_archive_at_outbox(void) {
  zs_nor_t nor = make_nor();
  zs_nor_storage_bindings_t bindings;
  zs_archive_storage_t archive_storage;
  zs_event_outbox_io_t outbox_io;
  zs_archive_t archive;
  zs_archive_layout_t overlapping;

  assert(zs_nor_storage_bind(
      &bindings, &nor, 256u, &archive_storage, &outbox_io));
  assert(archive_storage.ctx == &bindings.archive_adapter);
  assert(archive_storage.size_bytes == bindings.layout.outbox_base_address);
  assert(archive_storage.erase_block_bytes == ERASE_4_KIB);
  assert(outbox_io.ctx == &bindings.outbox_adapter);
  assert(outbox_io.slot_count == 256u);
  assert(bindings.outbox_adapter.base_address ==
         bindings.layout.outbox_base_address);
  assert((uint64_t)bindings.outbox_adapter.base_address +
             (uint64_t)outbox_io.slot_count * ERASE_4_KIB ==
         nor.geometry.capacity_bytes);
  assert(zs_archive_init(
      &archive, &archive_storage, &bindings.layout.archive));

  overlapping = bindings.layout.archive;
  overlapping.total_bytes += ERASE_4_KIB;
  assert(!zs_archive_init(&archive, &archive_storage, &overlapping));
}

static void test_shared_binding_failure_is_atomic(void) {
  zs_nor_t nor = make_nor();
  zs_nor_storage_bindings_t bindings;
  zs_nor_storage_bindings_t zero_bindings;
  zs_archive_storage_t archive_storage;
  zs_archive_storage_t zero_archive_storage;
  zs_event_outbox_io_t outbox_io;
  zs_event_outbox_io_t zero_outbox_io;

  memset(&zero_bindings, 0, sizeof(zero_bindings));
  memset(&zero_archive_storage, 0, sizeof(zero_archive_storage));
  memset(&zero_outbox_io, 0, sizeof(zero_outbox_io));
  memset(&bindings, 0xa5, sizeof(bindings));
  memset(&archive_storage, 0xa5, sizeof(archive_storage));
  memset(&outbox_io, 0xa5, sizeof(outbox_io));
  nor.port.millis = NULL;

  assert(!zs_nor_storage_bind(
      &bindings, &nor, 256u, &archive_storage, &outbox_io));
  assert(memcmp(&bindings, &zero_bindings, sizeof(bindings)) == 0);
  assert(memcmp(&archive_storage, &zero_archive_storage,
                sizeof(archive_storage)) == 0);
  assert(memcmp(&outbox_io, &zero_outbox_io, sizeof(outbox_io)) == 0);
  assert(!zs_nor_storage_bind(NULL, &nor, 256u,
                              &archive_storage, &outbox_io));
}

int main(void) {
  test_default_64m_tail_partition();
  test_slot_count_remains_a_target_input();
  test_capacity_and_geometry_guards();
  test_shared_binding_caps_archive_at_outbox();
  test_shared_binding_failure_is_atomic();
  puts("zs_nor_storage_layout_tests: OK");
  return 0;
}
