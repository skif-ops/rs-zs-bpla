#include "zs_nor_storage_layout.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define CAPACITY_64_MIB (64u * 1024u * 1024u)
#define ERASE_4_KIB 4096u

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

int main(void) {
  test_default_64m_tail_partition();
  test_slot_count_remains_a_target_input();
  test_capacity_and_geometry_guards();
  puts("zs_nor_storage_layout_tests: OK");
  return 0;
}
