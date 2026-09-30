/*
 * EVT-PRE-20 Rev.A application linker script for STM32U585VIT6Q, A/B banks
 * (MQTT_TLS_ICD_v0_1 addendum F).
 *
 * Derived from STM32U585VITXQ_ENGINEERING_FLASH.ld (same RAM map). The image
 * lives in one 1 MiB bank at 0x08000000 (whichever physical bank SWAP_BANK
 * maps there) and ends before the bank's last 8 KiB page, the A/B boot record;
 * the other bank at 0x08100000 receives the next image. The 32-byte .fw_info
 * block sits at image offset 0x400, right after the vector table.
 * TrustZone stays disabled (engineering profile); secure boot is not part of it.
 */

ENTRY(Reset_Handler)

_Min_Heap_Size = 0x400;
_Min_Stack_Size = 0x2000;

MEMORY
{
  FLASH  (rx)  : ORIGIN = 0x08000000, LENGTH = 1016K   /* bank 0x08000000..0x080FE000; the record page follows */
  RAM123 (xrw) : ORIGIN = 0x20000000, LENGTH = 768K
  SRAM4  (xrw) : ORIGIN = 0x28000000, LENGTH = 16K
}

_estack = ORIGIN(RAM123) + LENGTH(RAM123);
_sstack = _estack - _Min_Stack_Size;

SECTIONS
{
  .isr_vector : ALIGN(512)
  {
    KEEP(*(.isr_vector))
  } > FLASH

  .fw_info ORIGIN(FLASH) + 0x400 :
  {
    KEEP(*(.fw_info))
  } > FLASH

  .text :
  {
    *(.text)
    *(.text*)
    *(.glue_7)
    *(.glue_7t)
    *(.eh_frame)
    KEEP(*(.init))
    KEEP(*(.fini))
    _etext = .;
  } > FLASH

  .rodata :
  {
    *(.rodata)
    *(.rodata*)
  } > FLASH

  .ARM.extab :
  {
    *(.ARM.extab* .gnu.linkonce.armextab.*)
  } > FLASH

  .ARM :
  {
    __exidx_start = .;
    *(.ARM.exidx*)
    __exidx_end = .;
  } > FLASH

  .preinit_array :
  {
    PROVIDE_HIDDEN(__preinit_array_start = .);
    KEEP(*(.preinit_array*))
    PROVIDE_HIDDEN(__preinit_array_end = .);
  } > FLASH

  .init_array :
  {
    PROVIDE_HIDDEN(__init_array_start = .);
    KEEP(*(SORT(.init_array.*)))
    KEEP(*(.init_array*))
    PROVIDE_HIDDEN(__init_array_end = .);
  } > FLASH

  .fini_array :
  {
    PROVIDE_HIDDEN(__fini_array_start = .);
    KEEP(*(SORT(.fini_array.*)))
    KEEP(*(.fini_array*))
    PROVIDE_HIDDEN(__fini_array_end = .);
  } > FLASH

  _sidata = LOADADDR(.data);

  .data : ALIGN(8)
  {
    _sdata = .;
    *(.data)
    *(.data*)
    *(.RamFunc)
    *(.RamFunc*)
    _edata = .;
  } > RAM123 AT> FLASH

  .bss (NOLOAD) : ALIGN(8)
  {
    _sbss = .;
    __bss_start__ = _sbss;
    *(.bss)
    *(.bss*)
    *(COMMON)
    _ebss = .;
    __bss_end__ = _ebss;
  } > RAM123

  .retained (NOLOAD) : ALIGN(8)
  {
    /* Link placement only. PWR retention must be configured and measured. */
    _sretained = .;
    *(.retained)
    *(.retained*)
    _eretained = .;
  } > SRAM4

  .heap_stack (NOLOAD) : ALIGN(8)
  {
    PROVIDE(end = .);
    PROVIDE(_end = .);
    . = . + _Min_Heap_Size;
    . = . + _Min_Stack_Size;
    . = ALIGN(8);
  } > RAM123

  .ARM.attributes 0 : { *(.ARM.attributes) }
}

ASSERT(SIZEOF(.isr_vector) > 0, "missing STM32U585 interrupt vector");
ASSERT(ADDR(.fw_info) == 0x08000400 && SIZEOF(.fw_info) == 32, ".fw_info must be the 32-byte block at image offset 0x400");
ASSERT(_eretained <= ORIGIN(SRAM4) + LENGTH(SRAM4), "SRAM4 retained area overflow");
ASSERT(_end <= _sstack, "RAM123 heap/stack collision");
